"""H10: every preflight row keeps a space between its label and its value.

Found live on 2026-09-28: `Start-Shell.ps1 -CheckOnly` printed "process from this treepython (pid
27032)": that label is exactly the 22-character pad width, so nothing separated it from the value.
"""
from __future__ import annotations

import re
from pathlib import Path

START_SHELL = Path(__file__).resolve().parents[4] / "Start-Shell.ps1"


def test_h10_preflight_labels_never_run_into_their_values():
    text = START_SHELL.read_text(encoding="utf-8")
    fmt = re.search(r'function Line\(.*?\{\s*Write-Host \("(?P<fmt>[^"]*)" -f \$label\)', text, re.S)
    assert fmt, "Line helper not found"
    width = int(re.search(r"\{0,-(\d+)\}", fmt.group("fmt")).group(1))
    separated = fmt.group("fmt").endswith(" ")
    labels = re.findall(r"\bLine '([^']*)'", text)
    assert labels
    too_long = [label for label in labels if len(label) >= width and not separated]
    assert too_long == [], too_long
