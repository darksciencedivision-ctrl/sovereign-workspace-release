"""EPC-02 B-2/B-3 — the ceiling serves two audiences, and one refusal is not one of them.

The 8B ceiling (ENTRY 017) was implemented as a GLOBAL refusal. Its reason is hardware and is
true: this host has 8 GB of VRAM and a larger model straddles it. But a refusal is not the
only way to tell someone that. Implemented globally, it locked the operator out of 52 of his
own 60 installed models, and his ruling (ENTRY 030) is that the ceiling binds automated
testing, not him.

So the same authority now answers two audiences: OPERATOR admits an over-ceiling model with an
advisory naming the cost; TESTING refuses it exactly as before.

**The dangerous direction is widening.** The same authority also refuses two entries that look
local and execute REMOTELY — `glm-5.2:cloud`, `deepseek-v4-pro:cloud`, a few hundred bytes on
disk apiece. Selecting one leaves the host, which is provider spend, which is a mandatory STOP.
The only thing standing between the operator's library and a billable call is that the cloud
check is INDEPENDENT of the parameter check.

That independence is proven here by mutation rather than trusted because it was read once:
the ceiling is pushed wide enough to admit a 1.65-trillion-parameter model, and the cloud
pointers must still be refused.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.local import model_ceiling as mc  # noqa: E402


def record(name: str, params: str, size_bytes: int = 5_000_000_000,
           caps: tuple[str, ...] = ("completion",)) -> dict:
    return {
        "name": name, "size": size_bytes,
        "details": {"parameter_size": params, "family": "test", "quantization_level": "Q4"},
        "capabilities": list(caps),
    }


SMALL = record("small:8b", "8.0B")
LARGE = record("large:70b", "70.6B", size_bytes=42_000_000_000)
HUGE = record("huge:1.65t", "1.65T", size_bytes=90_000_000_000)
CLOUD = record("remote:cloud", "1.65T", size_bytes=323)
EMBED = record("embed:latest", "137M", size_bytes=300_000_000, caps=("embedding",))


class AudienceResolution(unittest.TestCase):

    def setUp(self) -> None:
        self._saved = os.environ.get(mc.AUDIENCE_ENV)
        os.environ.pop(mc.AUDIENCE_ENV, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(mc.AUDIENCE_ENV, None)
        else:
            os.environ[mc.AUDIENCE_ENV] = self._saved

    def test_the_default_serves_the_operator(self) -> None:
        """A fresh install serves the person who owns the machine. A test harness must opt IN
        to the stricter rule rather than depend on a default it might not get."""
        self.assertEqual(mc.resolve_audience(), mc.AUDIENCE_OPERATOR)

    def test_the_environment_selects_testing(self) -> None:
        os.environ[mc.AUDIENCE_ENV] = mc.AUDIENCE_TESTING
        self.assertEqual(mc.resolve_audience(), mc.AUDIENCE_TESTING)

    def test_an_explicit_argument_beats_the_environment(self) -> None:
        os.environ[mc.AUDIENCE_ENV] = mc.AUDIENCE_TESTING
        self.assertEqual(mc.resolve_audience(mc.AUDIENCE_OPERATOR), mc.AUDIENCE_OPERATOR)

    def test_an_unrecognised_value_falls_back_to_operator_rather_than_failing(self) -> None:
        """A typo in an environment variable must not silently narrow what the operator can
        reach, and must not raise on his display path either."""
        os.environ[mc.AUDIENCE_ENV] = "prodcution"
        self.assertEqual(mc.resolve_audience(), mc.AUDIENCE_OPERATOR)


class TheCeilingRefusesOnlyForTesting(unittest.TestCase):

    def test_testing_still_refuses_an_over_ceiling_model(self) -> None:
        v = mc.classify_local_model(LARGE, mc.AUDIENCE_TESTING)
        self.assertFalse(v.admitted)
        self.assertIn("70.6B", v.reason)

    def test_the_operator_gets_the_model_and_the_caveat(self) -> None:
        v = mc.classify_local_model(LARGE, mc.AUDIENCE_OPERATOR)
        self.assertTrue(v.admitted, v.reason)
        self.assertEqual(v.reason, "", "an admitted model must carry no refusal sentence")
        self.assertIn("VRAM", v.advisory)
        self.assertIn("slow", v.advisory)

    def test_a_within_ceiling_model_is_admitted_for_both_and_warns_neither(self) -> None:
        for audience in (mc.AUDIENCE_OPERATOR, mc.AUDIENCE_TESTING):
            v = mc.classify_local_model(SMALL, audience)
            self.assertTrue(v.admitted, f"{audience}: {v.reason}")
            self.assertEqual(v.advisory, "", f"{audience} got a caveat it does not need")

    def test_reasons_and_advisories_are_disjoint(self) -> None:
        """A selector greys with one map and annotates with the other. If a model could appear
        in both, 'refused' and 'offered with a warning' would collapse into one state."""
        verdicts = mc.classify_local_models([SMALL, LARGE, HUGE, CLOUD, EMBED],
                                            mc.AUDIENCE_OPERATOR)
        reasons = set(mc.reasons_by_name(verdicts))
        advisories = set(mc.advisories_by_name(verdicts))
        self.assertEqual(reasons & advisories, set())


class TheCloudRefusalSurvivesAnyCeiling(unittest.TestCase):
    """B-3. The mutation proof. Widening is the expensive direction to be wrong in."""

    def test_a_cloud_pointer_is_refused_for_both_audiences(self) -> None:
        for audience in (mc.AUDIENCE_OPERATOR, mc.AUDIENCE_TESTING):
            v = mc.classify_local_model(CLOUD, audience)
            self.assertFalse(v.admitted, f"{audience} admitted a cloud pointer")
            self.assertIn("remotely", v.reason)

    def test_a_cloud_pointer_stays_refused_with_the_ceiling_pushed_past_a_trillion(self) -> None:
        """Raise the parameter ceiling high enough to admit the largest thing in the library
        and confirm the cloud entries are STILL refused — proving the two checks are
        independent, rather than inferring it from reading the order once."""
        original = mc._TRUE_PARAM_LIMIT
        try:
            mc._TRUE_PARAM_LIMIT = 1.0e15  # a quadrillion: admits everything by size
            self.assertTrue(
                mc.classify_local_model(HUGE, mc.AUDIENCE_TESTING).admitted,
                "the mutation did not actually widen the ceiling; this test proves nothing"
            )
            for audience in (mc.AUDIENCE_OPERATOR, mc.AUDIENCE_TESTING):
                v = mc.classify_local_model(CLOUD, audience)
                self.assertFalse(
                    v.admitted,
                    f"{audience}: widening the parameter ceiling admitted a REMOTE model — "
                    f"selecting it would leave the host and become provider spend"
                )
        finally:
            mc._TRUE_PARAM_LIMIT = original
        self.assertEqual(mc._TRUE_PARAM_LIMIT, original, "the ceiling was not restored")

    def test_the_other_audience_independent_refusals_hold_too(self) -> None:
        """Non-chat and unreadable-size are refusals about what a model IS, not how big it is,
        so neither may vary by audience."""
        for audience in (mc.AUDIENCE_OPERATOR, mc.AUDIENCE_TESTING):
            self.assertFalse(mc.classify_local_model(EMBED, audience).admitted)
            self.assertFalse(
                mc.classify_local_model(record("mystery:x", "not-a-number"), audience).admitted)


class TheOperatorCanReachHisLibrary(unittest.TestCase):
    """The point of the change, stated as an assertion rather than left implied."""

    def test_the_operator_sees_far_more_than_the_testing_audience(self) -> None:
        library = [SMALL, LARGE, HUGE, CLOUD, EMBED]
        operator = mc.admitted_names(mc.classify_local_models(library, mc.AUDIENCE_OPERATOR))
        testing = mc.admitted_names(mc.classify_local_models(library, mc.AUDIENCE_TESTING))
        self.assertEqual(sorted(operator), ["huge:1.65t", "large:70b", "small:8b"])
        self.assertEqual(testing, ["small:8b"])
        self.assertNotIn("remote:cloud", operator)


if __name__ == "__main__":
    unittest.main()
