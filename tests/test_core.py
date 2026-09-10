from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.dedupe import lead_key, merge_leads, normalize_text
from leadflow_agent.models import Lead, QueryPlan, SearchGoal, WebHit
from leadflow_agent.scoring import score_lead
from leadflow_agent.storage import LeadStore


class FakeLocal:
    name = "fake-local"

    def __init__(self):
        self.calls = []

    def search_places(self, query, goal, *, count=20):
        self.calls.append(query)
        if query == "marcenaria":
            return [
                Lead(name="Alpha Móveis", city=goal.city, state=goal.state, phone="13 99999-1111", discovered_query=query, source_provider=self.name),
                Lead(name="Beta Planejados", city=goal.city, state=goal.state, discovered_query=query, source_provider=self.name),
            ]
        return [
            Lead(name="Alpha Moveis", city=goal.city, state=goal.state, phone="(13) 99999-1111", website="https://alpha.example", discovered_query=query, source_provider=self.name),
            Lead(name="Gamma Marcenaria", city=goal.city, state=goal.state, phone="13 98888-2222", discovered_query=query, source_provider=self.name),
        ]

    def search_web(self, query, *, country="BR", count=10):
        return [WebHit(title="Gamma Marcenaria", url="https://gamma.example", query=query)]


class FakeLLM:
    name = "fake-llm"

    def plan_queries(self, goal, *, max_queries=6):
        return QueryPlan(queries=["marcenaria", "móveis planejados"], rationale="test", generated_by=self.name)


class FakeWebDiscovery:
    name = "fake-web"

    def search_web(self, query, *, country="BR", count=10):
        return [
            WebHit(title="Empresa A", url="https://instagram.com/a", description="Empresa A telefone 13 99999-1111", query=query),
            WebHit(title="Lista", url="https://example.com/list", description="Empresa B e Empresa C", query=query),
        ]

    def heuristic_leads(self, hits, goal, *, query):
        return [Lead(name="Empresa A", city=goal.city, state=goal.state, phone="13 99999-1111", source_provider=self.name, discovered_query=query)]


class FakeExtractor:
    name = "fake-extractor"

    def extract_leads(self, hits, goal, *, query, max_leads=20):
        return [
            Lead(name="Empresa A", city=goal.city, state=goal.state, phone="13 99999-1111", source_provider="web+ai", discovered_query=query),
            Lead(name="Empresa B", city=goal.city, state=goal.state, phone="13 98888-2222", source_provider="web+ai", discovered_query=query),
            Lead(name="Empresa C", city=goal.city, state=goal.state, phone="13 97777-3333", source_provider="web+ai", discovered_query=query),
        ]


class CoreTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Móveis & Cia"), "moveis cia")

    def test_lead_key_prefers_phone(self):
        a = Lead(name="A", phone="+55 (13) 99999-1111")
        b = Lead(name="Different", phone="5513999991111")
        self.assertEqual(lead_key(a), lead_key(b))

    def test_merge(self):
        a = Lead(name="A", phone="123", socials=["https://instagram.com/a"])
        b = Lead(name="A", phone="123", website="https://a.example", socials=["https://facebook.com/a"])
        merge_leads(a, b)
        self.assertEqual(a.website, "https://a.example")
        self.assertEqual(len(a.socials), 2)

    def test_score_prefers_missing_site(self):
        lead = score_lead(Lead(name="A", phone="123", review_count=30))
        self.assertGreaterEqual(lead.score, 70)
        self.assertTrue(any("site não identificado" in r for r in lead.score_reasons))

    def test_agent_adapts_until_goal(self):
        provider = FakeLocal()
        agent = LeadResearchAgent(local_search=provider, web_search=provider, llm=FakeLLM())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3))
        self.assertEqual(len(report.leads), 3)
        self.assertEqual(report.queries_executed, ["marcenaria", "móveis planejados"])
        self.assertGreaterEqual(report.duplicates_removed, 1)

    def test_agent_web_enrichment(self):
        provider = FakeLocal()
        agent = LeadResearchAgent(local_search=provider, web_search=provider, llm=FakeLLM())
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            enrich_web=True,
        )
        self.assertTrue(any(lead.website for lead in report.leads))


    def test_agent_discovers_from_web_evidence_with_extractor(self):
        web = FakeWebDiscovery()
        agent = LeadResearchAgent(web_search=web, llm=FakeLLM(), lead_extractor=FakeExtractor())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3))
        self.assertEqual(len(report.leads), 3)
        self.assertEqual(report.local_results_seen, 2)

    def test_agent_web_discovery_has_heuristic_fallback(self):
        web = FakeWebDiscovery()
        agent = LeadResearchAgent(web_search=web, llm=FakeLLM())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1))
        self.assertEqual(len(report.leads), 1)
        self.assertEqual(report.leads[0].name, "Empresa A")

    def test_store_persists_report(self):
        provider = FakeLocal()
        agent = LeadResearchAgent(local_search=provider, web_search=provider, llm=FakeLLM())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3))
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "leadflow.db"
            store = LeadStore(str(db))
            try:
                run_id = store.save_report(report)
                self.assertEqual(run_id, 1)
                self.assertEqual(store.count_leads(), 3)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
