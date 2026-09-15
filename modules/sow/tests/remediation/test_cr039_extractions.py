"""CR-039 — behavior-preserving extraction of protocol validation from the desktop controller into
an independently testable module. navigation-guard.js is the demonstrated extraction (a protocol
validator split out of main.js), exercised directly here for the CR-039 pattern. (A renderer-spec
extraction was tried and reverted: it collided with retained mutation anchor P28, and the review's
guidance is to avoid churn in the retained falsification contract.)"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[4] / "modules" / "sow" / "apps" / "desktop"
GUARD = DESKTOP / "navigation-guard.js"
SHELL_STATIC = Path(__file__).resolve().parents[4] / "shell" / "static"
_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_cr039_extracted_protocol_validator_is_independently_testable(tmp_path):
    script = tmp_path / "run.js"
    script.write_text(
        "const { makeNavigationGuard } = require(%s);\n"
        "const path = require('path');\n"
        "const g = makeNavigationGuard(path.resolve('C:/app/renderer'));\n"
        "console.log(JSON.stringify({ok: g('file:///C:/app/renderer/index.html'),"
        " bad: g('file:///C:/app/secret.txt'), remote: g('https://x/y')}));\n"
        % json.dumps(GUARD.as_posix()),
        encoding="utf-8")
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"ok": True, "bad": False, "remote": False}


def test_cr039_main_wires_extracted_protocol_module():
    main = (DESKTOP / "main.js").read_text(encoding="utf-8", errors="replace")
    assert 'require("./navigation-guard")' in main
    assert (DESKTOP / "navigation-guard.js").exists()
    # the renderer-spec extraction was reverted to preserve the retained mutation anchor (P28)
    assert not (DESKTOP / "renderer-spec.js").exists()


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_cr039_shell_module_state_projection_is_pure_and_wired(tmp_path):
    module_path = SHELL_STATIC / "module-state.js"
    script = tmp_path / "project.js"
    script.write_text(
        "const { projectModuleState } = require(%s);\n"
        "const meta={READY:{cls:'ok',label:'Ready'},FAILED:{cls:'bad',label:'Failed'}};\n"
        "const p=projectModuleState({state:'FAILED',reason:'boom',port:5181},"
        "{state:'READY'},meta,(port)=>'http://127.0.0.1:'+port);\n"
        "console.log(JSON.stringify(p));\n" % json.dumps(module_path.as_posix()),
        encoding="utf-8",
    )
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    projected = json.loads(proc.stdout)
    assert projected["stateText"] == "Failed: boom"
    assert projected["reasonText"] == ""
    assert projected["resolvedUrl"] == "http://127.0.0.1:5181"
    assert projected["shouldCloseBrowser"] is True
    html = (SHELL_STATIC / "index.html").read_text(encoding="utf-8")
    assert html.index("module-state.js") < html.index("app.js")
    app = (SHELL_STATIC / "app.js").read_text(encoding="utf-8")
    assert "SWSModuleState.projectModuleState" in app
