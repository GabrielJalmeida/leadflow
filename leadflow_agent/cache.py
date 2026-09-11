from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator

from .models import WebHit
from .providers.base import WebSearchProvider


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_search_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    query TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    country TEXT NOT NULL,
    requested_count INTEGER NOT NULL,
    hits_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_web_search_cache_lookup
    ON web_search_cache(provider, normalized_query, country);
"""


@dataclass(slots=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0

    def delta(self, earlier: "CacheStats") -> "CacheStats":
        return CacheStats(
            hits=max(0, self.hits - earlier.hits),
            misses=max(0, self.misses - earlier.misses),
            writes=max(0, self.writes - earlier.writes),
        )


class PersistentSearchCache:
    """SQLite-backed cache for external web-search responses.

    The cache intentionally stores search evidence, not conclusions. Lead/entity
    conclusions live in the lead-memory layer and remain subject to identity
    resolution. This separation lets us save provider credits without making a
    stale search result become permanent truth.
    """

    def __init__(self, db_path: str, *, ttl_days: int = 14):
        self.path = Path(db_path)
        self.ttl_days = max(1, min(int(ttl_days), 90))
        self.stats = CacheStats()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a transactional SQLite connection and always close it.

        sqlite3.Connection's own context manager commits/rolls back but does
        *not* close the file handle. That leaks handles long enough for Windows
        to reject TemporaryDirectory cleanup with WinError 32.
        """
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(CACHE_SCHEMA)

    def get(
        self,
        *,
        provider: str,
        query: str,
        country: str,
        requested_count: int,
    ) -> list[WebHit] | None:
        key = _cache_key(provider, query, country)
        now = _utc_now()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT requested_count, hits_json, expires_at
                FROM web_search_cache
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                self.stats.misses += 1
                return None

            cached_count = int(row[0])
            expires_at = _parse_iso(str(row[2]))
            if expires_at is None or expires_at <= now or cached_count < requested_count:
                if expires_at is not None and expires_at <= now:
                    conn.execute("DELETE FROM web_search_cache WHERE cache_key = ?", (key,))
                self.stats.misses += 1
                return None

            try:
                raw_hits = json.loads(str(row[1]))
                hits = [
                    WebHit(
                        title=str(item.get("title") or ""),
                        url=str(item.get("url") or ""),
                        description=str(item.get("description") or ""),
                        query=str(item.get("query") or query),
                    )
                    for item in raw_hits
                    if isinstance(item, dict) and item.get("title") and item.get("url")
                ]
            except (TypeError, ValueError, json.JSONDecodeError):
                conn.execute("DELETE FROM web_search_cache WHERE cache_key = ?", (key,))
                self.stats.misses += 1
                return None

            conn.execute(
                """
                UPDATE web_search_cache
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE cache_key = ?
                """,
                (_iso(now), key),
            )
            self.stats.hits += 1
            return hits[:requested_count]

    def put(
        self,
        *,
        provider: str,
        query: str,
        country: str,
        requested_count: int,
        hits: list[WebHit],
    ) -> None:
        now = _utc_now()
        expires_at = now + timedelta(days=self.ttl_days)
        key = _cache_key(provider, query, country)
        payload = json.dumps(
            [
                {
                    "title": hit.title,
                    "url": hit.url,
                    "description": hit.description,
                    "query": hit.query,
                }
                for hit in hits
            ],
            ensure_ascii=False,
        )
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO web_search_cache (
                    cache_key, provider, query, normalized_query, country,
                    requested_count, hits_json, created_at, expires_at,
                    last_accessed_at, access_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    query=excluded.query,
                    requested_count=excluded.requested_count,
                    hits_json=excluded.hits_json,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    last_accessed_at=excluded.last_accessed_at
                """,
                (
                    key,
                    provider,
                    query,
                    _normalize_query(query),
                    country.upper(),
                    int(requested_count),
                    payload,
                    _iso(now),
                    _iso(expires_at),
                    _iso(now),
                ),
            )
        self.stats.writes += 1

    def prune_expired(self) -> int:
        now = _iso(_utc_now())
        with self._connection() as conn:
            cur = conn.execute("DELETE FROM web_search_cache WHERE expires_at <= ?", (now,))
            return int(cur.rowcount or 0)

    def snapshot(self) -> CacheStats:
        return CacheStats(self.stats.hits, self.stats.misses, self.stats.writes)


class CachedWebSearchProvider:
    """Decorator that makes any WebSearchProvider quota-aware via SQLite."""

    def __init__(
        self,
        provider: WebSearchProvider,
        cache: PersistentSearchCache,
        *,
        force_refresh: bool = False,
    ):
        self.provider = provider
        self.cache = cache
        self.force_refresh = bool(force_refresh)
        self.name = provider.name

    def search_web(self, query: str, *, country: str = "BR", count: int = 10) -> list[WebHit]:
        count = max(1, int(count))
        if not self.force_refresh:
            cached = self.cache.get(
                provider=self.provider.name,
                query=query,
                country=country,
                requested_count=count,
            )
            if cached is not None:
                return cached
        else:
            # A forced refresh is a deliberate provider call, so account for it
            # as a miss when reporting quota usage for this run.
            self.cache.stats.misses += 1

        hits = self.provider.search_web(query, country=country, count=count)
        self.cache.put(
            provider=self.provider.name,
            query=query,
            country=country,
            requested_count=count,
            hits=hits,
        )
        return hits

    def cache_snapshot(self) -> CacheStats:
        return self.cache.snapshot()

    def __getattr__(self, name: str):
        # Preserve optional provider capabilities (for example Tavily's
        # heuristic_leads) without making every wrapped provider appear to
        # implement them. This keeps hasattr() semantics correct.
        return getattr(self.provider, name)


def _normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def _cache_key(provider: str, query: str, country: str) -> str:
    raw = f"{provider.casefold()}|{country.upper()}|{_normalize_query(query)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
