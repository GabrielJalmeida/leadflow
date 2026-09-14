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
from leadflow_agent.validation import is_digital_contact_phone


class _Planner:
    name = "test-planner"

    def plan_queries(self, goal, *, max_queries=6):
        return QueryPlan(
            queries=[f"rodada-{index}" for index in range(max_queries)],
            rationale="teste de fulfillment",
            generated_by=self.name,
        )


class _RawPoolThenQualifiedProvider:
    name = "quota-provider"

    def __init__(self):
        self.calls: list[str] = []

    def search_places(self, query, goal, *, count=20):
        self.calls.append(query)
        index = len(self.calls) - 1
        if index == 0:
            # Satura rapidamente o antigo target_pool, mas nenhum destes
            # telefones fixos é contato digital elegível.
            return [
                Lead(
                    name=f"Fixo {i}",
                    city=goal.city,
                    state=goal.state,
                    phone=f"(13) 34{i:02d}-12{i:02d}",
                    source_provider=self.name,
                    identity_status=IdentityStatus.MATCHED,
                    identity_confidence=0.99,
                    website_status=WebsiteStatus.NOT_FOUND,
                )
                for i in range(6)
            ]
        if index == 1:
            return [
                Lead(
                    name=f"Móvel {i}",
                    city=goal.city,
                    state=goal.state,
                    phone=f"(13) 9{91000000 + i:08d}",
                    source_provider=self.name,
                    identity_status=IdentityStatus.MATCHED,
                    identity_confidence=0.99,
                    website_status=WebsiteStatus.NOT_FOUND,
                )
                for i in range(3)
            ]
        return []


class _OnlyUnqualifiedProvider:
    name = "unqualified-provider"

    def __init__(self):
        self.calls = 0

    def search_places(self, query, goal, *, count=20):
        self.calls += 1
        base = self.calls * 10
        return [
            Lead(
                name=f"Sem digital {base + i}",
                city=goal.city,
                state=goal.state,
                phone=f"(13) 34{i:02d}-12{i:02d}",
                source_provider=self.name,
                identity_status=IdentityStatus.MATCHED,
                identity_confidence=0.99,
                website_status=WebsiteStatus.NOT_FOUND,
            )
            for i in range(3)
        ]




class _UnknownContactableProvider:
    name = "unknown-contactable-provider"

    def __init__(self):
        self.calls = 0

    def search_places(self, query, goal, *, count=20):
        self.calls += 1
        base = self.calls * 10
        return [
            Lead(
                name=f"Contato {base + i}",
                city=goal.city,
                state=goal.state,
                phone=f"(13) 9{92000000 + base + i:08d}",
                source_provider=self.name,
                identity_status=IdentityStatus.MATCHED,
                identity_confidence=0.99,
                website_status=WebsiteStatus.UNKNOWN,
            )
            for i in range(4)
        ]


class _NoSiteInvestigator:
    def investigate(self, lead, goal, *, max_searches=2):
        lead.website_status = WebsiteStatus.NOT_FOUND
        lead.field_confidence["website"] = 0.8
        return InvestigationResult(lead=lead, searches_used=1)




class _MixedQualificationProvider:
    name = "mixed-qualification-provider"

    def search_places(self, query, goal, *, count=20):
        return [
            Lead(
                name="Sem contato A", city=goal.city, state=goal.state,
                website_status=WebsiteStatus.UNKNOWN, source_provider=self.name,
            ),
            Lead(
                name="Contato bom A", city=goal.city, state=goal.state,
                phone="(13) 99999-1101", website_status=WebsiteStatus.UNKNOWN,
                source_provider=self.name,
            ),
            Lead(
                name="Sem contato B", city=goal.city, state=goal.state,
                website_status=WebsiteStatus.UNKNOWN, source_provider=self.name,
            ),
            Lead(
                name="Contato bom B", city=goal.city, state=goal.state,
                phone="(13) 99999-1102", website_status=WebsiteStatus.UNKNOWN,
                source_provider=self.name,
            ),
        ]


class _RecordingNoSiteInvestigator:
    def __init__(self):
        self.calls: list[str] = []

    def investigate(self, lead, goal, *, max_searches=2):
        self.calls.append(lead.name)
        lead.website_status = WebsiteStatus.NOT_FOUND
        lead.identity_status = IdentityStatus.MATCHED
        lead.identity_confidence = 0.99
        return InvestigationResult(lead=lead, searches_used=1)


class QualifiedFulfillmentTests(unittest.TestCase):
    def test_fulfillment_does_not_stop_when_raw_pool_is_full_but_filters_will_reject(self):
        provider = _RawPoolThenQualifiedProvider()
        agent = LeadResearchAgent(local_search=provider, llm=_Planner())
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            max_queries=4,
            lead_filter=LeadFilterSpec(require_any_contact=True),
            filter_pool_multiplier=2,
            digital_contact_only=True,
            fulfill_quota=True,
        )

        self.assertGreaterEqual(len(provider.calls), 2)
        self.assertEqual(len(report.leads), 3)
        self.assertTrue(all(is_digital_contact_phone(lead.phone) for lead in report.leads))
        self.assertEqual(report.run_status, "completed")
        self.assertGreaterEqual(report.discovery_prequalified, 3)

    def test_without_fulfillment_old_raw_pool_stop_is_preserved(self):
        provider = _RawPoolThenQualifiedProvider()
        agent = LeadResearchAgent(local_search=provider, llm=_Planner())
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            max_queries=4,
            lead_filter=LeadFilterSpec(require_any_contact=True),
            filter_pool_multiplier=2,
            digital_contact_only=True,
            fulfill_quota=False,
        )

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(report.leads), 0)

    def test_deferred_website_sales_filters_do_not_force_every_query(self):
        provider = _UnknownContactableProvider()
        agent = LeadResearchAgent(
            local_search=provider,
            llm=_Planner(),
            investigator=_NoSiteInvestigator(),
        )
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            max_queries=5,
            investigate=True,
            investigation_limit=None,
            lead_filter=LeadFilterSpec(
                opportunity_types={OpportunityType.NEW_SITE},
                min_opportunity_score=35,
                require_any_contact=True,
            ),
            filter_pool_multiplier=2,
            digital_contact_only=True,
            fulfill_quota=True,
        )

        # UNKNOWN website state cannot satisfy website-sales before investigation,
        # but it also must not make discovery believe there are zero viable leads.
        self.assertEqual(provider.calls, 2)
        self.assertGreaterEqual(report.discovery_prequalified, 6)
        self.assertEqual(len(report.leads), 3)
        self.assertTrue(all(lead.opportunity.type == OpportunityType.NEW_SITE for lead in report.leads))
        self.assertEqual(report.run_status, "completed")

    def test_investigation_prioritizes_prequalified_contactable_candidates(self):
        provider = _MixedQualificationProvider()
        investigator = _RecordingNoSiteInvestigator()
        agent = LeadResearchAgent(
            local_search=provider,
            llm=_Planner(),
            investigator=investigator,
        )
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=2),
            max_queries=1,
            investigate=True,
            investigation_limit=2,
            lead_filter=LeadFilterSpec(
                opportunity_types={OpportunityType.NEW_SITE},
                min_opportunity_score=35,
                require_any_contact=True,
            ),
            filter_pool_multiplier=2,
            digital_contact_only=True,
            fulfill_quota=True,
        )

        self.assertEqual(investigator.calls, ["Contato bom A", "Contato bom B"])
        self.assertEqual(len(report.leads), 2)
        self.assertEqual(report.filter_rejected, 2)
        self.assertEqual(report.filter_rejection_reasons.get("no_contact_channel"), 2)

    def test_exhausted_queries_return_explicit_partial_results(self):
        provider = _OnlyUnqualifiedProvider()
        agent = LeadResearchAgent(local_search=provider, llm=_Planner())
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=3),
            max_queries=3,
            lead_filter=LeadFilterSpec(require_any_contact=True),
            filter_pool_multiplier=2,
            digital_contact_only=True,
            fulfill_quota=True,
        )

        self.assertEqual(provider.calls, 3)
        self.assertEqual(report.leads, [])
        self.assertEqual(report.run_status, "partial_results")
        self.assertIn("0/3", report.run_stop_reason or "")


if __name__ == "__main__":
    unittest.main()
