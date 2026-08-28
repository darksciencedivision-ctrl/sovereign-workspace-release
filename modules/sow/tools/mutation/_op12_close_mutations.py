"""Mutation runner for the guards added at the Phase 18B `.close` gate.

Kept in the tree rather than run once and described, because a mutation result asserted in a
report is exactly the class of claim this track has been reopened over three times: prose that
cannot disagree with its value. Run it and the eight verdicts are reproduced.

Each entry: (path, old_bytes, new_bytes, selector). It applies the mutation, runs the selector,
records RED (a test caught it) or GREEN (nothing did), restores the original bytes, and verifies
the restore is BYTE-IDENTICAL by sha256. Exit 1 if anything is GREEN or a restore diverges.

What it covers, and why each one exists:
  * the three §14 display-label surfaces — the operator directive's one verbatim label prohibition
    ("do not display `Gemini CLI` for the Google AI Pro path"), which at the close review could be
    violated with the whole 1870-test suite green (validator BLOCKING-1);
  * `registered_providers()`'s U256 spawnability intersection, deletable with the suite green
    (validator MEDIUM-1);
  * the status bar's display-ceiling clamp (spec-audit MINOR-1 / U277);
  * the three halves of the launch-path enumeration scoping — the rule, the provider set (the
    WRONG entry, not the missing one: U275), and the seam's threading through the product path
    (validator MAJOR-2 / MAJOR-3).

Usage: `py -3.12 tools/mutation/_op12_close_mutations.py`
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import _bytecode_discipline as _discipline  # CU-A1 (U534)

MUTATIONS = [
    ("adapters/frontier/antigravity.py",
     b'ANTIGRAVITY_DISPLAY = "Gemini \xc2\xb7 Antigravity"',
     b'ANTIGRAVITY_DISPLAY = "Gemini CLI"',
     "tests/unit/test_op12_pane_picker.py"),
    ("adapters/frontier/grok_build.py",
     b'GROK_DISPLAY = "Grok Build"',
     b'GROK_DISPLAY = "Gemini CLI"',
     "tests/unit/test_op12_pane_picker.py"),
    ("control_plane/nodes/pane_picker.py",
     b'    (ANTIGRAVITY_ADAPTER, ANTIGRAVITY_DISPLAY, "frontier"),',
     b'    (ANTIGRAVITY_ADAPTER, "Gemini CLI", "frontier"),',
     "tests/unit/test_op12_pane_picker.py"),
    ("control_plane/nodes/pane_picker.py",
     b'    dispatchable = frozenset(FRONTIER_PANE_ADAPTERS) | {OLLAMA_LOCAL_ADAPTER}\n'
     b'    return frozenset(p for p, _display, _locality in _PROVIDER_TABLE) & dispatchable',
     b'    _ = FRONTIER_PANE_ADAPTERS, OLLAMA_LOCAL_ADAPTER\n'
     b'    return frozenset(p for p, _display, _locality in _PROVIDER_TABLE)',
     "tests/unit/test_op12_pane_picker.py"),
    ("terminal/statusbar/statusbar-model.js",
     b'    return Number.isInteger(recorded) ? Math.min(fromFeed, recorded) : fromFeed;',
     b'    return fromFeed;',
     "JS:terminal"),
    # Re-anchored at W-25. The code was RESTRUCTURED, not deleted: the old two-line
    # `if op12_probes is None and provider not in _OP12_PROVIDERS:` became an outer
    # `if op12_probes is None:` with the provider scoping moved into a ternary (spec-audit MAJOR-1,
    # U290). The mutation's INTENT is unchanged and is what was re-read: leave `op12_probes` as
    # None so `build_host_picker` probes the REAL host, which is the cross-provider egress the
    # scoping exists to prevent — a Gemini pane emitting `grok --version`/`grok models` to grok.com
    # under the operator's SuperGrok session.
    ("tools/live/emit_worker_launch.py",
     b'        op12_probes = (no_op12_probes() if provider not in _OP12_PROVIDERS\n'
     b'                       else only_op12_probe(provider))',
     b'        pass',
     "tests/unit/test_emit_worker_launch.py"),
    # the WRONG entry, not the missing one (U275): scope the OP-12 pair out of the set that owes
    # the probe and every OP-12 launch is verified against an enumeration with no OP-12 options
    ("tools/live/emit_worker_launch.py",
     b'_OP12_PROVIDERS = (GROK_ADAPTER, ANTIGRAVITY_ADAPTER)',
     b'_OP12_PROVIDERS = ()',
     "tests/unit/test_emit_worker_launch.py"),
    ("tools/live/emit_worker_launch.py",
     b'        option = _assert_option_offered(option, role, offered_options, op12_probes)',
     b'        option = _assert_option_offered(option, role, offered_options)',
     "tests/unit/test_emit_worker_launch.py"),
]


def run(selector: str) -> tuple[bool, str]:
    if selector.startswith("JS:"):
        # Node 24 needs the GLOB, not the directory: `--test test/` resolves as a module and exits
        # nonzero with MODULE_NOT_FOUND, which reads as RED for every mutation whether guarded or
        # not. Caught while re-running the suites at the 18B close — a mutation harness that cannot
        # go green proves nothing, so the first JS result from this runner was discarded.
        proc = subprocess.run([r"D:\Program Files\nodejs\node.exe", "--test", "test/*.test.js"],
                              cwd=ROOT / selector.split(":", 1)[1], capture_output=True, text=True,
                              env=_discipline.child_env())
        if "MODULE_NOT_FOUND" in (proc.stdout + proc.stderr):
            raise RuntimeError("node could not load the test glob - harness fault, not a verdict")
    else:
        proc = subprocess.run([sys.executable, "-m", "pytest", selector, "-q"],
                              cwd=ROOT, capture_output=True, text=True,
                              env=_discipline.child_env())
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    return proc.returncode == 0, tail[-1] if tail else ""


def main() -> int:
    bad = 0
    for rel, old, new, selector in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        if old not in original:
            print(f"[SETUP-FAIL] {rel}: anchor not found -> {old[:60]!r}")
            bad += 1
            continue
        path.write_bytes(original.replace(old, new, 1))
        _discipline.invalidate_for(path)
        try:
            green, line = run(selector)
        finally:
            path.write_bytes(original)
        _discipline.invalidate_for(path)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        identical = after == before
        verdict = "GREEN (NOT GUARDED)" if green else "RED (guarded)"
        if green:
            bad += 1
        print(f"[{verdict}] {rel} :: {new[:52]!r}\n"
              f"          selector={selector} last={line!r} restore_byte_identical={identical} "
              f"sha256={after[:16]}")
        if not identical:
            bad += 1
    print(f"\nunguarded-or-broken: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
