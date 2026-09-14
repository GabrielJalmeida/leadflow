from __future__ import annotations

from typing import Any

from .models import Lead, ResearchReport
from .dedupe import lead_key

FRONTEND_CONTRACT_VERSION = "1.0"


def lead_card_contract(lead: Lead) -> dict[str, Any]:
    """Stable minimum payload the first frontend can rely on.

    Rich internal/persisted Lead payloads may evolve. The UI should depend on
    this smaller versioned contract instead of directly coupling to every
    dataclass field.
    """

    opportunity = lead.opportunity
    return {
        "lead_key": lead_key(lead),
        "name": lead.name,
        "location": {"city": lead.city, "state": lead.state, "country": lead.country},
        "contact": {
            "phone": lead.phone,
            "email": lead.email,
            "socials": list(lead.socials),
        },
        "website": {
            "url": lead.website,
            "status": lead.website_status.value,
            "technical_score": lead.website_audit.technical_score if lead.website_audit else None,
            "browser_ux_score": lead.browser_audit.ux_score if lead.browser_audit else None,
            "visual_score": lead.visual_audit.overall_score if lead.visual_audit else None,
        },
        "identity": {
            "status": lead.identity_status.value,
            "confidence": round(float(lead.identity_confidence), 4),
        },
        "lifecycle": {"status": "new", "note": "", "last_contacted_at": None},
        "opportunity": {
            "score": int(lead.score),
            "type": opportunity.type.value if opportunity else "unknown",
            "actionable": bool(opportunity.actionable) if opportunity else False,
            "service_fit": opportunity.service_fit if opportunity else "unknown",
            "reasons": list(opportunity.reasons) if opportunity else [],
            "cautions": list(opportunity.cautions) if opportunity else [],
        },
    }


def research_contract(report: ResearchReport) -> dict[str, Any]:
    return {
        "contract_version": FRONTEND_CONTRACT_VERSION,
        "run": {
            "status": report.run_status,
            "stop_reason": report.run_stop_reason,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "requested_results": report.goal.limit,
            "returned_results": len(report.leads),
            "quota_fulfilled": len(report.leads) >= report.goal.limit,
            "shortfall": max(0, report.goal.limit - len(report.leads)),
            "discovery": {
                "queries_executed": len(report.queries_executed),
                "unique_candidates": report.discovery_unique_candidates,
                "prequalified_candidates": report.discovery_prequalified,
                "source_results_seen": report.local_results_seen,
                "duplicates_removed": report.duplicates_removed,
                "quality_rejected": report.quality_rejected,
            },
            "quality": {
                "filter_candidates_seen": report.filter_candidates_seen,
                "filter_rejected": report.filter_rejected,
                "filter_rejection_reasons": dict(report.filter_rejection_reasons),
                "errors": list(report.errors),
            },
            "usage": {
                "search_calls": report.usage_search_calls,
                "llm_calls": report.usage_llm_calls,
                "website_audits": report.usage_website_audits,
                "browser_audits": report.usage_browser_audits,
                "visual_audits": report.usage_visual_audits,
            },
        },
        "goal": {
            "segment": report.goal.segment,
            "city": report.goal.city,
            "state": report.goal.state,
            "country": report.goal.country,
        },
        "leads": [lead_card_contract(lead) for lead in report.leads],
    }
