import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestRouterNoUnrequestedTransition(unittest.TestCase):
    def test_llamacpp_backend_contains_no_routing_policy(self):
        from pathlib import Path
        p = Path(WS) / "modules" / "sow" / "adapters" / "local" / "llamacpp.py"
        t = p.read_text(encoding="utf-8")
        self.assertIn("No routing policy", t)
        self.assertNotIn("models-max", t)

if __name__ == "__main__":
    unittest.main()
