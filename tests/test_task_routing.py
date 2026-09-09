# ---------------------------------------------------
# Coworkify — task_type -> Celery queue routing
#
# agent_step is the only task_type that needs codoctopus (and its LLM SDKs)
# installed in the worker's environment. Routing it to its own queue lets a
# dedicated worker consume just that queue, so the rest of the worker fleet
# never needs codoctopus at all. See docker-compose.yml's worker-agent
# service and the `worker` service's `-Q celery` flag for the deployment
# side of this; this file only covers the routing decision itself.
# ---------------------------------------------------

from __future__ import annotations

import uuid

from app.models.task import Task
from app.tasks.executor import dispatch_task, queue_for_task_type


def test_agent_step_routes_to_its_own_queue():
    assert queue_for_task_type("agent_step") == "agent_step"


def test_other_task_types_route_to_the_default_queue():
    for task_type in ("echo", "http_request", "job_search", "tailor_cv", "job_apply", "heavy_computation"):
        assert queue_for_task_type(task_type) == "celery"


def test_dispatch_task_sends_agent_step_to_the_agent_step_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.tasks.executor.execute_task.apply_async",
        lambda args, priority, queue: calls.append({"args": args, "priority": priority, "queue": queue}),
    )

    task = Task(id=uuid.uuid4(), name="do agent thing", task_type="agent_step", priority=5)
    dispatch_task(task)

    assert calls == [{"args": [str(task.id)], "priority": 5, "queue": "agent_step"}]


def test_dispatch_task_sends_everything_else_to_the_default_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.tasks.executor.execute_task.apply_async",
        lambda args, priority, queue: calls.append({"args": args, "priority": priority, "queue": queue}),
    )

    task = Task(id=uuid.uuid4(), name="say hi", task_type="echo", priority=3)
    dispatch_task(task)

    assert calls == [{"args": [str(task.id)], "priority": 3, "queue": "celery"}]
