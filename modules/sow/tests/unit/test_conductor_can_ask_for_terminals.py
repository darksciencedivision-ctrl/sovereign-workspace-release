"""EPC-03 Layer 6 — "open up two more terminals", governed.

The operator's ask:

    "I should be able to tell the conductor to open up two more terminals, and then it
     automatically open them up... it's gotta be able to communicate with those extra workers."

Three things have to be true at once for that to be a feature rather than a hazard: the model must
be able to ASK (L6-2), the ask must be visible and the operator's to decide (L6-3), and the number
of workers must be bounded by what the card can actually hold (L6-4). A model that can spawn
without any of those is not an orchestrator; it is an unbounded loop with a GPU.

L6-2 was MEASURED against `qwen3:8b` on this host before any of it was written, because "the model
can call a tool" is a claim about a specific model:

  * an objective needing three parallel reviewers -> ONE tool call, `open_worker_pane`
  * an objective needing none, three panes already idle -> NO tool call, and the content said
    "No additional workers are required for this task."

Both directions. A model that always calls the tool is not deciding anything.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from adapters.local.conductor_tools import (  # noqa: E402
    SPAWN_TOOL,
    SPAWN_TOOL_NAME,
    TOOL_TURN_MAX_TOKENS,
    SpawnRequest,
    request_worker_panes,
)
from control_plane.orchestration.conductor_spawn_requests import queue_spawn_requests  # noqa: E402
from control_plane.orchestration.operator_surface import ApprovalQueue  # noqa: E402
from control_plane.orchestration.pane_capacity import (  # noqa: E402
    max_concurrent_panes,
    pane_footprint_mib,
)

INSTALLED = ["llama3.2:3b", "qwen2.5:3b-instruct", "qwen2.5-coder:3b-instruct", "phi4-mini:3.8b"]


def daemon(tool_calls=(), content="", done_reason="stop", model="qwen3:8b"):
    """A transport standing in for the Ollama daemon, shaped like its real /api/chat response."""
    def transport(_payload):
        return {"model": model, "done_reason": done_reason,
                "message": {"role": "assistant", "content": content,
                            "tool_calls": list(tool_calls)}}
    return transport


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


class TheConductorCanAsk(unittest.TestCase):

    def test_the_tool_is_narrow_by_design(self) -> None:
        """A model may ask for A worker running A model. It may not choose the role, the permission
        profile, or the workspace — widening this schema is how a model acquires authority by
        parameter rather than by decision."""
        properties = SPAWN_TOOL["function"]["parameters"]["properties"]
        self.assertEqual(set(properties), {"model", "reason"})
        self.assertIn("may be refused", SPAWN_TOOL["function"]["description"])

    def test_a_tool_call_becomes_a_request(self) -> None:
        turn = request_worker_panes(
            objective="review three modules in parallel", live_panes=[],
            installed_models=INSTALLED, max_panes=3,
            transport=daemon([call(SPAWN_TOOL_NAME, model="llama3.2:3b", reason="auth module")]))
        self.assertEqual(len(turn.requests), 1)
        self.assertEqual(turn.requests[0].model, "llama3.2:3b")
        self.assertTrue(turn.requests[0].admissible)

    def test_arguments_that_arrive_as_a_JSON_STRING_are_still_read(self) -> None:
        """Ollama returns structured arguments; other runtimes stringify them. A conductor that
        silently ignored a stringified call would look like a model that declined to ask."""
        turn = request_worker_panes(
            objective="o", live_panes=[], installed_models=INSTALLED, max_panes=3,
            transport=daemon([{"function": {"name": SPAWN_TOOL_NAME,
                                            "arguments": '{"model": "llama3.2:3b", "reason": "x"}'}}]))
        self.assertEqual([r.model for r in turn.requests], ["llama3.2:3b"])

    def test_NOT_asking_is_a_first_class_outcome(self) -> None:
        """Measured on the live model: with three idle panes it declined and said why. A conductor
        that always asks is not deciding, and a turn with no requests must not look like a fault."""
        turn = request_worker_panes(
            objective="summarise one paragraph", live_panes=["pane-1", "pane-2", "pane-3"],
            installed_models=INSTALLED, max_panes=3,
            transport=daemon(content="No additional workers are required for this task."))
        self.assertEqual(turn.requests, [])
        self.assertIsNone(turn.error)
        self.assertIn("No additional workers", turn.content)

    def test_a_truncated_turn_is_reported_as_truncated(self) -> None:
        """The live probe finished on `done_reason=length` with one of three workers requested: the
        thinking tokens ate the budget. Reading that as its considered answer turns a truncation
        into a decision."""
        turn = request_worker_panes(
            objective="o", live_panes=[], installed_models=INSTALLED, max_panes=3,
            transport=daemon([call(SPAWN_TOOL_NAME, model="llama3.2:3b", reason="one of three")],
                             done_reason="length"))
        self.assertTrue(turn.truncated)

    def test_the_tool_turn_budget_exceeds_the_decomposition_budget(self) -> None:
        """Same measurement, expressed as a rule. A thinking model spends tokens before its first
        tool call, so a budget sized for the answer alone truncates the request list."""
        from adapters.local.conductor_backend import LOCAL_CONDUCTOR_MAX_TOKENS
        self.assertGreater(TOOL_TURN_MAX_TOKENS, 0)
        self.assertLess(TOOL_TURN_MAX_TOKENS, 8_192)
        self.assertNotEqual(TOOL_TURN_MAX_TOKENS, LOCAL_CONDUCTOR_MAX_TOKENS)

    def test_an_uninstalled_model_is_refused_with_the_reason(self) -> None:
        """A model working from the list in its prompt can transpose a tag. Passing that to the
        spawn chain would fetch gigabytes mid-dispatch."""
        turn = request_worker_panes(
            objective="o", live_panes=[], installed_models=INSTALLED, max_panes=3,
            transport=daemon([call(SPAWN_TOOL_NAME, model="llama4:400b", reason="x")]))
        self.assertFalse(turn.requests[0].admissible)
        self.assertIn("not installed", turn.requests[0].refusal)

    def test_a_duplicate_request_in_one_turn_is_refused(self) -> None:
        turn = request_worker_panes(
            objective="o", live_panes=[], installed_models=INSTALLED, max_panes=4,
            transport=daemon([call(SPAWN_TOOL_NAME, model="llama3.2:3b", reason="a"),
                              call(SPAWN_TOOL_NAME, model="llama3.2:3b", reason="b")]))
        self.assertTrue(turn.requests[0].admissible)
        self.assertFalse(turn.requests[1].admissible)

    def test_a_daemon_that_cannot_be_reached_is_a_turn_with_an_error(self) -> None:
        def explode(_payload):
            raise OSError("connection refused")
        turn = request_worker_panes(objective="o", live_panes=[], installed_models=INSTALLED,
                                    max_panes=3, transport=explode)
        self.assertEqual(turn.requests, [])
        self.assertIn("connection refused", turn.error)

    def test_a_call_to_some_OTHER_tool_is_ignored_not_honoured(self) -> None:
        turn = request_worker_panes(
            objective="o", live_panes=[], installed_models=INSTALLED, max_panes=3,
            transport=daemon([call("delete_everything", model="llama3.2:3b", reason="x")]))
        self.assertEqual(turn.requests, [])


class TheBoundIsEnforcedNotJustAnnounced(unittest.TestCase):

    def test_requests_past_the_bound_are_refused_with_the_arithmetic(self) -> None:
        """The model is TOLD the bound in its system prompt, and being told is not being stopped.
        A model is not a gate."""
        turn = request_worker_panes(
            objective="o", live_panes=["pane-1"], installed_models=INSTALLED, max_panes=2,
            bound_reason="8151 MiB VRAM measured by nvidia-smi",
            transport=daemon([call(SPAWN_TOOL_NAME, model="llama3.2:3b", reason="a"),
                              call(SPAWN_TOOL_NAME, model="qwen2.5:3b-instruct", reason="b")]))
        self.assertTrue(turn.requests[0].admissible)
        self.assertFalse(turn.requests[1].admissible)
        self.assertIn("at most 2 worker pane(s)", turn.requests[1].refusal)
        self.assertIn("nvidia-smi", turn.requests[1].refusal)

    def test_the_bound_is_stated_to_the_model_as_well_as_enforced(self) -> None:
        """A refusal a model cannot learn from is a refusal it repeats every turn."""
        seen = {}

        def transport(payload):
            seen["system"] = payload["messages"][0]["content"]
            return {"message": {"content": "", "tool_calls": []}}

        request_worker_panes(objective="o", live_panes=["pane-1"], installed_models=INSTALLED,
                             max_panes=2, bound_reason="measured VRAM", transport=transport)
        self.assertIn("at most 2 worker pane(s)", seen["system"])
        self.assertIn("pane-1", seen["system"])


class TheBoundIsMeasured(unittest.TestCase):
    """L6-4: "Measured from `nvidia-smi`, not hardcoded"."""

    def test_the_operators_measured_card_holds_no_worker_beside_an_8B_conductor(self) -> None:
        """The finding, pinned. 8151 MiB, less a 2000 MiB host reserve, less ~5927 MiB for an 8B
        conductor at 8192 context, leaves 224 MiB — which is not a 3B worker. This is why D-2 puts
        the workers at 4B and under: an arithmetic consequence of the hardware, not a preference."""
        bound = max_concurrent_panes(vram_mib=8151, worker_parameters_b=4.0,
                                     conductor_parameters_b=8.0, conductor_num_ctx=8_192)
        self.assertEqual(bound["max_panes"], 0)
        self.assertTrue(bound["measured"])
        self.assertIn("8151 MiB VRAM", bound["reason"])

    def test_a_bound_of_zero_says_what_would_change_it(self) -> None:
        """A limit the operator cannot act on is a limit he can only be annoyed by. Both levers
        are his; neither is pulled here."""
        bound = max_concurrent_panes(vram_mib=8151, conductor_parameters_b=8.0)
        self.assertIsNotNone(bound["advice"])
        self.assertIn("SMALLER conductor", bound["advice"])
        self.assertIn("SHORTER conductor context", bound["advice"])
        self.assertIn("operator's to pin", bound["advice"])

    def test_it_bounds_CONCURRENT_RESIDENCY_not_open_terminals(self) -> None:
        """Conflating the two produces a wrong product in either direction: bound the terminals by
        this and the operator is told he cannot open a window he plainly can; bound nothing by it
        and a conductor dispatches four tasks to a card that then pages."""
        bound = max_concurrent_panes(vram_mib=8151)
        self.assertIn("not open terminals", bound["bounds"])

    def test_a_bigger_card_holds_more(self) -> None:
        small = max_concurrent_panes(vram_mib=8151, worker_parameters_b=3.0)
        large = max_concurrent_panes(vram_mib=24576, worker_parameters_b=3.0)
        self.assertGreater(large["max_panes"], small["max_panes"])

    def test_an_unmeasurable_card_refuses_to_guess_and_says_so(self) -> None:
        bound = max_concurrent_panes(vram_mib=0)
        self.assertEqual(bound["max_panes"], 1)
        self.assertFalse(bound["measured"])
        self.assertIn("refusal to guess", bound["reason"])

    def test_a_footprint_rounds_UP_to_the_next_measured_class(self) -> None:
        """Under-estimating authorises a pane the card cannot hold, and the operator finds out when
        the daemon starts paging — silently, since /api/ps still reports the model loaded."""
        self.assertEqual(pane_footprint_mib(3.5, 0), pane_footprint_mib(4.0, 0))
        self.assertGreater(pane_footprint_mib(8.0, 0), pane_footprint_mib(4.0, 0))

    def test_context_costs_VRAM_and_the_bound_knows_it(self) -> None:
        self.assertGreater(pane_footprint_mib(3.0, 8_192), pane_footprint_mib(3.0, 2_048))


class TheOperatorDecides(unittest.TestCase):
    """L6-3: nothing spawns invisibly."""

    def test_a_request_becomes_a_PROTECTED_ACTION_in_the_drawer(self) -> None:
        queue = ApprovalQueue()
        result = queue_spawn_requests([SpawnRequest("llama3.2:3b", "review the auth module")],
                                      queue=queue, objective="review three modules",
                                      conductor_model="qwen3:8b")
        drawer = queue.drawer_model()
        self.assertEqual(result["queued_count"], 1)
        self.assertEqual(drawer["kind_counts"]["protected_action"], 1)
        self.assertEqual(drawer["badge_count"], 1)

    def test_the_row_says_a_MODEL_asked_not_the_operator(self) -> None:
        """An operator reading "spawn llama3.2:3b" needs to know whether he asked for it. That is
        the whole difference between the two rows."""
        queue = ApprovalQueue()
        queue_spawn_requests([SpawnRequest("llama3.2:3b", "auth module")], queue=queue,
                             conductor_model="qwen3:8b")
        row = queue.drawer_model()["pending"][0]
        self.assertEqual(row["origin"], "conductor")
        self.assertTrue(row["detail"]["model_initiated"])
        self.assertEqual(row["detail"]["requested_by"], "qwen3:8b")

    def test_the_request_is_QUEUED_never_executed(self) -> None:
        """`spawn` is already a protected verb, and the broker already refuses to auto-execute one
        from any source. A conductor gets exactly the treatment the operator's own spoken "spawn a
        worker" gets."""
        queue = ApprovalQueue()
        queue_spawn_requests([SpawnRequest("llama3.2:3b", "auth")], queue=queue)
        row = queue.drawer_model()["pending"][0]
        self.assertEqual(row["detail"]["verb"], "spawn")
        self.assertEqual(row["detail"]["category"], "protected")
        self.assertFalse(row["resolved"])
        self.assertIsNone(row["decision"])

    def test_the_row_carries_the_brokers_pending_id_so_a_decision_routes_BACK(self) -> None:
        """Without the ref, an approval would have nothing to approve — the operator's answer has
        to reach the same broker that queued it (`apply_protected_decision`)."""
        queue = ApprovalQueue()
        result = queue_spawn_requests([SpawnRequest("llama3.2:3b", "auth")], queue=queue)
        row = queue.drawer_model()["pending"][0]
        self.assertEqual(row["ref"], result["queued"][0]["pending_id"])
        self.assertTrue(row["ref"].startswith("q-"))

    def test_an_inadmissible_request_never_reaches_the_broker_and_is_still_reported(self) -> None:
        """A request that vanished silently gets asked again every turn, and an operator who never
        sees the ask cannot tell a bounded system from a broken one."""
        queue = ApprovalQueue()
        result = queue_spawn_requests(
            [SpawnRequest("nope:99b", "x", admissible=False, refusal="not installed on this host")],
            queue=queue)
        self.assertEqual(result["queued_count"], 0)
        self.assertEqual(result["refused_count"], 1)
        self.assertFalse(result["refused"][0]["reached_broker"])
        self.assertEqual(queue.drawer_model()["badge_count"], 0)

    def test_this_module_opens_nothing(self) -> None:
        """L6-1's property, asserted against the source. A private spawn route is the one thing
        D-3 forbids, and it would not announce itself."""
        import control_plane.orchestration.conductor_spawn_requests as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "emit_worker_launch", "spawn_conductor_pane",
                          "authorize_worker_pane", "Popen"):
            self.assertNotIn(forbidden + "(", source)
        self.assertIn("Spawns nothing", source)


if __name__ == "__main__":
    unittest.main()
