from __future__ import annotations

from typing import Protocol

from ..models import InvestigationCandidate, Lead, QueryPlan, SearchGoal, WebHit


class LocalSearchProvider(Protocol):
    name: str

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20) -> list[Lead]: ...


class WebSearchProvider(Protocol):
    name: str

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]: ...


class LeadExtractorProvider(Protocol):
    name: str

    def extract_leads(self, hits: list[WebHit], goal: SearchGoal, *, query: str, max_leads: int = 20) -> list[Lead]: ...




class LeadInvestigationExtractorProvider(Protocol):
    name: str

    def extract_investigation_candidates(
        self,
        hits: list[WebHit],
        lead: Lead,
        goal: SearchGoal,
        *,
        query: str,
        purpose: str,
        max_candidates: int = 12,
    ) -> list[InvestigationCandidate]: ...


class LLMProvider(Protocol):
    name: str

    def plan_queries(self, goal: SearchGoal, *, max_queries: int = 6) -> QueryPlan: ...
