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
        # A node BRANCH can outlive its worktree registration, and then `-b` is the wrong verb.
        #
        # `ensure` already documents the idempotent-across-restarts case, but it only recognises it
        # when git still REGISTERS a worktree for the branch. A branch with no registration falls
        # between the two: `_registered_worktrees()` reports nothing, `ensure` calls `create`, and
        # `git worktree add -b` dies with "a branch named 'node/<id>' already exists". Measured on
        # the operator's host after the SW-ORCH-001 F-23 orphan admin records were removed — that
        # removal released the registrations and left the branches, so every coding pane on those
        # ids stayed blocked by a second, quieter cause.
        #
        # Attaching to the existing branch is what `ensure`'s own contract asks for: the branch is
        # this node's accumulated work, and a pane reopening should continue it, not be refused
        # because it exists. Creating is for a node that has none.
        exists = subprocess.run(
            ["git", "-C", str(self._base), "rev-parse", "--verify", "--quiet",
             f"refs/heads/{branch}"], capture_output=True, text=True).returncode == 0
        if exists:
            _git(self._base, "worktree", "add", str(path), branch)
        else:
            _git(self._base, "worktree", "add", "-b", branch, str(path), self.trunk)
        binding = WorkspaceBinding(path, node_id, on_refusal=lambda kind, **d: self._emit("workspace_escape", **d))
        wt = NodeWorktree(node_id=node_id, branch=branch, path=path, binding=binding)
        self._nodes[node_id] = wt
        self._emit("worktree_created", node_id=node_id, branch=branch, path=str(path),
                   branch_reused=exists)
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

    def ensure(self, node_id: str) -> NodeWorktree:
        """`create`, but idempotent across PROCESS RESTARTS — the shape a pane actually needs.

        `_nodes` is in-memory, so a manager built in a fresh process believes it has provisioned
        nothing. `create` then runs `git worktree add -b node/<id>`, which FAILS because the branch
        and the directory are still on disk from the last run. That turns "the operator reopened a
        coding pane" into a refusal, which is the wrong answer: the containment is intact, it was
        established earlier.

        So an existing tree is ADOPTED rather than recreated. Adoption is deliberately narrow — the
        registered path for `node/<id>` must be the path this manager would itself have chosen. A
        worktree registered somewhere else under the same node id is NOT adopted: it would hand the
        pane a directory this manager does not control, which is the containment failure the whole
        module exists to prevent, arriving through the convenience door.
        """
        _validate_node_id(node_id)
        if node_id in self._nodes:
            return self._nodes[node_id]

        expected = self._worktrees_root / node_id
        registered = self._registered_worktrees().get(f"node/{node_id}")
        if registered is None:
            return self.create(node_id)
        if Path(registered).resolve() != expected.resolve():
            # The refusal itself is unchanged and non-negotiable (SW-ORCH-001 F-23 contract item 1):
            # a worktree this manager does not control is never adopted. What is ADDED is saying
            # which KIND of registration it is, because the two need opposite operator actions.
            raise WorktreeError(self._describe_unadoptable(node_id, registered, expected))
        if not expected.exists():
            raise WorktreeError(
                f"git still registers a worktree for node/{node_id} at {str(expected)!r} but the "
                f"directory is gone — run `git worktree prune` (fail closed rather than reuse a "
                f"half-removed tree)")

        binding = WorkspaceBinding(expected, node_id,
                                   on_refusal=lambda kind, **d: self._emit("workspace_escape", **d))
        wt = NodeWorktree(node_id=node_id, branch=f"node/{node_id}", path=expected, binding=binding)
        self._nodes[node_id] = wt
        self._emit("worktree_adopted", node_id=node_id, branch=wt.branch, path=str(expected))
        return wt

    def _registration_owner(self, registered: str) -> Path | None:
        """Which repository's admin area does the registered worktree point BACK to?

        A linked worktree's own `.git` is a file reading `gitdir: <repo>/.git/worktrees/<name>`.
        That backpointer is the authority on ownership, and it is what separates the two ways
        `ensure` can find a branch checked out somewhere unexpected. Returns None when it cannot be
        read — the directory is gone, it is not a linked worktree, or the file is unreadable — and
        None is deliberately NOT "mine": an unanswerable ownership question stays unanswered.
        """
        dotgit = Path(registered) / ".git"
        try:
            if not dotgit.is_file():
                return None
            text = dotgit.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not text.startswith("gitdir:"):
            return None
        try:
            return Path(text[len("gitdir:"):].strip()).resolve()
        except (OSError, ValueError):
            return None

    def _describe_unadoptable(self, node_id: str, registered: str, expected: Path) -> str:
        """Why this registration cannot be adopted, and what the operator should do about it.

        SW-ORCH-001 F-23. `ensure` collapsed two different situations into one permanent refusal:

          * CONFLICTING — the branch really is checked out elsewhere in THIS repository. A live
            claim. Adopting it would hand the pane a directory this manager does not control, and
            the right answer is the refusal that has always been here.
          * FOREIGN — the registration is an orphan admin record left behind when a repository was
            COPIED. `.git/worktrees/<id>/` came along with the copy, and its `gitdir` still points
            at a directory owned by the other repository. Nothing in this repository is using that
            branch; the metadata is simply stale. `git worktree prune` does not clear it, because
            prune removes records whose directory is GONE and this one still exists — in the other
            tree. Measured on the operator's host 2026-09-05: both `node/worker-pane-2` and
            `node/worker-pane-3` were in this state, so every coding pane on those ids refused at
            launch indefinitely, with containment working exactly as designed.

        Removing a foreign record is a Git admin mutation and is therefore the OPERATOR's call, not
        this manager's (contract item 4). This function detects, classifies, and names the exact
        remediation; it never runs it.
        """
        owner = self._registration_owner(registered)
        mine = (self._base / ".git").resolve()
        # Quoted, NOT `!r`. `repr()` of a Windows path doubles every separator (a user-profile
        # path comes back with each backslash written twice), and this message exists to hand an
        # operator two paths and a command
        # they can act on. `registered` comes back from `git worktree list --porcelain` already
        # spelled with forward slashes; it is quoted verbatim rather than normalised, because that
        # is what their own `git worktree list` will show and what the remediation command takes.
        head = (f'branch node/{node_id} is already checked out at "{registered}", not at the '
                f'managed path "{expected}" — refusing to adopt a worktree this manager does '
                f"not control (containment, invariant 29)")

        if owner is not None and owner != mine and mine not in owner.parents:
            return (
                f"{head}. That registration is FOREIGN, not a live claim: the worktree's own "
                f"`.git` points back to {str(owner)!r}, which is not this repository "
                f"({str(mine)!r}), so it is an orphan admin record left by a repository copy. "
                f"`git worktree prune` will NOT clear it — prune only removes records whose "
                f"directory is gone, and this one still exists in the other tree. To release the "
                f"branch name for this install, an operator deletes THIS repository's stale admin "
                f'directory: "{self._base / ".git" / "worktrees" / node_id}" — then re-opens the '
                f"pane. Do NOT use `git worktree remove` here: it deletes the WORKING TREE at "
                f'"{registered}", which belongs to the other repository, so the command that looks '
                f"like the tidy one destroys another repository's checkout. Deleting the admin "
                f"directory touches nothing outside this repository.")

        if owner is None:
            return (
                f"{head}. Ownership of that path could not be established — its `.git` backpointer "
                f"is missing or unreadable, so this manager cannot tell a live claim from an orphan "
                f"admin record. Refusing rather than guessing: inspect "
                f'`git -C "{self._base}" worktree list --porcelain` and the contents of '
                f'"{registered}" before deciding.')

        return (
            f"{head}. That registration belongs to THIS repository, so the branch is genuinely in "
            f"use somewhere else in it — a live claim, not stale metadata. Finish or remove that "
            f"worktree before re-opening this pane; this manager will not take a directory another "
            f"part of the same repository is holding.")

    def _registered_worktrees(self) -> dict[str, str]:
        """`{branch: path}` as GIT reports it — the authority on what already exists.

        Read from `git worktree list --porcelain` rather than from a directory scan: a directory
        that looks like a worktree but is not registered cannot be adopted, and a registered one
        whose directory was deleted must be reported rather than silently recreated.
        """
        out = _git(self._base, "worktree", "list", "--porcelain")
        found: dict[str, str] = {}
        path: str | None = None
        for line in out.splitlines():
            if line.startswith("worktree "):
                path = line[len("worktree "):].strip()
            elif line.startswith("branch ") and path is not None:
                ref = line[len("branch "):].strip()
                found[ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref] = path
        return found

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
