from __future__ import annotations

import re
import unicodedata

from .models import Lead


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def lead_key(lead: Lead) -> str:
    phone = normalize_phone(lead.phone)
    if len(phone) >= 8:
        return f"phone:{phone}"
    provider_id = (lead.provider_id or "").strip()
    if provider_id:
        return f"provider:{lead.source_provider}:{provider_id}"
    return f"name:{normalize_text(lead.name)}|{normalize_text(lead.city)}|{normalize_text(lead.state)}"


def merge_leads(current: Lead, incoming: Lead) -> Lead:
    for attr in (
        "address", "phone", "email", "website", "rating", "review_count",
        "latitude", "longitude", "provider_id", "provider_url",
    ):
        if getattr(current, attr) in (None, "") and getattr(incoming, attr) not in (None, ""):
            setattr(current, attr, getattr(incoming, attr))

    current.socials = list(dict.fromkeys([*current.socials, *incoming.socials]))
    current.categories = list(dict.fromkeys([*current.categories, *incoming.categories]))
    current.evidence.extend(incoming.evidence)
    if incoming.discovered_query and incoming.discovered_query not in current.discovered_query.split(" | "):
        current.discovered_query = " | ".join(filter(None, [current.discovered_query, incoming.discovered_query]))
    return current
