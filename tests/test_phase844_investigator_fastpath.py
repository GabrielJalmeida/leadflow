from __future__ import annotations

import unittest

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.filters import LeadFilterSpec
from leadflow_agent.models import (
    IdentityStatus,
    Lead,
    OpportunityType,
    QueryPlan,
    SearchGoal,
    WebsiteStatus,
)
from leadflow_agent.services.investigator import InvestigationResult


class _Planner:
    name = "planner"

    def plan_queries(self, goal, *, max_queries=6):
        return QueryPlan(queries=[goal.segment], rationale="test", generated_by=self.name)


class _Provider:
    name = "provider"

    def __init__(self, leads):
        self.leads = list(leads)

    def search_places(self, query, goal, *, count=20):
        return self.leads


class _NoSiteInvestigator:
    def __init__(self):
        self.calls: list[str] = []

    def investigate(self, lead, goal, *, max_searches=2):
        self.calls.append(lead.name)
        lead.website_status = WebsiteStatus.NOT_FOUND
        lead.identity_status = IdentityStatus.MATCHED
        lead.identity_confidence = 0.99
        return InvestigationResult(lead=lead, searches_used=2, extraction_calls=1)


class _FailIfAudited:
    def __init__(self):
        self.calls: list[str] = []

    def audit(self, lead, **kwargs):
        self.calls.append(lead.name)
        raise AssertionError("unverified website should not be audited for filtered quota fulfillment")


class InvestigatorFastPathTests(unittest.TestCase):
    def test_quota_first_investigation_stops_after_enough_final_leads(self):
        leads = [
            Lead(
                name=f"Empresa {index}",
                city="Praia Grande",
                state="SP",
                phone=f"(13) 99999-11{index:02d}",
                website_status=WebsiteStatus.UNKNOWN,
                source_provider="provider",
            )
            for index in range(1, 5)
        ]
        investigator = _NoSiteInvestigator()
        spec = LeadFilterSpec(
            opportunity_types={OpportunityType.NEW_SITE},
            min_opportunity_score=35,
            require_any_contact=True,
        )
        agent = LeadResearchAgent(
            local_search=_Provider(leads),
            llm=_Planner(),
            investigator=investigator,
        )
        report = agent.research(
            SearchGoal("marcenaria", "Praia Grande", state="SP", limit=2),
            max_queries=1,
            investigate=True,
            investigation_limit=4,
            investigation_budget=2,
            lead_filter=spec,
            fulfill_quota=True,
        )
        self.assertEqual(len(report.leads), 2)
        self.assertEqual(report.investigated_leads, 2)
        self.assertEqual(len(investigator.calls), 2)
        self.assertEqual(report.investigation_extractions, 2)

    def test_filtered_quota_run_does_not_audit_unverified_website(self):
        auditor = _FailIfAudited()
        spec = LeadFilterSpec(
            opportunity_types={OpportunityType.REDESIGN, OpportunityType.REBUILD},
            min_opportunity_score=35,
            require_any_contact=True,
        )
        lead = Lead(
            name="Site ainda não verificado",
            city="Praia Grande",
            state="SP",
            phone="(13) 99999-1111",
            website="https://example.com",
            website_status=WebsiteStatus.PRESENT,
            identity_status=IdentityStatus.UNVERIFIED,
            source_provider="provider",
        )
        agent = LeadResearchAgent(
            local_search=_Provider([lead]),
            llm=_Planner(),
            website_auditor=auditor,
        )
        report = agent.research(
            SearchGoal("marcenaria", "Praia Grande", state="SP", limit=1),
            max_queries=1,
            investigate=False,
            audit_websites=True,
            audit_limit=1,
            lead_filter=spec,
            fulfill_quota=True,
        )
        self.assertEqual(auditor.calls, [])
        self.assertEqual(report.website_audits_run, 0)


if __name__ == "__main__":
    unittest.main()
