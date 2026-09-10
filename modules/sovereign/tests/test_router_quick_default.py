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


if __name__ == "__main__":
    unittest.main()
