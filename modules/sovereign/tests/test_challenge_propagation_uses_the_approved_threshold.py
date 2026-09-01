"""F-1 — the propagation gate honours the manifest, not a hardcoded floor.

WHY THIS TEST EXISTS. `docs/audit/SYSTEM-REVIEW-20260831.md` F-1 records that
`synthesis/live_orchestrator.py` (2,906 lines) had behaviour changed during this programme with
no test covering it, in a module measuring 284 lines of test against 37,256 lines of source. This
is that coverage, scoped to the change rather than to the module - a coverage campaign was
explicitly not what was asked for.

THE DEFECT THIS PINS. `_build_non_cosmetic_challenge_result` resolved its propagation threshold as
`max(threshold_answer, 0.9)`. The manifest's approved value is `CHALLENGE_ANSWER_COSINE = 0.6`, so
the floor silently overrode an operator-approved threshold by 0.3. Measured consequence
(BOOT_PROOF_02): challenges genuinely incorporated by the king at cosine 0.706-0.784 with
`meaningful_change=true` were scored "not propagated", and the run was rejected as an
imperfect synthesis.

The floor is gone. These tests fail if it comes back, and they fail from the OUTSIDE - by feeding
a cosine the approved threshold admits and the old floor did not - rather than by reading the
source for a forbidden string.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from claim_arbitrator import challenge_answered_by  # noqa: E402
from semantic_claim_matching import load_semantic_matching_config  # noqa: E402

#: Read from the shipped manifest FILE rather than through `load_system_manifest`, which resolves a
#: runtime INSTALL root (it requires `sandbox_agi/` and `URI/` to exist) and cannot run against the
#: source tree. The bytes are the same bytes; only the resolver is skipped.
MANIFEST = json.loads((MODULE_ROOT / "SYSTEM_MANIFEST.json").read_text(encoding="utf-8-sig"))

#: The measured BOOT_PROOF_02 band: real challenges the king had genuinely incorporated.
BOOT_PROOF_02_COSINES = (0.706, 0.784)


class Embedding:
    def __init__(self, vector) -> None:
        self.ok, self.vector, self.model = True, vector, "fake-embed"
        self.error_code = self.error_message = ""


class CosineClient:
    """Returns two unit vectors separated by exactly the angle that yields `cosine`.

    Controlling the SIMILARITY rather than stubbing the decision is what makes this a test of the
    threshold comparison. A stub of `challenge_answered_by` would prove nothing about it.
    """

    def __init__(self, cosine: float) -> None:
        self._cosine = cosine
        self._first = True

    def embed(self, _text):
        if self._first:
            self._first = False
            return Embedding([1.0, 0.0])
        theta = math.acos(max(-1.0, min(1.0, self._cosine)))
        return Embedding([math.cos(theta), math.sin(theta)])


def manifest_with(threshold: float) -> dict:
    """The real manifest with ONE threshold overridden, so nothing else drifts out from under the
    assertion."""
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["THRESHOLDS"] = {**manifest["THRESHOLDS"], "CHALLENGE_ANSWER_COSINE": threshold}
    return manifest


#: Deliberately share no meaningful tokens. `challenge_answered_by` falls through to token-overlap
#: when the cosine gate does not fire, and text with shared vocabulary would be answered by that
#: second path - which would make every assertion below pass for the wrong reason.
CHALLENGE = "Quantify the residency headroom before scheduling another resident model."
CANDIDATE = "Bibliographic citation practices vary widely across humanities disciplines."


class TheApprovedThresholdGovernsPropagation(unittest.TestCase):

    def test_the_manifest_still_approves_0_6(self) -> None:
        """If the operator moves this value, the tests below move with it rather than pinning a
        number he changed."""
        config = load_semantic_matching_config(manifest=MANIFEST)
        self.assertAlmostEqual(config["threshold_answer"], 0.6, places=6)

    def test_the_BOOT_PROOF_02_band_is_detected_as_answered(self) -> None:
        """The regression, stated as behaviour. At the approved 0.6 these are answered; under the
        removed `max(..., 0.9)` floor every one of them was not."""
        for cosine in BOOT_PROOF_02_COSINES:
            with self.subTest(cosine=cosine):
                self.assertTrue(
                    challenge_answered_by(CHALLENGE, CANDIDATE,
                                          embedding_client=CosineClient(cosine),
                                          manifest=manifest_with(0.6), root=None),
                    f"cosine {cosine} is above the approved 0.6 and must count as answered; a "
                    f"0.9 floor has been reinstated somewhere")

    def test_a_cosine_below_the_approved_threshold_is_not_answered(self) -> None:
        """The other direction, so the tests above cannot be satisfied by a gate that says yes to
        everything."""
        self.assertFalse(
            challenge_answered_by(CHALLENGE, CANDIDATE,
                                  embedding_client=CosineClient(0.55),
                                  manifest=manifest_with(0.6), root=None))

    def test_the_MANIFEST_governs_the_gate_not_a_constant(self) -> None:
        """Raise the approved threshold above the sample and the same cosine must stop answering.
        A hardcoded comparison of any value passes the two tests above and fails this one."""
        self.assertFalse(
            challenge_answered_by(CHALLENGE, CANDIDATE,
                                  embedding_client=CosineClient(0.706),
                                  manifest=manifest_with(0.95), root=None),
            "the gate ignored a manifest threshold of 0.95, so it is not reading the manifest")

    def test_lowering_the_threshold_admits_more(self) -> None:
        self.assertTrue(
            challenge_answered_by(CHALLENGE, CANDIDATE,
                                  embedding_client=CosineClient(0.42),
                                  manifest=manifest_with(0.40), root=None))


class TheStructuralVarianceGateIsNotTouched(unittest.TestCase):
    """The recalibration was scoped to propagation detection. G-SV 0.90 is a different gate and
    the change must not have moved it - a fix that quietly widened a second threshold would be the
    more expensive version of the bug it repaired."""

    def test_the_claim_thresholds_are_unchanged_by_the_propagation_fix(self) -> None:
        config = load_semantic_matching_config(manifest=MANIFEST)
        self.assertAlmostEqual(config["threshold_agree"], 0.65, places=6)
        self.assertAlmostEqual(config["threshold_variance_low"], 0.45, places=6)

    def test_the_propagation_threshold_is_read_from_its_OWN_key(self) -> None:
        """`CHALLENGE_ANSWER_COSINE`, not one of the claim keys. Reading the wrong key would give a
        plausible number and silently couple two independent gates."""
        manifest = json.loads(json.dumps(MANIFEST))
        manifest["THRESHOLDS"] = {**manifest["THRESHOLDS"],
                                  "CHALLENGE_ANSWER_COSINE": 0.99,
                                  "CLAIM_AGREE_COSINE": 0.10,
                                  "CLAIM_VARIANCE_COSINE": 0.10}
        self.assertFalse(
            challenge_answered_by(CHALLENGE, CANDIDATE,
                                  embedding_client=CosineClient(0.80),
                                  manifest=manifest, root=None),
            "a cosine of 0.80 answered under CHALLENGE_ANSWER_COSINE=0.99 — the gate is reading "
            "some other threshold")


class TheGateFailsClosedOnUnusableInput(unittest.TestCase):

    def test_an_embedding_failure_does_not_become_a_silent_yes(self) -> None:
        class Broken:
            def embed(self, _t):
                e = Embedding([1.0, 0.0]); e.ok = False; e.error_code = "EMBED_FAILED"; return e

        self.assertFalse(
            challenge_answered_by(CHALLENGE, CANDIDATE, embedding_client=Broken(),
                                  manifest=manifest_with(0.6), root=None))

    def test_empty_text_is_not_answered(self) -> None:
        for challenge, candidate in (("", CANDIDATE), (CHALLENGE, ""), ("", "")):
            self.assertFalse(
                challenge_answered_by(challenge, candidate,
                                      embedding_client=CosineClient(0.99),
                                      manifest=manifest_with(0.6), root=None))


if __name__ == "__main__":
    unittest.main()


class TheFallbackCosineCheckAtTheChangedLine(unittest.TestCase):
    """The line the floor was actually ON.

    `_build_non_cosmetic_challenge_result` has TWO paths to "propagated": `challenge_answered_by`,
    covered above, and — when that returns False — a direct cosine comparison against
    `answer_threshold`. `max(threshold_answer, 0.9)` wrapped the SECOND one, so the tests above
    would have passed with the defect still in place. This class drives the fallback.

    Collaborators are patched, not the decision: the parser and the comparison gate are stubbed so
    the assertion is about the threshold comparison and nothing else. Note that
    `_compare_reasoning_outputs` legitimately keeps its own `max(..., 0.97)` / `max(..., 0.985)`
    floors — those are a different gate and the recalibration did not touch them, which is why
    these tests assert behaviour rather than the absence of `max(` in the file.
    """

    def setUp(self) -> None:
        from synthesis import live_orchestrator as lo
        self.lo = lo
        self._saved = {name: getattr(lo, name) for name in
                       ("_compare_reasoning_outputs", "_extract_bundle",
                        "challenge_answered_by", "compute_semantic_similarity")}
        lo._compare_reasoning_outputs = lambda *a, **k: {"meaningful_change": True}
        lo._extract_bundle = lambda _t: {"claim": "", "challenge": "", "evidence": "",
                                         "uncertainty": "", "final": "a synthesis paragraph"}
        # Force the fallback: the first path must not be what answers.
        lo.challenge_answered_by = lambda *a, **k: False

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            setattr(self.lo, name, value)

    def _run(self, cosine: float, threshold: float) -> dict:
        self.lo.compute_semantic_similarity = lambda *a, **k: {"cosine": cosine}
        return self.lo._build_non_cosmetic_challenge_result(
            actual_king="king", challenge_removed_king="king-without",
            challenge_texts=["the residency headroom is not quantified"],
            manifest=manifest_with(threshold), root=MODULE_ROOT)

    def test_the_BOOT_PROOF_02_band_propagates_through_the_FALLBACK(self) -> None:
        """0.706 and 0.784 against the approved 0.6. Under `max(..., 0.9)` both scored
        `propagated_to_synthesis: false` and the run was rejected as an imperfect synthesis."""
        for cosine in BOOT_PROOF_02_COSINES:
            with self.subTest(cosine=cosine):
                result = self._run(cosine, 0.6)
                self.assertEqual(result["propagated_count"], 1,
                                 f"cosine {cosine} did not propagate at the approved 0.6 — the "
                                 f"0.9 floor is back on the fallback comparison")
                self.assertTrue(result["passed"])

    def test_a_cosine_below_the_threshold_does_not_propagate(self) -> None:
        result = self._run(0.55, 0.6)
        self.assertEqual(result["propagated_count"], 0)
        self.assertFalse(result["passed"])

    def test_the_fallback_reads_the_MANIFEST_not_a_constant(self) -> None:
        self.assertEqual(self._run(0.706, 0.95)["propagated_count"], 0)
        self.assertEqual(self._run(0.706, 0.60)["propagated_count"], 1)

    def test_a_missing_cosine_does_not_propagate(self) -> None:
        """An embedding failure must not read as a propagated challenge."""
        self.lo.compute_semantic_similarity = lambda *a, **k: {"cosine": None}
        result = self.lo._build_non_cosmetic_challenge_result(
            actual_king="king", challenge_removed_king="king-without",
            challenge_texts=["a challenge"], manifest=manifest_with(0.6), root=MODULE_ROOT)
        self.assertEqual(result["propagated_count"], 0)

    def test_propagation_alone_does_not_pass_without_a_meaningful_change(self) -> None:
        """`passed` is the AND of both conditions. Loosening the threshold must not be able to
        pass a run whose king did not actually change."""
        self.lo._compare_reasoning_outputs = lambda *a, **k: {"meaningful_change": False}
        result = self._run(0.99, 0.6)
        self.assertEqual(result["propagated_count"], 1)
        self.assertFalse(result["passed"])
