import unittest

from leadflow_agent.filters import LeadFilterSpec, Presence, Readiness, assess_filter
from leadflow_agent.models import Lead, OpportunityAssessment, OpportunityType, VisualAudit, WebsiteStatus


class FilterTests(unittest.TestCase):
    def lead(self) -> Lead:
        lead = Lead(name="Acme", phone="(13) 99999-9999", socials=["https://instagram.com/acme"])
        lead.website_status = WebsiteStatus.NOT_FOUND
        lead.score = 80
        lead.opportunity = OpportunityAssessment(type=OpportunityType.NEW_SITE, score=80, actionable=True)
        return lead

    def test_no_site_ready_filter(self):
        spec = LeadFilterSpec(website_states={WebsiteStatus.NOT_FOUND}, readiness=Readiness.READY)
        self.assertTrue(assess_filter(self.lead(), spec).accepted)

    def test_instagram_missing_rejects_instagram_lead(self):
        spec = LeadFilterSpec(instagram=Presence.MISSING)
        self.assertFalse(assess_filter(self.lead(), spec).accepted)

    def test_visual_filter_requires_audit(self):
        spec = LeadFilterSpec(max_visual_score=60)
        result = assess_filter(self.lead(), spec)
        self.assertFalse(result.accepted)
        self.assertIn("visual_audit_missing", result.reasons)

    def test_visual_filter_uses_confident_score(self):
        lead = self.lead()
        lead.visual_audit = VisualAudit(50, 50, 50, 50, 50, 50, 50, 50, confidence=.9)
        self.assertTrue(assess_filter(lead, LeadFilterSpec(max_visual_score=60)).accepted)

    def test_require_any_contact(self):
        lead = Lead(name="No Contact")
        self.assertFalse(assess_filter(lead, LeadFilterSpec(require_any_contact=True)).accepted)


if __name__ == "__main__":
    unittest.main()

class _FilterLocal:
    name = "filter-local"
    def search_places(self, query, goal, *, count=20):
        return [
            Lead(name="Has Phone", city=goal.city, state=goal.state, phone="13 99999-1111", discovered_query=query),
            Lead(name="No Phone", city=goal.city, state=goal.state, discovered_query=query),
        ]


class AgentFilterIntegrationTests(unittest.TestCase):
    def test_agent_filters_after_building_candidate_pool(self):
        from leadflow_agent.agent import LeadResearchAgent
        from leadflow_agent.models import SearchGoal
        agent = LeadResearchAgent(local_search=_FilterLocal())
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1),
            lead_filter=LeadFilterSpec(phone=Presence.MISSING),
            filter_pool_multiplier=2,
        )
        self.assertEqual([lead.name for lead in report.leads], ["No Phone"])
        self.assertEqual(report.filter_candidates_seen, 2)
        self.assertEqual(report.filter_rejected, 1)
