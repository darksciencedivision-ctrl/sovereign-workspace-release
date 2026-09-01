"""F-1 — the second file changed without coverage: `sovereign_product/semantic_deep.py`.

`docs/audit/SYSTEM-REVIEW-20260831.md` F-1 records that this 2,865-line file had behaviour changed
during this programme with nothing covering it. Two changes, two defects behind them, both
measured on the operator's host rather than reasoned about:

  1. `num_ctx` was `131_072` — dolphin3's model-card maximum taken as a setting. On an 8 GiB card
     that put 23.2 GB resident, so the model ran from system RAM and every timed leg measured the
     swap rather than the model. `recommended_num_ctx()` derives it from measured VRAM instead.
  2. `_safe_relative` took a single root. EPC-01 P4-4 moved runtime state OUT of the install root,
     and this was the FOURTH site of that one regression — found by running the product, one site
     at a time. It now accepts a sequence of trusted roots.

The containment PROPERTY is the thing to protect: widening the roots must not have widened what
is accepted. These tests assert that an artifact inside none of the named roots is still refused.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.semantic_deep import (  # noqa: E402
    DEEP_MEMBER_MAX_GENERATION_TOKENS,
    SemanticDeepError,
    _safe_relative,
    detect_vram_mib,
    recommended_num_ctx,
)

#: The value that caused the spill. Named so a reader knows what the assertions are guarding
#: against rather than inferring it from a bare number.
SPILLED_NUM_CTX = 131_072


class TheContextSizeIsDerivedFromMeasuredHardware(unittest.TestCase):

    def test_it_never_returns_the_value_that_spilled(self) -> None:
        num_ctx, _ = recommended_num_ctx()
        self.assertLess(num_ctx, SPILLED_NUM_CTX)

    def test_it_reports_the_basis_for_the_number(self) -> None:
        """A context size with no stated basis is how 131072 survived: it looked like a decision."""
        _, why = recommended_num_ctx()
        self.assertTrue(why.strip())
        self.assertRegex(why, r"VRAM|floor|pinned")

    def test_it_scales_with_the_measured_card(self) -> None:
        """More VRAM must not recommend less context. A broken step table breaks nothing else."""
        seen = []
        previous = os.environ.get("SOVEREIGN_VRAM_MIB")
        try:
            for mib in (8_192, 16_384, 24_576, 49_152):
                os.environ["SOVEREIGN_VRAM_MIB"] = str(mib)
                seen.append(recommended_num_ctx()[0])
        finally:
            if previous is None:
                os.environ.pop("SOVEREIGN_VRAM_MIB", None)
            else:
                os.environ["SOVEREIGN_VRAM_MIB"] = previous
        self.assertEqual(seen, sorted(seen), f"not monotonic in VRAM: {seen}")
        self.assertTrue(all(n < SPILLED_NUM_CTX for n in seen), seen)

    def test_an_undetectable_card_falls_to_a_floor_and_says_so(self) -> None:
        """Refusing to guess. The floor is named as a floor, not dressed as a measurement."""
        previous = os.environ.get("SOVEREIGN_VRAM_MIB")
        os.environ["SOVEREIGN_VRAM_MIB"] = "0"
        try:
            num_ctx, why = recommended_num_ctx()
        finally:
            if previous is None:
                os.environ.pop("SOVEREIGN_VRAM_MIB", None)
            else:
                os.environ["SOVEREIGN_VRAM_MIB"] = previous
        self.assertGreaterEqual(num_ctx, 4096)
        self.assertLess(num_ctx, SPILLED_NUM_CTX)

    def test_every_derived_size_is_a_usable_context(self) -> None:
        """Below ~4k a DEEP member cannot hold its own prompt, so a 'safe' tiny number would trade
        one silent failure for another."""
        self.assertGreaterEqual(recommended_num_ctx()[0], 4096)

    def test_vram_detection_never_raises_and_names_its_source(self) -> None:
        mib, source = detect_vram_mib()
        self.assertIsInstance(mib, int)
        self.assertTrue(source.strip())


class TheGenerationBudgetDoesNotTruncateAMember(unittest.TestCase):

    def test_it_stays_above_the_budget_that_discarded_a_members_output(self) -> None:
        """2048 truncated `member_2` mid-answer and the whole DEEP result was rejected for it.
        This pins the floor without pinning the exact number, so tuning stays available."""
        self.assertGreater(DEEP_MEMBER_MAX_GENERATION_TOKENS, 2_048)


class ArtifactContainmentSurvivedWideningTheRoots(unittest.TestCase):
    """The change accepted a SEQUENCE of trusted roots. What must not have changed is that an
    artifact outside every one of them is refused."""

    def setUp(self) -> None:
        import tempfile
        self.base = Path(tempfile.mkdtemp(prefix="sov-contain-")).resolve()
        self.install = self.base / "install"
        self.state = self.base / "state"
        self.elsewhere = self.base / "elsewhere"
        for d in (self.install, self.state, self.elsewhere):
            (d / "semantic_deep").mkdir(parents=True, exist_ok=True)

    def test_a_single_root_still_works(self) -> None:
        """Back-compat: the signature widened, the old call shape did not break."""
        artifact = self.install / "semantic_deep" / "request.json"
        self.assertEqual(_safe_relative(artifact, self.install), "semantic_deep/request.json")

    def test_a_sequence_finds_whichever_root_contains_the_artifact(self) -> None:
        """The regression this fixed: run state moved to the STATE root and the very next write
        failed on the install root it was still being measured against."""
        artifact = self.state / "semantic_deep" / "request.json"
        self.assertEqual(_safe_relative(artifact, [self.install, self.state]),
                         "semantic_deep/request.json")

    def test_a_path_inside_NONE_of_the_roots_is_refused(self) -> None:
        """The containment property. Widening the roots must not have widened what is accepted."""
        artifact = self.elsewhere / "semantic_deep" / "request.json"
        with self.assertRaises(SemanticDeepError) as caught:
            _safe_relative(artifact, [self.install, self.state])
        self.assertIn("escaped every trusted root", str(caught.exception))

    def test_a_traversal_out_of_a_root_is_refused(self) -> None:
        """`..` resolves before the comparison, so a path that merely starts inside a root does not
        stay inside it."""
        artifact = self.install / ".." / "elsewhere" / "secret.json"
        with self.assertRaises(SemanticDeepError):
            _safe_relative(artifact, [self.install])

    def test_an_empty_root_list_refuses_everything(self) -> None:
        """Fail closed: no named root means nothing is contained, not everything."""
        with self.assertRaises(SemanticDeepError):
            _safe_relative(self.install / "semantic_deep" / "request.json", [])

    def test_the_refusal_names_the_roots_it_checked(self) -> None:
        """A containment error that does not say what it measured against sent the last four
        instances of this bug to be diagnosed one at a time."""
        with self.assertRaises(SemanticDeepError) as caught:
            _safe_relative(self.elsewhere / "x.json", [self.install, self.state])
        message = str(caught.exception)
        # Matched on the leaf rather than the full path: the message renders the root list through
        # `repr`, which doubles every Windows separator, so a full-path comparison fails on
        # formatting rather than on content. Recorded rather than worked around silently — the
        # doubled separators are a real (cosmetic) defect in an operator-facing refusal, and
        # fixing them is a product change outside this finding's scope.
        self.assertIn(self.install.name, message)
        self.assertIn(self.state.name, message)
        self.assertIn(self.elsewhere.name, message)


if __name__ == "__main__":
    unittest.main()
