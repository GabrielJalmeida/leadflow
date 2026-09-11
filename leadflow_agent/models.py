from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class IdentityStatus(str, Enum):
    """Confidence state for whether evidence belongs to the same real business."""

    UNVERIFIED = "unverified"
    MATCHED = "matched"
    PROBABLE_MATCH = "probable_match"
    AMBIGUOUS = "ambiguous"
    MISMATCH = "mismatch"


class WebsiteStatus(str, Enum):
    """Lifecycle state for a lead website.

    UNKNOWN means we have not investigated enough to make a claim.
    PRESENT means an official website was identified.
    NOT_FOUND means a dedicated investigation found no official website.
    UNREACHABLE means an official/likely website was identified but could not be reached.
    """

    UNKNOWN = "unknown"
    PRESENT = "present"
    NOT_FOUND = "not_found"
    UNREACHABLE = "unreachable"


@dataclass(slots=True)
class SearchGoal:
    segment: str
    city: str
    state: str = ""
    country: str = "Brazil"
    limit: int = 10
    require_phone: bool = False
    prefer_no_website: bool = True

    @property
    def location_label(self) -> str:
        parts = [self.city, self.state, self.country]
        return ", ".join(p.strip() for p in parts if p and p.strip())


@dataclass(slots=True)
class QueryPlan:
    queries: list[str]
    rationale: str = ""
    generated_by: str = "basic"


@dataclass(slots=True)
class Evidence:
    source: str
    kind: str
    url: str | None = None
    detail: str | None = None
    target_field: str | None = None
    confidence: float | None = None
    observed_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class RejectedCandidate:
    value: str
    target_field: str
    reason: str
    source: str = ""
    confidence: float = 0.0
    observed_name: str | None = None
    observed_city: str | None = None
    observed_state: str | None = None
    observed_phone: str | None = None
    rejected_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class Lead:
    name: str
    city: str = ""
    state: str = ""
    country: str = "Brazil"
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    website_status: WebsiteStatus = WebsiteStatus.UNKNOWN
    socials: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    rating: float | None = None
    review_count: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    provider_id: str | None = None
    provider_url: str | None = None
    source_provider: str = ""
    discovered_query: str = ""
    discovery_confidence: float = 0.0
    identity_status: IdentityStatus = IdentityStatus.UNVERIFIED
    identity_confidence: float = 0.0
    field_confidence: dict[str, float] = field(default_factory=dict)
    confidence_score: int = 0
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Backwards compatibility: providers from older code already setting a
        # website should automatically be treated as PRESENT.
        if self.website and self.website_status == WebsiteStatus.UNKNOWN:
            self.website_status = WebsiteStatus.PRESENT

        self.discovery_confidence = _clamp_confidence(self.discovery_confidence)
        self.identity_confidence = _clamp_confidence(self.identity_confidence)
        self.field_confidence = {
            str(key): _clamp_confidence(value)
            for key, value in self.field_confidence.items()
        }

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        return data


@dataclass(slots=True)
class InvestigationCandidate:
    name: str = ""
    city: str = ""
    state: str = ""
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    socials: list[str] = field(default_factory=list)
    source_url: str | None = None
    source_title: str = ""
    source: str = ""
    confidence: float = 0.0

    def __post_init__(self) -> None:
        self.confidence = _clamp_confidence(self.confidence)


@dataclass(slots=True)
class WebHit:
    title: str
    url: str
    description: str = ""
    query: str = ""


@dataclass(slots=True)
class ResearchReport:
    goal: SearchGoal
    plan: QueryPlan
    leads: list[Lead]
    queries_executed: list[str]
    local_results_seen: int
    duplicates_removed: int
    started_at: str
    finished_at: str
    errors: list[str] = field(default_factory=list)
    investigated_leads: int = 0
    investigation_searches: int = 0
    search_cache_hits: int = 0
    search_cache_misses: int = 0
    search_cache_writes: int = 0
    memory_hits: int = 0
    memory_fields_restored: int = 0
    memory_rejections_restored: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": asdict(self.goal),
            "plan": asdict(self.plan),
            "leads": [lead.to_dict() for lead in self.leads],
            "queries_executed": self.queries_executed,
            "local_results_seen": self.local_results_seen,
            "duplicates_removed": self.duplicates_removed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "errors": self.errors,
            "investigated_leads": self.investigated_leads,
            "investigation_searches": self.investigation_searches,
            "search_cache_hits": self.search_cache_hits,
            "search_cache_misses": self.search_cache_misses,
            "search_cache_writes": self.search_cache_writes,
            "memory_hits": self.memory_hits,
            "memory_fields_restored": self.memory_fields_restored,
            "memory_rejections_restored": self.memory_rejections_restored,
        }


def lead_from_dict(data: dict[str, Any]) -> Lead:
    """Rebuild a Lead from persisted JSON while tolerating older v0.x payloads."""

    payload = dict(data)
    try:
        payload["website_status"] = WebsiteStatus(
            payload.get("website_status", WebsiteStatus.UNKNOWN.value)
        )
    except (TypeError, ValueError):
        payload["website_status"] = WebsiteStatus.UNKNOWN
    try:
        payload["identity_status"] = IdentityStatus(
            payload.get("identity_status", IdentityStatus.UNVERIFIED.value)
        )
    except (TypeError, ValueError):
        payload["identity_status"] = IdentityStatus.UNVERIFIED

    evidence: list[Evidence] = []
    for item in payload.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        allowed = {field_.name for field_ in fields(Evidence)}
        evidence.append(Evidence(**{key: value for key, value in item.items() if key in allowed}))
    payload["evidence"] = evidence

    rejected: list[RejectedCandidate] = []
    for item in payload.get("rejected_candidates") or []:
        if not isinstance(item, dict):
            continue
        allowed = {field_.name for field_ in fields(RejectedCandidate)}
        try:
            rejected.append(
                RejectedCandidate(**{key: value for key, value in item.items() if key in allowed})
            )
        except TypeError:
            continue
    payload["rejected_candidates"] = rejected

    allowed_lead = {field_.name for field_ in fields(Lead)}
    clean = {key: value for key, value in payload.items() if key in allowed_lead}
    return Lead(**clean)


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))
