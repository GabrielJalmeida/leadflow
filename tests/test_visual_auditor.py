from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leadflow_agent.models import BrowserAudit, Lead, VisualAudit
from leadflow_agent.services.visual_auditor import VisualAuditor


class FakeVisualProvider:
    name = "fake-vision"

    def __init__(self):
        self.calls = 0

    def analyze_visual_audit(self, lead, *, desktop_screenshot, mobile_screenshot):
        self.calls += 1
        return VisualAudit(
            overall_score=48,
            desktop_score=52,
            mobile_score=44,
            modernity_score=40,
            hierarchy_score=55,
            brand_coherence_score=50,
            readability_score=65,
            conversion_clarity_score=30,
            confidence=0.88,
            strengths=["texto legível"],
            weaknesses=["CTA pouco destacado"],
            summary="Há espaço visível para redesign.",
            model="fake",
        )


class VisualAuditorTests(unittest.TestCase):
    def _lead(self, root: Path) -> Lead:
        desktop = root / "desktop.webp"
        mobile = root / "mobile.webp"
        desktop.write_bytes(b"desktop")
        mobile.write_bytes(b"mobile")
        return Lead(
            name="Empresa Visual",
            website="https://example.com",
            browser_audit=BrowserAudit(
                requested_url="https://example.com",
                final_url="https://example.com",
                loaded=True,
                desktop_screenshot=str(desktop),
                mobile_screenshot=str(mobile),
                ux_score=90,
            ),
        )

    def test_visual_audit_uses_browser_screenshots_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeVisualProvider()
            lead = self._lead(Path(tmp))
            outcome = VisualAuditor(provider).audit(lead)
            self.assertFalse(outcome.reused)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(lead.visual_audit.overall_score, 48)
            self.assertTrue(any(e.kind == "visual_audit" for e in lead.evidence))

    def test_recent_visual_audit_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeVisualProvider()
            lead = self._lead(Path(tmp))
            lead.visual_audit = VisualAudit(
                overall_score=80,
                desktop_score=80,
                mobile_score=80,
                modernity_score=80,
                hierarchy_score=80,
                brand_coherence_score=80,
                readability_score=80,
                conversion_clarity_score=80,
                confidence=0.9,
            )
            outcome = VisualAuditor(provider).audit(lead, max_age_days=14)
            self.assertTrue(outcome.reused)
            self.assertEqual(provider.calls, 0)
            self.assertEqual(outcome.audit.overall_score, 80)

    def test_stale_visual_audit_is_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeVisualProvider()
            lead = self._lead(Path(tmp))
            old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0).isoformat()
            lead.visual_audit = VisualAudit(
                overall_score=80,
                desktop_score=80,
                mobile_score=80,
                modernity_score=80,
                hierarchy_score=80,
                brand_coherence_score=80,
                readability_score=80,
                conversion_clarity_score=80,
                confidence=0.9,
                analyzed_at=old,
            )
            outcome = VisualAuditor(provider).audit(lead, max_age_days=14)
            self.assertFalse(outcome.reused)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(outcome.audit.overall_score, 48)

    def test_missing_screenshot_is_rejected(self):
        lead = Lead(
            name="Missing",
            website="https://example.com",
            browser_audit=BrowserAudit(
                requested_url="https://example.com",
                final_url="https://example.com",
                loaded=True,
                desktop_screenshot="missing-desktop.webp",
                mobile_screenshot="missing-mobile.webp",
            ),
        )
        with self.assertRaises(FileNotFoundError):
            VisualAuditor(FakeVisualProvider()).audit(lead)


if __name__ == "__main__":
    unittest.main()
