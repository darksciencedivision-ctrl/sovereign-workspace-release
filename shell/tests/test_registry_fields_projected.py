"""G28: worker registry projection includes created_utc and backend."""
import os, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(WS, "modules", "sow", "apps", "desktop", "control", "operational-state.js")

class TestRegistryFieldsProjected(unittest.TestCase):
    def test_created_utc_and_backend_projected(self):
        with open(SRC, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("created_utc:", t)
        self.assertIn("backend:", t)
        self.assertIn("record.startedAt", t)

if __name__ == "__main__":
    unittest.main()
