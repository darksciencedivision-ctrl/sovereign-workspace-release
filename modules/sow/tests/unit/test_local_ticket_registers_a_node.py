"""EPC-02 U313(A) — the LOCAL branch of the launch ticket must ask the registrar.

The gate was not `REGISTRABLE_PROVIDERS`. `emit_worker_launch.build_worker_launch_ticket`'s
local branch HARDCODED a no-record result and never called `_register_pane_node` at all:

    node_registration = _no_pane_node_record(
        "a LOCAL pane holds no subscription terminal and no frontier node record is "
        "written for it here: this wiring covers the two OP-12 frontier providers...")

So the emitter could report `ollama_local` as registrable all day and this path never asked.
It read as a deliberate design statement while being the reason invariant 2 ("every terminal
is a Sovereign node") was unmet for every local terminal on the host — measured: 154 node
events, grok_build 22, google_antigravity 20, local 0.

That is precisely the failure the comment beside `REGISTRABLE_PROVIDERS` predicts: *"a second
literal elsewhere is how a provider ends up in one list and not the other, which reads as
'deliberately not registered' and is really a typo (the U254 shape)."*

These tests pin the call site, so the second literal cannot come back.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from tools.live import emit_worker_launch as ewl  # noqa: E402


class Chrome:
    node_id = "pane-1"
    adapter = "ollama_local"
    locality = "local"
    model_slug = "granite4.2:3b"
    subscription = None


class Session:
    chrome = Chrome()
    launch = {"cwd": str(MODULE_ROOT), "argv": ["ollama", "run", "granite4.2:3b"]}
    permission_profile_id = "pp-worker-reasoning"
    provider = "ollama_local"
    residency_decision = {"model": "granite4.2:3b", "scheduled": True, "status": "RESIDENT"}


class RecordingRegistrar:
    """Stands in for the real registrar and records whether it was ASKED."""

    log_path = "/tmp/probe/node_events.jsonl"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def register_pane_session(self, session, *, session_id, lease_id="", residency=None):
        self.calls.append({"session_id": session_id, "lease_id": lease_id,
                           "residency": residency,
                           "adapter": getattr(session.chrome, "adapter", None)})

        class Out:
            node_key = "worker-pane-1"
            incarnation = 1
            validated_against = "node@1.1"
            adapter_schema_version = "node@1.1"
            record = {"node_id": "uuid-1", "class": "worker_reasoning", "locality": "local"}

        return Out()


class TheLocalBranchAsksTheRegistrar(unittest.TestCase):

    def test_a_local_session_reaches_the_registrar(self) -> None:
        """The whole defect in one assertion: before this, `calls` stayed empty."""
        registrar = RecordingRegistrar()
        result = ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                         adapter_id="ollama_local")
        self.assertEqual(len(registrar.calls), 1, "the registrar was never asked")
        self.assertTrue(result["registered"])
        self.assertEqual(result["node_key"], "worker-pane-1")

    def test_it_passes_NO_lease_for_a_local_pane(self) -> None:
        """A synthetic lease id would assert a subscription count nobody took."""
        registrar = RecordingRegistrar()
        ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                adapter_id="ollama_local")
        self.assertEqual(registrar.calls[0]["lease_id"], "")

    def test_the_canned_no_record_string_is_gone_from_the_success_path(self) -> None:
        """It named "the two OP-12 frontier providers" as a statement of fact on a path that is
        now capable of registering a third. A stale literal on a success path is how the next
        reader learns something untrue."""
        source = Path(ewl.__file__).read_text(encoding="utf-8")
        occurrences = source.count("this wiring covers the two OP-12 frontier providers")
        self.assertEqual(
            occurrences, 0,
            "the hardcoded local no-record message is still present; if it has been reinstated "
            "on the success path the local branch has stopped asking the registrar again")

    def test_an_adapter_outside_the_registrable_set_still_gets_no_record(self) -> None:
        """The refusal that SHOULD remain: claude_code and codex panes are still unwired
        (U313's other owed leg), and this must keep saying so rather than registering them."""
        registrar = RecordingRegistrar()
        result = ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                         adapter_id="claude_code")
        self.assertFalse(result["registered"])
        self.assertEqual(registrar.calls, [], "an unwired adapter must not reach the registrar")
        self.assertIn("outside the OP-12 node-registration wiring", result["reason"])

    def test_no_registrar_means_no_record_and_says_so(self) -> None:
        result = ewl._register_pane_node(None, Session(), session_id="s-1", lease_id="",
                                         adapter_id="ollama_local")
        self.assertFalse(result["registered"])
        self.assertIn("no registrar", result["reason"])


class WithoutAReservationThereIsStillNoRow(unittest.TestCase):
    """The operator's requirement: the fix must not have opened a door for unreserved panes."""

    def test_a_session_with_no_residency_decision_is_refused_by_the_fence(self) -> None:
        from node_runtime.supervisor.provider_node_registration import (
            ProviderNodeRegistrationRefused,
            _require_residency,
        )

        class Unreserved(Session):
            residency_decision = None

        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency(Unreserved.residency_decision, session_id="s-1",
                               model="granite4.2:3b")

    def test_a_forged_reservation_is_refused(self) -> None:
        from node_runtime.supervisor.provider_node_registration import (
            ProviderNodeRegistrationRefused,
            _require_residency,
        )
        for forged in ({"scheduled": "yes", "model": "granite4.2:3b"},
                       {"scheduled": True, "model": "some-other-model"},
                       {}):
            with self.assertRaises(ProviderNodeRegistrationRefused):
                _require_residency(forged, session_id="s-1", model="granite4.2:3b")


class TheFrontierPathIsUnchanged(unittest.TestCase):

    def test_a_frontier_adapter_still_registers_with_its_lease(self) -> None:
        registrar = RecordingRegistrar()

        class FrontierChrome(Chrome):
            adapter = "grok_build"
            locality = "frontier"

        class FrontierSession(Session):
            chrome = FrontierChrome()
            provider = "grok_build"

        ewl._register_pane_node(registrar, FrontierSession(), session_id="s-1",
                                lease_id="lease-abc", adapter_id="grok_build")
        self.assertEqual(registrar.calls[0]["lease_id"], "lease-abc",
                         "the frontier path must still carry its I-X3 lease")


if __name__ == "__main__":
    unittest.main()
