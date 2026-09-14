from __future__ import annotations

from typing import Any

from ..http import JsonHttpClient
from ..models import Evidence, Lead, SearchGoal


class OutscraperSearchProvider:
    """Google Maps business discovery through the user's Outscraper key."""

    name = "outscraper"
    SEARCH_URL = "https://api.outscraper.com/maps/search"
    BALANCE_URL = "https://api.outscraper.com/profile/balance"

    def __init__(self, api_key: str, *, http: JsonHttpClient | None = None):
        if not api_key.strip():
            raise ValueError("Outscraper API key is required.")
        self.api_key = api_key.strip()
        self.http = http or JsonHttpClient(timeout=90)

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self.api_key}

    def validate_key(self) -> tuple[bool, str]:
        try:
            data = self.http.get_json(self.BALANCE_URL, headers=self._headers)
        except Exception as exc:
            return False, str(exc)
        status = str(data.get("account_status") or "").strip().lower()
        if status and status not in {"valid", "active"}:
            return False, f"Outscraper account_status={status}"
        return True, "OK"

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20) -> list[Lead]:
        count = max(1, min(int(count), 500))
        full_query = f"{query}, {goal.location_label}"
        data = self.http.get_json(
            self.SEARCH_URL,
            params={
                "query": full_query,
                "limit": count,
                "async": "false",
                "region": "BR" if goal.country.casefold() in {"brazil", "brasil", "br"} else None,
            },
            headers=self._headers,
        )
        items = _flatten_data(data.get("data"))
        leads: list[Lead] = []
        for item in items:
            lead = self._parse_place(item, goal, query)
            if lead.name:
                leads.append(lead)
        return leads

    def _parse_place(self, item: dict[str, Any], goal: SearchGoal, query: str) -> Lead:
        name = _text(item.get("name")) or ""
        site = _url(item.get("site"))
        location_link = _url(item.get("location_link")) or _url(item.get("reviews_link"))
        category = _text(item.get("category")) or _text(item.get("type"))
        subtypes = _text(item.get("subtypes"))
        categories: list[str] = []
        if category:
            categories.append(category)
        if subtypes:
            categories.extend(part.strip() for part in subtypes.split(",") if part.strip())
        categories = list(dict.fromkeys(categories))

        evidence = [Evidence(source=self.name, kind="local_search", url=location_link, detail=query)]
        if site:
            evidence.append(Evidence(source=self.name, kind="official_site", url=site, detail=name))

        return Lead(
            name=name,
            city=_text(item.get("city")) or goal.city,
            state=_text(item.get("state")) or goal.state,
            country=_text(item.get("country")) or goal.country,
            address=_text(item.get("full_address")),
            phone=_text(item.get("phone")),
            email=_text(item.get("email")),
            website=site,
            socials=_socials(item),
            categories=categories,
            rating=_maybe_float(item.get("rating")),
            review_count=_maybe_int(item.get("reviews")),
            latitude=_maybe_float(item.get("latitude")),
            longitude=_maybe_float(item.get("longitude")),
            provider_id=_text(item.get("place_id")) or _text(item.get("google_id")),
            provider_url=location_link,
            source_provider=self.name,
            discovered_query=query,
            evidence=evidence,
            raw=item,
        )


def _flatten_data(value: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        result.append(value)
    elif isinstance(value, list):
        for item in value:
            result.extend(_flatten_data(item))
    return result


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _url(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    return text if text.startswith(("http://", "https://")) else None


def _socials(item: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("instagram", "facebook", "linkedin", "youtube", "twitter", "tiktok"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            candidates.append(value)
    for key in ("socials", "profiles"):
        value = item.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry.startswith(("http://", "https://")):
                    candidates.append(entry)
                elif isinstance(entry, dict):
                    url = str(entry.get("url") or "").strip()
                    if url.startswith(("http://", "https://")):
                        candidates.append(url)
    return list(dict.fromkeys(candidates))


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
