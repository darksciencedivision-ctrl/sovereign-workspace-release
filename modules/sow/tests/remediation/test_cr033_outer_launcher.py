"""CR-033 — the outer launcher must not map a null child exit code to success."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

OUTER = Path("D:/production software 3/Start-Sovereign.ps1")


@pytest.mark.skipif(not OUTER.exists(), reason="outer launcher not present")
def test_cr033_null_exit_is_not_success_in_source():
    text = OUTER.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"if\s*\(\s*\$null\s*-eq\s*\$code\s*\)\s*\{([^}]*)\}", text, re.DOTALL)
    assert m, "null-exit branch not found"
    body = m.group(1)
    assert "exit 0" not in body, "null exit must not be treated as success"
    assert re.search(r"exit\s+[1-9]\d*", body), "null exit must return a nonzero failure code"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell exit-code matrix is Windows-only")
@pytest.mark.parametrize("mode,expected", [("null", 70), ("zero", 0), ("two", 2)])
def test_cr033_exit_code_matrix(mode, expected, tmp_path):
    # Reproduce the corrected decision and assert only an explicit integer (0 succeeds) is trusted.
    script = tmp_path / "decide.ps1"
    script.write_text(
        "param($mode)\n"
        "if ($mode -eq 'null') { $code = $null }\n"
        "elseif ($mode -eq 'zero') { $code = 0 }\n"
        "else { $code = 2 }\n"
        "if ($null -eq $code) { exit 70 }\n"
        "exit $code\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), mode],
        capture_output=True)
    assert proc.returncode == expected, (mode, proc.returncode)
