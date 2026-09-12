from __future__ import annotations

import re
from enum import Enum


class PhoneKind(str, Enum):
    MOBILE = "mobile"
    FIXED_LINE = "fixed_line"
    OTHER = "other"
    INVALID = "invalid"


def phone_digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def classify_phone(value: str | None, *, country: str = "Brazil") -> PhoneKind:
    """Classify a phone structurally without claiming that it is active."""
    digits = phone_digits(value)
    if not digits:
        return PhoneKind.INVALID

    if country.casefold() in {"brazil", "br", "brasil"}:
        if digits.startswith("55") and len(digits) in {12, 13}:
            digits = digits[2:]
        if len(digits) == 11:
            ddd, subscriber = digits[:2], digits[2:]
            if ddd[0] != "0" and subscriber.startswith("9"):
                return PhoneKind.MOBILE
            return PhoneKind.INVALID
        if len(digits) == 10:
            ddd, subscriber = digits[:2], digits[2:]
            if ddd[0] != "0" and subscriber[:1] in {"2", "3", "4", "5"}:
                return PhoneKind.FIXED_LINE
            return PhoneKind.INVALID
        return PhoneKind.INVALID

    return PhoneKind.OTHER if 7 <= len(digits) <= 15 else PhoneKind.INVALID


def is_digital_contact_phone(value: str | None, *, country: str = "Brazil") -> bool:
    return classify_phone(value, country=country) in {PhoneKind.MOBILE, PhoneKind.OTHER}


def is_plausible_phone(value: str | None, *, country: str = "Brazil") -> bool:
    """Cheap structural validation; it does not prove a number is active."""
    return classify_phone(value, country=country) != PhoneKind.INVALID
