"""R19 — the router must not corrupt the execution payload.

route_query used to set normalized_query to `" ".join(query.split())`, collapsing every run of
whitespace -- including the newlines and indentation of a multiline program -- and that collapsed
string became the durable job input and what the executor ran. A submitted program therefore
reached the executor with its structure destroyed.

The matching text (used only to test routing rules) may still be collapsed, but the payload the
decision carries must preserve the request byte-for-byte, minus only a parsed inline route prefix.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.router import Route, route_query  # noqa: E402

PROGRAM = (
    "def solve(n):\n"
    "    total = 0\n"
    "    for i in range(n):\n"
    "        total += i * 2\n"
    "\n"
    "    return total\n"
)


class PayloadIsPreservedByteForByte(unittest.TestCase):
    def test_a_multiline_program_survives_routing_intact(self) -> None:
        decision = route_query(PROGRAM)
        self.assertEqual(decision.normalized_query, PROGRAM,
                         "the multiline payload must be preserved byte-for-byte")
        self.assertEqual(decision.route, Route.QUICK)  # no AUTO deep/research triggering

    def test_internal_newlines_and_indentation_are_not_collapsed(self) -> None:
        decision = route_query(PROGRAM)
        self.assertIn("\n    total = 0\n", decision.normalized_query)
        self.assertEqual(decision.normalized_query.count("\n"), PROGRAM.count("\n"))

    def test_double_spaces_are_preserved(self) -> None:
        text = "keep  the  double  spaces"
        self.assertEqual(route_query(text).normalized_query, text)

    def test_an_explicit_override_still_carries_the_raw_payload(self) -> None:
        decision = route_query(PROGRAM, override="DEEP")
        self.assertEqual(decision.normalized_query, PROGRAM)
        self.assertEqual(decision.route, Route.DEEP)

    def test_an_inline_override_strips_only_the_prefix_and_keeps_the_remainder(self) -> None:
        decision = route_query("route: QUICK " + PROGRAM)
        self.assertEqual(decision.route, Route.QUICK)
        self.assertTrue(decision.explicit)
        # The route prefix is gone; the program body keeps its exact bytes.
        self.assertEqual(decision.normalized_query, PROGRAM)


if __name__ == "__main__":
    unittest.main(verbosity=2)
