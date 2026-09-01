"""The node log as the product ACTUALLY writes it — not as the first test author imagined it.

WHY THIS FILE EXISTS. `test_node_log_reader.py` has nine tests and all nine passed while the
reader was wrong, because every fixture in it was invented. It keyed rows on `data.node_key` and
gave each row a `node_record.state`. Measured against the operator's real store on 2026-09-01,
the log contains neither of those things on the rows that matter:

    kinds: spawn 34, transition 36, exit 32          (no `register` kind at all)

    spawn       node_id="worker-pane-2"  data={adapter, pid, session_id,
                                               node_record{node_id:<uuid>, state:"SPAWNING", ...}}
    transition  node_id="worker-pane-2"  data={frm:"SPAWNING", to:"READY", reason:"..."}
    exit        node_id="worker-pane-2"  data={exit_code, expected}

`data.node_key` is absent everywhere. The only field common to all three kinds is the row's
TOP-LEVEL `node_id`, and the current state lives in `data.to` on a transition, nowhere else.

The reader preferred `node_record.node_id` — a per-INCARNATION uuid present only on spawn rows.
On the operator's own log that produced 36 phantom nodes, every one stuck at SPAWNING with
pid None, when the truth was two panes, both READY, both with live pids. The surface built to stop
the conductor guessing would have guessed differently.

A fabricated fixture cannot catch that. These tests are built from the real shape.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from control_plane.orchestration.node_log_reader import (  # noqa: E402
    latest_pane_state,
    pane_records,
    pane_records_as_objects,
)
from control_plane.orchestration.pane_presence import (  # noqa: E402
    live_pane_ids,
    presence_from_records,
)

UUID_A = "3ac93c1f-36af-526c-95a5-54f352c4b6a8"
UUID_B = "211af116-194f-5165-9f85-ea5d3de5f9a9"


def spawn(node_id: str, *, seq: int, record_uuid: str, model: str, state: str = "SPAWNING") -> dict:
    """A spawn row exactly as the supervisor writes it: identity on the ROW, a per-incarnation
    uuid inside the record, and no `data.node_key` anywhere."""
    return {
        "seq": seq, "kind": "spawn", "node_id": node_id, "incarnation": 1,
        "data": {
            "adapter": "ollama_local", "adapter_schema_version": "node@1.1",
            "lease_id": "", "node_class": "worker_reasoning", "pid": None,
            "session_id": f"{node_id}#5150.1", "subscription_ref": None,
            "node_record": {"node_id": record_uuid, "adapter": "ollama_local",
                            "locality": "local", "model_ref": model, "state": state,
                            "class": "worker_reasoning"},
        },
    }


def transition(node_id: str, *, seq: int, frm: str, to: str, reason: str) -> dict:
    return {"seq": seq, "kind": "transition", "node_id": node_id, "incarnation": 1,
            "data": {"frm": frm, "to": to, "reason": reason}}


def attest(node_id: str, *, seq: int, pid: int) -> dict:
    """The shell observing the ConPTY. Carries the pid and nothing else identifying."""
    return {"seq": seq, "kind": "transition", "node_id": node_id, "incarnation": 1,
            "data": {"frm": "SPAWNING", "to": "READY", "pid": pid,
                     "reason": "supervised ConPTY spawn observed by the shell"}}


def exited(node_id: str, *, seq: int, expected: bool = False) -> dict:
    return {"seq": seq, "kind": "exit", "node_id": node_id, "incarnation": 1,
            "data": {"exit_code": None, "expected": expected}}


class TheRowsJoinOnTheStableIdentity(unittest.TestCase):

    def test_a_spawn_and_its_transitions_are_ONE_node(self) -> None:
        """The defect in one assertion. Keyed on the record uuid these are two nodes: a phantom
        stuck at SPAWNING, and a second carrying the state. Keyed on the row, they are one pane."""
        folded = latest_pane_state([
            spawn("worker-pane-2", seq=1, record_uuid=UUID_A, model="granite4.2:3b"),
            attest("worker-pane-2", seq=2, pid=36592),
            transition("worker-pane-2", seq=3, frm="SPAWNING", to="READY",
                       reason="supervised ConPTY spawn observed by the shell"),
        ])
        self.assertEqual(len(folded), 1, f"expected one pane, got {[r['node_id'] for r in folded]}")
        self.assertEqual(folded[0]["node_id"], "worker-pane-2")
        self.assertEqual(folded[0]["state"], "READY")
        self.assertEqual(folded[0]["pid"], 36592)
        self.assertEqual(folded[0]["model"], "granite4.2:3b")

    def test_the_record_uuid_never_becomes_a_node_of_its_own(self) -> None:
        """A per-incarnation uuid is not a pane. Two spawns of the SAME pane must stay one pane."""
        folded = latest_pane_state([
            spawn("worker-pane-2", seq=1, record_uuid=UUID_A, model="qwen3:8b"),
            spawn("worker-pane-2", seq=2, record_uuid=UUID_B, model="qwen3:8b"),
            attest("worker-pane-2", seq=3, pid=4242),
        ])
        self.assertEqual([r["node_id"] for r in folded], ["worker-pane-2"])
        self.assertNotIn(UUID_A, [r["node_id"] for r in folded])

    def test_the_state_comes_from_the_transition_not_the_spawn_record(self) -> None:
        """`data.to` is the only place the new state appears. A fold reading `node_record.state`
        sees the spawn-time value for ever — which is why 36 panes read SPAWNING."""
        folded = latest_pane_state([
            spawn("worker-pane-9", seq=1, record_uuid=UUID_A, model="llama3.2:3b"),
            transition("worker-pane-9", seq=2, frm="SPAWNING", to="READY", reason="up"),
        ])
        self.assertEqual(folded[0]["state"], "READY")

    def test_a_terminated_pane_is_not_present(self) -> None:
        """30 of the operator's transitions read `SPAWNING -> TERMINATED, unexpected exit`. Those
        are history, not panes a conductor may address."""
        folded = latest_pane_state([
            spawn("worker-pane-4", seq=1, record_uuid=UUID_A, model="qwen3:8b"),
            transition("worker-pane-4", seq=2, frm="SPAWNING", to="TERMINATED",
                       reason="unexpected exit code=None"),
            exited("worker-pane-4", seq=3),
        ])
        self.assertEqual(folded, [])

    def test_a_pane_that_died_and_respawned_reads_from_its_LAST_state(self) -> None:
        folded = latest_pane_state([
            spawn("worker-pane-5", seq=1, record_uuid=UUID_A, model="qwen3:8b"),
            transition("worker-pane-5", seq=2, frm="SPAWNING", to="TERMINATED", reason="died"),
            spawn("worker-pane-5", seq=3, record_uuid=UUID_B, model="qwen3:8b"),
            attest("worker-pane-5", seq=4, pid=777),
        ])
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0]["state"], "READY")
        self.assertEqual(folded[0]["pid"], 777)


class PresenceNamesTheRealPanes(unittest.TestCase):
    """End to end on the real shape: what the operator's DISPATCH line would say."""

    def _log(self) -> Path:
        rows = [
            spawn("worker-pane-2", seq=1, record_uuid=UUID_A, model="granite4.2:3b"),
            attest("worker-pane-2", seq=2, pid=36592),
            spawn("worker-pane-3", seq=3, record_uuid=UUID_B, model="qwen2.5-coder:3b-instruct"),
            attest("worker-pane-3", seq=4, pid=5240),
            spawn("worker-pane-4", seq=5, record_uuid=UUID_A, model="qwen3:8b"),
            transition("worker-pane-4", seq=6, frm="SPAWNING", to="TERMINATED",
                       reason="unexpected exit code=None"),
        ]
        path = Path(tempfile.mkdtemp(prefix="sov-real-")) / "node_events.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_two_live_panes_and_the_dead_one_is_not_counted(self) -> None:
        presence = presence_from_records(pane_records_as_objects(self._log()))
        self.assertEqual(live_pane_ids(presence), ("worker-pane-2", "worker-pane-3"))

    def test_each_live_pane_carries_its_model_and_pid(self) -> None:
        rows = {r["node_id"]: r for r in pane_records(self._log())}
        self.assertEqual(rows["worker-pane-2"]["model"], "granite4.2:3b")
        self.assertEqual(rows["worker-pane-3"]["pid"], 5240)
        self.assertEqual(rows["worker-pane-2"]["locality"], "local")


if __name__ == "__main__":
    unittest.main()
