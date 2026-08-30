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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    focused = {Path(p).as_posix() for p in config.getini("phase19_focused_paths")}
    host_coupled = {Path(p).as_posix() for p in config.getini("phase19_host_coupled_paths")}
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
