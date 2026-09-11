from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from leadflow_agent.memory import LeadMemory
from leadflow_agent.models import (
    BrowserAudit,
    Evidence,
    IdentityStatus,
    Lead,
    QueryPlan,
    RejectedCandidate,
    ResearchReport,
    SearchGoal,
    WebsiteAudit,
    WebsiteStatus,
    VisualAudit,
)
from leadflow_agent.storage import LeadStore


class MemoryTests(unittest.TestCase):
    def _save(self, db: str, lead: Lead) -> None:
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1)
        report = ResearchReport(
            goal=goal,
            plan=QueryPlan(["marcenaria"], generated_by="test"),
            leads=[lead],
            queries_executed=["marcenaria"],
            local_results_seen=1,
            duplicates_removed=0,
            started_at="2026-09-11T12:00:00+00:00",
            finished_at="2026-09-11T12:00:01+00:00",
        )
        store = LeadStore(db)
        try:
            store.save_report(report)
        finally:
            store.close()

    def test_strong_provider_url_anchor_restores_verified_fields_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            stored = Lead(
                name="MP Marcenaria",
                city="Praia Grande",
                state="SP",
                provider_url="https://www.instagram.com/mp.marcenariapg",
                phone="(13) 97426-5722",
                website="https://mpmarcenaria.example",
                socials=["https://www.instagram.com/mp.marcenariapg"],
                address="Praia Grande, SP",
                identity_status=IdentityStatus.MATCHED,
                identity_confidence=0.98,
                field_confidence={
                    "phone": 0.95,
                    "website": 0.94,
                    "socials": 0.95,
                    "address": 0.90,
                },
                evidence=[
                    Evidence(
                        source="test",
                        kind="verified_field",
                        target_field="phone",
                        confidence=0.95,
                        detail="(13) 97426-5722",
                    )
                ],
                rejected_candidates=[
                    RejectedCandidate(
                        value="https://wrong.example",
                        target_field="website",
                        reason="identity mismatch",
                        confidence=0.99,
                    )
                ],
            )
            self._save(db, stored)

            current = Lead(
                name="MP Marcenaria",
                city="Praia Grande",
                state="SP",
                provider_url="https://www.instagram.com/mp.marcenariapg",
            )
            result = LeadMemory(db).hydrate(current)

            self.assertTrue(result.matched)
            self.assertEqual(current.phone, "(13) 97426-5722")
            self.assertEqual(current.website, "https://mpmarcenaria.example")
            self.assertEqual(current.website_status, WebsiteStatus.PRESENT)
            self.assertIn("https://www.instagram.com/mp.marcenariapg", current.socials)
            self.assertEqual(len(current.rejected_candidates), 1)
            self.assertGreaterEqual(result.fields_restored, 3)
            self.assertEqual(result.rejected_restored, 1)

    def test_same_name_and_city_without_durable_anchor_does_not_hydrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            self._save(
                db,
                Lead(
                    name="Marcenaria Alvorada",
                    city="Praia Grande",
                    state="SP",
                    phone="(13) 99999-1111",
                    field_confidence={"phone": 0.95},
                ),
            )
            current = Lead(name="Marcenaria Alvorada", city="Praia Grande", state="SP")
            result = LeadMemory(db).hydrate(current)
            self.assertFalse(result.matched)
            self.assertIsNone(current.phone)

    def test_recent_not_found_state_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            stored = Lead(
                name="Empresa Sem Site",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-sem-site",
                website_status=WebsiteStatus.NOT_FOUND,
                field_confidence={"website": 0.68},
                evidence=[
                    Evidence(
                        source="fake",
                        kind="website_not_found",
                        target_field="website",
                        confidence=0.68,
                        observed_at=now,
                    )
                ],
            )
            self._save(db, stored)
            current = Lead(
                name="Empresa Sem Site",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-sem-site",
            )
            result = LeadMemory(db).hydrate(current)
            self.assertTrue(result.matched)
            self.assertEqual(current.website_status, WebsiteStatus.NOT_FOUND)

    def test_recent_website_audit_is_restored_for_same_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            stored = Lead(
                name="Empresa Auditada",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-auditada",
                website="https://empresa.example",
                field_confidence={"website": 0.95},
                website_audit=WebsiteAudit(
                    requested_url="https://empresa.example",
                    final_url="https://empresa.example",
                    reachable=True,
                    status_code=200,
                    uses_https=True,
                    technical_score=90,
                ),
            )
            self._save(db, stored)
            current = Lead(
                name="Empresa Auditada",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-auditada",
                website="https://empresa.example",
            )
            result = LeadMemory(db).hydrate(current)
            self.assertTrue(result.matched)
            self.assertIsNotNone(current.website_audit)
            self.assertEqual(current.website_audit.technical_score, 90)


    def test_recent_browser_audit_is_restored_for_same_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            stored = Lead(
                name="Empresa Browser Auditada",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-browser",
                website="https://empresa.example",
                field_confidence={"website": 0.95},
                browser_audit=BrowserAudit(
                    requested_url="https://empresa.example",
                    final_url="https://empresa.example",
                    loaded=True,
                    status_code=200,
                    ux_score=74,
                ),
            )
            self._save(db, stored)
            current = Lead(
                name="Empresa Browser Auditada",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-browser",
                website="https://empresa.example",
            )
            result = LeadMemory(db).hydrate(current)
            self.assertTrue(result.matched)
            self.assertIsNotNone(current.browser_audit)
            self.assertEqual(current.browser_audit.ux_score, 74)

    def test_stale_not_found_state_returns_to_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            stored = Lead(
                name="Empresa Sem Site",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-sem-site",
                website_status=WebsiteStatus.NOT_FOUND,
                field_confidence={"website": 0.68},
                evidence=[
                    Evidence(
                        source="fake",
                        kind="website_not_found",
                        target_field="website",
                        confidence=0.68,
                        observed_at="2025-01-01T00:00:00+00:00",
                    )
                ],
            )
            self._save(db, stored)
            current = Lead(
                name="Empresa Sem Site",
                city="Praia Grande",
                state="SP",
                provider_url="https://instagram.com/empresa-sem-site",
            )
            LeadMemory(db).hydrate(current)
            self.assertEqual(current.website_status, WebsiteStatus.UNKNOWN)


    def test_recent_visual_audit_is_restored_for_same_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            stored = Lead(
                name="Empresa Visual Auditada", city="Praia Grande", state="SP",
                provider_url="https://instagram.com/empresa-visual",
                website="https://empresa.example", field_confidence={"website": 0.95},
                visual_audit=VisualAudit(
                    overall_score=58, desktop_score=60, mobile_score=56, modernity_score=50,
                    hierarchy_score=62, brand_coherence_score=60, readability_score=70,
                    conversion_clarity_score=45, confidence=0.86,
                ),
            )
            self._save(db, stored)
            current = Lead(
                name="Empresa Visual Auditada", city="Praia Grande", state="SP",
                provider_url="https://instagram.com/empresa-visual", website="https://empresa.example",
            )
            result = LeadMemory(db).hydrate(current)
            self.assertTrue(result.matched)
            self.assertIsNotNone(current.visual_audit)
            self.assertEqual(current.visual_audit.overall_score, 58)


if __name__ == "__main__":
    unittest.main()
