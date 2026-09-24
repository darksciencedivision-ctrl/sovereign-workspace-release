"""SW-24 - Distillery console must state its capability status honestly.

The served console was a static "idle" page that started no compute and never said WHY real
training and promotion do nothing, presenting a pre-functional module as a finished, idle-but-
ready peer. The console now derives an honest capability report from the real gates
(train.runner preflight + constants, ops.promotion authority) and labels preview evidence as
synthetic fixture kept separate from measured/qualified runs.

The distillery module runs as its own stdlib interpreter with the module root as cwd. Its
top-level import names (`distillery`, `train`, `ops`, `serve`, `capability`) collide in-process
with the shell's `shell/src/distillery.py` once another test has imported it, so these checks run
in an isolated subprocess with the distillery root as cwd - exactly the environment the module
launches in - rather than importing into the shared pytest interpreter.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
DISTILLERY = RELEASE_ROOT / "modules" / "distillery"


def _run_in_distillery(snippet: str) -> str:
    # No -I: for `-c` the cwd (the distillery root) must stay on sys.path so `import serve` /
    # `capability` and their local package imports resolve, exactly as the shipped launch does.
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(DISTILLERY), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


@pytest.fixture(scope="module")
def probe() -> dict:
    """Build the report, console HTML, health payload, and the real gate constants, in one
    isolated interpreter rooted at the distillery module."""
    snippet = (
        "import json, serve, capability\n"
        "from ops.promotion import PROMOTION_AUTHORITY_UNAVAILABLE\n"
        "from train.runner import MINIMUM_USABLE_VRAM_MIB, FIXTURE_EVIDENCE_CLASS, MEASURED_EVIDENCE_CLASS\n"
        "report = capability.capability_report()\n"
        "print('JSON_START' + json.dumps({\n"
        "  'report': report,\n"
        "  'console_html': serve.build_console_html(report),\n"
        "  'health': serve.health_payload(),\n"
        "  'promotion_const': PROMOTION_AUTHORITY_UNAVAILABLE,\n"
        "  'min_vram_mib': MINIMUM_USABLE_VRAM_MIB,\n"
        "  'fixture_class': FIXTURE_EVIDENCE_CLASS,\n"
        "  'measured_class': MEASURED_EVIDENCE_CLASS,\n"
        "}) + 'JSON_END')\n"
    )
    out = _run_in_distillery(snippet)
    blob = out.split("JSON_START", 1)[1].split("JSON_END", 1)[0]
    return json.loads(blob)


def _cap(report, cap_id):
    return next(c for c in report["capabilities"] if c["id"] == cap_id)


def test_training_and_promotion_reported_unavailable_with_reasons(probe):
    training = _cap(probe["report"], "real_training")
    promotion = _cap(probe["report"], "promotion")
    assert training["available"] is False
    assert training["reason"] == "BLOCKED_HARDWARE_CAPACITY"
    assert "VRAM" in training["detail"]
    assert promotion["available"] is False
    assert promotion["reason"] == "PROMOTION_AUTHORITY_UNAVAILABLE"


def test_reason_codes_and_vram_are_derived_from_the_real_gates_not_hardcoded(probe):
    # Anti-drift: the console reason/number must equal the actual gate constants.
    assert _cap(probe["report"], "promotion")["reason"] == probe["promotion_const"]
    min_gib = probe["min_vram_mib"] // 1024
    assert f"{min_gib} GiB" in _cap(probe["report"], "real_training")["detail"]


def test_evidence_is_labelled_fixture_and_separated_from_measured(probe):
    ev = probe["report"]["evidence"]
    assert ev["class_shown"] == probe["fixture_class"] == "SYNTHETIC_FIXTURE_ONLY"
    assert ev["measured_class"] == probe["measured_class"]
    # The note must make clear fixtures can never satisfy the promotion/qualification gates.
    assert "never" in ev["note"].lower() and probe["measured_class"] in ev["note"]


def test_every_capability_entry_is_well_formed(probe):
    for cap in probe["report"]["capabilities"]:
        assert set(("id", "label", "available", "reason", "detail")) <= set(cap)
        assert isinstance(cap["available"], bool)
        assert cap["reason"] and cap["detail"]


def test_console_html_surfaces_capability_status_and_evidence(probe):
    doc = probe["console_html"]
    for needle in ("Capability Status", "UNAVAILABLE", "BLOCKED_HARDWARE_CAPACITY",
                   "PROMOTION_AUTHORITY_UNAVAILABLE", "SYNTHETIC_FIXTURE_ONLY",
                   "maturity: preview", "Evidence"):
        assert needle in doc, f"console HTML missing: {needle}"


def test_health_payload_keeps_shell_required_keys(probe):
    # distillery.json identity requires ok/status/compute; the shell probe must not break.
    h = probe["health"]
    assert {"ok", "status", "compute"} <= set(h)
    assert h["compute"] is False
    assert h["maturity"] == "preview"
    assert h["capabilities_available"] == []  # nothing functional is available yet


def test_capability_introspection_is_fail_safe():
    # If a deeper import ever breaks, the report degrades to a truthful INTROSPECTION_FAILED
    # entry rather than crashing the health console. Injected in an isolated interpreter.
    snippet = (
        "import sys, types, json\n"
        "sys.modules['train.runner'] = types.ModuleType('train.runner')  # lacks the constants\n"
        "import capability\n"
        "cap = capability._training_capability()\n"
        "print('JSON_START' + json.dumps(cap) + 'JSON_END')\n"
    )
    out = _run_in_distillery(snippet)
    cap = json.loads(out.split("JSON_START", 1)[1].split("JSON_END", 1)[0])
    assert cap["available"] is False
    assert cap["reason"] == "CAPABILITY_INTROSPECTION_FAILED"
