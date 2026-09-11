from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from leadflow_agent.models import QueryPlan, ResearchReport, SearchGoal
from leadflow_agent.storage import DB_SCHEMA_VERSION, LeadStore


class StorageHardeningTests(unittest.TestCase):
    def test_old_research_runs_table_is_migrated_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "old.db"
            conn = sqlite3.connect(db)
            conn.execute(
                """CREATE TABLE research_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
                    segment TEXT NOT NULL, city TEXT NOT NULL, state TEXT, country TEXT,
                    requested_limit INTEGER NOT NULL, result_count INTEGER NOT NULL,
                    planner TEXT NOT NULL, queries_json TEXT NOT NULL
                )"""
            )
            conn.execute("CREATE TABLE leads (lead_key TEXT PRIMARY KEY, name TEXT NOT NULL, payload_json TEXT NOT NULL)")
            conn.execute("CREATE TABLE run_leads (run_id INTEGER, lead_key TEXT, position INTEGER)")
            conn.commit()
            conn.close()

            store = LeadStore(str(db))
            store.close()
            store = LeadStore(str(db))
            columns = {row[1] for row in store.conn.execute("PRAGMA table_info(research_runs)")}
            version = store.conn.execute("PRAGMA user_version").fetchone()[0]
            store.close()

            self.assertTrue({"run_status", "stop_reason", "usage_json"}.issubset(columns))
            self.assertEqual(version, DB_SCHEMA_VERSION)

    def test_run_status_and_usage_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "leadflow.db"
            store = LeadStore(str(db))
            report = ResearchReport(
                goal=SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10),
                plan=QueryPlan(["marcenaria"]),
                leads=[], queries_executed=["marcenaria"], local_results_seen=0,
                duplicates_removed=0, started_at="a", finished_at="b",
                run_status="partial_budget", run_stop_reason="budget",
                usage_search_calls=5, usage_llm_calls=2,
            )
            run_id = store.save_report(report)
            row = store.conn.execute(
                "SELECT run_status, stop_reason, usage_json FROM research_runs WHERE id=?", (run_id,)
            ).fetchone()
            store.close()
            self.assertEqual(row[0], "partial_budget")
            self.assertEqual(row[1], "budget")
            self.assertEqual(json.loads(row[2])["search_calls"], 5)


if __name__ == "__main__":
    unittest.main()
