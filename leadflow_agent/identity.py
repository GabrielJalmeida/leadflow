from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .dedupe import normalize_phone, normalize_text
from .models import IdentityStatus, Lead, RejectedCandidate


@dataclass(slots=True)
class IdentityCandidate:
    """Observed identity attributes for a possible match.

    A candidate may come from another lead, a website, a social profile or a
    future enrichment provider. Missing fields are intentionally allowed.
    """

    name: str = ""
    city: str = ""
    state: str = ""
    phone: str | None = None
    website: str | None = None
    address: str | None = None
    source: str = ""


@dataclass(slots=True)
class IdentityAssessment:
    status: IdentityStatus
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def safe_to_merge(self) -> bool:
        return self.status in {IdentityStatus.MATCHED, IdentityStatus.PROBABLE_MATCH} and self.confidence >= 0.80


def normalize_domain(url: str | None) -> str:
    if not url:
        return ""
    raw = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    try:
        host = urlparse(raw).netloc.casefold().split(":", 1)[0]
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip(".")


def candidate_from_lead(lead: Lead) -> IdentityCandidate:
    return IdentityCandidate(
        name=lead.name,
        city=lead.city,
        state=lead.state,
        phone=lead.phone,
        website=lead.website,
        address=lead.address,
        source=lead.source_provider,
    )


def assess_identity(reference: Lead, candidate: IdentityCandidate) -> IdentityAssessment:
    """Conservatively decide whether candidate evidence belongs to reference.

    Rule: a false association is worse than missing data. Name/category-like
    similarity alone is never enough to produce MATCHED.
    """

    reasons: list[str] = []
    ref_phone = normalize_phone(reference.phone)
    cand_phone = normalize_phone(candidate.phone)
    ref_domain = normalize_domain(reference.website)
    cand_domain = normalize_domain(candidate.website)

    if ref_phone and cand_phone and len(ref_phone) >= 8 and ref_phone == cand_phone:
        return IdentityAssessment(IdentityStatus.MATCHED, 0.99, ["same normalized phone"])

    if ref_domain and cand_domain and ref_domain == cand_domain:
        return IdentityAssessment(IdentityStatus.MATCHED, 0.98, ["same website domain"])

    ref_name = normalize_text(reference.name)
    cand_name = normalize_text(candidate.name)
    name_match = bool(ref_name and cand_name and ref_name == cand_name)

    ref_city = normalize_text(reference.city)
    cand_city = normalize_text(candidate.city)
    ref_state = normalize_text(reference.state)
    cand_state = normalize_text(candidate.state)

    if name_match:
        reasons.append("same normalized name")

        if ref_state and cand_state and ref_state != cand_state:
            return IdentityAssessment(
                IdentityStatus.MISMATCH,
                0.99,
                [*reasons, f"state mismatch: {reference.state} != {candidate.state}"],
            )

        if ref_city and cand_city and ref_city != cand_city:
            return IdentityAssessment(
                IdentityStatus.MISMATCH,
                0.97,
                [*reasons, f"city mismatch: {reference.city} != {candidate.city}"],
            )

        same_city = bool(ref_city and cand_city and ref_city == cand_city)
        same_state = bool(ref_state and cand_state and ref_state == cand_state)
        if same_city and (same_state or not ref_state or not cand_state):
            return IdentityAssessment(
                IdentityStatus.PROBABLE_MATCH,
                0.86 if same_state else 0.82,
                [*reasons, "same locality"],
            )

        return IdentityAssessment(
            IdentityStatus.AMBIGUOUS,
            0.52,
            [*reasons, "insufficient locality/contact evidence"],
        )

    # A domain/phone mismatch is not by itself evidence that two differently
    # named businesses conflict; they may simply be unrelated search results.
    return IdentityAssessment(
        IdentityStatus.AMBIGUOUS,
        0.25,
        ["insufficient identity overlap"],
    )


def assess_lead_pair(reference: Lead, candidate: Lead) -> IdentityAssessment:
    return assess_identity(reference, candidate_from_lead(candidate))


def record_rejected_candidate(
    lead: Lead,
    *,
    value: str,
    target_field: str,
    reason: str,
    source: str = "",
    confidence: float = 0.0,
    observed_name: str | None = None,
    observed_city: str | None = None,
    observed_state: str | None = None,
    observed_phone: str | None = None,
) -> None:
    if is_rejected_candidate(lead, value=value, target_field=target_field):
        return
    lead.rejected_candidates.append(
        RejectedCandidate(
            value=value,
            target_field=target_field,
            reason=reason,
            source=source,
            confidence=max(0.0, min(float(confidence), 1.0)),
            observed_name=observed_name,
            observed_city=observed_city,
            observed_state=observed_state,
            observed_phone=observed_phone,
        )
    )


def is_rejected_candidate(lead: Lead, *, value: str, target_field: str) -> bool:
    normalized_value = normalize_domain(value) if target_field == "website" else normalize_text(value)
    for item in lead.rejected_candidates:
        if item.target_field != target_field:
            continue
        other = normalize_domain(item.value) if target_field == "website" else normalize_text(item.value)
        if normalized_value and normalized_value == other:
            return True
    return False
