from __future__ import annotations

import unittest

from leadflow_agent.models import SearchGoal
from leadflow_agent.providers.outscraper import OutscraperSearchProvider, _flatten_data


class FakeHttp:
    def __init__(self):
        self.last_params = None

    def get_json(self, url, *, params=None, headers=None):
        self.last_params = params
        if "profile/balance" in url:
            return {"balance": 0, "account_status": "valid"}
        return {
            "status": "Success",
            "data": [[{
                "name": "Stylomar Marcenaria",
                "place_id": "place-1",
                "full_address": "Praia Grande, SP, Brazil",
                "country": "Brazil",
                "city": "Praia Grande",
                "state": "São Paulo",
                "site": None,
                "phone": "+55 13 99999-9999",
                "category": "Cabinet maker",
                "rating": 4.8,
                "reviews": 42,
                "latitude": -24.0,
                "longitude": -46.4,
                "location_link": "https://www.google.com/maps/place/x",
            }]]
        }


class OutscraperTests(unittest.TestCase):
    def test_flatten_data(self):
        self.assertEqual(len(_flatten_data([[{"a": 1}], [{"b": 2}]])), 2)

    def test_validate(self):
        provider = OutscraperSearchProvider("key", http=FakeHttp())
        ok, _ = provider.validate_key()
        self.assertTrue(ok)

    def test_search_parse(self):
        http = FakeHttp()
        provider = OutscraperSearchProvider("key", http=http)
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10)
        leads = provider.search_places("marcenaria", goal, count=10)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].name, "Stylomar Marcenaria")
        self.assertEqual(leads[0].phone, "+55 13 99999-9999")
        self.assertEqual(leads[0].review_count, 42)
        self.assertIn("Praia Grande", http.last_params["query"])


if __name__ == "__main__":
    unittest.main()
