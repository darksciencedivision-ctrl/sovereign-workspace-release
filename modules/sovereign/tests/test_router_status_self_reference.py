"""R21 / F-103 — STATUS is machine-self-state; topical status/health/version/AGI is not.

The machine_self_state rule matched bare "status", "health", "version", "which models", "AGI" and
so answered "what are the health benefits of green tea?" / "latest version of Python?" / "is AGI
possible?" with SOVEREIGN's own machine status. And CONTINUITY matched a bare "continue", so "why do
prices continue to rise?" routed to continuity recall.

STATUS now requires a reference to THIS assistant/system; ambiguous topical queries fall through to
QUICK. CONTINUITY's verbs count only as the leading imperative of the request.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.router import Route, route_query  # noqa: E402


class TopicalWordsDoNotRouteToStatus(unittest.TestCase):
    TOPICAL = (
        "What are the health benefits of green tea?",
        "What is the status of the Paris agreement?",
        "What is the latest version of Python?",
        "Is AGI possible?",
        "Explain the diagnostic criteria for diabetes",
        "which models of governance exist",
    )

    def test_topical_status_words_route_to_quick(self) -> None:
        for query in self.TOPICAL:
            self.assertEqual(route_query(query).route, Route.QUICK, query)


class SelfReferentialQueriesStillRouteToStatus(unittest.TestCase):
    SELF = (
        "what is your status",
        "who are you",
        "which models do you use",
        "what version are you running",
        "are you sentient",
        "what can you do",
        "is this system operational",
    )

    def test_self_referential_queries_route_to_status(self) -> None:
        for query in self.SELF:
            self.assertEqual(route_query(query).route, Route.STATUS, query)


class ContinuityVerbsAreLeadingImperativesOnly(unittest.TestCase):
    def test_topical_continue_is_not_continuity(self) -> None:
        self.assertEqual(route_query("Why do prices continue to rise?").route, Route.QUICK)
        self.assertEqual(route_query("Does the trend resume after a crash?").route, Route.QUICK)

    def test_leading_continue_is_continuity(self) -> None:
        for query in ("continue the analysis", "please resume where we left off",
                      "keep going from the last step", "as we discussed earlier"):
            self.assertEqual(route_query(query).route, Route.CONTINUITY, query)


if __name__ == "__main__":
    unittest.main(verbosity=2)
