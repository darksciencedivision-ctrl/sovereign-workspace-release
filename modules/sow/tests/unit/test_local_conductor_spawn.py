"""EPC-03 L5-1 — a conductor that can be born without a frontier subscription.

`conductor_spawn.spawn_claude_code_conductor` calls itself "the ONE place a LIVE `claude_code`-
backed conductor is born", and that was literally true: with no `claude` CLI it raises
`ClaudeCliUnavailable`, so on this host no conductor could spawn at all - while
`control_plane/conductor/registry.py` went on deriving LOCAL conductor seats from the operator's
model ceiling. The system offered a seat no code path could fill.

These tests hold the translation honest. Every frontier gate has a local counterpart that answers
the same question about a different cost, and the one gate with NO counterpart (operator live
terms) is absent for a stated reason, not by omission.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from node_runtime.supervisor import local_conductor_spawn as lcs  # noqa: E402
from scheduler.residency_planner.residency_planner import ResidencyPlanner  # noqa: E402

LOCAL_RECORD = {"name": "qwen3:8b", "size": 5_230_000_000,
                "details": {"parameter_size": "8.2B"}}
#: A tag that LOOKS local and holds no weights here - the shape that put a live spend path behind
#: a "local" label in the operator's own picker earlier in this programme.
CLOUD_RECORD = {"name": "gpt-oss-cloud:latest", "size": 1024,
                "details": {"parameter_size": "120B"}}


class Roster:
    def __init__(self, refuse: bool = False) -> None:
        self.calls: list = []
        self._refuse = refuse

    def assert_startup(self, capabilities, **kwargs):
        self.calls.append({"capabilities": list(capabilities), "kwargs": kwargs})
        if self._refuse:
            raise RuntimeError("roster says no")
        return True


def planner(total: int = 8151, footprint: int = 5900, model: str = "qwen3:8b") -> ResidencyPlanner:
    p = ResidencyPlanner(total)
    p.register_model(model, footprint)
    return p


def spawn(**overrides):
    kwargs = dict(
        mcp_client=object(), model="qwen3:8b", node_id="conductor-1",
        permission_profile_id="pp-conductor", profile_loader=Roster(),
        conductor_file_refs={}, residency_planner=planner(),
        residency_budget={"established": True, "vram_budget_mb": 8151},
        model_record=LOCAL_RECORD, installed_models=["qwen3:8b"], runtime_present=True)
    kwargs.update(overrides)
    return lcs.spawn_local_conductor(**kwargs)


class ALocalConductorIsConstructibleWithoutTheClaudeCli(unittest.TestCase):
    """L5-1's acceptance criterion, stated as one test."""

    def test_it_builds_a_started_ready_ConductorAdapter(self) -> None:
        adapter, authorization = spawn()
        self.assertEqual(type(adapter).__name__, "ConductorAdapter")
        self.assertEqual(authorization["model"], "qwen3:8b")
        self.assertEqual(authorization["node_class"], "conductor")

    def test_it_never_imports_or_needs_the_claude_cli(self) -> None:
        source = Path(lcs.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ClaudeCliBackend", source)
        self.assertNotIn("_detect_cli", source)

    def test_it_holds_no_subscription_and_says_so_rather_than_omitting_it(self) -> None:
        """Invariant 19: locality is per-node and a local node is not subscription-governed. A
        null that is PRESENT is a statement; a missing key is an oversight nobody can tell from
        a decision."""
        _adapter, authorization = spawn()
        self.assertIn("subscription", authorization)
        self.assertIsNone(authorization["subscription"])
        self.assertFalse(authorization["credential_held"])

    def test_no_subscription_terminal_is_acquired_at_start(self) -> None:
        """A synthetic subscription ref would make the adapter acquire a terminal nobody counted.
        The context carries an empty ref, which `ConductorAdapter.start()` already reads as
        nothing-to-acquire — by its own existing condition, not by a branch added for this path."""
        adapter, _ = spawn()
        self.assertEqual(adapter._context.subscription_ref, "")
        self.assertIsNone(adapter._governor)


class TheGatesAreTranslatedNotRelaxed(unittest.TestCase):

    def test_the_roster_gate_is_asserted_on_the_LOCAL_capability(self) -> None:
        roster = Roster()
        spawn(profile_loader=roster)
        capability = roster.calls[0]["capabilities"][0]
        self.assertEqual(capability.adapter, "ollama_local")
        self.assertEqual(capability.node_class, "conductor")
        self.assertFalse(capability.subscription_backed)

    def test_no_live_authorization_is_passed_to_a_path_that_cannot_spend(self) -> None:
        """Asserting a live gate on a free call is how a live gate stops meaning anything."""
        roster = Roster()
        spawn(profile_loader=roster)
        self.assertNotIn("live_auth", roster.calls[0]["kwargs"])

    def test_a_roster_refusal_is_attributed_to_the_roster(self) -> None:
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(profile_loader=Roster(refuse=True))
        self.assertEqual(caught.exception.gate, lcs.GATE_ROSTER)

    def test_a_CLOUD_routed_tag_is_refused__the_spend_wall(self) -> None:
        """The local counterpart of `assert_provider_live`. A tag with no weights on this machine
        is a spend path wearing a local label, and it is refused whatever its size."""
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(model="gpt-oss-cloud:latest", model_record=CLOUD_RECORD,
                  installed_models=["gpt-oss-cloud:latest"],
                  residency_planner=planner(model="gpt-oss-cloud:latest"))
        self.assertEqual(caught.exception.gate, lcs.GATE_NOT_LOCAL)
        self.assertIn("no model weights on this machine", str(caught.exception))

    def test_an_UNCHECKABLE_model_is_refused_rather_than_assumed_local(self) -> None:
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(model_record=None)
        self.assertEqual(caught.exception.gate, lcs.GATE_NOT_LOCAL)
        self.assertIn("could not be DECIDED", str(caught.exception))

    def test_an_OVER_CEILING_local_model_is_the_operators_call_and_is_admitted(self) -> None:
        """ENTRY 030: "You're only bound by the eight billion local models when you're doing the
        testing, not me." A 14B local conductor is slow, not a spend-wall violation, and refusing
        it here would misattribute a preference to a safety rule."""
        big = {"name": "qwen3:14b", "size": 9_280_000_000,
               "details": {"parameter_size": "14.8B"}}
        _adapter, authorization = spawn(
            model="qwen3:14b", model_record=big, installed_models=["qwen3:14b"],
            residency_planner=planner(total=16_000, footprint=9_900, model="qwen3:14b"),
            residency_budget={"established": True, "vram_budget_mb": 16_000})
        self.assertEqual(authorization["model"], "qwen3:14b")

    def test_a_missing_runtime_and_a_missing_MODEL_are_different_refusals(self) -> None:
        """One message covering both sends the operator to the wrong fix: an install versus a
        `pull` he has not run."""
        with self.assertRaises(lcs.LocalConductorRefused) as absent:
            spawn(runtime_present=False)
        self.assertEqual(absent.exception.gate, lcs.GATE_RUNTIME_ABSENT)

        with self.assertRaises(lcs.LocalConductorRefused) as missing:
            spawn(installed_models=["llama3.2:3b"])
        self.assertEqual(missing.exception.gate, lcs.GATE_MODEL_ABSENT)
        self.assertIn("ollama pull", str(missing.exception))


class TheResidencyGateIsTheAllowanceGate(unittest.TestCase):
    """Invariant 22 replaces the I-X3 subscription allowance. Same job: refuse a node the host
    cannot actually hold."""

    def test_a_reservation_is_taken_and_reported(self) -> None:
        _adapter, authorization = spawn()
        self.assertTrue(authorization["residency"]["scheduled"])
        self.assertEqual(authorization["residency"]["model"], "qwen3:8b")

    def test_no_planner_means_no_conductor_and_names_PROVENANCE_not_fit(self) -> None:
        """Nothing was measured. This refusal must never be readable as evidence that a model
        does not fit — that is a different fact with a different fix."""
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(residency_planner=None, residency_budget=None)
        self.assertEqual(caught.exception.gate, lcs.GATE_VRAM_BUDGET)
        self.assertIn("could not be established", str(caught.exception))

    def test_a_budget_that_is_not_the_one_ENFORCED_is_refused(self) -> None:
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(residency_budget={"established": True, "vram_budget_mb": 99_999})
        self.assertEqual(caught.exception.gate, lcs.GATE_VRAM_BUDGET)
        self.assertIn("99999MB", str(caught.exception).replace(",", ""))

    def test_a_model_that_would_displace_another_is_REFUSED_not_swapped(self) -> None:
        """The planner mirrors the daemon's residency; it does not own the host's VRAM and cannot
        tell whether a model it considers idle is mid-generation."""
        p = ResidencyPlanner(8151)
        p.register_model("other:8b", 5_900)
        p.register_model("qwen3:8b", 5_900)
        p.request_load("other:8b")
        p.complete_load("other:8b")
        with self.assertRaises(lcs.LocalConductorRefused) as caught:
            spawn(residency_planner=p)
        self.assertEqual(caught.exception.gate, lcs.GATE_VRAM_ADMISSION)

    def test_a_refusal_leaves_no_phantom_residency_entry(self) -> None:
        """`request_load` mutates and the planner has no cancel primitive, so everything decidable
        without it is decided first. A refusal that scheduled something would corrupt the very view
        the operator reads to understand why he was refused."""
        p = ResidencyPlanner(4_000)
        p.register_model("qwen3:8b", 5_900)
        with self.assertRaises(lcs.LocalConductorRefused):
            spawn(residency_planner=p,
                  residency_budget={"established": True, "vram_budget_mb": 4_000})
        statuses = {m["model"]: m["status"] for m in p.snapshot()["models"]}
        self.assertNotIn(statuses.get("qwen3:8b"), ("loading", "resident"))

    def test_an_injected_backend_does_not_exempt_a_caller_from_the_reservation(self) -> None:
        """The reservation is about the HOST's VRAM, not about whether this particular call
        reaches the daemon."""
        with self.assertRaises(lcs.LocalConductorRefused):
            spawn(backend=object(), residency_planner=None, residency_budget=None)


class TheAbsentGateIsAbsentForAStatedReason(unittest.TestCase):

    def test_the_operator_terms_gate_is_named_and_its_absence_explained(self) -> None:
        """It guards SPEND. Requiring it for a free local call would train the operator to click
        past the confirmation that guards real money. Left implicit, this reads as a dropped gate;
        the module says which gate it is and why it has no counterpart."""
        source = Path(lcs.__file__).read_text(encoding="utf-8")
        self.assertIn("operator live-terms confirmation", source)
        self.assertIn("spends nothing", source)

    def test_it_grants_no_authority_the_frontier_path_does_not(self) -> None:
        _adapter, authorization = spawn()
        self.assertIn("CANDIDATE", authorization["note"])
        self.assertTrue(authorization["spawned_by_supervisor"])


if __name__ == "__main__":
    unittest.main()
