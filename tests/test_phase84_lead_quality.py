from __future__ import annotations

import unittest

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.contact import resolve_contact_route
from leadflow_agent.dedupe import find_duplicate_key, lead_key
from leadflow_agent.filters import LeadFilterSpec, assess_filter
from leadflow_agent.models import IdentityStatus, Lead, QueryPlan, SearchGoal, WebsiteStatus
from leadflow_agent.planner import build_plan
from leadflow_agent.quality import sanitize_lead_fields
from leadflow_agent.scoring import score_lead
from leadflow_agent.search_service import SearchRequest
from leadflow_agent.validation import PhoneKind, classify_phone, is_digital_contact_phone


class _ShortPlanner:
    name = "short"
    def plan_queries(self, goal, *, max_queries=10):
        return QueryPlan(queries=[goal.segment, "móveis planejados"], generated_by=self.name)


class _QuotaLocal:
    name = "quota-local"
    def __init__(self):
        self.calls = []
    def search_places(self, query, goal, *, count=20):
        index = len(self.calls)
        self.calls.append(query)
        phone = f"13 34{index:02d}-12{index:02d}" if index < 5 else f"13 9{80000000 + index:08d}"
        return [Lead(name=f"Empresa {index}", city=goal.city, state=goal.state, phone=phone, source_provider=self.name, discovered_query=query, identity_status=IdentityStatus.MATCHED, identity_confidence=0.99, website_status=WebsiteStatus.NOT_FOUND)]


class Phase84LeadQualityTests(unittest.TestCase):
    def test_phone_classifier(self):
        self.assertEqual(classify_phone("(13) 99152-5154"), PhoneKind.MOBILE)
        self.assertEqual(classify_phone("(13) 3471-2700"), PhoneKind.FIXED_LINE)
        self.assertFalse(is_digital_contact_phone("(13) 3471-2700"))

    def test_digital_sanitizer_removes_fixed(self):
        lead = Lead(name="Paris", phone="(13) 3471-2700")
        self.assertEqual(sanitize_lead_fields(lead, digital_only=True), 1)
        self.assertIsNone(lead.phone)

    def test_same_domain_dedupes_different_phones(self):
        a = Lead(name="Paris", city="Praia Grande", state="SP", phone="(13) 99152-5154", website="https://www.planejadosparis.com.br")
        b = Lead(name="Paris", city="Praia Grande", state="SP", phone="(13) 3471-2700", website="https://planejadosparis.com.br/")
        self.assertEqual(lead_key(a), lead_key(b))

    def test_distinct_mobiles_same_name_remain_separate(self):
        a = Lead(name="Empresa X", city="Praia Grande", state="SP", phone="(13) 99111-1111")
        b = Lead(name="Empresa X", city="Praia Grande", state="SP", phone="(13) 99222-2222")
        self.assertIsNone(find_duplicate_key({lead_key(a): a}, b))

    def test_fixed_line_not_whatsapp(self):
        route = resolve_contact_route({"contact": {"phone": "(13) 3471-2700", "socials": []}, "location": {"country": "Brazil"}})
        self.assertEqual(route.channel, "none")

    def test_fixed_plus_instagram_prefers_instagram(self):
        route = resolve_contact_route({"contact": {"phone": "(13) 3471-2700", "socials": ["https://www.instagram.com/parisplanejados/"]}, "location": {"country": "Brazil"}})
        self.assertEqual(route.channel, "instagram")

    def test_fixed_line_no_contactability(self):
        lead = Lead(name="Fixed", phone="(13) 3471-2700", website_status=WebsiteStatus.NOT_FOUND, identity_status=IdentityStatus.MATCHED, identity_confidence=0.99)
        score_lead(lead)
        self.assertEqual(lead.opportunity.contactability_score, 0)

    def test_fixed_only_fails_useful_contact_filter(self):
        self.assertFalse(assess_filter(Lead(name="Fixed", phone="(13) 3471-2700"), LeadFilterSpec(require_any_contact=True)).accepted)

    def test_defaults(self):
        request = SearchRequest(segment="marcenaria", city="Praia Grande")
        self.assertEqual(request.max_queries, 10)
        self.assertEqual(request.filter_pool_multiplier, 5)
        self.assertEqual(request.contact_strategy, "digital-first")

    def test_short_plan_expands_to_budget(self):
        plan = build_plan(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10), _ShortPlanner(), max_queries=10)
        self.assertEqual(len(plan.queries), 10)

    def test_more_rounds_fill_filtered_quota(self):
        provider = _QuotaLocal()
        agent = LeadResearchAgent(local_search=provider, llm=_ShortPlanner())
        report = agent.research(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=5), max_queries=10, lead_filter=LeadFilterSpec(require_any_contact=True), filter_pool_multiplier=5, digital_contact_only=True)
        self.assertEqual(len(report.leads), 5)
        self.assertEqual(len(report.queries_executed), 10)
        self.assertTrue(all(is_digital_contact_phone(lead.phone) for lead in report.leads))


if __name__ == "__main__":
    unittest.main()
