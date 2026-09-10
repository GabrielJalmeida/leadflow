from __future__ import annotations

from .models import Lead


def score_lead(lead: Lead, *, prefer_no_website: bool = True) -> Lead:
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
        if not lead.website:
            score += 35
            reasons.append("site não identificado nas fontes consultadas +35")
        else:
            reasons.append("site identificado +0")
    elif lead.website:
        score += 10
        reasons.append("site identificado +10")

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
    lead.score_reasons = reasons
    return lead
