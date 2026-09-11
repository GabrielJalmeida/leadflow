from __future__ import annotations

import unittest

from leadflow_agent.enrichment import enrich_lead_from_web
from leadflow_agent.identity import (
    IdentityCandidate,
    assess_identity,
    is_rejected_candidate,
    record_rejected_candidate,
)
from leadflow_agent.models import IdentityStatus, Lead, SearchGoal, WebHit, WebsiteStatus


class FakeWeb:
    name = "fake-web"

    def __init__(self, hits):
        self.hits = hits

    def search_web(self, query, *, country="BR", count=10):
        return self.hits[:count]


class IdentityResolutionTests(unittest.TestCase):
    def test_same_name_different_city_is_mismatch(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        candidate = IdentityCandidate(
            name="Marcenaria Alvorada",
            city="Curitiba",
            state="PR",
            website="https://marcenariaalvorada.com.br",
        )
        result = assess_identity(lead, candidate)
        self.assertEqual(result.status, IdentityStatus.MISMATCH)
        self.assertGreaterEqual(result.confidence, 0.95)

    def test_same_phone_is_strong_match_even_if_name_differs(self):
        lead = Lead(name="Alvorada Planejados", city="Praia Grande", phone="(13) 99999-1234")
        candidate = IdentityCandidate(name="Alvorada Móveis", phone="13 99999-1234")
        result = assess_identity(lead, candidate)
        self.assertEqual(result.status, IdentityStatus.MATCHED)
        self.assertGreaterEqual(result.confidence, 0.99)

    def test_same_domain_is_strong_match(self):
        lead = Lead(name="Empresa A", website="https://www.empresa-a.com.br")
        candidate = IdentityCandidate(name="Empresa A Ltda", website="https://empresa-a.com.br/contato")
        result = assess_identity(lead, candidate)
        self.assertEqual(result.status, IdentityStatus.MATCHED)

    def test_same_name_same_locality_is_probable(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        candidate = IdentityCandidate(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        result = assess_identity(lead, candidate)
        self.assertEqual(result.status, IdentityStatus.PROBABLE_MATCH)
        self.assertTrue(result.safe_to_merge)

    def test_same_name_without_locality_is_ambiguous(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        candidate = IdentityCandidate(name="Marcenaria Alvorada")
        result = assess_identity(lead, candidate)
        self.assertEqual(result.status, IdentityStatus.AMBIGUOUS)
        self.assertFalse(result.safe_to_merge)

    def test_rejected_candidate_is_cached(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        record_rejected_candidate(
            lead,
            value="https://www.marcenariaalvorada.com.br/",
            target_field="website",
            reason="belongs to Curitiba/PR",
            confidence=0.99,
        )
        record_rejected_candidate(
            lead,
            value="https://marcenariaalvorada.com.br",
            target_field="website",
            reason="duplicate rejection",
            confidence=0.99,
        )
        self.assertEqual(len(lead.rejected_candidates), 1)
        self.assertTrue(
            is_rejected_candidate(
                lead,
                value="https://marcenariaalvorada.com.br/contato",
                target_field="website",
            )
        )

    def test_legacy_enrichment_does_not_attach_name_only_site(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        web = FakeWeb([
            WebHit(
                title="Marcenaria Alvorada | Móveis sob medida",
                url="https://marcenariaalvorada.com.br",
                description="Projetos de marcenaria e móveis planejados.",
            )
        ])
        enrich_lead_from_web(
            lead,
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"),
            web,
        )
        self.assertIsNone(lead.website)
        self.assertEqual(lead.website_status, WebsiteStatus.UNKNOWN)
        self.assertTrue(any(e.kind == "website_identity_check" for e in lead.evidence))

    def test_legacy_enrichment_accepts_name_and_expected_city(self):
        lead = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
        web = FakeWeb([
            WebHit(
                title="Marcenaria Alvorada - Praia Grande",
                url="https://marcenariaalvoradapg.com.br",
                description="Marcenaria Alvorada em Praia Grande SP. Móveis planejados.",
            )
        ])
        enrich_lead_from_web(
            lead,
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"),
            web,
        )
        self.assertEqual(lead.website, "https://marcenariaalvoradapg.com.br")
        self.assertEqual(lead.website_status, WebsiteStatus.PRESENT)
        self.assertGreaterEqual(lead.field_confidence.get("website", 0), 0.80)


if __name__ == "__main__":
    unittest.main()
