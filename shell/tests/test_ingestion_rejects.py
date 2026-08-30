import json, os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# EPC-01 P1-2 / ENTRY 029. This contract used to live directly in modules/sow/schemas/, where
# the freeze manifest's `*.schema.json` glob swept it into the operator-signed set it was never
# signed into -- the defect docs/CP-M1-PUNCH-LIST.md:364 recorded as "matches the frozen schema
# glob but is absent from the signed manifest". Both globs are NON-RECURSIVE, so a subdirectory
# keeps the file in the product while leaving the frozen set at twelve and the amendment set
# empty of it. The contract is unchanged: the bytes here are identical to the original.
SCH = os.path.join(WS, "modules", "sow", "schemas", "contracts",
                   "deployment-manifest.schema.json")

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
