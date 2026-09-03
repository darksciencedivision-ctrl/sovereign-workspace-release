"""The stated ceiling and the enforced ceiling are ONE number, and it can be set.

Two defects lived here, both measured on the operator's host before the fix:

  * `CEILING_NAMEPLATE_B` was derived from VRAM (11 on this card) while admission compared
    against a hardcoded `_TRUE_PARAM_LIMIT = 9.0e9`. Nothing kept them in agreement, so
    `ornith-1.5:9b` was refused with the sentence "has 9.0B parameters, above the operator's
    11B ceiling" — a refusal quoting a threshold that was not the one applied. The same split
    reached evidence: `enumerate_pane_picker` recorded `nameplate_b: 11` under
    `authority: ENTRY 017`, attributing to that ruling a figure it does not contain.

  * The ceiling could not be SET. `SOVEREIGN_VRAM_MIB=2800` moved the displayed nameplate to 4
    and changed admission not at all — seven 8B-class models stayed admitted under a reported
    4B ceiling. An operator asking for a run at or under 4B could not get one.

These tests are the record of both. `TheCeilingIsSettable` is the one that would have caught
the second defect: it asserts on the ADMITTED SET, not on the number the module reports, because
reporting the right number while admitting the wrong models is precisely what happened.
"""
from __future__ import annotations

import importlib
import os
import re
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


class _CeilingEnv(unittest.TestCase):
    """Reload the module under a chosen ceiling, and always put the environment back.

    The constants are import-time by design (the UI path reads them as plain names), so a test
    that changes the ceiling has to reload. Restoring in `tearDown` AND reloading again keeps a
    neighbouring file from inheriting a narrowed slate — the leak `test_local_model_ceiling`'s
    own teardown warns about.
    """

    def setUp(self) -> None:
        self._saved = os.environ.get(mc.CEILING_ENV)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(mc.CEILING_ENV, None)
        else:
            os.environ[mc.CEILING_ENV] = self._saved
        importlib.reload(mc)

    def _reload_with_ceiling(self, nameplate_b: str | None):
        if nameplate_b is None:
            os.environ.pop(mc.CEILING_ENV, None)
        else:
            os.environ[mc.CEILING_ENV] = nameplate_b
        return importlib.reload(mc)


class TheStatedCeilingIsTheEnforcedCeiling(_CeilingEnv):

    def test_the_refusal_quotes_the_threshold_it_actually_applied(self) -> None:
        """The defect in one assertion: a model refused for being over the ceiling must not be
        told it is above a number it is below."""
        m = self._reload_with_ceiling(None)
        v = m.classify_local_model(record("ornith-1.5:9b", "9.0B"), m.AUDIENCE_TESTING)
        self.assertFalse(v.admitted)
        quoted = [int(n) for n in re.findall(r"(\d+)B ceiling", v.reason)]
        self.assertTrue(quoted, f"the refusal names no ceiling at all:\n{v.reason}")
        for n in quoted:
            self.assertGreaterEqual(
                (v.parameters or 0), n * 1e9,
                f"refused a {v.parameter_size} model for being above a {n}B ceiling it is "
                f"UNDER — the sentence states a threshold that is not the one enforced:\n"
                f"{v.reason}")

    def test_the_two_constants_cannot_drift_apart(self) -> None:
        m = self._reload_with_ceiling(None)
        self.assertEqual(m._TRUE_PARAM_LIMIT, (m.CEILING_NAMEPLATE_B + 1.0) * 1e9,
                         "the enforced bound is no longer derived from the quoted nameplate")

    def test_the_default_is_entry_017s_eight_not_the_cards_capacity(self) -> None:
        """ENTRY 017 says eight billion. The card says 11.6B. The RULE is the ruling's number;
        the card's number is an advisory and belongs in `hardware_profile`."""
        m = self._reload_with_ceiling(None)
        self.assertEqual(m.CEILING_NAMEPLATE_B, 8)
        self.assertEqual(m._TRUE_PARAM_LIMIT, 9.0e9)


class TheEightBClassStillBehavesExactlyAsBefore(_CeilingEnv):
    """The fix must not move the boundary it was not asked to move."""

    def test_the_8b_nameplate_class_is_still_admitted(self) -> None:
        m = self._reload_with_ceiling(None)
        for name, params in (("qwen3:8b", "8.2B"), ("granite4.2:8b", "8.8B"),
                             ("dolphin3:8b", "8.0B")):
            with self.subTest(model=name):
                v = m.classify_local_model(record(name, params), m.AUDIENCE_TESTING)
                self.assertTrue(v.admitted, v.reason)

    def test_the_9b_class_is_still_refused(self) -> None:
        m = self._reload_with_ceiling(None)
        v = m.classify_local_model(record("ornith:9b", "9.0B"), m.AUDIENCE_TESTING)
        self.assertFalse(v.admitted)


class TheCeilingIsSettable(_CeilingEnv):
    """The test that would have caught the second defect — it asserts on the admitted SET."""

    #: One per nameplate class present in the operator's library around the boundary.
    LIBRARY = [
        record("qwen2.5:3b-instruct", "3.1B"),
        record("granite4.2:3b", "3.7B"),
        record("phi4-mini:3.8b", "3.8B"),
        record("dolphin3:8b", "8.0B"),
        record("qwen3:8b", "8.2B"),
        record("granite4.2:8b", "8.8B"),
        record("deepseek-r1:14b", "14.8B"),
    ]

    def test_a_4b_ceiling_actually_caps_the_slate_at_4b(self) -> None:
        m = self._reload_with_ceiling("4")
        verdicts = m.classify_local_models(self.LIBRARY, m.AUDIENCE_TESTING)
        admitted = [v for v in verdicts if v.admitted]
        over = [f"{v.name} ({v.parameter_size})" for v in admitted
                if (v.parameters or 0) >= 5.0e9]
        self.assertEqual(over, [], f"a 4B ceiling admitted models above the 4B class: {over}")
        self.assertEqual(
            sorted(v.name for v in admitted),
            ["granite4.2:3b", "phi4-mini:3.8b", "qwen2.5:3b-instruct"],
            "the 4B class itself must survive its own ceiling")

    def test_the_ceiling_the_operator_sets_is_the_one_reported(self) -> None:
        m = self._reload_with_ceiling("4")
        self.assertEqual(m.CEILING_NAMEPLATE_B, 4)
        v = m.classify_local_model(record("qwen3:8b", "8.2B"), m.AUDIENCE_TESTING)
        self.assertIn("4B ceiling", v.reason)

    def test_an_unreadable_setting_falls_back_rather_than_raising(self) -> None:
        """A typo must not take down a display path, and must not silently widen the slate."""
        # `inf` and `nan` are the ones worth naming: both PARSE as floats, and `int(inf)` raises
        # OverflowError rather than ValueError, so a handler catching only ValueError lets it
        # escape onto the display path.
        for bad in ("", "   ", "eight", "-3", "0", "inf", "-inf", "nan", "1e400"):
            with self.subTest(value=bad):
                m = self._reload_with_ceiling(bad)
                self.assertEqual(m.CEILING_NAMEPLATE_B, 8)


class TheOperatorIsNotToldAboutARuleThatDoesNotBindHim(_CeilingEnv):

    def test_the_advisory_names_hardware_and_no_ceiling(self) -> None:
        """EPC-02/ENTRY 030: for the operator there is no ceiling, only a measured cost. An
        advisory asserting "the operator's NB ceiling" was claiming a rule over the person the
        ruling exempted."""
        m = self._reload_with_ceiling(None)
        v = m.classify_local_model(record("deepseek-r1:70b", "70.6B", size_bytes=42_000_000_000),
                                   m.AUDIENCE_OPERATOR)
        self.assertTrue(v.admitted, v.reason)
        self.assertIn("VRAM", v.advisory)
        self.assertNotIn("ceiling", v.advisory.lower(),
                         "the operator advisory asserts a rule that does not bind him")
        self.assertNotIn("ENTRY 017", v.advisory)
