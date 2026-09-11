# LeadFlow Agent v0.1.4-dev

Open-source BYOK lead-research agent. This milestone replaces the assumption that a search result is already a business record.

## Core flow

```text
user goal
  -> Gemini Flash-Lite plans commercial search phrases
  -> Tavily searches the public web
  -> Gemini extracts zero, one, or many real businesses from each evidence set
  -> LeadFlow deduplicates, scores, exports and stores them in SQLite
```

A directory page can therefore produce multiple leads, while the directory itself is not treated as a lead.

## Identity safety

LeadFlow treats **false association as worse than missing data**. A business name alone is not enough to attach a website or merge identities. Same-name businesses in different cities/states are explicitly treated as different entities, while phone/domain matches provide much stronger identity evidence. Ambiguous website candidates remain unassigned until the Investigator can verify them.

## Why Tavily

Tavily is a web-search provider, not a business database. That matches LeadFlow's new architecture: search the same public evidence a person would inspect manually, then extract and verify business entities.

The default search depth is `basic` to control credit usage. Key validation uses Tavily's `/usage` endpoint and does not spend a search credit.

## Setup

```bat
python -m leadflow_agent setup
```

Recommended configuration:

- Gemini API key: your Google AI Studio key
- Gemini model: `gemini-3.1-flash-lite`
- Tavily API key: your Tavily key
- Brave / Outscraper: optional
- SQLite: press Enter for `leadflow.db`

Keys are stored only in the local `.env`, which is ignored by Git.

Then:

```bat
python -m leadflow_agent doctor
```

## First real search

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily
```

Or run:

```bat
test-praia-grande.bat
```

The search loop stops once enough unique leads have been accumulated or the planned query budget is exhausted.

## What Gemini does

Gemini is not used as a Maps/search provider in this version. It performs two bounded tasks:

1. plans useful search phrases and synonyms;
2. extracts business entities from Tavily evidence.

Extraction is evidence-only: it is instructed not to invent company names, contact data, URLs or addresses. Weak/ambiguous matches are dropped.

If Gemini is unavailable or rate-limited, Tavily has a conservative heuristic fallback for direct business/social results. Directory/list pages are deliberately skipped in this fallback because they require semantic extraction to avoid false leads.

## Lead Investigator

Discovery answers **which businesses exist**. The Investigator answers **which facts actually belong to each business**. It is opt-in because each investigated lead may spend additional search credits.

Recommended first test:

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily --investigate --investigation-limit 3 --investigation-budget 2
```

With that command the maximum extra search cost is explicit: `3 leads × 2 searches = 6` Tavily searches, in addition to discovery. The default investigation budget is capped at three searches per lead.

The Investigator:

1. searches contact/social evidence;
2. searches specifically for an official website/address;
3. asks Gemini to extract observed candidates without replacing observed locality with the requested city;
4. passes every candidate through entity resolution;
5. accepts only `MATCHED` / high-confidence `PROBABLE_MATCH` evidence;
6. remembers mismatches such as a same-name company in another state;
7. can mark `WebsiteStatus.NOT_FOUND` only after a bounded dedicated investigation.

`NOT_FOUND` means *LeadFlow investigated and did not identify an official website*. It is intentionally not a claim that no website can possibly exist.

### Phone hygiene

The Investigator applies structural phone validation before treating a number as usable. For Brazil it recognizes normal 10-digit fixed lines and 11-digit mobile numbers and rejects obvious truncated mobile-like values. This validation does **not** prove a number is active; active-number verification is a later concern.

### Legacy enrichment

`--enrich-web` is still available for compatibility, but the new `--investigate` path is the preferred architecture because it uses explicit identity resolution and a visible per-lead budget.

## Persistent research cache

LeadFlow now treats provider quota as a first-class engineering constraint. Web-search responses are cached in the same local SQLite database before another provider call is made. The default TTL is 14 days.

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily
```

Repeating the same search can reuse cached evidence instead of spending another Tavily search. The terminal reports:

- `Cache hits`: provider calls avoided;
- `Cache misses`: real web-search calls;
- `Entradas gravadas`: refreshed/new cache entries.

Controls:

```bat
--cache-ttl-days 14
--refresh-cache
--no-cache
```

`--refresh-cache` deliberately bypasses old entries and writes fresh results. `--no-cache` disables search caching entirely for the run.

## Persistent lead memory

Search-result caching and business memory are intentionally separate. Cached pages are only evidence; verified conclusions are restored from previous leads only when LeadFlow can establish a durable identity anchor such as the same provider URL/ID, phone, domain or social profile. **Same name + same city alone is not sufficient.**

The memory layer can reuse:

- previously verified phone/site/social/address fields;
- recent `WebsiteStatus.NOT_FOUND` conclusions (30-day freshness window);
- rejected website/social candidates for up to 180 days;
- compact identity/field evidence.

This lets a repeat run remember that a Curitiba website was already rejected for a Praia Grande company without turning a name collision into shared data. Use `--no-memory` when a completely fresh identity investigation is required.

A recent cached `NOT_FOUND` website state also prevents the Investigator from immediately spending another website search. Stale `NOT_FOUND` evidence returns to `UNKNOWN` and can be researched again.

## Runtime

The runtime still has no required third-party Python dependencies. HTTP, SQLite, CLI, JSON and CSV use the Python standard library.

## Outputs

Each run can produce:

- ranked terminal output;
- `output/*.csv`;
- `output/*.json`;
- accumulated local memory in `leadflow.db`.

## Security

Never commit `.env`. Never paste API keys into issues, screenshots, README files or chat logs.

## Website audit (Phase 4)

LeadFlow can now audit websites already associated with discovered leads without spending search or LLM credits:

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily --investigate --audit-websites --audit-limit 3
```

The lightweight local audit records objective signals such as HTTP status, HTTPS, redirects, response time, `<title>`, meta description, viewport, forms and WhatsApp/tel/mailto links. It intentionally does **not** treat a reachable domain as proof that the domain belongs to the business; identity resolution remains a separate responsibility.

Safety limits are built in: only public HTTP/HTTPS targets are allowed, local/private/link-local addresses are blocked, redirect targets are revalidated, the response body is capped, and each request has a timeout.

Useful options:

```text
--audit-limit 3        maximum websites audited in the run
--audit-timeout 8      per-site timeout (2–20 seconds)
--audit-ttl-days 7     reuse a recent saved audit
--refresh-audits       force a fresh HTTP audit
```

The current `technical_score` is a transparent static-readiness indicator, not an SEO/Lighthouse score and not yet part of the commercial Opportunity Score. A browser-based deep audit can be added later as an optional provider/service.

## Opportunity Intelligence (Phase 5)

LeadFlow no longer assumes that a business without a website is always the best prospect. After discovery, investigation and optional website audit, each lead receives an explainable opportunity assessment:

- `NEW_SITE` — a dedicated investigation found no official website.
- `REBUILD` — the associated website is unreachable or has severe technical failures.
- `REDESIGN` — the website works but has a weak technical baseline with clear modernization potential.
- `OPTIMIZATION` — the website has a reasonable base but still exposes technical/conversion gaps.
- `REVIEW_NEEDED` — more investigation is required, especially visual/design review.

The score is composed from **service need + contactability + business activity**, while confidence remains separate. A website-specific opportunity is marked `VERIFY` instead of `READY` until entity resolution reaches `matched` or `probable_match`.

Important: the HTTP/HTML website audit does **not** judge aesthetics. Even a `100/100` technical audit can still be a redesign opportunity; it simply needs a later visual/UX assessment.

## Browser / UX audit (Phase 6A)

The Phase 4 HTTP audit checks static technical facts. Phase 6A optionally opens an already-known public website in a real Chromium browser to measure observable UX behaviour without spending Tavily/Gemini credits.

Install the optional browser capability:

```bash
pip install -e ".[browser]"
python -m playwright install chromium
```

Then run:

```bash
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily --investigate --audit-websites --browser-audit --browser-audit-limit 3
```

The browser audit records:

- mobile horizontal overflow;
- visible contact/WhatsApp/phone CTAs above the fold;
- basic navigation-link presence;
- console and page/JavaScript errors;
- desktop and mobile full-page screenshots;
- a transparent `browser_ux_score` from 0–100.

`browser_ux_score` is **not** an aesthetic score. It does not claim whether the design is beautiful, modern, on-brand or competitive. Screenshots are intentionally retained for a future optional visual-intelligence phase and for human review in the frontend.

The browser layer reuses the same public-network safety principle as the HTTP auditor. Localhost/private/non-public network targets are blocked, including browser subrequests when possible.

Useful controls:

```text
--browser-audit-limit 3
--browser-timeout 12
--browser-audit-ttl-days 7
--refresh-browser-audits
```

Playwright is optional. The rest of LeadFlow remains usable without installing a browser runtime.

## Phase 6B — Visual Intelligence (optional)

After `--browser-audit` has produced desktop/mobile screenshots, LeadFlow can ask Gemini to review only the visible presentation quality. This is intentionally a separate subjective layer from Technical Health and Browser UX.

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily --investigate --investigation-limit 3 --investigation-budget 2 --audit-websites --audit-limit 3 --browser-audit --browser-audit-limit 3 --visual-audit --visual-audit-limit 3
```

Visual Intelligence reports independent 0–100 dimensions for overall presentation, desktop, mobile, modernity, hierarchy, brand coherence, readability and visible conversion clarity, plus an explicit model confidence. Low-confidence visual reviews are stored for inspection but are not allowed to drive the commercial opportunity type.

Important: a visual score is **not** a purchase probability and is not a technical score. It is an AI-assisted review of the screenshots. Technical Health, Browser UX, Visual Quality, Identity Confidence and Opportunity Fit remain separate signals.

Recent visual audits are reused for 14 days by default. Use `--refresh-visual-audits` to force a new review.

### Search profiles and advanced filters

LeadFlow keeps free-text search, but now also exposes curated segment presets and reusable qualification profiles:

```bat
python -m leadflow_agent segments
python -m leadflow_agent profiles
```

Examples:

```bat
python -m leadflow_agent search --segment marcenaria --city "Praia Grande" --state SP --profile new-site --investigate
```

```bat
python -m leadflow_agent search --segment marcenaria --city "Praia Grande" --state SP --profile visual-redesign --audit-websites --browser-audit --visual-audit --max-visual-score 60
```

Profiles are defaults, not restrictions: advanced flags can override website state, Instagram/phone/e-mail presence, READY/VERIFY state, opportunity types and technical/browser/visual score thresholds. Custom segments remain valid even when they are not in the preset catalog.

## Runtime safety & provider foundation (Phase 7.1)

LeadFlow now treats API quota and accidental large jobs as safety concerns, not merely user responsibility.

Normal search runs accept at most **100 requested leads**. A future Bulk Research workflow will handle larger jobs with checkpoints/resume instead of letting a typo such as `--limit 1000` start an unexpectedly expensive run.

Every run also has an independent hard safety envelope:

```text
search calls       20 default
AI operations      30 default
HTTP audits        25 default
browser audits     10 default
visual audits      10 default
```

These budgets are not promises to spend that amount; cache/memory may make the real usage much smaller. If a budget is reached, LeadFlow returns the useful work already completed with `partial_budget` status instead of looping indefinitely.

Advanced CLI users can lower or raise the envelope within conservative hard ranges:

```text
--max-search-calls
--max-llm-calls
--max-website-audits
--max-browser-audits
--max-visual-audits
```

The report exposes the actual per-run usage separately from requested result count. Repeated transient provider failures also trigger a per-run circuit breaker so an unhealthy API is not hammered indefinitely.

Cancellation is represented in the core through a callback hook even though the current CLI has no Cancel button yet. The first frontend can therefore stop a job cleanly without redesigning the research engine.

Provider roles/capabilities can be inspected with:

```bat
python -m leadflow_agent providers
```

Provider capability metadata deliberately does not encode volatile pricing. LeadFlow treats BYOK free/paid account choice as configuration; discovery/planning code depends on provider capabilities rather than billing plan names.
