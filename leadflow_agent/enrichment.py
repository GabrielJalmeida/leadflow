from __future__ import annotations

from urllib.parse import urlparse

from .dedupe import normalize_phone, normalize_text
from .identity import IdentityCandidate, assess_identity, is_rejected_candidate, record_rejected_candidate
from .models import Evidence, IdentityStatus, Lead, SearchGoal, WebsiteStatus
from .providers.base import WebSearchProvider


SOCIAL_HOSTS = {
    "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com", "tiktok.com", "www.tiktok.com",
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "youtube.com", "www.youtube.com",
}
DIRECTORY_HINTS = (
    "tripadvisor.", "yelp.", "foursquare.", "guiamais.", "telelistas.",
    "solutudo.", "econodata.", "cnpj.", "jusbrasil.", "reclameaqui.",
)


def host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold().split(":", 1)[0]
    except Exception:
        return ""


def is_social(url: str) -> bool:
    return host(url) in SOCIAL_HOSTS


def is_candidate_business_site(url: str) -> bool:
    domain = host(url)
    if not domain or domain in SOCIAL_HOSTS:
        return False
    return not any(token in domain for token in DIRECTORY_HINTS)


def enrich_lead_from_web(lead: Lead, goal: SearchGoal, provider: WebSearchProvider) -> Lead:
    """Conservative legacy enrichment with identity checks.

    A website is no longer attached merely because its result title resembles
    the business name. The hit needs corroborating identity evidence such as
    the expected locality or the lead's known phone. Ambiguous candidates are
    preserved as evidence for the future LeadInvestigator.
    """

    query = f'"{lead.name}" "{goal.city}" {goal.state}'.strip()
    hits = provider.search_web(query, country="BR", count=8)
    for hit in hits:
        lead.evidence.append(
            Evidence(source=provider.name, kind="web_search", url=hit.url, detail=hit.title)
        )
        if is_social(hit.url):
            if hit.url not in lead.socials:
                lead.socials.append(hit.url)
                lead.field_confidence["socials"] = max(
                    lead.field_confidence.get("socials", 0.0), 0.55
                )
            continue

        if lead.website is not None or not is_candidate_business_site(hit.url):
            continue
        if is_rejected_candidate(lead, value=hit.url, target_field="website"):
            continue

        candidate = _candidate_from_search_hit(lead, goal, hit.title, hit.description, hit.url)
        assessment = assess_identity(lead, candidate)
        lead.evidence.append(
            Evidence(
                source=provider.name,
                kind="website_identity_check",
                target_field="website",
                url=hit.url,
                confidence=assessment.confidence,
                detail=f"{assessment.status.value}: {'; '.join(assessment.reasons)}",
            )
        )

        if assessment.status in {IdentityStatus.MATCHED, IdentityStatus.PROBABLE_MATCH} and assessment.confidence >= 0.80:
            lead.website = hit.url
            lead.website_status = WebsiteStatus.PRESENT
            lead.field_confidence["website"] = max(
                lead.field_confidence.get("website", 0.0), assessment.confidence
            )
        elif assessment.status == IdentityStatus.MISMATCH:
            record_rejected_candidate(
                lead,
                value=hit.url,
                target_field="website",
                reason="identity_mismatch: " + "; ".join(assessment.reasons),
                source=provider.name,
                confidence=assessment.confidence,
                observed_name=candidate.name or None,
                observed_city=candidate.city or None,
                observed_state=candidate.state or None,
                observed_phone=candidate.phone,
            )

    return lead


def _candidate_from_search_hit(
    lead: Lead,
    goal: SearchGoal,
    title: str,
    description: str,
    url: str,
) -> IdentityCandidate:
    text = normalize_text(f"{title} {description}")
    lead_name = normalize_text(lead.name)
    expected_city = normalize_text(goal.city)
    expected_state = normalize_text(goal.state)

    observed_name = lead.name if lead_name and lead_name in text else title
    observed_city = goal.city if expected_city and expected_city in text else ""

    # State abbreviations are weak on their own, so only retain them when the
    # expected city is also explicitly present in the search evidence.
    observed_state = ""
    if observed_city and expected_state and expected_state in text.split():
        observed_state = goal.state

    observed_phone = None
    known_phone = normalize_phone(lead.phone)
    if known_phone and len(known_phone) >= 8:
        compact_text = normalize_phone(description)
        if known_phone in compact_text or known_phone[-8:] in compact_text:
            observed_phone = lead.phone

    return IdentityCandidate(
        name=observed_name,
        city=observed_city,
        state=observed_state,
        phone=observed_phone,
        website=url,
        source="web_search",
    )
