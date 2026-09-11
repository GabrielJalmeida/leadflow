from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from .models import ResearchReport


def _slug(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "research"


def export_report(report: ResearchReport, output_dir: str = "output") -> tuple[Path, Path]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{_slug(report.goal.segment)}-{_slug(report.goal.city)}-{_slug(report.goal.state)}-{stamp}"
    json_path = folder / f"{base}.json"
    csv_path = folder / f"{base}.csv"

    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "score", "confidence_score", "name", "phone", "email", "website", "website_status",
                "website_audit_score", "website_http_status", "website_https", "website_response_ms",
                "website_findings", "socials", "address",
                "city", "state", "categories", "rating", "review_count", "source_provider",
                "discovered_query", "score_reasons",
            ],
        )
        writer.writeheader()
        for lead in report.leads:
            writer.writerow(
                {
                    "score": lead.score,
                    "confidence_score": lead.confidence_score,
                    "name": lead.name,
                    "phone": lead.phone or "",
                    "email": lead.email or "",
                    "website": lead.website or "",
                    "website_status": lead.website_status.value,
                    "website_audit_score": lead.website_audit.technical_score if lead.website_audit else "",
                    "website_http_status": lead.website_audit.status_code if lead.website_audit and lead.website_audit.status_code is not None else "",
                    "website_https": lead.website_audit.uses_https if lead.website_audit else "",
                    "website_response_ms": lead.website_audit.response_time_ms if lead.website_audit and lead.website_audit.response_time_ms is not None else "",
                    "website_findings": " | ".join(lead.website_audit.findings) if lead.website_audit else "",
                    "socials": " | ".join(lead.socials),
                    "address": lead.address or "",
                    "city": lead.city,
                    "state": lead.state,
                    "categories": " | ".join(lead.categories),
                    "rating": lead.rating if lead.rating is not None else "",
                    "review_count": lead.review_count if lead.review_count is not None else "",
                    "source_provider": lead.source_provider,
                    "discovered_query": lead.discovered_query,
                    "score_reasons": " | ".join(lead.score_reasons),
                }
            )
    return csv_path, json_path
