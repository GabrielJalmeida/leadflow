from __future__ import annotations

from .dedupe import find_duplicate_key, lead_key, merge_leads
from .enrichment import enrich_lead_from_web
from .filters import LeadFilterSpec, assess_filter
from .models import Lead, ResearchReport, SearchGoal, utc_now_iso
from .memory import LeadMemory
from .planner import build_plan
from .quality import assess_lead_quality, sanitize_lead_fields
from .providers.base import LeadExtractorProvider, LLMProvider, LocalSearchProvider, WebSearchProvider
from .scoring import score_lead
from .services.investigator import LeadInvestigator
from .services.website_auditor import WebsiteAuditor
from .services.browser_auditor import BrowserAuditor
from .services.visual_auditor import VisualAuditor
from .runtime import BudgetExceeded, BudgetKind, RunCancelled, RunController, RunStatus


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
        browser_auditor: BrowserAuditor | None = None,
        visual_auditor: VisualAuditor | None = None,
        run_controller: RunController | None = None,
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
        self.browser_auditor = browser_auditor
        self.visual_auditor = visual_auditor
        self.run_controller = run_controller or RunController()

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
        browser_audit: bool = False,
        browser_audit_limit: int | None = 3,
        browser_timeout: float = 12.0,
        browser_audit_ttl_days: int = 7,
        refresh_browser_audits: bool = False,
        browser_artifacts_dir: str = "output/browser-audits",
        visual_audit: bool = False,
        visual_audit_limit: int | None = 3,
        visual_audit_ttl_days: int = 14,
        refresh_visual_audits: bool = False,
        lead_filter: LeadFilterSpec | None = None,
        filter_pool_multiplier: int = 2,
        digital_contact_only: bool = False,
    ) -> ResearchReport:
        started = utc_now_iso()
        cache_before = _cache_snapshot(self.web_search)
        plan = build_plan(goal, self.llm, max_queries=max_queries)
        unique: dict[str, Lead] = {}
        target_pool = goal.limit
        if lead_filter is not None and lead_filter.active:
            target_pool = min(1000, max(goal.limit, goal.limit * max(1, int(filter_pool_multiplier))))
        queries_executed: list[str] = []
        source_results_seen = 0
        duplicates_removed = 0
        quality_rejected = 0
        invalid_fields_removed = 0
        errors: list[str] = []
        controller = self.run_controller

        for query in plan.queries:
            try:
                controller.check_cancelled()
            except RunCancelled as exc:
                errors.append(str(exc))
                break
            if len(unique) >= target_pool:
                break
            remaining = max(1, target_pool - len(unique))
            queries_executed.append(query)

            if self.local_search is not None:
                request_count = min(100, max(20, remaining * 3))
                try:
                    found = self.local_search.search_places(query, goal, count=request_count)
                except (BudgetExceeded, RunCancelled) as exc:
                    errors.append(f"{query}: {exc}")
                    break
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
                except (BudgetExceeded, RunCancelled) as exc:
                    errors.append(f"{query}: search stopped: {exc}")
                    break
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
                invalid_fields_removed += sanitize_lead_fields(lead, digital_only=digital_contact_only)
                quality = assess_lead_quality(lead, segment=goal.segment)
                if not quality.accepted:
                    quality_rejected += 1
                    continue
                if goal.require_phone and not lead.phone:
                    continue
                key = lead_key(lead)
                duplicate_key = find_duplicate_key(unique, lead)
                if duplicate_key is not None:
                    duplicates_removed += 1
                    merge_leads(unique[duplicate_key], lead)
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
                    invalid_fields_removed += sanitize_lead_fields(lead, digital_only=digital_contact_only)

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
                    invalid_fields_removed += sanitize_lead_fields(
                        lead, digital_only=digital_contact_only
                    )

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
                        controller.consume(BudgetKind.WEBSITE_AUDIT)
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
                    except (BudgetExceeded, RunCancelled) as exc:
                        errors.append(f"{lead.name}: website audit stopped: {exc}")
                        break
                    except Exception as exc:
                        website_audit_errors += 1
                        errors.append(f"{lead.name}: website audit failed: {exc}")

        browser_audits_run = 0
        browser_audits_reused = 0
        browser_audit_errors = 0
        if browser_audit:
            if self.browser_auditor is None:
                errors.append("browser audit requested but no browser auditor is configured")
            else:
                browser_candidates = [lead for lead in leads if lead.website and lead.website_status.value == "present"]
                browser_candidates.sort(
                    key=lambda item: (
                        item.identity_confidence,
                        item.confidence_score,
                        item.score,
                    ),
                    reverse=True,
                )
                cap = len(browser_candidates) if browser_audit_limit is None else max(0, int(browser_audit_limit))
                for lead in browser_candidates[:cap]:
                    try:
                        controller.consume(BudgetKind.BROWSER_AUDIT)
                        outcome = self.browser_auditor.audit(
                            lead,
                            timeout=browser_timeout,
                            max_age_days=browser_audit_ttl_days,
                            force=refresh_browser_audits,
                            artifacts_dir=browser_artifacts_dir,
                        )
                        if outcome.reused:
                            browser_audits_reused += 1
                        else:
                            browser_audits_run += 1
                        if outcome.audit.error or not outcome.audit.loaded:
                            browser_audit_errors += 1
                    except (BudgetExceeded, RunCancelled) as exc:
                        errors.append(f"{lead.name}: browser audit stopped: {exc}")
                        break
                    except Exception as exc:
                        browser_audit_errors += 1
                        errors.append(f"{lead.name}: browser audit failed: {exc}")

        visual_audits_run = 0
        visual_audits_reused = 0
        visual_audit_errors = 0
        if visual_audit:
            if self.visual_auditor is None:
                errors.append("visual audit requested but no visual auditor is configured")
            else:
                visual_candidates = [
                    lead for lead in leads
                    if lead.website
                    and lead.browser_audit is not None
                    and lead.browser_audit.loaded
                    and lead.browser_audit.desktop_screenshot
                    and lead.browser_audit.mobile_screenshot
                ]
                visual_candidates.sort(
                    key=lambda item: (
                        item.identity_confidence,
                        item.confidence_score,
                        item.score,
                    ),
                    reverse=True,
                )
                cap = len(visual_candidates) if visual_audit_limit is None else max(0, int(visual_audit_limit))
                for lead in visual_candidates[:cap]:
                    try:
                        controller.consume(BudgetKind.VISUAL_AUDIT)
                        outcome = self.visual_auditor.audit(
                            lead,
                            max_age_days=visual_audit_ttl_days,
                            force=refresh_visual_audits,
                        )
                        if outcome.reused:
                            visual_audits_reused += 1
                        else:
                            visual_audits_run += 1
                        if outcome.audit.confidence < 0.45:
                            visual_audit_errors += 1
                            errors.append(
                                f"{lead.name}: visual audit low confidence "
                                f"({outcome.audit.confidence:.0%})"
                            )
                    except (BudgetExceeded, RunCancelled) as exc:
                        errors.append(f"{lead.name}: visual audit stopped: {exc}")
                        break
                    except Exception as exc:
                        visual_audit_errors += 1
                        errors.append(f"{lead.name}: visual audit failed: {exc}")

        # Re-score after enrichment/investigation/audits because verified fields
        # and browser behaviour can materially change the opportunity score.
        for lead in leads:
            score_lead(lead, prefer_no_website=goal.prefer_no_website)

        filter_candidates_seen = len(leads)
        filter_rejected = 0
        if lead_filter is not None and lead_filter.active:
            accepted: list[Lead] = []
            for lead in leads:
                if assess_filter(lead, lead_filter).accepted:
                    accepted.append(lead)
                else:
                    filter_rejected += 1
            leads = accepted

        leads.sort(
            key=lambda item: (
                bool(item.opportunity and item.opportunity.actionable),
                item.score,
                item.review_count if item.review_count is not None else -1,
                item.confidence_score,
                bool(item.phone),
            ),
            reverse=True,
        )
        leads = leads[: goal.limit]

        if len(leads) < goal.limit and controller.stop_reason is None:
            controller.status = RunStatus.PARTIAL_RESULTS
            controller.stop_reason = (
                f"quantidade parcial: {len(leads)}/{goal.limit} leads elegíveis após descoberta, "
                "deduplicação e filtros"
            )

        cache_after = _cache_snapshot(self.web_search)
        cache_hits = cache_misses = cache_writes = 0
        if cache_before is not None and cache_after is not None:
            delta = cache_after.delta(cache_before)
            cache_hits = delta.hits
            cache_misses = delta.misses
            cache_writes = delta.writes

        controller.finish()
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
            browser_audits_run=browser_audits_run,
            browser_audits_reused=browser_audits_reused,
            browser_audit_errors=browser_audit_errors,
            visual_audits_run=visual_audits_run,
            visual_audits_reused=visual_audits_reused,
            visual_audit_errors=visual_audit_errors,
            filter_candidates_seen=filter_candidates_seen,
            filter_rejected=filter_rejected,
            run_status=controller.status.value,
            run_stop_reason=controller.stop_reason,
            usage_search_calls=controller.usage.search_calls,
            usage_llm_calls=controller.usage.llm_calls,
            usage_website_audits=controller.usage.website_audits,
            usage_browser_audits=controller.usage.browser_audits,
            usage_visual_audits=controller.usage.visual_audits,
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
