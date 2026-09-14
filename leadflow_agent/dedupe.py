from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from .models import Lead, WebsiteStatus
from .validation import is_digital_contact_phone


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


def _website_domain(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError:
        return ""
    host = parsed.netloc.casefold().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _instagram_identity(socials: list[str]) -> str:
    reserved = {"p", "reel", "reels", "stories", "explore", "accounts", "direct", "tv"}
    for value in socials:
        try:
            parsed = urlparse(value)
        except ValueError:
            continue
        host = parsed.netloc.casefold().split(":", 1)[0]
        if host not in {"instagram.com", "www.instagram.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].casefold() not in reserved:
            return parts[0].casefold()
    return ""


def _same_local_identity(a: Lead, b: Lead) -> bool:
    return (
        normalize_text(a.name) == normalize_text(b.name)
        and normalize_text(a.city) == normalize_text(b.city)
        and normalize_text(a.state) == normalize_text(b.state)
    )


def lead_key(lead: Lead) -> str:
    domain = _website_domain(lead.website)
    if domain:
        return f"domain:{domain}"
    instagram = _instagram_identity(lead.socials)
    if instagram:
        return f"instagram:{instagram}"
    provider_id = (lead.provider_id or "").strip()
    if provider_id:
        return f"provider:{lead.source_provider}:{provider_id}"
    if is_digital_contact_phone(lead.phone, country=lead.country):
        phone = normalize_phone(lead.phone)
        if len(phone) >= 8:
            return f"mobile:{phone}"
    return f"name:{normalize_text(lead.name)}|{normalize_text(lead.city)}|{normalize_text(lead.state)}"


def find_duplicate_key(existing: dict[str, Lead], incoming: Lead) -> str | None:
    direct = lead_key(incoming)
    if direct in existing:
        return direct

    incoming_domain = _website_domain(incoming.website)
    incoming_instagram = _instagram_identity(incoming.socials)
    incoming_mobile = normalize_phone(incoming.phone) if is_digital_contact_phone(incoming.phone, country=incoming.country) else ""

    for key, current in existing.items():
        current_domain = _website_domain(current.website)
        current_instagram = _instagram_identity(current.socials)
        current_mobile = normalize_phone(current.phone) if is_digital_contact_phone(current.phone, country=current.country) else ""

        if incoming_domain and current_domain and incoming_domain == current_domain:
            return key
        if incoming_instagram and current_instagram and incoming_instagram == current_instagram:
            return key
        if incoming.provider_id and current.provider_id and incoming.source_provider == current.source_provider and incoming.provider_id == current.provider_id:
            return key
        if incoming_mobile and current_mobile and incoming_mobile == current_mobile:
            return key

        if not _same_local_identity(current, incoming):
            continue
        if incoming_domain and current_domain and incoming_domain != current_domain:
            continue
        if incoming_instagram and current_instagram and incoming_instagram != current_instagram:
            continue
        if incoming_mobile and current_mobile and incoming_mobile != current_mobile:
            continue
        return key
    return None


def merge_leads(current: Lead, incoming: Lead) -> Lead:
    for attr in (
        "address", "email", "website", "rating", "review_count",
        "latitude", "longitude", "provider_id", "provider_url",
    ):
        if getattr(current, attr) in (None, "") and getattr(incoming, attr) not in (None, ""):
            setattr(current, attr, getattr(incoming, attr))

    if incoming.phone:
        current_is_digital = is_digital_contact_phone(current.phone, country=current.country)
        incoming_is_digital = is_digital_contact_phone(incoming.phone, country=incoming.country)
        if not current.phone or (incoming_is_digital and not current_is_digital):
            current.phone = incoming.phone

    if current.website:
        current.website_status = WebsiteStatus.PRESENT
    elif current.website_status == WebsiteStatus.UNKNOWN and incoming.website_status != WebsiteStatus.UNKNOWN:
        current.website_status = incoming.website_status

    current.discovery_confidence = max(current.discovery_confidence, incoming.discovery_confidence)
    for field_name, confidence in incoming.field_confidence.items():
        current.field_confidence[field_name] = max(current.field_confidence.get(field_name, 0.0), confidence)

    current.socials = list(dict.fromkeys([*current.socials, *incoming.socials]))
    current.categories = list(dict.fromkeys([*current.categories, *incoming.categories]))
    current.evidence.extend(incoming.evidence)
    if incoming.discovered_query and incoming.discovered_query not in current.discovered_query.split(" | "):
        current.discovered_query = " | ".join(filter(None, [current.discovered_query, incoming.discovered_query]))
    return current
