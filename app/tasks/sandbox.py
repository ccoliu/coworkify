# ---------------------------------------------------
# Coworkify — restricted subprocess execution for the python/shell task types
#
# This is NOT a real sandbox: the child process still shares the worker
# container's filesystem and network namespace. What this module actually
# buys:
#   - a hard wall-clock timeout
#   - CPU time / memory / process-count / output-size limits (Linux rlimits)
#   - a stripped environment, so DATABASE_URL / JWT_SECRET / API keys etc.
#     sitting in the worker's own os.environ can't leak into user code
#   - a throwaway temp directory as the working directory
# A determined attacker with code execution here can still reach anything
# the worker container itself can reach over the network. That trade-off
# was a deliberate choice for this project's risk level, not an oversight —
# see the "python/shell sandboxing" decision in project memory.
# ---------------------------------------------------

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - resource is POSIX-only
    resource = None  # type: ignore[assignment]

MAX_TIMEOUT_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 4000
_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024  # 256MB address space
_FSIZE_LIMIT_BYTES = 10 * 1024 * 1024  # 10MB max file a child process may write
_NPROC_LIMIT = 32

# 只留執行必要的環境變數；worker 本身的 DATABASE_URL / REDIS_URL / JWT_SECRET /
# ANTHROPIC_API_KEY 等機密一律不繼承給使用者程式碼。
_ALLOWED_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL")


def _minimal_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if k in _ALLOWED_ENV_KEYS}


def _clamp_timeout(timeout_seconds: Any) -> int:
    try:
        value = int(timeout_seconds)
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT_SECONDS
    return max(1, min(value, MAX_TIMEOUT_SECONDS))


def _rlimits(cpu_seconds: int):
    if resource is None:
        return None

    def _set_limits():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (_FSIZE_LIMIT_BYTES, _FSIZE_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (_NPROC_LIMIT, _NPROC_LIMIT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _set_limits


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"


def run_sandboxed(build_args, *, shell: bool, timeout_seconds: Any) -> dict[str, Any]:
    """跑一個受限的 subprocess，回傳 {stdout, stderr, exit_code}。
    非 0 exit code 會被視為失敗，丟出 RuntimeError（附帶 stdout/stderr 摘要）。

    build_args 可以是現成的 command（list[str] 或 shell 字串），也可以是
    callable(tmpdir: str) -> command——後者可以在拿到 tmpdir 之後才把使用者
    程式碼寫進去，讓「寫檔的地方」跟「執行時的 cwd」是同一個乾淨的暫存目錄。
    """
    timeout = _clamp_timeout(timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="coworkify-sandbox-") as tmpdir:
        args = build_args(tmpdir) if callable(build_args) else build_args
        try:
            proc = subprocess.run(
                args,
                shell=shell,
                cwd=tmpdir,
                env=_minimal_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_rlimits(timeout),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out after {timeout}s. "
                f"stdout so far: {_truncate((exc.stdout or ''))!r}"
            ) from exc

    stdout = _truncate(proc.stdout or "")
    stderr = _truncate(proc.stderr or "")

    if proc.returncode < 0:
        # 負的 returncode = 被訊號殺掉。常見成因是 RLIMIT_CPU 觸發的 SIGKILL——
        # 這個機制常常搶在 subprocess.run 自己的 timeout= 機制前面先動手，
        # 導致這裡走的是「正常拿到已死 process」而不是 TimeoutExpired 那個分支。
        import signal

        try:
            sig_name = signal.Signals(-proc.returncode).name
        except ValueError:
            sig_name = str(-proc.returncode)
        raise RuntimeError(
            f"Killed by signal {sig_name} (likely hit the timeout or a resource limit).\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Exited with code {proc.returncode}.\nstdout: {stdout}\nstderr: {stderr}"
        )

    return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}


def python_command(code: str, tmpdir: str) -> list[str]:
    script_path = Path(tmpdir) / "script.py"
    script_path.write_text(code, encoding="utf-8")
    return [sys.executable, "-I", str(script_path)]
