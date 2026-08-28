"""Suite-wide fixtures. See `tests/live_call_guard.py` for why the live-CLI guard exists (U163)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.live_call_guard import install as install_live_call_guard  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live_cli: this test deliberately spawns a live provider CLI (costs quota)")


@pytest.fixture(autouse=True)
def _no_live_provider_cli(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs inside the guard unless it explicitly marks itself `live_cli`."""
    if request.node.get_closest_marker("live_cli"):
        return
    install_live_call_guard(monkeypatch)
