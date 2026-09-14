## Unreleased — Raw Discovery

- added explicit **Raw Discovery / Leads brutos** search mode;
- bypasses profile/final commercial filters;
- skips investigation and expensive website/browser/visual audits in raw mode;
- keeps sanitization, deduplication and existing-lead exclusion;
- added UI explanation and regression coverage.

## Unreleased — sales interaction history

- Added persistent `lead_interactions` history in SQLite.
- Added interaction timeline in the lead inspector.
- Added quick commercial outcomes: contact sent, responded, proposal sent and no interest.
- Interaction outcome can advance lifecycle stage while preserving the full lead record.
- Added API endpoints to list and create lead interactions.
- Database schema advanced to v7.
- Automated suite: **208 tests passing**.


## 0.2.0a1 — Sales Pipeline

- Added persistent sales lifecycle stages: awaiting response, responded, proposal sent, negotiating, won, and lost.
- Added Pipeline view for visualizing active commercial stages.
- Added lifecycle stage selector in the lead inspector.
- Contact queue automatically leaves the active queue once a lead reaches a post-contact sales stage.

## Unreleased — batch contact workflow

- Added multi-select in the lead results table.
- Added batch queue action for selected leads.
- Added batch contact opening for selected leads with WhatsApp URLs prefilled; sending remains manual.
- Added selection state and batch feedback to the React workspace.
## Phase 8.4.4 — Investigator Fast Path

- Batched bounded investigation evidence per lead so up to two search queries require one Gemini extraction call instead of one generation per query.
- Existing phone/e-mail/social contact now satisfies the contact-search need; Investigator no longer spends a query just to collect a second contact channel.
- Added quota-first early stop: once enough leads satisfy the final deterministic profile, the fixed investigation cap is not exhausted unnecessarily.
- Re-score immediately after investigation before choosing audit candidates.
- Filtered quota runs audit websites only after the business/site identity is `MATCHED` or `PROBABLE_MATCH`, avoiding wasted audits on unverified associations.
- Added `investigation_extractions` telemetry to reports, CLI and benchmark metrics.
- Local replay now estimates current investigation query/extraction cost from a captured `post_discovery` fixture.
- Status-less DNS/network `HTTPError`s are now treated as transient so provider circuit breakers can fail fast during outages.
- Latest real smoke snapshot estimates **9 searches / 5 batched investigation extractions** for the five selected candidates, compared with **9 legacy per-query extractions**.
- Automated suite: **199 tests passing**.


## Phase 8.4.4 — Fast Validation Loop

- Added replay snapshots at `post_discovery`, `post_investigation` and `post_audits`.
- Captures bounded investigation/website/browser/visual selection for diagnostics.
- Added deterministic local replay for scoring, filters, ranking and current investigation ordering with **0 provider calls / 0 LLM calls**.
- Added `--smoke` 3-lead validation mode; smoke runs cannot count toward the official quality gate.
- Added `run-phase844-smoke.bat` and `run-phase844-replay.bat`.
- Benchmark runs now export `replay_snapshot.json` beside `run.json`.
- Added regression coverage for replay serialization, selection priority and deterministic finalization.
- Automated suite: **191 tests passing**.

## Phase 8.4.4 — Benchmark stabilization patch 2

- Fixed investigation priority: candidates that already satisfy cheap contact-stage qualification are now investigated before candidates that would fail the final profile anyway.
- Fixed the same priority ordering for website/browser/visual audit candidate selection.
- Added aggregate final-filter rejection reasons to research reports and benchmark summaries so partial fulfillment can be diagnosed without guessing.
- Added regression coverage for the investigation-order bug found by the second real Marcenaria/Praia Grande benchmark.

## Unreleased

### Phase 8.4.4 — Real-World Quality Validation

- Added the dependency-free benchmark harness under `benchmarks/` and `scripts/run_benchmark.py`.
- Added the five official multi-segment benchmark cases and manual `review.csv` workflow.
- Added automatic fulfillment/discovery/usage metrics without auto-labeling real-world truth.
- Added manual quality summarization for precision, identity, phone, website attribution, duplicate/false-merge and contact usefulness.
- Benchmark result artifacts are local-only by default to avoid committing business contact data.
- Added benchmark validity guards so provider/network outages cannot be mistaken for product-quality regressions.
- Added `canonical_name_correct` review coverage to detect SEO/page titles returned as business names.
- Added `run-phase844-benchmark.bat` as a quota-aware Windows launcher for the first official benchmark case.
- Reviewed the first real `marcenaria — Praia Grande/SP — 10` diagnostic run: 10/10 fulfillment, 100% relevance, 90% identity precision, 100% phone plausibility, 0% duplicate rate and 70% overall row PASS rate.
- Fixed a false-opportunity defect where DNS/timeout/inconclusive website audits could be promoted to `REBUILD`; these now become `REVIEW_NEEDED` until a valid HTTP audit exists.
- Split operational hostname-resolution failure from SSRF/private-network blocking (`WebsiteResolutionError` vs `UnsafeWebsiteUrl`) and reduced confidence of inconclusive audit evidence.
- Added final-output website-audit validity metrics so a run with 2/2 inconclusive final website audits is rejected even if aggregate audit failures remain below 50%.
- Made discovery prequalification stage-aware: contact constraints still apply during discovery, while website/opportunity/readiness/audit filters wait for post-processing. Deferred filters use conservative overfetch so quota fulfillment is preserved.
- Expanded the regression suite to **185 passing tests**.


## Phase 8.2 — Local Application API

- Added a frontend-agnostic FastAPI local application layer bound to `127.0.0.1` by the CLI.
- Added asynchronous research runs with run IDs, status polling, result retrieval and real cancellation via the existing `RunController`.
- Added API catalogs for segments, profiles and provider capabilities.
- Added a shared `search_service` application layer so the proof-of-concept GUI and future frontend use the same research execution path.
- Extracted provider construction from the CLI into a reusable agent factory.
- Extracted contact routing/message preparation from Tkinter into a frontend-independent service module.
- Added local Host/Origin safeguards for the browser-facing API boundary.
- Added optional `api` dependencies instead of forcing FastAPI/Uvicorn onto CLI-only users.
- Added deterministic API and application-layer tests.
- No permanent frontend framework is selected in this phase; the UI stack will be chosen from the target visual/interaction references.

## Phase 8.1 — Contact Workspace v0

- Added one-click contact preparation to the functional GUI.
- WhatsApp click-to-chat links include an editable pre-filled message; the user still reviews and sends manually.
- Instagram is preferred over an unverified fixed-line phone when an Instagram profile is available.
- Brazilian mobile numbers are treated as WhatsApp candidates, not as verified WhatsApp accounts.
- Explicit `wa.me` / WhatsApp links have the highest contact-channel confidence.
- Facebook is intentionally excluded from the quick-contact route for now.
- Instagram contact opens the profile and copies the approved message to the clipboard.
- Added opportunity-aware default outreach drafts for new-site and redesign/rebuild/optimization leads.
- Added deterministic tests for channel resolution, phone normalization and WhatsApp message URLs.


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

## v0.1.4-dev — Phase 7.1: Runtime Safety & Provider Foundation

- Normal interactive/CLI research is now capped at 100 requested leads; larger volumes are reserved for a future resumable Bulk Research mode.
- Added a per-run hard `RunBudget` for real search calls, AI operations, HTTP audits, browser audits and visual audits.
- Added explicit run statuses and partial completion when a safety budget is exhausted instead of treating quota exhaustion as a crash.
- Added cancellation hooks so the future frontend can stop a running job between bounded operations.
- Added per-run provider usage counters to research reports and CLI output.
- Added per-provider transient-failure circuit breakers; repeated 408/429/5xx/timeouts stop further calls to an unhealthy provider during that run.
- Search-call accounting sits inside the persistent cache, so cache hits do not consume the external-search budget.
- Added provider capability metadata and a `providers` CLI command, keeping free/paid account choices separate from core business logic.
- Hardened Python packaging: explicit `leadflow_agent*` package discovery prevents runtime `data/`/`output/` folders from being mistaken for packages.
- Updated project license metadata to the current SPDX-string form.

## v0.1.4-dev — Phase 7.2: Core Hardening & Security Boundaries

- Added versioned frontend research contract (`contracts.py`).
- Added credential/token redaction and conservative user-input normalization.
- Centralized safe generated-artifact paths for exports and browser screenshots.
- Added stable public error taxonomy for provider/auth/rate-limit/runtime failures.
- Hardened Gemini web/screenshot prompts against instructions embedded in untrusted content.
- Added SQLite schema versioning and persisted run status/stop reason/usage counters.
- Added `docs/SECURITY.md` and `docs/FRONTEND_CONTRACT.md`.
- Added regression tests for security boundaries, frontend contract and legacy database migration.

## Phase 8.4.4 — Fast Capture Loop

- added `--capture-only` to the benchmark harness;
- added `run-phase844-capture.bat`;
- capture-only performs at most two discovery search calls;
- Gemini, Lead Investigator and all website/browser/visual audits are disabled;
- capture-only uses deterministic provider extraction and saves a replay snapshot;
- added `benchmarks/captures/` as a non-committed fixture workspace;
- clarified that smoke mode is now an integration test, not the normal debug loop.

## 0.2.0a1 — Sales workflow & AI workspace (14/09/2026)
- added persistent app settings for default contact message and AI prompt templates;
- added selectable AI destinations for text, image generation and site prototyping;
- changed the visual AI action to explicitly request generated images/concepts rather than prose-only ideation;
- added prototype-site prompt for external AI builders;
- expanded run diagnostics in the frontend for partial fulfillment and filter rejection causes;
- SQLite schema bumped to v5 for persistent app settings.

## UI polish — Configurações
- Reorganizada a tela de Configurações em um workspace de prompts.
- Variáveis com descrição breve e cópia com um clique.
- Seleção de IA visualmente separada por função.
- Barra de salvamento persistente e restauração por seção.
