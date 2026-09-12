from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .validation import is_digital_contact_phone


@dataclass(slots=True)
class ContactRoute:
    channel: str
    label: str
    whatsapp_number: str | None = None
    instagram_url: str | None = None
    whatsapp_source: str | None = None


def _normalize_whatsapp_number(phone: str | None, *, country: str = "Brazil") -> str | None:
    if not phone:
        return None
    raw = str(phone).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None

    country_folded = country.strip().casefold()
    if country_folded in {"brazil", "brasil", "br"}:
        if len(digits) in {10, 11}:
            digits = "55" + digits
        if not (digits.startswith("55") and len(digits) in {12, 13}):
            return None
        return digits

    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return digits
    return digits if 8 <= len(digits) <= 15 else None


def _instagram_profile_url(socials: list[str]) -> str | None:
    reserved = {"p", "reel", "reels", "stories", "explore", "accounts", "direct", "tv"}
    for value in socials:
        try:
            parsed = urlparse(str(value))
        except ValueError:
            continue
        host = parsed.netloc.casefold().split(":", 1)[0]
        if host not in {"instagram.com", "www.instagram.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if not parts or parts[0].casefold() in reserved:
            continue
        username = parts[0]
        return f"https://www.instagram.com/{username}/"
    return None


def _explicit_whatsapp_number(socials: list[str]) -> str | None:
    for value in socials:
        try:
            parsed = urlparse(str(value))
        except ValueError:
            continue
        host = parsed.netloc.casefold().split(":", 1)[0]
        if host in {"wa.me", "www.wa.me"}:
            digits = re.sub(r"\D", "", parsed.path)
            if 8 <= len(digits) <= 15:
                return digits
        if host in {"api.whatsapp.com", "www.whatsapp.com", "whatsapp.com"}:
            query = parse_qs(parsed.query)
            candidate = (query.get("phone") or [""])[0]
            digits = re.sub(r"\D", "", candidate)
            if 8 <= len(digits) <= 15:
                return digits
    return None


def resolve_contact_route(lead: dict[str, Any]) -> ContactRoute:
    contact = lead.get("contact") or {}
    location = lead.get("location") or {}
    socials = [str(item) for item in (contact.get("socials") or []) if item]
    instagram = _instagram_profile_url(socials)

    explicit_whatsapp = _explicit_whatsapp_number(socials)
    if explicit_whatsapp:
        return ContactRoute(
            channel="whatsapp",
            label="WhatsApp",
            whatsapp_number=explicit_whatsapp,
            instagram_url=instagram,
            whatsapp_source="explicit",
        )

    phone = _normalize_whatsapp_number(
        contact.get("phone"),
        country=str(location.get("country") or "Brazil"),
    )
    raw_phone = contact.get("phone")
    if phone and is_digital_contact_phone(raw_phone, country=str(location.get("country") or "Brazil")):
        return ContactRoute(
            channel="whatsapp",
            label="WhatsApp?",
            whatsapp_number=phone,
            instagram_url=instagram,
            whatsapp_source="mobile_candidate",
        )

    # Fixed lines can have WhatsApp Business, but without explicit evidence we
    # prefer Instagram when available instead of pretending the phone is WhatsApp.
    if instagram:
        return ContactRoute(
            channel="instagram",
            label="Instagram",
            whatsapp_number=phone,
            instagram_url=instagram,
            whatsapp_source="phone_candidate" if phone else None,
        )


    return ContactRoute(channel="none", label="—")


def build_contact_message(lead: dict[str, Any]) -> str:
    name = str(lead.get("name") or "empresa").strip()
    opportunity = lead.get("opportunity") or {}
    kind = str(opportunity.get("type") or "unknown")

    if kind == "new_site":
        return (
            f"Olá! Tudo bem? Vi o trabalho da {name} e achei muito interessante. "
            "Trabalho com desenvolvimento de sites para negócios locais e tive algumas ideias "
            "de como apresentar os projetos e serviços de vocês na internet. "
            "Posso te mostrar uma ideia sem compromisso?"
        )
    if kind in {"rebuild", "redesign", "optimization"}:
        return (
            f"Olá! Tudo bem? Vi o trabalho da {name} e dei uma olhada na presença online de vocês. "
            "Trabalho com desenvolvimento web e tive algumas ideias para deixar a apresentação "
            "do negócio mais moderna e facilitar o contato dos clientes. "
            "Posso te mostrar uma ideia sem compromisso?"
        )
    return (
        f"Olá! Tudo bem? Conheci o trabalho da {name} e achei interessante. "
        "Trabalho com desenvolvimento web e tive algumas ideias que podem ajudar na presença "
        "digital de vocês. Posso te mostrar uma ideia sem compromisso?"
    )


def build_whatsapp_url(number: str, message: str) -> str:
    digits = re.sub(r"\D", "", number)
    if not digits:
        raise ValueError("Número de WhatsApp inválido.")
    return f"https://wa.me/{digits}?text={quote(message, safe='')}"
