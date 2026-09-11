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


class OpportunityType(str, Enum):
    """Commercial service opportunity inferred from verified evidence."""

    UNKNOWN = "unknown"
    NEW_SITE = "new_site"
    REBUILD = "rebuild"
    REDESIGN = "redesign"
    OPTIMIZATION = "optimization"
    REVIEW_NEEDED = "review_needed"
    LOW_OPPORTUNITY = "low_opportunity"


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
class WebsiteAudit:
    requested_url: str
    final_url: str
    reachable: bool
    blocked: bool = False
    status_code: int | None = None
    response_time_ms: int | None = None
    redirect_count: int = 0
    content_type: str = ""
    uses_https: bool = False
    title: str | None = None
    has_meta_description: bool = False
    has_viewport: bool = False
    form_count: int = 0
    has_whatsapp: bool = False
    has_tel_link: bool = False
    has_email_link: bool = False
    technical_score: int = 0
    findings: list[str] = field(default_factory=list)
    error: str | None = None
    audited_at: str = field(default_factory=utc_now_iso)



@dataclass(slots=True)
class BrowserAudit:
    requested_url: str
    final_url: str
    loaded: bool
    status_code: int | None = None
    mobile_overflow: bool = False
    visible_contact_cta_count: int = 0
    nav_link_count: int = 0
    console_error_count: int = 0
    page_error_count: int = 0
    ux_score: int = 0
    desktop_screenshot: str | None = None
    mobile_screenshot: str | None = None
    findings: list[str] = field(default_factory=list)
    error: str | None = None
    audited_at: str = field(default_factory=utc_now_iso)




@dataclass(slots=True)
class VisualAudit:
    overall_score: int
    desktop_score: int
    mobile_score: int
    modernity_score: int
    hierarchy_score: int
    brand_coherence_score: int
    readability_score: int
    conversion_clarity_score: int
    confidence: float = 0.0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    summary: str = ""
    model: str = ""
    analyzed_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in (
            "overall_score", "desktop_score", "mobile_score", "modernity_score",
            "hierarchy_score", "brand_coherence_score", "readability_score",
            "conversion_clarity_score",
        ):
            setattr(self, name, max(0, min(int(getattr(self, name)), 100)))
        self.confidence = _clamp_confidence(self.confidence)


@dataclass(slots=True)
class OpportunityAssessment:
    type: OpportunityType = OpportunityType.UNKNOWN
    score: int = 0
    actionable: bool = False
    service_fit: str = "unknown"
    service_need_score: int = 0
    contactability_score: int = 0
    activity_score: int = 0
    website_health_score: int | None = None
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)


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
    website_audit: WebsiteAudit | None = None
    browser_audit: BrowserAudit | None = None
    visual_audit: VisualAudit | None = None
    opportunity: OpportunityAssessment | None = None
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
    quality_rejected: int = 0
    invalid_fields_removed: int = 0
    website_audits_run: int = 0
    website_audits_reused: int = 0
    website_audit_errors: int = 0
    browser_audits_run: int = 0
    browser_audits_reused: int = 0
    browser_audit_errors: int = 0
    visual_audits_run: int = 0
    visual_audits_reused: int = 0
    visual_audit_errors: int = 0
    filter_candidates_seen: int = 0
    filter_rejected: int = 0

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
            "quality_rejected": self.quality_rejected,
            "invalid_fields_removed": self.invalid_fields_removed,
            "website_audits_run": self.website_audits_run,
            "website_audits_reused": self.website_audits_reused,
            "website_audit_errors": self.website_audit_errors,
            "browser_audits_run": self.browser_audits_run,
            "browser_audits_reused": self.browser_audits_reused,
            "browser_audit_errors": self.browser_audit_errors,
            "visual_audits_run": self.visual_audits_run,
            "visual_audits_reused": self.visual_audits_reused,
            "visual_audit_errors": self.visual_audit_errors,
            "filter_candidates_seen": self.filter_candidates_seen,
            "filter_rejected": self.filter_rejected,
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

    opportunity = payload.get("opportunity")
    if isinstance(opportunity, dict):
        allowed = {field_.name for field_ in fields(OpportunityAssessment)}
        clean_opportunity = {key: value for key, value in opportunity.items() if key in allowed}
        try:
            clean_opportunity["type"] = OpportunityType(
                clean_opportunity.get("type", OpportunityType.UNKNOWN.value)
            )
        except (TypeError, ValueError):
            clean_opportunity["type"] = OpportunityType.UNKNOWN
        try:
            payload["opportunity"] = OpportunityAssessment(**clean_opportunity)
        except TypeError:
            payload["opportunity"] = None
    elif not isinstance(opportunity, OpportunityAssessment):
        payload["opportunity"] = None

    audit = payload.get("website_audit")
    if isinstance(audit, dict):
        allowed = {field_.name for field_ in fields(WebsiteAudit)}
        try:
            payload["website_audit"] = WebsiteAudit(
                **{key: value for key, value in audit.items() if key in allowed}
            )
        except TypeError:
            payload["website_audit"] = None
    elif not isinstance(audit, WebsiteAudit):
        payload["website_audit"] = None

    browser_audit = payload.get("browser_audit")
    if isinstance(browser_audit, dict):
        allowed = {field_.name for field_ in fields(BrowserAudit)}
        try:
            payload["browser_audit"] = BrowserAudit(
                **{key: value for key, value in browser_audit.items() if key in allowed}
            )
        except TypeError:
            payload["browser_audit"] = None
    elif not isinstance(browser_audit, BrowserAudit):
        payload["browser_audit"] = None

    visual_audit = payload.get("visual_audit")
    if isinstance(visual_audit, dict):
        allowed = {field_.name for field_ in fields(VisualAudit)}
        try:
            payload["visual_audit"] = VisualAudit(
                **{key: value for key, value in visual_audit.items() if key in allowed}
            )
        except (TypeError, ValueError):
            payload["visual_audit"] = None
    elif not isinstance(visual_audit, VisualAudit):
        payload["visual_audit"] = None

    allowed_lead = {field_.name for field_ in fields(Lead)}
    clean = {key: value for key, value in payload.items() if key in allowed_lead}
    return Lead(**clean)


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))
