from __future__ import annotations

import unittest

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.models import Lead, SearchGoal
from leadflow_agent.runtime import RunStatus
from leadflow_agent.search_service import SearchRequest


class _OneLeadLocal:
    name = "one-lead"

    def search_places(self, query, goal, *, count=20):
        return [
            Lead(
                name="Empresa Única",
                city=goal.city,
                state=goal.state,
                phone="13 99999-1111",
                source_provider=self.name,
                discovered_query=query,
            )
        ]


class Phase841FulfillmentTests(unittest.TestCase):
    def test_quota_fulfillment_is_enabled_by_default(self):
        request = SearchRequest(segment="marcenaria", city="Praia Grande")
        self.assertTrue(request.fulfill_quota)
        self.assertGreaterEqual(request.max_queries, 10)
        self.assertGreaterEqual(request.filter_pool_multiplier, 5)

    def test_shortfall_is_not_reported_as_completed(self):
        agent = LeadResearchAgent(local_search=_OneLeadLocal())
        report = agent.research(
            SearchGoal(segment="segmento muito específico", city="Praia Grande", state="SP", limit=2),
            max_queries=1,
        )
        self.assertEqual(len(report.leads), 1)
        self.assertEqual(report.run_status, RunStatus.PARTIAL_RESULTS.value)
        self.assertIn("1/2", report.run_stop_reason or "")


if __name__ == "__main__":
    unittest.main()
