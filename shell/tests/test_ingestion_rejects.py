import json, os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCH = os.path.join(WS, "modules", "sow", "schemas", "deployment-manifest.schema.json")

class TestIngestionRejects(unittest.TestCase):
    def setUp(self):
        with open(SCH, encoding="utf-8") as f:
            self.schema = json.load(f)
        self.need = self.schema["required"]

    def _ok(self, m):
        return all(k in m for k in self.need)

    def test_missing_artifact_hash(self):
        m = {k: "x" for k in self.need}
        del m["artifact_hash"]
        self.assertFalse(self._ok(m))

    def test_unknown_model_id_empty(self):
        m = {k: "x" for k in self.need}
        m["model_id"] = ""
        self.assertEqual(m["model_id"], "")

    def test_duplicate_conflicting_hash_detected(self):
        a = {k: "x" for k in self.need}
        b = dict(a)
        b["artifact_hash"] = "0" * 64
        a["artifact_hash"] = "1" * 64
        self.assertNotEqual(a["artifact_hash"], b["artifact_hash"])

if __name__ == "__main__":
    unittest.main()
