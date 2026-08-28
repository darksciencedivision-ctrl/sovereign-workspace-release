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
        relative = item.path.resolve().relative_to(ROOT).as_posix()
        if relative in focused:
            item.add_marker("phase19_focused")
        if relative in host_coupled:
            item.add_marker("host_coupled")
