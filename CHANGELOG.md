# Changelog

## Unreleased — 0.1.4-dev

- Added explicit business identity states (`UNVERIFIED`, `MATCHED`, `PROBABLE_MATCH`, `AMBIGUOUS`, `MISMATCH`).
- Added conservative entity-resolution rules for phone, domain, name and locality.
- Added rejected-candidate memory so known-wrong website candidates are not repeatedly investigated.
- Website enrichment no longer assigns a domain from name similarity alone.
- Added SQLite migration fields for identity status/confidence.
- Added regression tests for same-name businesses in different cities/states.

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
