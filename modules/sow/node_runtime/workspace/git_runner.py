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
from pathlib import Path

DEFAULT_GIT_TIMEOUT_S = 120.0
_MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024  # 8 MiB per stream ceiling

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


def _truncate(value, text: bool):
    if value is None:
        return "" if text else b""
    if len(value) > _MAX_GIT_OUTPUT_BYTES:
        return value[-_MAX_GIT_OUTPUT_BYTES:]
    return value


def run_git(repo: Path, *args: str, timeout: float = DEFAULT_GIT_TIMEOUT_S, text: bool = True):
    """Run `git -C <repo> <args...>` bounded and non-interactively.

    Returns (returncode, stdout, stderr) (str when text=True, else bytes). Raises GitTimeout on
    deadline, after killing the whole process tree.
    """
    argv = ["git", "-C", str(repo), *args]
    env = {**os.environ, **_NONINTERACTIVE_ENV}
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=text, env=env, creationflags=creationflags)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise GitTimeout(tuple(args), timeout) from exc
    return proc.returncode, _truncate(out, text), _truncate(err, text)
