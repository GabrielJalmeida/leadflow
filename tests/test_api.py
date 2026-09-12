from __future__ import annotations

import importlib.util
import threading
import time
import unittest

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient

    from leadflow_agent.api import SearchRunManager, create_app
    from leadflow_agent.search_service import SearchExecution, SearchRequest


@unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependency is not installed")
class ApiTests(unittest.TestCase):
    def _client(self, runner):
        manager = SearchRunManager(runner=runner)
        return TestClient(create_app(manager=manager)), manager

    def test_health_and_catalog_are_available(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        health = client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        segments = client.get("/api/v1/catalog/segments")
        self.assertEqual(segments.status_code, 200)
        self.assertTrue(segments.json()["free_text_allowed"])

        profiles = client.get("/api/v1/catalog/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertTrue(any(item["slug"] == "website-sales" for item in profiles.json()["items"]))

    def test_contact_prepare_returns_frontend_ready_action(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        response = client.post(
            "/api/v1/contact/prepare",
            json={
                "lead": {
                    "name": "Example Marcenaria",
                    "location": {"country": "Brazil"},
                    "contact": {
                        "phone": "(13) 99999-1234",
                        "socials": ["https://www.instagram.com/example/"],
                    },
                    "opportunity": {"type": "new_site"},
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel"], "whatsapp")
        self.assertIn("Example Marcenaria", payload["message"])
        self.assertTrue(payload["whatsapp_url"].startswith("https://wa.me/55"))

    def test_contact_prepare_prefers_instagram_for_fixed_line(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        response = client.post(
            "/api/v1/contact/prepare",
            json={
                "lead": {
                    "name": "Fixed Line Company",
                    "location": {"country": "Brazil"},
                    "contact": {
                        "phone": "(13) 3491-6447",
                        "socials": ["https://www.instagram.com/fixedline/"],
                    },
                    "opportunity": {"type": "new_site"},
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel"], "instagram")
        self.assertEqual(payload["instagram_url"], "https://www.instagram.com/fixedline/")

    def test_background_run_returns_frontend_contract(self):
        def runner(request: SearchRequest, _cancel):
            return SearchExecution(
                provider="fake",
                db_run_id=7,
                contract={
                    "contract_version": "1.0",
                    "run": {"status": "completed", "requested_results": request.limit, "returned_results": 1},
                    "goal": {"segment": request.segment, "city": request.city, "state": request.state, "country": request.country},
                    "leads": [{"name": "Example"}],
                },
            )

        client, _ = self._client(runner)
        response = client.post(
            "/api/v1/runs",
            json={
                "segment": "marcenaria",
                "city": "Praia Grande",
                "state": "SP",
                "limit": 10,
                "features": {"investigate": False, "audit_websites": False},
            },
        )
        self.assertEqual(response.status_code, 202)
        run_id = response.json()["id"]

        for _ in range(50):
            status_response = client.get(f"/api/v1/runs/{run_id}")
            if status_response.json()["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual(status_response.json()["status"], "completed")
        self.assertEqual(status_response.json()["db_run_id"], 7)

        result = client.get(f"/api/v1/runs/{run_id}/result")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["result"]["contract_version"], "1.0")
        self.assertEqual(result.json()["result"]["leads"][0]["name"], "Example")

    def test_cancel_signals_running_job(self):
        started = threading.Event()

        def runner(_request: SearchRequest, cancel):
            started.set()
            while not cancel():
                time.sleep(0.005)
            return SearchExecution(
                provider="fake",
                contract={
                    "contract_version": "1.0",
                    "run": {"status": "cancelled", "requested_results": 10, "returned_results": 0},
                    "goal": {},
                    "leads": [],
                },
            )

        client, _ = self._client(runner)
        response = client.post(
            "/api/v1/runs",
            json={
                "segment": "marcenaria",
                "city": "Praia Grande",
                "features": {"investigate": False, "audit_websites": False},
            },
        )
        run_id = response.json()["id"]
        self.assertTrue(started.wait(0.5))

        cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn(cancelled.json()["status"], {"cancelling", "cancelled"})

        for _ in range(50):
            item = client.get(f"/api/v1/runs/{run_id}").json()
            if item["status"] == "cancelled":
                break
            time.sleep(0.01)
        self.assertEqual(item["status"], "cancelled")

    def test_local_frontend_origin_gets_cors_headers(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:5173"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_non_local_browser_origin_cannot_start_run(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        response = client.post(
            "/api/v1/runs",
            headers={"Origin": "https://example.com"},
            json={
                "segment": "marcenaria",
                "city": "Praia Grande",
                "features": {"investigate": False, "audit_websites": False},
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_run_is_404(self):
        def runner(_request, _cancel):
            raise AssertionError("runner should not be called")

        client, _ = self._client(runner)
        response = client.get("/api/v1/runs/not-a-real-id")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
