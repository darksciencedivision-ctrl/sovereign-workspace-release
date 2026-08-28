"""Mutation runner for Phase 18C `.close` — the OP-12 acceptance verdict rules and the one
operator-facing instruction this unit corrected.

Same contract as `_op18c_probe_path_mutations.py`: apply the mutation, run the selector, record RED
(a test caught it) / GREEN (nothing did) / SETUP-FAIL (the run did not happen), restore the original
bytes, verify the restore is BYTE-IDENTICAL by sha256. Exit 1 if anything is GREEN or a restore
diverges. It is in the tree for the same reason: a mutation result asserted in a report is prose
that cannot disagree with its value.

What each mutation is about — every one of them is a way a GREEN 18C receipt could be produced by
the wrong world:

  1. **the world check inverted**: a host whose operator HAS opened the switch is read as
     fail-closed, so this receipt would stand in for the live legs it exists to say are owed;
  2. **an unreadable authorization read as fail-closed** — "we could not tell" recorded as
     "we checked";
  3. **the gate id stops being read**: any refusal, from any gate, accepted as evidence about the
     operator's switch (the `_gate_id` lesson: prose can be borrowed, an id cannot);
  4. **`selection_offered` no longer required**: a refusal at the host-enumeration gate — i.e. the
     option was never the host's — accepted as the live gate's;
  5. **`cli_present` no longer required**: an absent CLI refuses identically on an authorized host,
     so the receipt would prove nothing about the switch;
  6. **the two producers no longer have to agree** about which gate refused;
  7. **a refusal that took a lease** accepted as fail-closed;
  8. **the session count no longer compared**: a refusal that started something passes;
  9. **§14 crossed-provider text** no longer refused;
 10. **an absent ledger entry treated as unknown-but-fine** — the leg's whole point is that
     unknown fails closed;
 11. **the painted status-bar text no longer read**: "visible" degraded to "computed" (invariant 27);
 12. **a credential scan with nothing to look for** scored as clean;
 13. **an unread log sink** scored as clean;
 14. **the OWED block no longer required to cite anything** a reader can look up;
 15. **the corrected operator instruction reverted** to the sentence that stopped being true when
     18B `.scope` shipped the code-pinned extension (U289).

**Scoring, and the Node half of it.** Python selectors are classified by pytest's exit code
(0 GREEN, 1 RED, anything else SETUP-FAIL). Node selectors CANNOT be, and this is the 18B `.close`
lesson made permanent: `node --test` exits non-zero for reasons that are not a failing test at all
(a module resolution error under Node 24 exits 1 with MODULE_NOT_FOUND), which reads as RED for a
mutation nothing guarded. So a Node run is RED only when the TAP summary reports at least one
failure, and any other non-zero outcome is SETUP-FAIL.

Usage: `py -3.12 tools/mutation/_op18c_close_mutations.py`
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import _bytecode_discipline as _discipline  # CU-A1 (U534)

_VERDICT = "apps/desktop/selfcheck/op12-acceptance-verdict.js"
_RECON = "tools/providers/frontier_provider_recon.py"
_JS_TESTS = "apps/desktop/test/op12-acceptance-verdict.test.js"
_RECON_TESTS = "tests/unit/test_frontier_provider_recon.py"

#: (path, old_bytes, new_bytes, selector, kind) — kind is "node" or "pytest".
MUTATIONS = [
    (_VERDICT,
     b"  const op12 = OP12_PROVIDERS.filter((p) => providers.includes(p));\n  if (op12.length) {",
     b"  const op12 = OP12_PROVIDERS.filter((p) => providers.includes(p));\n  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (!providers) {\n    return {\n      fail_closed: false,",
     b"  if (!providers) {\n    return {\n      fail_closed: true,",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (ticket.refused_by !== LIVE_GATE_ID) {",
     b"  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (gates.selection_offered !== true) {",
     b"  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (gates.cli_present !== true) {",
     b"  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (launch.refusedBy !== ticket.refused_by) {",
     b"  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (ticket.lease !== null && ticket.lease !== undefined) {",
     b"  if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  } else if (a.sessions_after !== a.sessions_before) {",
     b"  } else if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  return (FOREIGN_WORDS[provider] || []).filter((w) => prose.includes(w));",
     b"  return [];",
     _JS_TESTS, "node"),
    # …and the other direction: the stripping that makes the rule usable in the world 18C is trying
    # to reach must not swallow the prose it is supposed to read.
    (_VERDICT,
     b'  return String(text || "").replace(/\\[[^\\]]*\\]/g, " ");',
     b'  return " ";',
     _JS_TESTS, "node"),
    (_VERDICT,
     b"    const foreign = foreignWordsIn(r.error, provider);\n    if (foreign.length) {",
     b"    const foreign = foreignWordsIn(r.error, provider);\n    if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"    if (entry === undefined || entry === null) { inUse[ref] = 0; continue; }",
     b"    if (entry === undefined || entry === null) { inUse[ref] = null; continue; }",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"    } else if (!text.includes(`0/${OP12_ALLOWANCE}`)) {",
     b"    } else if (false) {",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"  if (!values.length) {\n    reasons.push(\"no sentinel value was planted",
     b"  if (false) {\n    reasons.push(\"no sentinel value was planted",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"    if (typeof text !== \"string\") {\n      reasons.push(`${name} could not be read",
     b"    if (false) {\n      reasons.push(`${name} could not be read",
     _JS_TESTS, "node"),
    (_VERDICT,
     b"    if (!OWED_REFERENCE.test(value)) {",
     b"    if (false) {",
     _JS_TESTS, "node"),
    (_RECON,
     b"    if not covered:\n        return (\"To open it, editing that file is NOT sufficient",
     b"    if True:\n        return (\"To open it, editing that file is NOT sufficient",
     _RECON_TESTS, "pytest"),
]


#: pytest's own exit codes. 0 = all passed, 1 = tests failed. Everything else (2 interrupted,
#: 3 internal error, 4 usage error, 5 no tests collected) means the RUN did not happen — which is
#: never evidence that a mutation was caught.
_PYTEST_ALL_PASSED = 0
_PYTEST_TESTS_FAILED = 1

#: `node --test`'s TAP summary. A Node run counts as RED only if it reports a failing TEST; every
#: other non-zero outcome (a module that would not resolve, a syntax error before the runner starts)
#: is the harness's own breakage and must never be scored as safety.
#: The summary line's MARKER is the reporter's choice and is not even stable through this pipe:
#: `node --test` writes `# fail N` under the tap reporter and `ℹ fail N` under the spec reporter
#: it picks here, and that marker arrives mangled unless the pipe is decoded as UTF-8 (it is, below).
#: So the marker is SKIPPED and the COUNT is what is read. Two earlier spellings both scored every
#: Node run SETUP-FAIL — failing safe, and reporting nothing: `[#ℹ]` (the character does not
#: survive the default decode) and `\W{0,4}` (`ℹ`.isalnum() is True in Python, so it is a WORD
#: character and `\W` never matches it — a rule that looked right and was empirically false).
_NODE_FAIL_LINE = re.compile(r"^.{0,4}fail\s+(\d+)\s*$", re.M)


def run(selector: str, kind: str) -> tuple[str, str]:
    """Returns (verdict, last output line). Verdict is one of GREEN / RED / SETUP-FAIL."""
    if kind == "pytest":
        cmd = [sys.executable, "-m", "pytest", selector, "-q"]
    else:
        cmd = ["node", "--test", selector]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=_discipline.child_env())
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = out.strip().splitlines()
    line = tail[-1] if tail else ""
    if kind == "pytest":
        if proc.returncode == _PYTEST_ALL_PASSED:
            return "GREEN", line
        if proc.returncode == _PYTEST_TESTS_FAILED:
            return "RED", line
        return "SETUP-FAIL", f"pytest exit {proc.returncode}: {line}"
    m = _NODE_FAIL_LINE.search(out)
    if m is None:
        return "SETUP-FAIL", f"node exit {proc.returncode}, no TAP summary: {line}"
    failed = int(m.group(1))
    summary = next((ln for ln in out.splitlines() if ln.startswith("# fail")), line)
    if failed > 0:
        return "RED", summary
    if proc.returncode != 0:
        return "SETUP-FAIL", f"node exit {proc.returncode} with 0 reported failures: {line}"
    return "GREEN", summary


#: The lock + restore contract `pane_input_bypass_mutations.js` documents at length and neither
#: Python harness had (spec-audit MINOR-13). Both files this one mutates are PRODUCT files: a
#: Ctrl-C mid-run would otherwise leave `if (false) {` in the module that decides what the 18C
#: receipt may claim, or `if True:` in the operator's denial text, with nothing able to detect it.
_LOCK = ROOT / "tools" / "mutation" / ".op18c_close.lock"


@contextlib.contextmanager
def _restore_guard(targets: dict[Path, bytes]):
    """Restore every mutated file on ANY exit — normal, exception, or SIGINT/SIGTERM/SIGBREAK.

    The signal handlers raise `KeyboardInterrupt`, which unwinds through the `finally` below rather
    than killing the process where it stands. A stale lock file is a REFUSAL to run: it means a
    previous run was hard-killed and the tree may still carry a mutation, which is exactly the state
    where adopting whatever is on disk as "the original" would launder it."""
    if _LOCK.exists():
        raise SystemExit(
            f"{_LOCK} exists: a previous run did not finish. Verify every file below matches git "
            f"(`git diff --stat -- {' '.join(sorted(str(p.relative_to(ROOT)) for p in targets))}`) "
            "before deleting the lock.")
    _LOCK.write_text(f"pid {os.getpid()}\n", encoding="utf-8")

    def _interrupt(_sig, _frame):
        raise KeyboardInterrupt

    previous = []
    for name in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            previous.append((sig, signal.signal(sig, _interrupt)))
        except (ValueError, OSError):   # not settable on this platform/thread
            pass
    try:
        yield
    finally:
        for path, original in targets.items():
            if path.read_bytes() != original:
                path.write_bytes(original)
                _discipline.invalidate_for(path)
                print(f"[restored] {path.relative_to(ROOT)}")
        for sig, handler in previous:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)
        _LOCK.unlink(missing_ok=True)


def main() -> int:
    targets = {ROOT / rel: (ROOT / rel).read_bytes() for rel, *_ in MUTATIONS}
    with _restore_guard(targets):
        return _run_all()


def _run_all() -> int:
    bad = 0
    for rel, old, new, selector, kind in MUTATIONS:
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
            outcome, line = run(selector, kind)
        finally:
            path.write_bytes(original)
        _discipline.invalidate_for(path)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        identical = after == before
        verdict = {"GREEN": "GREEN (NOT GUARDED)", "RED": "RED (guarded)",
                   "SETUP-FAIL": "SETUP-FAIL (the run did not happen — NOT evidence)"}[outcome]
        if outcome != "RED":
            bad += 1
        print(f"[{verdict}] {rel} :: {new[:56]!r}\n"
              f"          selector={selector} last={line!r} restore_byte_identical={identical} "
              f"sha256={after[:16]}")
        if not identical:
            bad += 1
    print(f"\nunguarded-or-broken: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
