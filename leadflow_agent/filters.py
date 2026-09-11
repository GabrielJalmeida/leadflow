from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Lead, OpportunityType, WebsiteStatus


class Presence(str, Enum):
    ANY = "any"
    PRESENT = "present"
    MISSING = "missing"


class Readiness(str, Enum):
    ANY = "any"
    READY = "ready"
    VERIFY = "verify"


@dataclass(slots=True)
class LeadFilterSpec:
    website_states: set[WebsiteStatus] = field(default_factory=set)
    instagram: Presence = Presence.ANY
    phone: Presence = Presence.ANY
    email: Presence = Presence.ANY
    readiness: Readiness = Readiness.ANY
    opportunity_types: set[OpportunityType] = field(default_factory=set)
    min_opportunity_score: int | None = None
    max_technical_score: int | None = None
    max_browser_score: int | None = None
    max_visual_score: int | None = None
    min_visual_confidence: float = 0.55
    require_any_contact: bool = False

    @property
    def active(self) -> bool:
        return any((
            self.website_states,
            self.instagram != Presence.ANY,
            self.phone != Presence.ANY,
            self.email != Presence.ANY,
            self.readiness != Readiness.ANY,
            self.opportunity_types,
            self.min_opportunity_score is not None,
            self.max_technical_score is not None,
            self.max_browser_score is not None,
            self.max_visual_score is not None,
            self.require_any_contact,
        ))


@dataclass(frozen=True, slots=True)
class FilterDecision:
    accepted: bool
    reasons: tuple[str, ...] = ()


def _has_instagram(lead: Lead) -> bool:
    return any("instagram.com" in (url or "").lower() for url in lead.socials)


def _presence_matches(value: bool, requirement: Presence) -> bool:
    if requirement == Presence.ANY:
        return True
    return value if requirement == Presence.PRESENT else not value


def assess_filter(lead: Lead, spec: LeadFilterSpec) -> FilterDecision:
    reasons: list[str] = []

    if spec.website_states and lead.website_status not in spec.website_states:
        reasons.append(f"website={lead.website_status.value}")
    if not _presence_matches(_has_instagram(lead), spec.instagram):
        reasons.append("instagram")
    if not _presence_matches(bool(lead.phone), spec.phone):
        reasons.append("phone")
    if not _presence_matches(bool(lead.email), spec.email):
        reasons.append("email")

    actionable = bool(lead.opportunity and lead.opportunity.actionable)
    if spec.readiness == Readiness.READY and not actionable:
        reasons.append("not_ready")
    elif spec.readiness == Readiness.VERIFY and actionable:
        reasons.append("already_ready")

    if spec.opportunity_types:
        current = lead.opportunity.type if lead.opportunity else OpportunityType.UNKNOWN
        if current not in spec.opportunity_types:
            reasons.append(f"opportunity={current.value}")

    if spec.min_opportunity_score is not None and lead.score < spec.min_opportunity_score:
        reasons.append("opportunity_score")

    if spec.max_technical_score is not None:
        if lead.website_audit is None:
            reasons.append("technical_audit_missing")
        elif lead.website_audit.technical_score > spec.max_technical_score:
            reasons.append("technical_score")

    if spec.max_browser_score is not None:
        if lead.browser_audit is None:
            reasons.append("browser_audit_missing")
        elif lead.browser_audit.ux_score > spec.max_browser_score:
            reasons.append("browser_score")

    if spec.max_visual_score is not None:
        if lead.visual_audit is None:
            reasons.append("visual_audit_missing")
        elif lead.visual_audit.confidence < spec.min_visual_confidence:
            reasons.append("visual_confidence")
        elif lead.visual_audit.overall_score > spec.max_visual_score:
            reasons.append("visual_score")

    if spec.require_any_contact and not (lead.phone or lead.email or lead.socials):
        reasons.append("no_contact_channel")

    return FilterDecision(accepted=not reasons, reasons=tuple(reasons))
