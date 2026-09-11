from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leadflow_agent.models import BrowserAudit, Lead, lead_from_dict
from leadflow_agent.services.browser_auditor import BrowserAuditor, score_browser_signals


class BrowserAuditorTests(unittest.TestCase):
    def test_perfect_browser_signals_score_100(self):
        score, findings = score_browser_signals(
            loaded=True,
            mobile_overflow=False,
            visible_contact_cta_count=2,
            nav_link_count=5,
            console_error_count=0,
            page_error_count=0,
        )
        self.assertEqual(score, 100)
        self.assertEqual(findings, [])

    def test_mobile_overflow_and_missing_cta_are_flagged(self):
        score, findings = score_browser_signals(
            loaded=True,
            mobile_overflow=True,
            visible_contact_cta_count=0,
            nav_link_count=1,
            console_error_count=2,
            page_error_count=1,
        )
        self.assertLess(score, 50)
        self.assertTrue(any("overflow horizontal" in item for item in findings))
        self.assertTrue(any("CTA" in item for item in findings))

    def test_auditor_records_result_and_evidence(self):
        def runner(url: str, timeout: float, artifacts_dir: Path) -> BrowserAudit:
            self.assertEqual(url, "https://93.184.216.34")
            self.assertGreaterEqual(timeout, 4)
            self.assertTrue(artifacts_dir.exists())
            return BrowserAudit(
                requested_url=url,
                final_url=url,
                loaded=True,
                status_code=200,
                ux_score=82,
                visible_contact_cta_count=1,
            )

        with tempfile.TemporaryDirectory() as tmp:
            lead = Lead(name="Empresa", website="https://93.184.216.34")
            outcome = BrowserAuditor(runner=runner).audit(
                lead,
                artifacts_dir=Path(tmp),
            )
            self.assertFalse(outcome.reused)
            self.assertEqual(lead.browser_audit.ux_score, 82)
            self.assertTrue(any(item.kind == "browser_audit" for item in lead.evidence))

    def test_recent_browser_audit_is_reused(self):
        called = False

        def runner(url: str, timeout: float, artifacts_dir: Path) -> BrowserAudit:
            nonlocal called
            called = True
            raise AssertionError("runner should not be called")

        lead = Lead(
            name="Empresa",
            website="https://93.184.216.34",
            browser_audit=BrowserAudit(
                requested_url="https://93.184.216.34",
                final_url="https://93.184.216.34",
                loaded=True,
                status_code=200,
                ux_score=90,
            ),
        )
        outcome = BrowserAuditor(runner=runner).audit(lead)
        self.assertTrue(outcome.reused)
        self.assertFalse(called)

    def test_browser_audit_round_trips_from_json(self):
        lead = Lead(
            name="Persistida",
            website="https://93.184.216.34",
            browser_audit=BrowserAudit(
                requested_url="https://93.184.216.34",
                final_url="https://93.184.216.34",
                loaded=True,
                ux_score=77,
                mobile_overflow=True,
            ),
        )
        restored = lead_from_dict(lead.to_dict())
        self.assertIsNotNone(restored.browser_audit)
        self.assertEqual(restored.browser_audit.ux_score, 77)
        self.assertTrue(restored.browser_audit.mobile_overflow)

    def test_stale_browser_audit_is_refreshed(self):
        called = False

        def runner(url: str, timeout: float, artifacts_dir: Path) -> BrowserAudit:
            nonlocal called
            called = True
            return BrowserAudit(
                requested_url=url,
                final_url=url,
                loaded=True,
                status_code=200,
                ux_score=88,
            )

        old = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0).isoformat()
        lead = Lead(
            name="Empresa",
            website="https://93.184.216.34",
            browser_audit=BrowserAudit(
                requested_url="https://93.184.216.34",
                final_url="https://93.184.216.34",
                loaded=True,
                ux_score=20,
                audited_at=old,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            outcome = BrowserAuditor(runner=runner).audit(
                lead,
                max_age_days=7,
                artifacts_dir=tmp,
            )
        self.assertFalse(outcome.reused)
        self.assertTrue(called)
        self.assertEqual(lead.browser_audit.ux_score, 88)


if __name__ == "__main__":
    unittest.main()
