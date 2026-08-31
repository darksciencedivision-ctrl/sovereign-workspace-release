"""EPC-02 — the conductor can name the panes that are actually up.

Measured against the operator's running system: four Electron processes, a screenful of ConPTY
consoles, and a conductor dispatching to `worker-A` and `worker-B` — two synthetic ids from a
hardcoded tuple. His panes appeared nowhere in the feed.

The cause was not missing infrastructure. `register_pane_session` already registers a governed
pane as a Sovereign node behind three fences; `attest_spawned` already records a live pid as a
separate act; `NodeRegistry` already tracks state and incarnation. Nothing read any of it.

These tests hold the line that matters most about presence: knowing a pane is UP is not knowing
it DID anything. Presence must never become a live-worker claim by implication.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from control_plane.orchestration.pane_presence import (  # noqa: E402
    LIVE_PANE_STATES,
    PanePresence,
    live_pane_ids,
    presence_feed,
    presence_from_records,
)


class Row:
    """A registry row, shaped as NodeRegistry hands one back."""

    def __init__(self, node_id, state="READY", pid=4242, model="llama3.2:3b", incarnation=1):
        self.node_id = node_id
        self.state = state
        self.pid = pid
        self.model = model
        self.incarnation = incarnation


class PresenceReadsTheRegistry(unittest.TestCase):

    def test_it_names_the_panes_that_are_up(self) -> None:
        presence = presence_from_records([Row("pane-1"), Row("pane-2")])
        self.assertEqual([p.node_id for p in presence], ["pane-1", "pane-2"])
        self.assertTrue(all(p.is_live for p in presence))

    def test_a_pane_needs_BOTH_a_live_state_and_a_pid(self) -> None:
        """A live state with no pid has not been attested spawned; a pid with no live state is a
        process the registry no longer vouches for. Either alone is a claim too far."""
        self.assertFalse(PanePresence("a", "m", "READY", None).is_live)
        self.assertFalse(PanePresence("b", "m", "STOPPED", 99).is_live)
        self.assertTrue(PanePresence("c", "m", "READY", 99).is_live)

    def test_SPAWNING_is_not_live(self) -> None:
        """At ticket time the ConPTY has not been spawned - which is why `attest_spawned` is a
        separate act. Offering a conductor a pane that may never come up would be presence
        asserting more than the registry knows."""
        self.assertNotIn("SPAWNING", LIVE_PANE_STATES)
        self.assertFalse(PanePresence("d", "m", "SPAWNING", 1).is_live)

    def test_an_unreadable_row_is_skipped_not_guessed(self) -> None:
        """An invented node id would be worse than a missing one."""
        broken = object()
        presence = presence_from_records([Row("pane-1"), broken, Row("")])
        self.assertEqual([p.node_id for p in presence], ["pane-1"])

    def test_it_survives_a_registry_that_returns_nothing(self) -> None:
        """This runs on the operator's display path; it must not be able to take it down."""
        for empty in ([], None, ()):
            self.assertEqual(presence_from_records(empty), [])

    def test_ordering_is_stable(self) -> None:
        first = presence_from_records([Row("z"), Row("a"), Row("m")])
        second = presence_from_records([Row("m"), Row("z"), Row("a")])
        self.assertEqual([p.node_id for p in first], [p.node_id for p in second])


class PresenceIsNotALiveWorkerClaim(unittest.TestCase):
    """The property this module exists to preserve."""

    def test_a_mock_dispatch_is_reported_as_not_addressing_live_panes(self) -> None:
        """The operator's exact situation: real panes up, dispatch to worker-A/worker-B."""
        feed = presence_feed(presence_from_records([Row("pane-1"), Row("pane-2")]),
                             dispatched_to=["worker-A", "worker-B"])
        self.assertEqual(feed["panes_live"], ["pane-1", "pane-2"])
        self.assertEqual(feed["dispatched_to"], ["worker-A", "worker-B"])
        self.assertFalse(feed["dispatched_to_live_panes"])

    def test_it_says_so_in_words_an_operator_can_read(self) -> None:
        feed = presence_feed([], dispatched_to=["worker-A"])
        self.assertIn("NOT a claim that any pane executed work", feed["note"])
        self.assertIn("U58", feed["note"])

    def test_addressing_real_panes_is_reported_as_such(self) -> None:
        feed = presence_feed(presence_from_records([Row("pane-1")]), dispatched_to=["pane-1"])
        self.assertTrue(feed["dispatched_to_live_panes"])

    def test_an_empty_dispatch_is_not_counted_as_addressing_panes(self) -> None:
        """`all()` over an empty sequence is True. Presence must not read a dispatch that
        happened to nobody as having reached live panes."""
        feed = presence_feed(presence_from_records([Row("pane-1")]), dispatched_to=[])
        self.assertFalse(feed["dispatched_to_live_panes"])

    def test_a_dead_pane_is_not_a_valid_target(self) -> None:
        feed = presence_feed(presence_from_records([Row("pane-1", state="STOPPED")]),
                             dispatched_to=["pane-1"])
        self.assertEqual(feed["panes_live"], [])
        self.assertFalse(feed["dispatched_to_live_panes"])

    def test_the_feed_carries_no_leg_field_at_all(self) -> None:
        """A leg is derived from evidence by the packet builder. Presence must not offer a
        field that could be mistaken for one."""
        feed = presence_feed(presence_from_records([Row("pane-1")]), dispatched_to=["pane-1"])
        for forbidden in ("legs", "worker_legs", "live", "accepted", "candidate"):
            self.assertNotIn(forbidden, feed)


class LivePaneIds(unittest.TestCase):

    def test_it_returns_only_live_panes(self) -> None:
        presence = presence_from_records([
            Row("up-1"), Row("down", state="STOPPED"), Row("up-2"), Row("pending", pid=None)])
        self.assertEqual(live_pane_ids(presence), ("up-1", "up-2"))


if __name__ == "__main__":
    unittest.main()
