from __future__ import annotations

from typing import Any

from ..models import InvestigationCandidate, Lead, QueryPlan, SearchGoal, VisualAudit, WebHit
from ..runtime import BudgetKind, CircuitBreaker, RunController


class _GuardedBase:
    def __init__(self, provider: Any, controller: RunController, *, role: str):
        self.provider = provider
        self.controller = controller
        self.name = provider.name
        self.breaker = CircuitBreaker(f"{self.name}:{role}")

    def _call(self, kind: BudgetKind, method: str, *args, **kwargs):
        self.breaker.before_call()
        self.controller.consume(kind)
        try:
            result = getattr(self.provider, method)(*args, **kwargs)
        except Exception as exc:
            self.breaker.record_failure(exc)
            raise
        self.breaker.record_success()
        return result

    def __getattr__(self, name: str):
        return getattr(self.provider, name)


class GuardedWebSearchProvider(_GuardedBase):
    def __init__(self, provider: Any, controller: RunController):
        super().__init__(provider, controller, role="web-search")

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]:
        return self._call(BudgetKind.SEARCH, "search_web", query, country=country, count=count)


class GuardedLocalSearchProvider(_GuardedBase):
    def __init__(self, provider: Any, controller: RunController):
        super().__init__(provider, controller, role="local-search")

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20) -> list[Lead]:
        return self._call(BudgetKind.SEARCH, "search_places", query, goal, count=count)


class GuardedAIProvider(_GuardedBase):
    def __init__(self, provider: Any, controller: RunController):
        super().__init__(provider, controller, role="ai")

    def plan_queries(self, goal: SearchGoal, *, max_queries: int = 6) -> QueryPlan:
        return self._call(BudgetKind.LLM, "plan_queries", goal, max_queries=max_queries)

    def extract_leads(
        self,
        hits: list[WebHit],
        goal: SearchGoal,
        *,
        query: str,
        max_leads: int = 20,
    ) -> list[Lead]:
        return self._call(
            BudgetKind.LLM,
            "extract_leads",
            hits,
            goal,
            query=query,
            max_leads=max_leads,
        )

    def extract_investigation_candidates(
        self,
        hits: list[WebHit],
        lead: Lead,
        goal: SearchGoal,
        *,
        query: str,
        purpose: str,
        max_candidates: int = 12,
    ) -> list[InvestigationCandidate]:
        return self._call(
            BudgetKind.LLM,
            "extract_investigation_candidates",
            hits,
            lead,
            goal,
            query=query,
            purpose=purpose,
            max_candidates=max_candidates,
        )

    def analyze_visual_audit(self, *args, **kwargs) -> VisualAudit:
        return self._call(BudgetKind.LLM, "analyze_visual_audit", *args, **kwargs)
