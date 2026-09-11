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
