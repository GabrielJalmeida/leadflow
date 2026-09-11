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
