# ---------------------------------------------------
# Coworkify — python / shell steps in the restricted subprocess
#
# These run real subprocesses. They check the contract a workflow author
# relies on (main()'s return value, `inputs`, ./get_input) and the limits
# that keep user code contained: the worker's secrets are not inherited,
# runaway code is killed, oversized results are refused.
#
# The sandbox is POSIX-only by design (shell steps, rlimits via the
# `resource` module), so this module is skipped on Windows. CI and the
# worker containers run it on Linux.
# ---------------------------------------------------

from __future__ import annotations

import os
import sys
import time

import pytest

from app.tasks.handler import handle_python, handle_shell

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the sandbox is POSIX-only")


# --- python -------------------------------------------------------------------------


def test_main_return_value_becomes_value_with_its_type_intact():
    result = handle_python({"code": "def main():\n    print('working')\n    return {'n': 3, 'ok': True, 'none': None}"})

    assert result["value"] == {"n": 3, "ok": True, "none": None}
    assert result["stdout"].strip() == "working"
    assert result["exit_code"] == 0


def test_upstream_results_arrive_as_a_global_and_as_a_main_argument():
    inputs = {"input_1": {"repo": "x"}, "items": [1, 2]}

    as_global = handle_python({"code": "def main():\n    return inputs['items']", "inputs": inputs})
    as_argument = handle_python({"code": "def main(data):\n    return data['input_1']['repo']", "inputs": inputs})

    assert as_global["value"] == [1, 2]
    assert as_argument["value"] == "x"


def test_code_without_main_just_runs():
    result = handle_python({"code": "print(1 + 1)"})
    assert result["stdout"].strip() == "2"
    assert result["value"] is None


def test_a_large_return_value_is_not_truncated_through_stdout():
    # stdout 會被截到 4000 字；回傳值走檔案，不受影響
    result = handle_python({"code": "def main():\n    return 'x' * 10000"})
    assert len(result["value"]) == 10000


def test_a_return_value_over_1mb_is_refused():
    with pytest.raises(RuntimeError, match="over the 1024KB limit"):
        handle_python({"code": "def main():\n    return 'x' * (2 * 1024 * 1024)"})


def test_an_exception_fails_the_step_with_the_traceback():
    with pytest.raises(RuntimeError) as exc:
        handle_python({"code": "def main():\n    raise ValueError('bad row')"})
    assert "ValueError: bad row" in str(exc.value)


def test_worker_secrets_are_not_inherited(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("JWT_SECRET", "secret")

    result = handle_python({"code": "import os\ndef main():\n    return sorted(os.environ)"})

    assert "DATABASE_URL" not in result["value"]
    assert "JWT_SECRET" not in result["value"]


def test_runaway_code_is_killed_at_the_timeout():
    with pytest.raises(RuntimeError, match="Timed out|Killed by signal"):
        handle_python({"code": "while True:\n    pass", "timeout_seconds": 1})


def test_a_timeout_also_kills_background_children():
    # shell 裡丟到背景的程序不會跟著直接的子程序一起死，要整個 process group 一起殺
    with pytest.raises(RuntimeError, match="Timed out"):
        handle_shell({"command": "sleep 30 & echo $! > /tmp/coworkify-orphan.pid; wait", "timeout_seconds": 1})

    with open("/tmp/coworkify-orphan.pid") as f:
        pid = int(f.read())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_memory_is_capped():
    with pytest.raises(RuntimeError, match="MemoryError|Killed by signal"):
        handle_python({"code": "def main():\n    return len(bytearray(1024 * 1024 * 1024))"})


def test_each_run_gets_a_fresh_working_directory():
    write = handle_python({"code": "open('leftover.txt', 'w').write('x')"})
    read = handle_python({"code": "import os\ndef main():\n    return os.path.exists('leftover.txt')"})
    assert write["exit_code"] == 0
    assert read["value"] is False


# --- shell --------------------------------------------------------------------------


def test_shell_reads_upstream_values_with_get_input():
    result = handle_shell({
        "command": "echo \"$(./get_input input_1.repo) has $(./get_input items.1) items\"",
        "inputs": {"input_1": {"repo": "airflow"}, "items": [5, 7]},
    })
    assert result["stdout"].strip() == "airflow has 7 items"


def test_get_input_fails_loudly_on_a_missing_key():
    with pytest.raises(RuntimeError, match="no such key 'nope'"):
        handle_shell({"command": "set -e; ./get_input input_1.nope", "inputs": {"input_1": {}}})


def test_a_failing_command_fails_the_step():
    with pytest.raises(RuntimeError, match="Exited with code 3"):
        handle_shell({"command": "echo partial; exit 3"})


def test_python_and_shell_require_their_code():
    with pytest.raises(ValueError):
        handle_python({})
    with pytest.raises(ValueError):
        handle_shell({})
