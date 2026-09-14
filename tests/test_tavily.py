from __future__ import annotations

import unittest

from leadflow_agent.models import SearchGoal
from leadflow_agent.providers.tavily import TavilySearchProvider


class FakeHttp:
    def __init__(self):
        self.posts = []

    def get_json(self, url, *, params=None, headers=None):
        return {"key": {"usage": 7, "limit": 1000}}

    def post_json(self, url, *, payload, headers=None):
        self.posts.append((url, payload, headers))
        return {
            "results": [
                {
                    "title": "Marcenaria | Praia Grande (@mp.marcenariapg) - Instagram",
                    "url": "https://www.instagram.com/mp.marcenariapg",
                    "content": "WhatsApp: (13) 97426-5722 – Praia Grande/SP",
                },
                {
                    "title": "Marcenarias / Marceneiros em Praia Grande, SP — WhatsApp",
                    "url": "https://acheioprofissional.com.br/marceneiro/praia-grande",
                    "content": "São 17 profissionais. Marcenaria Open Art, Planejados, Carpintaria Menezes.",
                },
            ]
        }


class TavilyTests(unittest.TestCase):
    def test_validate_key_uses_usage(self):
        provider = TavilySearchProvider("tvly-test", http=FakeHttp())
        ok, detail = provider.validate_key()
        self.assertTrue(ok)
        self.assertIn("7/1000", detail)

    def test_search_web(self):
        http = FakeHttp()
        provider = TavilySearchProvider("tvly-test", http=http)
        hits = provider.search_web('"marcenaria" "Praia Grande"', count=10)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].url, "https://www.instagram.com/mp.marcenariapg")
        self.assertEqual(http.posts[0][1]["search_depth"], "basic")
        self.assertEqual(http.posts[0][1]["country"], "brazil")

    def test_heuristic_requires_segment_signal(self):
        from leadflow_agent.models import WebHit
        provider = TavilySearchProvider("tvly-test", http=FakeHttp())
        hits = [WebHit(
            title="Forte Madeiras",
            url="https://www.fortemadeiras.com.br",
            description="Madeiras, ferragens e materiais para profissionais.",
        )]
        leads = provider.heuristic_leads(
            hits, SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"), query="marcenaria"
        )
        self.assertEqual(leads, [])

    def test_heuristic_skips_social_reels_and_posts(self):
        provider = TavilySearchProvider("tvly-test", http=FakeHttp())
        hits = [
            __import__("leadflow_agent.models", fromlist=["WebHit"]).WebHit(
                title="Conheça a Forte Madeiras, a loja mais completa e a ...",
                url="https://www.instagram.com/reel/DSGL728kZ9S",
                description="telefone (13) 99794-3496",
            ),
            __import__("leadflow_agent.models", fromlist=["WebHit"]).WebHit(
                title="Instagram",
                url="https://www.instagram.com/p/DFvkz7zRO-k",
                description="telefone (13) 3494-2931",
            ),
        ]
        leads = provider.heuristic_leads(
            hits, SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"), query="marcenaria"
        )
        self.assertEqual(leads, [])

    def test_heuristic_skips_directory_and_extracts_direct_profile(self):
        provider = TavilySearchProvider("tvly-test", http=FakeHttp())
        hits = provider.search_web('"marcenaria" "Praia Grande"', count=10)
        leads = provider.heuristic_leads(
            hits,
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"),
            query="marcenaria",
        )
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].name, "Marcenaria")
        self.assertIn("97426-5722", leads[0].phone or "")
        self.assertEqual(leads[0].socials[0], "https://www.instagram.com/mp.marcenariapg")


if __name__ == "__main__":
    unittest.main()
