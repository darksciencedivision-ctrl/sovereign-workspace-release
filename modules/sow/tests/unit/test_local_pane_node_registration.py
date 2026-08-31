"""EPC-02 U313(A) — a local pane is a Sovereign node, named by its residency reservation.

U313: *"Invariant 2 says every terminal is a Sovereign node"* — and then only two frontier
providers were ever wired. Measured on the operator's host: 154 node events, `grok_build` 22,
`google_antigravity` 20, `openai_codex_cli` 0, `claude_code` 0, local 0. A local pane held a
terminal and wrote no record, the node registry stayed empty, and a conductor asking who was up
got nothing — so it dispatched to `worker-A` and `worker-B` while the operator's real panes sat
there unmentioned.

THE FENCE IS NOT WEAKENED TO LET LOCAL PANES IN. Fence 2 asks every pane the same question —
name the counted resource you were admitted under — and takes the honest answer for the pane's
kind. A frontier pane names the subscription its terminal was counted against. A local pane has
no subscription to name (`ollama_session`: *"a local model involves NO subscription and NO
credential... the governance that applies is VRAM residency (invariant 22)"*), so it names the
ResidencyPlanner decision that admitted it.

A synthetic lease was considered and REJECTED. It would have satisfied the existing fence while
putting a lease id onto a terminal nobody counted — the precise claim that fence exists to make
unrepresentable. These tests exist mostly to prove that door stayed shut.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER  # noqa: E402
from node_runtime.supervisor.provider_node_registration import (  # noqa: E402
    GATE_UNRESERVED_RESIDENCY,
    OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS,
    REGISTRABLE_PROVIDERS,
    RESIDENCY_GOVERNED_ADAPTERS,
    ProviderNodeRegistrationRefused,
    _require_residency,
)

RESERVED = {"scheduled": True, "model": "llama3.2:3b", "status": "RESIDENT"}


class TheLocalAdapterIsRegistrable(unittest.TestCase):

    def test_ollama_can_now_write_a_node_record(self) -> None:
        """The one-line fact underneath the whole conductor-cannot-see-workers chain."""
        self.assertIn(OLLAMA_LOCAL_ADAPTER, REGISTRABLE_PROVIDERS)

    def test_the_frontier_providers_are_untouched(self) -> None:
        """Additive. A change that quietly dropped a provider would be worse than the gap."""
        self.assertIn("grok_build", REGISTRABLE_PROVIDERS)
        self.assertIn("google_antigravity", REGISTRABLE_PROVIDERS)

    def test_only_the_local_adapter_is_residency_governed(self) -> None:
        """A frontier pane must never be admitted on a residency reservation - it spends money,
        and VRAM is not the resource that governs that."""
        self.assertEqual(RESIDENCY_GOVERNED_ADAPTERS, frozenset({OLLAMA_LOCAL_ADAPTER}))

    def test_local_descriptors_do_not_demand_tool_use(self) -> None:
        """Most models at or under 4B on this host report `completion` only. A descriptor
        demanding tools would silently exclude the very panes this wiring exists to register."""
        for descriptor in OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS:
            self.assertNotEqual(descriptor["requirements"].get("tool_use"), True)
            # node@1.1 enumerates ["any", "local_only", "frontier_ok"]; the schema is the
            # authority on its own vocabulary and refused a descriptor saying "local".
            self.assertEqual(descriptor["requirements"].get("locality"), "local_only")


class ARecordCannotBeForgedWithoutAReservation(unittest.TestCase):
    """The operator's explicit requirement, and the point of the whole design."""

    def test_no_reservation_is_refused(self) -> None:
        with self.assertRaises(ProviderNodeRegistrationRefused) as caught:
            _require_residency(None, session_id="s1", model="llama3.2:3b")
        self.assertEqual(caught.exception.gate, GATE_UNRESERVED_RESIDENCY)

    def test_an_UNSCHEDULED_reservation_is_refused(self) -> None:
        """The planner queued it rather than admitting it. A queued pane is not a resident one."""
        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency({"scheduled": False, "model": "llama3.2:3b"},
                               session_id="s1", model="llama3.2:3b")

    def test_an_EMPTY_reservation_is_refused(self) -> None:
        """`{}` must not read as a reservation. A falsey-but-present object is the shape a
        forge takes when someone passes whatever they have to hand."""
        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency({}, session_id="s1", model="llama3.2:3b")

    def test_a_reservation_for_ANOTHER_model_is_refused(self) -> None:
        """The subtlest forge: a real, scheduled reservation that admitted a different model.
        A record must name the reservation that admitted THIS pane."""
        with self.assertRaises(ProviderNodeRegistrationRefused) as caught:
            _require_residency({"scheduled": True, "model": "qwen3:8b"},
                               session_id="s1", model="llama3.2:3b")
        self.assertIn("qwen3:8b", str(caught.exception))
        self.assertIn("llama3.2:3b", str(caught.exception))

    def test_a_truthy_non_boolean_scheduled_is_refused(self) -> None:
        """`scheduled` must be True, not merely truthy. "yes" and 1 are the shapes a JSON
        round-trip or a hand-written fixture produces, and neither is the planner's answer."""
        for sneaky in ("yes", 1, "True", [1]):
            with self.assertRaises(ProviderNodeRegistrationRefused):
                _require_residency({"scheduled": sneaky, "model": "llama3.2:3b"},
                                   session_id="s1", model="llama3.2:3b")

    def test_a_genuine_reservation_is_accepted_and_names_what_governs_it(self) -> None:
        record = _require_residency(RESERVED, session_id="s1", model="llama3.2:3b")
        self.assertEqual(record["governed_by"], "vram_residency")
        self.assertEqual(record["model"], "llama3.2:3b")
        self.assertEqual(record["status"], "RESIDENT")

    def test_the_record_never_claims_a_subscription(self) -> None:
        """The whole reason a synthetic lease was rejected. A local record must not carry a
        field that could later be read as a counted terminal."""
        record = _require_residency(RESERVED, session_id="s1", model="llama3.2:3b")
        for forbidden in ("lease_id", "subscription", "subscription_governed", "terminal"):
            self.assertNotIn(forbidden, record)

    def test_a_ResidencyDecision_object_is_accepted_as_well_as_a_mapping(self) -> None:
        """The planner returns a dataclass; a caller may pass it straight through rather than
        converting, and a converted dict must not be the only accepted shape."""
        from scheduler.residency_planner.residency_planner import ResidencyDecision
        decision = ResidencyDecision(model="llama3.2:3b", scheduled=True, status="RESIDENT")
        self.assertEqual(
            _require_residency(decision, session_id="s1", model="llama3.2:3b")["model"],
            "llama3.2:3b")

    def test_a_REFUSED_planner_decision_is_refused_here_too(self) -> None:
        from scheduler.residency_planner.residency_planner import ResidencyDecision
        queued = ResidencyDecision(model="llama3.2:3b", scheduled=False, status="QUEUED")
        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency(queued, session_id="s1", model="llama3.2:3b")


class TheLocalRecordSaysWhatItIs(unittest.TestCase):
    """The record is written to an APPEND-ONLY log that can never be corrected, so a wrong
    field is permanent. These fail if the record misdescribes a local pane.

    One correction recorded here rather than quietly fixed: I reported `node_class` as null
    from a demonstration. It never was — the record field is `class`, and my demo read
    `node_class`. `provider_facts` returned `worker_reasoning` correctly all along. What the
    demo DID surface is the defect below, which is real.
    """

    def _record(self, locality: str) -> dict:
        from node_runtime.supervisor.provider_node_registration import build_pane_node_record

        class Chrome:
            node_id = "pane-local-1"
            adapter = OLLAMA_LOCAL_ADAPTER
            model_slug = "llama3.2:3b"
            subscription = None

        Chrome.locality = locality

        class Session:
            chrome = Chrome()
            launch = {"cwd": str(MODULE_ROOT)}
            permission_profile_id = "worker-default"
            provider = OLLAMA_LOCAL_ADAPTER

        return build_pane_node_record(Session(), session_id="s-1", incarnation=1)

    def test_class_is_never_null_for_a_local_pane(self) -> None:
        """The operator's stop condition, asserted on the field the record actually uses."""
        record = self._record("local")
        self.assertIsNotNone(record.get("class"))
        self.assertEqual(record["class"], "worker_reasoning")

    def test_class_is_one_the_schema_admits(self) -> None:
        self.assertIn(self._record("local")["class"],
                      {"conductor", "worker_reasoning", "worker_coding_specialist",
                       "voice_input_service"})

    def test_a_local_pane_is_NOT_recorded_as_frontier(self) -> None:
        """The real defect the demonstration surfaced. `locality` was the literal "frontier" -
        true while only grok and antigravity could register, and a lie the moment a local pane
        could. On an append-only log that is permanent."""
        self.assertEqual(self._record("local")["locality"], "local")

    def test_a_frontier_pane_is_still_recorded_as_frontier(self) -> None:
        """Additive: the change must not have inverted the existing providers."""
        self.assertEqual(self._record("frontier")["locality"], "frontier")

    def test_a_local_record_names_no_subscription(self) -> None:
        """It holds none. A ref here would be the synthetic lease by another route."""
        self.assertIsNone(self._record("local").get("subscription_ref"))

    def test_the_record_carries_the_model_it_runs(self) -> None:
        self.assertEqual(self._record("local")["model_ref"], "llama3.2:3b")


if __name__ == "__main__":
    unittest.main()
