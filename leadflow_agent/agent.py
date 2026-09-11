from __future__ import annotations

from .dedupe import lead_key, merge_leads
from .enrichment import enrich_lead_from_web
from .models import Lead, ResearchReport, SearchGoal, utc_now_iso
from .memory import LeadMemory
from .planner import build_plan
from .quality import assess_lead_quality, sanitize_lead_fields
from .providers.base import LeadExtractorProvider, LLMProvider, LocalSearchProvider, WebSearchProvider
from .scoring import score_lead
from .services.investigator import LeadInvestigator
from .services.website_auditor import WebsiteAuditor


class LeadResearchAgent:
    def __init__(
        self,
        *,
        local_search: LocalSearchProvider | None = None,
        web_search: WebSearchProvider | None = None,
        llm: LLMProvider | None = None,
        lead_extractor: LeadExtractorProvider | None = None,
        investigator: LeadInvestigator | None = None,
        lead_memory: LeadMemory | None = None,
        website_auditor: WebsiteAuditor | None = None,
    ):
        if local_search is None and web_search is None:
            raise ValueError("LeadResearchAgent requires a local or web search provider.")
        self.local_search = local_search
        self.web_search = web_search
        self.llm = llm
        self.lead_extractor = lead_extractor
        self.investigator = investigator
        self.lead_memory = lead_memory
        self.website_auditor = website_auditor

    def research(
        self,
        goal: SearchGoal,
        *,
        max_queries: int = 6,
        enrich_web: bool = False,
        enrichment_limit: int | None = None,
        investigate: bool = False,
        investigation_limit: int | None = None,
        investigation_budget: int = 2,
        audit_websites: bool = False,
        audit_limit: int | None = 3,
        audit_timeout: float = 8.0,
        audit_ttl_days: int = 7,
        refresh_audits: bool = False,
    ) -> ResearchReport:
        started = utc_now_iso()
        cache_before = _cache_snapshot(self.web_search)
        plan = build_plan(goal, self.llm, max_queries=max_queries)
        unique: dict[str, Lead] = {}
        queries_executed: list[str] = []
        source_results_seen = 0
        duplicates_removed = 0
        quality_rejected = 0
        invalid_fields_removed = 0
        errors: list[str] = []

        for query in plan.queries:
            if len(unique) >= goal.limit:
                break
            remaining = max(1, goal.limit - len(unique))
            queries_executed.append(query)

            if self.local_search is not None:
                request_count = min(100, max(20, remaining * 3))
                try:
                    found = self.local_search.search_places(query, goal, count=request_count)
                except Exception as exc:
                    errors.append(f"{query}: {exc}")
                    continue
                source_results_seen += len(found)
            else:
                assert self.web_search is not None
                request_count = min(20, max(10, remaining * 2))
                web_query = _build_web_discovery_query(query, goal)
                try:
                    hits = self.web_search.search_web(web_query, country="BR", count=request_count)
                except Exception as exc:
                    errors.append(f"{query}: search failed: {exc}")
                    continue
                source_results_seen += len(hits)

                found: list[Lead] = []
                if self.lead_extractor is not None:
                    try:
                        found = self.lead_extractor.extract_leads(
                            hits,
                            goal,
                            query=query,
                            max_leads=max(remaining * 3, 10),
                        )
                    except Exception as exc:
                        errors.append(f"{query}: AI extraction failed: {exc}")

                # If AI is absent or temporarily rate-limited, keep a useful
                # deterministic fallback for direct business/social results.
                if not found and hasattr(self.web_search, "heuristic_leads"):
                    try:
                        found = self.web_search.heuristic_leads(hits, goal, query=query)  # type: ignore[attr-defined]
                    except Exception as exc:
                        errors.append(f"{query}: heuristic extraction failed: {exc}")

            for lead in found:
                invalid_fields_removed += sanitize_lead_fields(lead)
                quality = assess_lead_quality(lead, segment=goal.segment)
                if not quality.accepted:
                    quality_rejected += 1
                    continue
                if goal.require_phone and not lead.phone:
                    continue
                key = lead_key(lead)
                if key in unique:
                    duplicates_removed += 1
                    merge_leads(unique[key], lead)
                else:
                    unique[key] = lead

        leads = list(unique.values())

        memory_hits = 0
        memory_fields_restored = 0
        memory_rejections_restored = 0
        if self.lead_memory is not None:
            for lead in leads:
                try:
                    memory = self.lead_memory.hydrate(lead)
                except Exception as exc:
                    errors.append(f"{lead.name}: memory hydration failed: {exc}")
                    continue
                if memory.matched:
                    memory_hits += 1
                    memory_fields_restored += memory.fields_restored
                    memory_rejections_restored += memory.rejected_restored
                    # Old cached/memorized data may predate newer validators.
                    invalid_fields_removed += sanitize_lead_fields(lead)

        if enrich_web and self.web_search is not None:
            candidates = leads if enrichment_limit is None else leads[: max(0, enrichment_limit)]
            for lead in candidates:
                if lead.website is None or not lead.socials:
                    try:
                        enrich_lead_from_web(lead, goal, self.web_search)
                    except Exception as exc:
                        from .models import Evidence
                        lead.evidence.append(Evidence(source=self.web_search.name, kind="enrichment_error", detail=str(exc)))

        # Preliminary score determines which candidates are worth spending a
        # bounded investigation budget on. Investigation is opt-in so a normal
        # discovery run never spends unexpected provider credits.
        for lead in leads:
            score_lead(lead, prefer_no_website=goal.prefer_no_website)

        investigated_leads = 0
        investigation_searches = 0
        if investigate:
            if self.investigator is None:
                errors.append("investigation requested but no investigator is configured")
            else:
                ordered = sorted(
                    leads,
                    key=lambda item: (item.score, item.confidence_score, bool(item.phone)),
                    reverse=True,
                )
                cap = len(ordered) if investigation_limit is None else max(0, int(investigation_limit))
                for lead in ordered[:cap]:
                    try:
                        investigation = self.investigator.investigate(
                            lead,
                            goal,
                            max_searches=investigation_budget,
                        )
                        investigated_leads += 1
                        investigation_searches += investigation.searches_used
                        for error in investigation.errors:
                            errors.append(f"{lead.name}: {error}")
                    except Exception as exc:
                        errors.append(f"{lead.name}: investigation failed: {exc}")

        website_audits_run = 0
        website_audits_reused = 0
        website_audit_errors = 0
        if audit_websites:
            if self.website_auditor is None:
                errors.append("website audit requested but no auditor is configured")
            else:
                audit_candidates = [lead for lead in leads if lead.website]
                audit_candidates.sort(
                    key=lambda item: (
                        item.identity_confidence,
                        item.confidence_score,
                        item.score,
                    ),
                    reverse=True,
                )
                cap = len(audit_candidates) if audit_limit is None else max(0, int(audit_limit))
                for lead in audit_candidates[:cap]:
                    try:
                        outcome = self.website_auditor.audit(
                            lead,
                            timeout=audit_timeout,
                            max_age_days=audit_ttl_days,
                            force=refresh_audits,
                        )
                        if outcome.reused:
                            website_audits_reused += 1
                        else:
                            website_audits_run += 1
                        if outcome.audit.error or outcome.audit.blocked:
                            website_audit_errors += 1
                    except Exception as exc:
                        website_audit_errors += 1
                        errors.append(f"{lead.name}: website audit failed: {exc}")

        # Re-score after enrichment/investigation/audit because verified fields
        # and website availability can materially change the opportunity score.
        for lead in leads:
            score_lead(lead, prefer_no_website=goal.prefer_no_website)

        leads.sort(
            key=lambda item: (
                item.score,
                item.review_count if item.review_count is not None else -1,
                bool(item.phone),
            ),
            reverse=True,
        )
        leads = leads[: goal.limit]

        cache_after = _cache_snapshot(self.web_search)
        cache_hits = cache_misses = cache_writes = 0
        if cache_before is not None and cache_after is not None:
            delta = cache_after.delta(cache_before)
            cache_hits = delta.hits
            cache_misses = delta.misses
            cache_writes = delta.writes

        return ResearchReport(
            goal=goal,
            plan=plan,
            leads=leads,
            queries_executed=queries_executed,
            local_results_seen=source_results_seen,
            duplicates_removed=duplicates_removed,
            started_at=started,
            finished_at=utc_now_iso(),
            errors=errors,
            investigated_leads=investigated_leads,
            investigation_searches=investigation_searches,
            search_cache_hits=cache_hits,
            search_cache_misses=cache_misses,
            search_cache_writes=cache_writes,
            memory_hits=memory_hits,
            memory_fields_restored=memory_fields_restored,
            memory_rejections_restored=memory_rejections_restored,
            quality_rejected=quality_rejected,
            invalid_fields_removed=invalid_fields_removed,
            website_audits_run=website_audits_run,
            website_audits_reused=website_audits_reused,
            website_audit_errors=website_audit_errors,
        )


def _cache_snapshot(provider):
    if provider is None:
        return None
    snapshot = getattr(provider, "cache_snapshot", None)
    if snapshot is None:
        return None
    try:
        return snapshot()
    except Exception:
        return None


def _build_web_discovery_query(query: str, goal: SearchGoal) -> str:
    location = " ".join(part for part in (goal.city, goal.state) if part).strip()
    # Contact/social terms bias general web search toward evidence that is useful
    # for prospecting without requiring a dedicated business-listings database.
    return f'"{query}" "{location}" telefone OR WhatsApp OR Instagram'.strip()
