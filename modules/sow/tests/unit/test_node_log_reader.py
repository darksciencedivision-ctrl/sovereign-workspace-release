"""EPC-03 L3-5 — read the node log without becoming its second opener.

`AppendOnlyEventLog.__init__` opens the file in APPEND mode and caches `prev_hash`. Its own
caller records what two openers cost: *"two PROCESSES appending would write duplicate `seq`
values and break the chain permanently… that would wedge the whole governed-probe path with no
repair an append-only log permits."*

So presence reads the JSONL directly. These tests hold the two properties that matter: it never
opens for append, and it folds a HISTORY into a current state rather than reporting the first
row it finds.
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
    read_node_rows,
)


def row(node_key: str, *, seq: int = 1, state: str = "SPAWNING", pid=None,
        model: str = "llama3.2:3b", locality: str = "local",
        node_class: str = "worker_reasoning") -> dict:
    return {
        "seq": seq, "incarnation": 1, "kind": "register",
        "data": {
            "node_key": node_key, "pid": pid, "node_class": node_class,
            "node_record": {"state": state, "model_ref": model, "adapter": "ollama_local",
                            "locality": locality, "class": node_class},
        },
    }


def write(rows) -> Path:
    path = Path(tempfile.mkdtemp(prefix="sov-logread-")) / "node_events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


class ItReadsWithoutOpeningForAppend(unittest.TestCase):

    def test_it_never_constructs_an_AppendOnlyEventLog(self) -> None:
        """The property, asserted against the source. A reader that constructed one would be
        the second opener that breaks the hash chain permanently."""
        from control_plane.orchestration import node_log_reader
        source = Path(node_log_reader.__file__).read_text(encoding="utf-8")
        # The class name appears in the docstring explaining WHY it is not used; it must never
        # appear as a call.
        self.assertNotIn("AppendOnlyEventLog(", source)

    def test_a_missing_log_yields_no_panes_rather_than_raising(self) -> None:
        """This feeds the operator's conductor surface. A missing file is the normal state
        before the first pane is ever registered."""
        self.assertEqual(pane_records("/no/such/path/node_events.jsonl"), [])

    def test_a_malformed_line_is_skipped_not_fatal(self) -> None:
        path = write([row("pane-1")])
        path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
        self.assertEqual(len(read_node_rows(path)), 1)


class ItFoldsAHistoryIntoTheCurrentState(unittest.TestCase):

    def test_the_newest_row_wins(self) -> None:
        """A pane is registered SPAWNING and later attested READY. Both rows are permanent;
        only the last is true now. Reading the first is how a pane stays SPAWNING forever in a
        surface that claims to show what is up."""
        path = write([row("pane-1", seq=1, state="SPAWNING"),
                      row("pane-1", seq=2, state="READY", pid=4242)])
        folded = pane_records(path)
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0]["state"], "READY")
        self.assertEqual(folded[0]["pid"], 4242)

    def test_an_attested_pid_survives_a_later_row_that_omits_it(self) -> None:
        """A pid, once attested, is a fact about the process. A later bookkeeping row that
        carries no pid field must not un-attest it."""
        path = write([row("pane-1", seq=1, state="SPAWNING"),
                      row("pane-1", seq=2, state="READY", pid=99),
                      row("pane-1", seq=3, state="READY", pid=None)])
        self.assertEqual(pane_records(path)[0]["pid"], 99)

    def test_a_closed_pane_is_not_reported_as_present(self) -> None:
        """A node that reached a terminal state is not addressable, whatever pid the log
        remembers for it."""
        path = write([row("pane-1", seq=1, state="READY", pid=99),
                      row("pane-1", seq=2, state="CLOSED", pid=99)])
        self.assertEqual(pane_records(path), [])

    def test_several_panes_are_each_folded_separately(self) -> None:
        path = write([row("pane-1", seq=1, state="READY", pid=1),
                      row("pane-2", seq=2, state="SPAWNING"),
                      row("pane-3", seq=3, state="READY", pid=3)])
        folded = {r["node_id"]: r for r in pane_records(path)}
        self.assertEqual(set(folded), {"pane-1", "pane-2", "pane-3"})
        self.assertEqual(folded["pane-2"]["pid"], None)

    def test_it_carries_what_presence_needs_to_name_a_pane(self) -> None:
        path = write([row("pane-1", seq=1, state="READY", pid=7, model="granite4.2:3b")])
        record = pane_records(path)[0]
        self.assertEqual(record["model"], "granite4.2:3b")
        self.assertEqual(record["locality"], "local")
        self.assertEqual(record["node_class"], "worker_reasoning")

    def test_a_row_with_no_node_key_is_skipped(self) -> None:
        """An invented id would be worse than a missing one."""
        self.assertEqual(latest_pane_state([{"data": {"pid": 1}}, row("pane-1")]).__len__(), 1)


if __name__ == "__main__":
    unittest.main()
