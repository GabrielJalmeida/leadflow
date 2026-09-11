from __future__ import annotations

import re


def phone_digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def is_plausible_phone(value: str | None, *, country: str = "Brazil") -> bool:
    """Cheap structural validation; it does not prove a number is active.

    Brazil rules intentionally reject a common scraped-data failure: a mobile
    number whose ninth digit was truncated. For other countries we only apply
    the E.164 length envelope until country-specific validators are added.
    """

    digits = phone_digits(value)
    if not digits:
        return False

    if country.casefold() in {"brazil", "br", "brasil"}:
        if digits.startswith("55") and len(digits) in {12, 13}:
            digits = digits[2:]

        if len(digits) == 11:
            ddd = digits[:2]
            subscriber = digits[2:]
            return ddd[0] not in {"0"} and subscriber.startswith("9")

        if len(digits) == 10:
            ddd = digits[:2]
            subscriber = digits[2:]
            # Brazilian fixed lines have 8-digit subscriber numbers and do not
            # start with 9. Restrict to the common fixed-line initial range.
            return ddd[0] not in {"0"} and subscriber[:1] in {"2", "3", "4", "5"}

        return False

    return 7 <= len(digits) <= 15
