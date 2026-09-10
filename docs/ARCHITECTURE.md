# LeadFlow Agent — Architecture v0.1.3

## Core principle

Lead discovery is an evidence-driven research loop, not a query against a magical lead database.

## Components

### SearchGoal
Defines segment, location, target quantity and basic constraints.

### LLMProvider
Gemini Flash-Lite plans commercial search phrases. The agent has a deterministic fallback if planning fails.

### WebSearchProvider
Tavily searches public web evidence. Search results are pages/snippets, not automatically business entities.

### LeadExtractorProvider
Gemini receives bounded Tavily evidence and returns structured companies supported by that evidence. One directory result may yield several businesses.

### LocalSearchProvider
Still supported for structured providers such as Brave/Outscraper, but no longer required by the core agent.

### LeadResearchAgent
Owns the loop:

1. plan queries;
2. search evidence or structured local data;
3. extract business entities;
4. normalize/deduplicate;
5. continue while the target quantity has not been reached;
6. optionally enrich selected candidates;
7. score and rank;
8. persist/export.

### LeadStore
SQLite persistence for research runs and unique entities. This is the seed of LeadFlow's own reusable index.

## Evidence rules

- Search results are evidence, not truth by themselves.
- Missing website means `not identified`, not `confirmed absent`.
- The extractor must not invent contact data.
- Source URLs are preserved with the lead.
- Directory pages are valuable evidence but must not become fake company records.

## Provider strategy

Provider-specific response shapes stop at adapters. BYOK configuration remains separate from business logic. Tavily, Brave and other future providers can coexist.

## Next milestone

Add a verification stage with explicit confidence states:

- business identity confirmed;
- phone confirmed by one or multiple sources;
- official site confirmed / likely / not found;
- social presence confirmed;
- website quality audit.

Only after discovery + verification is reliable should the dashboard and campaign features become the priority.
