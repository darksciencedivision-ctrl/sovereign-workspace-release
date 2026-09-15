"""CR-030 — retained test commands must match the source-only tree (truthful, no false pass)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOW = RELEASE_ROOT / "modules" / "sow"
SOVEREIGN = RELEASE_ROOT / "modules" / "sovereign"


def test_cr030_sow_pytest_targets_the_retained_pack():
    ini = (SOW / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r"(?m)^testpaths\s*=\s*tests\b", ini)
    # the retained pack exists and holds real tests
    pack = SOW / "tests" / "remediation"
    assert pack.is_dir()
    assert list(pack.glob("test_*.py")), "retained regression pack is empty"
    # both phase19 keys are present (conftest registers them) ...
    for key in ("phase19_focused_paths", "phase19_host_coupled_paths"):
        assert re.search(rf"(?m)^{key}\s*=", ini), f"{key} missing"
    # ... but no indented test-path continuation lines remain (the lists named removed files)
    assert not re.search(r"(?m)^\s+tests/(unit|integration)/", ini), "phase19 lists still name removed files"
    # the false "2382 passed" contract must be gone
    assert "2382 passed" not in ini


def test_cr030_sow_default_command_collects_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(SOW), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "tests collected" in proc.stdout


def test_cr030_ui_test_lane_is_non_qualifying_not_false_pass():
    pkg = json.loads((SOVEREIGN / "ui" / "ui_shell" / "package.json").read_text(encoding="utf-8"))
    test_cmd = pkg["scripts"]["test"]
    # must NOT silently pass with zero tests
    assert "--passWithNoTests" not in test_cmd
    assert test_cmd.strip() != "vitest run"
    assert "UNSUPPORTED" in test_cmd and "process.exit(1)" in test_cmd


def test_cr030_test_sovereign_pytest_is_conditional():
    script = (SOVEREIGN / "Test-Sovereign.ps1").read_text(encoding="utf-8")
    # no unconditional `pytest ... tests` that fails on the removed dir
    assert "INTENTIONALLY UNSUPPORTED" in script
    assert "unsupportedLanes" in script
    # the final banner must not unconditionally claim a clean pass
    assert 'if ($script:unsupportedLanes.Count -gt 0)' in script
