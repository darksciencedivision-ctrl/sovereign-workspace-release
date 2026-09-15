"""CR-017 — the SOW runtime-write declaration must cover every durable write root.

runtime_writes in shell/modules/sow.json is the authoritative declaration consumed by backup /
migration / immutable-install verification. Every state-root path the product writes must be
contained by a declared root.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOW_JSON = RELEASE_ROOT / "shell" / "modules" / "sow.json"
DESKTOP = RELEASE_ROOT / "modules" / "sow" / "apps" / "desktop"


def _declared_state_roots() -> set[str]:
    data = json.loads(SOW_JSON.read_text(encoding="utf-8"))
    roots = set()
    for entry in data["runtime_writes"]:
        m = re.fullmatch(r"\$\{state_root\}/([^/]+)", entry)
        if m:
            roots.add(m.group(1))
    return roots


def test_cr017_store_is_declared_and_matches_runtime_env():
    data = json.loads(SOW_JSON.read_text(encoding="utf-8"))
    declared = _declared_state_roots()
    # the durable node store (leases, node events, journal db, probes) — the review's core omission
    assert "store" in declared, declared
    # runtime code and the declaration must agree on where the store lives
    store_env = data["launch"]["env_set"]["SOVEREIGN_STORE_ROOT"]
    assert store_env == "${state_root}/store"


def test_cr017_all_known_durable_roots_declared():
    declared = _declared_state_roots()
    required = {".recovery", "receipts", "store", ".approvals", "journal"}
    missing = required - declared
    assert not missing, f"undeclared durable write roots: {sorted(missing)}"


def test_cr017_no_undeclared_state_root_write_in_js():
    declared = _declared_state_roots()
    # Trace state-root writes in the desktop code: path.join(sowStateRoot(), "<seg>", ...) and the
    # journal's path.join(state, "journal"...). Every first segment must be a declared root.
    js_files = [DESKTOP / "main.js"] + list((DESKTOP / "control").glob("*.js"))
    seen: set[str] = set()
    pat_state = re.compile(r'sowStateRoot\(\)\s*,\s*"([^"]+)"')
    pat_journal = re.compile(r'path\.join\(\s*state\s*,\s*"([^"]+)"')
    for f in js_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        seen.update(pat_state.findall(text))
        seen.update(pat_journal.findall(text))
    assert seen, "expected to find some state-root writes to check"
    undeclared = {seg for seg in seen if seg not in declared}
    assert not undeclared, f"code writes to undeclared state-root segments: {sorted(undeclared)}"
