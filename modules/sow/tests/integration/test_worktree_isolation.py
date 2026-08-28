"""Phase 10 exit criteria: per-node git worktrees; cross-node mutation attempts fail and are
logged; controlled merge path (worker branch -> gate -> operator-approved merge). Real git in
a temp repo (never the build repo)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from node_runtime.workspace.binding import WorkspaceEscape
from node_runtime.workspace.worktree import (
    MergeCoordinator,
    MergeRefused,
    WorktreeError,
    WorktreeManager,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    base = tmp_path / "proj"
    base.mkdir()
    _git(base, "init", "-b", "main")
    _git(base, "config", "user.email", "op@sovereign.local")
    _git(base, "config", "user.name", "operator")
    (base / "README.md").write_text("trunk\n", encoding="utf-8")
    _git(base, "add", "-A")
    _git(base, "commit", "-m", "initial")
    return base


def test_each_node_gets_its_own_worktree_and_branch(repo) -> None:
    events = []
    mgr = WorktreeManager(repo, on_event=lambda k, **d: events.append((k, d)))
    a = mgr.create("coder-A")
    b = mgr.create("coder-B")
    assert a.branch == "node/coder-A" and b.branch == "node/coder-B"
    assert a.path != b.path and a.path.is_dir() and b.path.is_dir()
    assert sum(1 for k, _ in events if k == "worktree_created") == 2


def test_node_works_only_in_its_own_worktree(repo) -> None:
    mgr = WorktreeManager(repo)
    a = mgr.create("coder-A")
    a.binding.write_text("src/feature.py", "print('A work')\n")   # inside own worktree: ok
    assert (a.path / "src" / "feature.py").is_file()
    sha = mgr.commit("coder-A", "A adds feature")
    assert len(sha) == 40


def test_cross_node_mutation_refused_and_logged(repo) -> None:
    events = []
    mgr = WorktreeManager(repo, on_event=lambda k, **d: events.append((k, d)))
    a = mgr.create("coder-A")
    mgr.create("coder-B")
    # coder-A tries to write into coder-B's worktree via traversal -> refused + logged
    with pytest.raises(WorkspaceEscape):
        a.binding.write_text("../coder-B/sabotage.py", "malicious")
    assert any(k == "workspace_escape" for k, _ in events)
    assert not (mgr.get("coder-B").path / "sabotage.py").exists()


def test_controlled_merge_requires_gate_pass_and_operator_approval(repo) -> None:
    events = []
    mgr = WorktreeManager(repo, on_event=lambda k, **d: events.append((k, d)))
    merger = MergeCoordinator(repo, on_event=lambda k, **d: events.append((k, d)))
    a = mgr.create("coder-A")
    a.binding.write_text("out.py", "x = 1\n")
    mgr.commit("coder-A", "A work")

    # a FAIL gate cannot merge
    with pytest.raises(MergeRefused, match="gate verdict"):
        merger.merge(a, gate_verdict="FAIL", operator_approved=True)
    # a passing gate without operator approval cannot merge
    with pytest.raises(MergeRefused, match="operator approval"):
        merger.merge(a, gate_verdict="PASS", operator_approved=False)
    # both -> merge applies
    sha = merger.merge(a, gate_verdict="PASS", operator_approved=True)
    assert len(sha) == 40
    # the trunk now contains A's file
    assert (repo / "out.py").read_text(encoding="utf-8") == "x = 1\n"
    assert any(k == "merge_applied" for k, _ in events)
    assert sum(1 for k, _ in events if k == "merge_refused") == 2


def test_unapproved_work_never_reaches_trunk(repo) -> None:
    mgr = WorktreeManager(repo)
    merger = MergeCoordinator(repo)
    a = mgr.create("coder-A")
    a.binding.write_text("secret.py", "leak = True\n")
    mgr.commit("coder-A", "A work")
    with pytest.raises(MergeRefused):
        merger.merge(a, gate_verdict="FAIL", operator_approved=True)
    assert not (repo / "secret.py").exists()  # trunk untouched by unmerged work


@pytest.mark.parametrize("bad_id", ["../evil", "..", ".", "HEAD", "main", "-x", "a/b", "a\\b", "node with space"])
def test_invalid_node_id_refused(repo, bad_id) -> None:
    """F2: node_id is explicitly validated, not left to git's incidental ref rules."""
    with pytest.raises(WorktreeError, match="invalid node_id"):
        WorktreeManager(repo).create(bad_id)


def test_merge_conflict_aborts_and_restores_clean_trunk(repo) -> None:
    """F1: a conflicting merge must not leave the trunk half-merged — it aborts (trunk
    restored) and logs merge_failed, fail closed."""
    events = []
    mgr = WorktreeManager(repo, on_event=lambda k, **d: events.append((k, d)))
    merger = MergeCoordinator(repo, on_event=lambda k, **d: events.append((k, d)))
    # trunk edits README; node A edits the SAME line -> conflict on merge
    (repo / "README.md").write_text("trunk change\n", encoding="utf-8")
    _git(repo, "commit", "-am", "trunk edits readme")
    a = mgr.create("coder-A")  # branched from the ORIGINAL trunk... but we branched after commit
    # make A diverge on the same file from its base
    a.binding.write_text("README.md", "A change\n")
    mgr.commit("coder-A", "A edits readme")
    # force divergence: reset A's base is complex; instead edit trunk again to guarantee conflict
    (repo / "README.md").write_text("trunk change 2\n", encoding="utf-8")
    _git(repo, "commit", "-am", "trunk edits readme again")
    with pytest.raises(MergeRefused, match="aborted|failed"):
        merger.merge(a, gate_verdict="PASS", operator_approved=True)
    # trunk is clean (no MERGE_HEAD, working tree not conflicted) and has the trunk content
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert (repo / "README.md").read_text(encoding="utf-8") == "trunk change 2\n"
    assert any(k == "merge_failed" for k, _ in events)


def test_operator_approved_must_be_strict_true(repo) -> None:
    """F3: a truthy-but-not-True value does not approve a merge (fail closed)."""
    mgr = WorktreeManager(repo); merger = MergeCoordinator(repo)
    a = mgr.create("coder-A")
    a.binding.write_text("f.py", "1\n"); mgr.commit("coder-A", "w")
    with pytest.raises(MergeRefused, match="operator approval"):
        merger.merge(a, gate_verdict="PASS", operator_approved=1)  # truthy, not True
    with pytest.raises(MergeRefused, match="operator approval"):
        merger.merge(a, gate_verdict="PASS", operator_approved="yes")
