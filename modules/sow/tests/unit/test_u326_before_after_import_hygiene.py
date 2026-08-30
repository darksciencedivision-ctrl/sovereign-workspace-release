"""W-75: tools/evaluation/u326_before_after.py used to EXECUTE itself on import.

Module top level held an argv read, a cwd-rooted sys.path insert, three product
imports, a `git show` subprocess, a %TEMP% write and an unconditional main() -
so a bare import ran git, wrote outside its directory and died with
ModuleNotFoundError from any other cwd. These tests pin the repaired contract:
importing the module is side-effect-free, the repo root comes from __file__
rather than the caller's cwd, and the evaluation still works end to end when
INVOKED from a foreign working directory.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

TOOL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "evaluation" / "u326_before_after.py"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_importing_the_tool_has_no_side_effects(monkeypatch):
    """Every executable step used to sit at module top level. With subprocess.run poisoned,
    the import must still succeed - and it must leave sys.path alone."""
    import sys as _sys

    def _boom(*a, **kw):
        raise AssertionError("importing u326_before_after spawned a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    path_before = list(_sys.path)

    mod = _load("u326ba_hygiene_nosideeffects")

    assert list(_sys.path) == path_before, "the import mutated sys.path"
    assert not hasattr(mod, "before"), "the import executed the historical product module"
    assert hasattr(mod, "main"), "the entrypoint vanished"


def test_the_repo_root_is_resolved_from_the_file_not_the_cwd(monkeypatch, tmp_path):
    """W-57 class: the old code inserted Path.cwd() into sys.path, so every product import
    depended on the caller happening to stand in the repo root."""
    monkeypatch.chdir(tmp_path)
    mod = _load("u326ba_hygiene_root")

    assert mod.ROOT == REPO_ROOT


#: The evaluation replays unit 19.2's before/after by `git show`-ing the commit BEFORE that
#: work landed. SOW was vendored into the Sovereign Workspace and its upstream history was not
#: carried across, so that object does not exist here and the tool exits 128.
_BASE_COMMIT = "b529314"


def _base_commit_is_present() -> bool:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{_BASE_COMMIT}^{{commit}}"],
        capture_output=True, text=True, check=False)
    return proc.returncode == 0


def test_the_evaluation_still_runs_when_invoked_from_a_foreign_cwd(tmp_path):
    """POSITIVE control - the repair may not silence the instrument. Run the script for real
    from OUTSIDE the repository: it must reproduce its recorded verdict matrix.

    EPC-01 P2-10. Structurally unsatisfiable in the consolidated repository — see
    `_BASE_COMMIT`. The skip is CONDITIONAL on the object being genuinely absent, so the
    control revives by itself if the history is ever grafted in or the module returns to its
    own repository. An unconditional skip would retire a positive control permanently in
    exchange for a green suite today, which is exactly the silencing this test guards against.
    """
    if not _base_commit_is_present():
        pytest.skip(
            f"the evaluation replays from {_BASE_COMMIT}, which is not an object in this "
            f"repository: SOW is vendored into the Sovereign Workspace and its upstream "
            f"history was not carried across. The control cannot run from here, and revives "
            f"automatically if the history is restored."
        )
    proc = subprocess.run(
        [sys.executable, str(TOOL)],
        capture_output=True, text=True, cwd=str(tmp_path), timeout=180, check=False)
    assert proc.returncode == 0, f"the evaluation failed when invoked:\n{proc.stderr[-800:]}"
    assert "of 34 scenarios differ" in proc.stdout, (
        f"the verdict summary is missing from the output:\n{proc.stdout[-400:]}")
