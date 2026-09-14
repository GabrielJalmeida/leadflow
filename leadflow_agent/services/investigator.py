from __future__ import annotations

from dataclasses import dataclass, field

from ..dedupe import normalize_phone
from ..enrichment import is_candidate_business_site, is_social
from ..identity import IdentityCandidate, assess_identity, is_rejected_candidate, record_rejected_candidate
from ..models import (
    Evidence,
    IdentityStatus,
    InvestigationCandidate,
    Lead,
    SearchGoal,
    WebHit,
    WebsiteStatus,
)
from ..providers.base import LeadInvestigationExtractorProvider, WebSearchProvider
from ..validation import is_plausible_phone


@dataclass(slots=True)
class InvestigationResult:
    lead: Lead
    searches_used: int = 0
    queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    accepted_candidates: int = 0
    rejected_candidates: int = 0
    ambiguous_candidates: int = 0
    extraction_calls: int = 0


class LeadInvestigator:
    """Investigate one discovered lead using a bounded number of web searches.

    The service is intentionally conservative: evidence is merged only when
    entity resolution says it is safe. Ambiguous same-name businesses remain
    unresolved instead of contaminating the lead.
    """

    def __init__(
        self,
        *,
        web_search: WebSearchProvider,
        extractor: LeadInvestigationExtractorProvider,
    ):
        self.web_search = web_search
        self.extractor = extractor

    def investigate(
        self,
        lead: Lead,
        goal: SearchGoal,
        *,
        max_searches: int = 2,
        results_per_search: int = 8,
    ) -> InvestigationResult:
        max_searches = max(1, min(int(max_searches), 3))
        results_per_search = max(3, min(int(results_per_search), 12))
        result = InvestigationResult(lead=lead)

        queries = build_investigation_queries(lead, goal)
        saw_safe_identity = False
        saw_ambiguous_website = False
        website_searches = 0
        search_batches: list[tuple[str, str, list[WebHit]]] = []

        # Search first, extract second. Gemini supports one batched extraction for
        # all bounded searches of the same lead, which prevents the old 1 LLM call
        # per query pattern. Providers without batch support keep the legacy path.
        for query, purpose in queries:
            if result.searches_used >= max_searches:
                break
            if _investigation_complete(lead, goal):
                break

            result.queries.append(query)
            result.searches_used += 1
            if purpose == "website":
                website_searches += 1

            try:
                hits = self.web_search.search_web(query, country="BR", count=results_per_search)
            except Exception as exc:
                result.errors.append(f"{purpose}: search failed: {exc}")
                continue

            for hit in hits:
                lead.evidence.append(
                    Evidence(
                        source=self.web_search.name,
                        kind="investigation_search",
                        url=hit.url,
                        detail=f"{purpose}: {hit.title}",
                    )
                )
            search_batches.append((query, purpose, hits))

        extracted_batches: list[list[InvestigationCandidate]] = []
        capability_source = getattr(self.extractor, "provider", self.extractor)
        supports_batch = hasattr(capability_source, "extract_investigation_candidates_batch")
        batch_extractor = (
            getattr(self.extractor, "extract_investigation_candidates_batch", None)
            if supports_batch
            else None
        )
        if search_batches and callable(batch_extractor):
            try:
                result.extraction_calls += 1
                candidates = batch_extractor(
                    search_batches,
                    lead,
                    goal,
                    max_candidates=20,
                )
                extracted_batches = [list(candidates)]
            except Exception as exc:
                # The batch provider already owns its retry policy. Falling back
                # to N extra LLM calls after a terminal batch failure would make
                # outages slower and more expensive, so keep the failure bounded.
                result.errors.append(f"batch extraction failed: {exc}")
        else:
            for query, purpose, hits in search_batches:
                try:
                    result.extraction_calls += 1
                    candidates = self.extractor.extract_investigation_candidates(
                        hits,
                        lead,
                        goal,
                        query=query,
                        purpose=purpose,
                        max_candidates=12,
                    )
                except Exception as exc:
                    result.errors.append(f"{purpose}: extraction failed: {exc}")
                    continue
                extracted_batches.append(list(candidates))

        for candidates in extracted_batches:
            for candidate in candidates:
                assessment = assess_identity(lead, _identity_candidate(candidate, goal))
                lead.evidence.append(
                    Evidence(
                        source=candidate.source or self.extractor.name,
                        kind="identity_assessment",
                        target_field="identity",
                        url=candidate.source_url,
                        confidence=assessment.confidence,
                        detail=(
                            f"{assessment.status.value}: "
                            + "; ".join(assessment.reasons)
                        ),
                    )
                )

                if assessment.status == IdentityStatus.MISMATCH:
                    result.rejected_candidates += 1
                    _remember_rejections(lead, candidate, assessment.confidence, assessment.reasons)
                    continue

                if not assessment.safe_to_merge:
                    result.ambiguous_candidates += 1
                    if candidate.website and is_candidate_business_site(candidate.website):
                        saw_ambiguous_website = True
                    continue

                saw_safe_identity = True
                result.accepted_candidates += 1
                _merge_verified_candidate(lead, candidate, assessment.status, assessment.confidence, goal)

        # NOT_FOUND means a dedicated investigation was performed and no
        # official website was identified. It does not mean "provably has no
        # website". Keep UNKNOWN whenever an unresolved website candidate exists.
        if (
            not lead.website
            and lead.website_status == WebsiteStatus.UNKNOWN
            and website_searches >= 1
            and result.searches_used >= 2
            and saw_safe_identity
            and not saw_ambiguous_website
        ):
            lead.website_status = WebsiteStatus.NOT_FOUND
            lead.field_confidence["website"] = max(
                lead.field_confidence.get("website", 0.0),
                0.68,
            )
            lead.evidence.append(
                Evidence(
                    source=self.web_search.name,
                    kind="website_not_found",
                    target_field="website",
                    confidence=0.68,
                    detail=(
                        "Dedicated investigation completed without identifying "
                        "an official website; this is not proof that none exists."
                    ),
                )
            )

        return result


def build_investigation_queries(lead: Lead, goal: SearchGoal) -> list[tuple[str, str]]:
    """Build deterministic, quota-aware queries in priority order."""

    if _investigation_complete(lead, goal):
        return []

    locality = " ".join(part for part in (goal.city, goal.state) if part).strip()
    base = f'"{lead.name}" "{locality}"'.strip()
    queries: list[tuple[str, str]] = []

    if not _has_useful_contact_route(lead, goal):
        queries.append((f"{base} telefone WhatsApp Instagram contato", "contact"))

    # A recent NOT_FOUND state can come from persistent memory and means a
    # dedicated website investigation already happened. UNKNOWN/UNREACHABLE
    # may be retried; PRESENT without a URL is inconsistent and should be fixed.
    if (
        lead.website_status in {WebsiteStatus.UNKNOWN, WebsiteStatus.UNREACHABLE}
        or (lead.website_status == WebsiteStatus.PRESENT and not lead.website)
    ):
        queries.append((f"{base} site oficial endereço contato", "website"))

    if not lead.address:
        queries.append((f"{base} endereço telefone", "identity"))

    # A known social handle is often a very strong disambiguator, but only add
    # it as a third/fallback query so the default budget of two searches stays
    # inexpensive.
    if lead.socials:
        handle = _social_handle(lead.socials[0])
        if handle:
            queries.append((f'"{handle}" "{locality}"', "social"))

    # Fully populated leads still deserve no extra API calls.
    return list(dict.fromkeys(queries))


def _identity_candidate(candidate: InvestigationCandidate, goal: SearchGoal) -> IdentityCandidate:
    return IdentityCandidate(
        name=candidate.name,
        city=candidate.city,
        state=candidate.state,
        phone=(candidate.phone if is_plausible_phone(candidate.phone, country=goal.country) else None),
        website=candidate.website,
        address=candidate.address,
        source=candidate.source,
    )


def _merge_verified_candidate(
    lead: Lead,
    candidate: InvestigationCandidate,
    identity_status: IdentityStatus,
    identity_confidence: float,
    goal: SearchGoal,
) -> None:
    lead.identity_status = _stronger_identity_status(lead.identity_status, identity_status)
    lead.identity_confidence = max(lead.identity_confidence, identity_confidence)

    field_confidence = max(0.0, min(candidate.confidence * identity_confidence, 1.0))

    if candidate.phone and is_plausible_phone(candidate.phone, country=goal.country):
        incoming_phone = normalize_phone(candidate.phone)
        current_phone = normalize_phone(lead.phone)
        current_is_plausible = is_plausible_phone(lead.phone, country=goal.country)
        if not current_is_plausible:
            lead.phone = candidate.phone
            _record_field_evidence(lead, candidate, "phone", field_confidence)
        elif incoming_phone and current_phone and incoming_phone == current_phone:
            lead.field_confidence["phone"] = max(
                lead.field_confidence.get("phone", 0.0), field_confidence
            )

    if candidate.email and not lead.email:
        lead.email = candidate.email
        _record_field_evidence(lead, candidate, "email", field_confidence)

    if candidate.address and not lead.address:
        lead.address = candidate.address
        _record_field_evidence(lead, candidate, "address", field_confidence)

    if candidate.website and is_candidate_business_site(candidate.website):
        if not is_rejected_candidate(lead, value=candidate.website, target_field="website"):
            if not lead.website:
                lead.website = candidate.website
                lead.website_status = WebsiteStatus.PRESENT
                _record_field_evidence(lead, candidate, "website", field_confidence)

    for social in candidate.socials:
        if not social or not is_social(social):
            continue
        if is_rejected_candidate(lead, value=social, target_field="socials"):
            continue
        if social not in lead.socials:
            lead.socials.append(social)
            _record_field_evidence(lead, candidate, "socials", field_confidence, value=social)


def _record_field_evidence(
    lead: Lead,
    candidate: InvestigationCandidate,
    target_field: str,
    confidence: float,
    *,
    value: str | None = None,
) -> None:
    lead.field_confidence[target_field] = max(
        lead.field_confidence.get(target_field, 0.0), confidence
    )
    lead.evidence.append(
        Evidence(
            source=candidate.source or "investigator",
            kind="verified_field",
            target_field=target_field,
            url=candidate.source_url,
            confidence=confidence,
            detail=value or getattr(candidate, target_field if target_field != "socials" else "source_title", None),
        )
    )


def _remember_rejections(
    lead: Lead,
    candidate: InvestigationCandidate,
    confidence: float,
    reasons: list[str],
) -> None:
    reason = "identity_mismatch: " + "; ".join(reasons)
    if candidate.website:
        record_rejected_candidate(
            lead,
            value=candidate.website,
            target_field="website",
            reason=reason,
            source=candidate.source,
            confidence=confidence,
            observed_name=candidate.name or None,
            observed_city=candidate.city or None,
            observed_state=candidate.state or None,
            observed_phone=candidate.phone,
        )
    for social in candidate.socials:
        record_rejected_candidate(
            lead,
            value=social,
            target_field="socials",
            reason=reason,
            source=candidate.source,
            confidence=confidence,
            observed_name=candidate.name or None,
            observed_city=candidate.city or None,
            observed_state=candidate.state or None,
            observed_phone=candidate.phone,
        )


def _stronger_identity_status(current: IdentityStatus, incoming: IdentityStatus) -> IdentityStatus:
    rank = {
        IdentityStatus.MISMATCH: 0,
        IdentityStatus.UNVERIFIED: 1,
        IdentityStatus.AMBIGUOUS: 2,
        IdentityStatus.PROBABLE_MATCH: 3,
        IdentityStatus.MATCHED: 4,
    }
    return incoming if rank[incoming] > rank[current] else current


def _has_useful_contact_route(lead: Lead, goal: SearchGoal) -> bool:
    # Investigation is for qualification, not profile completion. One usable
    # public channel is enough; do not spend a search just to collect a second
    # channel when phone/email/social already exists.
    return bool(
        is_plausible_phone(lead.phone, country=goal.country)
        or lead.email
        or lead.socials
    )


def _investigation_complete(lead: Lead, goal: SearchGoal) -> bool:
    # Email is intentionally not required: many small businesses have no public
    # email. Stop when the core outreach/identity fields are already strong.
    return bool(
        is_plausible_phone(lead.phone, country=goal.country)
        and lead.socials
        and lead.address
        and (
            (lead.website_status == WebsiteStatus.PRESENT and bool(lead.website))
            or lead.website_status == WebsiteStatus.NOT_FOUND
        )
    )


def _social_handle(url: str) -> str:
    value = url.rstrip("/").split("/")[-1]
    value = value.split("?", 1)[0].strip()
    return value if value and value not in {"instagram.com", "facebook.com"} else ""
