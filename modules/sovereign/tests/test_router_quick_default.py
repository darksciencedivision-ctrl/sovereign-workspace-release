"""SWS-BENCH-02: QUICK is the default; DEEP stays an explicit override."""
from __future__ import annotations

import unittest

from sovereign_product.router import Route, route_query


class QuickIsDefault(unittest.TestCase):
    def test_short_request_is_quick(self) -> None:
        decision = route_query("What port does sovereign listen on?")
        self.assertEqual(decision.route, Route.QUICK)

    def test_long_form_without_deep_signal_is_quick(self) -> None:
        query = (
            "Please summarize the documented install steps for a local Windows "
            "host using only the folder distribution and the existing launcher "
            "flags so a first-time operator can start the product from the zip."
        )
        self.assertGreaterEqual(len(query.split()), 30)
        decision = route_query(query)
        self.assertEqual(decision.route, Route.QUICK)

    def test_explicit_deep_override_still_selects_deep(self) -> None:
        decision = route_query("short question", override="DEEP")
        self.assertEqual(decision.route, Route.DEEP)
        self.assertTrue(decision.explicit)


class DeepIsExplicitOnly(unittest.TestCase):
    """R20: the keyword-driven DEEP rule is gone. Analytical phrasing routes to QUICK under AUTO;
    DEEP is reachable only through an explicit override."""

    DEEP_PHRASING = (
        "Explain recursion",
        "analyze the trade-offs between the two designs",
        "compare Postgres and SQLite for this workload",
        "why does the launcher fail on a read-only install",
        "evaluate the architecture and critique the strategy",
        "walk me through the root cause step by step",
    )

    def test_analytical_phrasing_is_quick_under_auto(self) -> None:
        for query in self.DEEP_PHRASING:
            self.assertEqual(route_query(query).route, Route.QUICK, query)

    def test_deep_is_still_reachable_by_explicit_override(self) -> None:
        self.assertEqual(route_query("Explain recursion", override="DEEP").route, Route.DEEP)

    def test_deep_is_reachable_by_inline_override(self) -> None:
        decision = route_query("route: DEEP compare these two options")
        self.assertEqual(decision.route, Route.DEEP)
        self.assertTrue(decision.explicit)


class ResearchIsExplicitOnly(unittest.TestCase):
    """F-116: RESEARCH is opt-in. Ordinary requests that merely mention sources/search/latest do
    not enter a multi-minute research run under AUTO; RESEARCH is explicit-only."""

    RESEARCH_PHRASING = (
        "cite sources for the claim that WAL improves write throughput",
        "search the web for the current price",
        "find the latest research on this",
        "look it up and give me citations",
        "what does the literature say about it",
    )

    def test_research_phrasing_is_quick_under_auto(self) -> None:
        for query in self.RESEARCH_PHRASING:
            self.assertEqual(route_query(query).route, Route.QUICK, query)

    def test_research_is_still_reachable_by_explicit_override(self) -> None:
        self.assertEqual(
            route_query("cite sources for X", override="RESEARCH").route, Route.RESEARCH)


if __name__ == "__main__":
    unittest.main()
