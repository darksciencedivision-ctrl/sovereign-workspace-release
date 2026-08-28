"""Per-node git worktree isolation + controlled merge (Plan §7-P10; invariants 29, 16, 1).

Each coding node works in its OWN git worktree on its OWN branch (`node/<node_id>`). A node
never edits another node's worktree — the Phase-3 WorkspaceBinding contains its filesystem
access to its worktree path, and cross-node write attempts are refused and logged. Work
reaches the shared trunk only through a CONTROLLED MERGE PATH: a node commits on its branch,
a gate must PASS, and the OPERATOR must approve, before the MergeCoordinator merges — any
merge lacking a passing gate or operator approval is refused and logged (invariant 1: the
system never self-authorizes the protected merge action).

Enforcement honesty (U10): ENFORCED here = git-worktree separation + API-layer path
containment + controlled-merge gating. NOT enforced = OS-level filesystem denial between
SAME-USER node processes (that needs restricted tokens / separate accounts / admin, deferred
to a hardening pass); a node bypassing the WorkspaceBinding with raw syscalls is out of scope.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from node_runtime.workspace.binding import WorkspaceBinding

# node ids become both a branch (node/<id>) and a directory; validate explicitly rather than
# relying incidentally on git's ref-name rules (spec-audit F2). Alnum start, then [A-Za-z0-9._-],
# and never a path/ref hazard.
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESERVED_IDS = frozenset({".", "..", "HEAD", "main", "master"})


class WorktreeError(Exception):
    pass


class MergeRefused(Exception):
    pass


def _validate_node_id(node_id: str) -> None:
    if not _NODE_ID_RE.match(node_id) or ".." in node_id or node_id in _RESERVED_IDS:
        raise WorktreeError(f"invalid node_id for a worktree/branch: {node_id!r}")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


@dataclass
class NodeWorktree:
    node_id: str
    branch: str
    path: Path
    binding: WorkspaceBinding


class WorktreeManager:
    def __init__(self, base_repo: Path, on_event: Callable[..., Any] | None = None) -> None:
        self._base = Path(base_repo)
        if not (self._base / ".git").exists():
            raise WorktreeError(f"not a git repo: {self._base}")
        self._worktrees_root = self._base / "worktrees"
        self._on_event = on_event
        self._nodes: dict[str, NodeWorktree] = {}
        # keep the node worktrees out of the trunk working tree (spec-audit F4): a stray
        # `git add -A` in the trunk must not embed the node repos
        exclude = self._base / ".git" / "info" / "exclude"
        try:
            existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if "worktrees/" not in existing:
                exclude.write_text(existing + "\nworktrees/\n", encoding="utf-8")
        except OSError:
            pass

    def _emit(self, kind: str, **data: Any) -> None:
        if self._on_event is not None:
            self._on_event(kind, **data)

    @property
    def trunk(self) -> str:
        # the base repo's current branch is the trunk we merge into
        return _git(self._base, "rev-parse", "--abbrev-ref", "HEAD")

    def create(self, node_id: str) -> NodeWorktree:
        _validate_node_id(node_id)
        if node_id in self._nodes:
            raise WorktreeError(f"worktree for {node_id} already exists")
        branch = f"node/{node_id}"
        path = self._worktrees_root / node_id
        _git(self._base, "worktree", "add", "-b", branch, str(path), self.trunk)
        binding = WorkspaceBinding(path, node_id, on_refusal=lambda kind, **d: self._emit("workspace_escape", **d))
        wt = NodeWorktree(node_id=node_id, branch=branch, path=path, binding=binding)
        self._nodes[node_id] = wt
        self._emit("worktree_created", node_id=node_id, branch=branch, path=str(path))
        return wt

    def commit(self, node_id: str, message: str) -> str:
        """Stage and commit everything in the node's own worktree; returns the commit sha."""
        if node_id not in self._nodes:
            raise WorktreeError(f"no worktree for {node_id!r}")
        wt = self._nodes[node_id]
        _git(wt.path, "add", "-A")
        _git(wt.path, "-c", "user.email=node@sovereign.local", "-c", f"user.name={node_id}",
             "commit", "-m", message, "--allow-empty")
        sha = _git(wt.path, "rev-parse", "HEAD")
        self._emit("node_commit", node_id=node_id, sha=sha)
        return sha

    def get(self, node_id: str) -> NodeWorktree:
        if node_id not in self._nodes:
            raise WorktreeError(f"no worktree for {node_id!r}")
        return self._nodes[node_id]

    def remove(self, node_id: str) -> None:
        wt = self._nodes.pop(node_id, None)
        if wt is not None:
            _git(self._base, "worktree", "remove", "--force", str(wt.path))
            _git(self._base, "branch", "-D", wt.branch)  # don't leave a dangling node branch
            self._emit("worktree_removed", node_id=node_id)


class MergeCoordinator:
    """The ONLY path from a node branch into the trunk. Requires a passing gate verdict AND
    operator approval; otherwise refuses and logs (invariant 1)."""

    def __init__(self, base_repo: Path, on_event: Callable[..., Any] | None = None) -> None:
        self._base = Path(base_repo)
        self._on_event = on_event

    def _emit(self, kind: str, **data: Any) -> None:
        if self._on_event is not None:
            self._on_event(kind, **data)

    def merge(self, wt: NodeWorktree, *, gate_verdict: str, operator_approved: bool) -> str:
        if gate_verdict not in ("PASS", "PASS_WITH_RESERVATIONS"):
            self._emit("merge_refused", node_id=wt.node_id, branch=wt.branch, reason=f"gate verdict {gate_verdict}")
            raise MergeRefused(f"merge refused: gate verdict is {gate_verdict!r}, not a pass")
        if operator_approved is not True:  # strict boolean gate: truthy values do not approve (F3)
            self._emit("merge_refused", node_id=wt.node_id, branch=wt.branch, reason="operator approval required")
            raise MergeRefused("merge refused: operator approval required (invariant 1)")
        trunk = _git(self._base, "rev-parse", "--abbrev-ref", "HEAD")
        proc = subprocess.run(["git", "-C", str(self._base), "merge", "--no-ff", wt.branch,
                               "-m", f"merge {wt.branch} into {trunk} (gate {gate_verdict})"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            # a conflict/failure must not leave the trunk half-merged: abort to restore a clean
            # trunk (fail closed), log it, and raise (spec-audit F1)
            subprocess.run(["git", "-C", str(self._base), "merge", "--abort"], capture_output=True, text=True)
            self._emit("merge_failed", node_id=wt.node_id, branch=wt.branch, trunk=trunk,
                       reason=proc.stderr.strip()[:300])
            raise MergeRefused(f"merge of {wt.branch} failed and was aborted (trunk restored): "
                               f"{proc.stderr.strip()[:200]}")
        sha = _git(self._base, "rev-parse", "HEAD")
        self._emit("merge_applied", node_id=wt.node_id, branch=wt.branch, trunk=trunk, sha=sha, gate_verdict=gate_verdict)
        return sha
