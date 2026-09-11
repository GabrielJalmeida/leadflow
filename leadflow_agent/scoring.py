from __future__ import annotations

from .models import IdentityStatus, Lead, WebsiteStatus


def score_lead(lead: Lead, *, prefer_no_website: bool = True) -> Lead:
    """Calculate opportunity and evidence confidence separately.

    `lead.score` remains the opportunity score for backwards compatibility.
    `lead.confidence_score` describes how trustworthy/complete the evidence is.
    """

    score = 0
    reasons: list[str] = []

    if lead.phone:
        score += 25
        reasons.append("telefone encontrado +25")
    if lead.email:
        score += 5
        reasons.append("e-mail encontrado +5")
    if lead.socials:
        score += 10
        reasons.append("presença social encontrada +10")

    if prefer_no_website:
        if lead.website_status == WebsiteStatus.NOT_FOUND:
            score += 35
            reasons.append("ausência de site verificada +35")
        elif lead.website_status == WebsiteStatus.UNREACHABLE:
            score += 10
            reasons.append("site identificado, mas indisponível +10")
        elif lead.website_status == WebsiteStatus.PRESENT:
            reasons.append("site oficial identificado +0")
        else:
            reasons.append("site ainda não investigado +0")
    elif lead.website_status == WebsiteStatus.PRESENT:
        score += 10
        reasons.append("site oficial identificado +10")

    if lead.review_count is not None:
        if lead.review_count >= 20:
            score += 15
            reasons.append("20+ avaliações: sinal forte de atividade +15")
        elif lead.review_count >= 5:
            score += 10
            reasons.append("5+ avaliações: sinal de atividade +10")
        elif lead.review_count > 0:
            score += 5
            reasons.append("possui avaliações +5")

    if lead.rating is not None and lead.rating >= 4.0:
        score += 5
        reasons.append("rating >= 4.0 +5")

    lead.score = min(score, 100)
    lead.confidence_score = evidence_confidence_score(lead)
    lead.score_reasons = reasons
    return lead


def evidence_confidence_score(lead: Lead) -> int:
    """Heuristic trust score for the current prototype.

    This is deliberately conservative. It does not claim a field is verified
    merely because it exists; later the LeadInvestigator will attach multiple
    independent evidence records and make this stronger.
    """

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
