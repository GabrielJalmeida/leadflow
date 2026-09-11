
## [Unreleased] — Phase 5 Opportunity Intelligence

- Replaces the old "no website = best lead" heuristic with an explainable opportunity engine.
- Adds opportunity types: `new_site`, `rebuild`, `redesign`, `optimization`, `review_needed`.
- Separates service need, contactability, activity, website health and evidence confidence.
- Adds an actionability gate: unverified identity/site associations cannot outrank verified commercial opportunities.
- Treats a 100/100 technical website audit as a healthy technical baseline, not proof of good visual design or positioning.
- Persists opportunity type/actionability/service fit to SQLite and exports the components to CSV/JSON.
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

## v0.1.4-dev — Phase 6A: Browser & UX Intelligence

- Added an optional Playwright/Chromium browser audit for websites already associated with leads.
- Keeps browser UX separate from static technical health and future visual/aesthetic scoring.
- Measures mobile horizontal overflow, visible above-the-fold contact CTAs, navigation links, console errors and page errors.
- Captures desktop and mobile full-page screenshots for later human/AI visual review.
- Reuses browser audits from lead memory for 7 days by default and persists `browser_ux_score` in SQLite/JSON/CSV.
- Adds SSRF-oriented request routing so browser requests to localhost/private/non-public addresses are aborted.
- Browser UX can upgrade a technically healthy website into `REDESIGN` or `OPTIMIZATION` when objective mobile/conversion friction is detected.
- Playwright remains an optional dependency; normal discovery/investigation/HTTP audit still works without it.

## 0.1.4-dev — Phase 6B Visual Intelligence

- Added optional Gemini multimodal visual review over desktop/mobile browser screenshots.
- Added separate visual quality dimensions: overall, desktop, mobile, modernity, hierarchy, brand coherence, readability and conversion clarity.
- Added explicit visual-confidence gating; low-confidence AI review cannot drive opportunity scoring.
- Added persistent visual-audit memory (14-day default) and SQLite/CSV/JSON fields.
- Opportunity Intelligence can now identify redesign opportunities even when technical/browser checks are healthy.
- Visual analysis never changes business identity or technical audit facts.

## v0.1.4-dev — Phase 7: Search Profiles & Filters

- Added curated segment presets while preserving unrestricted free-text segment search.
- Added reusable search profiles (`balanced`, `website-sales`, `new-site`, `redesign`, `visual-redesign`, `ready-only`, `instagram-first`, `phone-first`).
- Added post-qualification filters for website state, Instagram, phone, email, readiness, opportunity type and audit thresholds.
- Added a bounded candidate-pool multiplier so filtered searches can inspect more candidates without silently becoming unbounded.
- Added `segments` and `profiles` CLI discovery commands.
