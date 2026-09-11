from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .http import HTTPError


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_BUDGET = "partial_budget"
    CANCELLED = "cancelled"


class BudgetKind(str, Enum):
    SEARCH = "search"
    LLM = "llm"
    WEBSITE_AUDIT = "website_audit"
    BROWSER_AUDIT = "browser_audit"
    VISUAL_AUDIT = "visual_audit"


@dataclass(slots=True)
class RunBudget:
    """Hard safety envelope for one research run.

    These limits are intentionally independent from user-facing result counts.
    A filter that asks for 100 final leads must never grant the agent unlimited
    provider calls while trying to satisfy that request.
    """

    max_search_calls: int = 20
    max_llm_calls: int = 30
    max_website_audits: int = 25
    max_browser_audits: int = 10
    max_visual_audits: int = 10

    def __post_init__(self) -> None:
        for name in (
            "max_search_calls",
            "max_llm_calls",
            "max_website_audits",
            "max_browser_audits",
            "max_visual_audits",
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
            setattr(self, name, value)

    def limit_for(self, kind: BudgetKind) -> int:
        return {
            BudgetKind.SEARCH: self.max_search_calls,
            BudgetKind.LLM: self.max_llm_calls,
            BudgetKind.WEBSITE_AUDIT: self.max_website_audits,
            BudgetKind.BROWSER_AUDIT: self.max_browser_audits,
            BudgetKind.VISUAL_AUDIT: self.max_visual_audits,
        }[kind]


@dataclass(slots=True)
class RunUsage:
    search_calls: int = 0
    llm_calls: int = 0
    website_audits: int = 0
    browser_audits: int = 0
    visual_audits: int = 0

    def count_for(self, kind: BudgetKind) -> int:
        return {
            BudgetKind.SEARCH: self.search_calls,
            BudgetKind.LLM: self.llm_calls,
            BudgetKind.WEBSITE_AUDIT: self.website_audits,
            BudgetKind.BROWSER_AUDIT: self.browser_audits,
            BudgetKind.VISUAL_AUDIT: self.visual_audits,
        }[kind]

    def increment(self, kind: BudgetKind) -> None:
        if kind == BudgetKind.SEARCH:
            self.search_calls += 1
        elif kind == BudgetKind.LLM:
            self.llm_calls += 1
        elif kind == BudgetKind.WEBSITE_AUDIT:
            self.website_audits += 1
        elif kind == BudgetKind.BROWSER_AUDIT:
            self.browser_audits += 1
        elif kind == BudgetKind.VISUAL_AUDIT:
            self.visual_audits += 1


class BudgetExceeded(RuntimeError):
    def __init__(self, kind: BudgetKind, used: int, limit: int):
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"run budget exhausted for {kind.value}: {used}/{limit}")


class RunCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class RunController:
    budget: RunBudget = field(default_factory=RunBudget)
    cancel_check: Callable[[], bool] | None = None
    usage: RunUsage = field(default_factory=RunUsage)
    status: RunStatus = RunStatus.RUNNING
    stop_reason: str | None = None

    def check_cancelled(self) -> None:
        if self.cancel_check is not None and self.cancel_check():
            self.status = RunStatus.CANCELLED
            self.stop_reason = "cancelamento solicitado"
            raise RunCancelled(self.stop_reason)

    def consume(self, kind: BudgetKind) -> None:
        self.check_cancelled()
        used = self.usage.count_for(kind)
        limit = self.budget.limit_for(kind)
        if used >= limit:
            self.status = RunStatus.PARTIAL_BUDGET
            self.stop_reason = f"orçamento de {kind.value} atingido ({used}/{limit})"
            raise BudgetExceeded(kind, used, limit)
        self.usage.increment(kind)

    def finish(self) -> None:
        if self.status == RunStatus.RUNNING:
            self.status = RunStatus.COMPLETED


class CircuitOpenError(RuntimeError):
    pass


@dataclass(slots=True)
class CircuitBreaker:
    """Small per-run provider circuit breaker.

    It opens only after repeated transient provider/network failures. Permanent
    4xx configuration errors are still returned immediately to the caller but
    do not create a misleading transient outage state.
    """

    name: str
    failure_threshold: int = 3
    consecutive_failures: int = 0
    open: bool = False

    def before_call(self) -> None:
        if self.open:
            raise CircuitOpenError(
                f"circuit breaker aberto para {self.name} após "
                f"{self.consecutive_failures} falhas transitórias consecutivas"
            )

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self, exc: Exception) -> None:
        if not _is_transient(exc):
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= max(1, int(self.failure_threshold)):
            self.open = True


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.status_code in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, ConnectionError)) or "timed out" in str(exc).casefold()
