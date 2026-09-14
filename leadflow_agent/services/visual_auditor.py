from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from ..models import Evidence, Lead, VisualAudit


class VisualAnalysisProvider(Protocol):
    name: str

    def analyze_visual_audit(
        self,
        lead: Lead,
        *,
        desktop_screenshot: str | Path,
        mobile_screenshot: str | Path,
    ) -> VisualAudit: ...


@dataclass(slots=True)
class VisualAuditOutcome:
    audit: VisualAudit
    reused: bool = False


class VisualAuditor:
    """Subjective visual review over deterministic browser screenshots.

    This layer deliberately cannot change business identity or technical facts.
    It only assesses visible presentation quality, with an explicit confidence.
    """

    def __init__(self, provider: VisualAnalysisProvider) -> None:
        self.provider = provider

    def audit(
        self,
        lead: Lead,
        *,
        max_age_days: int = 14,
        force: bool = False,
    ) -> VisualAuditOutcome:
        browser = lead.browser_audit
        if browser is None or not browser.loaded:
            raise ValueError("lead has no successful browser audit")
        if not browser.desktop_screenshot or not browser.mobile_screenshot:
            raise ValueError("browser audit has no desktop/mobile screenshots")

        desktop = Path(browser.desktop_screenshot)
        mobile = Path(browser.mobile_screenshot)
        if not desktop.exists() or not mobile.exists():
            raise FileNotFoundError("browser screenshots are missing from disk")

        if not force and _audit_is_fresh(lead.visual_audit, max_age_days=max_age_days):
            assert lead.visual_audit is not None
            return VisualAuditOutcome(audit=lead.visual_audit, reused=True)

        audit = self.provider.analyze_visual_audit(
            lead,
            desktop_screenshot=desktop,
            mobile_screenshot=mobile,
        )
        lead.visual_audit = audit
        lead.evidence.append(
            Evidence(
                source=f"visual_audit:{self.provider.name}",
                kind="visual_audit",
                target_field="website",
                url=browser.final_url or lead.website,
                detail=(
                    f"visual_score={audit.overall_score}; confidence={audit.confidence:.2f}; "
                    f"modernity={audit.modernity_score}; hierarchy={audit.hierarchy_score}"
                ),
                confidence=audit.confidence,
            )
        )
        return VisualAuditOutcome(audit=audit, reused=False)


def _audit_is_fresh(audit: VisualAudit | None, *, max_age_days: int) -> bool:
    if audit is None:
        return False
    try:
        observed = datetime.fromisoformat(audit.analyzed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc) >= (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
    )
