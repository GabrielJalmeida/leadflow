from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings
from .contact import build_contact_message, build_whatsapp_url, resolve_contact_route
from .contracts import FRONTEND_CONTRACT_VERSION
from .errors import classify_error
from .security import UnsafeInput
from .profiles import PROFILES
from .providers.catalog import PROVIDER_CATALOG
from .search_service import (
    SearchBudgets,
    SearchExecution,
    SearchFeatures,
    SearchFilters,
    SearchRequest,
    execute_search,
)
from .segments import grouped_segments
from .storage import LeadStore

API_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SearchFiltersModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    website: Literal["any", "unknown", "present", "not_found", "unreachable"] | None = None
    instagram: Literal["any", "present", "missing"] | None = None
    phone: Literal["any", "present", "missing"] | None = None
    email: Literal["any", "present", "missing"] | None = None
    readiness: Literal["any", "ready", "verify"] | None = None
    opportunity_types: list[
        Literal["new_site", "rebuild", "redesign", "optimization", "review_needed", "low_opportunity"]
    ] = Field(default_factory=list)
    min_opportunity_score: int | None = Field(default=None, ge=0, le=100)
    max_technical_score: int | None = Field(default=None, ge=0, le=100)
    max_browser_score: int | None = Field(default=None, ge=0, le=100)
    max_visual_score: int | None = Field(default=None, ge=0, le=100)
    min_visual_confidence: int = Field(default=55, ge=0, le=100)
    require_any_contact: bool = False


class SearchFeaturesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigate: bool = True
    investigation_limit: int = Field(default=3, ge=0, le=100)
    investigation_budget: int = Field(default=2, ge=1, le=3)
    audit_websites: bool = True
    audit_limit: int = Field(default=3, ge=0, le=100)
    audit_timeout: float = Field(default=8.0, ge=2, le=20)
    browser_audit: bool = False
    browser_audit_limit: int = Field(default=3, ge=0, le=25)
    browser_timeout: float = Field(default=12.0, ge=4, le=30)
    visual_audit: bool = False
    visual_audit_limit: int = Field(default=3, ge=0, le=20)


class SearchBudgetsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_search_calls: int = Field(default=30, ge=1, le=50)
    max_llm_calls: int = Field(default=30, ge=1, le=100)
    max_website_audits: int = Field(default=25, ge=0, le=50)
    max_browser_audits: int = Field(default=10, ge=0, le=25)
    max_visual_audits: int = Field(default=10, ge=0, le=20)


class ContactPrepareModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead: dict[str, Any]
    message: str | None = Field(default=None, max_length=4000)

class LifecycleUpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["new", "queued", "contacted", "accepted", "ignored", "hidden", "awaiting_response", "responded", "proposal_sent", "negotiating", "won", "lost"]
    note: str = Field(default="", max_length=2000)


class QueueCreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str | None = Field(default=None, max_length=4000)



class FollowUpCreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    follow_up_at: str = Field(min_length=10, max_length=40)
    note: str = Field(default="", max_length=2000)


class InteractionCreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(default="note", min_length=1, max_length=80)
    channel: str = Field(default="manual", min_length=1, max_length=80)
    outcome: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=4000)
    status: Literal["new", "queued", "contacted", "accepted", "ignored", "hidden", "awaiting_response", "responded", "proposal_sent", "negotiating", "won", "lost"] | None = None

class SettingsUpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_message_template: str = Field(min_length=1, max_length=8000)
    site_text_prompt_template: str = Field(min_length=1, max_length=16000)
    visual_prompt_template: str = Field(min_length=1, max_length=16000)
    prototype_prompt_template: str = Field(min_length=1, max_length=16000)
    text_ai: Literal["chatgpt", "gemini", "claude"] = "chatgpt"
    image_ai: Literal["chatgpt", "gemini", "midjourney"] = "chatgpt"
    prototype_ai: Literal["chatgpt", "gemini", "v0", "lovable", "claude"] = "v0"


class SearchRunCreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    segment: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(default="", max_length=40)
    country: str = Field(default="Brazil", min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=100)
    max_queries: int = Field(default=20, ge=1, le=20)
    profile: str = "website-sales"
    provider: Literal["auto", "tavily", "brave", "outscraper"] = "auto"
    no_ai: bool = False
    require_phone: bool = False
    filter_pool_multiplier: int = Field(default=5, ge=1, le=8)
    contact_strategy: Literal["digital-first", "multichannel"] = "digital-first"
    fulfill_quota: bool = True
    use_cache: bool = True
    refresh_cache: bool = False
    cache_ttl_days: int = Field(default=14, ge=1, le=90)
    use_memory: bool = True
    exclude_existing_leads: bool = True
    raw_discovery: bool = False
    filters: SearchFiltersModel = Field(default_factory=SearchFiltersModel)
    features: SearchFeaturesModel = Field(default_factory=SearchFeaturesModel)
    budgets: SearchBudgetsModel = Field(default_factory=SearchBudgetsModel)

    def to_domain(self) -> SearchRequest:
        return SearchRequest(
            segment=self.segment,
            city=self.city,
            state=self.state,
            country=self.country,
            limit=self.limit,
            max_queries=self.max_queries,
            profile=self.profile,
            provider=self.provider,
            no_ai=self.no_ai,
            require_phone=self.require_phone,
            filter_pool_multiplier=self.filter_pool_multiplier,
            contact_strategy=self.contact_strategy,
            fulfill_quota=self.fulfill_quota,
            use_cache=self.use_cache,
            refresh_cache=self.refresh_cache,
            cache_ttl_days=self.cache_ttl_days,
            use_memory=self.use_memory,
            exclude_existing_leads=self.exclude_existing_leads,
            raw_discovery=self.raw_discovery,
            filters=SearchFilters(**self.filters.model_dump()),
            features=SearchFeatures(**self.features.model_dump()),
            budgets=SearchBudgets(**self.budgets.model_dump()),
        )


@dataclass(slots=True)
class _RunRecord:
    id: str
    request: SearchRequest
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    provider: str | None = None
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    db_run_id: int | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    worker: threading.Thread | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "provider": self.provider,
            "db_run_id": self.db_run_id,
            "error": self.error,
        }


Runner = Callable[[SearchRequest, Callable[[], bool]], SearchExecution]


class SearchRunManager:
    """Small in-process job manager for the local application API.

    It deliberately keeps only recent runtime state in memory. Durable research
    data remains in SQLite through the existing LeadStore path.
    """

    def __init__(self, *, runner: Runner | None = None, max_history: int = 100):
        self._runner = runner or self._default_runner
        self._max_history = max(10, int(max_history))
        self._runs: dict[str, _RunRecord] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _default_runner(request: SearchRequest, cancel_check: Callable[[], bool]) -> SearchExecution:
        return execute_search(
            request,
            cancel_check=cancel_check,
            persist=True,
            export_results=False,
        )

    def create(self, request: SearchRequest) -> dict[str, Any]:
        record = _RunRecord(id=uuid.uuid4().hex, request=request)
        worker = threading.Thread(target=self._work, args=(record.id,), daemon=True, name=f"leadflow-{record.id[:8]}")
        record.worker = worker
        with self._lock:
            self._runs[record.id] = record
            self._trim_locked()
        worker.start()
        return record.snapshot()

    def _work(self, run_id: str) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            if record.cancel_event.is_set():
                record.status = "cancelled"
                record.finished_at = _utc_now()
                return
            record.status = "running"
            record.started_at = _utc_now()

        try:
            execution = self._runner(record.request, record.cancel_event.is_set)
        except Exception as exc:
            public = classify_error(exc, secrets=Settings.load().secret_values())
            with self._lock:
                record = self._runs.get(run_id)
                if record is None:
                    return
                record.status = "cancelled" if public.code.value == "cancelled" else "failed"
                record.error = {
                    "code": public.code.value,
                    "message": public.message,
                    "retryable": public.retryable,
                }
                record.finished_at = _utc_now()
            return

        run_contract = execution.contract.get("run") or {}
        final_status = str(run_contract.get("status") or "completed")
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            record.status = final_status
            record.provider = execution.provider
            record.result = execution.contract
            record.db_run_id = execution.db_run_id
            record.finished_at = _utc_now()

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._runs.get(run_id)
            return None if record is None else record.snapshot()

    def result(self, run_id: str) -> tuple[dict[str, Any] | None, str | None]:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None, None
            return record.result, record.status

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            if record.status in {"completed", "partial_budget", "partial_results", "cancelled", "failed"}:
                return record.snapshot()
            record.cancel_event.set()
            if record.status == "queued":
                record.status = "cancelled"
                record.finished_at = _utc_now()
            else:
                record.status = "cancelling"
            return record.snapshot()

    def _trim_locked(self) -> None:
        if len(self._runs) <= self._max_history:
            return
        finished = [
            item for item in self._runs.values()
            if item.status in {"completed", "partial_budget", "partial_results", "cancelled", "failed"}
        ]
        finished.sort(key=lambda item: item.finished_at or item.created_at)
        while len(self._runs) > self._max_history and finished:
            victim = finished.pop(0)
            self._runs.pop(victim.id, None)


class LocalOriginGuardMiddleware(BaseHTTPMiddleware):
    """Reject browser-originated mutation requests from non-local origins."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and not _is_local_origin(origin):
                return Response(status_code=status.HTTP_403_FORBIDDEN, content="origin not allowed")
        return await call_next(request)


def _is_local_origin(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


DEFAULT_APP_SETTINGS: dict[str, object] = {
    "contact_message_template": "Olá! Tudo bem? Vi o trabalho da {{name}} e achei muito interessante. Trabalho com desenvolvimento de sites e tive algumas ideias de como melhorar a presença digital de vocês. Posso te mostrar uma ideia sem compromisso?",
    "site_text_prompt_template": "Crie um conceito completo de website comercial para {{name}}, segmento {{segment}}, cidade {{city}}/{{state}}. Use apenas os fatos fornecidos. Defina posicionamento, sitemap, hero, proposta de valor, CTAs, seções, copy sugerida, direção visual e estratégia de conversão. Não invente fatos; marque hipóteses.\n\nDADOS DO LEAD:\n{{lead_context}}",
    "visual_prompt_template": "GERE IMAGENS CONCEPT PARA APRESENTAÇÃO COMERCIAL. Crie uma direção visual premium para {{name}}, segmento {{segment}}. Gere propostas de hero, mockup de homepage e cenas para apresentação. Use os dados abaixo apenas como contexto e não invente fatos da empresa.\n\nDADOS DO LEAD:\n{{lead_context}}",
    "prototype_prompt_template": "CONSTRUA UM PROTÓTIPO FUNCIONAL DE WEBSITE responsivo para {{name}}, segmento {{segment}}. Gere uma interface real e navegável, com homepage, hero, serviços, prova social, galeria e contato. Use placeholders quando faltar informação e não invente fatos. O resultado deve ser uma base de demonstração para proposta comercial.\n\nDADOS DO LEAD:\n{{lead_context}}",
    "text_ai": "chatgpt",
    "image_ai": "chatgpt",
    "prototype_ai": "v0",
}

def create_app(*, manager: SearchRunManager | None = None) -> FastAPI:
    manager = manager or SearchRunManager()
    app = FastAPI(
        title="LeadFlow Local API",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.run_manager = manager
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.add_middleware(LocalOriginGuardMiddleware)

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        settings = Settings.load()
        return {
            "status": "ok",
            "api_version": API_VERSION,
            "frontend_contract_version": FRONTEND_CONTRACT_VERSION,
            "configured": {
                "gemini": bool(settings.gemini_api_key),
                "tavily": bool(settings.tavily_api_key),
                "brave": bool(settings.brave_api_key),
                "outscraper": bool(settings.outscraper_api_key),
            },
        }

    @app.get("/api/v1/catalog/segments")
    def segments() -> dict[str, Any]:
        groups = []
        for category, items in grouped_segments().items():
            groups.append({
                "category": category,
                "items": [
                    {"slug": item.slug, "label": item.label, "aliases": list(item.aliases)}
                    for item in items
                ],
            })
        return {"groups": groups, "free_text_allowed": True}

    @app.get("/api/v1/catalog/profiles")
    def profiles() -> dict[str, Any]:
        return {
            "items": [
                {"slug": item.slug, "label": item.label, "description": item.description}
                for item in PROFILES.values()
            ]
        }

    @app.get("/api/v1/catalog/providers")
    def providers() -> dict[str, Any]:
        settings = Settings.load()
        configured = {
            "tavily": bool(settings.tavily_api_key),
            "brave": bool(settings.brave_api_key),
            "outscraper": bool(settings.outscraper_api_key),
            "gemini": bool(settings.gemini_api_key),
        }
        return {
            "items": [
                {
                    "slug": item.slug,
                    "label": item.label,
                    "roles": list(item.roles),
                    "capabilities": list(item.capabilities),
                    "byok": item.byok,
                    "configured": configured.get(item.slug, False),
                }
                for item in PROVIDER_CATALOG.values()
            ]
        }


    @app.post("/api/v1/contact/prepare")
    def prepare_contact(payload: ContactPrepareModel) -> dict[str, Any]:
        route = resolve_contact_route(payload.lead)
        if payload.message:
            message = payload.message.strip()
        else:
            store = LeadStore(Settings.load().db_path)
            try:
                template = str(store.get_app_settings(DEFAULT_APP_SETTINGS).get("contact_message_template") or "")
            finally:
                store.close()
            opportunity = payload.lead.get("opportunity") or {}
            message = template.replace("{{name}}", str(payload.lead.get("name") or "empresa"))
            message = message.replace("{{segment}}", str((payload.lead.get("segment") or payload.lead.get("location", {}).get("city") or "negócio")))
            message = message.replace("{{city}}", str(payload.lead.get("location", {}).get("city") or ""))
            message = message.replace("{{state}}", str(payload.lead.get("location", {}).get("state") or ""))
            message = message.replace("{{opportunity_type}}", str(opportunity.get("type") or ""))
            message = message.strip() or build_contact_message(payload.lead)
        whatsapp_url = None
        if route.whatsapp_number:
            whatsapp_url = build_whatsapp_url(route.whatsapp_number, message)
        return {
            "channel": route.channel,
            "label": route.label,
            "message": message,
            "whatsapp_number": route.whatsapp_number,
            "whatsapp_url": whatsapp_url,
            "instagram_url": route.instagram_url,
            "whatsapp_source": route.whatsapp_source,
        }

    @app.post("/api/v1/runs", status_code=status.HTTP_202_ACCEPTED)
    def create_run(payload: SearchRunCreateModel, request: Request) -> dict[str, Any]:
        try:
            domain = payload.to_domain()
            # Perform cheap deterministic validation before starting a worker.
            # Provider/network validation remains inside the worker.
            from .search_service import validate_search_request

            validate_search_request(domain, Settings.load())
        except (ValueError, UnsafeInput) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return request.app.state.run_manager.create(domain)

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str, request: Request) -> dict[str, Any]:
        item = request.app.state.run_manager.get(run_id)
        if item is None:
            raise HTTPException(status_code=404, detail="run not found")
        return item

    @app.get("/api/v1/runs/{run_id}/result")
    def get_result(run_id: str, request: Request, response: Response) -> dict[str, Any]:
        result, run_status = request.app.state.run_manager.result(run_id)
        if run_status is None:
            raise HTTPException(status_code=404, detail="run not found")
        if result is None:
            if run_status == "failed":
                item = request.app.state.run_manager.get(run_id) or {}
                raise HTTPException(status_code=409, detail=item.get("error") or "run failed")
            response.status_code = status.HTTP_202_ACCEPTED
            return {"id": run_id, "status": run_status, "result": None}
        return {"id": run_id, "status": run_status, "result": result}

    @app.post("/api/v1/runs/{run_id}/cancel")
    def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
        item = request.app.state.run_manager.cancel(run_id)
        if item is None:
            raise HTTPException(status_code=404, detail="run not found")
        return item

    @app.get("/api/v1/leads")
    def list_leads(status_filter: str = "all") -> dict[str, Any]:
        allowed = {"all", "new", "queued", "contacted", "accepted", "ignored", "hidden", "awaiting_response", "responded", "proposal_sent", "negotiating", "won", "lost"}
        if status_filter not in allowed:
            raise HTTPException(status_code=422, detail="status inválido")
        store = LeadStore(Settings.load().db_path)
        try:
            return {"leads": store.list_leads(status_filter), "count": len(store.list_leads(status_filter))}
        finally:
            store.close()

    @app.post("/api/v1/leads/{lead_key}/lifecycle")
    def update_lead_lifecycle(lead_key: str, payload: LifecycleUpdateModel) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            if not store.update_lifecycle(lead_key, payload.status, payload.note):
                raise HTTPException(status_code=404, detail="lead not found")
            leads = store.list_leads("all")
            lead = next((item for item in leads if item.get("lead_key") == lead_key), None)
            return {"lead": lead}
        finally:
            store.close()

    @app.post("/api/v1/leads/{lead_key}/queue")
    def enqueue_lead(lead_key: str, payload: QueueCreateModel) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            item = store.enqueue_contact(lead_key, payload.message)
            if item is None:
                raise HTTPException(status_code=404, detail="lead not found")
            return item
        finally:
            store.close()

    @app.get("/api/v1/queue")
    def get_queue() -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            items = store.list_queue()
            return {"items": items, "count": len(items)}
        finally:
            store.close()


    @app.get("/api/v1/leads/{lead_key}/interactions")
    def get_interactions(lead_key: str, limit: int = 50) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            if store.get_lead(lead_key) is None:
                raise HTTPException(status_code=404, detail="lead not found")
            return {"items": store.list_interactions(lead_key, limit)}
        finally:
            store.close()

    @app.post("/api/v1/leads/{lead_key}/interactions")
    def add_interaction(lead_key: str, payload: InteractionCreateModel) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            item = store.add_interaction(lead_key, kind=payload.kind, channel=payload.channel, outcome=payload.outcome, note=payload.note, status=payload.status)
            if item is None:
                raise HTTPException(status_code=404, detail="lead not found")
            return item
        finally:
            store.close()

    @app.get("/api/v1/follow-ups")
    def get_follow_ups(due_only: bool = False) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            items = store.list_follow_ups(due_only)
            return {"items": items, "count": len(items)}
        finally:
            store.close()

    @app.post("/api/v1/leads/{lead_key}/follow-up")
    def schedule_follow_up(lead_key: str, payload: FollowUpCreateModel) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            lead = store.schedule_follow_up(lead_key, payload.follow_up_at, payload.note)
            if lead is None:
                raise HTTPException(status_code=404, detail="lead not found")
            return {"lead": lead}
        finally:
            store.close()

    @app.delete("/api/v1/leads/{lead_key}/follow-up")
    def clear_follow_up(lead_key: str) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            if not store.clear_follow_up(lead_key):
                raise HTTPException(status_code=404, detail="lead not found")
            lead = store.get_lead(lead_key)
            return {"lead": lead}
        finally:
            store.close()

    @app.get("/api/v1/settings")
    def get_settings() -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            return {"settings": store.get_app_settings(DEFAULT_APP_SETTINGS)}
        finally:
            store.close()

    @app.put("/api/v1/settings")
    def update_settings(payload: SettingsUpdateModel) -> dict[str, Any]:
        store = LeadStore(Settings.load().db_path)
        try:
            values = payload.model_dump()
            store.set_app_settings(values)
            return {"settings": store.get_app_settings(DEFAULT_APP_SETTINGS)}
        finally:
            store.close()

    return app
