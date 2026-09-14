from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .dedupe import lead_key
from .models import ResearchReport


DB_SCHEMA_VERSION = 7

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
    queries_json TEXT NOT NULL,
    run_status TEXT NOT NULL DEFAULT 'completed',
    stop_reason TEXT,
    usage_json TEXT NOT NULL DEFAULT '{}'
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
    lifecycle_status TEXT NOT NULL DEFAULT 'new',
    lifecycle_note TEXT NOT NULL DEFAULT '',
    last_contacted_at TEXT,
    follow_up_at TEXT,
    follow_up_note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contact_queue (
    lead_key TEXT PRIMARY KEY,
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'queued',
    message TEXT,
    last_action_at TEXT,
    FOREIGN KEY (lead_key) REFERENCES leads(lead_key)
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lead_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_key TEXT NOT NULL,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kind TEXT NOT NULL DEFAULT 'note',
    channel TEXT NOT NULL DEFAULT 'manual',
    outcome TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (lead_key) REFERENCES leads(lead_key)
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
        run_columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(research_runs)").fetchall()
        }
        if "run_status" not in run_columns:
            self.conn.execute("ALTER TABLE research_runs ADD COLUMN run_status TEXT NOT NULL DEFAULT 'completed'")
        if "stop_reason" not in run_columns:
            self.conn.execute("ALTER TABLE research_runs ADD COLUMN stop_reason TEXT")
        if "usage_json" not in run_columns:
            self.conn.execute("ALTER TABLE research_runs ADD COLUMN usage_json TEXT NOT NULL DEFAULT '{}'")

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
        if "lifecycle_status" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'new'")
        if "lifecycle_note" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN lifecycle_note TEXT NOT NULL DEFAULT ''")
        if "last_contacted_at" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN last_contacted_at TEXT")
        if "follow_up_at" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN follow_up_at TEXT")
        if "follow_up_note" not in columns:
            self.conn.execute("ALTER TABLE leads ADD COLUMN follow_up_note TEXT NOT NULL DEFAULT ''")
        self.conn.execute("CREATE TABLE IF NOT EXISTS contact_queue (lead_key TEXT PRIMARY KEY, queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'queued', message TEXT, last_action_at TEXT, FOREIGN KEY (lead_key) REFERENCES leads(lead_key))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS lead_interactions (id INTEGER PRIMARY KEY AUTOINCREMENT, lead_key TEXT NOT NULL, occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, kind TEXT NOT NULL DEFAULT 'note', channel TEXT NOT NULL DEFAULT 'manual', outcome TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', FOREIGN KEY (lead_key) REFERENCES leads(lead_key))")
        self.conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def save_report(self, report: ResearchReport) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO research_runs (
                started_at, finished_at, segment, city, state, country,
                requested_limit, result_count, planner, queries_json,
                run_status, stop_reason, usage_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.started_at, report.finished_at, report.goal.segment,
                report.goal.city, report.goal.state, report.goal.country,
                report.goal.limit, len(report.leads), report.plan.generated_by,
                json.dumps(report.queries_executed, ensure_ascii=False),
                report.run_status, report.run_stop_reason,
                json.dumps({
                    "search_calls": report.usage_search_calls,
                    "llm_calls": report.usage_llm_calls,
                    "website_audits": report.usage_website_audits,
                    "browser_audits": report.usage_browser_audits,
                    "visual_audits": report.usage_visual_audits,
                }, ensure_ascii=False),
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
                    score, source_provider, lifecycle_status, lifecycle_note, last_contacted_at, follow_up_at, follow_up_note, payload_json
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    lifecycle_status=leads.lifecycle_status,
                    lifecycle_note=leads.lifecycle_note,
                    last_contacted_at=leads.last_contacted_at,
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
                    lead.score, lead.source_provider, "new", "", None, None, "", payload,
                ),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO run_leads (run_id, lead_key, position) VALUES (?, ?, ?)",
                (run_id, key, position),
            )
        self.conn.commit()
        return run_id

    def existing_lead_keys(self) -> set[str]:
        rows = self.conn.execute("SELECT lead_key FROM leads").fetchall()
        return {str(row[0]) for row in rows}

    def list_leads(self, status: str = "all") -> list[dict]:
        where = "" if status == "all" else " WHERE lifecycle_status = ?"
        args = () if status == "all" else (status,)
        rows = self.conn.execute(
            "SELECT lead_key, payload_json, lifecycle_status, lifecycle_note, last_contacted_at, follow_up_at, follow_up_note, updated_at FROM leads" + where + " ORDER BY score DESC, updated_at DESC",
            args,
        ).fetchall()
        result=[]
        for lead_key_value, payload_json, lifecycle_status, note, last_contacted_at, follow_up_at, follow_up_note, updated_at in rows:
            payload=json.loads(payload_json)
            opportunity=payload.get("opportunity") or {}
            website=payload.get("website_audit") or {}
            browser=payload.get("browser_audit") or {}
            visual=payload.get("visual_audit") or {}
            result.append({
                "lead_key": lead_key_value,
                "name": payload.get("name", ""),
                "location": {"city": payload.get("city", ""), "state": payload.get("state", ""), "country": payload.get("country", "")},
                "contact": {"phone": payload.get("phone"), "email": payload.get("email"), "socials": list(payload.get("socials") or [])},
                "website": {
                    "url": payload.get("website"),
                    "status": payload.get("website_status", "unknown"),
                    "technical_score": website.get("technical_score"),
                    "browser_ux_score": browser.get("ux_score"),
                    "visual_score": visual.get("overall_score"),
                },
                "identity": {"status": payload.get("identity_status", "unverified"), "confidence": payload.get("identity_confidence", 0)},
                "opportunity": {
                    "score": payload.get("score", 0),
                    "type": opportunity.get("type", "unknown"),
                    "actionable": bool(opportunity.get("actionable", False)),
                    "service_fit": opportunity.get("service_fit", "unknown"),
                    "reasons": list(opportunity.get("reasons") or []),
                    "cautions": list(opportunity.get("cautions") or []),
                },
                "lifecycle": {"status": lifecycle_status, "note": note, "last_contacted_at": last_contacted_at, "follow_up_at": follow_up_at, "follow_up_note": follow_up_note, "updated_at": updated_at},
            })
        return result

    def update_lifecycle(self, lead_key_value: str, status: str, note: str = "") -> bool:
        allowed={"new","queued","contacted","accepted","ignored","hidden","awaiting_response","responded","proposal_sent","negotiating","won","lost"}
        if status not in allowed:
            raise ValueError(f"status de lifecycle inválido: {status}")
        now=None
        if status == "contacted":
            from .models import utc_now_iso
            now=utc_now_iso()
        cur=self.conn.execute(
            "UPDATE leads SET lifecycle_status=?, lifecycle_note=?, last_contacted_at=COALESCE(?, last_contacted_at), updated_at=CURRENT_TIMESTAMP WHERE lead_key=?",
            (status, note[:2000], now, lead_key_value),
        )
        if status != "queued":
            self.conn.execute("UPDATE contact_queue SET status=?, last_action_at=CURRENT_TIMESTAMP WHERE lead_key=?", ("done" if status in {"contacted","awaiting_response","responded","proposal_sent","negotiating","won","lost"} else status, lead_key_value))
        self.conn.commit()
        return cur.rowcount > 0

    def enqueue_contact(self, lead_key_value: str, message: str | None = None) -> dict | None:
        row=self.conn.execute("SELECT lifecycle_status FROM leads WHERE lead_key=?", (lead_key_value,)).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "INSERT INTO contact_queue(lead_key,status,message) VALUES(?, 'queued', ?) ON CONFLICT(lead_key) DO UPDATE SET status='queued', message=COALESCE(excluded.message, contact_queue.message), last_action_at=CURRENT_TIMESTAMP",
            (lead_key_value, message),
        )
        self.conn.execute("UPDATE leads SET lifecycle_status='queued', updated_at=CURRENT_TIMESTAMP WHERE lead_key=?", (lead_key_value,))
        self.conn.commit()
        return self.queue_item(lead_key_value)

    def queue_item(self, lead_key_value: str) -> dict | None:
        row=self.conn.execute(
            "SELECT q.lead_key,q.queued_at,q.status,q.message,q.last_action_at,l.payload_json,l.lifecycle_status FROM contact_queue q JOIN leads l ON l.lead_key=q.lead_key WHERE q.lead_key=?",
            (lead_key_value,),
        ).fetchone()
        if row is None:
            return None
        payload=json.loads(row[5])
        payload["lead_key"]=row[0]
        payload["lifecycle"]={"status":row[6]}
        return {"lead_key":row[0],"queued_at":row[1],"status":row[2],"message":row[3],"last_action_at":row[4],"lead":payload}

    def list_queue(self) -> list[dict]:
        rows=self.conn.execute(
            "SELECT q.lead_key,q.queued_at,q.status,q.message,q.last_action_at,l.payload_json FROM contact_queue q JOIN leads l ON l.lead_key=q.lead_key WHERE q.status='queued' ORDER BY q.queued_at ASC"
        ).fetchall()
        result=[]
        for row in rows:
            payload=json.loads(row[5]); payload["lead_key"]=row[0]
            result.append({"lead_key":row[0],"queued_at":row[1],"status":row[2],"message":row[3],"last_action_at":row[4],"lead":payload})
        return result

    def get_app_settings(self, defaults: dict[str, object] | None = None) -> dict[str, object]:
        stored = {str(row[0]): json.loads(row[1]) for row in self.conn.execute("SELECT key, value_json FROM app_settings").fetchall()}
        result = dict(defaults or {})
        result.update(stored)
        return result

    def set_app_settings(self, values: dict[str, object]) -> dict[str, object]:
        for key, value in values.items():
            self.conn.execute(
                "INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP",
                (str(key), json.dumps(value, ensure_ascii=False)),
            )
        self.conn.commit()
        return self.get_app_settings()

    def schedule_follow_up(self, lead_key_value: str, follow_up_at: str, note: str = "") -> dict | None:
        cur = self.conn.execute(
            "UPDATE leads SET follow_up_at=?, follow_up_note=?, updated_at=CURRENT_TIMESTAMP WHERE lead_key=?",
            (follow_up_at, note[:2000], lead_key_value),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_lead(lead_key_value)

    def clear_follow_up(self, lead_key_value: str) -> bool:
        cur = self.conn.execute(
            "UPDATE leads SET follow_up_at=NULL, follow_up_note='', updated_at=CURRENT_TIMESTAMP WHERE lead_key=?",
            (lead_key_value,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def list_follow_ups(self, due_only: bool = False) -> list[dict]:
        where = "WHERE l.follow_up_at IS NOT NULL"
        params: tuple = ()
        if due_only:
            where += " AND l.follow_up_at <= CURRENT_TIMESTAMP"
        rows = self.conn.execute(
            f"SELECT l.lead_key,l.payload_json,l.follow_up_at,l.follow_up_note FROM leads l {where} ORDER BY l.follow_up_at ASC",
            params,
        ).fetchall()
        result=[]
        for row in rows:
            payload=json.loads(row[1]); payload["lead_key"]=row[0]
            payload.setdefault("lifecycle", {})
            payload["lifecycle"]["follow_up_at"] = row[2]
            payload["lifecycle"]["follow_up_note"] = row[3]
            result.append({"lead_key":row[0],"follow_up_at":row[2],"note":row[3],"lead":payload})
        return result


    def add_interaction(self, lead_key_value: str, *, kind: str = "note", channel: str = "manual", outcome: str = "", note: str = "", status: str | None = None) -> dict | None:
        if self.conn.execute("SELECT 1 FROM leads WHERE lead_key=?", (lead_key_value,)).fetchone() is None:
            return None
        from .models import utc_now_iso
        occurred_at = utc_now_iso()
        self.conn.execute(
            "INSERT INTO lead_interactions(lead_key,occurred_at,kind,channel,outcome,note) VALUES(?,?,?,?,?,?)",
            (lead_key_value, occurred_at, kind[:80], channel[:80], outcome[:120], note[:4000]),
        )
        if status:
            allowed={"new","queued","contacted","accepted","ignored","hidden","awaiting_response","responded","proposal_sent","negotiating","won","lost"}
            if status not in allowed:
                raise ValueError(f"status de lifecycle inválido: {status}")
            last_contacted = occurred_at if status == "contacted" else None
            self.conn.execute(
                "UPDATE leads SET lifecycle_status=?, lifecycle_note=?, last_contacted_at=COALESCE(?, last_contacted_at), updated_at=CURRENT_TIMESTAMP WHERE lead_key=?",
                (status, note[:2000], last_contacted, lead_key_value),
            )
            if status != "queued":
                self.conn.execute("UPDATE contact_queue SET status=?, last_action_at=CURRENT_TIMESTAMP WHERE lead_key=?", ("done" if status in {"contacted","awaiting_response","responded","proposal_sent","negotiating","won","lost"} else status, lead_key_value))
        self.conn.commit()
        return {"id": int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]), "lead_key": lead_key_value, "occurred_at": occurred_at, "kind": kind, "channel": channel, "outcome": outcome, "note": note, "lead": self.get_lead(lead_key_value)}

    def list_interactions(self, lead_key_value: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, occurred_at, kind, channel, outcome, note FROM lead_interactions WHERE lead_key=? ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (lead_key_value, max(1, min(int(limit), 200))),
        ).fetchall()
        return [{"id": int(row[0]), "lead_key": lead_key_value, "occurred_at": row[1], "kind": row[2], "channel": row[3], "outcome": row[4], "note": row[5]} for row in rows]

    def get_lead(self, lead_key_value: str) -> dict | None:
        rows = self.conn.execute("SELECT payload_json,lifecycle_status,follow_up_at,follow_up_note,last_contacted_at FROM leads WHERE lead_key=?", (lead_key_value,)).fetchone()
        if rows is None:
            return None
        payload=json.loads(rows[0]); payload["lead_key"]=lead_key_value
        payload["lifecycle"]={"status":rows[1],"follow_up_at":rows[2],"follow_up_note":rows[3],"last_contacted_at":rows[4]}
        return payload

    def count_leads(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM leads").fetchone()
        return int(row[0]) if row else 0
