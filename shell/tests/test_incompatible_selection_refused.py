"""G40: incompatible selection refused before spawn."""
import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestIncompatibleSelectionRefused(unittest.TestCase):
    def test_runtime_name_refused_as_model(self):
        from control_plane.canonical_registry import refuse_incompatible, IncompatibleSelection
        with self.assertRaises(IncompatibleSelection) as cm:
            refuse_incompatible("opencode", "local_model")
        self.assertIn("runtime", str(cm.exception).lower())

    def test_powershell_rejects_model_ref(self):
        from control_plane.canonical_registry import refuse_incompatible, IncompatibleSelection
        with self.assertRaises(IncompatibleSelection):
            refuse_incompatible("qwen3:8b", "powershell")

if __name__ == "__main__":
    unittest.main()
