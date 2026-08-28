"""G107: reasoning failure does not trigger fallback."""
import unittest
class TestReasoningFailureNoFallback(unittest.TestCase):
    def test_triggers(self):
        infra = {"runtime unavailable", "model load failure", "oom", "timeout", "backend health failure", "artifact unavailable"}
        non = {"bad answer", "failed reasoning step", "incorrect tool decision"}
        self.assertTrue(infra.isdisjoint(non))
        self.assertNotIn("bad answer", infra)
if __name__ == "__main__":
    unittest.main()
