"""Every committed receipt is READ (punch list 2.1, W-19).

The audit found 86 receipts under `docs/evidence/receipts/` of which 15 report
`ok: false` and 3 carry no `ok` field at all — and nothing in any suite ever
opened one. A receipt that nobody reads is a file, not evidence.

WHAT THIS GATE IS. It fails on any receipt that does not report success, unless
that receipt is in the waiver table below. The waiver is not a mute button: each
entry PINS the verdict the receipt actually carries, so a waived receipt that
changes still fails, a waiver for a receipt that no longer exists still fails,
and a NEW receipt cannot inherit a waiver by reusing a name.

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


def test_no_unwaived_receipt_reports_a_failure() -> None:
    """W-19. Every receipt reports success, or is waived with its verdict pinned."""
    verdicts = read_receipts(RECEIPTS)
    assert verdicts, f"no receipts found under {RECEIPTS} — the reader is pointed at nothing"
    offenders = {name: v for name, v in verdicts.items()
                 if v != OK and name not in WAIVED}
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
