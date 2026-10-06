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
- **Definitions separate from runs**: A workflow is a reusable "production line" (`workflow_definitions`); each execution is a run carrying its own input. A run keeps a snapshot of the steps and the definition version it used, so editing a definition later never rewrites history.
- **Form-driven input**: A definition can declare an `input_schema` (field names, types, defaults, required flags); the frontend generates and validates a form before each run, and the values enter the workflow through its `input` node. Raw material can also come from the web — `fetch_page` fetches a URL and extracts structured fields by CSS selector.
- **Type-safe data passing**: `python` steps read every upstream result from a global `inputs` variable (types fully preserved), and `shell` steps read values with `$(./get_input <path>)`. Neither goes through string interpolation, so there is no type loss and no command injection.
- **Explicit output**: When a run finishes, every terminal node's result is collected into `workflows.result` instead of being scattered across individual task logs.
- **Re-run and resume**: `POST /workflows/{id}/rerun` creates a new run from the same snapshot and input; `POST /workflows/{id}/retry` resumes the same run from the point of failure without re-running upstream steps that already succeeded.
- **Cron-based recurring schedules**: A schedule points directly at a workflow definition and carries its own input, so the next trigger always uses the latest version of the definition. Celery Beat checks periodically and creates and dispatches runs when due, with timezone handling consistent across the app.
- **Redis sliding-window rate limiting**: Request rate is tracked per logged-in user, protecting the system from any single source overwhelming it.
- **Real-time task status push**: WebSocket + Redis Pub/Sub push task status changes instantly, no frontend polling required.
- **Account authentication**: Register/login with bcrypt-hashed passwords and JWT session tokens; users can self-register from the frontend.
- **Live Ops dashboard**: The React frontend visualizes queue depth, throughput, and error rate in real time; the run detail page renders the same canvas in read-only mode, colouring nodes by task status and updating live over WebSocket.

---

## Supported Task Handlers

This list is defined in `app/tasks/catalog.py` and served — along with each field's spec — from `GET /tasks/types`. The frontend's task-creation form and the workflow property panel are both rendered from it, so **adding a task type requires no frontend changes**.

| Task Type (task_type) | Description |
| :--- | :--- |
| `input` | The workflow's data entry point. At run time it is replaced with the values from the Run form (or, if the definition declares no `input_schema`, the JSON hard-coded in its payload). Its result is the raw material for the whole workflow |
| `fetch_page` | Fetches a web page and extracts fields by CSS selector — another source of raw material. With an item selector set it returns a list that can feed `for_each` directly. It reuses `http_request`'s SSRF checks and re-validates every redirect hop |
| `python` | Runs a snippet of Python in a restricted subprocess. Define a `main()` and its return value automatically becomes the result's `result.value`; upstream results are in the global `inputs` (or declare `main(inputs)`) |
| `shell` | Runs a shell command in a restricted subprocess. Upstream results are in `inputs.json` in the working directory; read a single value with `$(./get_input input_1.price)` |
| `http_request` | Sends an HTTP request; targets pointing at private networks or cloud metadata endpoints are blocked |
| `condition` | Evaluates a condition and returns `passed=true/false`. It always succeeds — downstream steps use `branch_of` + `branch_when` to point at it and implement if/else |
| `agent_step` | Runs a [Codoctopus](https://github.com/ccoliu/Codoctopus) agent step — the payload carries `role` (system prompt), `instruction`, an optional `model` (`"provider:model"`), and `tools` (`read_file` / `write_file` / `list_files` / `http_request` / `run_tests`). Setting `output_fields` (e.g. `{"fixable": "boolean", "effort": ["small", "large"]}`) switches to structured output: the result is that object itself, so downstream code can read `inputs["judge"]["fixable"]`. Requires `codoctopus` to be installed in the worker environment; see the note below. |
| `notify` | Sends a Discord webhook notification (title, message, link, and a level that sets the colour), usually as a workflow's last step. The webhook URL defaults to the worker's `DISCORD_WEBHOOK_URL` environment variable — it is effectively a password, so keep it out of workflow definitions |

> The worker must be able to `import codoctopus` for `agent_step` to work. For local development: `pip install -e "<codoctopus-checkout>[anthropic]"` (the `[anthropic]` extra is required — the SDK is an optional dependency; `[openai]` / `[gemini]` / `[all]` also work, or point at an `ollama:` model and install no SDK at all).
>
> For containerized deployments you don't need codoctopus in every worker — `agent_step` is the only task type that needs it, so it is routed to a dedicated `agent_step` queue consumed only by the `worker-agent` service (see `Dockerfile.agent`), started with `docker compose --profile agent up`. All other workers are unaffected. To use it, set `CODOCTOPUS_PATH` (pointing at your local Codoctopus checkout) and `AGENT_STEP_DEFAULT_MODEL` in `.env`, plus whatever the provider needs (e.g. `ANTHROPIC_API_KEY`, or `OPENAI_BASE_URL` for a local OpenAI-compatible server). If an `agent_step` is scheduled in an environment with no worker-agent running it simply stays `pending` — it will not fail, and no other worker will pick it up by mistake.

> `python` and `shell` run in a restricted subprocess (timeout, CPU / memory limits, a cleared environment — see `app/tasks/sandbox.py`). **This is not a full sandbox** — it still shares the worker's filesystem and network, so don't point it at untrusted input.

The early demo handlers (`echo`, `heavy_computation`, `flaky_task`, `job_search`, …) are still registered in `TASK_REGISTRY` — existing rows and tests reference them — but are deliberately left out of the catalog above, so they don't appear in the frontend's task-type picker.

---

## Visual Workflow Builder

![Workflow builder](<workflow-builder.png>)

`/workflows/new` is a React Flow canvas, auto-laid out with dagre. Existing definitions open on the same canvas at `/definitions/{id}/edit` (auto-laid out on load); saving replaces the whole definition and bumps its version:

- **Build by dragging**: Drag a task type from the left-hand palette onto the canvas to create a node; draw an edge between two nodes to declare a `depends_on` relationship
- **Branching is just wiring**: A `condition` node exposes `true` and `false` outputs on its right edge — whichever one you drag from sets that step's `branch_of` / `branch_when` automatically, with no manual step-key bookkeeping
- **Fan-out and fan-in**: For each / Reduce from in the property panel set up fan-out and fan-in, drawn on the canvas as dashed edges showing where the data comes from. A reduce step rejects manually drawn incoming edges (its dependencies are decided by the system after expansion)
- **Property panel**: The right-hand form is generated from the field specs in `GET /tasks/types`; the code fields on `python` / `shell` are CodeMirror editors (syntax highlighting, auto-indent, expand-to-modal editing, and direct `.py` upload)
- **Input field editor**: Above the canvas you define the workflow's `input_schema` (key / label / type / default / required / options). The run and schedule forms are generated from it, in the same shape as the field specs from `GET /tasks/types`
- **Live validation**: The frontend mirrors the backend's `validate_dag` rules (see `frontend/src/features/workflows/validateGraph.ts`), surfacing problems on the nodes and above the canvas and blocking submission while any remain. The backend copy is still the final gate — the two must be maintained together. There are also non-blocking yellow warnings, e.g. a `python` step still using `{{steps...}}` templates in its code
- **Keyboard shortcuts**: `Delete` removes the selected node or edge, `Esc` clears the selection, `Ctrl+D` duplicates a node, `L` re-runs auto-layout, `F` fits the view

The run detail page renders **the same canvas** in read-only mode to show an actual run: nodes are coloured by task status and update live over WebSocket, the branch that wasn't taken is dimmed out as `cancelled`, and clicking any node shows its payload and error message.

![Workflow run view](<workflow-run.png>)

The run above is a nested-branch workflow: `condition_1` took the `false` path into `python_2`, and `condition_2` took `true` into `shell_2`. The untaken `shell_1` and `shell_3` were marked `cancelled` along with their downstream nodes, yet the workflow as a whole is still `Success` — a branch not being taken is the expected outcome, not a failure.

---

## Case Study: A GitHub Issue Triage Pipeline

A pipeline that runs every hour: it pulls the issues opened in [apache/airflow](https://github.com/apache/airflow) during the past hour, has a local LLM judge how fixable each one is, sorts them into tiers, and posts the result to Discord. New issues on popular projects get claimed quickly; the point is to see the ones worth picking up before someone else does.

![Issue triage pipeline](<pipeline-canvas.png>)

| Step | Type | What it does |
| :--- | :--- | :--- |
| `input_1` | `input` | Parameters for this run: `repo`, `hours` (window length), `max_issues` |
| `window` | `python` | Computes an hour-aligned time window and builds the GitHub Search API URL |
| `fetch` | `http_request` | Calls the Search API |
| `shape` | `python` | Turns the response into a list of issues and decides in code whether each one is already being handled: the author ticked "willing to submit a PR" in the issue form, or the Timeline API shows a PR that will close it |
| `judge` | `agent_step` | `for_each: shape` — one LLM call per issue, in parallel, returning fixed fields via structured output |
| `digest` | `python` | `reduce_of: judge` — pairs each issue with its verdict in order, sorts them into 🟢 / 🟡 / ⚪ tiers, and builds the message |
| `condition_3` | `condition` | Continues only when `digest` reports `has_news` |
| `notify` | `notify` | Sends the Discord notification |

Some design decisions:

- **The model states facts; code decides the tier.** `judge`'s `output_fields` only ask what the issue says: is it a feature request, does it include reproduction steps, does it point at a specific cause, how large is the change. Whether an issue is "ready to pick up" or "needs investigation first" is decided by a few `if`s in `digest`. Asked "how fixable is this?" directly, a 9B local model is erratic; asked "does the body contain a stack trace?", it is far more consistent. Changing the tier rules also means editing code rather than rewriting a prompt and re-checking how the model behaves.
- **Issues someone has already claimed never reach the model's judgement.** If the author ticked "willing to submit a PR", or a PR that closes the issue already exists, the issue goes to ⚪ regardless of what the model says — these are facts that can be looked up, not guessed.
- **The time window is aligned to the hour.** Each run queries `[top of the hour - hours, top of the hour)`, with one second taken off the upper bound because GitHub range queries include both ends. Even if a trigger fires a few minutes late, consecutive windows still line up end to end — nothing is counted twice or missed.
- **No new issues still converges normally.** When `shape` returns an empty list, `judge` expands to 0 items, `digest` still runs and returns `has_news: false`, and `condition_3` stops the notification. In practice most hours take this path.
- **Data passing doesn't go through string templates.** `digest` simply does `zip(inputs["shape"], inputs["judge"])`; the reduce step receives results in item order, regardless of the order in which the individual verdicts finished.

![Discord notification](<pipeline-discord.png>)

The model is `qwen/qwen3.5-9b` running locally in LM Studio behind an OpenAI-compatible API (`AGENT_STEP_DEFAULT_MODEL=openai:qwen/qwen3.5-9b`, with `OPENAI_BASE_URL` pointing at LM Studio), executed by `worker-agent`. The schedule's cron is `5 * * * *` (five minutes past every hour). From 2026-09-22 through 2026-09-24 it ran 55 times: 49 runs found no new issues, 6 sent a notification, and 17 issues were judged in total. Two more runs failed because LM Studio had unloaded the model and `judge` exhausted its retries — not a pipeline problem; once fixed, `/retry` resumes such a run from the failed step.

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

After registering an account on the login page, open **Getting started** in the sidebar (http://localhost:5173/getting-started) — it walks through a complete example from building a workflow to running it, and is the fastest way in.

### 3. Run the tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```
Run these on the host, not inside a container. Most tests need no external services. `tests/test_executor_workflow.py` holds the executor integration tests: they connect to the Postgres at `.env`'s `DATABASE_URL`, create a separate `<POSTGRES_DB>_test` database, and walk workflows through dispatch, `inputs` assembly, for_each / reduce (including expanding to 0 items), branch cancellation, failure, and retry. Celery dispatch is replaced with a recorder, so no worker or Redis is needed. If the database is unreachable these tests are skipped — add `-rs` to see why — and `TEST_DATABASE_URL` points them somewhere else.

> If a native Postgres installed on the host also listens on 5432, `localhost:5432` reaches that one instead and fails with `password authentication failed`. Change both `POSTGRES_PORT` and `DATABASE_URL` in `.env` to another port (e.g. 5433), then run `docker compose up -d postgres`.

### 4. Run a Locust load test
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
| `GET` | `/tasks/{task_id}/logs` | The task's full execution history (oldest first): one entry per attempt, with error message, result, and execution time |
| `DELETE` | `/tasks/{task_id}` | Delete a task |

### Workflow Definitions (production lines)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/definitions/` | Create a workflow definition (`steps` plus an optional `input_schema`); it does not run by itself |
| `GET` | `/definitions/` | Paginated list of definitions, with run counts and the latest run |
| `GET` | `/definitions/{definition_id}` | Look up a single definition |
| `PUT` | `/definitions/{definition_id}` | Replace the whole definition; the version bumps when `steps` or `input_schema` change |
| `DELETE` | `/definitions/{definition_id}` | Delete a definition (its schedules go with it; past runs are kept) |
| `POST` | `/definitions/{definition_id}/runs` | Run it once with an `input`, returning the new run |
| `GET` | `/definitions/{definition_id}/runs` | Paginated list of this definition's runs |

### Workflow Runs (individual executions)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/workflows/` | Paginated list of all runs |
| `GET` | `/workflows/{workflow_id}` | Overall status, the live status of each node's task, and this run's `input` and final `result` |
| `POST` | `/workflows/{workflow_id}/rerun` | Run again with the same snapshot and the same input, creating a **new** run; the previous one is kept intact |
| `POST` | `/workflows/{workflow_id}/retry` | Resume the **same** run from the point of failure: the failed steps and the downstream steps they cancelled go back to pending, while upstream steps that succeeded are not re-run |
| `POST` | `/workflows/{workflow_id}/promote-to-schedule` | Register this run's definition and input as a recurring cron schedule |
| `DELETE` | `/workflows/{workflow_id}` | Delete this run |
| `POST` | `/workflows/` | **Legacy path**: create a one-off run that belongs to no definition, kept for existing scripts and load tests |

A minimal "feed data in, consume it downstream" example:
```json
POST /definitions/
{
  "name": "demo-pipeline",
  "input_schema": [
    { "key": "keyword", "label": "Keyword", "kind": "string", "required": true }
  ],
  "steps": [
    {
      "key": "input_1", "name": "input", "task_type": "input",
      "payload": { "data": "{}" },
      "depends_on": []
    },
    {
      "key": "greet", "name": "build-greeting", "task_type": "python",
      "payload": { "code": "def main():\n    return {'greeting': 'hello ' + inputs['input_1']['keyword']}" },
      "depends_on": ["input_1"]
    }
  ]
}
```
```json
POST /definitions/{definition_id}/runs
{ "input": { "keyword": "backend" } }
```

**How data flows**

- `python` steps: the global `inputs` is `{step_key: upstream result}` covering **every ancestor step** (not just direct parents), with types fully preserved; when the upstream is a `python` step you get its `main()` return value. You can also declare `def main(inputs):`
- `shell` steps: the same data is written to `inputs.json` in the working directory; read a single value with `$(./get_input input_1.keyword)` (the dotted path mirrors Python's brackets)
- `{{steps.<key>.result}}` / `{{steps.<key>.result.<field>}}`: string templates for the other task types (`http_request`, `condition`, …), substituted by the executor just before dispatch. **Step keys may only contain letters, digits, and underscores** — the substitution regex is `[a-zA-Z0-9_]+`. This is string interpolation and loses types, so prefer the two options above whenever the value comes from user input
- `{{item}}` / `{{item.<field>}}`: the current item inside a `for_each` fan-out
- `{{items}}`: all collected results inside a `reduce_of` step. A `python` reduce step reads `inputs["<for_each step key>"]` instead, which is the list of results **in item order** (regardless of which items finished first), ready to `zip` with the for_each source list

**Fan-out and fan-in (for_each / reduce)**

- A step with `for_each: <key>` expands into N tasks, one per item of that step's result (which must be a list; for a python step, its `main()` return value), running in parallel
- Another step with `reduce_of: <for_each step key>` waits until every expanded task has finished and collects their results into a list — that's fan-out / fan-in
- A reduce step's dependencies are decided by the system after expansion, so it can't set its own `depends_on`, and it can't also be a for_each or branch step
- On the canvas both are set in the right-hand property panel (For each / Reduce from) and drawn as dashed edges labelled `for each` and `reduce`, distinct from the solid edges of regular dependencies
- If a payload references a step through a template, that step must be in `depends_on` — otherwise creation is rejected, since there would be no guarantee it runs first

**Branching and failure**

- `depends_on` can list multiple keys, supporting branching and merging (a real DAG, not just a linear chain)
- `branch_of` + `branch_when` point at a `condition` step; only the side matching the condition's result runs, and the other side — along with everything downstream of it — is marked `cancelled`. This is the **expected outcome, not a workflow failure**
- When a node fails permanently (retries exhausted), all downstream nodes are automatically marked `cancelled` and the whole workflow is marked `failed`. After fixing the problem, `/retry` re-runs only the failed part — branches that weren't taken stay `cancelled` and are never woken up by mistake

**Output**: once a workflow completes, the successful results of every terminal node (nodes nothing else depends on) are collected into `workflows.result` as `{step_key: result}`, visible in the `GET /workflows/{id}` response and in the Result card on the detail page.

### Schedules (recurring runs)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/schedules/` | Create a schedule bound to a cron expression: it points at a definition (`definition_id`) and carries the `input` to use each time |
| `GET` | `/schedules/` | List all schedules |
| `GET` | `/schedules/{schedule_id}` | Look up a single schedule |
| `PATCH` | `/schedules/{schedule_id}` | Update the name, cron expression, input, or enabled state |
| `DELETE` | `/schedules/{schedule_id}` | Delete a schedule |

Celery Beat checks all `enabled=true` schedules once a minute; when `next_run_at` is due, it creates a new run from **the definition as it is at that moment**, dispatches its root nodes, and computes the next run time from the cron expression. Because a schedule stores a `definition_id` rather than a copy of the steps, edits to the definition take effect on the next trigger. The cron expression is interpreted in the app's configured timezone (`Asia/Taipei`), consistent with how `next_run_at` is displayed and compared.

A schedule's `input` is validated against the `input_schema` when it is saved, and again at trigger time. If a definition change makes the input invalid, that trigger is skipped with the reason logged, and the schedule still moves on to its next time, so other schedules are never blocked.

### Other
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | API server health check |
| `WS` | `/ws/tasks` | WebSocket for real-time task status updates (Redis Pub/Sub) |

Every endpoint under `/tasks`, `/definitions`, `/workflows`, and `/schedules` requires a JWT obtained via `/auth/register` or `/auth/login`, sent in the `Authorization: Bearer <token>` header, and is rate-limited per logged-in identity via Redis sliding-window limiting.

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

> These numbers are not directly comparable with an earlier version's 288 RPS / 38.9 ms: the two runs used different concurrency (a little over 100 users then, 150 now), the code changed considerably in between, and the earlier run predates the fix for the rate limiter's event-loop-blocking bug. The first attempt at this re-run had 83% `403` responses because the container hadn't re-read `.env` and was still using an old API key; those numbers were discarded, and the table above comes from the corrected run in which every request passed authentication. The current bottleneck is believed to be that `/tasks` uses synchronous (`def`, not `async def`) SQLAlchemy calls, which FastAPI runs in a thread pool — this tends to queue up under high concurrency. Switching the DB layer to async (`asyncpg` + SQLAlchemy async session) is the next lever to pull for more throughput.
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
- **Getting started page**: An in-app tutorial that walks through a real example (input → python check → condition branch → a shell step on each branch) from building to running, reading results, and scheduling, plus a summary of how data is passed and a troubleshooting guide.
- **Tasks page**: Task list, filtering, and single-task creation, with status updated live over WebSocket.
- **Workflows page**: The top half lists every workflow definition (run count, status of the latest run, with Run / Edit shortcuts); the bottom half lists recent runs. "New workflow" opens the [visual canvas builder](#visual-workflow-builder).
- **Definition detail page**: A Run form generated from the `input_schema`, an overview of the steps, and this definition's runs.
- **Run detail page**: The same canvas in read-only mode showing the actual run, with each node's live status; once finished it shows this run's Input and Result, and offers Re-run, Retry from the point of failure, or promotion to a schedule. Clicking a node opens a side drawer with its payload and full execution history (including every retry's error message, and it survives a page refresh).
- **Schedules page**: Manage recurring runs — pick a workflow definition, enter a cron expression (including common presets like "every day at 9:00") and the input this schedule should use; shows next/last run time and lets you enable/disable or edit at any time.
- **Ops page**: Live monitoring metrics — queue depth, throughput trend, error rate, and more.
