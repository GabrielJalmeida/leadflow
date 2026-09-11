from __future__ import annotations

from .models import IdentityStatus, Lead, WebsiteStatus
from .opportunity import assess_opportunity


def score_lead(lead: Lead, *, prefer_no_website: bool = True) -> Lead:
    """Calculate opportunity intelligence and evidence confidence separately.

    `prefer_no_website` remains in the signature for v0.x compatibility, but the
    v2 engine no longer assumes that no-site businesses are always better than
    businesses with weak websites.
    """

    lead.confidence_score = evidence_confidence_score(lead)
    assess_opportunity(lead)
    return lead


def evidence_confidence_score(lead: Lead) -> int:
    identity = lead.discovery_confidence
    if lead.identity_status in {IdentityStatus.MATCHED, IdentityStatus.PROBABLE_MATCH}:
        identity = max(identity, lead.identity_confidence)
    elif lead.identity_status == IdentityStatus.MISMATCH:
        identity = 0.0
    if identity <= 0 and lead.evidence:
        identity = 0.50

    score = identity * 60
    score += _field_points(lead, "phone", bool(lead.phone), 10)
    score += _field_points(lead, "email", bool(lead.email), 5)
    score += _field_points(
        lead,
        "website",
        lead.website_status == WebsiteStatus.PRESENT and bool(lead.website),
        10,
    )
    score += _field_points(lead, "socials", bool(lead.socials), 10)
    score += _field_points(lead, "address", bool(lead.address), 5)
    return min(100, max(0, round(score)))


def _field_points(lead: Lead, field: str, present: bool, max_points: int) -> float:
    if not present:
        return 0.0
    confidence = lead.field_confidence.get(field, 0.50)
    return max_points * max(0.0, min(confidence, 1.0))
