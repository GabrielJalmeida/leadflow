# Phase 8.4.4 — Benchmark Run 01 (Diagnostic)

**Date:** 2026-09-13  
**Case:** `marcenaria-praia-grande-sp`  
**Target:** 10  
**Status:** reviewed diagnostic sample; **not counted as official 1/5**

## Why it is not official

The run fulfilled 10/10 and had no top-level provider errors, but both final returned leads that had websites also had inconclusive HTTP audits caused by hostname/DNS resolution failure. The previous benchmark validity rule looked at the aggregate audit error rate (3/10 = 30%), so it incorrectly considered the run valid. The corrected rule also evaluates the final website-bearing leads (2/2 = 100% inconclusive) and therefore invalidates this measurement for the official quality gate.

This does **not** discard the manual review. Discovery/identity/contact observations remain valuable diagnostic evidence; only the final opportunity/audit conclusions are contaminated.

## Diagnostic metrics

| Metric | Result |
|---|---:|
| Requested / returned | 10 / 10 |
| Fulfillment@N | 100% |
| Precision@N | 100% |
| Canonical-name precision | 90% |
| Identity precision | 90% |
| Phone plausibility | 100% |
| Website attribution false-positive rate | 0% |
| Duplicate rate | 0% |
| False-merge rate | 0% |
| Contact usefulness | 90% |
| Evidence sufficiency | 90% |
| Overall row PASS rate | 70% |
| Queries executed | 20 |
| Unique candidates | 40 |
| Search calls | 37 |
| LLM calls | 30 |
| Final website audits | 2 |
| Final website audits inconclusive | 2 (100%) |

## Defects observed

### D1 — Inconclusive network audit could become REBUILD

A website that failed local DNS/HTTP reachability could receive a low technical score and a strong `REBUILD` opportunity. This is unsafe because a local resolver outage, timeout or network path failure says nothing reliable about the customer's real website quality.

**Fix applied:**

- added `WebsiteResolutionError` for operational DNS failures;
- kept `UnsafeWebsiteUrl` only for genuinely unsafe/private targets;
- inconclusive audits carry low evidence confidence;
- `UNREACHABLE` / blocked / no-status audits produce `REVIEW_NEEDED` with `website_reachability_review`, not `REBUILD`;
- regression tests added.

### D2 — Aggregate validity hid final-result contamination

The run-wide website-audit error rate was below 50%, but the only two final leads with websites were both inconclusive.

**Fix applied:** benchmark metrics now include:

- `final_website_audits`;
- `final_website_audit_errors`;
- `final_website_audit_error_rate`.

A >=50% inconclusive rate among final website-bearing leads invalidates the quality-gate measurement.

### D3 — Deferred filters exhausted discovery queries

The `website-sales` profile filters on opportunity type/score, but those values are created after investigation/audit. During raw discovery they were `UNKNOWN`, causing `prequalified_candidates = 0` and all 20 planned queries to run.

**Fix applied:** preliminary qualification is stage-aware. It preserves cheap observable contact constraints but defers website state, readiness, opportunity and audit-score filters. When filters are deferred, discovery uses conservative overfetch (up to 3x requested quantity) rather than stopping at exactly N raw leads.

### D4 — Identity/unit ambiguity remains

One reviewed result showed a brand/unit/contact ambiguity. This is a real entity-resolution risk, not an infrastructure artifact. It is intentionally **not patched from one sample**. We will look for repetition across the remaining benchmarks and only then define the Phase 8.4.5 identity correction.

## Regression status

```text
python -m unittest discover -s tests -v
Ran 185 tests
OK
```

The frontend source was not changed by this patch. A Vite build was not revalidated in the sandbox because `frontend/node_modules` is intentionally absent from the clean working tree.

## Next gate

1. Rerun `marcenaria-praia-grande-sp` with fresh provider/network access.
2. Confirm `quality_gate_measurement_valid = true`.
3. Confirm final website audits no longer turn DNS/network failure into `REBUILD`.
4. Check whether stage-aware prequalification reduces query/search usage while keeping 10/10.
5. Manually review the rerun.
6. If valid, count it as official benchmark **1/5** and proceed to the other four cases.
