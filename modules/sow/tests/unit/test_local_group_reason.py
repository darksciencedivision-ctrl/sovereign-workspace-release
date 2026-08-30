"""
FIXUP-01 F-5 / N-25 — the local provider group always says WHY it is empty.

Phase D refuted N-25 as written: the Electron picker is not frontier-only, and there is no
missing local code path. `tools/live/enumerate_pane_picker.py` enumerates `ollama list`,
`pane_picker` builds an `ollama_local` group, `counts.local` exists, and the renderer paints
zero-option groups with their own reason. The punch-list finding rested on
`grep ollama apps/desktop/*.js`, a non-recursive glob that cannot see `apps/desktop/picker/`.

What DID survive reproduction is this: `_group_status` falls back to the generic
"no options enumerated for this provider" when a group has neither options nor a `group_reason`,
and the local group was passed no `group_reason` at all. So with Ollama down the operator was
told, about the one provider that costs nothing to run, only that nothing had been enumerated —
naming neither Ollama nor anything they could act on. `local_admission_reason` had already
computed the actionable text; it reached the individual options and not the group heading, which
is the only thing visible when there are zero options.

That is the N-22 lesson in a second place, and it is what these tests pin.
"""
import unittest

from control_plane.nodes.pane_picker import _local_group_reason, _group_status

DAEMON_DOWN = ("no local pane can be authorized: this host's VRAM admission budget could not be "
               "established - ollama daemon unreachable - no planner")


class TestLocalGroupReasonIsActionable(unittest.TestCase):

    def test_daemon_down_reports_the_admission_reason_not_a_generic_line(self):
        reason = _local_group_reason([], DAEMON_DOWN)
        self.assertEqual(reason, DAEMON_DOWN)
        status = _group_status([], reason)
        self.assertFalse(status["available"])
        self.assertEqual(status["option_count"], 0)
        self.assertNotEqual(
            status["reason"], "no options enumerated for this provider",
            "the local group fell back to the generic line; the operator is told nothing about "
            "Ollama (N-25)")
        self.assertIn("ollama", status["reason"].lower(),
                      "the local group's reason must name the runtime it is waiting on")

    def test_runtime_present_but_nothing_pulled_is_its_own_distinct_reason(self):
        """A daemon that is running and empty is a different fact from a daemon that is down,
        and the operator's next action differs: pull a model vs start Ollama."""
        reason = _local_group_reason([], None)
        self.assertIsNotNone(reason)
        self.assertNotEqual(reason, DAEMON_DOWN)
        self.assertIn("ollama list", reason)
        status = _group_status([], reason)
        self.assertNotEqual(status["reason"], "no options enumerated for this provider")

    def test_models_present_and_admissible_needs_no_group_reason(self):
        self.assertIsNone(_local_group_reason(["qwen3:8b"], None))

    def test_models_present_but_inadmissible_still_reports_the_admission_reason(self):
        """Options exist but every one is greyed; the heading must carry the same cause rather
        than looking available."""
        self.assertEqual(_local_group_reason(["qwen3:8b"], DAEMON_DOWN), DAEMON_DOWN)

    def test_the_generic_fallback_still_exists_for_groups_that_have_no_reason(self):
        """The fallback is not deleted — it is simply no longer what the local group gets."""
        self.assertEqual(_group_status([], None)["reason"],
                         "no options enumerated for this provider")


class TestLocalEnumerationIsNotGatedByLiveOperation(unittest.TestCase):
    """S-18 / OD-31. Local models cost nothing, so they must not be gated behind the operator's
    spend switch. Phase D measured that they are not; this pins it so a future change to the
    live-authorization path cannot quietly take local models with it."""

    def test_local_options_are_built_without_any_live_authorization(self):
        from control_plane.nodes.pane_picker import _local_options
        options = _local_options(["qwen3:8b", "qwen2.5-coder:7b"], None, None)
        self.assertEqual(len(options), 2)
        for opt in options:
            self.assertEqual(opt["locality"], "local")
            self.assertNotIn("live_operation", str(opt.get("unavailable_reason") or ""),
                             "a local option is being refused by the frontier spend switch")


if __name__ == "__main__":
    unittest.main()
