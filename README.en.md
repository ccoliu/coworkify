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
- **Visual workflow builder**: Drag nodes onto a canvas and draw an edge to declare a dependency; a `condition` node's `true` / `false` outputs map directly onto if/else branches. The frontend mirrors the backend's DAG validation rules, flagging problems on the nodes themselves and blocking submission.
- **Explicit input and output**: An `input` node is the workflow's data entry point, consumed downstream via `{{steps.<key>.result.<field>}}`; when the run finishes, every terminal node's result is collected into `workflows.result` instead of being scattered across individual task logs.
- **One-click re-run**: A workflow keeps the step template it was created from, so `POST /workflows/{id}/rerun` runs it again from that same template while leaving the previous run's state and history fully intact.
- **Cron-based recurring schedules**: A workflow can be bound to a standard 5-field cron expression (e.g. "every day at 9am"); Celery Beat periodically checks and, when due, automatically creates and dispatches the whole workflow, with timezone handling consistent across the app.
- **Redis sliding-window rate limiting**: Request rate is tracked per logged-in user, protecting the system from any single source overwhelming it.
- **Real-time task status push**: WebSocket + Redis Pub/Sub push task status changes instantly, no frontend polling required.
- **Account authentication**: Register/login with bcrypt-hashed passwords and JWT session tokens; users can self-register from the frontend.
- **Live Ops dashboard**: The React frontend visualizes queue depth, throughput, and error rate in real time; the workflow detail page renders the same canvas in read-only mode, colouring nodes by task status and updating live over WebSocket.

---

## Supported Task Handlers

This list is defined in `app/tasks/catalog.py` and served — along with each field's spec — from `GET /tasks/types`. The frontend's task-creation form and the workflow property panel are both rendered from it, so **adding a task type requires no frontend changes**.

| Task Type (task_type) | Description |
| :--- | :--- |
| `input` | The workflow's data entry point. Its payload carries a JSON blob and its result is the workflow's raw material, consumed downstream via `{{steps.<key>.result.<field>}}` |
| `python` | Runs a snippet of Python in a restricted subprocess. Define a `main()` and its return value automatically becomes the result's `result.value` |
| `shell` | Runs a shell command in a restricted subprocess |
| `http_request` | Sends an HTTP request; targets pointing at private networks or cloud metadata endpoints are blocked |
| `condition` | Evaluates a condition and returns `passed=true/false`. It always succeeds — downstream steps use `branch_of` + `branch_when` to point at it and implement if/else |
| `agent_step` | Runs a [Codoctopus](https://github.com/ccoliu/Codoctopus) agent step — the payload carries `role` (system prompt), `instruction`, an optional `model` (`"provider:model"`), and `tools` (`read_file` / `write_file` / `list_files` / `http_request` / `run_tests`). Requires `codoctopus` to be installed in the worker environment; see the note below. |

> The worker must be able to `import codoctopus` for `agent_step` to work. For local development: `pip install -e "<codoctopus-checkout>[anthropic]"` (the `[anthropic]` extra is required — the SDK is an optional dependency; `[openai]` / `[gemini]` / `[all]` also work, or point at an `ollama:` model and install no SDK at all).
>
> For containerized deployments you don't need codoctopus in every worker — `agent_step` is the only task type that needs it, so it is routed to a dedicated `agent_step` queue consumed only by the `worker-agent` service (see `Dockerfile.agent`), started with `docker compose --profile agent up`. All other workers are unaffected. To use it, set `CODOCTOPUS_PATH` (pointing at your local Codoctopus checkout) and `AGENT_STEP_DEFAULT_MODEL` in `.env`, plus whatever the provider needs (e.g. `ANTHROPIC_API_KEY`, or `OPENAI_BASE_URL` for a local OpenAI-compatible server). If an `agent_step` is scheduled in an environment with no worker-agent running it simply stays `pending` — it will not fail, and no other worker will pick it up by mistake.

> `python` and `shell` run in a restricted subprocess (timeout, CPU / memory limits, a cleared environment — see `app/tasks/sandbox.py`). **This is not a full sandbox** — it still shares the worker's filesystem and network, so don't point it at untrusted input.

The early demo handlers (`echo`, `heavy_computation`, `flaky_task`, `job_search`, …) are still registered in `TASK_REGISTRY` — existing rows and tests reference them — but are deliberately left out of the catalog above, so they don't appear in the frontend's task-type picker.

---

## Visual Workflow Builder

![Workflow builder](<workflow-builder.png>)

`/workflows/new` is a React Flow canvas, auto-laid out with dagre:

- **Build by dragging**: Drag a task type from the left-hand palette onto the canvas to create a node; draw an edge between two nodes to declare a `depends_on` relationship
- **Branching is just wiring**: A `condition` node exposes `true` and `false` outputs on its right edge — whichever one you drag from sets that step's `branch_of` / `branch_when` automatically, with no manual step-key bookkeeping
- **Property panel**: The right-hand form is generated from the field specs in `GET /tasks/types`; the code fields on `python` / `shell` are CodeMirror editors (syntax highlighting, auto-indent, expand-to-modal editing, and direct `.py` upload)
- **Live validation**: The frontend mirrors the backend's `validate_dag` rules (see `frontend/src/features/workflows/validateGraph.ts`), surfacing problems on the nodes and above the canvas and blocking submission while any remain. The backend copy is still the final gate — the two must be maintained together
- **Keyboard shortcuts**: `Delete` removes the selected node or edge, `Esc` clears the selection, `Ctrl+D` duplicates a node, `L` re-runs auto-layout, `F` fits the view

The workflow detail page renders **the same canvas** in read-only mode to show an actual run: nodes are coloured by task status and update live over WebSocket, the branch that wasn't taken is dimmed out as `cancelled`, and clicking any node shows its payload and error message.

![Workflow run view](<workflow-run.png>)

The run above is a nested-branch workflow: `condition_1` took the `false` path into `python_2`, and `condition_2` took `true` into `shell_2`. The untaken `shell_1` and `shell_3` were marked `cancelled` along with their downstream nodes, yet the workflow as a whole is still `Success` — a branch not being taken is the expected outcome, not a failure.

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
| `GET` | `/workflows/` | Paginated list of all workflows |
| `GET` | `/workflows/{workflow_id}` | Look up a workflow's overall status, the live status of each node's task, and its final `result` |
| `POST` | `/workflows/{workflow_id}/rerun` | Run the stored step template again, creating a **new** workflow; the previous run's state and history are kept intact |
| `POST` | `/workflows/{workflow_id}/promote-to-schedule` | Register this workflow's step template as a recurring cron schedule |
| `DELETE` | `/workflows/{workflow_id}` | Delete a workflow |

A minimal "feed data in, consume it downstream" example:
```json
POST /workflows/
{
  "name": "demo-pipeline",
  "steps": [
    {
      "key": "input_1", "name": "input", "task_type": "input",
      "payload": { "data": "{\"keyword\": \"backend\"}" },
      "depends_on": []
    },
    {
      "key": "greet", "name": "build-greeting", "task_type": "python",
      "payload": { "code": "def main():\n    return {\"greeting\": \"hello {{steps.input_1.result.keyword}}\"}" },
      "depends_on": ["input_1"]
    }
  ]
}
```

**How data flows**

- `{{steps.<key>.result}}` / `{{steps.<key>.result.<field>}}`: pulls in an upstream step's result, substituted by the executor just before dispatch. **Step keys may only contain letters, digits, and underscores** — the substitution regex is `[a-zA-Z0-9_]+`
- `{{item}}` / `{{item.<field>}}`: the current item inside a `for_each` fan-out
- `{{items}}`: all collected results inside a `reduce_of` step
- If a payload references a step, that step must also appear in `depends_on` — otherwise creation is rejected, since there would be no guarantee it runs first

**Branching and failure**

- `depends_on` can list multiple keys, supporting branching and merging (a real DAG, not just a linear chain)
- `branch_of` + `branch_when` point at a `condition` step; only the side matching the condition's result runs, and the other side — along with everything downstream of it — is marked `cancelled`. This is the **expected outcome, not a workflow failure**
- When a node fails permanently (retries exhausted), all downstream nodes are automatically marked `cancelled` and the whole workflow is marked `failed`

**Output**: once a workflow completes, the successful results of every terminal node (nodes nothing else depends on) are collected into `workflows.result` as `{step_key: result}`, visible in the `GET /workflows/{id}` response and in the Result card on the detail page.

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
- **Workflows page**: Lists every workflow ever created; "New workflow" opens the [visual canvas builder](#visual-workflow-builder). Clicking into a workflow shows the same canvas as a read-only run view, with each node's live status, a Result card once everything completes, and one-click Re-run or promote-to-schedule.
- **Schedules page**: Manage recurring workflows with a cron expression input (including common presets like "every day at 9:00"), showing next/last run time, and letting you enable/disable or edit at any time. Step editing here still uses the older form-based UI — it hasn't been moved to the canvas yet.
- **Ops page**: Live monitoring metrics — queue depth, throughput trend, error rate, and more.
