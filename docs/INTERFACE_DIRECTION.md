# LeadFlow — Interface Direction v0.1

## Direction: Signal Workspace
A dense professional workspace with restrained digital materiality: deep graphite/navy base, localized light, mostly solid operational surfaces, translucent context surfaces only where depth communicates hierarchy.

## App shell
- compact global navigation rail;
- stable top context/status bar;
- primary data workspace;
- contextual right inspector;
- persistent bottom system status.

## Canonical layout
`Navigation rail → data workspace → selected-lead inspector`

The first production slice uses Data Workspace + List/Detail + Supporting Pane patterns. Selection must preserve table position and search context.

## Density
- visual density: 6.5/10
- information density: 8.5/10
- motion: 3.5/10
- keyboard acceleration target: 8/10

## Material rules
- no generic glassmorphism over every surface;
- data table stays high-contrast and nearly opaque;
- blur/translucency reserved for shell/context surfaces;
- accent light represents active/processing/selected state;
- no decorative charts or KPI cards without a decision purpose;
- moderate radius; borders and tone do more work than shadow.

## First vertical slice
Search → run state → results grid → lead inspector → prepared WhatsApp/Instagram contact.

## Adaptive behavior
Expanded: table + persistent inspector.
Medium: table + overlay inspector.
Compact: single workspace; inspector overlays and low-priority table columns hide.

## Explicitly deferred
Lead rotation/history, insufficient-data queue, CRM pipeline, follow-up, reply assistant, analytics, command palette, saved views, bulk contact queue and Tauri packaging.
