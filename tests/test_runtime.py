from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.agent import LeadResearchAgent
from leadflow_agent.cache import CachedWebSearchProvider, PersistentSearchCache
from leadflow_agent.cli import _parser, _search
from leadflow_agent.config import Settings
from leadflow_agent.http import HTTPError
from leadflow_agent.models import Lead, SearchGoal, WebHit
from leadflow_agent.providers.guarded import GuardedAIProvider, GuardedLocalSearchProvider, GuardedWebSearchProvider
from leadflow_agent.runtime import (
    BudgetExceeded,
    BudgetKind,
    CircuitOpenError,
    RunBudget,
    RunCancelled,
    RunController,
    RunStatus,
)


class _FakeWeb:
    name = "fake-web"

    def __init__(self):
        self.calls = 0

    def search_web(self, query: str, *, country: str = "BR", count: int = 10):
        self.calls += 1
        return [WebHit(title="Example", url="https://example.com", description="", query=query)]


class _FailingWeb:
    name = "failing-web"

    def __init__(self):
        self.calls = 0

    def search_web(self, query: str, *, country: str = "BR", count: int = 10):
        self.calls += 1
        raise HTTPError("HTTP 503", status_code=503)


class _NetworkFailingWeb:
    name = "network-failing-web"

    def __init__(self):
        self.calls = 0

    def search_web(self, query: str, *, country: str = "BR", count: int = 10):
        self.calls += 1
        raise HTTPError("Network error: DNS name resolution failed")


class _EmptyLocal:
    name = "empty-local"

    def search_places(self, query: str, goal: SearchGoal, *, count: int = 20):
        return []


class _BatchAI:
    name = "batch-ai"

    def __init__(self):
        self.calls = 0

    def extract_investigation_candidates_batch(
        self, search_batches, lead, goal, *, max_candidates=20
    ):
        self.calls += 1
        return []


class RuntimeSafetyTests(unittest.TestCase):
    def test_budget_blocks_call_after_limit(self):
        controller = RunController(RunBudget(max_search_calls=1))
        controller.consume(BudgetKind.SEARCH)
        with self.assertRaises(BudgetExceeded):
            controller.consume(BudgetKind.SEARCH)
        self.assertEqual(controller.status, RunStatus.PARTIAL_BUDGET)
        self.assertEqual(controller.usage.search_calls, 1)

    def test_cancel_hook_stops_run(self):
        controller = RunController(cancel_check=lambda: True)
        with self.assertRaises(RunCancelled):
            controller.check_cancelled()
        self.assertEqual(controller.status, RunStatus.CANCELLED)

    def test_cached_hit_does_not_spend_second_search_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = _FakeWeb()
            controller = RunController(RunBudget(max_search_calls=5))
            guarded = GuardedWebSearchProvider(fake, controller)
            cached = CachedWebSearchProvider(
                guarded,
                PersistentSearchCache(str(Path(tmp) / "cache.db"), ttl_days=1),
            )
            cached.search_web("query", count=1)
            cached.search_web("query", count=1)
            self.assertEqual(fake.calls, 1)
            self.assertEqual(controller.usage.search_calls, 1)

    def test_circuit_breaker_opens_after_transient_failures(self):
        failing = _FailingWeb()
        controller = RunController(RunBudget(max_search_calls=10))
        guarded = GuardedWebSearchProvider(failing, controller)
        for _ in range(3):
            with self.assertRaises(HTTPError):
                guarded.search_web("query")
        with self.assertRaises(CircuitOpenError):
            guarded.search_web("query")
        self.assertEqual(failing.calls, 3)
        self.assertEqual(controller.usage.search_calls, 3)

    def test_guarded_batch_investigation_counts_one_llm_call(self):
        controller = RunController(RunBudget(max_llm_calls=3))
        provider = _BatchAI()
        guarded = GuardedAIProvider(provider, controller)
        guarded.extract_investigation_candidates_batch(
            [("query", "website", [])],
            Lead(name="Empresa", city="Praia Grande", state="SP"),
            SearchGoal("marcenaria", "Praia Grande", state="SP"),
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(controller.usage.llm_calls, 1)

    def test_circuit_breaker_treats_statusless_network_error_as_transient(self):
        failing = _NetworkFailingWeb()
        controller = RunController(RunBudget(max_search_calls=10))
        guarded = GuardedWebSearchProvider(failing, controller)
        for _ in range(3):
            with self.assertRaises(HTTPError):
                guarded.search_web("query")
        with self.assertRaises(CircuitOpenError):
            guarded.search_web("query")
        self.assertEqual(failing.calls, 3)

    def test_agent_returns_partial_report_when_search_budget_exhausts(self):
        controller = RunController(RunBudget(max_search_calls=1))
        local = GuardedLocalSearchProvider(_EmptyLocal(), controller)
        agent = LeadResearchAgent(local_search=local, run_controller=controller)
        report = agent.research(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10),
            max_queries=3,
        )
        self.assertEqual(report.run_status, "partial_budget")
        self.assertEqual(report.usage_search_calls, 1)
        self.assertIsNotNone(report.run_stop_reason)

    def test_cli_rejects_1000_leads_before_provider_calls(self):
        args = _parser().parse_args([
            "search", "--segment", "marcenaria", "--city", "Praia Grande", "--limit", "1000"
        ])
        self.assertEqual(_search(args, Settings()), 2)


if __name__ == "__main__":
    unittest.main()
