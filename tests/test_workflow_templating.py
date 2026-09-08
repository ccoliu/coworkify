# ---------------------------------------------------
# Coworkify — Gap A/B templating and validation tests
#
# These cover the pure, DB-free logic: WorkflowCreate's validator (a pydantic
# model_validator needs no DB to run) and the render_* helpers in
# app/tasks/executor.py. The DB-integration side of Gap A/B (advance_workflow
# actually rendering and dispatching against real rows) was verified by hand
# against a live docker-compose stack — see the PR/commit description — and
# isn't duplicated here since this repo has no test-DB fixture yet.
# ---------------------------------------------------

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.workflow import WorkflowCreate
from app.tasks.executor import (
    _format_for_interpolation,
    payload_has_step_refs,
    render_reduce_payloads,
    render_step_refs,
)


def make_workflow(**overrides):
    base = {"name": "wf", "steps": []}
    base.update(overrides)
    return base


# --- WorkflowCreate: step-result references ------------------------------


def test_a_step_ref_requires_the_referenced_step_in_depends_on():
    with pytest.raises(ValidationError, match="加進 depends_on"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {"key": "a", "name": "a", "task_type": "echo", "payload": {}},
                    {
                        "key": "b",
                        "name": "b",
                        "task_type": "echo",
                        "payload": {"message": "{{steps.a.result}}"},
                        "depends_on": [],
                    },
                ]
            )
        )


def test_a_step_ref_is_accepted_once_the_dependency_is_declared():
    wf = WorkflowCreate.model_validate(
        make_workflow(
            steps=[
                {"key": "a", "name": "a", "task_type": "echo", "payload": {}},
                {
                    "key": "b",
                    "name": "b",
                    "task_type": "echo",
                    "payload": {"message": "{{steps.a.result}}"},
                    "depends_on": ["a"],
                },
            ]
        )
    )
    assert wf.steps[1].depends_on == ["a"]


def test_a_step_cannot_reference_an_unknown_step():
    # depends_on is deliberately empty here, not ["nope"] - putting the
    # nonexistent key in depends_on instead trips the earlier, generic
    # "depends_on references an unknown step" check first, which raises a
    # different, correct-but-different message than the one this test wants
    # to isolate (found the hard way: a wrong assumption about which
    # validator branch fires first, not a real bug).
    with pytest.raises(ValidationError, match="payload 參照了不存在的 step 'nope'"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {
                        "key": "a",
                        "name": "a",
                        "task_type": "echo",
                        "payload": {"message": "{{steps.nope.result}}"},
                        "depends_on": [],
                    }
                ]
            )
        )


def test_a_step_cannot_reference_its_own_result():
    # depends_on stays empty for the same reason as above: the self-reference
    # check in the payload-ref loop runs regardless, before the
    # "must be in depends_on" check, so it doesn't need "a" listed there.
    with pytest.raises(ValidationError, match="payload 不能參照自己的結果"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {
                        "key": "a",
                        "name": "a",
                        "task_type": "echo",
                        "payload": {"message": "{{steps.a.result}}"},
                        "depends_on": [],
                    }
                ]
            )
        )


def test_a_for_each_step_cannot_use_step_refs():
    with pytest.raises(ValidationError, match="動態展開步驟.*不支援"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {"key": "a", "name": "a", "task_type": "job_search", "payload": {}},
                    {
                        "key": "b",
                        "name": "b",
                        "task_type": "echo",
                        "payload": {"message": "{{steps.a.result}}"},
                        "for_each": "a",
                        "depends_on": ["a"],
                    },
                ]
            )
        )


# --- WorkflowCreate: reduce_of ---------------------------------------------


def test_reduce_of_must_point_at_a_for_each_step():
    with pytest.raises(ValidationError, match="不是動態展開步驟"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {"key": "a", "name": "a", "task_type": "echo", "payload": {}},
                    {"key": "b", "name": "b", "task_type": "echo", "payload": {}, "reduce_of": "a"},
                ]
            )
        )


def test_reduce_of_cannot_set_its_own_depends_on():
    with pytest.raises(ValidationError, match="不可自行指定 depends_on"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {"key": "a", "name": "a", "task_type": "job_search", "payload": {}},
                    {"key": "b", "name": "b", "task_type": "echo", "payload": {}, "for_each": "a"},
                    {
                        "key": "c",
                        "name": "c",
                        "task_type": "echo",
                        "payload": {},
                        "reduce_of": "b",
                        "depends_on": ["a"],
                    },
                ]
            )
        )


def test_a_step_cannot_be_both_for_each_and_reduce_of():
    with pytest.raises(ValidationError, match="不能同時 for_each 和 reduce_of"):
        WorkflowCreate.model_validate(
            make_workflow(
                steps=[
                    {"key": "a", "name": "a", "task_type": "job_search", "payload": {}},
                    {
                        "key": "b",
                        "name": "b",
                        "task_type": "echo",
                        "payload": {},
                        "for_each": "a",
                        "reduce_of": "a",
                    },
                ]
            )
        )


def test_a_valid_for_each_plus_reduce_pipeline_is_accepted():
    wf = WorkflowCreate.model_validate(
        make_workflow(
            steps=[
                {"key": "search", "name": "search", "task_type": "job_search", "payload": {}},
                {
                    "key": "tailor",
                    "name": "tailor",
                    "task_type": "tailor_cv",
                    "payload": {"title": "{{item.title}}"},
                    "for_each": "search",
                },
                {
                    "key": "combine",
                    "name": "combine",
                    "task_type": "echo",
                    "payload": {"message": "{{items}}"},
                    "reduce_of": "tailor",
                },
            ]
        )
    )
    assert wf.steps[2].reduce_of == "tailor"


# --- _format_for_interpolation --------------------------------------------


def test_format_for_interpolation_passes_strings_through_unquoted():
    assert _format_for_interpolation("hello") == "hello"


def test_format_for_interpolation_uses_json_not_python_repr():
    rendered = _format_for_interpolation({"a": 1, "b": [1, 2]})
    assert rendered == '{"a": 1, "b": [1, 2]}'
    assert "'" not in rendered, "must be valid JSON, not Python repr with single quotes"


# --- render_step_refs -------------------------------------------------


def test_render_step_refs_full_match_preserves_the_original_type():
    rendered = render_step_refs({"message": "{{steps.a.result}}"}, {"a": [1, 2, 3]})
    assert rendered["message"] == [1, 2, 3]
    assert isinstance(rendered["message"], list)


def test_render_step_refs_embedded_match_interpolates_as_text():
    rendered = render_step_refs({"message": "got: {{steps.a.result.name}}!"}, {"a": {"name": "Ann"}})
    assert rendered["message"] == "got: Ann!"


def test_render_step_refs_walks_nested_dicts_and_lists():
    rendered = render_step_refs(
        {"outer": {"inner": ["{{steps.a.result}}", "static"]}}, {"a": "value"}
    )
    assert rendered["outer"]["inner"] == ["value", "static"]


def test_render_step_refs_resolves_a_dotted_path():
    rendered = render_step_refs({"x": "{{steps.a.result.user.name}}"}, {"a": {"user": {"name": "Ann"}}})
    assert rendered["x"] == "Ann"


def test_render_step_refs_missing_key_resolves_to_none():
    rendered = render_step_refs({"x": "{{steps.a.result.nope}}"}, {"a": {"name": "Ann"}})
    assert rendered["x"] is None


# --- render_reduce_payloads -----------------------------------------------


def test_render_reduce_payloads_full_match_gives_the_raw_list():
    rendered = render_reduce_payloads({"message": "{{items}}"}, [{"x": 1}, {"x": 2}])
    assert rendered["message"] == [{"x": 1}, {"x": 2}]


def test_render_reduce_payloads_embedded_match_uses_json():
    rendered = render_reduce_payloads({"message": "results: {{items}}"}, [1, 2])
    assert rendered["message"] == "results: [1, 2]"


def test_render_reduce_payloads_adds_items_even_with_no_placeholder():
    rendered = render_reduce_payloads({"message": "no placeholder here"}, [1, 2])
    assert rendered["items"] == [1, 2]
    assert rendered["message"] == "no placeholder here"


# --- payload_has_step_refs -------------------------------------------------


def test_payload_has_step_refs_true_when_present_anywhere_nested():
    assert payload_has_step_refs({"a": {"b": ["{{steps.x.result}}"]}}) is True


def test_payload_has_step_refs_false_for_a_plain_payload():
    assert payload_has_step_refs({"message": "nothing special here"}) is False
