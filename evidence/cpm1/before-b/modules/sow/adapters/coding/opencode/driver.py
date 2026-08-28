"""Drive OpenCode for real in an isolated worktree, from scoped MCP context. Phase 14C `.worktree`.

The chain this module proves (directive §9 table 14C, middle cell):

    scoped MCP context  →  isolated worktree modification  →  tests run

The CANDIDATE artifact submission + controlled merge is the NEXT sub-step (`.gate`); this one stops
at "the worktree has been driven and its tests have run".

`OpenCodeDriver` is deterministic ORCHESTRATION around a real `opencode run` subprocess. The
subprocess call is injected as a `Runner`, so the deterministic suite proves every governance
property with a scripted fake while the live integration test passes the real subprocess runner —
the same mock-first/real-live split the frontier (`claude_code.py`) and `.harness` layers use.

Load-bearing properties, all enforced in code and fail-closed (Buildout Directive §4):

  - **Scoped context, never the full transcript (invariant 8).** `read_scoped_objective` fetches
    EXACTLY the one assigned MCP entry (`get_content` by entry_id). The driver never sweeps the
    store, never blanket-forwards the conversation.

  - **Isolated worktree modification (Phase 10; invariants 29, 1).** OpenCode is pinned to the
    node's OWN git worktree via `--dir <worktree>` + `cwd`. Changes are read back with `git status`
    INSIDE the worktree; the base trunk working tree is checked for any modification outside the
    worktree — a change there flips `escaped=True` and is logged (and if the check itself cannot
    run, `escaped` is forced True, `containment_verified=False` — fail closed, never read as
    "clean"). Honesty per U10: this detects escapes into the BASE-TRUNK working tree only; it is a
    *detected* escape via worktree scoping + a git-status diff, NOT an OS syscall sandbox around a
    rogue subprocess (a write elsewhere on disk is out of scope here). The node's own
    `WorkspaceBinding` path guard governs the DRIVER's filesystem calls (and worktree.py's commit
    path); it is NOT applied to the spawned `opencode` subprocess.

  - **U30 discharged — OpenCode config isolation.** OpenCode reads provider config from
    `opencode.json`/`OPENCODE_CONFIG`, not only the env. `write_scoped_opencode_config` writes a
    SESSION-LOCAL config declaring ONLY the loopback Ollama provider + the pinned local model, and
    the driver points `OPENCODE_CONFIG` at it — so a host cloud-provider `opencode.json` cannot
    influence the driven run. Defence in depth: the harness `build_env` scrubs every provider
    credential var and the model is pinned to `ollama/*` (`_require_local_model`), so even a leaked
    cloud provider definition has no key and is never selected. The config's Ollama `baseURL` MUST
    be loopback or the write is refused (§2.3 — no off-box/paid routing).

  - **§2.2 no credential / §2.3 local-only.** Inherited verbatim from the harness builders.

HONESTY (recorded, directive §6). OpenCode ITSELF is genuinely driven headlessly: it spawns,
connects to the pinned local Ollama model, runs its agent loop, and EXECUTES its real tools
(read/glob/edit) inside the worktree — observed live. Small local coder models are FLAKY at
COMPLETING a multi-step tool edit headlessly (tool-arg schema slips, early stops, prose-only turns)
— a model-quality limitation, not a harness/governance defect (model-quality conclusions are
limited to local backends, §5 phase-13). The live test therefore asserts the drive + real tool
execution + worktree confinement and RECORDS whether a completed edit landed; it never fabricates
an edit that the model did not produce.
"""
from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from adapters.coding.opencode.harness import (
    ModelNotLocal,
    OpenCodeCliHarness,
    _is_loopback_ollama_host,
    _require_local_model,
    local_model_ref,
)
from node_runtime.supervisor.opencode_spawn import SupervisedOpenCode
from node_runtime.workspace.worktree import NodeWorktree

# The local Ollama OpenAI-compatible endpoint the scoped config points at. Loopback ONLY.
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"

# default wall-clock budget for one `opencode run` drive (a local model can be slow; the caller
# may lower it). The drive performs no git commits — that is worktree.py/`.gate` territory.
_DRIVE_TIMEOUT_S = 480.0


class DriveRefused(Exception):
    """A precondition for driving OpenCode in the worktree was not met — fail closed, no spawn."""


@dataclass(frozen=True)
class RunOutcome:
    """What a `Runner` returns: the raw result of one `opencode run` invocation."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class Runner(Protocol):
    """The one subprocess seam. The deterministic suite injects a scripted fake; the live test
    passes `subprocess_runner`. Keeping this a Protocol is what lets the whole governed path be
    proven WITHOUT a real spawn (and the real spawn be exercised only by the opt-in live test)."""

    def __call__(self, argv: list[str], *, cwd: str, env: dict[str, str],
                 timeout: float) -> RunOutcome: ...


def subprocess_runner(argv: list[str], *, cwd: str, env: dict[str, str],
                      timeout: float) -> RunOutcome:
    """The REAL runner: spawn `opencode run …` as a subprocess. Never used by the deterministic
    suite (only the opt-in live integration test passes it)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              cwd=cwd, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        return RunOutcome(returncode=124, stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                          stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                          timed_out=True)
    return RunOutcome(returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


@dataclass(frozen=True)
class DriveResult:
    """The observable evidence of one worktree drive. `.gate` turns a successful, tests-passing
    drive into a CANDIDATE artifact + controlled merge."""

    drove: bool                       # opencode spawned and returned (not a spawn/precondition fault)
    returncode: int | None
    timed_out: bool
    tool_events: int                  # count of tool-execution events observed in the JSON stream
    changed_files: tuple[str, ...]    # worktree-relative paths the drive modified (git status)
    edit_completed: bool              # at least one file in the worktree actually changed
    escaped: bool                     # a modification was detected in the base trunk tree, OR
                                      # containment could not be verified (fail-closed — see below)
    model: str                        # the pinned local model actually driven (ollama/*)
    config_path: str                  # the session-local OPENCODE_CONFIG used (U30)
    containment_verified: bool = True  # False ⇒ the base-trunk escape check could not run; when
                                      # False, `escaped` is forced True (fail closed, Buildout §4)
    stdout_tail: str = ""
    stderr_tail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "drove": self.drove, "returncode": self.returncode, "timed_out": self.timed_out,
            "tool_events": self.tool_events, "changed_files": list(self.changed_files),
            "edit_completed": self.edit_completed, "escaped": self.escaped, "model": self.model,
            "config_path": self.config_path, "containment_verified": self.containment_verified,
            "stdout_tail": self.stdout_tail[-400:], "stderr_tail": self.stderr_tail[-400:],
        }


@dataclass(frozen=True)
class TestOutcome:
    """Result of running the worktree's tests after the drive ("tests run" exit criterion)."""

    ran: bool
    returncode: int
    passed: bool
    stdout_tail: str = ""
    stderr_tail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"ran": self.ran, "returncode": self.returncode, "passed": self.passed,
                "stdout_tail": self.stdout_tail[-400:], "stderr_tail": self.stderr_tail[-400:]}


def write_scoped_opencode_config(session_dir: Path, *, model: str,
                                 base_url: str = DEFAULT_OLLAMA_BASE_URL) -> Path:
    """U30 discharge. Write a SESSION-LOCAL `opencode.json` declaring ONLY the loopback Ollama
    provider and the pinned local model, and return its path. `OPENCODE_CONFIG` will point here so a
    host cloud-provider config cannot influence the driven run. `model` is a bare tag or `ollama/`
    ref; the `baseURL` MUST be loopback (§2.3 — no off-box/paid routing) or the write is refused."""
    # a model already qualified with a NON-ollama provider (e.g. "openai/gpt-4o") must be refused,
    # not silently re-prefixed to a nonsensical "ollama/openai/…" — fail closed (§2.3).
    if "/" in (model or "") and not model.startswith("ollama/"):
        raise ModelNotLocal(
            f"model {model!r} names a non-local provider — only bare tags or ollama/* are drivable "
            f"(§2.3, fail closed)")
    ref = local_model_ref(model)
    _require_local_model(ref)  # fail closed: only ollama/* is drivable
    tag = ref.split("/", 1)[1]
    if not _is_loopback_ollama_host(base_url):
        raise DriveRefused(
            f"refuse to write an OpenCode config with a non-loopback Ollama baseURL {base_url!r} "
            f"— that would route the 'local' model off-box (§2.3, fail closed)")
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "ollama": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Ollama (local, sovereign-pinned)",
                "options": {"baseURL": base_url},
                "models": {tag: {"name": tag, "tools": True}},
            }
        },
    }
    path = session_dir / "opencode.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


def _git_out(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise DriveRefused(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def _porcelain_paths(repo: Path) -> set[str]:
    """Modified/added/untracked paths per `git status --porcelain` (worktree-relative, forward
    slashes). Used both to read the drive's changes and to prove the base trunk stayed clean."""
    out = _git_out(repo, "status", "--porcelain", "--untracked-files=all")
    paths: set[str] = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        p = line[3:].strip().strip('"')
        if " -> " in p:  # rename: take the destination
            p = p.split(" -> ", 1)[1]
        paths.add(p.replace("\\", "/"))
    return paths


def _count_tool_events(stdout: str, stderr: str) -> int:
    """Count tool-execution signals in OpenCode's output. `--format json` emits JSON event lines;
    the human stream marks executed tools with the arrows/labels we saw live (Read/Glob/Edit …).
    A best-effort observability metric (NOT a gate) — the gate is the file-change + tests-run."""
    n = 0
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and (ev.get("type") in ("tool", "tool_use", "tool_call")
                                     or ev.get("name") in ("read", "edit", "write", "glob",
                                                           "grep", "bash", "list")):
            n += 1
    # human-stream fallback: OpenCode prints executed tools as "→ Read …" / "✗ Read … failed"
    for marker in ("→ Read", "→ Edit", "→ Write", "→ Glob", "→ Grep", "→ Bash",
                   "Read ", "Edit ", "Glob "):
        n += (stderr or "").count(marker)
    return n


class OpenCodeDriver:
    """Drives a supervisor-admitted OpenCode harness against a local model, in the node's own
    worktree, from a single scoped MCP entry. Everything fail-closed."""

    def __init__(self, supervised: SupervisedOpenCode, worktree: NodeWorktree, mcp_client: Any, *,
                 base_repo: Path, session_dir: Path, base_url: str = DEFAULT_OLLAMA_BASE_URL,
                 timeout_s: float = _DRIVE_TIMEOUT_S, runner: Runner | None = None,
                 use_pure: bool = True, on_event: Callable[..., Any] | None = None) -> None:
        if not isinstance(supervised.harness, OpenCodeCliHarness):
            # only the real CLI harness carries build_env/build_run_command with the flags we need;
            # a mock-drive path uses drive() with an injected runner + this same real builder.
            self._harness = OpenCodeCliHarness(
                executable=getattr(supervised.harness, "executable", None))
        else:
            self._harness = supervised.harness
        # never trust the harness (invariant 29): re-assert the supervisor provenance so a
        # hand-built SupervisedOpenCode cannot bypass the spawn gate (invariant 2, fail closed).
        if not getattr(supervised.context, "spawned_by_supervisor", False):
            raise DriveRefused(
                "SupervisedOpenCode context was not spawned by the supervisor — refuse to drive "
                "(invariant 2 / I-C1, fail closed)")
        self._sup = supervised
        self._wt = worktree
        self._mcp = mcp_client
        self._base_repo = Path(base_repo)
        self._session_dir = Path(session_dir)
        self._base_url = base_url
        self._timeout = timeout_s
        self._runner = runner or subprocess_runner
        self._use_pure = use_pure
        self._on_event = on_event
        model = supervised.probe.coder_model
        if not model:
            raise DriveRefused(
                "supervised harness has no local coder model to drive (fail closed §2.3)")
        self._model = local_model_ref(model)
        _require_local_model(self._model)  # belt-and-suspenders pin at construction

    def _emit(self, kind: str, **data: Any) -> None:
        if self._on_event is not None:
            self._on_event(kind, **data)

    def read_scoped_objective(self, context_entry_id: str) -> str:
        """Read EXACTLY the one assigned MCP entry (scoped context, invariant 8) — never a store
        sweep, never the full transcript. Fail closed on a missing/empty assignment."""
        if not context_entry_id:
            raise DriveRefused("no scoped context entry assigned — refuse to drive (fail closed)")
        ctx = self._mcp.call("get_content", entry_id=context_entry_id)
        content_b64 = ctx.get("content_b64") if isinstance(ctx, dict) else None
        if not content_b64:
            raise DriveRefused(f"scoped MCP entry {context_entry_id!r} has no content (fail closed)")
        objective = base64.b64decode(content_b64).decode("utf-8")
        self._emit("scoped_context_read", node_id=self._wt.node_id, entry_id=context_entry_id,
                   chars=len(objective))
        return objective

    def build_command(self, objective: str) -> list[str]:
        """`opencode run [--pure] --auto --dir <worktree> -m ollama/<model> --format json <obj>`.
        The model pin (§2.3) is enforced inside the harness builder."""
        return self._harness.build_run_command(
            objective, model=self._model, workdir=str(self._wt.path),
            auto=True, pure=self._use_pure)

    def build_env(self, config_path: Path) -> dict[str, str]:
        """Scrubbed child env (harness §2.2/§2.3) + `OPENCODE_CONFIG` pointed at the session-local
        scoped config (U30). Setting OPENCODE_CONFIG on the SCRUBBED env, in that order, guarantees
        the config pointer is never mistaken for a credential and dropped."""
        env = self._harness.build_env()
        env["OPENCODE_CONFIG"] = str(config_path)
        return env

    def drive(self, objective: str) -> DriveResult:
        """Write the scoped config (U30), build the pinned command, run OpenCode in the worktree,
        then read back what changed. Confinement: changes are read from the worktree's own git
        status; the base trunk working tree is checked for any out-of-worktree modification."""
        config_path = write_scoped_opencode_config(
            self._session_dir, model=self._model, base_url=self._base_url)
        argv = self.build_command(objective)
        env = self.build_env(config_path)

        # snapshot the base trunk BEFORE the drive; if the check itself cannot run, we must NOT
        # later read a clean-looking empty diff as "confined" (fail closed, Buildout §4).
        base_before = self._try_base_status_outside_worktree()
        self._emit("drive_start", node_id=self._wt.node_id, model=self._model,
                   config=str(config_path), argv_tail=argv[-4:])
        outcome = self._runner(argv, cwd=str(self._wt.path), env=env, timeout=self._timeout)

        changed = tuple(sorted(_porcelain_paths(self._wt.path)))
        base_after = self._try_base_status_outside_worktree()
        if base_before is None or base_after is None:
            # the base-trunk containment check could not be verified on one/both sides ⇒ fail closed:
            # treat as escaped so an UNVERIFIABLE drive can never read as "confined, nothing escaped".
            containment_verified, escaped, outside = False, True, []
            self._emit("drive_containment_unverified", node_id=self._wt.node_id)
        else:
            containment_verified = True
            outside = sorted(base_after - base_before)
            escaped = bool(outside)
            if escaped:
                self._emit("drive_escape_detected", node_id=self._wt.node_id, outside=outside)
        drove = not outcome.timed_out and outcome.returncode is not None
        result = DriveResult(
            drove=drove, returncode=outcome.returncode, timed_out=outcome.timed_out,
            tool_events=_count_tool_events(outcome.stdout, outcome.stderr),
            changed_files=changed, edit_completed=len(changed) > 0, escaped=escaped,
            model=self._model, config_path=str(config_path),
            containment_verified=containment_verified,
            stdout_tail=(outcome.stdout or "")[-800:], stderr_tail=(outcome.stderr or "")[-800:])
        self._emit("drive_done", node_id=self._wt.node_id, **result.as_dict())
        return result

    def run_worktree_tests(self, test_argv: list[str], *, timeout: float = 120.0) -> TestOutcome:
        """Run the worktree's tests after the drive ("tests run" exit criterion). Executed INSIDE
        the worktree (cwd) so the tests exercise the driven tree, not the trunk. A non-zero exit is
        a real failing-tests signal (fail closed), not a crash of the driver."""
        if not test_argv:
            raise DriveRefused("no test command supplied — 'tests run' cannot be satisfied vacuously")
        try:
            proc = subprocess.run(test_argv, capture_output=True, text=True, timeout=timeout,
                                  cwd=str(self._wt.path), check=False)
        except subprocess.TimeoutExpired:
            self._emit("worktree_tests_timeout", node_id=self._wt.node_id)
            return TestOutcome(ran=True, returncode=124, passed=False,
                               stderr_tail="tests timed out")
        outcome = TestOutcome(ran=True, returncode=proc.returncode, passed=proc.returncode == 0,
                              stdout_tail=(proc.stdout or "")[-800:], stderr_tail=(proc.stderr or "")[-800:])
        self._emit("worktree_tests_done", node_id=self._wt.node_id, **outcome.as_dict())
        return outcome

    def _try_base_status_outside_worktree(self) -> set[str] | None:
        """Paths dirty in the BASE trunk working tree that are NOT the node worktrees dir. A drive
        that only touches its own worktree leaves this empty; anything here is a base-trunk escape.
        Returns None if `git status` could not run — the caller MUST treat None as fail-closed
        (unverifiable containment), never as an empty (clean) diff. NOTE: this detects escapes into
        the base trunk working tree ONLY; a write elsewhere on disk (outside the base repo) is out
        of scope here and left to OS-level containment (U10)."""
        try:
            dirty = _porcelain_paths(self._base_repo)
        except DriveRefused:
            return None
        return {p for p in dirty if not p.startswith("worktrees/")}
