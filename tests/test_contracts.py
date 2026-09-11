from __future__ import annotations

import unittest

from leadflow_agent.contracts import FRONTEND_CONTRACT_VERSION, research_contract
from leadflow_agent.models import (
    IdentityStatus,
    Lead,
    OpportunityAssessment,
    OpportunityType,
    QueryPlan,
    ResearchReport,
    SearchGoal,
)


class FrontendContractTests(unittest.TestCase):
    def test_contract_is_versioned_and_small(self):
        lead = Lead(
            name="Empresa X",
            city="Praia Grande",
            state="SP",
            phone="(13) 99999-9999",
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            score=88,
            opportunity=OpportunityAssessment(
                type=OpportunityType.REDESIGN,
                score=88,
                actionable=True,
                service_fit="website_redesign",
                reasons=["site visualmente fraco"],
            ),
            raw={"provider_secret_shape": "must-not-leak-to-ui-contract"},
        )
        report = ResearchReport(
            goal=SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10),
            plan=QueryPlan(["marcenaria"]),
            leads=[lead],
            queries_executed=["marcenaria"],
            local_results_seen=1,
            duplicates_removed=0,
            started_at="2026-09-11T00:00:00+00:00",
            finished_at="2026-09-11T00:00:01+00:00",
            run_status="completed",
            usage_search_calls=1,
        )
        payload = research_contract(report)
        self.assertEqual(payload["contract_version"], FRONTEND_CONTRACT_VERSION)
        self.assertEqual(payload["run"]["returned_results"], 1)
        self.assertEqual(payload["leads"][0]["opportunity"]["type"], "redesign")
        self.assertTrue(payload["leads"][0]["opportunity"]["actionable"])
        self.assertNotIn("raw", payload["leads"][0])


if __name__ == "__main__":
    unittest.main()
