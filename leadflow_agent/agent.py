from __future__ import annotations

from .dedupe import lead_key, merge_leads
from .enrichment import enrich_lead_from_web
from .models import Lead, ResearchReport, SearchGoal, utc_now_iso
from .planner import build_plan
from .providers.base import LeadExtractorProvider, LLMProvider, LocalSearchProvider, WebSearchProvider
from .scoring import score_lead


class LeadResearchAgent:
    def __init__(
        self,
        *,
        local_search: LocalSearchProvider | None = None,
        web_search: WebSearchProvider | None = None,
        llm: LLMProvider | None = None,
        lead_extractor: LeadExtractorProvider | None = None,
    ):
        if local_search is None and web_search is None:
            raise ValueError("LeadResearchAgent requires a local or web search provider.")
        self.local_search = local_search
        self.web_search = web_search
        self.llm = llm
        self.lead_extractor = lead_extractor

    def research(
        self,
        goal: SearchGoal,
        *,
        max_queries: int = 6,
        enrich_web: bool = False,
        enrichment_limit: int | None = None,
    ) -> ResearchReport:
        started = utc_now_iso()
        plan = build_plan(goal, self.llm, max_queries=max_queries)
        unique: dict[str, Lead] = {}
        queries_executed: list[str] = []
        source_results_seen = 0
        duplicates_removed = 0
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
                if goal.require_phone and not lead.phone:
                    continue
                key = lead_key(lead)
                if key in unique:
                    duplicates_removed += 1
                    merge_leads(unique[key], lead)
                else:
                    unique[key] = lead

        leads = list(unique.values())

        if enrich_web and self.web_search is not None:
            candidates = leads if enrichment_limit is None else leads[: max(0, enrichment_limit)]
            for lead in candidates:
                if lead.website is None or not lead.socials:
                    try:
                        enrich_lead_from_web(lead, goal, self.web_search)
                    except Exception as exc:
                        from .models import Evidence
                        lead.evidence.append(Evidence(source=self.web_search.name, kind="enrichment_error", detail=str(exc)))

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
        )


def _build_web_discovery_query(query: str, goal: SearchGoal) -> str:
    location = " ".join(part for part in (goal.city, goal.state) if part).strip()
    # Contact/social terms bias general web search toward evidence that is useful
    # for prospecting without requiring a dedicated business-listings database.
    return f'"{query}" "{location}" telefone OR WhatsApp OR Instagram'.strip()
