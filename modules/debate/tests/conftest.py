"""Debate suite fixtures — EPC-01 P3-1.

Running this suite left SIXTEEN untracked directories inside `modules/debate/tests/`
(`.r4-guard-*`, `.r8-*`, `.r10-*`, `.r11-*`, `.r12-*` and friends). They were not cleaned up
and they were not gitignored, so a full test run dirtied the source tree — which matters more
than tidiness here: `tools/release/build_release.ps1` refuses to cut a release from a tree
with modifications, and `package_boundary_gate` counts stray files as violations. SOW has a
guard for exactly this class (`test_runtime_writes_are_gitignored.py`); debate had none.

Four test modules build their scratch config under `dir=ROOT / "tests"` deliberately — the app
resolves paths relative to its config file, so a `tmp_path` elsewhere would change what is
under test. Rather than restructure four fixtures and risk the thing they cover, this sweeps
what they leave: the directory is snapshotted before the session and anything new is removed
after it.

The sweeper is a backstop, not a licence. A test that cleans up after itself is still better,
and `test_smoke.py`, `test_v1_1_regressions.py` and `test_v1_2_1_hostile_e2e.py` already do.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

#: Prefixes the suite is known to create. Anything matching these and absent before the
#: session is removed after it. Deliberately narrow — a stray file that does NOT match one of
#: these is left alone and will show up in `git status`, which is the correct outcome for
#: something nobody predicted.
SCRATCH_PREFIXES = (
    ".r", ".smoke-", ".soak-", ".qualification-", ".hostile-", ".v1-unit-",
    ".v1-1-unit-",
)


def _scratch_entries() -> set[Path]:
    return {
        path for path in TESTS_DIR.iterdir()
        if path.name.startswith(SCRATCH_PREFIXES)
    }


@pytest.fixture(scope="session", autouse=True)
def _sweep_scratch_directories():
    before = _scratch_entries()
    yield
    for path in _scratch_entries() - before:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except OSError:
                pass
