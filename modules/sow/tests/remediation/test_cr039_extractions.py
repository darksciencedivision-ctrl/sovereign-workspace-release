"""CR-039 — behavior-preserving extraction of protocol validation from the desktop controller into
independently testable modules (renderer-spec.js, and navigation-guard.js from CR-032)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[4] / "modules" / "sow" / "apps" / "desktop"
_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_cr039_renderer_spec_pure_core(tmp_path):
    mod = (DESKTOP / "renderer-spec.js").as_posix()
    script = tmp_path / "run.js"
    script.write_text(
        "const { sanitizeRendererSpec } = require(%s);\n"
        "const allow = ['title', 'file', 'cwd'];\n"
        "const out = {};\n"
        "out.filters = sanitizeRendererSpec({title:'t', file:'f', evil:'x', env:{K:'v'}}, allow);\n"
        "out.nonobject = sanitizeRendererSpec(null, allow);\n"
        "out.empty = sanitizeRendererSpec({}, allow);\n"
        "console.log(JSON.stringify(out));\n" % json.dumps(mod),
        encoding="utf-8")
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    # allow-listed keys kept, everything else refused (and refused key NAMES surfaced for logging)
    assert out["filters"]["clean"] == {"title": "t", "file": "f"}
    assert sorted(out["filters"]["refused"]) == ["env", "evil"]
    assert out["nonobject"] == {"clean": {}, "refused": []}
    assert out["empty"] == {"clean": {}, "refused": []}


def test_cr039_main_wires_extracted_protocol_modules():
    main = (DESKTOP / "main.js").read_text(encoding="utf-8", errors="replace")
    # both protocol-validation splits are required from main.js and their modules exist
    assert 'require("./renderer-spec")' in main
    assert 'require("./navigation-guard")' in main
    assert (DESKTOP / "renderer-spec.js").exists()
    assert (DESKTOP / "navigation-guard.js").exists()
    # the pure logic no longer lives inline as a raw loop in the controller
    assert "sanitizeRendererSpecCore" in main
