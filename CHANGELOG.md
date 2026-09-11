# Changelog

## Unreleased — 0.1.4-dev

- Added explicit business identity states (`UNVERIFIED`, `MATCHED`, `PROBABLE_MATCH`, `AMBIGUOUS`, `MISMATCH`).
- Added conservative entity-resolution rules for phone, domain, name and locality.
- Added rejected-candidate memory so known-wrong website candidates are not repeatedly investigated.
- Website enrichment no longer assigns a domain from name similarity alone.
- Added SQLite migration fields for identity status/confidence.
- Added regression tests for same-name businesses in different cities/states.
- Added bounded `LeadInvestigator` service for per-lead contact/site/address research.
- Added `--investigate`, `--investigation-limit` and `--investigation-budget` CLI controls so extra provider cost is explicit.
- Added Gemini investigation extraction that preserves observed locality, including conflicting same-name businesses.
- Added conservative field merging: ambiguous candidates are not attached to leads.
- Added website `NOT_FOUND` transition only after dedicated bounded investigation with corroborated business identity.
- Added basic Brazilian phone-structure validation and replacement of obvious truncated numbers when stronger evidence exists.
- Added investigation metrics to reports (`investigated_leads`, `investigation_searches`).
- Added persistent SQLite web-search cache with TTL, refresh and disable controls.
- Added cache metrics so each run reports searches saved versus real provider calls.
- Added conservative persistent lead memory for verified fields and rejected candidates.
- Lead memory requires a durable identity anchor; same-name/same-city alone never hydrates data.
- Recent website `NOT_FOUND` evidence can be reused for 30 days; stale absence evidence returns to `UNKNOWN`.
- Rejected candidate memory expires after 180 days instead of becoming permanent truth.
- Investigator no longer spends contact searches solely because public email is missing.
- Resolved website state (`PRESENT` or recent `NOT_FOUND`) can now stop redundant investigation work.

## 0.1.3

- Added Tavily as the recommended BYOK discovery provider.
- Tavily key validation now uses `/usage`, avoiding a paid/search-credit validation query.
- Added web-evidence discovery mode to `LeadResearchAgent`.
- Added Gemini evidence-based lead extraction.
- A single Tavily result may now yield multiple explicitly named businesses.
- Directory/list pages are no longer incorrectly treated as one company in no-AI fallback mode.
- Tavily + Gemini is now preferred automatically when both keys are configured.
- Tavily can also perform optional per-lead web enrichment.
- Search output now says `Resultados-fonte vistos`, because Tavily results are evidence pages rather than local-business records.
- Outscraper and Brave remain optional adapters, but are no longer the recommended setup.

## 0.1.2

- Removed Gemini Google Maps/Search grounding from the core discovery path.
- Gemini became a planner/reasoning provider only.
- Default model changed to `gemini-3.1-flash-lite`.
- Added Outscraper and retained Brave as independent search providers.

## 0.1.1

- Gemini-first grounding experiment; retired as the default path after API-tier quota testing.

### v0.1.4-dev Phase 3.2 — Resilience & Quality Guardrails
- Gemini generation now retries transient 429/5xx failures with exponential backoff and jitter.
- HTTP errors expose structured status codes so retry policy is explicit instead of string-parsed.
- Deterministic fallback no longer promotes Instagram/TikTok/etc. posts or reels as businesses.
- Added a conservative lead quality gate to reject platform labels, marketing-copy titles, truncated titles, and directory pages masquerading as companies.
- Invalid Brazilian phone shapes are removed before dedupe/storage and again after memory hydration.
- Basic planner fallback now uses useful woodworking synonyms for `marcenaria` instead of low-value `empresa/profissional` suffixes.
- Research reports expose rejected-candidate and invalid-field counters.

## v0.1.4-dev — Phase 4: Website Verification & Audit Engine

- Added opt-in, local website auditing with `--audit-websites`.
- Audit does not consume Tavily/Gemini credits; it performs a bounded HTTP GET against the known website.
- Added SSRF-oriented safety guardrails: only public HTTP/HTTPS targets are allowed and every redirect is revalidated.
- Added objective static signals: HTTP status, HTTPS, redirect count, response time, title, meta description, viewport, forms and contact links (WhatsApp/tel/mailto).
- Added a conservative 0–100 technical readiness score; it is stored separately and does not yet change the commercial opportunity score.
- Added audit persistence in lead payloads and SQLite query columns, with 7-day memory reuse by default.
- Added `--audit-limit`, `--audit-timeout`, `--audit-ttl-days` and `--refresh-audits`.
- Added CSV/JSON audit fields and terminal summaries.
- Added unit coverage for public/private URL validation, unreachable sites, safety blocking, signal extraction and memory reuse.
