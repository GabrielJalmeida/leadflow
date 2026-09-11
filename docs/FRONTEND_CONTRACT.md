# Frontend Contract v1.0

The future UI must not couple directly to every internal `Lead` or provider-specific field. `leadflow_agent.contracts.research_contract()` exposes a smaller versioned boundary.

Top-level shape:

```text
contract_version
run
  status
  stop_reason
  requested_results
  returned_results
  usage

goal
leads[]
  name
  location
  contact
  website
  identity
  opportunity
```

`contract_version = "1.0"` is the compatibility marker. Internal persistence may gain fields without forcing a frontend rewrite. Breaking UI-contract changes require a new contract version.

The first functional frontend should consume this contract rather than raw provider responses or SQLite `payload_json`.
