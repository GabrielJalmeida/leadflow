from __future__ import annotations

from urllib.parse import urlparse

from .models import Evidence, Lead, SearchGoal, WebsiteStatus
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
    """Legacy lightweight enrichment.

    Important: failure to find a website here keeps the state UNKNOWN. Only the
    future LeadInvestigator may promote UNKNOWN -> NOT_FOUND after dedicated
    verification.
    """

    query = f'"{lead.name}" "{goal.city}" {goal.state}'.strip()
    hits = provider.search_web(query, country="BR", count=8)
    for hit in hits:
        lead.evidence.append(Evidence(source=provider.name, kind="web_search", url=hit.url, detail=hit.title))
        if is_social(hit.url) and hit.url not in lead.socials:
            lead.socials.append(hit.url)
            lead.field_confidence["socials"] = max(lead.field_confidence.get("socials", 0.0), 0.55)
        elif lead.website is None and is_candidate_business_site(hit.url):
            lead.website = hit.url
            lead.website_status = WebsiteStatus.PRESENT
            lead.field_confidence["website"] = max(lead.field_confidence.get("website", 0.0), 0.55)
            lead.evidence.append(
                Evidence(
                    source=provider.name,
                    kind="website_candidate",
                    target_field="website",
                    url=hit.url,
                    confidence=0.55,
                    detail=hit.title,
                )
            )
    return lead
