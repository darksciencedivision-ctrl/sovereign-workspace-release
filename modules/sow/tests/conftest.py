"""Suite-wide fixtures. See `tests/live_call_guard.py` for why the live-CLI guard exists (U163)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# EPC-01 P1-5. This was `from tests.live_call_guard import install`, which resolves only when
# THIS module's `tests` directory is the one the name `tests` binds to. That holds when the
# suite runs from modules/sow, and fails in a whole-product run from the repository root:
# `modules/sow/tests` is a namespace package (no __init__.py) while `modules/distillery/tests`
# is a regular one, and a regular package wins the import search regardless of sys.path order.
# The guard would then silently not be installed, or collection would abort — and the guard's
# whole job is to stop a test spending live provider quota (U163), so importing it by a name
# that can bind elsewhere is the wrong mechanism. Loading it from ITS OWN path cannot bind to
# another module's file.
import importlib.util  # noqa: E402

_guard_path = Path(__file__).resolve().parent / "live_call_guard.py"
_spec = importlib.util.spec_from_file_location("sow_tests_live_call_guard", _guard_path)
if _spec is None or _spec.loader is None:  # pragma: no cover - a missing guard is fatal
    raise ImportError(f"the live-call guard is missing from {_guard_path}")
_live_call_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_live_call_guard)
install_live_call_guard = _live_call_guard.install


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live_cli: this test deliberately spawns a live provider CLI (costs quota)")


@pytest.fixture(autouse=True)
def _no_live_provider_cli(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs inside the guard unless it explicitly marks itself `live_cli`."""
    if request.node.get_closest_marker("live_cli"):
        return
    install_live_call_guard(monkeypatch)
