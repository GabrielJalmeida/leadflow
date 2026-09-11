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

## Enrichment

After discovery works, optional per-lead enrichment can run additional web searches:

```bat
python -m leadflow_agent search --segment "marcenaria" --city "Praia Grande" --state SP --limit 10 --provider tavily --enrich-web --enrichment-limit 5
```

This can consume additional search credits, so it is disabled by default.

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
