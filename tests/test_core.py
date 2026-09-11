from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.dedupe import lead_key, merge_leads, normalize_text
from leadflow_agent.models import Lead, QueryPlan, SearchGoal, WebHit, WebsiteAudit, WebsiteStatus
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


class FakeBadWebDiscovery:
    name = "fake-web"

    def search_web(self, query, *, country="BR", count=10):
        return [WebHit(title="Instagram", url="https://instagram.com/p/abc", description="", query=query)]

    def heuristic_leads(self, hits, goal, *, query):
        return [Lead(name="Instagram", city=goal.city, state=goal.state, source_provider=self.name, provider_url=hits[0].url)]


class FakeExtractor:
    name = "fake-extractor"

    def extract_leads(self, hits, goal, *, query, max_leads=20):
        return [
            Lead(name="Empresa A", city=goal.city, state=goal.state, phone="13 99999-1111", source_provider="web+ai", discovered_query=query),
            Lead(name="Empresa B", city=goal.city, state=goal.state, phone="13 98888-2222", source_provider="web+ai", discovered_query=query),
            Lead(name="Empresa C", city=goal.city, state=goal.state, phone="13 97777-3333", source_provider="web+ai", discovered_query=query),
        ]


class FakeInvestigator:
    def __init__(self):
        self.calls = []

    def investigate(self, lead, goal, *, max_searches=2):
        from types import SimpleNamespace
        self.calls.append((lead.name, max_searches))
        return SimpleNamespace(searches_used=max_searches, errors=[])


class FakeWebsiteAuditor:
    def __init__(self):
        self.calls = []

    def audit(self, lead, *, timeout=8.0, max_age_days=7, force=False):
        from types import SimpleNamespace
        self.calls.append(lead.name)
        audit = WebsiteAudit(
            requested_url=lead.website,
            final_url=lead.website,
            reachable=True,
            status_code=200,
            uses_https=True,
            technical_score=85,
        )
        lead.website_audit = audit
        return SimpleNamespace(audit=audit, reused=False)


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

    def test_unknown_site_is_not_treated_as_no_site(self):
        lead = score_lead(Lead(name="A", phone="123", review_count=30))
        self.assertEqual(lead.website_status, WebsiteStatus.UNKNOWN)
        self.assertEqual(lead.opportunity.type.value, "review_needed")
        self.assertTrue(any("ainda não resolvido" in r for r in lead.score_reasons))

    def test_verified_missing_site_is_new_site_opportunity_when_identity_matches(self):
        from leadflow_agent.models import IdentityStatus
        lead = score_lead(Lead(
            name="A",
            phone="13 99999-1111",
            socials=["https://instagram.com/a"],
            review_count=30,
            website_status=WebsiteStatus.NOT_FOUND,
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
        ))
        self.assertEqual(lead.opportunity.type.value, "new_site")
        self.assertTrue(lead.opportunity.actionable)
        self.assertGreaterEqual(lead.score, 70)
        self.assertTrue(any("primeiro site" in r for r in lead.score_reasons))

    def test_website_auto_marks_present(self):
        lead = Lead(name="A", website="https://a.example")
        self.assertEqual(lead.website_status, WebsiteStatus.PRESENT)

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

    def test_agent_quality_gate_rejects_generic_platform_candidate(self):
        web = FakeBadWebDiscovery()
        agent = LeadResearchAgent(web_search=web, llm=FakeLLM())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1))
        self.assertEqual(report.leads, [])
        self.assertGreaterEqual(report.quality_rejected, 1)

    def test_agent_web_discovery_has_heuristic_fallback(self):
        web = FakeWebDiscovery()
        agent = LeadResearchAgent(web_search=web, llm=FakeLLM())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1))
        self.assertEqual(len(report.leads), 1)
        self.assertEqual(report.leads[0].name, "Empresa A")


    def test_agent_investigation_is_bounded_and_reported(self):
        provider = FakeLocal()
        investigator = FakeInvestigator()
        agent = LeadResearchAgent(
            local_search=provider,
            web_search=provider,
            llm=FakeLLM(),
            investigator=investigator,
        )
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            investigate=True,
            investigation_limit=2,
            investigation_budget=2,
        )
        self.assertEqual(report.investigated_leads, 2)
        self.assertEqual(report.investigation_searches, 4)
        self.assertEqual(len(investigator.calls), 2)

    def test_agent_website_audit_is_bounded_and_reported(self):
        provider = FakeLocal()
        auditor = FakeWebsiteAuditor()
        agent = LeadResearchAgent(
            local_search=provider,
            web_search=provider,
            llm=FakeLLM(),
            website_auditor=auditor,
        )
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            audit_websites=True,
            audit_limit=1,
        )
        self.assertEqual(report.website_audits_run, 1)
        self.assertEqual(len(auditor.calls), 1)
        self.assertTrue(any(lead.website_audit for lead in report.leads))

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
                columns = {row[1] for row in store.conn.execute("PRAGMA table_info(leads)")}
                self.assertIn("website_status", columns)
                self.assertIn("confidence_score", columns)
                self.assertIn("identity_status", columns)
                self.assertIn("identity_confidence", columns)
                self.assertIn("website_audit_score", columns)
                self.assertIn("website_last_audited_at", columns)
                self.assertIn("opportunity_type", columns)
                self.assertIn("opportunity_actionable", columns)
                self.assertIn("opportunity_service_fit", columns)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
