"""P2 SOVEREIGN durability: R28, F-118, F-110.

R28: requeue reset the timestamps but LEFT progress_json, so a retried job's fresh 1% failed the
     no-regression guard and the job sat in `running` with no executor.
F-118: _pid_alive used os.kill(pid, 0), which on Windows is CTRL_C_EVENT (not a liveness test) --
     it returned True after the process was killed, so a crashed run's lock was never reclaimed.
F-110: the assistant's own prior answers were admitted as citeable evidence, so a fabricated answer
     could be cited back to satisfy attribution the next turn.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.store import SovereignStore  # noqa: E402
from sovereign_product.research import _ResearchLock  # noqa: E402
from sovereign_product.evidence import EvidenceBuilder  # noqa: E402


class R28_RequeueResetsProgress(unittest.TestCase):
    def test_a_retried_job_starts_from_clean_progress(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r28-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        store = SovereignStore(tmp / "s.db")
        session = store.create_session(title="New chat")["session_id"]
        job = store.admit_job(session, route="QUICK", input_text="q", user_content="q")["job"]
        jid = job["job_id"]
        store.transition_job(jid, "running", expected_status="queued")
        store.update_job_progress(jid, {"percent": 80, "stage": "generation"})
        store.transition_job(jid, "failed", expected_status="running")
        # Explicit retry: failed -> queued.
        store.transition_job(jid, "queued", expected_status="failed")
        self.assertEqual(store.get_job(jid)["progress"], {}, "requeue must clear attempt progress")
        # The new attempt's fresh 1% must be accepted (no regression against the old 80%).
        store.transition_job(jid, "running", expected_status="queued")
        store.update_job_progress(jid, {"percent": 1, "stage": "running"})
        self.assertEqual(store.get_job(jid)["progress"]["percent"], 1)


class F118_PidLiveness(unittest.TestCase):
    def test_live_process_is_alive(self) -> None:
        self.assertTrue(_ResearchLock._pid_alive(os.getpid()))

    def test_nonexistent_pid_is_not_alive(self) -> None:
        self.assertFalse(_ResearchLock._pid_alive(2_000_000_000))
        self.assertFalse(_ResearchLock._pid_alive(0))

    def test_a_killed_process_is_not_alive(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(_ResearchLock._pid_alive(child.pid))
        finally:
            child.kill()
            child.wait(timeout=5)
        # After the OS has reaped it, liveness is False (not True, as os.kill(pid,0) gave).
        deadline = time.time() + 5
        while time.time() < deadline and _ResearchLock._pid_alive(child.pid):
            time.sleep(0.1)
        self.assertFalse(_ResearchLock._pid_alive(child.pid))


class F110_NoSelfCitation(unittest.TestCase):
    def test_assistant_turns_are_not_offered_as_citeable_sources(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="f110-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        builder = EvidenceBuilder(tmp, approved_paths=(), message_source=None, query_relevance=True)
        messages = [
            {"id": "u1", "role": "user", "content": "which critic model is configured"},
            {"id": "s1", "role": "sovereign", "content": "the critic model is imaginary:999b"},
        ]
        ordered, omissions = builder._ordered_session_messages(
            messages, session_id="sess", query="which critic model is configured")
        source_ids = {sid for sid, _content, _meta in ordered}
        self.assertNotIn("message:s1", source_ids,
                         "an assistant answer must not be a citeable evidence source (F-110)")
        self.assertTrue(any("s1" in o["source"] and "F-110" in o["reason"] for o in omissions))


if __name__ == "__main__":
    unittest.main(verbosity=2)
