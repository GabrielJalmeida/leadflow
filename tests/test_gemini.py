from __future__ import annotations

import unittest

from leadflow_agent.models import SearchGoal, WebHit
from leadflow_agent.providers.gemini import GeminiPlannerProvider, _extract_generate_text, _extract_json_object


class FakeHttp:
    def __init__(self, response=None, get_response=None):
        self.response = response or {}
        self.get_response = get_response or {"models": [{"name": "models/gemini-3.1-flash-lite"}]}
        self.posts = []

    def post_json(self, url, *, payload, headers=None):
        self.posts.append((url, payload, headers))
        return self.response

    def get_json(self, url, *, params=None, headers=None):
        return self.get_response


class GeminiTests(unittest.TestCase):
    def test_extract_json_code_fence(self):
        self.assertEqual(_extract_json_object('```json\n{"a":1}\n```')["a"], 1)

    def test_extract_generate_text(self):
        data = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
        self.assertEqual(_extract_generate_text(data), "hello")

    def test_validate_model_without_generation(self):
        provider = GeminiPlannerProvider("abc", http=FakeHttp())
        ok, _ = provider.validate_key(live_generation=False)
        self.assertTrue(ok)

    def test_planner_generatecontent(self):
        response = {"candidates": [{"content": {"parts": [{"text": '{"queries":["marcenaria","móveis planejados"],"rationale":"x"}'}]}}]}
        provider = GeminiPlannerProvider("abc", http=FakeHttp(response=response))
        plan = provider.plan_queries(SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"), max_queries=4)
        self.assertEqual(plan.queries[0], "marcenaria")
        self.assertIn("móveis planejados", plan.queries)
        self.assertTrue(plan.generated_by.startswith("gemini:"))


    def test_extract_multiple_leads_from_directory_evidence(self):
        response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"leads":[{"name":"Marcenaria Open Art","phone":null,"email":null,"website":null,"socials":[],"address":null,"source_url":"https://example.com/lista","source_title":"Lista","confidence":0.92},{"name":"Carpintaria Menezes","phone":null,"email":null,"website":null,"socials":[],"address":null,"source_url":"https://example.com/lista","source_title":"Lista","confidence":0.88}]}'
                    }]
                }
            }]
        }
        provider = GeminiPlannerProvider("abc", http=FakeHttp(response=response))
        hits = [WebHit(title="Lista", url="https://example.com/lista", description="Marcenaria Open Art, Carpintaria Menezes")]
        leads = provider.extract_leads(
            hits,
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"),
            query="marcenaria",
        )
        self.assertEqual([lead.name for lead in leads], ["Marcenaria Open Art", "Carpintaria Menezes"])
        self.assertTrue(all(lead.source_provider == "tavily+gemini" for lead in leads))


if __name__ == "__main__":
    unittest.main()
