from __future__ import annotations

from dataclasses import dataclass

from .models import (
    IdentityStatus,
    Lead,
    OpportunityAssessment,
    OpportunityType,
    WebsiteStatus,
)


@dataclass(slots=True)
class _Components:
    service_need: int = 0
    contactability: int = 0
    activity: int = 0

    @property
    def total(self) -> int:
        return self.service_need + self.contactability + self.activity


def assess_opportunity(lead: Lead) -> OpportunityAssessment:
    """Build an explainable commercial-opportunity assessment.

    The engine deliberately separates need from trust. A technically broken site
    can be a strong service fit, but an unverified business/site association is
    not actionable yet. Visual/design quality is also not inferred from HTTP/HTML
    checks; technically healthy sites remain REVIEW_NEEDED until a visual audit
    exists in a future phase.
    """

    reasons: list[str] = []
    cautions: list[str] = []
    components = _Components()

    if lead.identity_status == IdentityStatus.MISMATCH:
        assessment = OpportunityAssessment(
            type=OpportunityType.UNKNOWN,
            score=0,
            actionable=False,
            service_fit="do_not_contact",
            reasons=["identidade marcada como mismatch"],
            cautions=["dados podem pertencer a outra empresa"],
        )
        lead.opportunity = assessment
        lead.score = 0
        lead.score_reasons = assessment.reasons + assessment.cautions
        return assessment

    components.contactability, contact_reasons = _contactability(lead)
    reasons.extend(contact_reasons)

    components.activity, activity_reasons = _activity(lead)
    reasons.extend(activity_reasons)

    opp_type, service_fit, need_score, need_reasons, need_cautions = _service_need(lead)
    components.service_need = need_score
    reasons.extend(need_reasons)
    cautions.extend(need_cautions)

    raw = min(100, components.total)
    actionable = _is_actionable(lead)

    # False association is worse than missing information. Keep promising but
    # unverified opportunities visible without letting them outrank verified ones.
    if not actionable:
        raw = min(raw, 55)
        cautions.append("verificar identidade antes de abordagem comercial")

    # Low evidence should not masquerade as precision even if the need looks high.
    if lead.confidence_score and lead.confidence_score < 50:
        raw = min(raw, 60)
        cautions.append("confiança geral do lead ainda é baixa")

    assessment = OpportunityAssessment(
        type=opp_type,
        score=max(0, raw),
        actionable=actionable,
        service_fit=service_fit,
        service_need_score=components.service_need,
        contactability_score=components.contactability,
        activity_score=components.activity,
        website_health_score=(lead.website_audit.technical_score if lead.website_audit else None),
        reasons=reasons,
        cautions=_unique(cautions),
    )
    lead.opportunity = assessment
    lead.score = assessment.score
    lead.score_reasons = assessment.reasons + [f"ATENÇÃO: {item}" for item in assessment.cautions]
    return assessment


def _contactability(lead: Lead) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if lead.phone:
        score += 15
        reasons.append("telefone disponível +15")
    if lead.socials:
        score += 6
        reasons.append("canal social disponível +6")
    if lead.email:
        score += 4
        reasons.append("e-mail disponível +4")
    return min(score, 25), reasons


def _activity(lead: Lead) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if lead.review_count is not None:
        if lead.review_count >= 20:
            score += 12
            reasons.append("20+ avaliações: forte sinal de atividade +12")
        elif lead.review_count >= 5:
            score += 8
            reasons.append("5+ avaliações: sinal de atividade +8")
        elif lead.review_count > 0:
            score += 4
            reasons.append("possui avaliações +4")
    if lead.rating is not None and lead.rating >= 4.0:
        score += 3
        reasons.append("rating >= 4.0 +3")
    if lead.socials:
        score += 5
        reasons.append("presença social reforça atividade +5")
    return min(score, 20), reasons


def _service_need(
    lead: Lead,
) -> tuple[OpportunityType, str, int, list[str], list[str]]:
    reasons: list[str] = []
    cautions: list[str] = []

    if lead.website_status == WebsiteStatus.NOT_FOUND:
        reasons.append("ausência de site investigada: oportunidade de primeiro site +45")
        return OpportunityType.NEW_SITE, "new_website", 45, reasons, cautions

    if lead.website_status == WebsiteStatus.UNREACHABLE:
        reasons.append("site identificado, mas indisponível: forte oportunidade de rebuild +55")
        return OpportunityType.REBUILD, "website_rebuild", 55, reasons, cautions

    if lead.website_status == WebsiteStatus.UNKNOWN:
        reasons.append("estado do site ainda não resolvido +20")
        cautions.append("investigar website antes de definir oferta")
        return OpportunityType.REVIEW_NEEDED, "investigate_first", 20, reasons, cautions

    audit = lead.website_audit
    if audit is None:
        reasons.append("site existe, mas ainda não foi auditado +18")
        cautions.append("auditoria técnica/visual necessária")
        return OpportunityType.REVIEW_NEEDED, "website_review", 18, reasons, cautions

    if not audit.reachable or audit.status_code is None:
        reasons.append("auditoria não conseguiu alcançar o site: oportunidade de rebuild +55")
        if audit.error:
            cautions.append(f"falha observada: {audit.error}")
        return OpportunityType.REBUILD, "website_rebuild", 55, reasons, cautions

    browser = lead.browser_audit
    if browser is not None and browser.loaded:
        if browser.ux_score <= 40:
            reasons.append(f"browser UX {browser.ux_score}/100: problemas severos de experiência mobile/conversão +46")
            cautions.append("avaliação visual/estética ainda não foi realizada")
            return OpportunityType.REDESIGN, "website_redesign", 46, reasons, cautions
        if browser.ux_score <= 65:
            reasons.append(f"browser UX {browser.ux_score}/100: fricções de mobile/CTA detectadas +34")
            cautions.append("estética e posicionamento visual ainda exigem revisão")
            return OpportunityType.OPTIMIZATION, "website_optimization", 34, reasons, cautions

    visual = lead.visual_audit
    if visual is not None and visual.confidence >= 0.55:
        if visual.overall_score <= 40:
            reasons.append(
                f"visual quality {visual.overall_score}/100: forte oportunidade de redesign +46"
            )
            cautions.append(
                f"avaliação visual por IA com confiança {visual.confidence:.0%}; revisar screenshot antes da abordagem"
            )
            return OpportunityType.REDESIGN, "website_redesign", 46, reasons, cautions
        if visual.overall_score <= 60:
            reasons.append(
                f"visual quality {visual.overall_score}/100: apresentação visivelmente defasada/inconsistente +38"
            )
            cautions.append(
                f"avaliação visual por IA com confiança {visual.confidence:.0%}; usar como apoio, não como fato absoluto"
            )
            return OpportunityType.REDESIGN, "website_redesign", 38, reasons, cautions
        if visual.overall_score <= 75:
            reasons.append(
                f"visual quality {visual.overall_score}/100: espaço visível para refinamento +27"
            )
            cautions.append("oportunidade visual moderada; confirmar manualmente antes do pitch")
            return OpportunityType.OPTIMIZATION, "website_optimization", 27, reasons, cautions

    score = audit.technical_score
    if score <= 30:
        reasons.append(f"website health {score}/100: problemas técnicos severos +50")
        return OpportunityType.REBUILD, "website_rebuild", 50, reasons, cautions
    if score <= 55:
        reasons.append(f"website health {score}/100: forte espaço para modernização +42")
        return OpportunityType.REDESIGN, "website_redesign", 42, reasons, cautions
    if score <= 75:
        reasons.append(f"website health {score}/100: melhorias técnicas/conversão +30")
        return OpportunityType.OPTIMIZATION, "website_optimization", 30, reasons, cautions
    if score <= 90:
        reasons.append(f"website health {score}/100: base técnica razoável +20")
        cautions.append("qualidade visual e posicionamento ainda não foram avaliados")
        return OpportunityType.REVIEW_NEEDED, "visual_review", 20, reasons, cautions

    reasons.append(f"website health {score}/100: baseline técnico saudável +10")
    if visual is not None and visual.confidence >= 0.55:
        cautions.append(
            f"visual quality {visual.overall_score}/100 (confiança {visual.confidence:.0%}); "
            "site tecnicamente saudável pode ainda ter oportunidade visual"
        )
    elif browser is not None:
        cautions.append(f"browser UX {browser.ux_score}/100; estética/branding ainda não foram avaliados")
    else:
        cautions.append("100/100 técnico não mede design, estética, conteúdo ou competitividade")
    return OpportunityType.REVIEW_NEEDED, "visual_review", 10, reasons, cautions


def _is_actionable(lead: Lead) -> bool:
    return lead.identity_status in {IdentityStatus.MATCHED, IdentityStatus.PROBABLE_MATCH}


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
