"""One bounded, non-interactive git subprocess wrapper (CR-028).

Several orchestration paths (worktree create/merge, candidate packaging, the OpenCode driver's
containment checks) called `git` directly with no timeout. A credential helper prompt, a stuck
`index.lock`, a hook that waits, or a damaged repository could hang orchestration indefinitely. Every
git invocation now routes through `run_git`, which:

  * runs with a NON-INTERACTIVE environment so git never blocks on a credential/askpass prompt,
  * enforces an operation-specific deadline,
  * kills the WHOLE process tree on timeout (git spawns helpers/hooks — killing only the direct
    child leaves them running), and
  * bounds retained output.

Windows-only product (taskkill tree cleanup mirrors the OpenCode driver).
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

DEFAULT_GIT_TIMEOUT_S = 120.0
_MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024  # 8 MiB per stream ceiling
_READ_CHUNK_BYTES = 65536

# A git call must never block on interactive credential/askpass prompts.
_NONINTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GCM_INTERACTIVE": "Never",
    "GIT_ASKPASS": "echo",
    "SSH_ASKPASS": "echo",
    "GIT_PAGER": "cat",
}


class GitTimeout(Exception):
    """A git invocation exceeded its deadline; its whole process tree was killed."""

    def __init__(self, args: tuple[str, ...], timeout: float) -> None:
        self.args_tuple = args
        self.timeout = timeout
        super().__init__(f"git {' '.join(args)} timed out after {timeout:g}s")


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


def _drain(stream, sink: dict) -> None:
    """SW-20: read a pipe in chunks, retaining only the last _MAX_GIT_OUTPUT_BYTES — so a huge diff,
    log or noisy hook is bounded to the ceiling as it is produced, never buffered whole in memory.
    Records whether truncation occurred so the ceiling is an honest bound, not a silent drop."""
    buf = bytearray()
    truncated = False
    try:
        while True:
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            buf += chunk
            if len(buf) > _MAX_GIT_OUTPUT_BYTES:
                del buf[:len(buf) - _MAX_GIT_OUTPUT_BYTES]
                truncated = True
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass
        sink["buf"] = bytes(buf)
        sink["truncated"] = truncated


def run_git(repo: Path, *args: str, timeout: float = DEFAULT_GIT_TIMEOUT_S, text: bool = True):
    """Run `git -C <repo> <args...>` bounded and non-interactively.

    Returns (returncode, stdout, stderr) (str when text=True, else bytes). Output is drained
    incrementally into a bounded tail (SW-20), so peak memory stays near the per-stream ceiling even
    when git emits far more. Raises GitTimeout on deadline, after killing the whole process tree.
    """
    argv = ["git", "-C", str(repo), *args]
    env = {**os.environ, **_NONINTERACTIVE_ENV}
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Binary pipes so the byte ceiling is exact regardless of `text`; the bounded tail is decoded
    # once at the end (cheap: at most the ceiling).
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, creationflags=creationflags)
    out_sink: dict = {}
    err_sink: dict = {}
    t_out = threading.Thread(target=_drain, args=(proc.stdout, out_sink), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, err_sink), daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        raise GitTimeout(tuple(args), timeout) from exc
    # The child has exited; the drain threads see EOF and finish promptly.
    t_out.join(timeout=10)
    t_err.join(timeout=10)
    out = out_sink.get("buf", b"")
    err = err_sink.get("buf", b"")
    if text:
        out = out.decode("utf-8", errors="replace")
        err = err.decode("utf-8", errors="replace")
    return proc.returncode, out, err
