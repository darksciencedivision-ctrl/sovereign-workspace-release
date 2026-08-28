"""Host enumeration → picker contract (Phase 16B `.host-picker`).

`tools/live/enumerate_pane_picker.build_host_picker` is the ONE place the live host is
enumerated into the per-pane picker option set the shell renders (over `--emit-picker`). The
picker CONTENT is host-dependent (real `ollama list`, real `LiveAuthorization`), so these tests
assert the CONTRACT the shell depends on — shape, required per-option fields, internally
consistent counts, and that nothing is fabricated — rather than exact model names. The pure
option logic (greyed-with-reason, residency, no fabrication) is covered by test_pane_picker.py;
this proves the host builder emits that logic's output in the stable shape.
"""
from __future__ import annotations

import json
import sys

from tools.live import enumerate_pane_picker as epp

_REQUIRED_OPTION_KEYS = {
    "provider", "adapter", "locality", "label", "model_slug", "verified", "is_fallback",
    "roles", "residency", "available", "unavailable_reason", "note",
}


def _assert_wellformed_picker(picker: dict) -> None:
    assert set(picker.keys()) >= {"providers", "options", "authorization", "counts"}
    # every option carries the full contract — no partial/fabricated option reaches the shell
    for opt in picker["options"]:
        assert _REQUIRED_OPTION_KEYS <= set(opt.keys()), f"option missing keys: {opt}"
        assert isinstance(opt["roles"], list) and opt["roles"], "every option offers >=1 role"
        # fail-closed honesty: a greyed option MUST carry a specific reason, never a blank grey
        if opt["available"] is False:
            assert opt["unavailable_reason"], f"greyed option without a reason: {opt}"
        else:
            assert opt["unavailable_reason"] is None
    # the flat list is exactly the union of the grouped lists (the UI can render either)
    grouped = [o for g in picker["providers"] for o in g["options"]]
    assert grouped == picker["options"]
    # counts are internally consistent — the shell trusts them for the badge/summary
    c = picker["counts"]
    assert c["total"] == len(picker["options"])
    assert c["available"] == sum(1 for o in picker["options"] if o["available"])
    assert c["total"] == c["frontier"] + c["local"]


def test_build_host_picker_returns_wellformed_contract() -> None:
    picker, meta = epp.build_host_picker(op12_probes=epp.no_op12_probes())
    _assert_wellformed_picker(picker)
    # meta provenance the operator report prints is present and honest
    assert set(meta.keys()) >= {
        "authorization", "claude_probe", "codex_probe", "ollama_enumerated", "residency_provenance",
    }
    assert isinstance(meta["ollama_enumerated"], list)
    # the picker's authorization block mirrors the live gate (never fabricated as authorized)
    assert picker["authorization"] == meta["authorization"]


def test_local_options_mirror_the_live_ollama_enumeration_exactly() -> None:
    # No fabrication and no omission: the local option labels are exactly the de-duplicated set of
    # what `ollama list` returned (the picker sorts + de-dupes; it never invents a model, and the
    # operator's Kimi/Qwen availability is decided PURELY by what the host really offers — OP-10).
    picker, meta = epp.build_host_picker(op12_probes=epp.no_op12_probes())
    local_labels = {o["label"] for o in picker["options"] if o["provider"] == "ollama_local"}
    enumerated = {m for m in meta["ollama_enumerated"] if isinstance(m, str) and m.strip()}
    assert local_labels == enumerated
    # every local option is credential-free and carries a residency state string (invariant 22)
    for o in picker["options"]:
        if o["provider"] == "ollama_local":
            assert o["available"] is True and o["subscription_backed"] is False
            assert isinstance(o["residency"], str) and o["residency"]


def test_emit_picker_prints_only_the_picker_json(capsys) -> None:
    rc = epp.main(op12_probes=epp.no_op12_probes(), argv=["--emit-picker"])
    assert rc == 0
    out = capsys.readouterr().out
    picker = json.loads(out)  # the WHOLE stdout is exactly one picker dict (stable shell contract)
    _assert_wellformed_picker(picker)


def test_full_report_mode_wraps_the_picker_with_provenance(capsys) -> None:
    rc = epp.main(op12_probes=epp.no_op12_probes(), argv=[])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert "picker" in report and "phase" in report and "residency_provenance" in report
    _assert_wellformed_picker(report["picker"])
