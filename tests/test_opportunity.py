import unittest

from leadflow_agent.models import (
    IdentityStatus,
    Lead,
    OpportunityType,
    BrowserAudit,
    WebsiteAudit,
    WebsiteStatus,
    VisualAudit,
    lead_from_dict,
)
from leadflow_agent.scoring import score_lead


class OpportunityIntelligenceTests(unittest.TestCase):
    def test_verified_no_site_is_actionable_new_site(self):
        lead = Lead(
            name="Alpha Marcenaria",
            phone="13 99999-1111",
            socials=["https://instagram.com/alpha"],
            website_status=WebsiteStatus.NOT_FOUND,
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            review_count=25,
            rating=4.8,
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.NEW_SITE)
        self.assertTrue(lead.opportunity.actionable)
        self.assertGreaterEqual(lead.score, 80)

    def test_unverified_broken_site_is_capped_and_requires_verification(self):
        lead = Lead(
            name="Takal-like",
            phone="11 98566-5011",
            website="https://example.com",
            website_status=WebsiteStatus.UNREACHABLE,
            identity_status=IdentityStatus.UNVERIFIED,
            website_audit=WebsiteAudit(
                requested_url="https://example.com",
                final_url="https://example.com",
                reachable=False,
                uses_https=True,
                technical_score=15,
                error="certificate expired",
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REBUILD)
        self.assertFalse(lead.opportunity.actionable)
        self.assertLessEqual(lead.score, 55)
        self.assertTrue(any("verificar identidade" in c for c in lead.opportunity.cautions))

    def test_verified_broken_site_can_be_strong_rebuild(self):
        lead = Lead(
            name="Beta",
            phone="13 99999-2222",
            socials=["https://instagram.com/beta"],
            website="https://beta.example",
            website_status=WebsiteStatus.UNREACHABLE,
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            review_count=30,
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REBUILD)
        self.assertTrue(lead.opportunity.actionable)
        self.assertGreaterEqual(lead.score, 80)

    def test_healthy_technical_site_does_not_claim_good_design(self):
        lead = Lead(
            name="Gamma",
            phone="13 3333-4444",
            website="https://gamma.example",
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            website_audit=WebsiteAudit(
                requested_url="https://gamma.example",
                final_url="https://gamma.example",
                reachable=True,
                status_code=200,
                uses_https=True,
                technical_score=100,
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REVIEW_NEEDED)
        self.assertEqual(lead.opportunity.service_fit, "visual_review")
        self.assertTrue(any("não mede design" in c for c in lead.opportunity.cautions))


    def test_browser_ux_can_reveal_redesign_need_on_technically_healthy_site(self):
        lead = Lead(
            name="Healthy but awkward",
            phone="13 3333-1111",
            website="https://healthy.example",
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            website_audit=WebsiteAudit(
                requested_url="https://healthy.example",
                final_url="https://healthy.example",
                reachable=True,
                status_code=200,
                uses_https=True,
                technical_score=100,
            ),
            browser_audit=BrowserAudit(
                requested_url="https://healthy.example",
                final_url="https://healthy.example",
                loaded=True,
                status_code=200,
                ux_score=35,
                mobile_overflow=True,
                visible_contact_cta_count=0,
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REDESIGN)
        self.assertEqual(lead.opportunity.service_fit, "website_redesign")
        self.assertTrue(lead.opportunity.actionable)

    def test_mid_health_site_is_optimization_not_no_site(self):
        lead = Lead(
            name="Delta",
            phone="13 3333-5555",
            website="https://delta.example",
            identity_status=IdentityStatus.PROBABLE_MATCH,
            identity_confidence=0.88,
            website_audit=WebsiteAudit(
                requested_url="https://delta.example",
                final_url="https://delta.example",
                reachable=True,
                status_code=200,
                uses_https=True,
                technical_score=68,
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.OPTIMIZATION)
        self.assertTrue(lead.opportunity.actionable)

    def test_identity_mismatch_zeroes_opportunity(self):
        lead = Lead(
            name="Same Name Wrong City",
            website="https://wrong.example",
            identity_status=IdentityStatus.MISMATCH,
            identity_confidence=0.99,
        )
        score_lead(lead)
        self.assertEqual(lead.score, 0)
        self.assertFalse(lead.opportunity.actionable)

    def test_opportunity_round_trips_from_json(self):
        lead = Lead(
            name="Persisted",
            phone="13 99999-7777",
            website_status=WebsiteStatus.NOT_FOUND,
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
        )
        score_lead(lead)
        restored = lead_from_dict(lead.to_dict())
        self.assertIsNotNone(restored.opportunity)
        self.assertEqual(restored.opportunity.type, OpportunityType.NEW_SITE)
        self.assertEqual(restored.opportunity.score, lead.opportunity.score)


    def test_low_visual_score_can_reveal_redesign_need_on_healthy_site(self):
        lead = Lead(
            name="Healthy but dated",
            phone="13 3333-1111",
            website="https://healthy.example",
            identity_status=IdentityStatus.MATCHED,
            identity_confidence=0.99,
            website_audit=WebsiteAudit(
                requested_url="https://healthy.example", final_url="https://healthy.example",
                reachable=True, status_code=200, uses_https=True, technical_score=100,
            ),
            browser_audit=BrowserAudit(
                requested_url="https://healthy.example", final_url="https://healthy.example",
                loaded=True, ux_score=95,
            ),
            visual_audit=VisualAudit(
                overall_score=38, desktop_score=40, mobile_score=36, modernity_score=30,
                hierarchy_score=45, brand_coherence_score=42, readability_score=60,
                conversion_clarity_score=32, confidence=0.88,
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REDESIGN)
        self.assertEqual(lead.opportunity.service_fit, "website_redesign")
        self.assertTrue(any("visual quality" in r for r in lead.opportunity.reasons))

    def test_low_confidence_visual_does_not_drive_opportunity(self):
        lead = Lead(
            name="Ambiguous screenshot", website="https://healthy.example",
            identity_status=IdentityStatus.MATCHED, identity_confidence=0.99,
            website_audit=WebsiteAudit(
                requested_url="https://healthy.example", final_url="https://healthy.example",
                reachable=True, status_code=200, uses_https=True, technical_score=100,
            ),
            browser_audit=BrowserAudit(
                requested_url="https://healthy.example", final_url="https://healthy.example",
                loaded=True, ux_score=95,
            ),
            visual_audit=VisualAudit(
                overall_score=20, desktop_score=20, mobile_score=20, modernity_score=20,
                hierarchy_score=20, brand_coherence_score=20, readability_score=20,
                conversion_clarity_score=20, confidence=0.30,
            ),
        )
        score_lead(lead)
        self.assertEqual(lead.opportunity.type, OpportunityType.REVIEW_NEEDED)


if __name__ == "__main__":
    unittest.main()
