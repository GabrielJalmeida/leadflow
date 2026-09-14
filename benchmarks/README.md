# LeadFlow Phase 8.4.4 Benchmark

This folder contains the **manual real-world quality benchmark** for LeadFlow.
It exists to answer a question that unit tests cannot answer:

> Are the leads returned by the product actually the right businesses, in the
> right place, with correctly attributed contact/website data and a useful
> commercial opportunity?

The benchmark does **not** auto-label truth from the web. The runner only
captures LeadFlow's output and generates a review sheet. A human must inspect
real-world evidence and fill the manual columns.

## Official cases

`cases.yaml` contains the five minimum Phase 8.4.4 cases:

1. marcenaria — Praia Grande/SP — 10
2. estetica automotiva — Santos/SP — 10
3. vidracaria — Sao Vicente/SP — 10
4. eletricista — Campinas/SP — 10
5. moveis planejados — Sao Luis/MA — 10

## Running one case

From the repository root:

```bash
python scripts/run_benchmark.py --case marcenaria-praia-grande-sp
```

To force fresh provider calls instead of reusing search cache:

```bash
python scripts/run_benchmark.py --case marcenaria-praia-grande-sp --refresh-cache
```

Windows shortcut from the repository root:

```text
run-phase844-benchmark.bat
```

The launcher asks for confirmation before forcing fresh calls so the user does
not spend provider quota accidentally.

To use an explicit `.env` file without copying it into the repository:

```bash
python scripts/run_benchmark.py \
  --case marcenaria-praia-grande-sp \
  --dotenv /path/to/.env \
  --refresh-cache
```

The benchmark intentionally requires `--all` to run every official case. This
prevents an accidental multi-case run from consuming external provider quota.

```bash
python scripts/run_benchmark.py --all
```

## Artifacts

Each run is written under:

```text
benchmarks/results/<timestamp>_<case-id>/
```

The directory contains:

- `run.json` — full sanitized LeadFlow research report;
- `leads.csv` — normal LeadFlow export;
- `review.csv` — human review worksheet;
- `metrics.json` — automatic run metrics plus manual metrics when summarized;
- `summary.md` — compact benchmark summary.

The harness also computes **quality-gate measurement validity**. A run with
provider/network failures or a website-audit failure rate of 50% or more is
flagged as invalid and must not count toward the five official Phase 8.4.4
benchmarks. The final returned leads are checked separately: when >=50% of the
website audits attached to final leads are blocked/inconclusive, the run is also
invalid even if the aggregate run-wide audit failure rate is lower. This prevents
infrastructure outages from being misdiagnosed as LeadFlow quality failures or
from becoming false commercial `REBUILD` recommendations.

`benchmarks/results/` is ignored by Git except for `.gitkeep` because benchmark
artifacts can contain public business contact data and should not be committed
by default.


## Fast validation loop (development)

Do **not** rerun the full 10-lead benchmark after every deterministic code change.
Phase 8.4.4 now has a faster three-level loop:

```text
unit/regression tests
        ↓
local replay (0 provider calls)
        ↓
3-lead smoke test when external behaviour must be checked
        ↓
10-lead official benchmark only at a phase gate
```

Every new benchmark/smoke run captures `replay_snapshot.json` with candidate
states at `post_discovery`, `post_investigation` and `post_audits`, plus the
candidates selected for bounded investigation/auditing. These artifacts remain
local and are ignored by Git because they may contain public business data.

Replay scoring, filtering, ranking and the **current investigation selection**
without Tavily/Gemini calls:

```bash
python scripts/run_benchmark.py --replay benchmarks/results/<run>
```

On Windows use `run-phase844-replay.bat`. Replay writes
`replay_post_audits.json` and `replay_post_audits.md` beside the captured run.
Provider calls and LLM calls are always `0`.

To capture a small real-world snapshot without waiting for a full official run:

```bash
python scripts/run_benchmark.py --case marcenaria-praia-grande-sp --smoke --refresh-cache
```

This asks for only 3 leads and writes to `benchmarks/smoke/`. On Windows use
`run-phase844-smoke.bat`. Smoke runs are **never eligible** to count as one of
the five official benchmark cases.

Important: benchmark runs created **before** this replay feature do not contain
the full pre-filter candidate pool, so they cannot reconstruct investigator
selection faithfully. One new smoke/benchmark capture is required; after that,
deterministic iterations can be replayed in seconds.

## Manual review semantics

Use only these values in review fields:

```text
PASS
FAIL
UNCERTAIN
```

For normal validation fields, `PASS` means the claim is correct.
`canonical_name_correct` specifically checks whether LeadFlow returned a usable
business name rather than an SEO/page title such as "Móveis Planejados em
Praia Grande". For the two negative defect checks below, the meaning is
deliberately inverted so a row can be read as a checklist:

- `is_duplicate`: `PASS` = no duplicate problem; `FAIL` = duplicate detected.
- `is_false_merge`: `PASS` = no false merge; `FAIL` = false merge detected.

Do not turn uncertainty into `PASS`. If evidence is insufficient, mark
`UNCERTAIN` and explain it in `notes`.

## Review columns

The worksheet preserves the Phase 8.4.4 fields:

```text
benchmark_id
run_id
rank
lead_name
canonical_name_correct
segment_match
city_match
state_match
real_business
identity_correct
phone_present
phone_kind
phone_plausible
instagram_correct
website_status_predicted
website_status_manual
website_correctly_attributed
opportunity_type_predicted
opportunity_type_manual
is_duplicate
is_false_merge
contact_route_useful
evidence_sufficient
final_grade
notes
```

It also includes read-only context columns such as phone, website URL, social
URLs, identity state, score, evidence count and source URLs.

## Summarizing a reviewed file

After filling `review.csv`:

```bash
python scripts/run_benchmark.py --summarize benchmarks/results/<run>/review.csv
```

This updates `metrics.json` and `summary.md` with manual metrics such as:

- Precision@N;
- identity precision;
- phone plausibility;
- website attribution false-positive rate;
- duplicate rate;
- false-merge rate;
- contact usefulness;
- overall PASS rate.

## Phase gate

Phase 8.4.4 is not complete until all five official cases have been run and at
least 50 leads have been manually reviewed. Fixes should be grouped by the
pipeline stage responsible for the observed failure, then covered by a
regression test before Phase 8.4.5 is considered complete.

## Ultra-fast development capture

For ordinary debugging, do **not** run a full smoke/benchmark first. Capture a
real discovery fixture with at most two provider searches and no Gemini or audit
layers:

```bash
python scripts/run_benchmark.py --case marcenaria-praia-grande-sp --capture-only --refresh-cache
```

Windows shortcut:

```text
run-phase844-capture.bat
```

Artifacts are written to `benchmarks/captures/`. The important file is
`replay_snapshot.json`. After that, deterministic changes to selection, scoring,
filtering and ranking should be checked locally with `--replay` before any new
external smoke test is considered.

Development hierarchy from fastest to slowest:

```text
unit/regression tests -> fast capture (only when a new fixture is needed)
-> local replay -> 3-lead smoke (integration only) -> official 10-lead benchmark
```

`--capture-only` is intentionally **not** eligible for the Phase 8.4.4 quality
gate because it disables AI extraction, investigation and website audits.

## Investigator Fast Path diagnostics

Replay now also estimates the current investigation cost from a captured
`post_discovery` fixture without calling providers. The generated replay report
shows:

- estimated investigation searches;
- estimated batched investigation extraction calls;
- the legacy per-query extraction count for comparison;
- the number of extraction calls avoided by batching;
- the query purposes selected for each candidate.

During live filtered quota runs, LeadFlow now batches the bounded searches for
one lead into a single Gemini extraction when supported, stops investigation as
soon as the requested quota is already satisfied, and only spends website-audit
work on identity-verified business/site associations.
