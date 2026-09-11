# LeadFlow Agent — Architecture v0.1.4-dev

## Core principle

LeadFlow is an evidence-driven business research agent, not a query against a single lead database.

The safety rule for enrichment is:

> **False association is worse than missing information.**

## Pipeline

```text
SearchGoal
  -> Query planning
  -> Discovery
  -> Entity extraction
  -> Deduplication
  -> Entity resolution
  -> Optional Lead Investigator
  -> Evidence confidence + opportunity scoring
  -> SQLite / CSV / JSON
```

## Components

### SearchGoal
Defines segment, location, target quantity and basic constraints.

### LLMProvider
Gemini Flash-Lite plans commercial search phrases. The agent retains a deterministic fallback when planning fails.

### WebSearchProvider
Tavily searches public web evidence. Results are pages/snippets, not automatically canonical businesses.

### LeadExtractorProvider
Gemini converts bounded discovery evidence into structured companies. A single directory result may yield several companies.

### Entity resolution
`identity.py` compares observed candidates against the reference lead. Strong signals include normalized phone/domain. Name + corroborated locality can produce a probable match. Same name with conflicting city/state produces a mismatch. Name alone is ambiguous.

Rejected website/social candidates are retained on the lead so later work can avoid repeating known-wrong associations.

### LeadInvestigator
`services/investigator.py` performs bounded per-lead research after discovery.

Its responsibilities are intentionally separate from discovery:

1. build deterministic, quota-aware searches;
2. collect web evidence;
3. ask the extractor for observed candidate identities;
4. run entity resolution;
5. merge only safely matched fields;
6. retain ambiguous/rejected evidence;
7. update website state and confidence.

Investigation is opt-in. The CLI exposes both the number of leads to investigate and the maximum web searches per lead. This prevents silent provider-credit consumption.

### Phone validation
`validation.py` provides cheap structural validation. Brazilian mobile/fixed-line shapes are checked before a number is considered usable by the Investigator. This is syntax/plausibility validation, not active-number verification.

### LeadResearchAgent
Owns orchestration:

1. plan discovery queries;
2. search evidence or structured local data;
3. extract business entities;
4. normalize/deduplicate;
5. continue until target quantity/query budget is exhausted;
6. optionally investigate a bounded set of leads;
7. re-score after investigation;
8. persist/export.

### LeadStore
SQLite persistence for research runs and unique entities. `payload_json` preserves richer evidence while normalized columns support common queries.

## Website semantics

- `UNKNOWN`: not investigated enough.
- `PRESENT`: official website identified with sufficient identity evidence.
- `NOT_FOUND`: a dedicated investigation was completed without identifying an official website. This is not proof of non-existence.
- `UNREACHABLE`: website identified but unavailable; deeper website auditing is a later milestone.

Only `NOT_FOUND` receives the strong no-site opportunity bonus.

## Evidence rules

- Search output is evidence, not truth by itself.
- Web text is treated as untrusted data in Gemini extraction prompts.
- Observed city/state must be preserved; they must never be overwritten with the desired search location during extraction.
- Missing data is preferable to attaching data from another company.
- Every accepted field should gain source evidence and field confidence.
- Known rejected candidates should not be accepted later without stronger contradictory evidence.

## Provider strategy

Provider-specific response shapes stop at adapters. BYOK configuration remains separate from business logic. Tavily is the current development baseline; Brave, local/business APIs and future providers can coexist.

## Cost strategy

Discovery and investigation have separate budgets. A normal discovery run does not automatically trigger per-lead research. A recommended development test investigates three leads with two searches each, placing an explicit upper bound of six extra web searches.

## Next milestones

1. run the Investigator against the real Praia Grande benchmark and inspect false positives/negatives;
2. improve name similarity/entity fingerprints based on real failures;
3. add persistent investigation cache so repeated runs can reuse evidence and rejected candidates;
4. add website reachability/quality audit;
5. only then freeze the backend API contract and build the frontend.

## Website Verification & Audit Engine

`services/website_auditor.py` is deliberately independent from discovery and entity resolution. It receives a website already attached to a lead and performs a bounded, static HTTP audit. It cannot increase identity confidence merely because a domain responds.

The fetcher manually handles redirects so every redirect target can be checked before access. Localhost, RFC1918/private, link-local, loopback, reserved and other non-global IP targets are blocked to reduce SSRF risk in the local desktop application. Audit results are persisted as part of the lead payload and can be reused from LeadMemory while fresh.


## Opportunity Intelligence

`WebsiteAuditor` produces technical facts. `opportunity.assess_opportunity()` converts verified facts into a commercial hypothesis without changing entity identity. The opportunity engine must never treat technical reachability as proof that a domain belongs to a lead.

Final ordering prefers actionable (`matched`/`probable_match`) opportunities before unverified ones. This is intentional: false association is considered worse than missing information. Visual quality is outside the HTTP audit and remains `REVIEW_NEEDED` until a visual/UX audit exists.

## Phase 6A — Browser / UX audit

Website intelligence is intentionally split into independent layers:

1. `WebsiteAuditor`: bounded HTTP/HTML technical facts.
2. `BrowserAuditor`: deterministic real-browser behaviour and screenshots.
3. Future `VisualIntelligenceProvider`: optional subjective/AI-assisted visual assessment.

This prevents `100/100 technical` from being interpreted as `100/100 design`. Browser UX may influence the opportunity type only for objective problems such as severe mobile overflow, missing contact paths or runtime errors. Visual aesthetics remain unresolved until a dedicated visual-review phase.

The browser dependency is optional and loaded lazily. Discovery, entity resolution, investigation, cache, memory and HTTP website auditing do not require Playwright.

## Visual Intelligence boundary

`VisualAuditor` consumes screenshots previously created by `BrowserAuditor` and delegates multimodal analysis to a provider (currently Gemini). It cannot mutate business identity, website ownership, HTTP/TLS facts or browser measurements.

The layer outputs `VisualAudit`, which is subjective and confidence-gated. `Opportunity Intelligence` may use the result only when confidence is sufficient. This keeps the product model explicit:

- Technical Health: protocol/HTML facts.
- Browser UX: deterministic browser behavior.
- Visual Quality: subjective multimodal review.
- Identity Confidence: whether the evidence belongs to the intended business.
- Opportunity Fit: commercial interpretation of the above for the selected sales goal.
