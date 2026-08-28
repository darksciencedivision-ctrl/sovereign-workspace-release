"""G82: Ollama unsupported paths return supported:false with a reason."""
import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestOllamaUnsupportedHonest(unittest.TestCase):
    def test_unsupported_have_reason(self):
        from adapters.base.backend import OllamaBackend
        b = OllamaBackend("qwen3:8b")
        for meth in ("load_model", "unload_model", "cancel"):
            r = getattr(b, meth)("x")
            self.assertIs(r.get("supported"), False)
            self.assertTrue(r.get("reason"))

if __name__ == "__main__":
    unittest.main()
