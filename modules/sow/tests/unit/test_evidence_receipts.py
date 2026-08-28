"""Every committed receipt is READ (punch list 2.1, W-19; M-7).

The audit found 86 receipts under `docs/evidence/receipts/` of which 15 report
`ok: false` and 3 carry no `ok` field at all — and nothing in any suite ever
opened one. A receipt that nobody reads is a file, not evidence.

WHAT THIS GATE IS. It fails on any receipt that does not report success, unless
that receipt is in the waiver table below. The waiver is not a mute button: each
entry PINS the verdict the receipt actually carries, so a waived receipt that
changes still fails, a waiver for a receipt that no longer exists still fails,
and a NEW receipt cannot inherit a waiver by reusing a name.

M-7 closed two gaps in this machinery:
  1. the fail-on-undeclared-`ok:false` behavior is now PROVEN by a negative
     end-to-end test (`undeclared_failures` is the extracted gate decision, and
     a fresh unwaived `ok:false` receipt is shown to be flagged by exactly the
     code path the real gate runs);
  2. every waiver carries a MACHINE-readable kind (`WAIVER_KINDS`) from a fixed
     vocabulary — the deliberate-falsification receipts among them are tagged
     `deliberate_falsification`, so the class is identifiable by code, not only
     by the prose reason.

`docs/evidence/` is append-only evidence, so no receipt is edited to make this
pass. A historical failure stays recorded as a failure and is waived with the
reason it is not a live regression.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RECEIPTS = REPO / "docs" / "evidence" / "receipts"

#: Verdict vocabulary this reader emits, so a caller never has to re-derive one.
OK = "ok"
FAILED = "ok:false"
NO_VERDICT = "no `ok` field"


def receipt_verdict(payload: object) -> str:
    """The verdict a receipt reports, or NO_VERDICT when it reports none in this vocabulary."""
    if not isinstance(payload, dict) or "ok" not in payload:
        return NO_VERDICT
    return OK if payload["ok"] is True else FAILED


def read_receipts(directory: Path) -> dict[str, str]:
    """`name -> verdict` for every `*.json` under `directory`. Unparsable is its own answer:
    a receipt that cannot be read is not a receipt that passed."""
    out: dict[str, str] = {}
    for path in sorted(directory.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out[path.name] = f"unreadable: {type(exc).__name__}"
            continue
        out[path.name] = receipt_verdict(payload)
    return out


#: Historical receipts consciously waived. `name -> (verdict it carries, why it is not a live
#: regression)`. Populated only AFTER this gate was run with an empty table and shown to go red on
#: all 18 — an instrument that passes on first contact has not been calibrated, it has been
#: assumed.
_SUPERSEDED = ("historical intermediate run: a LATER receipt for the same unit reports ok:true, "
               "so this records a state that was true when written and is not a live regression")
_LIVE_BLOCKED = ("18E live acceptance, NOT superseded — this unit has 0 passing receipts and 4 "
                 "failing. Grok Build waits on its own workspace_trust gate, which the loop may "
                 "not answer (invariant 1). A real, still-open live-run blocker, waived as READ "
                 "rather than as resolved")

WAIVED: dict[str, tuple[str, str]] = {
    # -- a different receipt SCHEMA: `result`/`failed_leg`, no `ok` field ------------------------
    "FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json": (
        NO_VERDICT,
        "carries `result: PARTIAL_ACCEPTANCE` instead of `ok`. Its own `failed_leg` names the gap: "
        "no real microphone utterance was submitted, because Phase D was not run after Phase A "
        "failed strict worker readiness (Gemini AUTH_REQUIRED, Grok USAGE_LIMIT)"),
    "FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json": (
        NO_VERDICT,
        "carries `result: PARTIAL_ACCEPTANCE` instead of `ok`. Its `validation` block records the "
        "gap honestly: the full Python suite timed out at the explicit 600 s ceiling without a "
        "result and is NOT counted as passed"),
    "PHASE18C_PROBE_ENGINE_REPORT.json": (
        NO_VERDICT,
        "a probe-engine REPORT, not a selfcheck: it carries no verdict field of any kind. Waived "
        "as unreadable-by-this-gate rather than as passing"),

    # -- 17C: a falsification receipt whose own checks failed ------------------------------------
    "PHASE17C_DISARM_FALSIFICATION.json": (
        FAILED,
        "17C disarm falsification; its failed_checks name "
        "`receipt_matches_committed_tracked_product_tree_with_disclosed_exclusions` and "
        "`operator_keystroke_disarmed_the_voice_turn`. Historical, predates this baseline, and no "
        "later 17C receipt supersedes it — waived as READ, not as resolved"),

    # -- 18C/18E: live acceptance blocked on provider gates, NOT superseded -----------------------
    "PHASE18C_ACCEPTANCE_SELFCHECK.json": (
        FAILED,
        "18C live acceptance: the operator's switch authorized grok_build/google_antigravity while "
        "the 18C acceptance expected the OP-6 pair. A scope mismatch recorded at the time"),
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json": (FAILED, _LIVE_BLOCKED),
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0726Z.json": (FAILED, _LIVE_BLOCKED),
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0758Z.json": (FAILED, _LIVE_BLOCKED),
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_phase-18e.close_20260802T082536Z.json": (
        FAILED, _LIVE_BLOCKED),

    # -- 19.3 / 19.4 / 19.6 / 19.7: intermediate rounds, each superseded by a later ok:true --------
    "PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json": (
        FAILED, _SUPERSEDED + " (this is leg B, the receipt that FALSIFIED the own-echo exclusion "
                              "and opened U360 — it is evidence of a repair, not of a defect)"),
    "PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.round1_20260810T114605Z.json": (
        FAILED, _SUPERSEDED),
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_ab-pre-repair_20260810T193555Z.json": (
        FAILED, _SUPERSEDED + " (named `ab-pre-repair`: it records the PRE-repair state on purpose)"),
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_diag_20260810T193721Z.json": (
        FAILED, _SUPERSEDED + " (a diagnostic run, not an acceptance run)"),
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round3-rerun_20260810T193502Z.json": (
        FAILED, _SUPERSEDED),
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round3_20260810T193358Z.json": (
        FAILED, _SUPERSEDED),
    "PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-clean-tree_20260811T084527Z.json": (
        FAILED, _SUPERSEDED),
    "PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-round1_20260811T084317Z.json": (
        FAILED, _SUPERSEDED),
    "PHASE19_7_RUNTIME_HONESTY_SELFCHECK_19.7_20260813T225618Z.json": (
        FAILED, _SUPERSEDED + " (its failed check was `rendered_prints_no_fabricated_zero_counts`; "
                              "the 19.7-round4-repairs receipt reports ok:true)"),
}

#: M-7: the machine-readable kind of every waiver, from a FIXED vocabulary. Prose reasons say
#: WHY; this table says WHAT CLASS the waived receipt belongs to, so code (not eyeballs) can
#: answer "which waived receipts are deliberate-falsification records?".
SUPERSEDED = "superseded"
LIVE_BLOCKED = "live_blocked"
NO_VERDICT_SCHEMA = "no_verdict_schema"
DELIBERATE_FALSIFICATION = "deliberate_falsification"
HISTORICAL_SCOPE_MISMATCH = "historical_scope_mismatch"
KINDS = frozenset({SUPERSEDED, LIVE_BLOCKED, NO_VERDICT_SCHEMA,
                   DELIBERATE_FALSIFICATION, HISTORICAL_SCOPE_MISMATCH})

WAIVER_KINDS: dict[str, str] = {
    # a different receipt schema: `result`/`failed_leg`/report shapes, no `ok` field
    "FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json": NO_VERDICT_SCHEMA,
    "FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json": NO_VERDICT_SCHEMA,
    "PHASE18C_PROBE_ENGINE_REPORT.json": NO_VERDICT_SCHEMA,
    # deliberate-falsification records: the ok:false IS the evidence — the run was meant to
    # show a failure state (a mutation caught, a pre-repair baseline, a diagnostic leg)
    "PHASE17C_DISARM_FALSIFICATION.json": DELIBERATE_FALSIFICATION,
    "PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json":
        DELIBERATE_FALSIFICATION,
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_ab-pre-repair_20260810T193555Z.json":
        DELIBERATE_FALSIFICATION,
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_diag_20260810T193721Z.json": DELIBERATE_FALSIFICATION,
    # live acceptance blocked on provider gates the loop may not answer — still-open
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json": LIVE_BLOCKED,
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0726Z.json": LIVE_BLOCKED,
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_CLOSE_20260802T0758Z.json": LIVE_BLOCKED,
    "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_phase-18e.close_20260802T082536Z.json": LIVE_BLOCKED,
    # one-off historical mismatch recorded at the time
    "PHASE18C_ACCEPTANCE_SELFCHECK.json": HISTORICAL_SCOPE_MISMATCH,
    # intermediate rounds superseded by a later ok:true receipt of the same unit
    "PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.round1_20260810T114605Z.json": SUPERSEDED,
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round3-rerun_20260810T193502Z.json":
        SUPERSEDED,
    "PHASE19_4_READINESS_WINDOW_SELFCHECK_phase-19.4.round3_20260810T193358Z.json": SUPERSEDED,
    "PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-clean-tree_20260811T084527Z.json": SUPERSEDED,
    "PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-round1_20260811T084317Z.json": SUPERSEDED,
    "PHASE19_7_RUNTIME_HONESTY_SELFCHECK_19.7_20260813T225618Z.json": SUPERSEDED,
}


def undeclared_failures(verdicts: dict[str, str],
                        waived: dict[str, tuple[str, str]] | None = None) -> dict[str, str]:
    """The gate decision, extracted so it can be proven directly (M-7): every receipt whose
    verdict is not `ok` and that is not EFFECTIVELY waived. A waiver is effective only while
    its pinned verdict still matches the receipt's actual verdict — a drifted waiver is no
    waiver (the drift is independently re-checked by the waiver-rot test, so this is defense
    in depth, not the only catch). An empty result is the ONLY way the gate is satisfied; an
    undeclared or mis-waived `ok:false` receipt always lands here."""
    table = WAIVED if waived is None else waived
    return {name: v for name, v in verdicts.items()
            if v != OK and not (name in table and table[name][0] == v)}


def waiver_kind_problems(waived: dict[str, tuple[str, str]],
                         kinds: dict[str, str]) -> list[str]:
    """Machine-tag integrity (M-7): every waiver must carry exactly one known kind, the tag
    set must cover the waiver table and nothing else, and the kind must agree with the pinned
    verdict (`no_verdict_schema` iff the receipt carries no `ok` field)."""
    problems = []
    for name in waived:
        if name not in kinds:
            problems.append(f"{name}: waived with no machine kind")
    for name in set(kinds) - set(waived):
        problems.append(f"{name}: machine kind for a receipt that is not waived")
    for name, kind in kinds.items():
        if name not in waived:
            continue
        if kind not in KINDS:
            problems.append(f"{name}: unknown machine kind {kind!r}")
            continue
        expected = waived[name][0]
        if kind == NO_VERDICT_SCHEMA and expected != NO_VERDICT:
            problems.append(f"{name}: kind {kind!r} but pinned verdict {expected!r}")
        if kind != NO_VERDICT_SCHEMA and expected == NO_VERDICT:
            problems.append(f"{name}: kind {kind!r} but the receipt carries no `ok` field")
    return problems


def test_no_unwaived_receipt_reports_a_failure() -> None:
    """W-19. Every receipt reports success, or is waived with its verdict pinned. The decision
    is the extracted `undeclared_failures` — the exact function the negative tests below prove
    fails on an undeclared `ok:false` (M-7)."""
    verdicts = read_receipts(RECEIPTS)
    assert verdicts, f"no receipts found under {RECEIPTS} — the reader is pointed at nothing"
    offenders = undeclared_failures(verdicts)
    assert not offenders, (
        f"{len(offenders)} receipt(s) do not report success and are not waived:\n  "
        + "\n  ".join(f"{n}: {v}" for n, v in sorted(offenders.items())))


def test_every_waiver_still_applies_and_still_describes_the_receipt() -> None:
    """A waiver is a CLAIM about a specific file, re-checked here. Three ways it can rot: the
    receipt disappears, the receipt's verdict changes, or a NEW receipt reuses the name."""
    verdicts = read_receipts(RECEIPTS)
    stale = sorted(name for name in WAIVED if name not in verdicts)
    assert not stale, f"waivers for receipts that no longer exist: {stale}"
    drifted = {name: (expected, verdicts[name])
               for name, (expected, _why) in WAIVED.items()
               if verdicts[name] != expected}
    assert not drifted, (
        "waived receipts whose verdict changed — re-read them before re-waiving:\n  "
        + "\n  ".join(f"{n}: waived as {e!r}, now {a!r}" for n, (e, a) in sorted(drifted.items())))
    unnecessary = sorted(name for name, (expected, _why) in WAIVED.items() if expected == OK)
    assert not unnecessary, f"waivers for receipts that PASS — delete them: {unnecessary}"
    for name, (_expected, why) in WAIVED.items():
        assert why.strip(), f"{name} is waived with no reason"


def test_the_reader_is_not_vacuous(tmp_path: Path) -> None:
    """NEGATIVE. The gate must catch a failing receipt it has never seen — otherwise the green
    above is a statement about the waiver table, not about the receipts."""
    (tmp_path / "PASSES.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "FAILS.json").write_text(json.dumps({"ok": False}), encoding="utf-8")
    (tmp_path / "SILENT.json").write_text(json.dumps({"result": "PARTIAL"}), encoding="utf-8")
    (tmp_path / "BROKEN.json").write_text("{not json", encoding="utf-8")

    verdicts = read_receipts(tmp_path)
    assert verdicts["PASSES.json"] == OK
    assert verdicts["FAILS.json"] == FAILED
    assert verdicts["SILENT.json"] == NO_VERDICT
    assert verdicts["BROKEN.json"].startswith("unreadable")

    offenders = {n: v for n, v in verdicts.items() if v != OK}
    assert set(offenders) == {"FAILS.json", "SILENT.json", "BROKEN.json"}


def test_a_new_receipt_cannot_inherit_a_waiver(tmp_path: Path) -> None:
    """NEGATIVE. The waiver pins the VERDICT, so a file that changes under a waived name is caught
    rather than absorbed — the failure mode that makes most allow-lists worthless."""
    (tmp_path / "WAIVED_NAME.json").write_text(json.dumps({"ok": False}), encoding="utf-8")
    verdicts = read_receipts(tmp_path)
    waived = {"WAIVED_NAME.json": (NO_VERDICT, "waived as a schema-less report")}
    drifted = {n: (e, verdicts[n]) for n, (e, _w) in waived.items() if verdicts[n] != e}
    assert drifted, "a waived name whose verdict changed must not pass unnoticed"


# ---- M-7: the fail-on-undeclared behavior is PROVEN, and waivers are machine-tagged ------------


def test_the_gate_fails_end_to_end_on_an_undeclared_ok_false_receipt(tmp_path: Path) -> None:
    """NEGATIVE, end-to-end (M-7): a fresh `ok:false` receipt with no waiver is flagged by the
    SAME function the real gate runs — the fail-on-undeclared behavior is demonstrated, not
    claimed. Waiving that exact receipt with its pinned verdict clears it; a waiver pinned to
    the WRONG verdict does not."""
    (tmp_path / "CLEAN.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "UNDECLARED_FAIL.json").write_text(json.dumps({"ok": False}), encoding="utf-8")
    verdicts = read_receipts(tmp_path)

    offenders = undeclared_failures(verdicts, waived={})
    assert offenders == {"UNDECLARED_FAIL.json": FAILED}, (
        "an unwaived ok:false receipt must be the gate's offender set")

    offenders = undeclared_failures(
        verdicts, waived={"UNDECLARED_FAIL.json": (FAILED, "demonstration waiver")})
    assert offenders == {}, "a correctly pinned waiver clears the receipt"

    offenders = undeclared_failures(
        verdicts, waived={"UNDECLARED_FAIL.json": (OK, "wrongly pinned waiver")})
    assert offenders == {"UNDECLARED_FAIL.json": FAILED}, (
        "a waiver pinned to the WRONG verdict is no waiver: the receipt still fails the gate")


def test_every_waiver_carries_a_machine_kind() -> None:
    """M-7: the waiver table is fully machine-tagged from the fixed KINDS vocabulary, and every
    tag agrees with the pinned verdict."""
    problems = waiver_kind_problems(WAIVED, WAIVER_KINDS)
    assert not problems, "waiver machine-tag problems:\n  " + "\n  ".join(sorted(problems))


def test_the_deliberate_falsification_receipts_are_machine_tagged() -> None:
    """M-7: the deliberate-falsification class — receipts whose ok:false IS the evidence (a
    caught mutation, a pre-repair baseline, a diagnostic leg) — is identifiable by code."""
    tagged = sorted(n for n, k in WAIVER_KINDS.items() if k == DELIBERATE_FALSIFICATION)
    assert tagged == sorted([
        "PHASE17C_DISARM_FALSIFICATION.json",
        "PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json",
        "PHASE19_4_READINESS_WINDOW_SELFCHECK_ab-pre-repair_20260810T193555Z.json",
        "PHASE19_4_READINESS_WINDOW_SELFCHECK_diag_20260810T193721Z.json",
    ]), f"the deliberate-falsification class changed: {tagged}"
    for name in tagged:
        assert WAIVED[name][0] == FAILED, f"{name}: a falsification record must carry ok:false"


def test_a_waiver_with_an_unknown_or_missing_kind_is_rejected() -> None:
    """NEGATIVE (M-7): a waiver without a machine kind, or with one outside the vocabulary,
    fails the tag integrity check — the class system cannot rot silently."""
    waived = {
        "A.json": (FAILED, "x"),
        "B.json": (NO_VERDICT, "x"),
    }
    problems = waiver_kind_problems(waived, {"A.json": "invented_kind"})
    assert any("B.json" in p and "no machine kind" in p for p in problems)
    assert any("A.json" in p and "unknown machine kind" in p for p in problems)
    problems = waiver_kind_problems(waived, {"A.json": SUPERSEDED, "B.json": SUPERSEDED})
    assert any("B.json" in p and "no `ok` field" in p for p in problems), (
        "a kind that contradicts the pinned verdict must be rejected")
