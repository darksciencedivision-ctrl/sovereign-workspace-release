"""EPC-04 W-5 — an OpenCode coding pane registers as a Sovereign node.

Invariant 2 is "every terminal is a Sovereign node", and it does not carve out coding. U313 is the
cautionary case directly upstream of this one: `ollama_local` sat in `REGISTRABLE_PROVIDERS` while
the emitter's local branch never called the registrar, so the invariant read as satisfied and was
not — measured on the operator's host as 154 node events with local 0.

So these tests pin the CALL, the ADAPTER it is made with, and the record's governed fields. A pane
that opens without a row is the failure; a pane that registers as the wrong thing is the subtler
one, because a conductor reading the registry then routes reasoning work to a file-editing harness.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

SCHEMA_DIR = MODULE_ROOT / "schemas"

from adapters.coding.opencode.session import OPENCODE_LOCAL_ADAPTER  # noqa: E402
from node_runtime.supervisor.provider_node_registration import (  # noqa: E402
    REGISTRABLE_PROVIDERS,
    RESIDENCY_GOVERNED_ADAPTERS,
    ProviderNodeRegistrationRefused,
    _PROVIDER_FACTS,
    _require_residency,
)
from tools.live import emit_worker_launch as ewl  # noqa: E402


class Chrome:
    node_id = "coding-pane-1"
    adapter = OPENCODE_LOCAL_ADAPTER
    locality = "local"
    model_slug = "qwen2.5-coder:3b"
    subscription = None


class Session:
    chrome = Chrome()
    launch = {"cwd": str(MODULE_ROOT / "worktrees" / "coding-pane-1"),
              "argv": ["opencode", "...", "--pure", "-m", "ollama/qwen2.5-coder:3b"]}
    permission_profile_id = "pp-worker-coding"
    provider = OPENCODE_LOCAL_ADAPTER
    residency_decision = {"model": "qwen2.5-coder:3b", "scheduled": True, "status": "RESIDENT"}


class RecordingRegistrar:
    log_path = "/tmp/probe/node_events.jsonl"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def register_pane_session(self, session, *, session_id, lease_id="", residency=None):
        self.calls.append({"session_id": session_id, "lease_id": lease_id, "residency": residency,
                           "adapter": getattr(session.chrome, "adapter", None)})

        class Out:
            node_key = "worker-coding-pane-1"
            incarnation = 1
            validated_against = "node@1.1"
            adapter_schema_version = "node@1.1"
            record = {"node_id": "uuid-9", "class": "worker_coding_specialist",
                      "locality": "local"}

        return Out()


class TheCodingPaneIsARegistrableProvider(unittest.TestCase):

    def test_opencode_can_write_a_node_record(self) -> None:
        self.assertIn(OPENCODE_LOCAL_ADAPTER, REGISTRABLE_PROVIDERS)

    def test_its_node_class_is_coding_not_reasoning(self) -> None:
        """The registry answers "who is up and what can they do". Filing a harness with write hands
        as a reasoning worker answers that question wrongly while looking correct."""
        node_class, _descriptors = _PROVIDER_FACTS[OPENCODE_LOCAL_ADAPTER]
        self.assertEqual(node_class, "worker_coding_specialist")

    def test_its_node_class_is_one_the_node_schema_admits(self) -> None:
        """The regression this pins. The class above was `worker_coding`, which is NOT a member of
        `node@1.1`'s enum, so every OpenCode pane launch was refused at `node_record_invalid` —
        after passing selection, local-runtime and residency, which is why it read as a governed
        refusal rather than a typo. Asserting the literal alone cannot catch that: the old literal
        was asserted too, and agreed with the bug. This asserts the class against the SCHEMA the
        registrar validates against, so any future class here must be one a record can be written
        with. Every registrable provider is checked, not just this one."""
        enum = json.loads(
            (SCHEMA_DIR / "node.schema@1.1.json").read_text(encoding="utf-8")
        )["properties"]["class"]["enum"]
        for provider in REGISTRABLE_PROVIDERS:
            node_class, _descriptors = _PROVIDER_FACTS[provider]
            self.assertIn(node_class, enum,
                          f"{provider} registers class {node_class!r}, which node@1.1 refuses — "
                          f"its panes cannot open (invariant 2)")

    def test_it_declares_a_coding_capability_bound_to_local_only(self) -> None:
        _node_class, descriptors = _PROVIDER_FACTS[OPENCODE_LOCAL_ADAPTER]
        self.assertEqual([d["capability"] for d in descriptors], ["coding"])
        for descriptor in descriptors:
            # node@1.1 enumerates ["any", "local_only", "frontier_ok"]; "local" is not a member
            self.assertEqual(descriptor["requirements"]["locality"], "local_only")
            self.assertNotEqual(descriptor["requirements"].get("tool_use"), True)

    def test_it_is_governed_by_residency_and_therefore_holds_no_lease(self) -> None:
        self.assertIn(OPENCODE_LOCAL_ADAPTER, RESIDENCY_GOVERNED_ADAPTERS)


class TheEmitterAsksTheRegistrar(unittest.TestCase):

    def test_an_opencode_session_reaches_the_registrar(self) -> None:
        """The U313 assertion, restated for the new provider: `calls` must not stay empty."""
        registrar = RecordingRegistrar()
        result = ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                         adapter_id=OPENCODE_LOCAL_ADAPTER)
        self.assertEqual(len(registrar.calls), 1, "the registrar was never asked")
        self.assertTrue(result["registered"])
        self.assertEqual(registrar.calls[0]["adapter"], OPENCODE_LOCAL_ADAPTER)

    def test_it_passes_NO_lease_because_there_is_no_subscription_to_count(self) -> None:
        """Invariant 19. A synthetic lease id would assert a terminal nobody counted."""
        registrar = RecordingRegistrar()
        ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                adapter_id=OPENCODE_LOCAL_ADAPTER)
        self.assertEqual(registrar.calls[0]["lease_id"], "")

    def test_the_record_carries_a_non_null_class_and_local_locality(self) -> None:
        """W-5's done-when, verbatim: `class` non-null, `locality: local`, `subscription: null`."""
        registrar = RecordingRegistrar()
        result = ewl._register_pane_node(registrar, Session(), session_id="s-1", lease_id="",
                                         adapter_id=OPENCODE_LOCAL_ADAPTER)
        self.assertTrue(result["registered"])
        self.assertIsNone(Session.chrome.subscription)
        self.assertEqual(Session.chrome.locality, "local")


class WithoutAReservationThereIsStillNoRow(unittest.TestCase):
    """A coding pane gets no exemption from invariant 22: same weights, same card."""

    def test_a_coding_pane_with_no_residency_decision_is_refused(self) -> None:
        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency(None, session_id="s-1", model="qwen2.5-coder:3b")

    def test_a_coding_pane_whose_reservation_was_not_scheduled_is_refused(self) -> None:
        """"A planner answered" is not "the model was admitted" — the fence reads the verdict."""
        unscheduled = {"model": "qwen2.5-coder:3b", "scheduled": False, "status": "REFUSED"}
        with self.assertRaises(ProviderNodeRegistrationRefused):
            _require_residency(unscheduled, session_id="s-1", model="qwen2.5-coder:3b")

    def test_the_real_reservation_passes_so_the_two_tests_above_are_not_vacuous(self) -> None:
        self.assertTrue(_require_residency(Session.residency_decision, session_id="s-1",
                                           model="qwen2.5-coder:3b"))


if __name__ == "__main__":
    unittest.main()
