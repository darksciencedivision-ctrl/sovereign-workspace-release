"""F-108 / F-114 — QUICK and DEEP have product-appropriate time budgets, not 24 hours.

OLLAMA_GENERATION_TIMEOUT_SECONDS (86400) was the QUICK overall timeout, and deep_timeout defaulted
to None -- so DEEP had no overall bound and a 24h-per-call ceiling. With one worker, a single hung
Ollama call blocked the product for up to a day. With R22 enforcing an absolute per-call deadline,
the route budgets are now the actual ceilings.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER,
    ROOT_MARKER_CONTENT,
    resolve_product_paths,
)
from sovereign_product import server as server_mod  # noqa: E402
from sovereign_product.server import (  # noqa: E402
    DEEP_OVERALL_TIMEOUT_SECONDS,
    DEEP_PER_CALL_TIMEOUT_SECONDS,
    QUICK_TIMEOUT_SECONDS,
    ProductService,
)


class RouteBudgetsAreProductScale(unittest.TestCase):
    def test_constants_are_minutes_not_a_day(self) -> None:
        for name, value in (("QUICK", QUICK_TIMEOUT_SECONDS),
                            ("DEEP per-call", DEEP_PER_CALL_TIMEOUT_SECONDS),
                            ("DEEP overall", DEEP_OVERALL_TIMEOUT_SECONDS)):
            self.assertGreater(value, 0, name)
            self.assertLessEqual(value, 3600.0, f"{name} budget is larger than an hour")
        # A day is off the table entirely.
        self.assertLess(max(QUICK_TIMEOUT_SECONDS, DEEP_OVERALL_TIMEOUT_SECONDS), 86_400.0)

    def test_service_defaults_use_the_bounded_budgets(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="f108-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        root = tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        shutil.copyfile(MODULE_ROOT / "SYSTEM_MANIFEST.json", root / "SYSTEM_MANIFEST.json")
        state = tmp / "state"
        paths = resolve_product_paths(root, state_dir=state, approved_roots=(state,), create=True)
        service = ProductService(
            paths=paths, model_client=object(), quick_executor=object(),
            deep_executor=object(), research_executor=object(), evidence_builder=object(),
            start_workers=False)
        self.assertEqual(service.quick_timeout, QUICK_TIMEOUT_SECONDS)
        self.assertEqual(service.deep_timeout, DEEP_OVERALL_TIMEOUT_SECONDS)
        self.assertIsNotNone(service.deep_timeout, "DEEP must have an overall bound (F-114)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
