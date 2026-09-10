from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    observed_at: str = field(default_factory=utc_now_iso)


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
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_raw:
            data.pop("raw", None)
        return data


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
        }
