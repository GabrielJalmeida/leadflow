from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.cache import CachedWebSearchProvider, PersistentSearchCache
from leadflow_agent.models import WebHit


class FakeWeb:
    name = "fake-web"

    def __init__(self):
        self.calls = 0

    def search_web(self, query, *, country="BR", count=10):
        self.calls += 1
        return [
            WebHit(
                title=f"Result {index}",
                url=f"https://example.com/{index}",
                description="evidence",
                query=query,
            )
            for index in range(count)
        ]


class CacheTests(unittest.TestCase):
    def test_second_identical_search_uses_persistent_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            upstream = FakeWeb()
            cache = PersistentSearchCache(db, ttl_days=14)
            provider = CachedWebSearchProvider(upstream, cache)

            first = provider.search_web("marcenaria praia grande", count=5)
            second = provider.search_web("marcenaria praia grande", count=5)

            self.assertEqual(len(first), 5)
            self.assertEqual(len(second), 5)
            self.assertEqual(upstream.calls, 1)
            self.assertEqual(cache.stats.hits, 1)
            self.assertEqual(cache.stats.misses, 1)
            self.assertEqual(cache.stats.writes, 1)

    def test_cache_survives_new_provider_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            first_upstream = FakeWeb()
            CachedWebSearchProvider(
                first_upstream,
                PersistentSearchCache(db),
            ).search_web("empresa x", count=4)
            self.assertEqual(first_upstream.calls, 1)

            second_upstream = FakeWeb()
            cache = PersistentSearchCache(db)
            result = CachedWebSearchProvider(second_upstream, cache).search_web(
                "empresa x", count=4
            )
            self.assertEqual(len(result), 4)
            self.assertEqual(second_upstream.calls, 0)
            self.assertEqual(cache.stats.hits, 1)

    def test_larger_requested_count_refreshes_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            upstream = FakeWeb()
            provider = CachedWebSearchProvider(
                upstream,
                PersistentSearchCache(db),
            )
            provider.search_web("empresa x", count=3)
            provider.search_web("empresa x", count=6)
            self.assertEqual(upstream.calls, 2)

    def test_force_refresh_bypasses_existing_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "leadflow.db")
            upstream = FakeWeb()
            base_cache = PersistentSearchCache(db)
            CachedWebSearchProvider(upstream, base_cache).search_web("empresa x", count=3)

            refreshed = CachedWebSearchProvider(
                upstream,
                PersistentSearchCache(db),
                force_refresh=True,
            )
            refreshed.search_web("empresa x", count=3)
            self.assertEqual(upstream.calls, 2)


if __name__ == "__main__":
    unittest.main()
