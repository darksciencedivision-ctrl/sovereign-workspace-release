"""CR-032 — desktop navigation allowlist must permit only the packaged renderer, not any file URL."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parents[4] / "modules" / "sow" / "apps" / "desktop"
GUARD = DESKTOP / "navigation-guard.js"

_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_cr032_only_packaged_renderer_is_permitted(tmp_path):
    script = tmp_path / "run.js"
    script.write_text(
        "const {{ makeRoot, guard }} = (() => {{\n"
        "  const {{ makeNavigationGuard }} = require({guard});\n"
        "  const path = require('path');\n"
        "  const root = path.resolve('C:/app/renderer');\n"
        "  return {{ makeRoot: root, guard: makeNavigationGuard(root) }};\n"
        "}})();\n"
        "const cases = {{\n"
        "  packaged: 'file:///C:/app/renderer/index.html',\n"
        "  packaged_asset: 'file:///C:/app/renderer/assets/app.js',\n"
        "  remote: 'https://evil.example/x',\n"
        "  sibling: 'file:///C:/app/other.html',\n"
        "  parent: 'file:///C:/app/secret.txt',\n"
        "  encoded_traversal: 'file:///C:/app/renderer/%2e%2e/secret.txt',\n"
        "  unc: 'file://server/share/x',\n"
        "  alt_drive: 'file:///D:/app/renderer/index.html',\n"
        "  root_dir: 'file:///C:/app/renderer/',\n"
        "  empty: '',\n"
        "}};\n"
        "const out = {{}};\n"
        "for (const [k, v] of Object.entries(cases)) out[k] = guard(v);\n"
        "console.log(JSON.stringify(out));\n".format(guard=json.dumps(str(GUARD))),
        encoding="utf-8",
    )
    proc = subprocess.run([_NODE, str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip())

    assert result["packaged"] is True
    assert result["packaged_asset"] is True
    for denied in ("remote", "sibling", "parent", "encoded_traversal", "unc",
                   "alt_drive", "root_dir", "empty"):
        assert result[denied] is False, f"{denied} was permitted"
