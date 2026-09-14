from __future__ import annotations

import unittest

from leadflow_agent.models import Lead
from leadflow_agent.quality import assess_lead_quality, sanitize_lead_fields


class QualityGateTests(unittest.TestCase):
    def test_rejects_platform_name(self):
        decision = assess_lead_quality(Lead(name="Instagram"), segment="marcenaria")
        self.assertFalse(decision.accepted)
        self.assertIn("generic_name", decision.reasons)

    def test_rejects_marketing_copy_as_name(self):
        lead = Lead(name="Conheça a Forte Madeiras, a loja mais completa e a ...")
        decision = assess_lead_quality(lead, segment="marcenaria")
        self.assertFalse(decision.accepted)

    def test_allows_short_branded_business_name(self):
        decision = assess_lead_quality(Lead(name="3Art Marcenaria"), segment="marcenaria")
        self.assertTrue(decision.accepted)

    def test_rejects_directory_page_as_business(self):
        lead = Lead(
            name="Marcenarias em Praia Grande - SP - Marcenarias.net.br",
            provider_url="https://www.marcenarias.net.br/cidade/marcenarias-em-praia-grande-sp",
        )
        decision = assess_lead_quality(lead, segment="marcenaria")
        self.assertFalse(decision.accepted)

    def test_removes_truncated_brazil_phone(self):
        lead = Lead(name="3Art Marcenaria", phone="(13) 99666-309", country="Brazil", field_confidence={"phone": 0.9})
        removed = sanitize_lead_fields(lead)
        self.assertEqual(removed, 1)
        self.assertIsNone(lead.phone)
        self.assertNotIn("phone", lead.field_confidence)


if __name__ == "__main__":
    unittest.main()
