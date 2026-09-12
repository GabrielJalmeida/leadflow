# LeadFlow Frontend — first functional slice

This is the first permanent-stack frontend for LeadFlow. It intentionally implements one vertical slice well:

**search → background run → results → lead inspector → prepared contact**

It is not the final visual pass and it does not implement CRM/history/follow-up yet.

## Run locally

Terminal 1, repository root:

```bash
leadflow api
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (normally `http://127.0.0.1:5173`).

## Build check

```bash
npm run typecheck
npm run build
```

## Architecture

- React + TypeScript + Vite
- TanStack Query for server state/polling
- TanStack Table for the opportunity grid
- Zustand for small workspace/view state
- Fluent System Icons
- Custom CSS token/material system (no template UI kit)

The interface consumes only the LeadFlow Local API / Frontend Contract boundary.
