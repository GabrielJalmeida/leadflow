from __future__ import annotations

import re
from urllib.parse import urlparse

from ..http import JsonHttpClient
from ..models import Evidence, Lead, SearchGoal, WebHit


_SOCIAL_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "linkedin.com",
    "www.linkedin.com",
    "tiktok.com",
    "www.tiktok.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "youtube.com",
    "www.youtube.com",
}

_DIRECTORY_HINTS = (
    "tripadvisor.", "yelp.", "foursquare.", "mapquest.", "yellowpages.",
    "guiamais.", "telelistas.", "solutudo.", "econodata.", "cnpj.",
)


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split(":", 1)[0]
    except Exception:
        return ""


def _looks_like_social(url: str) -> bool:
    return _host(url) in _SOCIAL_HOSTS


def _looks_like_business_site(url: str) -> bool:
    host = _host(url)
    if not host or host in _SOCIAL_HOSTS:
        return False
    return not any(hint in host for hint in _DIRECTORY_HINTS)


def _float_pair(value: object) -> tuple[float | None, float | None]:
    if not isinstance(value, list) or len(value) < 2:
        return None, None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None, None


def _clean_phone(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class BraveSearchProvider:
    """Brave provider for both local business and web search.

    Docs:
      local: https://api.search.brave.com/res/v1/local/place_search
      web:   https://api.search.brave.com/res/v1/web/search
    """

    name = "brave"
    PLACE_URL = "https://api.search.brave.com/res/v1/local/place_search"
    WEB_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, *, http: JsonHttpClient | None = None):
        if not api_key.strip():
            raise ValueError("Brave Search API key is required.")
        self.api_key = api_key.strip()
        self.http = http or JsonHttpClient()

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Subscription-Token": self.api_key}

    def validate_key(self) -> tuple[bool, str]:
        try:
            data = self.http.get_json(
                self.PLACE_URL,
                params={"q": "coffee", "location": "Sao Paulo Brazil", "country": "BR", "count": 1},
                headers=self._headers,
            )
        except Exception as exc:
            return False, str(exc)
        if isinstance(data.get("results"), list):
            return True, "OK"
        return False, "Resposta inesperada da Brave Place Search API."

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20) -> list[Lead]:
        count = max(1, min(int(count), 100))
        data = self.http.get_json(
            self.PLACE_URL,
            params={
                "q": query,
                "location": goal.location_label,
                "country": "BR" if goal.country.lower() in {"brazil", "brasil", "br"} else None,
                "units": "metric",
                "safesearch": "moderate",
                "count": count,
            },
            headers=self._headers,
        )
        items = data.get("results") or []
        leads: list[Lead] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            lead = self._parse_place(item, goal, query)
            if lead.name:
                leads.append(lead)
        return leads

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]:
        count = max(1, min(int(count), 20))
        data = self.http.get_json(
            self.WEB_URL,
            params={
                "q": query,
                "country": country,
                "count": count,
                "extra_snippets": "true",
            },
            headers=self._headers,
        )
        results = ((data.get("web") or {}).get("results") or [])
        hits: list[WebHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or not title:
                continue
            description = str(item.get("description") or "").strip()
            hits.append(WebHit(title=title, url=url, description=description, query=query))
        return hits

    def _parse_place(self, item: dict, goal: SearchGoal, query: str) -> Lead:
        address = item.get("postal_address") if isinstance(item.get("postal_address"), dict) else {}
        contact = item.get("contact") if isinstance(item.get("contact"), dict) else {}
        rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}

        lat, lon = _float_pair(item.get("coordinates"))
        # Brave documents coordinates as a [lat, long] pair.
        display_address = str(address.get("displayAddress") or "").strip() or None
        city = str(address.get("addressLocality") or goal.city).strip()
        state = str(address.get("addressRegion") or goal.state).strip()
        country = str(address.get("country") or goal.country).strip()

        related_urls: list[str] = []
        for nested in item.get("results") or []:
            if isinstance(nested, dict):
                url = str(nested.get("url") or "").strip()
                if url:
                    related_urls.append(url)
        for profile in item.get("profiles") or []:
            if isinstance(profile, dict):
                url = str(profile.get("url") or "").strip()
                if url:
                    related_urls.append(url)

        socials = list(dict.fromkeys(url for url in related_urls if _looks_like_social(url)))
        website = next((url for url in related_urls if _looks_like_business_site(url)), None)

        provider_url = str(item.get("provider_url") or item.get("url") or "").strip() or None
        title = str(item.get("title") or "").strip()
        categories = [str(x).strip() for x in (item.get("categories") or []) if str(x).strip()]

        evidence = [Evidence(source=self.name, kind="local_search", url=provider_url, detail=query)]
        for url in related_urls[:6]:
            evidence.append(Evidence(source=self.name, kind="related_web", url=url, detail=title))

        return Lead(
            name=title,
            city=city,
            state=state,
            country=country,
            address=display_address,
            phone=_clean_phone(contact.get("telephone")),
            email=str(contact.get("email") or "").strip() or None,
            website=website,
            socials=socials,
            categories=categories,
            rating=_maybe_float(rating.get("ratingValue")),
            review_count=_maybe_int(rating.get("reviewCount")),
            latitude=lat,
            longitude=lon,
            provider_id=str(item.get("id") or "").strip() or None,
            provider_url=provider_url,
            source_provider=self.name,
            discovered_query=query,
            evidence=evidence,
            raw=item,
        )


def _maybe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
