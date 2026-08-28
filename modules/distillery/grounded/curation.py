from __future__ import annotations

from distillery.common import ContractError
from source_admission import assert_admitted


def select_trainable_turns(trace: dict) -> list[dict]:
    return [turn for turn in trace.get("turns", []) if not turn.get("superseded") and turn.get("tool_status") != "failed"]


def mine_ch1(trace: dict, *, internal_use_authorized: bool = False) -> dict:
    assert_admitted(trace.get("source_admission_class", "UNKNOWN"), internal_use_authorized=internal_use_authorized)
    if trace.get("outcome") not in {"success", "implicit_success"}:
        raise ContractError("only successful or implicit-positive sessions enter CH1")
    selected = select_trainable_turns(trace)
    if not selected:
        raise ContractError("trace has no trainable turns after masking")
    return {"source_trace_id": trace["trace_id"], "channel": "CH1", "turns": selected, "recovery_arc_preserved": any(turn.get("recovery") for turn in selected)}


def screen_volatile_facts(sample: dict) -> dict:
    screened = dict(sample)
    volatile = bool(sample.get("frequently_changing_fact"))
    screened["prefer_lookup"] = volatile
    screened["training_weight"] = 0.0 if volatile and sample.get("channel") == "CH-M" else 1.0
    return screened
