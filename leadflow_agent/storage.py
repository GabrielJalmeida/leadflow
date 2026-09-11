from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .dedupe import lead_key
from .models import ResearchReport


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
    website_status TEXT NOT NULL DEFAULT 'unknown',
    identity_status TEXT NOT NULL DEFAULT 'unverified',
    identity_confidence REAL NOT NULL DEFAULT 0,
    address TEXT,
    confidence_score INTEGER NOT NULL DEFAULT 0,
    opportunity_type TEXT NOT NULL DEFAULT 'unknown',
    opportunity_actionable INTEGER NOT NULL DEFAULT 0,
    opportunity_service_fit TEXT NOT NULL DEFAULT 'unknown',
    website_audit_score INTEGER,
    website_last_audited_at TEXT,
    browser_ux_score INTEGER,
    browser_last_audited_at TEXT,
    visual_score INTEGER,
    visual_last_audited_at TEXT,
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
        self._migrate_existing_database()

    def _migrate_existing_database(self) -> None:
        """Small idempotent migration layer for v0.x SQLite databases."""
        columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(leads)").fetchall()
        }
        if "website_status" not in columns:
            self.conn.execute(
                "ALTER TABLE leads ADD COLUMN website_status TEXT NOT NULL DEFAULT 'unknown'"
            )
        if "identity_status" not in columns:
            self.conn.execute(
                "ALTER TABLE leads ADD COLUMN identity_status TEXT NOT NULL DEFAULT 'unverified'"
            )
        if "identity_confidence" not in columns:
            self.conn.execute(
                "ALTER TABLE leads ADD COLUMN identity_confidence REAL NOT NULL DEFAULT 0"
            )
        if "confidence_score" not in columns:
            self.conn.execute(
                "ALTER TABLE leads ADD COLUMN confidence_score INTEGER NOT NULL DEFAULT 0"
            )
        if "opportunity_type" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN opportunity_type TEXT NOT NULL DEFAULT 'unknown'")
        if "opportunity_actionable" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN opportunity_actionable INTEGER NOT NULL DEFAULT 0")
        if "opportunity_service_fit" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN opportunity_service_fit TEXT NOT NULL DEFAULT 'unknown'")
        if "website_audit_score" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN website_audit_score INTEGER")
        if "website_last_audited_at" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN website_last_audited_at TEXT")
        if "browser_ux_score" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN browser_ux_score INTEGER")
        if "browser_last_audited_at" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN browser_last_audited_at TEXT")
        if "visual_score" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN visual_score INTEGER")
        if "visual_last_audited_at" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN visual_last_audited_at TEXT")
        self.conn.commit()

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
                    website, website_status, identity_status, identity_confidence,
                    address, confidence_score, opportunity_type, opportunity_actionable,
                    opportunity_service_fit, website_audit_score, website_last_audited_at,
                    browser_ux_score, browser_last_audited_at, visual_score, visual_last_audited_at,
                    score, source_provider, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lead_key) DO UPDATE SET
                    name=excluded.name,
                    city=excluded.city,
                    state=excluded.state,
                    country=excluded.country,
                    phone=COALESCE(excluded.phone, leads.phone),
                    email=COALESCE(excluded.email, leads.email),
                    website=COALESCE(excluded.website, leads.website),
                    website_status=CASE
                        WHEN excluded.website IS NOT NULL THEN 'present'
                        WHEN leads.website_status = 'present' THEN leads.website_status
                        ELSE excluded.website_status
                    END,
                    identity_status=CASE
                        WHEN excluded.identity_confidence >= leads.identity_confidence THEN excluded.identity_status
                        ELSE leads.identity_status
                    END,
                    identity_confidence=MAX(excluded.identity_confidence, leads.identity_confidence),
                    address=COALESCE(excluded.address, leads.address),
                    confidence_score=MAX(excluded.confidence_score, leads.confidence_score),
                    opportunity_type=excluded.opportunity_type,
                    opportunity_actionable=excluded.opportunity_actionable,
                    opportunity_service_fit=excluded.opportunity_service_fit,
                    website_audit_score=COALESCE(excluded.website_audit_score, leads.website_audit_score),
                    website_last_audited_at=COALESCE(excluded.website_last_audited_at, leads.website_last_audited_at),
                    browser_ux_score=COALESCE(excluded.browser_ux_score, leads.browser_ux_score),
                    browser_last_audited_at=COALESCE(excluded.browser_last_audited_at, leads.browser_last_audited_at),
                    visual_score=COALESCE(excluded.visual_score, leads.visual_score),
                    visual_last_audited_at=COALESCE(excluded.visual_last_audited_at, leads.visual_last_audited_at),
                    score=excluded.score,
                    source_provider=excluded.source_provider,
                    payload_json=excluded.payload_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    key, lead.name, lead.city, lead.state, lead.country, lead.phone,
                    lead.email, lead.website, lead.website_status.value,
                    lead.identity_status.value, lead.identity_confidence, lead.address,
                    lead.confidence_score,
                    lead.opportunity.type.value if lead.opportunity else "unknown",
                    int(lead.opportunity.actionable) if lead.opportunity else 0,
                    lead.opportunity.service_fit if lead.opportunity else "unknown",
                    lead.website_audit.technical_score if lead.website_audit else None,
                    lead.website_audit.audited_at if lead.website_audit else None,
                    lead.browser_audit.ux_score if lead.browser_audit else None,
                    lead.browser_audit.audited_at if lead.browser_audit else None,
                    lead.visual_audit.overall_score if lead.visual_audit else None,
                    lead.visual_audit.analyzed_at if lead.visual_audit else None,
                    lead.score, lead.source_provider, payload,
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
