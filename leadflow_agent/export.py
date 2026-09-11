from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .models import ResearchReport
from .security import redact_text, safe_child_path, safe_slug


def export_report(report: ResearchReport, output_dir: str = "output") -> tuple[Path, Path]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{safe_slug(report.goal.segment, fallback='research')}-{safe_slug(report.goal.city, fallback='city')}-{safe_slug(report.goal.state, fallback='state')}-{stamp}"
    json_path = safe_child_path(folder, f"{base}.json")
    csv_path = safe_child_path(folder, f"{base}.csv")

    payload = report.to_dict()
    payload["errors"] = [redact_text(item) for item in payload.get("errors", [])]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "score", "confidence_score", "opportunity_type", "opportunity_actionable",
                "service_fit", "service_need_score", "contactability_score", "activity_score",
                "name", "phone", "email", "website", "website_status",
                "website_audit_score", "website_http_status", "website_https", "website_response_ms",
                "website_findings", "browser_ux_score", "mobile_overflow",
                "visible_contact_ctas", "console_errors", "page_errors", "browser_findings",
                "desktop_screenshot", "mobile_screenshot", "visual_score", "visual_confidence",
                "visual_modernity", "visual_hierarchy", "visual_brand_coherence",
                "visual_readability", "visual_conversion_clarity", "visual_strengths",
                "visual_weaknesses", "visual_summary", "socials", "address",
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
                    "opportunity_type": lead.opportunity.type.value if lead.opportunity else "",
                    "opportunity_actionable": lead.opportunity.actionable if lead.opportunity else "",
                    "service_fit": lead.opportunity.service_fit if lead.opportunity else "",
                    "service_need_score": lead.opportunity.service_need_score if lead.opportunity else "",
                    "contactability_score": lead.opportunity.contactability_score if lead.opportunity else "",
                    "activity_score": lead.opportunity.activity_score if lead.opportunity else "",
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
                    "browser_ux_score": lead.browser_audit.ux_score if lead.browser_audit else "",
                    "mobile_overflow": lead.browser_audit.mobile_overflow if lead.browser_audit else "",
                    "visible_contact_ctas": lead.browser_audit.visible_contact_cta_count if lead.browser_audit else "",
                    "console_errors": lead.browser_audit.console_error_count if lead.browser_audit else "",
                    "page_errors": lead.browser_audit.page_error_count if lead.browser_audit else "",
                    "browser_findings": " | ".join(lead.browser_audit.findings) if lead.browser_audit else "",
                    "desktop_screenshot": lead.browser_audit.desktop_screenshot if lead.browser_audit else "",
                    "mobile_screenshot": lead.browser_audit.mobile_screenshot if lead.browser_audit else "",
                    "visual_score": lead.visual_audit.overall_score if lead.visual_audit else "",
                    "visual_confidence": lead.visual_audit.confidence if lead.visual_audit else "",
                    "visual_modernity": lead.visual_audit.modernity_score if lead.visual_audit else "",
                    "visual_hierarchy": lead.visual_audit.hierarchy_score if lead.visual_audit else "",
                    "visual_brand_coherence": lead.visual_audit.brand_coherence_score if lead.visual_audit else "",
                    "visual_readability": lead.visual_audit.readability_score if lead.visual_audit else "",
                    "visual_conversion_clarity": lead.visual_audit.conversion_clarity_score if lead.visual_audit else "",
                    "visual_strengths": " | ".join(lead.visual_audit.strengths) if lead.visual_audit else "",
                    "visual_weaknesses": " | ".join(lead.visual_audit.weaknesses) if lead.visual_audit else "",
                    "visual_summary": lead.visual_audit.summary if lead.visual_audit else "",
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
