# LeadFlow Security Boundaries — v0.1.4-dev

LeadFlow researches public web content, calls BYOK providers and writes local artifacts. Treat all external content as hostile data, not instructions.

## Current trust boundaries

### Trusted configuration

- CLI/UI options after validation.
- Local user-owned API credentials.
- LeadFlow code and migrations distributed by the project.

### Untrusted data

- search-result titles/snippets;
- websites, redirects and browser subresources;
- text visible inside screenshots;
- business names, addresses and URLs returned by providers;
- LLM output until parsed and validated against LeadFlow rules.

Untrusted data must never gain authority to execute code, read local files, reveal credentials, change configuration, send messages or trigger deployment.

## Implemented controls

- SSRF protection for website/browser auditing: localhost, private, link-local, loopback, reserved/non-global destinations are blocked.
- Redirect and browser-subresource destinations are validated independently.
- Search inputs reject control/bidi-override characters and enforce conservative length limits.
- Generated artifact paths use sanitized names and must remain below their configured output root.
- Common API-key/token/bearer forms are redacted before user-facing diagnostic output and JSON error export.
- Gemini extraction and screenshot-review prompts explicitly mark web/screenshot content as untrusted and instruct the model not to follow embedded instructions.
- Provider calls are bounded by per-run budgets and circuit breakers.
- Large normal-mode runs are rejected before provider calls (`--limit` max 100).
- SQLite schema has a version and idempotent migrations.
- Frontend consumers receive a smaller versioned contract instead of depending on internal provider payloads.

## Secrets

`.env` is development-only and must never be committed. The future desktop build should move stored credentials into the OS credential vault/keyring. LeadFlow exports must not intentionally include API credentials.

## Not implemented yet

The current build is local/BYOK and has no account system, payment flow or public network service. The following belong to later threat models:

- authentication, sessions, password reset and MFA;
- cloud API authorization and tenant isolation;
- subscription/payment webhooks and entitlements;
- telemetry/privacy controls;
- code signing and secure updater;
- automated outreach permissions and suppression lists.

These are intentionally not simulated with weak local substitutes.
