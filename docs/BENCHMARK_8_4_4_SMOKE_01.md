# Phase 8.4.4 — Smoke 01 Diagnostic

Date: 2026-09-13/14 (local run)
Case: `marcenaria-praia-grande-sp`
Mode: non-official smoke, target 3

## Observed result

- requested: 3
- returned: 1
- fulfillment: 33.3%
- discovery queries: 2
- unique candidates: 15
- prequalified candidates: 12
- investigated leads: 5
- investigation searches: 10
- search calls: 12
- LLM calls: 9
- website audits: 3
- external/provider/network failures: 5
- quality-gate measurement: invalid
- runtime: approximately 6 minutes

## Interpretation

Discovery is no longer the bottleneck. Two queries produced 15 unique candidates,
12 of which passed discovery-stage prequalification. The current development
latency comes from post-discovery work: bounded investigation still expands into
multiple provider searches and Gemini extraction calls per candidate.

The smoke also validates the Phase 8.4.4 priority fix at the deterministic level:
the current investigation ordering places contactable candidates first. The run
was not eligible as a quality benchmark because Gemini/provider failures caused
several investigated leads to remain unresolved (`review_needed`).

## Process decision

A 3-lead smoke is still too expensive to be the normal debugging loop. From this
point onward:

1. unit/regression tests are the default loop;
2. `--capture-only` is used only when a fresh real-world fixture is needed;
3. capture-only performs at most two search calls and zero Gemini/investigation/audits;
4. deterministic changes are validated with local replay;
5. 3-lead smoke is reserved for integration checks;
6. 10-lead runs are reserved for official Phase 8.4.4 gates.

The product-performance problem (full user runs can still be slow when the
Investigator needs many external calls) remains a separate optimization target;
the fast-capture work fixes development iteration time without hiding that
runtime concern.

## Follow-up patch — Investigator Fast Path

The replayable `post_discovery` fixture was used to optimize the expensive stage
without another provider run. The patch keeps the same conservative identity
rules while reducing avoidable external work:

- existing phone/e-mail/social contact skips a redundant contact-search query;
- all bounded search evidence for one lead is extracted in one Gemini generation
  when batch extraction is supported;
- investigation stops early when the requested final quota is already satisfied;
- filtered quota runs only audit websites after identity is matched/probable;
- status-less DNS/network failures now contribute to the provider circuit breaker.

Deterministic replay on the same smoke fixture estimates a maximum of **9
investigation searches / 5 batched extraction calls** for the five selected
candidates, versus **9 extraction calls** under the legacy per-query extraction
strategy. The next external smoke is therefore an integration/latency check,
not part of the ordinary debugging loop.
