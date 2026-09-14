from __future__ import annotations

import unittest

from leadflow_agent.models import (
    IdentityStatus,
    InvestigationCandidate,
    Lead,
    SearchGoal,
    WebHit,
    WebsiteStatus,
)
from leadflow_agent.services.investigator import LeadInvestigator, build_investigation_queries


class FakeWeb:
    name = "fake-web"

    def __init__(self):
        self.calls: list[str] = []

    def search_web(self, query, *, country="BR", count=10):
        self.calls.append(query)
        return [
            WebHit(
                title="Search evidence",
                url=f"https://evidence.example/{len(self.calls)}",
                description="Evidence",
                query=query,
            )
        ]


class QueueExtractor:
    name = "fake-extractor"

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = 0

    def extract_investigation_candidates(
        self,
        hits,
        lead,
        goal,
        *,
        query,
        purpose,
        max_candidates=12,
    ):
        index = self.calls
        self.calls += 1
        if index >= len(self.batches):
            return []
        return self.batches[index]


class BatchExtractor:
    name = "batch-extractor"

    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.batch_calls = 0
        self.legacy_calls = 0

    def extract_investigation_candidates_batch(
        self,
        search_batches,
        lead,
        goal,
        *,
        max_candidates=20,
    ):
        self.batch_calls += 1
        return self.candidates[:max_candidates]

    def extract_investigation_candidates(
        self, hits, lead, goal, *, query, purpose, max_candidates=12
    ):
        self.legacy_calls += 1
        return self.candidates[:max_candidates]


class InvestigatorTests(unittest.TestCase):
    def setUp(self):
        self.goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP")

    def test_verified_candidate_merges_fields(self):
        lead = Lead(name="MP Marcenaria", city="Praia Grande", state="SP")
        extractor = QueueExtractor([
            [
                InvestigationCandidate(
                    name="MP Marcenaria",
                    city="Praia Grande",
                    state="SP",
                    phone="(13) 97426-5722",
                    website="https://mpmarcenaria.example",
                    socials=["https://www.instagram.com/mp.marcenariapg"],
                    address="Praia Grande, SP",
                    source_url="https://evidence.example/1",
                    source="fake",
                    confidence=0.95,
                )
            ]
        ])
        result = LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=2,
        )
        self.assertEqual(result.accepted_candidates, 1)
        self.assertEqual(lead.phone, "(13) 97426-5722")
        self.assertEqual(lead.website, "https://mpmarcenaria.example")
        self.assertEqual(lead.website_status, WebsiteStatus.PRESENT)
        self.assertIn("https://www.instagram.com/mp.marcenariapg", lead.socials)
        self.assertEqual(lead.identity_status, IdentityStatus.PROBABLE_MATCH)
        self.assertGreaterEqual(lead.identity_confidence, 0.80)

    def test_same_name_other_city_is_rejected(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        extractor = QueueExtractor([
            [
                InvestigationCandidate(
                    name="Marcenaria Alvorada",
                    city="Curitiba",
                    state="PR",
                    website="https://marcenariaalvorada.com.br",
                    phone="(41) 3333-3333",
                    source_url="https://evidence.example/1",
                    source="fake",
                    confidence=0.98,
                )
            ],
            [],
        ])
        result = LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=2,
        )
        self.assertGreaterEqual(result.rejected_candidates, 1)
        self.assertIsNone(lead.website)
        self.assertNotEqual(lead.phone, "(41) 3333-3333")
        self.assertTrue(
            any(item.value == "https://marcenariaalvorada.com.br" for item in lead.rejected_candidates)
        )

    def test_ambiguous_website_is_not_attached_or_marked_not_found(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        ambiguous = InvestigationCandidate(
            name="Marcenaria Alvorada",
            website="https://marcenariaalvorada.com.br",
            source_url="https://evidence.example/1",
            source="fake",
            confidence=0.90,
        )
        extractor = QueueExtractor([[ambiguous], [ambiguous]])
        result = LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=2,
        )
        self.assertGreaterEqual(result.ambiguous_candidates, 1)
        self.assertIsNone(lead.website)
        self.assertEqual(lead.website_status, WebsiteStatus.UNKNOWN)

    def test_dedicated_investigation_can_mark_website_not_found(self):
        lead = Lead(name="MP Marcenaria", city="Praia Grande", state="SP")
        safe_no_site = InvestigationCandidate(
            name="MP Marcenaria",
            city="Praia Grande",
            state="SP",
            phone="(13) 97426-5722",
            socials=["https://www.instagram.com/mp.marcenariapg"],
            source_url="https://evidence.example/1",
            source="fake",
            confidence=0.94,
        )
        safe_no_site_2 = InvestigationCandidate(
            name="MP Marcenaria",
            city="Praia Grande",
            state="SP",
            address="Praia Grande, SP",
            source_url="https://evidence.example/2",
            source="fake",
            confidence=0.91,
        )
        extractor = QueueExtractor([[safe_no_site], [safe_no_site_2]])
        result = LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=2,
        )
        self.assertEqual(result.searches_used, 2)
        self.assertEqual(lead.website_status, WebsiteStatus.NOT_FOUND)
        self.assertGreaterEqual(lead.field_confidence.get("website", 0), 0.60)
        self.assertTrue(any(e.kind == "website_not_found" for e in lead.evidence))

    def test_budget_limits_searches(self):
        lead = Lead(name="Empresa X", city="Praia Grande", state="SP")
        web = FakeWeb()
        extractor = QueueExtractor([[], [], []])
        result = LeadInvestigator(web_search=web, extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=1,
        )
        self.assertEqual(result.searches_used, 1)
        self.assertEqual(len(web.calls), 1)


    def test_invalid_existing_phone_is_replaced_by_verified_phone(self):
        lead = Lead(
            name="3Art Marcenaria",
            city="Praia Grande",
            state="SP",
            phone="(13) 99666-309",
        )
        extractor = QueueExtractor([[
            InvestigationCandidate(
                name="3Art Marcenaria",
                city="Praia Grande",
                state="SP",
                phone="(13) 99966-6309",
                source_url="https://evidence.example/1",
                source="fake",
                confidence=0.95,
            )
        ]])
        LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=1,
        )
        self.assertEqual(lead.phone, "(13) 99966-6309")

    def test_query_builder_prioritizes_contact_then_website(self):
        lead = Lead(name="Empresa X", city="Praia Grande", state="SP")
        queries = build_investigation_queries(lead, self.goal)
        self.assertGreaterEqual(len(queries), 2)
        self.assertEqual(queries[0][1], "contact")
        self.assertEqual(queries[1][1], "website")

    def test_query_builder_does_not_search_contact_only_for_missing_email(self):
        lead = Lead(
            name="Empresa X",
            city="Praia Grande",
            state="SP",
            phone="(13) 99999-1111",
            socials=["https://instagram.com/empresa-x"],
            address="Praia Grande, SP",
        )
        queries = build_investigation_queries(lead, self.goal)
        self.assertFalse(any(purpose == "contact" for _, purpose in queries))
        self.assertTrue(any(purpose == "website" for _, purpose in queries))

    def test_phone_only_is_already_a_useful_contact_route(self):
        lead = Lead(
            name="Empresa X",
            city="Praia Grande",
            state="SP",
            phone="(13) 99999-1111",
        )
        queries = build_investigation_queries(lead, self.goal)
        self.assertFalse(any(purpose == "contact" for _, purpose in queries))
        self.assertTrue(any(purpose == "website" for _, purpose in queries))

    def test_social_only_is_already_a_useful_contact_route(self):
        lead = Lead(
            name="Empresa X",
            city="Praia Grande",
            state="SP",
            socials=["https://instagram.com/empresa-x"],
        )
        queries = build_investigation_queries(lead, self.goal)
        self.assertFalse(any(purpose == "contact" for _, purpose in queries))
        self.assertTrue(any(purpose == "website" for _, purpose in queries))

    def test_batch_extractor_uses_one_llm_extraction_for_two_searches(self):
        lead = Lead(
            name="MP Marcenaria",
            city="Praia Grande",
            state="SP",
            phone="(13) 97426-5722",
        )
        extractor = BatchExtractor([
            InvestigationCandidate(
                name="MP Marcenaria",
                city="Praia Grande",
                state="SP",
                phone="(13) 97426-5722",
                address="Praia Grande, SP",
                source_url="https://evidence.example/1",
                source="fake",
                confidence=0.96,
            )
        ])
        result = LeadInvestigator(web_search=FakeWeb(), extractor=extractor).investigate(
            lead,
            self.goal,
            max_searches=2,
        )
        self.assertEqual(result.searches_used, 2)
        self.assertEqual(result.extraction_calls, 1)
        self.assertEqual(extractor.batch_calls, 1)
        self.assertEqual(extractor.legacy_calls, 0)

    def test_recent_not_found_memory_can_make_investigation_complete(self):
        lead = Lead(
            name="Empresa X",
            city="Praia Grande",
            state="SP",
            phone="(13) 99999-1111",
            socials=["https://instagram.com/empresa-x"],
            address="Praia Grande, SP",
            website_status=WebsiteStatus.NOT_FOUND,
        )
        self.assertEqual(build_investigation_queries(lead, self.goal), [])



if __name__ == "__main__":
    unittest.main()
