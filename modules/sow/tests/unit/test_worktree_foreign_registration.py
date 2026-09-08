"""SW-ORCH-001 F-23 — a FOREIGN worktree registration is classified, not merely refused.

Measured on the operator's host, 2026-09-05. `D:\\production software 3\\release-worktree` and
`D:\\producttion software 2\\release-worktree` are separate repositories (each reports
`git rev-parse --git-common-dir` = `.git`), but the first carried admin records at
`.git/worktrees/worker-pane-{2,3}/` whose `gitdir` files pointed into the second — orphans left
behind when the tree was copied. `WorktreeManager.ensure` refused, correctly and permanently, so
every OpenCode coding pane on those two pane ids could never open.

`git worktree prune` does not clear such a record: prune removes registrations whose directory is
GONE, and these directories still exist in the other tree.

The refusal is not what changed and these tests pin that it did not: an uncontrolled worktree is
still refused. What is added is the ability to tell a live claim from stale metadata, and to name
the remediation for the second.

Real Git in temporary directories throughout. A mocked porcelain reader proves nothing about the
behaviour this finding is made of.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from node_runtime.workspace.worktree import WorktreeError, WorktreeManager


def _git(repo, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _repo(root):
    """A real repository with one commit, so `git worktree add` has a trunk to branch from."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t.local", "-c", "user.name=t", "commit", "-m", "seed")
    return root


def _events(sink):
    return lambda kind, **data: sink.append((kind, data))


def _names_path(message: str, path) -> bool:
    """Does `message` name `path`, whichever separator style it is spelled in?

    `git worktree list --porcelain` reports paths with forward slashes even on Windows, and the
    refusal quotes git verbatim — deliberately, because that is the spelling the operator will see
    in their own `git worktree list` output and the one the suggested remediation command takes.
    The managed path, built from `Path`, arrives with backslashes. Both are the same location, so
    the assertion is about whether the path is NAMED, not about which separator it is named with.
    """
    text = str(path)
    return text in message or text.replace("\\", "/") in message


# --- the measured defect --------------------------------------------------------------------

def test_a_foreign_registration_is_classified_and_its_remediation_named(tmp_path):
    """The exact shape from the operator's disk: two repos, one holding the other's record."""
    mine = _repo(tmp_path / "production software 3" / "release-worktree")
    other = _repo(tmp_path / "producttion software 2" / "release-worktree")

    # `other` legitimately owns a worktree for the branch name.
    other_wt = other / "worktrees" / "w-1"
    _git(other, "worktree", "add", "-b", "node/w-1", str(other_wt), "main")

    # `mine` acquires an orphan admin record pointing at it — what a directory copy produces.
    shutil.copytree(other / ".git" / "worktrees" / "w-1", mine / ".git" / "worktrees" / "w-1")
    _git(mine, "branch", "node/w-1", "main")

    mgr = WorktreeManager(mine)
    with pytest.raises(WorktreeError) as excinfo:
        mgr.ensure("w-1")
    msg = str(excinfo.value)

    # still a refusal, with the original containment sentence intact
    assert "refusing to adopt a worktree this manager does not control" in msg
    assert "invariant 29" in msg
    # ...but now classified, with both paths and the remediation named
    assert "FOREIGN" in msg
    assert _names_path(msg, other_wt)
    assert _names_path(msg, mine / "worktrees" / "w-1")
    assert "prune" in msg and "will NOT clear it" in msg
    # the remediation is deleting THIS repository's stale admin directory...
    assert _names_path(msg, mine / ".git" / "worktrees" / "w-1")
    # ...and it must warn against the command that looks tidier and is destructive: `git worktree
    # remove` deletes the WORKING TREE, which here belongs to the other repository.
    assert "Do NOT use `git worktree remove`" in msg


def test_the_foreign_remediation_never_proposes_destroying_the_other_repos_tree(tmp_path):
    """A refusal that recommends `git worktree remove` would be worse than the defect.

    The registered path belongs to another repository. `git worktree remove` operates on the
    WORKING TREE, so running it from this repository deletes that repository's checkout — an
    unrecoverable action proposed by a message whose whole purpose is containment. This pins that
    the safe remediation is the only one offered.
    """
    mine = _repo(tmp_path / "mine")
    other = _repo(tmp_path / "other")
    other_wt = other / "worktrees" / "w-1"
    _git(other, "worktree", "add", "-b", "node/w-1", str(other_wt), "main")
    shutil.copytree(other / ".git" / "worktrees" / "w-1", mine / ".git" / "worktrees" / "w-1")

    with pytest.raises(WorktreeError) as excinfo:
        WorktreeManager(mine).ensure("w-1")
    msg = str(excinfo.value)

    assert "worktree remove --force" not in msg
    assert "Do NOT use `git worktree remove`" in msg
    # the other repository's tree is untouched by merely being refused
    assert other_wt.exists()


def test_after_the_foreign_record_is_removed_the_pane_can_open(tmp_path):
    """The operator's remediation actually works — the branch name is released to this install."""
    mine = _repo(tmp_path / "mine")
    other = _repo(tmp_path / "other")
    other_wt = other / "worktrees" / "w-1"
    _git(other, "worktree", "add", "-b", "node/w-1", str(other_wt), "main")
    shutil.copytree(other / ".git" / "worktrees" / "w-1", mine / ".git" / "worktrees" / "w-1")

    mgr = WorktreeManager(mine)
    with pytest.raises(WorktreeError):
        mgr.ensure("w-1")

    # the operator-authorized step: drop the orphan admin record
    shutil.rmtree(mine / ".git" / "worktrees" / "w-1")

    wt = WorktreeManager(mine).ensure("w-1")
    assert wt.path == mine / "worktrees" / "w-1"
    assert wt.path.exists()
    assert wt.branch == "node/w-1"


# --- the refusal must NOT have weakened -------------------------------------------------------

def test_a_conflicting_registration_in_this_repo_still_refuses_and_is_not_foreign(tmp_path):
    """A live claim inside this repository: refused, and explicitly not called stale."""
    mine = _repo(tmp_path / "mine")
    elsewhere = mine / "somewhere-else"
    _git(mine, "worktree", "add", "-b", "node/w-1", str(elsewhere), "main")

    mgr = WorktreeManager(mine)
    with pytest.raises(WorktreeError) as excinfo:
        mgr.ensure("w-1")
    msg = str(excinfo.value)

    assert "refusing to adopt a worktree this manager does not control" in msg
    assert "FOREIGN" not in msg
    assert "belongs to THIS repository" in msg
    assert "live claim" in msg
    # the remediation for a foreign record must NOT be offered for a live one
    assert "worktree remove --force" not in msg


def test_a_registration_at_the_managed_path_is_still_adopted(tmp_path):
    """Unchanged behaviour: the idempotent-across-restarts case `ensure` exists for."""
    mine = _repo(tmp_path / "mine")
    seen: list = []
    first = WorktreeManager(mine, _events(seen)).ensure("w-1")

    # a fresh manager, as after a process restart: `_nodes` is empty, the tree is on disk
    seen.clear()
    again = WorktreeManager(mine, _events(seen)).ensure("w-1")

    assert again.path == first.path
    assert [k for k, _ in seen] == ["worktree_adopted"]


def test_a_registered_worktree_whose_directory_is_gone_still_says_prune(tmp_path):
    """Unchanged behaviour: the missing-directory case keeps its own distinct refusal."""
    mine = _repo(tmp_path / "mine")
    wt = WorktreeManager(mine).ensure("w-1")
    shutil.rmtree(wt.path)

    with pytest.raises(WorktreeError) as excinfo:
        WorktreeManager(mine).ensure("w-1")
    msg = str(excinfo.value)

    assert "git worktree prune" in msg
    assert "directory is gone" in msg
    assert "FOREIGN" not in msg


def test_unreadable_ownership_refuses_rather_than_guessing(tmp_path):
    """Fail closed: an unanswerable ownership question is reported, never resolved as 'mine'."""
    mine = _repo(tmp_path / "mine")
    other = _repo(tmp_path / "other")
    other_wt = other / "worktrees" / "w-1"
    _git(other, "worktree", "add", "-b", "node/w-1", str(other_wt), "main")
    shutil.copytree(other / ".git" / "worktrees" / "w-1", mine / ".git" / "worktrees" / "w-1")

    # the backpointer is destroyed; ownership becomes unanswerable
    (other_wt / ".git").unlink()

    with pytest.raises(WorktreeError) as excinfo:
        WorktreeManager(mine).ensure("w-1")
    msg = str(excinfo.value)

    assert "could not be established" in msg
    assert "Refusing rather than guessing" in msg
    assert "FOREIGN" not in msg


def test_a_node_branch_that_outlived_its_registration_is_attached_not_recreated(tmp_path):
    """The SECOND cause, found by running the repair on the operator's host.

    Removing an orphan admin record releases the REGISTRATION and leaves the BRANCH. `ensure` then
    sees nothing registered, calls `create`, and `git worktree add -b` dies with "a branch named
    'node/<id>' already exists" — so the pane stays blocked by a quieter cause than the one just
    repaired. `ensure`'s own contract says a node reopening should continue its accumulated work,
    which means attaching to the branch, not refusing because it exists.
    """
    mine = _repo(tmp_path / "mine")
    _git(mine, "branch", "node/w-1", "main")          # branch present, no worktree registered
    assert "node/w-1" in _git(mine, "branch", "--list", "node/w-1")

    seen: list = []
    wt = WorktreeManager(mine, _events(seen)).ensure("w-1")

    assert wt.path == mine / "worktrees" / "w-1"
    assert wt.path.exists()
    assert wt.branch == "node/w-1"
    kinds = dict((k, d) for k, d in seen)
    assert "worktree_created" in kinds
    assert kinds["worktree_created"]["branch_reused"] is True, (
        "the event must say the branch was REUSED rather than minted, or an operator reading the "
        "event stream cannot tell a fresh node from one continuing earlier work")


def test_a_node_with_no_branch_still_gets_a_fresh_one(tmp_path):
    """The unchanged path: a genuinely new node mints its branch off the trunk."""
    mine = _repo(tmp_path / "mine")
    seen: list = []
    wt = WorktreeManager(mine, _events(seen)).ensure("w-2")

    assert wt.branch == "node/w-2"
    kinds = dict((k, d) for k, d in seen)
    assert kinds["worktree_created"]["branch_reused"] is False


def test_node_id_validation_is_unchanged(tmp_path):
    """Regression: the containment guards around node ids do not weaken."""
    mine = _repo(tmp_path / "mine")
    mgr = WorktreeManager(mine)
    for bad in ("..", "HEAD", "main", "a/b", "../escape", ".hidden"):
        with pytest.raises(WorktreeError):
            mgr.ensure(bad)
