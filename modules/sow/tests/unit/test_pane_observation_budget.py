"""EPC-03 L4-3/L4-4 — how much of a worker pane a conductor can actually read.

L4-4's criterion is "Measured, not assumed", and the first draft of the module failed it: it
carried "roughly 0.5 MiB per 1k tokens" for the KV cache, which is ~290x too small. The real
figure came from loading `qwen3:8b` at four context lengths on the operator's host and reading
`/api/ps` and `nvidia-smi` at each. The 16384 row is the one that matters — the model SPILLED,
1641 MiB of it moved to system RAM, and `/api/ps` still reported it loaded. That is the same
failure this build already paid for at `num_ctx: 131_072`.

These tests pin the derivation's SHAPE and its refusals. They cannot re-measure the host, so they
assert the properties a wrong constant would break, and one anchored case at the measured VRAM.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from control_plane.orchestration.pane_observation import (  # noqa: E402
    MAX_OBSERVATION_CHARS,
    MEASURED_8B_WEIGHTS_MIB,
    MEASURED_KV_MIB_PER_1K,
    MIN_OBSERVATION_CHARS,
    OBSERVATION_SCHEMA,
    observation_budget,
    observation_evidence,
    recommended_num_ctx,
)


class TheContextIsDerivedFromMeasuredHardware(unittest.TestCase):

    def test_the_operators_measured_card_gets_the_context_that_stayed_RESIDENT(self) -> None:
        """8151 MiB was the measured total. At 8192 the model sat entirely in VRAM (5900 MiB);
        at 16384 it spilled. The derivation must land on the last resident step, not the first
        one that fits on paper."""
        num_ctx, reason = recommended_num_ctx(8151)
        self.assertEqual(num_ctx, 8192)
        self.assertIn("8151 MiB", reason)
        self.assertIn("145 MiB per 1k", reason)

    def test_a_card_too_small_for_the_weights_says_so_and_does_not_guess_upward(self) -> None:
        num_ctx, reason = recommended_num_ctx(4096)
        self.assertEqual(num_ctx, 2_048)
        self.assertLess(num_ctx, 8192)
        self.assertIn("does not hold an 8B model", reason)

    def test_more_VRAM_never_recommends_LESS_context(self) -> None:
        """Monotonicity. A step table with a typo breaks this and nothing else would catch it."""
        seen = [recommended_num_ctx(v)[0] for v in range(4_000, 32_000, 500)]
        self.assertEqual(seen, sorted(seen))

    def test_an_unmeasurable_card_refuses_to_dress_a_default_as_a_measurement(self) -> None:
        num_ctx, reason = recommended_num_ctx(0)
        self.assertEqual(num_ctx, 8_192)
        self.assertIn("could not be measured", reason)
        self.assertIn("default", reason)

    def test_the_measured_constants_are_the_measured_ones(self) -> None:
        """A regression guard on the specific mistake this replaced: a plausible-looking constant
        that nobody had run the arithmetic on. 145 MiB/1k is what the host reported between
        num_ctx 2048 and 8192; anything near 0.5 is the old wrong figure returning."""
        self.assertGreater(MEASURED_KV_MIB_PER_1K, 100)
        self.assertLess(MEASURED_KV_MIB_PER_1K, 250)
        self.assertGreater(MEASURED_8B_WEIGHTS_MIB, 4_000)


class TheBudgetReportsItsOwnDerivation(unittest.TestCase):

    def test_it_returns_the_figures_not_only_the_answer(self) -> None:
        """A receipt that shows the derivation can be checked; one that asserts a number cannot."""
        budget = observation_budget(num_ctx=8_192)
        for key in ("num_ctx", "num_ctx_reason", "reserved_prompt_tokens",
                    "reserved_response_tokens", "chars_per_token", "total_max_chars"):
            self.assertIn(key, budget)

    def test_the_prompt_and_the_response_are_reserved_before_any_pane_text(self) -> None:
        small = observation_budget(num_ctx=4_096)
        large = observation_budget(num_ctx=32_768)
        self.assertLess(small["total_max_chars"], large["total_max_chars"])
        # 4096 - 1200 - 2048 = 848 tokens for observation, at 3 chars each.
        self.assertEqual(small["total_max_chars"], 848 * 3)

    def test_a_context_too_small_to_read_a_pane_says_so_rather_than_returning_a_sliver(self) -> None:
        """A 60-character window is not an observation. A conductor that cannot usefully read its
        panes should be told, not handed something it will reason from anyway."""
        budget = observation_budget(num_ctx=3_400)
        self.assertFalse(budget["fits"])
        self.assertEqual(budget["total_max_chars"], 0)
        self.assertIn("should not pretend to", budget["reason"])

    def test_the_ceiling_caps_a_huge_context_and_says_that_it_did(self) -> None:
        budget = observation_budget(num_ctx=131_072)
        self.assertEqual(budget["total_max_chars"], MAX_OBSERVATION_CHARS)
        self.assertTrue(budget["capped_by_ceiling"])

    def test_the_floor_and_the_ceiling_are_the_right_way_round(self) -> None:
        self.assertLess(MIN_OBSERVATION_CHARS, MAX_OBSERVATION_CHARS)


def observation(pane_id: str, **kw) -> dict:
    base = {"schema": OBSERVATION_SCHEMA, "pane_id": pane_id, "answerable": True,
            "text": "x" * 100, "chars": 100, "truncated": False, "dropped_chars": 0,
            "redactions": 0, "redaction_kinds": []}
    base.update(kw)
    return base


class ObservationEvidenceIsNotALeg(unittest.TestCase):
    """The honesty line of Layer 4. A reviewer must be able to see from the SHAPE that this fold
    cannot make an execution claim."""

    def test_the_fold_carries_no_leg_field_at_all(self) -> None:
        fold = observation_evidence([observation("pane-1")])
        self.assertNotIn("legs", fold)
        self.assertNotIn("leg", fold)
        self.assertNotIn("executed", fold)

    def test_the_note_states_what_an_observation_is_not(self) -> None:
        fold = observation_evidence([observation("pane-1")])
        self.assertIn("NOT a claim", fold["note"])
        self.assertIn("net, not a proof", fold["note"])

    def test_a_drifted_producer_is_REFUSED_not_best_effort_parsed(self) -> None:
        """Half-understood text reaching a conductor is worse than no observation, which this
        fold can express honestly."""
        fold = observation_evidence([
            observation("pane-1"),
            {"schema": "pane_observation@2.0", "pane_id": "pane-2", "answerable": True},
            {"text": "no schema at all"},
        ])
        self.assertEqual(fold["panes_observed"], 1)
        self.assertEqual(len(fold["refused"]), 2)
        self.assertEqual(fold["refused"][0]["schema"], "pane_observation@2.0")

    def test_an_unanswerable_pane_is_reported_with_its_reason(self) -> None:
        fold = observation_evidence([
            observation("pane-1"),
            observation("pane-2", answerable=False, reason="the pane holds no readable stream buffer"),
        ])
        self.assertEqual(fold["panes_observed"], 1)
        self.assertEqual(fold["unanswerable"][0]["pane_id"], "pane-2")
        self.assertIn("no readable stream buffer", fold["unanswerable"][0]["reason"])

    def test_an_overrun_is_REPORTED_never_silently_corrected(self) -> None:
        """A conductor whose window did not fit is reasoning from a truncated screen. That has to
        be visible on the receipt."""
        budget = observation_budget(num_ctx=8_192)
        fold = observation_evidence(
            [observation("pane-1", chars=budget["total_max_chars"] + 1)], budget)
        self.assertFalse(fold["within_budget"])
        self.assertGreater(fold["total_chars"], fold["budget_chars"])

    def test_it_reports_what_redaction_removed_and_claims_nothing_more(self) -> None:
        fold = observation_evidence([
            observation("pane-1", redactions=2, redaction_kinds=["api_key"]),
            observation("pane-2", redactions=1, redaction_kinds=["private_key", "api_key"]),
        ])
        self.assertEqual(fold["redactions"], 3)
        self.assertEqual(fold["redaction_kinds"], ["api_key", "private_key"])

    def test_no_observations_folds_to_an_honest_empty_record(self) -> None:
        fold = observation_evidence([])
        self.assertEqual(fold["panes_observed"], 0)
        self.assertEqual(fold["observed"], [])
        self.assertFalse(fold["within_budget"])


if __name__ == "__main__":
    unittest.main()
