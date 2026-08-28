import os, sys, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "modules", "sow"))

class TestPlannerNeverEvictsGenerating(unittest.TestCase):
    def test_no_process_control_in_planner(self):
        from pathlib import Path
        p = Path(WS) / "modules" / "sow" / "scheduler" / "residency_planner" / "residency_planner.py"
        t = p.read_text(encoding="utf-8")
        for w in ("CreateProcess", "TerminateJobObject", "taskkill", "subprocess.Popen", "os.kill"):
            self.assertNotIn(w, t)

if __name__ == "__main__":
    unittest.main()
