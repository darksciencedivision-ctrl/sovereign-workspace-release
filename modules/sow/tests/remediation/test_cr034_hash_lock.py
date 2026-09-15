"""CR-034 — the Sovereign Python dependency lock must be hash-locked, not just version-pinned."""
from __future__ import annotations

import re
from pathlib import Path

SOVEREIGN = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
LOCK = SOVEREIGN / "requirements.lock.txt"
REQ_IN = SOVEREIGN / "requirements.in"

TOP_LEVEL = {"flask": "3.1.3", "requests": "2.34.2", "chromadb": "1.5.9",
             "numpy": "2.5.1", "pydantic": "2.13.4"}


def test_cr034_lock_and_input_exist():
    assert LOCK.exists(), "hash-locked requirements.lock.txt missing"
    assert REQ_IN.exists(), "approved requirements.in input missing"


def test_cr034_every_requirement_is_hash_pinned():
    text = LOCK.read_text(encoding="utf-8")
    # Collect each pinned requirement (name==version) and require it to carry >=1 sha256 hash.
    # In a --generate-hashes lock, a requirement and its hashes form one backslash-continued block.
    blocks = re.split(r"\n(?=[A-Za-z0-9._-]+==)", text)
    pinned = 0
    for block in blocks:
        m = re.match(r"([A-Za-z0-9._-]+)==([^\s\\]+)", block.strip())
        if not m:
            continue
        pinned += 1
        assert "--hash=sha256:" in block, f"{m.group(1)}=={m.group(2)} has no hash"
    assert pinned >= len(TOP_LEVEL), f"only {pinned} pinned requirements found"


def test_cr034_top_level_pins_present_and_match():
    text = LOCK.read_text(encoding="utf-8").lower()
    for name, version in TOP_LEVEL.items():
        assert re.search(rf"(?m)^{re.escape(name)}=={re.escape(version)}\b", text), f"{name}=={version}"


def test_cr034_lock_is_generate_hashes_output():
    head = LOCK.read_text(encoding="utf-8")[:400]
    assert "--generate-hashes" in head and "pip-compile" in head
