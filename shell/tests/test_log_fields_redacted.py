import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, WS)

class TestLogFieldsRedacted(unittest.TestCase):
    def test_new_fields_pass_through_redaction(self):
        from shell.src.logring import LogRing
        r = LogRing()
        r.write(b"hello token=supersecrettokenvalue", runtime="ollama",
                model_id="qwen3:8b", artifact_id="qwen3-8b.gguf",
                request_id="req-1", load_state="RESIDENT", fallback_reason=None)
        out = r.read()
        self.assertIn("runtime=ollama", out)
        self.assertIn("artifact_id=qwen3-8b.gguf", out)
        self.assertNotIn("supersecrettokenvalue", out)
        self.assertIn("[REDACTED]", out)

if __name__ == "__main__":
    unittest.main()
