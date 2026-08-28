import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestPromotionAxisOrthogonal(unittest.TestCase):
    def test_axes_are_separate_fields(self):
        from control_plane.canonical_registry import dump_registry
        from pathlib import Path
        row = dump_registry()["models"][0]
        self.assertIn("promotion_state", row)
        t = (Path(WS) / "modules" / "sow" / "scheduler" / "residency_planner" / "residency_planner.py").read_text(encoding="utf-8")
        self.assertIn("RESIDENT", t.upper() or "resident")
        self.assertIn("not_loaded", t.lower())

if __name__ == "__main__":
    unittest.main()
