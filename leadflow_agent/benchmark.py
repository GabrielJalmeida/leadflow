from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MANUAL_VALUES = {"", "PASS", "FAIL", "UNCERTAIN"}

REVIEW_FIELDS = [
    "benchmark_id",
    "run_id",
    "rank",
    "lead_name",
    "canonical_name_correct",
    "segment_match",
    "city_match",
    "state_match",
    "real_business",
    "identity_correct",
    "phone_present",
    "phone_kind",
    "phone_plausible",
    "instagram_correct",
    "website_status_predicted",
    "website_status_manual",
    "website_correctly_attributed",
    "opportunity_type_predicted",
    "opportunity_type_manual",
    "is_duplicate",
    "is_false_merge",
    "contact_route_useful",
    "evidence_sufficient",
    "final_grade",
    "notes",
    # Read-only context that makes manual review possible without reopening the
    # raw JSON for every row.
    "phone",
    "email",
    "website_url",
    "socials",
    "address",
    "lead_city",
    "lead_state",
    "identity_status_predicted",
    "identity_confidence",
    "confidence_score",
    "opportunity_score",
    "evidence_count",
    "source_urls",
]

MANUAL_CHECK_FIELDS = [
    "canonical_name_correct",
    "segment_match",
    "city_match",
    "state_match",
    "real_business",
    "identity_correct",
    "phone_present",
    "phone_plausible",
    "instagram_correct",
    "website_correctly_attributed",
    "is_duplicate",
    "is_false_merge",
    "contact_route_useful",
    "evidence_sufficient",
    "final_grade",
]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    id: str
    segment: str
    city: str
    state: str
    target: int = 10


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _load_minimal_yaml(text: str) -> list[dict[str, Any]]:
    """Parse the deliberately tiny YAML subset used by benchmarks/cases.yaml.

    Avoiding PyYAML keeps the benchmark harness dependency-free. Supported
    syntax is a top-level list of flat mappings with scalar values.
    """

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if stripped:
                if ":" not in stripped:
                    raise ValueError(f"Invalid benchmark YAML at line {line_number}")
                key, value = stripped.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue
        if current is None or ":" not in stripped:
            raise ValueError(f"Invalid benchmark YAML at line {line_number}")
        key, value = stripped.split(":", 1)
        current[key.strip()] = _parse_scalar(value)
    if current is not None:
        items.append(current)
    return items


def load_benchmark_cases(path: str | Path) -> list[BenchmarkCase]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        raw_items = json.loads(text)
    else:
        raw_items = _load_minimal_yaml(text)

    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_items, start=1):
        try:
            case = BenchmarkCase(
                id=str(item["id"]).strip(),
                segment=str(item["segment"]).strip(),
                city=str(item["city"]).strip(),
                state=str(item.get("state", "")).strip(),
                target=int(item.get("target", 10)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid benchmark case #{index}: {exc}") from exc
        if not case.id or not case.segment or not case.city:
            raise ValueError(f"Benchmark case #{index} has blank required fields")
        if case.id in seen_ids:
            raise ValueError(f"Duplicate benchmark id: {case.id}")
        if not 1 <= case.target <= 100:
            raise ValueError(f"Benchmark case {case.id} has invalid target: {case.target}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("No benchmark cases found")
    return cases


def _final_website_audit_summary(report: dict[str, Any]) -> tuple[int, int]:
    """Count inconclusive website audits attached to the final returned leads.

    Aggregate run error rate can hide a serious quality problem when only a few
    returned leads have websites. For opportunity classification, 2/2 failed
    final-site audits is much more important than 2/10 across the whole run.
    """

    total = 0
    inconclusive = 0
    for lead in report.get("leads") or []:
        audit = lead.get("website_audit") if isinstance(lead, dict) else None
        if not isinstance(audit, dict):
            continue
        total += 1
        if (
            bool(audit.get("blocked"))
            or audit.get("status_code") is None
            or not bool(audit.get("reachable"))
        ):
            inconclusive += 1
    return total, inconclusive


def _external_failure_summary(report: dict[str, Any]) -> tuple[int, list[str]]:
    errors = [str(item or "") for item in (report.get("errors") or [])]
    lowered = [item.casefold() for item in errors]
    markers = (
        "network error",
        "temporary failure in name resolution",
        "name or service not known",
        "connection refused",
        "connection reset",
        "timed out",
        "timeout",
        "provider unavailable",
        "authentication",
        "invalid api key",
        "quota exceeded",
        "rate limit",
        "http 429",
    )
    external_errors = sum(1 for item in lowered if any(marker in item for marker in markers))

    website_audits_run = int(report.get("website_audits_run") or 0)
    website_audits_reused = int(report.get("website_audits_reused") or 0)
    website_audit_errors = int(report.get("website_audit_errors") or 0)
    website_audit_total = website_audits_run + website_audits_reused

    reasons: list[str] = []
    if external_errors:
        reasons.append(f"{external_errors} external/provider/network errors recorded")
    if website_audit_total and website_audit_errors / website_audit_total >= 0.5:
        reasons.append(
            f"website audit failure rate is {website_audit_errors}/{website_audit_total} (>=50%)"
        )

    final_audit_total, final_audit_errors = _final_website_audit_summary(report)
    if final_audit_total and final_audit_errors / final_audit_total >= 0.5:
        reasons.append(
            "final-lead website audit inconclusive rate is "
            f"{final_audit_errors}/{final_audit_total} (>=50%)"
        )
    return external_errors, reasons


def automatic_metrics(report: dict[str, Any]) -> dict[str, Any]:
    requested = int(report.get("goal", {}).get("limit") or 0)
    leads = list(report.get("leads") or [])
    returned = len(leads)
    external_errors, validity_reasons = _external_failure_summary(report)
    website_audits_run = int(report.get("website_audits_run") or 0)
    website_audits_reused = int(report.get("website_audits_reused") or 0)
    website_audit_errors = int(report.get("website_audit_errors") or 0)
    website_audit_total = website_audits_run + website_audits_reused
    final_website_audits, final_website_audit_errors = _final_website_audit_summary(report)
    return {
        "requested": requested,
        "returned": returned,
        "quota_fulfilled": returned >= requested if requested else False,
        "fulfillment_at_n": round(returned / requested, 4) if requested else 0.0,
        "queries_executed": len(report.get("queries_executed") or []),
        "unique_candidates": int(report.get("discovery_unique_candidates") or 0),
        "prequalified_candidates": int(report.get("discovery_prequalified") or 0),
        "quality_rejected": int(report.get("quality_rejected") or 0),
        "invalid_fields_removed": int(report.get("invalid_fields_removed") or 0),
        "duplicates_removed": int(report.get("duplicates_removed") or 0),
        "investigated_leads": int(report.get("investigated_leads") or 0),
        "investigation_searches": int(report.get("investigation_searches") or 0),
        "investigation_extractions": int(report.get("investigation_extractions") or 0),
        "filter_candidates_seen": int(report.get("filter_candidates_seen") or 0),
        "filter_rejected": int(report.get("filter_rejected") or 0),
        "filter_rejection_reasons": dict(report.get("filter_rejection_reasons") or {}),
        "search_calls": int(report.get("usage_search_calls") or 0),
        "llm_calls": int(report.get("usage_llm_calls") or 0),
        "website_audits": int(report.get("usage_website_audits") or 0),
        "website_audits_run": website_audits_run,
        "website_audits_reused": website_audits_reused,
        "website_audit_errors": website_audit_errors,
        "website_audit_error_rate": (
            round(website_audit_errors / website_audit_total, 4)
            if website_audit_total
            else None
        ),
        "final_website_audits": final_website_audits,
        "final_website_audit_errors": final_website_audit_errors,
        "final_website_audit_error_rate": (
            round(final_website_audit_errors / final_website_audits, 4)
            if final_website_audits
            else None
        ),
        "browser_audits": int(report.get("usage_browser_audits") or 0),
        "browser_audit_errors": int(report.get("browser_audit_errors") or 0),
        "visual_audits": int(report.get("usage_visual_audits") or 0),
        "visual_audit_errors": int(report.get("visual_audit_errors") or 0),
        "cache_hits": int(report.get("search_cache_hits") or 0),
        "cache_misses": int(report.get("search_cache_misses") or 0),
        "cache_writes": int(report.get("search_cache_writes") or 0),
        "errors": len(report.get("errors") or []),
        "external_failure_errors": external_errors,
        "quality_gate_measurement_valid": not validity_reasons,
        "validity_reasons": validity_reasons,
        "stop_reason": report.get("run_stop_reason"),
        "run_status": report.get("run_status"),
    }


def _first_instagram(socials: Iterable[str]) -> str:
    for url in socials:
        if "instagram.com" in str(url).lower():
            return str(url)
    return ""


def _source_urls(lead: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for evidence in lead.get("evidence") or []:
        url = str(evidence.get("url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    provider_url = str(lead.get("provider_url") or "").strip()
    if provider_url and provider_url not in urls:
        urls.insert(0, provider_url)
    return urls


def build_review_rows(
    report: dict[str, Any],
    *,
    benchmark_id: str,
    run_id: str | int | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, lead in enumerate(report.get("leads") or [], start=1):
        socials = [str(item) for item in (lead.get("socials") or [])]
        opportunity = lead.get("opportunity") or {}
        evidence = lead.get("evidence") or []
        row = {field: "" for field in REVIEW_FIELDS}
        row.update(
            {
                "benchmark_id": benchmark_id,
                "run_id": "" if run_id is None else str(run_id),
                "rank": rank,
                "lead_name": lead.get("name") or "",
                "phone_kind": "",  # human checks mobile/fixed/other during review
                "website_status_predicted": lead.get("website_status") or "unknown",
                "opportunity_type_predicted": opportunity.get("type") or "unknown",
                "phone": lead.get("phone") or "",
                "email": lead.get("email") or "",
                "website_url": lead.get("website") or "",
                "socials": " | ".join(socials),
                "address": lead.get("address") or "",
                "lead_city": lead.get("city") or "",
                "lead_state": lead.get("state") or "",
                "identity_status_predicted": lead.get("identity_status") or "unverified",
                "identity_confidence": lead.get("identity_confidence") or 0,
                "confidence_score": lead.get("confidence_score") or 0,
                "opportunity_score": lead.get("score") or 0,
                "evidence_count": len(evidence),
                "source_urls": " | ".join(_source_urls(lead)),
            }
        )
        # A dedicated Instagram context field is not part of the original phase
        # schema; putting all socials above keeps the worksheet stable while
        # making the most common digital-first route visible.
        if _first_instagram(socials) and not row["socials"]:
            row["socials"] = _first_instagram(socials)
        rows.append(row)
    return rows


def write_review_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_review_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _status(value: Any) -> str:
    return str(value or "").strip().upper()


def validate_review_rows(rows: Iterable[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):  # CSV header is line 1
        for field in MANUAL_CHECK_FIELDS:
            value = _status(row.get(field))
            if value not in MANUAL_VALUES:
                errors.append(f"line {index}: {field}={value!r} is invalid")
    return errors


def _rate(pass_count: int, fail_count: int) -> float | None:
    denominator = pass_count + fail_count
    return round(pass_count / denominator, 4) if denominator else None


def summarize_manual_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = validate_review_rows(rows)
    if errors:
        raise ValueError("Invalid manual review values: " + "; ".join(errors[:8]))

    def counts(field: str) -> tuple[int, int, int]:
        values = [_status(row.get(field)) for row in rows]
        return values.count("PASS"), values.count("FAIL"), values.count("UNCERTAIN")

    relevance_pass = relevance_fail = relevance_uncertain = 0
    for row in rows:
        values = [_status(row.get(field)) for field in ("segment_match", "city_match", "state_match", "real_business")]
        if "FAIL" in values:
            relevance_fail += 1
        elif values and all(value == "PASS" for value in values):
            relevance_pass += 1
        else:
            relevance_uncertain += 1

    name_pass, name_fail, name_uncertain = counts("canonical_name_correct")
    identity_pass, identity_fail, identity_uncertain = counts("identity_correct")
    phone_pass, phone_fail, phone_uncertain = counts("phone_plausible")
    website_pass, website_fail, website_uncertain = counts("website_correctly_attributed")
    duplicate_pass, duplicate_fail, duplicate_uncertain = counts("is_duplicate")
    false_merge_pass, false_merge_fail, false_merge_uncertain = counts("is_false_merge")
    contact_pass, contact_fail, contact_uncertain = counts("contact_route_useful")
    evidence_pass, evidence_fail, evidence_uncertain = counts("evidence_sufficient")
    final_pass, final_fail, final_uncertain = counts("final_grade")

    return {
        "rows": len(rows),
        "reviewed_final": final_pass + final_fail + final_uncertain,
        "precision_at_n": _rate(relevance_pass, relevance_fail),
        "canonical_name_precision": _rate(name_pass, name_fail),
        "identity_precision": _rate(identity_pass, identity_fail),
        "phone_plausibility": _rate(phone_pass, phone_fail),
        "website_attribution_precision": _rate(website_pass, website_fail),
        "website_attribution_false_positive_rate": _rate(website_fail, website_pass),
        "duplicate_rate": _rate(duplicate_fail, duplicate_pass),
        "false_merge_rate": _rate(false_merge_fail, false_merge_pass),
        "contact_usefulness": _rate(contact_pass, contact_fail),
        "evidence_sufficiency": _rate(evidence_pass, evidence_fail),
        "overall_pass_rate": _rate(final_pass, final_fail),
        "uncertain": {
            "relevance": relevance_uncertain,
            "canonical_name": name_uncertain,
            "identity": identity_uncertain,
            "phone": phone_uncertain,
            "website_attribution": website_uncertain,
            "duplicate": duplicate_uncertain,
            "false_merge": false_merge_uncertain,
            "contact": contact_uncertain,
            "evidence": evidence_uncertain,
            "final": final_uncertain,
        },
    }


def write_metrics(path: str | Path, automatic: dict[str, Any], manual: dict[str, Any] | None = None) -> Path:
    path = Path(path)
    payload = {"automatic": automatic, "manual": manual}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _format_rate(value: Any) -> str:
    if value is None:
        return "not reviewed"
    return f"{float(value) * 100:.1f}%"


def write_summary(
    path: str | Path,
    *,
    case: BenchmarkCase | None,
    automatic: dict[str, Any],
    manual: dict[str, Any] | None = None,
) -> Path:
    path = Path(path)
    title = case.id if case else "review"
    lines = [
        f"# LeadFlow Benchmark — {title}",
        "",
        "## Automatic run metrics",
        "",
        f"- Requested: **{automatic.get('requested', 0)}**",
        f"- Returned: **{automatic.get('returned', 0)}**",
        f"- Fulfillment@N: **{_format_rate(automatic.get('fulfillment_at_n'))}**",
        f"- Quota fulfilled: **{automatic.get('quota_fulfilled', False)}**",
        f"- Queries executed: **{automatic.get('queries_executed', 0)}**",
        f"- Unique candidates: **{automatic.get('unique_candidates', 0)}**",
        f"- Prequalified candidates: **{automatic.get('prequalified_candidates', 0)}**",
        f"- Duplicates removed: **{automatic.get('duplicates_removed', 0)}**",
        f"- Filter rejected: **{automatic.get('filter_rejected', 0)}**",
        f"- Investigation searches: **{automatic.get('investigation_searches', 0)}**",
        f"- Investigation extraction calls: **{automatic.get('investigation_extractions', 0)}**",
        f"- Search calls: **{automatic.get('search_calls', 0)}**",
        f"- LLM calls: **{automatic.get('llm_calls', 0)}**",
        f"- Website audits: **{automatic.get('website_audits', 0)}**",
        f"- Website audit errors: **{automatic.get('website_audit_errors', 0)}**",
        f"- Final-lead website audits: **{automatic.get('final_website_audits', 0)}**",
        f"- Final-lead inconclusive audits: **{automatic.get('final_website_audit_errors', 0)}**",
        f"- Final-lead audit error rate: **{_format_rate(automatic.get('final_website_audit_error_rate'))}**",
        f"- External/provider/network errors: **{automatic.get('external_failure_errors', 0)}**",
        f"- Quality-gate measurement valid: **{automatic.get('quality_gate_measurement_valid', False)}**",
        f"- Stop reason: **{automatic.get('stop_reason') or 'none'}**",
        "",
    ]
    filter_reasons = automatic.get("filter_rejection_reasons") or {}
    if filter_reasons:
        lines.extend(["### Final-filter rejection reasons", ""])
        lines.extend(
            f"- `{reason}`: **{count}**"
            for reason, count in sorted(
                filter_reasons.items(), key=lambda item: (-int(item[1]), str(item[0]))
            )
        )
        lines.append("")

    validity_reasons = automatic.get("validity_reasons") or []
    if validity_reasons:
        lines.extend(["### Measurement validity warnings", ""])
        lines.extend(f"- {reason}" for reason in validity_reasons)
        lines.append("")
    lines.extend([
        "## Manual quality metrics",
        "",
    ])
    if manual is None:
        lines.extend(
            [
                "Manual review is still pending.",
                "",
                "Fill `review.csv` using PASS / FAIL / UNCERTAIN, then run:",
                "",
                "```bash",
                "python scripts/run_benchmark.py --summarize <path-to-review.csv>",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                f"- Precision@N: **{_format_rate(manual.get('precision_at_n'))}**",
                f"- Canonical-name precision: **{_format_rate(manual.get('canonical_name_precision'))}**",
                f"- Identity precision: **{_format_rate(manual.get('identity_precision'))}**",
                f"- Phone plausibility: **{_format_rate(manual.get('phone_plausibility'))}**",
                f"- Website attribution false-positive rate: **{_format_rate(manual.get('website_attribution_false_positive_rate'))}**",
                f"- Duplicate rate: **{_format_rate(manual.get('duplicate_rate'))}**",
                f"- False-merge rate: **{_format_rate(manual.get('false_merge_rate'))}**",
                f"- Contact usefulness: **{_format_rate(manual.get('contact_usefulness'))}**",
                f"- Evidence sufficiency: **{_format_rate(manual.get('evidence_sufficiency'))}**",
                f"- Overall PASS rate: **{_format_rate(manual.get('overall_pass_rate'))}**",
                "",
                f"Uncertain counts: `{json.dumps(manual.get('uncertain', {}), ensure_ascii=False)}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
