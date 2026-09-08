# ---------------------------------------------------
# Coworkify — agent_step handler tests
#
# handle_agent_step is a plain sync function (it wraps its own asyncio.run
# internally, same as every other Celery task handler in this module), so it
# can be called directly here with no DB, no Celery worker, and no Redis —
# exactly like the other handlers in this file could be, if they had tests.
#
# A scripted codoctopus provider stands in for a real LLM (see codoctopus's
# own test suite for the same pattern) so this needs no API key.
# ---------------------------------------------------

from __future__ import annotations

import pytest

from codoctopus.llm import register_provider
from codoctopus.llm.base import Provider
from codoctopus.llm.types import Completion, StopReason, ToolCall

from app.tasks.handler import TASK_REGISTRY, get_task_handler, handle_agent_step


class ScriptedProvider(Provider):
    """Replies with a fixed string, ignoring tools entirely."""

    name = "scripted"
    default_model = "scripted-1"

    async def _complete(self, messages, *, system, tools, output_schema, max_tokens, **kwargs):
        return Completion(text=f"handled: {messages[-1].content}", model=self.model)


class ToolCallingProvider(Provider):
    """First turn: call read_file. Second turn: report the tool result."""

    name = "toolcalling"
    default_model = "toolcalling-1"

    def __init__(self, model=None, **options):
        super().__init__(model, **options)
        self.turn = 0

    async def _complete(self, messages, *, system, tools, output_schema, max_tokens, **kwargs):
        self.turn += 1
        if self.turn == 1:
            return Completion(
                text="",
                model=self.model,
                stop_reason=StopReason.TOOL_USE,
                tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "note.txt"})],
            )
        return Completion(text=f"file said: {messages[-1].tool_results[0].content}", model=self.model)


@pytest.fixture(autouse=True, scope="module")
def _register_scripted_providers():
    register_provider("scripted", lambda model=None, **kw: ScriptedProvider(model, **kw))
    register_provider("toolcalling", lambda model=None, **kw: ToolCallingProvider(model, **kw))


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "note.txt").write_text("hello from disk", encoding="utf-8")
    return tmp_path


# --- registration ------------------------------------------------------


def test_agent_step_is_registered():
    assert "agent_step" in TASK_REGISTRY
    assert get_task_handler("agent_step") is handle_agent_step


# --- payload validation --------------------------------------------------


def test_missing_role_raises():
    with pytest.raises(ValueError, match="role and payload.instruction are required"):
        handle_agent_step({"instruction": "do something"})


def test_missing_instruction_raises():
    with pytest.raises(ValueError, match="role and payload.instruction are required"):
        handle_agent_step({"role": "be helpful"})


# --- the plain (no-tools) path -------------------------------------------


def test_returns_the_agents_final_text_as_output():
    result = handle_agent_step({"role": "be terse", "instruction": "say hi", "model": "scripted:x"})

    assert result == {"output": "handled: say hi"}


def test_defaults_to_the_env_default_model_when_none_given(monkeypatch):
    monkeypatch.setenv("AGENT_STEP_DEFAULT_MODEL", "scripted:x")

    result = handle_agent_step({"role": "be terse", "instruction": "say hi"})

    assert result == {"output": "handled: say hi"}


# --- the tools path -----------------------------------------------------


def test_a_tool_actually_runs_not_just_gets_mentioned(workspace):
    result = handle_agent_step(
        {
            "role": "read files",
            "instruction": "read note.txt",
            "model": "toolcalling:x",
            "tools": ["read_file"],
            "workspace": str(workspace),
        }
    )

    assert result == {"output": "file said: hello from disk"}


def test_an_unknown_tool_name_raises_with_the_available_list():
    with pytest.raises(ValueError, match="Unknown tool.*delete_everything"):
        handle_agent_step(
            {"role": "r", "instruction": "i", "model": "scripted:x", "tools": ["delete_everything"]}
        )
