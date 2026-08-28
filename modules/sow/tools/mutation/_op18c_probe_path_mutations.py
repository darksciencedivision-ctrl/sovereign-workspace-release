"""Mutation runner for the governed probe path added at Phase 18C `.probe-path` (U234).

Same contract as `_op12_close_mutations.py`, and kept in the tree for the same reason: a mutation
result asserted in a report is prose that cannot disagree with its value. Run it and the verdicts
are reproduced.

Each entry: (path, old_bytes, new_bytes, selector). It applies the mutation, runs the selector,
records RED (a test caught it) or GREEN (nothing did), restores the original bytes, and verifies the
restore is BYTE-IDENTICAL by sha256. Exit 1 if anything is GREEN or a restore diverges.

What each mutation is about:
  1. **the U75-class defect this unit's own test found before the reviewers did** — counting the
     governor by node id instead of lease key made a SECOND concurrent probe of one provider an
     idempotent re-acquire: it ran uncounted and then released a lease the first probe still held;
  2. the durable lease never released ⇒ the probe leaks the operator's single terminal (D-LOOP-1);
  3. the in-process governor never released;
  4. the R8 §6 operator-terms gate removed (invariant 1: not ours to assume);
  5. the CLI-presence gate downgraded to "resolve whatever answers to that name" (fail-open);
  6. the env scrub emptied ⇒ `XAI_API_KEY` reaches the child (§13/§2.2);
  7. the child's workspace binding dropped (`cwd=None` — "wherever we happened to start");
  8. `run_probe` bypassing the session entirely, which is the whole of U234 in one line;
  9. the unreachable-supervisor branch DOWNGRADING to the naked spawn instead of refusing;
 10. `_SUPERVISED_PROBE_PATH` pointing at a module that does not exist (the flag is a CLAIM).

Added at the 18C review round, each one a GREEN a reviewer found — the mutations that mattered most
were the ones this file did not have:
 11. **`run_probe` selecting the naked `subprocess_runner` instead of the supervised one.** The
     single production line that discharges U234 could be swapped for the exact spawn it forbids
     with the whole suite green, because every test passed `runner=` and nothing ever exercised the
     `runner is None` wiring;
 12. the host deployment profile not reaching gate 1 (an air-gapped host opening a leased session);
 13. the OPERATOR's R8 §6 determination assumed rather than passed (invariant 1);
 14. the child's argv[0] not bound to the executable the gate resolved;
 15. `process_tree_clean` asserted `True` instead of measured from the boundary's own outcome.

**Scoring.** `run()` classifies by pytest's exit code: 0 ⇒ GREEN (nothing caught it), 1 ⇒ RED (a test
failed, i.e. guarded), and ANY OTHER code ⇒ SETUP-FAIL. The third case is the one this file used to
get wrong: it scored `return code != 0` as RED, so a mutation that produced a SyntaxError (exit 2) or
selected no tests at all (exit 5) was recorded as "a test caught it" — a harness that reports its own
breakage as evidence of safety.

Usage: `py -3.12 tools/mutation/_op18c_probe_path_mutations.py`
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import _bytecode_discipline as _discipline  # CU-A1 (U534)

_SESSION = "node_runtime/supervisor/provider_probe_session.py"
_RECON = "tools/providers/frontier_provider_recon.py"
_SESSION_TESTS = "tests/unit/test_op12_probe_session.py"
_SCOPE_TESTS = "tests/unit/test_op12_provider_scope.py"

MUTATIONS = [
    (_SESSION,
     b"    gov.acquire(ref, lease_key)",
     b"    gov.acquire(ref, node_id)",
     _SESSION_TESTS),
    (_SESSION,
     b"                    lease_released = led.release(lease.lease_id)",
     b"                    lease_released = True",
     _SESSION_TESTS),
    (_SESSION,
     b"            gov.release(ref, lease_key)",
     b"            pass",
     _SESSION_TESTS),
    (_SESSION,
     b"    if not operator_terms_confirmed:",
     b"    if False:",
     _SESSION_TESTS),
    (_SESSION,
     b"    if not (isinstance(resolved, str) and resolved.strip()):",
     b"    if False:",
     _SESSION_TESTS),
    (_SESSION,
     b"            env_scrub_names=tuple(worker_env_scrub_names(base_env)),",
     b"            env_scrub_names=(),",
     _SESSION_TESTS),
    (_SESSION,
     b"                                       stdin=subprocess.DEVNULL, cwd=session.workspace)",
     b"                                       stdin=subprocess.DEVNULL, cwd=None)",
     _SESSION_TESTS),
    (_RECON,
     b"    with stack:                     # the lease is released here on EVERY exit path (D-LOOP-1)",
     b"    if True:",
     _SCOPE_TESTS),
    # The unreachable-supervisor branch DOWNGRADING instead of refusing. The first spelling of this
    # one injected an undefined name (`_NEVER`), so it proved "a NameError propagates" — not the
    # property it names. This spelling is a faithful downgrade: the branch falls through to the
    # naked `subprocess_runner`, exactly what a build with a broken supervisor must never do.
    (_RECON,
     b'            return None, {"refused_by": "supervision",',
     b'            factory = None; loader_factory = None  # noqa\n'
     b'            return None, {"refused_by": "downgraded-not-refused",',
     _SCOPE_TESTS),
    (_RECON,
     b'_PROBE_SESSION_MODULE = "node_runtime.supervisor.provider_probe_session"',
     b'_PROBE_SESSION_MODULE = "node_runtime.supervisor.gone"',
     _SCOPE_TESTS),
    # --- added at the 18C review round: five GREENs the reviewers found -------------------------
    (_RECON,
     b"        run = runner if runner is not None else _supervised_runner(session)",
     b"        run = runner if runner is not None else subprocess_runner()",
     _SCOPE_TESTS),
    (_RECON,
     b"            profile_loader=loader,",
     b"            profile_loader=__import__('control_plane.profiles.loader', fromlist=['x'])"
     b".ProfileLoader(__import__('control_plane.profiles.loader', fromlist=['x'])"
     b".DeploymentProfile('cloud')),",
     _SCOPE_TESTS),
    (_RECON,
     b"            operator_terms_confirmed=True,",
     b"",
     _SCOPE_TESTS),
    (_SESSION,
     b"        if not cmd or cmd[0] != session.executable:",
     b"        if False:",
     _SESSION_TESTS),
    (_SESSION,
     b"            session.process_tree_clean = False",
     b"            session.process_tree_clean = True",
     _SESSION_TESTS),
]


#: pytest's own exit codes. 0 = all passed, 1 = tests failed. Everything else (2 interrupted,
#: 3 internal error, 4 usage error, 5 no tests collected) means the RUN did not happen — which is
#: never evidence that a mutation was caught.
_PYTEST_ALL_PASSED = 0
_PYTEST_TESTS_FAILED = 1


def run(selector: str) -> tuple[str, str]:
    """Returns (verdict, last output line). Verdict is one of GREEN / RED / SETUP-FAIL."""
    proc = subprocess.run([sys.executable, "-m", "pytest", selector, "-q"],
                          cwd=ROOT, capture_output=True, text=True,
                          env=_discipline.child_env())
    tail = (proc.stdout or proc.stderr).strip().splitlines()
    line = tail[-1] if tail else ""
    if proc.returncode == _PYTEST_ALL_PASSED:
        return "GREEN", line
    if proc.returncode == _PYTEST_TESTS_FAILED:
        return "RED", line
    return "SETUP-FAIL", f"pytest exit {proc.returncode}: {line}"


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
            outcome, line = run(selector)
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
