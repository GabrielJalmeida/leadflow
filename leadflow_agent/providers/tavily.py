from __future__ import annotations

import re
from urllib.parse import urlparse

from ..http import JsonHttpClient
from ..models import Evidence, Lead, WebHit, SearchGoal


SOCIAL_HOSTS = {
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com",
    "tiktok.com", "www.tiktok.com",
    "x.com", "www.x.com",
    "twitter.com", "www.twitter.com",
    "youtube.com", "www.youtube.com",
}
DIRECTORY_HINTS = (
    "servilink.", "acheioprofissional.", "guiamais.", "telelistas.",
    "solutudo.", "econodata.", "cnpj.", "jusbrasil.", "reclameaqui.",
    "yelp.", "foursquare.", "tripadvisor.",
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s*)?\(?\d{2}\)?[\s.-]*(?:9\s*)?\d{4}[\s.-]*\d{4}(?!\d)")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


class TavilySearchProvider:
    """Web search for lead discovery using the user's Tavily API key.

    Tavily returns evidence pages, not canonical business records. The agent can
    pair this provider with Gemini extraction to turn those pages/snippets into
    one or many Lead objects.
    """

    name = "tavily"
    SEARCH_URL = "https://api.tavily.com/search"
    USAGE_URL = "https://api.tavily.com/usage"

    def __init__(self, api_key: str, *, http: JsonHttpClient | None = None):
        if not api_key.strip():
            raise ValueError("Tavily API key is required.")
        self.api_key = api_key.strip()
        self.http = http or JsonHttpClient(timeout=45)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def validate_key(self) -> tuple[bool, str]:
        """Validate via /usage so doctor does not spend a search credit."""
        try:
            data = self.http.get_json(self.USAGE_URL, headers=self._headers)
        except Exception as exc:
            return False, str(exc)
        key = data.get("key")
        if not isinstance(key, dict):
            return False, "Resposta inesperada do endpoint /usage da Tavily."
        usage = key.get("usage")
        limit = key.get("limit")
        suffix = f" — uso {usage}/{limit}" if usage is not None and limit is not None else ""
        return True, f"OK{suffix}"

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]:
        count = max(1, min(int(count), 20))
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": count,
            "include_answer": False,
            "include_raw_content": False,
            "topic": "general",
        }
        if country.upper() in {"BR", "BRA", "BRAZIL"}:
            payload["country"] = "brazil"

        data = self.http.post_json(self.SEARCH_URL, payload=payload, headers=self._headers)
        hits: list[WebHit] = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            content = str(item.get("content") or "").strip()
            if not title or not url:
                continue
            hits.append(WebHit(title=title, url=url, description=content, query=query))
        return hits

    def heuristic_leads(self, hits: list[WebHit], goal: SearchGoal, *, query: str) -> list[Lead]:
        """Best-effort fallback when no LLM is configured.

        It only promotes direct business/social pages. Directory/list pages are
        preserved as evidence for Gemini mode but skipped here because parsing a
        list page as one business would create false leads.
        """
        leads: list[Lead] = []
        for hit in hits:
            domain = _host(hit.url)
            if _looks_like_directory(domain, hit.title):
                continue
            name = _business_name_from_title(hit.title)
            if not name:
                continue
            phone_match = PHONE_RE.search(hit.description or "")
            email_match = EMAIL_RE.search(hit.description or "")
            social = hit.url if domain in SOCIAL_HOSTS else None
            website = None if social else (hit.url if _candidate_site(hit.url) else None)
            lead = Lead(
                name=name,
                city=goal.city,
                state=goal.state,
                country=goal.country,
                phone=phone_match.group(0).strip() if phone_match else None,
                email=email_match.group(0).strip() if email_match else None,
                website=website,
                socials=[social] if social else [],
                categories=[goal.segment],
                provider_url=hit.url,
                source_provider=self.name,
                discovered_query=query,
                evidence=[Evidence(source=self.name, kind="web_search", url=hit.url, detail=hit.title)],
                raw={"title": hit.title, "description": hit.description, "url": hit.url},
            )
            leads.append(lead)
        return leads


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold().split(":", 1)[0]
    except Exception:
        return ""


def _looks_like_directory(domain: str, title: str) -> bool:
    if any(token in domain for token in DIRECTORY_HINTS):
        return True
    folded = title.casefold()
    markers = ("profissionais", "marcenarias /", "lista de ", "melhores ", "guia de ")
    return any(marker in folded for marker in markers)


def _candidate_site(url: str) -> bool:
    domain = _host(url)
    if not domain or domain in SOCIAL_HOSTS:
        return False
    return not any(token in domain for token in DIRECTORY_HINTS)


def _business_name_from_title(title: str) -> str:
    text = re.sub(r"\s*\(@[^)]*\)", "", title).strip()
    text = re.sub(r"\s+-\s+(Instagram|Facebook|LinkedIn|TikTok|YouTube).*$", "", text, flags=re.I).strip()
    # Common local-result title: "Business | Praia Grande ..."
    if " | " in text:
        text = text.split(" | ", 1)[0].strip()
    return text[:160].strip()
