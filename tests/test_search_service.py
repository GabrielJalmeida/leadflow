from __future__ import annotations

import unittest

from leadflow_agent.config import Settings
from leadflow_agent.filters import Presence, Readiness
from leadflow_agent.models import OpportunityType, WebsiteStatus
from leadflow_agent.search_service import (
    SearchFeatures,
    SearchFilters,
    SearchRequest,
    build_filter_spec,
    validate_search_request,
)


class SearchServiceTests(unittest.TestCase):
    def test_validates_normal_mode_limits(self):
        request = SearchRequest(
            segment="marcenaria",
            city="Praia Grande",
            limit=1000,
            features=SearchFeatures(investigate=False, audit_websites=False),
        )
        with self.assertRaises(ValueError):
            validate_search_request(request, Settings())

    def test_free_text_segment_is_preserved(self):
        request = SearchRequest(
            segment="  vendedor de milho  ",
            city=" Praia Grande ",
            features=SearchFeatures(investigate=False, audit_websites=False),
        )
        validated = validate_search_request(request, Settings())
        self.assertEqual(validated.segment, "vendedor de milho")
        self.assertEqual(validated.city, "Praia Grande")

    def test_filters_can_override_profile_defaults(self):
        request = SearchRequest(
            segment="marcenaria",
            city="Praia Grande",
            profile="new-site",
            features=SearchFeatures(investigate=False, audit_websites=False),
            filters=SearchFilters(
                website="any",
                instagram="present",
                readiness="verify",
                opportunity_types=["redesign"],
                min_opportunity_score=50,
            ),
        )
        spec = build_filter_spec(request)
        self.assertEqual(spec.website_states, set())
        self.assertEqual(spec.instagram, Presence.PRESENT)
        self.assertEqual(spec.readiness, Readiness.VERIFY)
        self.assertEqual(spec.opportunity_types, {OpportunityType.REDESIGN})
        self.assertEqual(spec.min_opportunity_score, 50)

    def test_profile_defaults_remain_when_filter_is_unspecified(self):
        request = SearchRequest(
            segment="marcenaria",
            city="Praia Grande",
            profile="new-site",
            features=SearchFeatures(investigate=False, audit_websites=False),
        )
        spec = build_filter_spec(request)
        self.assertEqual(spec.website_states, {WebsiteStatus.NOT_FOUND})
        self.assertEqual(spec.readiness, Readiness.READY)

    def test_investigator_requires_gemini(self):
        request = SearchRequest(segment="marcenaria", city="Praia Grande")
        with self.assertRaises(ValueError):
            validate_search_request(request, Settings())


if __name__ == "__main__":
    unittest.main()
