"""The Phase 19 calibrated gate runner (punch list 2.6, W-24).

ONE bounded command that runs every instrument this programme calibrated, and
emits a MACHINE-READABLE result that distinguishes five states. It deliberately
does not reduce to a single green boolean, because the thing this repository
keeps rediscovering is that a green from an uncalibrated instrument is worse than
a red — it is a claim nobody re-checks.

FIVE STATES, and the distinctions are load-bearing:

  PASS                      the step ran here and succeeded.
  FAIL                      the step ran here and failed. Blocking.
  SKIP                      not applicable on this host, with the missing
                            prerequisite NAMED.
  NOT_VERIFIED_ON_THIS_HOST the step cannot be executed here at all. NOT a pass,
                            NOT a failure — an outstanding validation leg.
  KNOWN_OPEN_DEBT           a DECLARED, register-backed open finding. It is not
                            green, and it is not a fresh regression either.

RECEIPT SEMANTICS, ruled and enforced by `receipt_debt_report()`:

  readable                    != passing
  waived-for-ingestion        != resolved
  superseded historical       -> nonblocking
  current unresolved          -> KNOWN_OPEN_DEBT, never PASS

W-19 proved the four 18E receipts can be READ and classified. It did not prove
their condition passed — this host measures 0 passing / 4 failing for that unit
with the workspace-trust condition still live. If this runner ever reports them
as PASS, the composition has silently converted an ingestion waiver into an
acceptance, which is precisely what it must not do.

EXIT CODES, which also refuse to collapse:
  0  every step PASS (SKIP / NOT_VERIFIED are reported but do not block)
  1  at least one FAIL
  2  no FAIL, but at least one KNOWN_OPEN_DEBT or NOT_VERIFIED_ON_THIS_HOST

Run from the repository root:  py -3.12 tools/run_phase19_gate.py
                               py -3.12 tools/run_phase19_gate.py --json report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = "phase19_gate_report@1.0"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
NOT_VERIFIED = "NOT_VERIFIED_ON_THIS_HOST"
KNOWN_OPEN_DEBT = "KNOWN_OPEN_DEBT"


@dataclass
class Step:
    name: str
    argv: list[str]
    timeout_s: float
    cwd: Path = ROOT
    #: Register row + reason. A step listed here that FAILS is a declared debt, not a regression.
    debt: "Debt | None" = None
    #: Missing prerequisite -> this step is SKIPped, naming it.
    requires: str | None = None


@dataclass
class Result:
    name: str
    state: str
    detail: str
    exit_code: int | None = None
    duration_s: float = 0.0
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"step": self.name, "state": self.state, "detail": self.detail,
                "exit_code": self.exit_code, "duration_s": round(self.duration_s, 2),
                "evidence": self.evidence}


# ---------------------------------------------------------------------------------------------
# DECLARED DEBTS. A failure here is KNOWN_OPEN_DEBT rather than FAIL, and each cites its register
# row. Nothing becomes a debt by failing — it becomes a debt by being WRITTEN DOWN here first.
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Debt:
    """A registered open finding, FINGERPRINTED.

    Registration is not permission to downgrade arbitrary failure. A registered step whose failure
    does not match this fingerprint exactly is a NEW defect wearing an old badge, and is reported
    as FAIL.
    """

    register_row: str
    why: str
    exit_code: int
    #: Every one of these must appear in the step's output for the failure to be THIS failure.
    signatures: tuple[str, ...]

    def matches(self, exit_code: int | None, output: str) -> tuple[bool, str]:
        if exit_code != self.exit_code:
            return False, f"exit {exit_code}, registered debt expects exit {self.exit_code}"
        missing = [s for s in self.signatures if s not in output]
        if missing:
            return False, f"output no longer carries {missing!r}"
        return True, ""


DECLARED_DEBTS: dict[str, Debt] = {
    "mutation:_op18d_close_mutations": Debt(
        register_row="U446",
        why=("row R3 (`the incarnation is asked of memory, not of the log`) does not hold at HEAD: "
             "the mutation applies and its grading test still passes. Proven PRE-EXISTING by "
             "re-running with the W-03 changes stashed. Owner: Tier 2 calibration."),
        exit_code=1,
        signatures=(
            "28/29 RED",                    # 27/29 would be a SECOND row failing -> FAIL
            "all restores byte-identical",  # a diverged restore is never a debt
            "R3",                           # it must still be R3 that does not hold
            "GREEN (guard does not hold)",
        )),
}

#: Receipts whose CURRENT unresolved condition is registered: filename -> SHA-256 OF ITS BYTES.
#:
#: The filename alone was not enough, and the gap is the same class this runner exists to close: a
#: registered receipt could keep its name, have its CONTENTS replaced, and still be recognised as
#: the old debt. Filename is identity; the hash is the fingerprint of the KNOWN CONDITION.
#:
#: Deliberately literal, with a useful consequence: when one of these is genuinely repaired, its
#: hash changes and this runner REFUSES to keep calling it old debt. It must then be re-adjudicated
#: and re-registered, or removed. A machine should be annoying about that.
#:
#: ⚠ RE-TAKE THIS PIN AFTER ANY NORMALIZATION PASS. A content-pinned registry is only as stable as
#: the bytes beneath it, and a pass that rewrites bytes WITHOUT changing meaning will invalidate
#: every hash here. W-26's CRLF/BOM sweep normalised two of these receipts
#: (PHASE17C_DISARM_FALSIFICATION.json, PHASE18C_PROBE_ENGINE_REPORT.json); it happened to land
#: BEFORE this pin was taken, which was ordering luck rather than design. Had it landed after, both
#: would now read FAIL for a reason having nothing to do with their condition, and whoever inherited
#: that would be debugging a phantom. So: after any encoding repair, EOL sweep, or re-serialisation
#: that touches docs/evidence/receipts/, re-take these hashes and say in the commit that only the
#: ENCODING moved — never re-take them to make a red run green.
REGISTERED_UNRESOLVED_RECEIPTS: dict[str, str] = {
    "FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json":
        "412c0932494db8f6db9b4d456b472bc7519ea267ef18f1221060486e5ddb968c",
    "FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json":
        "e31f0c8a0d86032b6ac61b8dff342e78f1bfc14c489fb4c118fc17250a8b1953",
    "PHASE17C_DISARM_FALSIFICATION.json":
        "2f6c03153e12c70ea62a828ec2ac8cfdea160905a36b5cdd5486a5d7811f5a7b",
    "PHASE18C_ACCEPTANCE_SELFCHECK.json":
        "bb2d5e8391db58d59e7af524683a6975eff7ff47d1f91f9fa0a3ca03ff6022e2",
    "PHASE18C_PROBE_ENGINE_REPORT.json":
        "83aa16622caa55e69c2202a35c3cc09331ebbacac6a839c91001cc4403368fc7",
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json":
        "3b803daa1983965f90e2785adfae50fa6599c93b78a08e9f4ecc0cf53b4c64e9",
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0726Z.json":
        "5fdb93ee1b177f69b9095d85f88f9bf15527966ae203a30299e916d83a574e10",
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0758Z.json":
        "c12179438a537d6a025c438204b1756476f37b2b9b2751486a3eeb84b15851bc",
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_phase-18e.close_20260802T082536Z.json":
        "33a05ac95ed02173f0ab5e6aed53255ada8d130bd131cf02dc97d859c2ff856c",
}


def registered_debt_state(directory: Path, name: str) -> tuple[bool, str]:
    """Is THIS file the registered known condition? `(matches, why_not)`.

    Both halves must hold: the exact registered filename AND the exact registered bytes. A renamed
    copy of a known debt is not registered under its new name and therefore does not match.
    """
    expected = REGISTERED_UNRESOLVED_RECEIPTS.get(name)
    if expected is None:
        return False, "not a registered receipt filename"
    path = directory / name
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return False, f"registered receipt could not be read: {exc}"
    if actual != expected:
        return False, (f"content changed: sha256 {actual[:16]}… != registered {expected[:16]}… — "
                       f"re-adjudicate it rather than carrying the old debt forward")
    return True, ""


def _node() -> str | None:
    return shutil.which("node")


def _npm() -> str | None:
    return shutil.which("npm")


def _terminal_test_files() -> list[str]:
    """The COMPLETE measured set, from W-27's pin — never a glob."""
    from tests.unit.test_terminal_suite_coverage import EXPECTED_FILES

    return [f"terminal/test/{name}" for name in EXPECTED_FILES]


def build_steps() -> list[Step]:
    node, npm = _node(), _npm()
    steps: list[Step] = [
        Step("python-suite",
             [sys.executable, "tools/run_phase19_pytest.py", "full"], 1500.0),
        Step("freeze-check",
             [sys.executable, "tools/manifest/compute_manifest.py", "--check"], 300.0),
        # These policies live in the Python suite; they are re-run as NAMED steps so the report
        # carries a state for each instrument rather than one aggregate.
        Step("receipt-reader",
             [sys.executable, "-m", "pytest", "-q", "tests/unit/test_evidence_receipts.py"], 300.0),
        Step("text-integrity",
             [sys.executable, "-m", "pytest", "-q", "tests/unit/test_text_integrity.py"], 300.0),
        Step("skip-count-policy",
             [sys.executable, "-m", "pytest", "-q", "tests/unit/test_js_skip_policy.py"], 300.0),
        Step("host-prerequisites",
             [sys.executable, "-m", "pytest", "-q", "tests/unit/test_host_prerequisites.py"], 300.0),
        Step("test-surface-guard",
             [sys.executable, "-m", "pytest", "-q",
              "tests/unit/test_no_vacuous_test_surface.py"], 300.0),
        Step("live-call-guard",
             [sys.executable, "-m", "pytest", "-q",
              "tests/unit/test_no_live_provider_calls_in_suite.py"], 600.0),
    ]

    steps.append(Step("desktop-js-suite", [npm or "npm", "test"], 1200.0,
                      cwd=ROOT / "apps" / "desktop",
                      requires=None if npm else "npm on PATH"))
    steps.append(Step("terminal-js-suite",
                      [node or "node", "--test", *_terminal_test_files()], 900.0,
                      requires=None if node else "node on PATH"))

    for path in sorted((ROOT / "tools" / "mutation").glob("*.py")):
        if path.name.startswith("__"):
            continue
        name = f"mutation:{path.stem}"
        steps.append(Step(name, [sys.executable, f"tools/mutation/{path.name}"], 1200.0,
                          debt=DECLARED_DEBTS.get(name)))
    for path in sorted((ROOT / "tools" / "mutation").glob("*.js")):
        name = f"falsification:{path.stem}"
        # Run from the repository root: each JS harness resolves ROOT itself via
        # `path.resolve(__dirname, "..", "..")`, so it does not need the desktop cwd its npm
        # script happens to use.
        steps.append(Step(name, [node or "node", f"tools/mutation/{path.name}"], 1200.0,
                          debt=DECLARED_DEBTS.get(name),
                          requires=None if node else "node on PATH"))
    return steps


def run_step(step: Step) -> Result:
    if step.requires:
        return Result(step.name, SKIP, f"host prerequisite missing: {step.requires}")
    started = time.perf_counter()
    try:
        proc = subprocess.run(step.argv, cwd=step.cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=step.timeout_s,
                              check=False)
    except subprocess.TimeoutExpired:
        return Result(step.name, FAIL, f"exceeded its {step.timeout_s:g}s ceiling",
                      duration_s=time.perf_counter() - started)
    except OSError as exc:
        return Result(step.name, FAIL, f"could not be spawned: {exc}",
                      duration_s=time.perf_counter() - started)

    duration = time.perf_counter() - started
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-3:])
    if proc.returncode == 0:
        return Result(step.name, PASS, tail or "ok", proc.returncode, duration)
    if step.debt:
        combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        same, mismatch = step.debt.matches(proc.returncode, combined)
        if same:
            return Result(step.name, KNOWN_OPEN_DEBT,
                          f"{step.debt.register_row}: {step.debt.why}",
                          proc.returncode, duration,
                          {"register_row": step.debt.register_row,
                           "fingerprint_matched": list(step.debt.signatures), "tail": tail})
        return Result(step.name, FAIL,
                      f"registered as {step.debt.register_row} but the failure DOES NOT MATCH that "
                      f"fingerprint ({mismatch}) — a new defect may not inherit a registered "
                      f"debt's status. Tail: {tail}",
                      proc.returncode, duration, {"expected_debt": step.debt.register_row})
    return Result(step.name, FAIL, tail or f"exit {proc.returncode}", proc.returncode, duration)


def receipt_debt_report() -> list[Result]:
    """The ruled receipt semantics, enforced as its own step.

    A waiver in W-19's table means the evidence system can INGEST a historical receipt shape. It
    does not mean the condition passed. A waived receipt whose unit has NO later passing receipt is
    a CURRENT unresolved failure and is reported as KNOWN_OPEN_DEBT — never PASS.
    """
    from tests.unit.test_evidence_receipts import OK, RECEIPTS, WAIVED, read_receipts

    verdicts = read_receipts(RECEIPTS)
    # A receipt's UNIT is its name up to the `_SELFCHECK` suffix, which is what groups a
    # pre-repair run with the later run that superseded it.
    by_unit: dict[str, dict[str, int]] = {}
    for name, verdict in verdicts.items():
        unit = name.split("_SELFCHECK")[0]
        bucket = by_unit.setdefault(unit, {"pass": 0, "notpass": 0})
        bucket["pass" if verdict == OK else "notpass"] += 1

    results: list[Result] = []
    superseded, unresolved, unregistered = [], [], []
    for name, (verdict, _why) in sorted(WAIVED.items()):
        unit = name.split("_SELFCHECK")[0]
        counts = by_unit.get(unit, {"pass": 0, "notpass": 0})
        row = {"receipt": name, "verdict": verdict, "unit": unit,
               "unit_passing": counts["pass"], "unit_not_passing": counts["notpass"]}
        if counts["pass"] > 0:
            superseded.append(row)
            continue
        registered, why_not = registered_debt_state(RECEIPTS, name)
        if registered:
            unresolved.append(row)
        else:
            # Waived for INGESTION, unit has no passing sibling, and NOT the registered condition
            # -- either an unregistered filename, or the registered filename carrying DIFFERENT
            # bytes. Neither may inherit a debt by belonging to the same unit as one.
            unregistered.append({**row, "why_not_registered": why_not})

    results.append(Result(
        "receipts:superseded-historical", PASS,
        f"{len(superseded)} waived receipt(s) whose unit has a later passing receipt — "
        f"nonblocking, and READ rather than treated as a parser failure",
        evidence={"receipts": superseded}))

    if unresolved:
        results.append(Result(
            "receipts:current-unresolved", KNOWN_OPEN_DEBT,
            f"{len(unresolved)} REGISTERED unresolved receipt(s). Waived for INGESTION, not "
            f"resolved: readable != passing. These may never report PASS.",
            evidence={"receipts": unresolved}))
    else:
        results.append(Result("receipts:current-unresolved", PASS,
                              "no registered unresolved receipt"))

    if unregistered:
        results.append(Result(
            "receipts:unregistered-failure", FAIL,
            f"{len(unregistered)} waived receipt(s) have no passing sibling and are NOT in "
            f"REGISTERED_UNRESOLVED_RECEIPTS. A new failure may not inherit a registered debt by "
            f"belonging to the same unit — register it deliberately or repair it.",
            evidence={"receipts": unregistered}))
    else:
        results.append(Result("receipts:unregistered-failure", PASS,
                              "every unresolved waived receipt is registered by name"))
    return results


def not_verified_legs() -> list[Result]:
    """Validation this host CANNOT perform. Reported so they cannot quietly become evidence."""
    return [
        Result("linux-clean-checkout", NOT_VERIFIED,
               "Linux clean-checkout acceptance: NOT VERIFIED ON THIS HOST. The host-prerequisite "
               "gating (W-22) is proved here by injection; the off-host acceptance leg has not run."),
        Result("missing-py312-skip-behaviour", NOT_VERIFIED,
               "The 28 cross-language legs skipping when `py -3.12` is absent was NOT executed. "
               "W-23 proves the POLICY over a skip count by injection, not the host behaviour."),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase 19 calibrated gate runner")
    ap.add_argument("--json", type=Path, default=None, help="also write the report here")
    ap.add_argument("--only", default=None, help="substring filter over step names")
    ns = ap.parse_args(argv)

    steps = [s for s in build_steps() if not ns.only or ns.only in s.name]
    results: list[Result] = []
    for step in steps:
        result = run_step(step)
        results.append(result)
        print(f"{result.state:<26} {result.name}  ({result.duration_s:.1f}s)", flush=True)

    for extra in receipt_debt_report() + not_verified_legs():
        results.append(extra)
        print(f"{extra.state:<26} {extra.name}", flush=True)

    counts = {state: sum(1 for r in results if r.state == state)
              for state in (PASS, FAIL, SKIP, NOT_VERIFIED, KNOWN_OPEN_DEBT)}
    report = {
        "schema": SCHEMA,
        "generated_by": "tools/run_phase19_gate.py",
        "summary": counts,
        # Stated so no reader has to infer it: this is NOT one boolean.
        "verdict_note": ("PASS counts only steps that ran and succeeded HERE. "
                         "NOT_VERIFIED_ON_THIS_HOST is neither pass nor failure. "
                         "KNOWN_OPEN_DEBT is a declared, register-backed open finding and is not "
                         "green."),
        "steps": [r.as_dict() for r in results],
    }
    text = json.dumps(report, indent=2, sort_keys=False)
    if ns.json:
        ns.json.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)

    if counts[FAIL]:
        return 1
    if counts[KNOWN_OPEN_DEBT] or counts[NOT_VERIFIED]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
