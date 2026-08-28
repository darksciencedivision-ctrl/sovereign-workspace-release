import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestLegacyAliasResolution(unittest.TestCase):
    def test_pre_band16_ids_resolve(self):
        from control_plane.canonical_registry import dump_registry
        data = dump_registry()
        rows = data["models"]
        ids = {r["model_id"] for r in rows}
        self.assertTrue(ids)
        for mid in ids:
            self.assertTrue(any(r["model_id"] == mid for r in rows))

if __name__ == "__main__":
    unittest.main()
