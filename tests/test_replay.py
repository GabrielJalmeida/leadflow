from __future__ import annotations

import unittest

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.filters import LeadFilterSpec
from leadflow_agent.models import IdentityStatus, Lead, OpportunityType, QueryPlan, SearchGoal, WebsiteStatus
from leadflow_agent.replay import (
    deserialize_filter_spec,
    order_for_investigation,
    replay_finalize,
    serialize_filter_spec,
)
from leadflow_agent.services.investigator import InvestigationResult


class _Planner:
    name = "replay-planner"

    def plan_queries(self, goal, *, max_queries=6):
        return QueryPlan(queries=["one"], rationale="replay test", generated_by=self.name)


class _Provider:
    name = "replay-provider"

    def search_places(self, query, goal, *, count=20):
        return [
            Lead(name="Sem contato", city=goal.city, state=goal.state),
            Lead(
                name="Contato B",
                city=goal.city,
                state=goal.state,
                phone="(13) 99999-0202",
                identity_status=IdentityStatus.MATCHED,
                identity_confidence=0.95,
            ),
            Lead(
                name="Contato A",
                city=goal.city,
                state=goal.state,
                phone="(13) 99999-0101",
                identity_status=IdentityStatus.MATCHED,
                identity_confidence=0.95,
            ),
        ]


class _Investigator:
    def investigate(self, lead, goal, *, max_searches=2):
        lead.website_status = WebsiteStatus.NOT_FOUND
        lead.identity_status = IdentityStatus.MATCHED
        lead.identity_confidence = 0.99
        return InvestigationResult(lead=lead, searches_used=1)


class ReplayTests(unittest.TestCase):
    def test_filter_spec_round_trip(self):
        original = LeadFilterSpec(
            website_states={WebsiteStatus.NOT_FOUND},
            opportunity_types={OpportunityType.NEW_SITE},
            min_opportunity_score=35,
            require_any_contact=True,
        )
        restored = deserialize_filter_spec(serialize_filter_spec(original))
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.website_states, original.website_states)
        self.assertEqual(restored.opportunity_types, original.opportunity_types)
        self.assertEqual(restored.min_opportunity_score, 35)
        self.assertTrue(restored.require_any_contact)

    def test_replay_capture_reproduces_deterministic_finalization_without_provider_calls(self):
        spec = LeadFilterSpec(
            opportunity_types={OpportunityType.NEW_SITE},
            min_opportunity_score=35,
            require_any_contact=True,
        )
        agent = LeadResearchAgent(
            local_search=_Provider(),
            llm=_Planner(),
            investigator=_Investigator(),
        )
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=2),
            max_queries=1,
            investigate=True,
            investigation_limit=2,
            lead_filter=spec,
            fulfill_quota=True,
            capture_replay=True,
        )
        self.assertIsNotNone(report.replay_snapshot)
        snapshot = report.replay_snapshot or {}
        self.assertIn("post_discovery", snapshot["stages"])
        self.assertIn("post_investigation", snapshot["stages"])
        self.assertIn("post_audits", snapshot["stages"])
        self.assertEqual(
            [item["name"] for item in snapshot["selections"]["investigation"]],
            ["Contato B", "Contato A"],
        )

        replay = replay_finalize(snapshot, stage="post_audits")
        self.assertEqual(replay["provider_calls"], 0)
        self.assertEqual(replay["llm_calls"], 0)
        self.assertEqual(replay["returned"], len(report.leads))
        self.assertEqual(
            [lead["name"] for lead in replay["leads"]],
            [lead.name for lead in report.leads],
        )

    def test_investigation_order_puts_contactable_candidates_first(self):
        spec = LeadFilterSpec(require_any_contact=True)
        leads = _Provider().search_places("x", SearchGoal("marcenaria", "Praia Grande"))
        ordered = order_for_investigation(leads, spec)
        self.assertEqual([lead.name for lead in ordered[:2]], ["Contato B", "Contato A"])
        self.assertEqual(ordered[-1].name, "Sem contato")


if __name__ == "__main__":
    unittest.main()

class FastCapturePolicyTests(unittest.TestCase):
    def test_discovery_snapshot_can_drive_investigation_order_without_provider_calls(self):
        goal = SearchGoal("marcenaria", "Praia Grande", state="SP", limit=3)
        spec = LeadFilterSpec(require_any_contact=True)
        agent = LeadResearchAgent(local_search=_Provider(), llm=_Planner())
        report = agent.research(
            goal,
            max_queries=1,
            investigate=False,
            audit_websites=False,
            lead_filter=spec,
            fulfill_quota=False,
            capture_replay=True,
        )
        snapshot = report.replay_snapshot or {}
        replay = replay_finalize(snapshot, stage="post_discovery")
        self.assertEqual(replay["provider_calls"], 0)
        self.assertEqual(replay["llm_calls"], 0)
        self.assertEqual(replay["investigation_order"][:2], ["Contato B", "Contato A"])
