from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.models import Lead, QueryPlan, ResearchReport, SearchGoal
from leadflow_agent.storage import DB_SCHEMA_VERSION, LeadStore


class LeadLifecycleTests(unittest.TestCase):
    def _store(self, tmp: str) -> tuple[LeadStore, str]:
        store = LeadStore(str(Path(tmp) / "leadflow.db"))
        report = ResearchReport(
            goal=SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=1),
            plan=QueryPlan(["marcenaria Praia Grande"]),
            leads=[Lead("Empresa Lifecycle", city="Praia Grande", state="SP", phone="13999990000")],
            queries_executed=["marcenaria Praia Grande"], local_results_seen=1, duplicates_removed=0,
            started_at="a", finished_at="b",
        )
        store.save_report(report)
        return store, next(iter(store.existing_lead_keys()))

    def test_schema_and_default_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            self.assertEqual(store.conn.execute("PRAGMA user_version").fetchone()[0], DB_SCHEMA_VERSION)
            self.assertEqual(store.list_leads("all")[0]["lifecycle"]["status"], "new")
            self.assertIn(key, store.existing_lead_keys())
            store.close()

    def test_queue_then_contacted_removes_from_active_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            item = store.enqueue_contact(key, "Olá!")
            self.assertEqual(item["status"], "queued")
            self.assertEqual(store.list_queue()[0]["status"], "queued")
            store.update_lifecycle(key, "contacted")
            self.assertEqual(store.list_leads("contacted")[0]["lifecycle"]["status"], "contacted")
            self.assertEqual(store.list_queue(), [])
            store.close()

    def test_hidden_lead_can_be_restored_to_new_without_losing_contact_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            store.update_lifecycle(key, "contacted")
            contacted_at = store.list_leads("contacted")[0]["lifecycle"]["last_contacted_at"]
            store.update_lifecycle(key, "hidden")
            store.update_lifecycle(key, "new")
            lead = store.list_leads("new")[0]
            self.assertEqual(lead["lead_key"], key)
            self.assertEqual(lead["lifecycle"]["status"], "new")
            self.assertEqual(lead["lifecycle"]["last_contacted_at"], contacted_at)
            self.assertEqual(store.list_leads("hidden"), [])
            store.close()

    def test_follow_up_can_be_scheduled_and_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            lead = store.schedule_follow_up(key, "2099-01-02T12:00:00Z", "retorno da proposta")
            self.assertEqual(lead["lifecycle"]["follow_up_at"], "2099-01-02T12:00:00Z")
            self.assertEqual(store.list_follow_ups()[0]["note"], "retorno da proposta")
            self.assertEqual(store.list_leads("all")[0]["lifecycle"]["follow_up_note"], "retorno da proposta")
            self.assertTrue(store.clear_follow_up(key))
            self.assertEqual(store.list_follow_ups(), [])
            store.close()

    def test_lifecycle_views_are_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            for status in ("accepted", "ignored", "hidden"):
                store.update_lifecycle(key, status)
                self.assertEqual(store.list_leads(status)[0]["lead_key"], key)
            store.close()

    def test_sales_pipeline_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            for status in ("accepted", "contacted", "awaiting_response", "responded", "proposal_sent", "negotiating", "won", "lost"):
                self.assertTrue(store.update_lifecycle(key, status))
                self.assertEqual(store.list_leads(status)[0]["lifecycle"]["status"], status)
            self.assertEqual(store.list_queue(), [])
            store.close()

    def test_interaction_history_records_outcome_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            item = store.add_interaction(key, kind="sales_activity", channel="whatsapp", outcome="Respondeu", note="Pediu exemplos.", status="responded")
            self.assertIsNotNone(item)
            self.assertEqual(item["outcome"], "Respondeu")
            self.assertEqual(item["lead"]["lifecycle"]["status"], "responded")
            rows = store.list_interactions(key)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["note"], "Pediu exemplos.")
            self.assertEqual(store.list_leads("responded")[0]["lead_key"], key)
            store.close()

    def test_interaction_without_status_keeps_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, key = self._store(tmp)
            store.update_lifecycle(key, "contacted")
            item = store.add_interaction(key, outcome="Anotação", note="Cliente visualizou", status=None)
            self.assertEqual(item["lead"]["lifecycle"]["status"], "contacted")
            self.assertEqual(store.list_interactions(key)[0]["outcome"], "Anotação")
            store.close()


if __name__ == "__main__":
    unittest.main()
