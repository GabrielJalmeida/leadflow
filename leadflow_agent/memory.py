from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dedupe import normalize_phone, normalize_text
from .identity import normalize_domain
from .models import Evidence, Lead, RejectedCandidate, WebsiteStatus, lead_from_dict
from .validation import is_plausible_phone


@dataclass(slots=True)
class MemoryHydrationResult:
    matched: bool = False
    fields_restored: int = 0
    rejected_restored: int = 0
    evidence_restored: int = 0
    reason: str = ""


class LeadMemory:
    """Reuses previously verified lead knowledge without unsafe name-only joins.

    Persistent memory is intentionally stricter than normal entity resolution.
    A same-name/same-city record alone is not enough: at least one durable anchor
    (provider id/url, phone, domain, or social profile) must overlap before data
    is restored from an older run.
    """

    def __init__(self, db_path: str):
        self.path = Path(db_path)

    def hydrate(self, lead: Lead) -> MemoryHydrationResult:
        if not self.path.exists():
            return MemoryHydrationResult(reason="database does not exist yet")

        stored = self._find_strong_match(lead)
        if stored is None:
            return MemoryHydrationResult(reason="no strongly anchored previous lead")

        result = MemoryHydrationResult(matched=True, reason="strong identity anchor matched")

        # Rejected candidates are valuable negative knowledge. Keep only recent
        # items so a business rebrand/domain transfer is not rejected forever.
        cutoff_rejected = _utc_now() - timedelta(days=180)
        existing_rejected = {
            (item.target_field, _candidate_key(item.target_field, item.value))
            for item in lead.rejected_candidates
        }
        for item in stored.rejected_candidates:
            rejected_at = _parse_iso(item.rejected_at)
            if rejected_at is None or rejected_at < cutoff_rejected:
                continue
            key = (item.target_field, _candidate_key(item.target_field, item.value))
            if key in existing_rejected:
                continue
            lead.rejected_candidates.append(item)
            existing_rejected.add(key)
            result.rejected_restored += 1

        # Restore only fields with enough previous confidence. Current valid
        # observations always win over memory.
        if (
            not is_plausible_phone(lead.phone, country=lead.country)
            and is_plausible_phone(stored.phone, country=stored.country)
            and stored.field_confidence.get("phone", 0.0) >= 0.75
        ):
            lead.phone = stored.phone
            result.fields_restored += 1

        if not lead.email and stored.email and stored.field_confidence.get("email", 0.0) >= 0.75:
            lead.email = stored.email
            result.fields_restored += 1

        if not lead.address and stored.address and stored.field_confidence.get("address", 0.0) >= 0.75:
            lead.address = stored.address
            result.fields_restored += 1

        if not lead.website and stored.website and stored.website_status == WebsiteStatus.PRESENT:
            if stored.field_confidence.get("website", 0.0) >= 0.75:
                lead.website = stored.website
                lead.website_status = WebsiteStatus.PRESENT
                result.fields_restored += 1
        elif (
            not lead.website
            and lead.website_status == WebsiteStatus.UNKNOWN
            and stored.website_status == WebsiteStatus.NOT_FOUND
            and stored.field_confidence.get("website", 0.0) >= 0.60
            and _has_recent_not_found_evidence(stored, max_age_days=30)
        ):
            lead.website_status = WebsiteStatus.NOT_FOUND
            result.fields_restored += 1

        stored_social_conf = stored.field_confidence.get("socials", 0.0)
        if stored_social_conf >= 0.75:
            for social in stored.socials:
                if social not in lead.socials:
                    lead.socials.append(social)
                    result.fields_restored += 1

        for field_name, confidence in stored.field_confidence.items():
            lead.field_confidence[field_name] = max(
                lead.field_confidence.get(field_name, 0.0), confidence
            )

        if stored.identity_confidence > lead.identity_confidence:
            lead.identity_confidence = stored.identity_confidence
            lead.identity_status = stored.identity_status

        if (
            lead.website
            and stored.website
            and normalize_domain(lead.website) == normalize_domain(stored.website)
            and lead.website_audit is None
            and stored.website_audit is not None
            and _audit_is_recent(stored.website_audit.audited_at, max_age_days=7)
        ):
            lead.website_audit = stored.website_audit
            result.fields_restored += 1

        if (
            lead.website
            and stored.website
            and normalize_domain(lead.website) == normalize_domain(stored.website)
            and lead.browser_audit is None
            and stored.browser_audit is not None
            and _audit_is_recent(stored.browser_audit.audited_at, max_age_days=7)
        ):
            lead.browser_audit = stored.browser_audit
            result.fields_restored += 1

        # Persist only compact, conclusion-bearing evidence; raw search-result
        # evidence is already handled by the web-search cache.
        durable_kinds = {"verified_field", "website_not_found", "identity_assessment", "website_audit", "browser_audit"}
        existing_evidence = {
            (item.kind, item.target_field, item.url, item.detail)
            for item in lead.evidence
        }
        for item in stored.evidence:
            if item.kind not in durable_kinds:
                continue
            key = (item.kind, item.target_field, item.url, item.detail)
            if key in existing_evidence:
                continue
            lead.evidence.append(item)
            existing_evidence.add(key)
            result.evidence_restored += 1

        return result

    def _find_strong_match(self, lead: Lead) -> Lead | None:
        try:
            conn = sqlite3.connect(self.path, timeout=30)
        except sqlite3.Error:
            return None
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='leads'"
            ).fetchone()
            if table is None:
                return None
            rows = conn.execute(
                "SELECT payload_json FROM leads ORDER BY updated_at DESC LIMIT 5000"
            ).fetchall()
        except sqlite3.Error:
            return None
        finally:
            conn.close()

        target_name = normalize_text(lead.name)
        target_city = normalize_text(lead.city)
        target_state = normalize_text(lead.state)
        best: tuple[int, Lead] | None = None

        for row in rows:
            try:
                payload = json.loads(str(row[0]))
                candidate = lead_from_dict(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            if normalize_text(candidate.name) != target_name:
                continue
            if target_state and normalize_text(candidate.state) and normalize_text(candidate.state) != target_state:
                continue
            if target_city and normalize_text(candidate.city) and normalize_text(candidate.city) != target_city:
                continue

            strength = _anchor_strength(lead, candidate)
            if strength <= 0:
                continue
            if best is None or strength > best[0]:
                best = (strength, candidate)

        return best[1] if best else None


def _anchor_strength(current: Lead, stored: Lead) -> int:
    score = 0
    if current.provider_id and stored.provider_id and current.provider_id == stored.provider_id:
        score += 5

    if current.provider_url and stored.provider_url:
        if _normalize_url(current.provider_url) == _normalize_url(stored.provider_url):
            score += 4

    current_phone = normalize_phone(current.phone)
    stored_phone = normalize_phone(stored.phone)
    if current_phone and stored_phone and current_phone == stored_phone and len(current_phone) >= 10:
        score += 5

    current_domain = normalize_domain(current.website)
    stored_domain = normalize_domain(stored.website)
    if current_domain and stored_domain and current_domain == stored_domain:
        score += 5

    current_socials = {_normalize_url(value) for value in current.socials if value}
    stored_socials = {_normalize_url(value) for value in stored.socials if value}
    if current_socials & stored_socials:
        score += 4

    return score


def _candidate_key(target_field: str, value: str) -> str:
    if target_field == "website":
        return normalize_domain(value)
    return normalize_text(value)


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def _has_recent_not_found_evidence(lead: Lead, *, max_age_days: int) -> bool:
    cutoff = _utc_now() - timedelta(days=max_age_days)
    for item in lead.evidence:
        if item.kind != "website_not_found":
            continue
        observed = _parse_iso(item.observed_at)
        if observed is not None and observed >= cutoff:
            return True
    return False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _audit_is_recent(value: str, *, max_age_days: int) -> bool:
    observed = _parse_iso(value)
    if observed is None:
        return False
    return observed >= (_utc_now() - timedelta(days=max_age_days))
