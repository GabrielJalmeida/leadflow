from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agent_factory import build_agent
from .config import Settings
from .contracts import research_contract
from .export import export_report
from .filters import LeadFilterSpec, Presence, Readiness
from .models import OpportunityType, SearchGoal, WebsiteStatus
from .profiles import PROFILES, get_profile
from .runtime import RunBudget, RunController
from .security import normalize_user_text
from .segments import resolve_segment
from .storage import LeadStore


@dataclass(slots=True)
class SearchFilters:
    website: str | None = None
    instagram: str | None = None
    phone: str | None = None
    email: str | None = None
    readiness: str | None = None
    opportunity_types: list[str] = field(default_factory=list)
    min_opportunity_score: int | None = None
    max_technical_score: int | None = None
    max_browser_score: int | None = None
    max_visual_score: int | None = None
    min_visual_confidence: int = 55
    require_any_contact: bool = False


@dataclass(slots=True)
class SearchFeatures:
    investigate: bool = True
    investigation_limit: int = 3
    investigation_budget: int = 2
    audit_websites: bool = True
    audit_limit: int = 3
    audit_timeout: float = 8.0
    browser_audit: bool = False
    browser_audit_limit: int = 3
    browser_timeout: float = 12.0
    visual_audit: bool = False
    visual_audit_limit: int = 3
    capture_replay: bool = False


@dataclass(slots=True)
class SearchBudgets:
    max_search_calls: int = 30
    max_llm_calls: int = 30
    max_website_audits: int = 25
    max_browser_audits: int = 10
    max_visual_audits: int = 10


@dataclass(slots=True)
class SearchRequest:
    segment: str
    city: str
    state: str = ""
    country: str = "Brazil"
    limit: int = 10
    max_queries: int = 20
    profile: str = "website-sales"
    provider: str = "auto"
    no_ai: bool = False
    require_phone: bool = False
    filter_pool_multiplier: int = 5
    contact_strategy: str = "digital-first"
    fulfill_quota: bool = True
    use_cache: bool = True
    refresh_cache: bool = False
    cache_ttl_days: int = 14
    use_memory: bool = True
    exclude_existing_leads: bool = True
    raw_discovery: bool = False
    filters: SearchFilters = field(default_factory=SearchFilters)
    features: SearchFeatures = field(default_factory=SearchFeatures)
    budgets: SearchBudgets = field(default_factory=SearchBudgets)


@dataclass(slots=True)
class SearchExecution:
    contract: dict
    provider: str
    db_run_id: int | None = None
    total_leads: int | None = None
    csv_path: str | None = None
    json_path: str | None = None


def validate_search_request(request: SearchRequest, settings: Settings | None = None) -> SearchRequest:
    request.segment = normalize_user_text(request.segment, field="segmento", max_length=120)
    request.city = normalize_user_text(request.city, field="cidade", max_length=120)
    request.state = normalize_user_text(request.state, field="estado", max_length=40, allow_empty=True)
    request.country = normalize_user_text(request.country, field="país", max_length=80)

    if not 1 <= int(request.limit) <= 100:
        raise ValueError("limit deve ficar entre 1 e 100 no modo normal")
    if not 1 <= int(request.max_queries) <= 20:
        raise ValueError("max_queries deve ficar entre 1 e 20")
    if request.profile not in PROFILES:
        raise ValueError(f"Perfil desconhecido: {request.profile}")
    if request.provider not in {"auto", "tavily", "brave", "outscraper"}:
        raise ValueError(f"Provider desconhecido: {request.provider}")
    if not 1 <= int(request.filter_pool_multiplier) <= 8:
        raise ValueError("filter_pool_multiplier deve ficar entre 1 e 8")
    if request.contact_strategy not in {"digital-first", "multichannel"}:
        raise ValueError("contact_strategy deve ser digital-first ou multichannel")
    if not 1 <= int(request.cache_ttl_days) <= 90:
        raise ValueError("cache_ttl_days deve ficar entre 1 e 90")
    if request.refresh_cache and not request.use_cache:
        raise ValueError("refresh_cache exige use_cache=true")

    features = request.features
    if features.investigation_limit < 0:
        raise ValueError("investigation_limit não pode ser negativo")
    if not 1 <= features.investigation_budget <= 3:
        raise ValueError("investigation_budget deve ficar entre 1 e 3")
    if features.audit_limit < 0 or features.browser_audit_limit < 0 or features.visual_audit_limit < 0:
        raise ValueError("limites de auditoria não podem ser negativos")
    if not 2 <= features.audit_timeout <= 20:
        raise ValueError("audit_timeout deve ficar entre 2 e 20 segundos")
    if not 4 <= features.browser_timeout <= 30:
        raise ValueError("browser_timeout deve ficar entre 4 e 30 segundos")

    budget_ranges = {
        "max_search_calls": (1, 50),
        "max_llm_calls": (1, 100),
        "max_website_audits": (0, 50),
        "max_browser_audits": (0, 25),
        "max_visual_audits": (0, 20),
    }
    for name, (minimum, maximum) in budget_ranges.items():
        value = int(getattr(request.budgets, name))
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} deve ficar entre {minimum} e {maximum}")

    filters = request.filters
    if filters.website is not None and filters.website not in {"any", *(item.value for item in WebsiteStatus)}:
        raise ValueError(f"website filter inválido: {filters.website}")
    for name in ("instagram", "phone", "email"):
        if getattr(filters, name) is not None and getattr(filters, name) not in {item.value for item in Presence}:
            raise ValueError(f"{name} filter inválido")
    if filters.readiness is not None and filters.readiness not in {item.value for item in Readiness}:
        raise ValueError("readiness filter inválido")
    valid_opportunities = {item.value for item in OpportunityType if item != OpportunityType.UNKNOWN}
    if any(item not in valid_opportunities for item in filters.opportunity_types):
        raise ValueError("opportunity_types contém valor inválido")
    for name in (
        "min_opportunity_score",
        "max_technical_score",
        "max_browser_score",
        "max_visual_score",
        "min_visual_confidence",
    ):
        value = getattr(filters, name)
        if value is not None and not 0 <= int(value) <= 100:
            raise ValueError(f"{name} deve ficar entre 0 e 100")

    settings = settings or Settings.load()
    if not request.raw_discovery and features.investigate and (request.no_ai or not settings.gemini_api_key):
        raise ValueError("Investigator requer Gemini configurado")
    if not request.raw_discovery and features.visual_audit and (request.no_ai or not settings.gemini_api_key):
        raise ValueError("Visual IA requer Gemini configurado")
    if not request.raw_discovery and features.browser_audit and importlib.util.find_spec("playwright") is None:
        raise ValueError('Browser/UX requer Playwright; instale o extra "browser"')
    return request


def build_filter_spec(request: SearchRequest) -> LeadFilterSpec:
    filters = request.filters
    spec = get_profile(request.profile).filters()

    if filters.website == "any":
        spec.website_states.clear()
    elif filters.website is not None:
        spec.website_states = {WebsiteStatus(filters.website)}

    if filters.instagram is not None:
        spec.instagram = Presence(filters.instagram)
    if filters.phone is not None:
        spec.phone = Presence(filters.phone)
    if filters.email is not None:
        spec.email = Presence(filters.email)
    if filters.readiness is not None:
        spec.readiness = Readiness(filters.readiness)
    if filters.opportunity_types:
        spec.opportunity_types = {OpportunityType(item) for item in filters.opportunity_types}
    if filters.min_opportunity_score is not None:
        spec.min_opportunity_score = int(filters.min_opportunity_score)
    if filters.max_technical_score is not None:
        spec.max_technical_score = int(filters.max_technical_score)
    if filters.max_browser_score is not None:
        spec.max_browser_score = int(filters.max_browser_score)
    if filters.max_visual_score is not None:
        spec.max_visual_score = int(filters.max_visual_score)
    spec.min_visual_confidence = int(filters.min_visual_confidence) / 100.0
    if filters.require_any_contact:
        spec.require_any_contact = True
    return spec


def execute_search(
    request: SearchRequest,
    *,
    settings: Settings | None = None,
    cancel_check: Callable[[], bool] | None = None,
    persist: bool = True,
    export_results: bool = False,
) -> SearchExecution:
    """Application-layer entry point shared by desktop UI and HTTP API."""

    settings = settings or Settings.load()
    request = validate_search_request(request, settings)

    effective_max_queries = int(request.max_queries)
    effective_pool_multiplier = int(request.filter_pool_multiplier)
    effective_search_budget = int(request.budgets.max_search_calls)
    effective_investigation_limit = int(request.features.investigation_limit)

    if request.raw_discovery:
        # Raw mode is intentionally discovery-only: ignore user-facing quality
        # profile filters and expensive enrichment/audits so the user can inspect
        # the discovered businesses themselves. Basic sanitization + dedupe still
        # protect the result from malformed records and exact duplicates.
        effective_investigation_limit = 0

    if request.fulfill_quota:
        # A requested quantity is a fulfillment target, not merely a hint.
        # Give discovery enough semantic angles to keep searching before a
        # partial result is accepted, while preserving a hard per-run ceiling.
        effective_max_queries = max(
            effective_max_queries,
            min(20, max(12, int(request.limit) * 2)),
        )
        effective_pool_multiplier = max(effective_pool_multiplier, 5)

        local_source_available = (
            request.provider in {"brave", "outscraper"}
            or (
                request.provider == "auto"
                and bool(settings.brave_api_key or settings.outscraper_api_key)
            )
        )
        web_source_available = (
            request.provider in {"tavily", "brave"}
            or (
                request.provider == "outscraper"
                and bool(settings.tavily_api_key or settings.brave_api_key)
            )
            or (
                request.provider == "auto"
                and bool(settings.tavily_api_key or settings.brave_api_key)
            )
        )
        discovery_source_count = max(
            1,
            int(local_source_available) + int(web_source_available),
        )
        if request.features.investigate:
            effective_investigation_limit = max(
                effective_investigation_limit,
                min(15, int(request.limit) + max(2, int(request.limit) // 3)),
            )
        investigation_reserve = (
            effective_investigation_limit * request.features.investigation_budget
            if request.features.investigate
            else 0
        )
        required_search_budget = (
            effective_max_queries * discovery_source_count + investigation_reserve
        )
        effective_search_budget = max(
            effective_search_budget,
            min(50, required_search_budget),
        )

    controller = RunController(
        RunBudget(
            max_search_calls=effective_search_budget,
            max_llm_calls=request.budgets.max_llm_calls,
            max_website_audits=request.budgets.max_website_audits,
            max_browser_audits=request.budgets.max_browser_audits,
            max_visual_audits=request.budgets.max_visual_audits,
        ),
        cancel_check=cancel_check,
    )
    selected_provider, agent = build_agent(
        settings,
        no_ai=request.no_ai,
        provider_name=request.provider,
        use_cache=request.use_cache,
        refresh_cache=request.refresh_cache,
        cache_ttl_days=request.cache_ttl_days,
        use_memory=request.use_memory,
        run_controller=controller,
    )

    preset = resolve_segment(request.segment)
    segment = preset.label if preset is not None else request.segment
    goal = SearchGoal(
        segment=segment,
        city=request.city,
        state=request.state,
        country=request.country,
        limit=request.limit,
        require_phone=request.require_phone,
        prefer_no_website=True,
    )
    spec = None if request.raw_discovery else build_filter_spec(request)
    features = request.features
    run_investigation = features.investigate and not request.raw_discovery
    run_audit_websites = features.audit_websites and not request.raw_discovery
    run_browser_audit = features.browser_audit and not request.raw_discovery
    run_visual_audit = features.visual_audit and not request.raw_discovery

    # Fresh searches should not keep resurfacing businesses already present in
    # the user's local lead library. Lifecycle/history controls remain separate
    # so the user can still inspect, re-queue or restore existing leads.
    excluded_lead_keys: set[str] = set()
    if request.exclude_existing_leads:
        store = LeadStore(settings.db_path)
        try:
            excluded_lead_keys = store.existing_lead_keys()
        finally:
            store.close()

    # Browser screenshots are required by visual analysis. HTTP audit also runs
    # when a deeper website layer is requested so the scores remain independent.
    audit_websites = (features.audit_websites or features.browser_audit or features.visual_audit) and not request.raw_discovery
    browser_audit = (features.browser_audit or features.visual_audit) and not request.raw_discovery

    report = agent.research(
        goal,
        max_queries=effective_max_queries,
        investigate=run_investigation,
        investigation_limit=effective_investigation_limit,
        investigation_budget=features.investigation_budget,
        audit_websites=(audit_websites and not request.raw_discovery),
        audit_limit=features.audit_limit,
        audit_timeout=features.audit_timeout,
        audit_ttl_days=7,
        browser_audit=run_browser_audit or run_visual_audit,
        browser_audit_limit=features.browser_audit_limit,
        browser_timeout=features.browser_timeout,
        browser_audit_ttl_days=7,
        visual_audit=run_visual_audit,
        visual_audit_limit=features.visual_audit_limit,
        visual_audit_ttl_days=14,
        lead_filter=spec,
        filter_pool_multiplier=effective_pool_multiplier,
        digital_contact_only=request.contact_strategy == "digital-first",
        fulfill_quota=request.fulfill_quota,
        capture_replay=features.capture_replay,
        excluded_lead_keys=excluded_lead_keys,
    )

    csv_path: Path | None = None
    json_path: Path | None = None
    if export_results:
        csv_path, json_path = export_report(report)

    db_run_id: int | None = None
    total_leads: int | None = None
    if persist:
        store = LeadStore(settings.db_path)
        try:
            db_run_id = store.save_report(report)
            total_leads = store.count_leads()
        finally:
            store.close()

    return SearchExecution(
        contract=research_contract(report),
        provider=selected_provider,
        db_run_id=db_run_id,
        total_leads=total_leads,
        csv_path=str(csv_path.resolve()) if csv_path else None,
        json_path=str(json_path.resolve()) if json_path else None,
    )
