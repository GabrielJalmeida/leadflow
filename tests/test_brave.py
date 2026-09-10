from __future__ import annotations

import unittest

from leadflow_agent.models import SearchGoal
from leadflow_agent.providers.brave import BraveSearchProvider


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.last_params = None

    def get_json(self, url, *, params=None, headers=None):
        self.last_params = params
        return self.payload


class BraveParsingTests(unittest.TestCase):
    def test_parse_local_business(self):
        payload = {
            "results": [
                {
                    "id": "abc",
                    "title": "Stylomar Marcenaria",
                    "provider_url": "https://example.local/stylomar",
                    "coordinates": [-24.0, -46.4],
                    "postal_address": {
                        "displayAddress": "Rua Exemplo, Praia Grande - SP",
                        "addressLocality": "Praia Grande",
                        "addressRegion": "SP",
                        "country": "Brazil",
                    },
                    "contact": {"telephone": "+55 13 99999-9999", "email": "oi@example.com"},
                    "rating": {"ratingValue": 4.8, "reviewCount": 42},
                    "categories": ["Marcenaria"],
                    "profiles": [{"url": "https://www.instagram.com/stylomar", "name": "Instagram"}],
                    "results": [{"url": "https://stylomar.example", "title": "Stylomar"}],
                }
            ]
        }
        http = FakeHttp(payload)
        provider = BraveSearchProvider("key", http=http)
        goal = SearchGoal(segment="marcenaria", city="Praia Grande", state="SP", limit=10)
        leads = provider.search_places("marcenaria", goal, count=10)
        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead.name, "Stylomar Marcenaria")
        self.assertEqual(lead.phone, "+55 13 99999-9999")
        self.assertEqual(lead.website, "https://stylomar.example")
        self.assertIn("https://www.instagram.com/stylomar", lead.socials)
        self.assertEqual(lead.review_count, 42)
        self.assertEqual(http.last_params["location"], "Praia Grande, SP, Brazil")


if __name__ == "__main__":
    unittest.main()
