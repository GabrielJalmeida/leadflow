from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .dedupe import lead_key
from .models import Lead, ResearchReport


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    segment TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT,
    country TEXT,
    requested_limit INTEGER NOT NULL,
    result_count INTEGER NOT NULL,
    planner TEXT NOT NULL,
    queries_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
    lead_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    country TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    address TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    source_provider TEXT,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS run_leads (
    run_id INTEGER NOT NULL,
    lead_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (run_id, lead_key),
    FOREIGN KEY (run_id) REFERENCES research_runs(id),
    FOREIGN KEY (lead_key) REFERENCES leads(lead_key)
);
"""


class LeadStore:
    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def save_report(self, report: ResearchReport) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO research_runs (
                started_at, finished_at, segment, city, state, country,
                requested_limit, result_count, planner, queries_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.started_at, report.finished_at, report.goal.segment,
                report.goal.city, report.goal.state, report.goal.country,
                report.goal.limit, len(report.leads), report.plan.generated_by,
                json.dumps(report.queries_executed, ensure_ascii=False),
            ),
        )
        run_id = int(cur.lastrowid)
        for position, lead in enumerate(report.leads, start=1):
            key = lead_key(lead)
            payload = json.dumps(lead.to_dict(), ensure_ascii=False)
            self.conn.execute(
                """
                INSERT INTO leads (
                    lead_key, name, city, state, country, phone, email,
                    website, address, score, source_provider, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lead_key) DO UPDATE SET
                    name=excluded.name,
                    city=excluded.city,
                    state=excluded.state,
                    country=excluded.country,
                    phone=COALESCE(excluded.phone, leads.phone),
                    email=COALESCE(excluded.email, leads.email),
                    website=COALESCE(excluded.website, leads.website),
                    address=COALESCE(excluded.address, leads.address),
                    score=excluded.score,
                    source_provider=excluded.source_provider,
                    payload_json=excluded.payload_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    key, lead.name, lead.city, lead.state, lead.country, lead.phone,
                    lead.email, lead.website, lead.address, lead.score,
                    lead.source_provider, payload,
                ),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO run_leads (run_id, lead_key, position) VALUES (?, ?, ?)",
                (run_id, key, position),
            )
        self.conn.commit()
        return run_id

    def count_leads(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM leads").fetchone()
        return int(row[0]) if row else 0
