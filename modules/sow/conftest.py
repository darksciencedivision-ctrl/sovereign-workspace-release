"""Pytest rootdir anchor: puts the repo root on sys.path so tests import product
packages (control_plane.*, mcp_server.*, ...) regardless of invocation directory."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the Phase 19 suite contract stored in pytest.ini."""
    parser.addini("phase19_suite_timeout_seconds", "whole-suite wall-clock ceiling")
    parser.addini("phase19_focused_paths", "reproducible Phase 19 focused subset", type="linelist")
    parser.addini("phase19_host_coupled_paths", "tests requiring an otherwise idle host", type="linelist")


#: The one file the Phase 19 subsets are declared in. Read by PATH rather than through
#: `config.getini`, and that is the whole point of this constant.
#:
#: `getini` answers from the ACTIVE ini, which pytest resolves upward from the invocation's
#: arguments. Run from modules/sow that is this module's pytest.ini and the lists are found; run
#: from the repository root it is the root pytest.ini, which does not carry them, so `getini`
#: returned an EMPTY list and every item went unmarked. Measured: `pytest -m host_coupled` at the
#: root reported "no tests collected (4094 deselected)" while the same selector from modules/sow
#: returned its eight files. A declared-but-unapplied marker is worse than an absent one —
#: `-m "not host_coupled"` looked like it excluded the load-sensitive tests and excluded none.
#:
#: Not hypothetical: `tests/integration/test_opencode_candidate_live.py` drives a real coder model,
#: passes alone in 141s, and times out (returncode 124) against the full suite. It was ALREADY in
#: the host-coupled list and still ran unmarked in the whole-product run, which is the only run
#: where competing load decides the outcome.
#:
#: Copying the lists into the root config would fix the symptom and split one contract across two
#: files. Reading the declaring file directly keeps a single source and makes the marking identical
#: from every invocation. `tools/run_phase19_pytest.py` already reads this same file this same way.
_PHASE19_CONFIG = ROOT / "pytest.ini"


def _phase19_paths(key: str) -> set[str]:
    """The declared subset `key`, as posix paths relative to ROOT. Never raises: this runs during
    collection, and an unreadable contract must not abort the run — it degrades to marking nothing,
    which is the behaviour that existed before the file was consulted at all."""
    import configparser  # noqa: PLC0415 - collection-time only

    parser = configparser.ConfigParser()
    try:
        if not parser.read(_PHASE19_CONFIG, encoding="utf-8") or "pytest" not in parser:
            return set()
        raw = parser["pytest"].get(key, "")
    except (OSError, configparser.Error):
        return set()
    # configparser keeps the `#` comment lines that sit INSIDE these values (the host-coupled list
    # carries one), so they are dropped here rather than becoming a path that matches nothing.
    return {Path(line.strip()).as_posix() for line in raw.splitlines()
            if line.strip() and not line.strip().startswith("#")}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    focused = _phase19_paths("phase19_focused_paths")
    host_coupled = _phase19_paths("phase19_host_coupled_paths")
    for item in items:
        # EPC-01 P1-4. `relative_to` RAISES on a path outside ROOT, and pytest turns that
        # into an INTERNALERROR that aborts the whole run. Invoked from modules/sow the set
        # of collected items is always inside ROOT, so the bug was invisible here — but a
        # run from the repository root also collects modules/debate, shell/ and dev/, and
        # the first foreign item killed collection for everything. It reached recipients:
        # `pytest` at the root of the extracted archive crashed instead of reporting.
        #
        # This conftest's job is to MARK the Phase 19 subsets, which are defined relative to
        # this module. An item outside the module has no such marker by definition, so
        # skipping it is the correct behaviour, not a workaround.
        resolved = item.path.resolve()
        if not resolved.is_relative_to(ROOT):
            continue
        relative = resolved.relative_to(ROOT).as_posix()
        if relative in focused:
            item.add_marker("phase19_focused")
        if relative in host_coupled:
            item.add_marker("host_coupled")
