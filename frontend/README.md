# Coworkify frontend

React + TypeScript + Tailwind SPA for the Coworkify task platform.

## Develop

```bash
npm install
npm run dev
```

Vite's dev server proxies `/api/*` → `http://localhost:8000` and `/ws/*` →
`ws://localhost:8000` (see `vite.config.ts`), so it talks straight to the
FastAPI backend from `docker-compose up` with no CORS setup needed. Open
http://localhost:5173 and sign in with one of the keys from `API_KEYS`
in the backend's `.env`.

## Build

```bash
npm run build   # outputs to dist/
```

For a production deploy where the frontend isn't served from the same
origin as the API (no reverse proxy in front of both), set
`VITE_API_BASE_URL` / `VITE_WS_URL` at build time — see `.env.example`.
If Nginx sits in front of both (as planned for the Week 4 EC2 deploy),
just route `/api` and `/ws` to the API container and ship the default
build as-is.

## Structure

- `src/lib` — API client, WS/task types, formatting helpers
- `src/context` — auth (API key), toast notifications, WebSocket connection
- `src/components` — shared UI primitives (Button, Card, Modal, form fields, status badge)
- `src/features/tasks` — task list filters/table, create-task modal
- `src/features/ops` — status counts, throughput sparkline, live event feed
- `src/pages` — routed screens (Login, Dashboard, TaskDetail, Ops)

## Known gaps (backend, not this UI)

- `GET /tasks/{id}/logs` is documented in the root README but not implemented,
  so the task detail page's "live activity" only shows events observed over
  the WebSocket during the current session — no historical execution log.
- Deleting a task removes the DB row but doesn't revoke an already-queued
  Celery job.
