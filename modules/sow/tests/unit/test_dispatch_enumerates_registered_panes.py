"""EPC-03 L3-5 — the conductor dispatches to the panes that exist, not to two invented ids.

Measured before the change, on the operator's running system: four Electron processes, a
screenful of ConPTY consoles, and a dispatch feed that read

    "assignments": [{"node": "worker-A", ...}, {"node": "worker-B", ...}],
    "pane_presence": {"panes_present": [], "panes_live": [], ...}

`pane_presence` was built in EPC-02 and could fold a registry perfectly well. It was never
handed one: every caller left `pane_records` at its `()` default. The conductor was not blind
because presence was missing; it was blind because nothing looked.

Two things this must NOT become, both named in the operator's own instructions:

  * `DEFAULT_WORKER_IDS` is untouched - *"Do not 'fix' DEFAULT_WORKER_IDS to make the banner
    say workers exist."* It remains the fallback for a host with no registered pane. What
    changed is that the dispatch stops REACHING for it when a real pane can be named.
  * Addressing a live pane is not executing on one. The legs stay `mock` and U58 stays owed
    until a pane publishes a CANDIDATE through the evidence path.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from control_plane.orchestration import conductor_dispatch as cd  # noqa: E402

CONDUCTOR_DIR = MODULE_ROOT / "conductor"


class Rec:
    def __init__(self, node_id, state="READY", pid=1234, model="llama3.2:3b"):
        self.node_id, self.state, self.pid, self.model = node_id, state, pid, model


class TheResolverPrefersRealPanes(unittest.TestCase):

    def test_with_no_registered_pane_the_dispatch_is_exactly_what_it_was(self) -> None:
        """The fallback the operator asked to be left alone."""
        self.assertEqual(cd.resolve_worker_ids((), None), cd.DEFAULT_WORKER_IDS)

    def test_live_panes_are_addressed_instead_of_the_synthetic_ids(self) -> None:
        """The defect in one assertion. If this returns `worker-A`/`worker-B` on a host with two
        live panes, the conductor is still guessing."""
        resolved = cd.resolve_worker_ids([Rec("pane-1"), Rec("pane-2")], None)
        self.assertEqual(resolved, ("pane-1", "pane-2"))
        self.assertNotIn("worker-A", resolved)

    def test_a_pinned_list_always_wins(self) -> None:
        """Tests and the emitter pin their ids. Quietly retargeting a caller's explicit request
        would be a worse failure than the stale default this replaces."""
        self.assertEqual(cd.resolve_worker_ids([Rec("pane-1")], ["w-1", "w-2"]), ("w-1", "w-2"))

    def test_a_SPAWNING_pane_is_not_addressed(self) -> None:
        """D-5. A ticket exists; the ConPTY may never come up. `attest_spawned` is a separate act
        with a live pid behind it, and dispatching to an unattested pane would be presence
        asserting more than the registry knows."""
        self.assertEqual(cd.resolve_worker_ids([Rec("pane-1", state="SPAWNING", pid=None)], None),
                         cd.DEFAULT_WORKER_IDS)

    def test_a_live_state_with_no_pid_is_not_addressed(self) -> None:
        self.assertEqual(cd.resolve_worker_ids([Rec("pane-1", pid=None)], None),
                         cd.DEFAULT_WORKER_IDS)


class TheRegistryIsReadAtTheBoundaryNotInTheFold(unittest.TestCase):
    """`fold_dispatch_feed` documents itself as PURE so the fold is unit-testable without a host.
    A registry read inside it would make every fold test depend on the operator's live store."""

    def test_the_fold_reads_no_log_of_its_own(self) -> None:
        import inspect
        source = inspect.getsource(cd.fold_dispatch_feed)
        self.assertNotIn("registered_pane_records", source)

    def test_the_fold_reports_only_the_records_it_was_given(self) -> None:
        trace = {"objective": "o", "assignments": [], "plan_gate": {"verdict": "PASS"}}
        self.assertEqual(cd.fold_dispatch_feed(trace)["pane_presence"]["panes_present"], [])
        given = cd.fold_dispatch_feed(trace, [Rec("pane-1")])["pane_presence"]
        self.assertEqual(given["panes_live"], ["pane-1"])


class TheRegistryReadIsSafeOnEveryHost(unittest.TestCase):

    def test_it_honours_the_redirect_so_a_check_never_reads_the_operators_store(self) -> None:
        import os
        import tempfile
        log = Path(tempfile.mkdtemp(prefix="sov-l35-")) / "node_events.jsonl"
        log.write_text(json.dumps({
            "seq": 1, "incarnation": 1,
            "data": {"node_key": "pane-x", "pid": 77,
                     "node_record": {"state": "READY", "model_ref": "qwen2.5:3b-instruct",
                                     "class": "worker_reasoning", "locality": "local"}}}) + "\n",
            encoding="utf-8")
        previous = os.environ.get("SOW_NODE_EVENT_LOG")
        os.environ["SOW_NODE_EVENT_LOG"] = str(log)
        try:
            records = cd.registered_pane_records()
        finally:
            if previous is None:
                os.environ.pop("SOW_NODE_EVENT_LOG", None)
            else:
                os.environ["SOW_NODE_EVENT_LOG"] = previous
        self.assertEqual([r.node_id for r in records], ["pane-x"])
        self.assertEqual(cd.resolve_worker_ids(records, None), ("pane-x",))

    def test_a_broken_registry_costs_the_presence_line_not_the_dispatch(self) -> None:
        """This runs on the operator's display path. A registry fault must degrade, not raise."""
        self.assertEqual(cd.registered_pane_records("/no/such/dir/node_events.jsonl"), [])


class ADispatchToRealPanesIsStillMockFirst(unittest.TestCase):
    """The honesty line. `dispatched_to_live_panes` says the conductor addressed panes that are
    up. It never says a pane ran anything - that remains `worker_handles` plus the evidence
    derivation, and neither is touched here."""

    def test_the_end_to_end_feed_names_the_registered_pane_and_still_owes_U58(self) -> None:
        import os
        import tempfile
        store = Path(tempfile.mkdtemp(prefix="sov-l35-run-"))
        log = store / "nodes" / "node_events.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(json.dumps({
            "seq": i, "incarnation": 1,
            "data": {"node_key": f"pane-{i}", "pid": 900 + i,
                     "node_record": {"state": "READY", "model_ref": "llama3.2:3b",
                                     "class": "worker_reasoning", "locality": "local"}}})
            for i in (1, 2)) + "\n", encoding="utf-8")

        previous = os.environ.get("SOW_NODE_EVENT_LOG")
        os.environ["SOW_NODE_EVENT_LOG"] = str(log)
        try:
            feed = cd.run_governed_dispatch(conductor_dir=CONDUCTOR_DIR,
                                            store_root=store / "run")
        finally:
            if previous is None:
                os.environ.pop("SOW_NODE_EVENT_LOG", None)
            else:
                os.environ["SOW_NODE_EVENT_LOG"] = previous

        addressed = {a["node"] for a in feed["assignments"]}
        self.assertTrue(addressed, "nothing was dispatched")
        self.assertTrue(addressed <= {"pane-1", "pane-2"},
                        f"the dispatch still addressed synthetic ids: {sorted(addressed)}")
        presence = feed["pane_presence"]
        self.assertEqual(presence["panes_live"], ["pane-1", "pane-2"])
        self.assertTrue(presence["dispatched_to_live_panes"])

        # ...and none of that is an execution claim.
        self.assertEqual(feed["legs"], {"conductor": "mock", "workers": "mock"})
        self.assertTrue(feed["live_workers_owed"]["owed"])
        self.assertEqual(feed["live_workers_owed"]["issue"], "U58")
        self.assertIn("NOT a claim that any pane executed work", presence["note"])

    def test_the_presence_line_and_the_addressed_ids_come_from_ONE_read(self) -> None:
        """Two reads could disagree - a feed that dispatched to a pane it does not list as
        present would be exactly the incoherence this layer exists to remove."""
        import inspect
        source = inspect.getsource(cd.run_governed_dispatch)
        self.assertEqual(source.count("registered_pane_records()"), 1)
        self.assertIn("fold_dispatch_feed(trace, panes)", source)


if __name__ == "__main__":
    unittest.main()
