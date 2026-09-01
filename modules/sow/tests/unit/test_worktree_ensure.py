"""`WorktreeManager.ensure` — the restart-safe provisioning a coding pane depends on (EPC-04 W-3).

These run against REAL git repositories in `tmp_path`, not a fake. The behaviour under test is
git's ("the branch is already checked out"), and a stub would only assert what the stub was told.
That distinction is not academic here: this programme has already shipped one reader that passed
nine tests written against an invented data shape while being wrong about the real one.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from node_runtime.workspace.worktree import WorktreeError, WorktreeManager

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "trunk"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "README.md").write_text("trunk\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")
    return root


def test_ensure_provisions_a_worktree_when_none_exists(repo):
    wt = WorktreeManager(repo).ensure("pane-1")
    assert wt.path.exists()
    assert wt.branch == "node/pane-1"
    assert wt.path.parent == repo / "worktrees"


def test_ensure_adopts_the_existing_worktree_after_a_process_restart(repo):
    """The behaviour that makes reopening a coding pane work rather than refuse."""
    first = WorktreeManager(repo).ensure("pane-1")

    # a genuinely fresh manager: empty `_nodes`, exactly as a new process has
    second = WorktreeManager(repo).ensure("pane-1")

    assert second.path == first.path
    assert second.branch == first.branch


def test_create_is_what_fails_on_restart_which_is_why_ensure_exists(repo):
    """The falsifier for the test above: `create` must NOT be quietly restart-safe already."""
    WorktreeManager(repo).create("pane-1")
    with pytest.raises((WorktreeError, Exception)):
        WorktreeManager(repo).create("pane-1")


def test_ensure_refuses_to_adopt_a_worktree_outside_the_managed_path(repo, tmp_path):
    """CONTAINMENT. An adopted tree this manager does not control is the failure it must not have.

    A branch checked out somewhere else — by the operator, by another tool — is not the pane's
    tree. Handing it over would give the model write hands in a directory outside the managed
    root, which is exactly the containment the refusal being lifted (U95) was protecting.
    """
    elsewhere = tmp_path / "somewhere-else"
    _git(repo, "worktree", "add", "-b", "node/pane-1", str(elsewhere))

    with pytest.raises(WorktreeError) as err:
        WorktreeManager(repo).ensure("pane-1")
    msg = str(err.value)
    assert "does not control" in msg
    # git reports worktree paths with forward slashes on Windows; the refusal must NAME the
    # offending location, and comparing separators would test the platform, not the guard.
    assert str(elsewhere).replace("\\", "/") in msg.replace("\\", "/")


def test_ensure_refuses_when_git_registers_a_worktree_whose_directory_is_gone(repo):
    """Fail closed rather than reuse a half-removed tree."""
    mgr = WorktreeManager(repo)
    wt = mgr.ensure("pane-1")
    shutil.rmtree(wt.path)

    with pytest.raises(WorktreeError) as err:
        WorktreeManager(repo).ensure("pane-1")
    assert "prune" in str(err.value)


def test_two_panes_never_share_a_worktree_or_a_branch(repo):
    """W-3, stated as the property: isolation is PER NODE."""
    mgr = WorktreeManager(repo)
    a, b = mgr.ensure("pane-a"), mgr.ensure("pane-b")
    assert a.path != b.path
    assert a.branch != b.branch
    assert a.path.exists() and b.path.exists()


def test_a_node_worktree_starts_from_the_trunk_and_leaves_it_unmodified(repo):
    """The property W-6 has to demonstrate live, asserted here where it can be controlled."""
    trunk_head = _git(repo, "rev-parse", "HEAD")
    wt = WorktreeManager(repo).ensure("pane-1")

    (wt.path / "written-by-the-node.txt").write_text("model output\n", encoding="utf-8")
    _git(wt.path, "add", "-A")
    _git(wt.path, "-c", "user.email=n@x.invalid", "-c", "user.name=node", "commit", "-m", "work")

    assert _git(repo, "rev-parse", "HEAD") == trunk_head          # trunk commit unmoved
    assert not (repo / "written-by-the-node.txt").exists()        # trunk tree unmodified
    assert _git(repo, "status", "--porcelain") == ""              # and clean
