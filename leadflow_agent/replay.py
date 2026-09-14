from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from .filters import LeadFilterSpec, Presence, Readiness, assess_filter
from .models import Lead, OpportunityType, SearchGoal, WebsiteStatus, lead_from_dict
from .scoring import score_lead
from .services.investigator import build_investigation_queries

REPLAY_SNAPSHOT_VERSION = 1


def serialize_filter_spec(spec: LeadFilterSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    return {
        "website_states": sorted(item.value for item in spec.website_states),
        "instagram": spec.instagram.value,
        "phone": spec.phone.value,
        "email": spec.email.value,
        "readiness": spec.readiness.value,
        "opportunity_types": sorted(item.value for item in spec.opportunity_types),
        "min_opportunity_score": spec.min_opportunity_score,
        "max_technical_score": spec.max_technical_score,
        "max_browser_score": spec.max_browser_score,
        "max_visual_score": spec.max_visual_score,
        "min_visual_confidence": spec.min_visual_confidence,
        "require_any_contact": spec.require_any_contact,
    }


def deserialize_filter_spec(data: dict[str, Any] | None) -> LeadFilterSpec | None:
    if not data:
        return None
    return LeadFilterSpec(
        website_states={WebsiteStatus(value) for value in data.get("website_states") or []},
        instagram=Presence(data.get("instagram", Presence.ANY.value)),
        phone=Presence(data.get("phone", Presence.ANY.value)),
        email=Presence(data.get("email", Presence.ANY.value)),
        readiness=Readiness(data.get("readiness", Readiness.ANY.value)),
        opportunity_types={OpportunityType(value) for value in data.get("opportunity_types") or []},
        min_opportunity_score=data.get("min_opportunity_score"),
        max_technical_score=data.get("max_technical_score"),
        max_browser_score=data.get("max_browser_score"),
        max_visual_score=data.get("max_visual_score"),
        min_visual_confidence=float(data.get("min_visual_confidence", 0.55)),
        require_any_contact=bool(data.get("require_any_contact", False)),
    )


def snapshot_leads(leads: Iterable[Lead]) -> list[dict[str, Any]]:
    return [lead.to_dict() for lead in leads]


def build_replay_snapshot(
    goal: SearchGoal,
    lead_filter: LeadFilterSpec | None,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": REPLAY_SNAPSHOT_VERSION,
        "goal": asdict(goal),
        "lead_filter": serialize_filter_spec(lead_filter),
        "settings": dict(settings or {}),
        "stages": {},
        "selections": {},
    }


def capture_stage(snapshot: dict[str, Any] | None, stage: str, leads: Iterable[Lead]) -> None:
    if snapshot is None:
        return
    snapshot.setdefault("stages", {})[stage] = snapshot_leads(leads)


def capture_selection(snapshot: dict[str, Any] | None, name: str, leads: Iterable[Lead]) -> None:
    if snapshot is None:
        return
    snapshot.setdefault("selections", {})[name] = [
        {
            "name": lead.name,
            "phone": lead.phone,
            "website": lead.website,
            "source_provider": lead.source_provider,
            "provider_id": lead.provider_id,
        }
        for lead in leads
    ]


def preliminary_filter_spec(lead_filter: LeadFilterSpec | None) -> LeadFilterSpec | None:
    if lead_filter is None or not lead_filter.active:
        return lead_filter
    return LeadFilterSpec(
        instagram=lead_filter.instagram,
        phone=lead_filter.phone,
        email=lead_filter.email,
        require_any_contact=lead_filter.require_any_contact,
    )


def preliminary_accepts(lead: Lead, lead_filter: LeadFilterSpec | None) -> bool:
    spec = preliminary_filter_spec(lead_filter)
    if spec is None or not spec.active:
        return True
    return assess_filter(lead, spec).accepted


def order_for_investigation(leads: Iterable[Lead], lead_filter: LeadFilterSpec | None) -> list[Lead]:
    return sorted(
        list(leads),
        key=lambda item: (
            preliminary_accepts(item, lead_filter),
            item.score,
            item.confidence_score,
            bool(item.phone),
        ),
        reverse=True,
    )


def order_for_audit(leads: Iterable[Lead], lead_filter: LeadFilterSpec | None) -> list[Lead]:
    return sorted(
        list(leads),
        key=lambda item: (
            preliminary_accepts(item, lead_filter),
            item.identity_confidence,
            item.confidence_score,
            item.score,
        ),
        reverse=True,
    )


def replay_finalize(snapshot: dict[str, Any], *, stage: str = "post_audits") -> dict[str, Any]:
    """Re-run deterministic scoring/filtering/ranking with zero provider calls.

    This intentionally does not fake investigation or web audits. To validate
    selection policy, use ``post_discovery`` diagnostics. To validate changes to
    scoring, filters, ranking or opportunity rules, use ``post_audits``.
    """

    stages = snapshot.get("stages") or {}
    if stage not in stages:
        available = ", ".join(sorted(stages)) or "none"
        raise ValueError(f"Replay stage '{stage}' is unavailable; available: {available}")

    goal = SearchGoal(**dict(snapshot.get("goal") or {}))
    lead_filter = deserialize_filter_spec(snapshot.get("lead_filter"))
    leads = [lead_from_dict(item) for item in stages.get(stage) or []]

    for lead in leads:
        score_lead(lead, prefer_no_website=goal.prefer_no_website)

    rejected = 0
    rejection_reasons: dict[str, int] = {}
    if lead_filter is not None and lead_filter.active:
        accepted: list[Lead] = []
        for lead in leads:
            decision = assess_filter(lead, lead_filter)
            if decision.accepted:
                accepted.append(lead)
            else:
                rejected += 1
                for reason in decision.reasons:
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        leads = accepted

    leads.sort(
        key=lambda item: (
            bool(item.opportunity and item.opportunity.actionable),
            item.score,
            item.review_count if item.review_count is not None else -1,
            item.confidence_score,
            bool(item.phone),
        ),
        reverse=True,
    )
    final = leads[: goal.limit]

    post_discovery = [lead_from_dict(item) for item in stages.get("post_discovery") or []]
    for lead in post_discovery:
        score_lead(lead, prefer_no_website=goal.prefer_no_website)
    investigation_order = order_for_investigation(post_discovery, lead_filter)
    settings = snapshot.get("settings") or {}
    investigation_limit = int(settings.get("investigation_limit") or 0)
    investigation_budget = max(1, min(int(settings.get("investigation_budget") or 2), 3))
    selected_for_investigation = investigation_order[:investigation_limit]
    investigation_plan: list[dict[str, Any]] = []
    estimated_searches = 0
    estimated_batch_extractions = 0
    for lead in selected_for_investigation:
        queries = build_investigation_queries(lead, goal)[:investigation_budget]
        estimated_searches += len(queries)
        if queries:
            estimated_batch_extractions += 1
        investigation_plan.append({
            "name": lead.name,
            "searches": len(queries),
            "purposes": [purpose for _, purpose in queries],
            "queries": [query for query, _ in queries],
        })

    return {
        "replay_version": REPLAY_SNAPSHOT_VERSION,
        "stage": stage,
        "provider_calls": 0,
        "llm_calls": 0,
        "input_candidates": len(stages.get(stage) or []),
        "filter_rejected": rejected,
        "filter_rejection_reasons": rejection_reasons,
        "requested": goal.limit,
        "returned": len(final),
        "quota_fulfilled": len(final) >= goal.limit,
        "leads": [lead.to_dict() for lead in final],
        "investigation_order": [lead.name for lead in investigation_order],
        "investigation_selected": [lead.name for lead in selected_for_investigation],
        "investigation_plan": investigation_plan,
        "estimated_investigation_searches_max": estimated_searches,
        "estimated_investigation_extractions_batch_max": estimated_batch_extractions,
        "estimated_investigation_extractions_legacy_max": estimated_searches,
        "estimated_batch_extraction_savings_max": max(0, estimated_searches - estimated_batch_extractions),
    }
