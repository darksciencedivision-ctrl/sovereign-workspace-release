"""CR-031 — the optional spike compositor must not ship vulnerable Electron deps and must stay
excluded from product packaging."""
from __future__ import annotations

import json
import re
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[4] / "modules" / "sow" / "tools" / "spike_compositor"


def test_cr031_electron_upgraded_off_vulnerable_major():
    pkg = json.loads((SPIKE / "package.json").read_text(encoding="utf-8"))
    spec = pkg["devDependencies"]["electron"]
    major = int(re.search(r"(\d+)", spec).group(1))
    assert major >= 43, f"spike electron {spec} is still on the vulnerable major"


def test_cr031_spike_excluded_from_packaging():
    pkg = json.loads((SPIKE / "package.json").read_text(encoding="utf-8"))
    # private=true keeps it out of any publish/package step; it lives under tools/, not the product.
    assert pkg.get("private") is True


def test_cr031_lock_has_no_electron_31():
    lock = (SPIKE / "package-lock.json").read_text(encoding="utf-8")
    assert '"electron": "^31' not in lock and "electron/-/electron-31" not in lock
