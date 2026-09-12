from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import Lead, SearchGoal, WebHit
from ..runtime import BudgetExceeded, RunCancelled


@dataclass(slots=True)
class _CombinedCacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0

    def delta(self, earlier: "_CombinedCacheStats") -> "_CombinedCacheStats":
        return _CombinedCacheStats(
            hits=max(0, self.hits - earlier.hits),
            misses=max(0, self.misses - earlier.misses),
            writes=max(0, self.writes - earlier.writes),
        )


class RoundRobinWebSearchProvider:
    """Rotate configured web providers between discovery calls.

    One provider is used per call so search budgets remain predictable. If the
    selected provider fails for a non-budget/non-cancellation reason, the next
    configured provider is attempted before the discovery call is considered
    failed.
    """

    def __init__(self, providers: list[Any]):
        self.providers = [provider for provider in providers if provider is not None]
        if not self.providers:
            raise ValueError("RoundRobinWebSearchProvider requires at least one provider.")
        self.name = "+".join(dict.fromkeys(provider.name for provider in self.providers))
        self._cursor = 0
        self._last_provider: Any | None = None

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]:
        start = self._cursor % len(self.providers)
        errors: list[str] = []
        for offset in range(len(self.providers)):
            index = (start + offset) % len(self.providers)
            provider = self.providers[index]
            try:
                hits = provider.search_web(query, country=country, count=count)
            except (BudgetExceeded, RunCancelled):
                raise
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            self._cursor = (index + 1) % len(self.providers)
            self._last_provider = provider
            return hits
        raise RuntimeError("Todos os provedores web falharam: " + " | ".join(errors))

    def heuristic_leads(self, hits: list[WebHit], goal: SearchGoal, *, query: str) -> list[Lead]:
        ordered = []
        if self._last_provider is not None:
            ordered.append(self._last_provider)
        ordered.extend(provider for provider in self.providers if provider not in ordered)
        for provider in ordered:
            heuristic = getattr(provider, "heuristic_leads", None)
            if heuristic is None:
                continue
            leads = heuristic(hits, goal, query=query)
            if leads:
                return leads
        return []

    def cache_snapshot(self) -> _CombinedCacheStats:
        total = _CombinedCacheStats()
        for provider in self.providers:
            snapshot = getattr(provider, "cache_snapshot", None)
            if snapshot is None:
                continue
            try:
                stats = snapshot()
            except Exception:
                continue
            total.hits += int(getattr(stats, "hits", 0))
            total.misses += int(getattr(stats, "misses", 0))
            total.writes += int(getattr(stats, "writes", 0))
        return total


class RoundRobinLocalSearchProvider:
    """Rotate configured local-business providers between discovery calls."""

    def __init__(self, providers: list[Any]):
        self.providers = [provider for provider in providers if provider is not None]
        if not self.providers:
            raise ValueError("RoundRobinLocalSearchProvider requires at least one provider.")
        self.name = "+".join(dict.fromkeys(provider.name for provider in self.providers))
        self._cursor = 0

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20) -> list[Lead]:
        start = self._cursor % len(self.providers)
        errors: list[str] = []
        for offset in range(len(self.providers)):
            index = (start + offset) % len(self.providers)
            provider = self.providers[index]
            try:
                leads = provider.search_places(query, goal, count=count)
            except (BudgetExceeded, RunCancelled):
                raise
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
            self._cursor = (index + 1) % len(self.providers)
            return leads
        raise RuntimeError("Todos os provedores locais falharam: " + " | ".join(errors))
