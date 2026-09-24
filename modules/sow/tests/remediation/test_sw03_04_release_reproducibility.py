"""SW-03 / SW-04 — release reproducibility (system-review 2026-09-22).

Contract tests over the provisioning script and the docs it must keep truthful. They do not run a
full provision (that needs a clean machine + network); they pin the behaviors the review required:
  SW-03 an explicit SOW interpreter, and drift checked against the lock (an existing venv is not
        assumed current),
  SW-04 the operator UI is built + validated by provisioning, and no doc claims a prebuilt UI ships.
"""
from __future__ import annotations

from pathlib import Path

RELEASE = Path(__file__).resolve().parents[4]
PROVISION = RELEASE / "Provision-Workspace.ps1"
SOV = RELEASE / "modules" / "sovereign"


def _provision_text() -> str:
    return PROVISION.read_text(encoding="utf-8")


# -- SW-03 -----------------------------------------------------------------
def test_sw03_provisions_an_explicit_sow_interpreter():
    text = _provision_text()
    assert PROVISION.is_file()
    # a SOW venv target alongside sovereign and debate
    assert "id = 'sow'" in text, "provisioning has no SOW venv target"
    for module in ("sovereign", "debate", "sow"):
        assert f"id = '{module}'" in text, f"{module} has no provisioned interpreter"


def test_sw03_existing_venv_is_verified_against_the_lock_not_assumed_current():
    text = _provision_text()
    # drift detection exists and is used
    assert "Get-VenvDrift" in text and "Get-DeclaredPins" in text
    assert "pip list --format=json" in text, "installed distributions are not enumerated"
    # the old 'exists -> present, skip' shortcut must be gone (drift is checked either way)
    assert ".venv already present" not in text, "an existing venv is still assumed current"
    # deterministic reinstall reconciles drift
    assert "--require-hashes" in text


# -- SW-04 -----------------------------------------------------------------
def test_sw04_provisioning_builds_and_validates_the_sovereign_ui():
    text = _provision_text()
    assert "ui\\ui_shell" in text or "ui/ui_shell" in text, "no UI build step"
    assert "npm run build" in text, "UI is not built"
    # validates the built assets, not mere presence of the dir
    assert "index.html" in text and "assets" in text, "UI build is not validated"


def test_sw04_docs_do_not_claim_a_prebuilt_ui_ships():
    for name in ("README_PRODUCTION.md", "README_RUN.md"):
        doc = (SOV / name).read_text(encoding="utf-8")
        low = doc.lower()
        assert "prebuilt operator ui" not in low, f"{name} still claims a prebuilt UI"
        assert "ui bundle is included" not in low, f"{name} still claims the UI bundle is included"
        assert "prebuilt bundle directly" not in low, f"{name} still tells operators to skip the build"


# -- guard: the em-dash class of parse breakage stays fixed ----------------
def test_provision_script_is_ascii_only():
    raw = PROVISION.read_bytes()
    offenders = [(i, b) for i, b in enumerate(raw) if b > 0x7F]
    assert not offenders, f"non-ASCII bytes in Provision-Workspace.ps1 at {offenders[:5]}"
