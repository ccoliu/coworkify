# Coworkify - Distributed Task Scheduling & Execution Platform

English | [繁體中文](README.md)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?style=flat&logo=PostgreSQL&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D.svg?style=flat&logo=Redis&logoColor=white)](https://redis.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?style=flat&logo=React&logoColor=white)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=Docker&logoColor=white)](https://www.docker.com/)

**Coworkify** is a lightweight, high-performance, and flexible distributed task scheduling and management platform (architecturally inspired by Apache Airflow and Celery). Users and microservices can define, schedule, track, and monitor asynchronous tasks through a RESTful API, with support for chaining multiple tasks into a DAG workflow, using Redis + Postgres + Celery, expecting to handle 10M+ requests per day.

![alt text](<coworkify.png>)
---

## Key Features

- **Full task lifecycle management**: State machine covering `pending` ➔ `running` ➔ `success` / `failed` / `retrying` / `cancelled`.
- **High-performance async architecture**: FastAPI as the core API gateway, backed by Redis for a low-latency message broker.
- **Priority queue scheduling**: Weighted task priority so high-priority tasks jump the queue.
- **Scheduling & delayed execution**: Supports immediate execution, execution at a specific time, and recurring schedules.
- **Resilient retry mechanism**: Configurable `max_retries` with exponential backoff.
- **DAG workflow orchestration**: Chain multiple tasks by dependency (`task1 → task2 → task3`, including branching/merging); a single node failure automatically cascades cancellation to downstream nodes.
- **Cron-based recurring schedules**: A workflow can be bound to a standard 5-field cron expression (e.g. "every day at 9am"); Celery Beat periodically checks and, when due, automatically creates and dispatches the whole workflow, with timezone handling consistent across the app.
- **Redis sliding-window rate limiting**: Request rate is tracked per logged-in user, protecting the system from any single source overwhelming it.
- **Real-time task status push**: WebSocket + Redis Pub/Sub push task status changes instantly, no frontend polling required.
- **Account authentication**: Register/login with bcrypt-hashed passwords and JWT session tokens; users can self-register from the frontend.
- **Live Ops dashboard**: The React frontend visualizes queue depth, throughput, and error rate in real time, plus a visual DAG graph for tracking workflow execution.

---

## Supported Task Handlers

| Task Type (task_type) | Description |
| :--- | :--- |
| `echo` | Simple echo task, used to verify system connectivity |
| `heavy_computation` | Simulates a long-running computation with a configurable duration |
| `flaky_task` | Simulates a task that may fail, used to test the automatic retry mechanism |

---

## Quick Start

### Requirements
- Docker / Docker Compose

### 1. Configure environment variables
Copy a `.env` file (see `docker-compose.yml` for the required variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `JWT_SECRET`, etc.) and fill in your own values. `JWT_SECRET` is used to sign login tokens — generate a random string with `python -c "import secrets; print(secrets.token_hex(32))"`.

### 2. Start all services with one command
```bash
docker-compose up -d --build
```
This starts: PostgreSQL, Redis, the FastAPI API, a Celery Worker, Celery Beat (schedule checker), and the React frontend.

- Frontend dashboard: http://localhost:5173
- API docs (Swagger UI): http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 3. Run a Locust load test
```bash
locust -f tests/locustfile.py --host http://localhost:8000
```

---

## Main API Endpoints

### Auth
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/auth/register` | Register a new account (username + password); returns a JWT immediately on success |
| `POST` | `/auth/login` | Log in to an existing account, returns a JWT |
| `GET` | `/auth/me` | Look up the current logged-in user, used to confirm the token is still valid |

### Tasks
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/tasks/` | Create and automatically dispatch a task (supports immediate execution or a `scheduled_at` time) |
| `GET` | `/tasks/` | Paginated task list (supports filtering by status/type and priority ordering) |
| `GET` | `/tasks/{task_id}` | Look up a single task's detailed status and result |
| `DELETE` | `/tasks/{task_id}` | Delete a task |

### Workflows (DAG)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/workflows/` | Create a DAG workflow; automatically dispatches root nodes that have no dependencies |
| `GET` | `/workflows/{workflow_id}` | Look up a workflow's overall status and the live status of each node's task |

A 3-node linear workflow example:
```json
POST /workflows/
{
  "name": "demo-pipeline",
  "steps": [
    { "key": "t1", "name": "step1", "task_type": "echo", "payload": {"message": "step1"}, "depends_on": [] },
    { "key": "t2", "name": "step2", "task_type": "echo", "payload": {"message": "step2"}, "depends_on": ["t1"] },
    { "key": "t3", "name": "step3", "task_type": "echo", "payload": {"message": "step3"}, "depends_on": ["t2"] }
  ]
}
```
`depends_on` can list multiple keys, supporting branching and merging (a real DAG, not just a linear chain); when a node fails permanently (retries exhausted), all downstream nodes are automatically marked `cancelled` and the whole workflow is marked `failed`.

### Schedules (recurring workflows)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/schedules/` | Create a recurring workflow bound to a cron expression (steps use the same shape as `/workflows/`) |
| `GET` | `/schedules/` | List all schedules |
| `GET` | `/schedules/{schedule_id}` | Look up a single schedule |
| `PATCH` | `/schedules/{schedule_id}` | Update a schedule's content, cron expression, or enabled state |
| `DELETE` | `/schedules/{schedule_id}` | Delete a schedule |

Celery Beat checks all `enabled=true` schedules once a minute; when `next_run_at` is due, it creates a new workflow from `steps` and dispatches the root nodes, then computes the next run time from the cron expression. The cron expression is interpreted in the app's configured timezone (`Asia/Taipei`), consistent with how `next_run_at` is displayed and compared.

### Other
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | API server health check |
| `WS` | `/ws/tasks` | WebSocket for real-time task status updates (Redis Pub/Sub) |

Every endpoint under `/tasks`, `/workflows`, and `/schedules` requires a JWT obtained via `/auth/register` or `/auth/login`, sent in the `Authorization: Bearer <token>` header, and is rate-limited per logged-in identity via Redis sliding-window limiting.

---

## Benchmark Results

Load-tested with **Locust** at 150 concurrent users over a 2-minute window, simulating concurrent read/write traffic (database queries, task creation, and Redis queue dispatch), with the database cleared beforehand:
- **Total requests**: 23,310
- **Failure rate**: **0.06% (14 failures, all Windows-loopback-level `ConnectionResetError`, not application-layer errors)**
- **Throughput**: **194.5 RPS**
- **Average latency**: **443 ms**
- **P95 latency**: **820 ms**
- **Median latency**: **410 ms**

| API Endpoint | Request Type | Avg Latency (ms) | Throughput (RPS) | Failure Rate |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | Health check | 115 ms | 32.7 RPS | 0.05% |
| `GET /tasks` | Paginated DB query | 502 ms | 97.2 RPS | 0.08% |
| `POST /tasks` | Task creation + queue dispatch | 520 ms | 64.5 RPS | 0.04% |

> Latency is higher than in an earlier version because this run was measured **after** fixing an event-loop-blocking bug in the API rate limiter, using clean numbers from requests that actually passed auth and hit the database; the earlier 288 RPS / 38.9ms figures mostly measured fast auth-rejected requests that barely touched the database, so the two are not directly comparable. The current bottleneck is believed to be that `/tasks` uses synchronous (`def`, not `async def`) SQLAlchemy calls, which FastAPI runs in a thread pool — this tends to queue up under high concurrency. Switching the DB layer to async (`asyncpg` + SQLAlchemy async session) is the next lever to pull for more throughput.
>
> These numbers were measured **before** switching authentication from API keys to JWT-based login (the identity-check mechanism changed, but both are O(1) lookups/decodes and shouldn't be the main bottleneck); this table will be updated after a re-measurement.

### Workflow Creation Throughput

The same 150-concurrency test round also included `POST /workflows` (creating a 3-node linear pipeline each time):

| API Endpoint | Request Type | Avg Latency (ms) | Throughput (RPS) | Failure Rate |
| :--- | :--- | :--- | :--- | :--- |
| `POST /workflows` | Create a 3-node workflow + dispatch root node | 578 ms | 24.6 RPS | 0.20% |

2,941 workflows were created during the test, and all were later confirmed to have **run to completion in order, with none stuck or errored** (the `advance_workflow` chained-dispatch logic holds up under high concurrency). One caveat: workflow tasks share the same `concurrency=4` Celery worker pool with the regular `POST /tasks` test traffic, so when many `heavy_computation` tasks (which really do `sleep(1)` second) pile up, workflow chain completion times get pushed back — this is queuing delay from shared resources, not a logic bug. If you want to measure workflow latency in isolation, run it separately from other task-type load, or give workflows their own dedicated Celery queue.

---

## Frontend Development

A React + TypeScript + Tailwind SPA — see [frontend/README.md](frontend/README.md) for details. Once `docker-compose up` is running, the Vite dev server automatically proxies `/api` and `/ws` to the backend, so no extra CORS setup is needed.

- **Login page**: Register a new account or log in with an existing one; the JWT is stored in the browser's localStorage after login, so a page refresh doesn't require logging in again.
- **Tasks page**: Task list, filtering, and single-task creation, with status updated live over WebSocket.
- **Workflows page**: Lists every workflow ever created; a multi-step form lets you build a new DAG (each step can check which earlier steps it depends on), and clicking into one shows a topologically-layered pipeline diagram with each node's live execution status.
- **Schedules page**: Manage recurring workflows using the same step editor plus a cron expression input (with common presets like "every day at 9:00"), showing next/last run time, and letting you enable/disable or edit at any time.
- **Ops page**: Live monitoring metrics — queue depth, throughput trend, error rate, and more.
