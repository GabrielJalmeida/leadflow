from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import Lead
from .validation import is_digital_contact_phone, is_plausible_phone


_GENERIC_NAMES = {
    "instagram", "facebook", "linkedin", "tiktok", "youtube", "whatsapp",
    "marcenaria", "marceneiro", "moveis planejados", "móveis planejados",
    "empresa", "profissional", "servicos", "serviços",
}
_MARKETING_PREFIXES = (
    "conheca ", "conheça ", "mais detalhes", "quer um orcamento", "quer um orçamento",
    "veja ", "confira ", "saiba mais", "acesse ", "clique ", "fale conosco",
    "transforme ", "descubra ", "a loja mais ", "o melhor ", "os melhores ",
)
_DIRECTORY_HOST_TOKENS = (
    "marcenarias.net.br", "acheioprofissional.", "servilink.", "guiamais.",
    "telelistas.", "solutudo.", "econodata.", "cnpj.", "yelp.", "foursquare.",
)


@dataclass(slots=True)
class QualityDecision:
    accepted: bool
    reasons: list[str]


def assess_lead_quality(lead: Lead, *, segment: str = "") -> QualityDecision:
    """Conservative pre-storage quality gate for discovered lead candidates.

    This gate intentionally favors false negatives over contaminating the lead
    database with post titles, platform labels, directory pages, or malformed
    contact data. It does not replace entity resolution.
    """

    reasons: list[str] = []
    name = " ".join((lead.name or "").split()).strip()
    folded = _fold(name)

    if not name or len(name) < 3:
        reasons.append("missing_or_too_short_name")
    if len(name) > 120 or len(name.split()) > 14:
        reasons.append("name_looks_like_sentence")
    if folded in {_fold(value) for value in _GENERIC_NAMES}:
        reasons.append("generic_name")
    if any(folded.startswith(_fold(prefix)) for prefix in _MARKETING_PREFIXES):
        reasons.append("marketing_copy_as_name")
    if name.endswith(("...", "…")):
        reasons.append("truncated_title_as_name")
    if name.count("!") + name.count("?") >= 1:
        reasons.append("sentence_punctuation_in_name")

    source_host = _host(lead.provider_url or "")
    if source_host and any(token in source_host for token in _DIRECTORY_HOST_TOKENS):
        # Directory-sourced businesses are allowed when an extractor returns a
        # genuine company name. Reject only when the candidate itself still
        # looks like the directory/listing title.
        if " em " in folded and segment and _fold(segment) in folded:
            reasons.append("directory_page_as_business")
        if "marcenarias.net.br" in folded or "lista" in folded:
            reasons.append("directory_page_as_business")

    return QualityDecision(accepted=not reasons, reasons=list(dict.fromkeys(reasons)))


def sanitize_lead_fields(lead: Lead, *, digital_only: bool = False) -> int:
    """Remove invalid fields and fixed lines from digital-first actionable contact."""
    removed = 0
    invalid = lead.phone and not is_plausible_phone(lead.phone, country=lead.country)
    not_digital = lead.phone and digital_only and not is_digital_contact_phone(lead.phone, country=lead.country)
    if invalid or not_digital:
        lead.phone = None
        lead.field_confidence.pop("phone", None)
        removed += 1
    return removed


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold().split(":", 1)[0]
    except Exception:
        return ""


def _fold(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip()
