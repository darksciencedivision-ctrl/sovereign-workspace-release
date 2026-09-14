"""F-121 marker-root order; F-127 provenance header braces."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "modules" / "sovereign" / "tools"))
sys.path.insert(0, str(REPO / "modules" / "sovereign"))


class MarkerRootOrderTests(unittest.TestCase):
    def test_search_uses_a_sequence_not_a_set(self) -> None:
        import inspect
        import sovereign_paths as sp
        src = inspect.getsource(sp._search_for_marker_root)
        self.assertIn("anchors = (", src)
        self.assertNotIn("anchors = {", src)


class ProvenanceHeaderTests(unittest.TestCase):
    def test_braces_in_topic_do_not_break_header(self) -> None:
        import format_alignmentforum as af
        # A synthetic Windows path with a backslash-U sequence (tests LaTeX-strip safety). Drive Z:
        # is used deliberately: the developer-identifier boundary gate treats a literal user-home
        # path on the C drive as a leaked machine path, and this synthetic fixture must not trip it.
        header = af._provenance_header(
            "sess-1", "Z:\\Users\\x {not-a-field}", {"gate_timestamp": "t",
                                                    "gate_passed": True,
                                                    "synthesis_tag": "tag",
                                                    "seeded_by": []},
            ["tag"], "2026-01-01T00:00:00Z")
        self.assertIn("Z:\\Users\\x {not-a-field}", header)
        self.assertIn("SOVEREIGN v", header)

    def test_windows_path_users_not_stripped_as_latex(self) -> None:
        import format_alignmentforum as af
        out = af._normalize_for_af(r"see Z:\Users\operator\file")
        self.assertIn(r"\Users", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
