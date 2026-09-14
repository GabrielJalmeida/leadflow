# LeadFlow Local Application API

Phase 8.2 introduces the frontend-independent application boundary that future LeadFlow interfaces will use.

The API is intentionally local-first. The CLI starts it on `127.0.0.1`; it is not designed to bind publicly by default.

## Install

```bash
python -m pip install -e ".[api]"
```

Browser auditing remains a separate optional capability:

```bash
python -m pip install -e ".[api,browser]"
python -m playwright install chromium
```

## Start

```bash
leadflow api
```

Default address:

```text
http://127.0.0.1:8765
```

OpenAPI documentation:

```text
http://127.0.0.1:8765/docs
```

A different local port can be selected:

```bash
leadflow api --port 9000
```

The CLI deliberately does not expose a `--host` option. This keeps the default product boundary local while the authentication/cloud model is still future work.

## API surface

### Health

```http
GET /api/v1/health
```

Returns API health and whether each BYOK provider is configured. It never returns API keys.

### Catalogs

```http
GET /api/v1/catalog/segments
GET /api/v1/catalog/profiles
GET /api/v1/catalog/providers
```

These endpoints allow a future interface to build controls from backend capabilities instead of duplicating provider/profile/segment constants in frontend code.

### Start a research run

```http
POST /api/v1/runs
Content-Type: application/json
```

Example:

```json
{
  "segment": "marcenaria",
  "city": "Praia Grande",
  "state": "SP",
  "limit": 10,
  "profile": "website-sales",
  "provider": "auto",
  "features": {
    "investigate": true,
    "audit_websites": true,
    "browser_audit": false,
    "visual_audit": false
  }
}
```

The endpoint returns `202 Accepted` and a run ID. Research is not executed inside the request/response cycle.

### Poll status

```http
GET /api/v1/runs/{run_id}
```

Possible runtime states include:

```text
queued
running
cancelling
completed
partial_budget
cancelled
failed
```

### Get results

```http
GET /api/v1/runs/{run_id}/result
```

Completed results contain the stable `Frontend Contract v1` payload from `leadflow_agent.contracts` rather than the full internal dataclasses.

### Cancel

```http
POST /api/v1/runs/{run_id}/cancel
```

Cancellation signals the existing `RunController`; the process is not killed abruptly.

## Search request structure

The API already exposes backend capabilities needed by a future Quick Search / Advanced Search interface:

- free-text or preset segment;
- location and result count;
- search profile;
- discovery provider;
- website / Instagram / phone / email filters;
- READY / VERIFY and opportunity filters;
- technical, browser and visual thresholds;
- investigator / HTTP audit / browser audit / visual audit controls;
- cache and memory controls;
- per-run safety budgets.

The frontend does not need to know provider-specific implementation details.

## Security boundary

Current local safeguards:

- CLI binds only to `127.0.0.1`;
- trusted Host validation;
- local browser origins are CORS-enabled for development regardless of the eventual frontend framework;
- browser-originated mutation requests are rejected when the `Origin` is not local;
- provider keys are never returned by health/catalog endpoints;
- request limits remain bounded by the application layer;
- errors pass through LeadFlow's public error taxonomy and secret redaction.

This is not the future cloud authentication model. Authentication, user accounts, entitlements and remote deployment remain separate later phases.

## Frontend decision intentionally deferred

Phase 8.2 does **not** select React, Vue, Svelte, Tailwind, Tauri or another UI stack.

The permanent frontend stack should be selected after the target visual references, interaction density, desktop behavior, data-visualization needs and packaging expectations are reviewed. The API boundary exists specifically so that decision can be made without changing the LeadFlow intelligence core.
