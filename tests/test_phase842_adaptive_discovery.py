from __future__ import annotations

import unittest

from leadflow_agent.agent import LeadResearchAgent, _build_web_discovery_query
from leadflow_agent.agent_factory import build_agent
from leadflow_agent.config import Settings
from leadflow_agent.models import Lead, QueryPlan, SearchGoal, WebHit
from leadflow_agent.providers.multi import RoundRobinLocalSearchProvider, RoundRobinWebSearchProvider
from leadflow_agent.search_service import SearchBudgets, SearchRequest


class _Local:
    def __init__(self, name: str, lead_name: str):
        self.name = name
        self.lead_name = lead_name
        self.calls: list[str] = []

    def search_places(self, query, goal, *, count=20):
        self.calls.append(query)
        return [Lead(
            name=self.lead_name,
            city=goal.city,
            state=goal.state,
            phone="13 99999-1111",
            source_provider=self.name,
            discovered_query=query,
        )]


class _Web:
    def __init__(self, name: str, *, fail: bool = False):
        self.name = name
        self.fail = fail
        self.calls: list[str] = []

    def search_web(self, query, *, country="BR", count=10):
        self.calls.append(query)
        if self.fail:
            raise RuntimeError(f"{self.name} offline")
        return [WebHit(
            title=f"{self.name} result",
            url=f"https://{self.name}.example/business",
            description="empresa local",
            query=query,
        )]


class _Planner:
    name = "planner"

    def plan_queries(self, goal, *, max_queries=6):
        return QueryPlan(queries=[goal.segment], generated_by=self.name)


class _Extractor:
    name = "extractor"

    def extract_leads(self, hits, goal, *, query, max_leads=20):
        return [Lead(
            name="Empresa Web",
            city=goal.city,
            state=goal.state,
            phone="13 98888-2222",
            source_provider=self.name,
            provider_url=hits[0].url,
            discovered_query=query,
        )]


class Phase842AdaptiveDiscoveryTests(unittest.TestCase):
    def test_round_robin_web_rotates_sources(self):
        first = _Web("primeiro")
        second = _Web("segundo")
        multi = RoundRobinWebSearchProvider([first, second])

        multi.search_web("a")
        multi.search_web("b")

        self.assertEqual(len(first.calls), 1)
        self.assertEqual(len(second.calls), 1)
        self.assertEqual(multi.name, "primeiro+segundo")

    def test_round_robin_web_falls_back_when_one_source_fails(self):
        failing = _Web("falho", fail=True)
        healthy = _Web("saudavel")
        multi = RoundRobinWebSearchProvider([failing, healthy])

        hits = multi.search_web("teste")

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(failing.calls), 1)
        self.assertEqual(len(healthy.calls), 1)

    def test_round_robin_local_rotates_sources(self):
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP")
        first = _Local("local-a", "Empresa A")
        second = _Local("local-b", "Empresa B")
        multi = RoundRobinLocalSearchProvider([first, second])

        self.assertEqual(multi.search_places("a", goal)[0].name, "Empresa A")
        self.assertEqual(multi.search_places("b", goal)[0].name, "Empresa B")

    def test_agent_combines_local_and_web_discovery_in_same_round(self):
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=2)
        local = _Local("local", "Empresa Local")
        web = _Web("web")
        agent = LeadResearchAgent(
            local_search=local,
            web_search=web,
            llm=_Planner(),
            lead_extractor=_Extractor(),
        )

        report = agent.research(goal, max_queries=1)

        self.assertEqual({lead.name for lead in report.leads}, {"Empresa Local", "Empresa Web"})
        self.assertEqual(len(local.calls), 1)
        self.assertEqual(len(web.calls), 1)

    def test_auto_provider_uses_all_configured_discovery_capabilities(self):
        selected, agent = build_agent(
            Settings(
                tavily_api_key="tavily-test",
                brave_api_key="brave-test",
                db_path=":memory:",
            ),
            no_ai=True,
            provider_name="auto",
            use_cache=False,
            use_memory=False,
        )
        self.assertEqual(selected, "tavily+brave")
        self.assertIsNotNone(agent.local_search)
        self.assertIsNotNone(agent.web_search)

    def test_instagram_query_uses_social_retrieval_angle(self):
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP")
        query = _build_web_discovery_query("marcenaria Instagram", goal)
        self.assertIn("perfil Instagram contato", query)

    def test_quota_defaults_allow_broader_discovery(self):
        request = SearchRequest(segment="marcenaria", city="Praia Grande")
        self.assertEqual(request.max_queries, 20)
        self.assertGreaterEqual(request.budgets.max_search_calls, 30)
        self.assertTrue(request.fulfill_quota)


if __name__ == "__main__":
    unittest.main()
