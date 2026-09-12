"""R05 (F-104) and R07 — job admission and completion are each one transaction.

R05: two concurrent submissions for a session must not both be admitted. The active-job check, the
user-message insert and the job insert are one transaction, backed by a DB partial unique index
`idx_jobs_one_active_per_session`, so exactly one turn wins and the other is refused with no orphan
message left behind.

R07: finishing a job writes the accepted answer, bumps progress and transitions running->completed
in one transaction, and re-checks cancellation inside it. It is therefore impossible to end with an
`accepted` output message attached to a job that is not `completed`: a fault before commit leaves
the job running with no answer, and a cancel that lands mid-flight discards the answer.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.store import (  # noqa: E402
    ActiveJobExists,
    InvalidTransition,
    SovereignStore,
)


class _StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r05r07-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.store = SovereignStore(self.tmp / "sovereign.db")
        self.session = self.store.create_session(title="New chat")["session_id"]

    def _active_jobs(self) -> list[dict]:
        return self.store.list_jobs(status=("queued", "running"), session_id=self.session)


class AdmissionIsAtomic(_StoreCase):
    def test_a_single_admission_creates_one_message_and_one_job(self) -> None:
        out = self.store.admit_job(
            self.session, route="QUICK", input_text="hi there", user_content="hi there")
        self.assertEqual(out["job"]["status"], "queued")
        self.assertEqual(out["message"]["role"], "user")
        self.assertEqual(out["job"]["input_message_id"], out["message"]["message_id"])
        self.assertEqual(len(self._active_jobs()), 1)

    def test_a_second_admission_while_one_is_active_is_refused(self) -> None:
        self.store.admit_job(
            self.session, route="QUICK", input_text="first", user_content="first")
        messages_before = len(self.store.list_messages(self.session))
        with self.assertRaises(ActiveJobExists) as ctx:
            self.store.admit_job(
                self.session, route="QUICK", input_text="second", user_content="second")
        # The refusal carries the existing job, and left no orphan user message behind.
        self.assertIn(ctx.exception.active_job["status"], ("queued", "running"))
        self.assertEqual(len(self.store.list_messages(self.session)), messages_before)
        self.assertEqual(len(self._active_jobs()), 1)

    def test_concurrent_admissions_admit_exactly_one(self) -> None:
        threads = 8
        barrier = threading.Barrier(threads)
        results: list[str] = []
        lock = threading.Lock()

        def attempt(i: int) -> None:
            barrier.wait()
            try:
                self.store.admit_job(
                    self.session, route="QUICK",
                    input_text=f"q{i}", user_content=f"q{i}")
                with lock:
                    results.append("admitted")
            except ActiveJobExists:
                with lock:
                    results.append("refused")

        workers = [threading.Thread(target=attempt, args=(i,)) for i in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        self.assertEqual(results.count("admitted"), 1, results)
        self.assertEqual(results.count("refused"), threads - 1, results)
        # Exactly one job and one user message survived the barrier.
        self.assertEqual(len(self._active_jobs()), 1)
        self.assertEqual(
            [m for m in self.store.list_messages(self.session) if m["role"] == "user"].__len__(),
            1,
        )

    def test_the_partial_unique_index_exists(self) -> None:
        connection = sqlite3.connect(self.store.db_path)
        try:
            names = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        finally:
            connection.close()
        self.assertIn("idx_jobs_one_active_per_session", names)

    def test_a_completed_job_frees_the_session_for_a_new_admission(self) -> None:
        first = self.store.admit_job(
            self.session, route="QUICK", input_text="one", user_content="one")["job"]
        self.store.transition_job(first["job_id"], "running", expected_status="queued")
        self.store.complete_job_with_answer(first["job_id"], content="an answer")
        # No longer active -> a second admission is allowed.
        second = self.store.admit_job(
            self.session, route="QUICK", input_text="two", user_content="two")["job"]
        self.assertEqual(second["status"], "queued")


class MigrationCollapsesPreExistingDuplicates(unittest.TestCase):
    """A database written by the buggy admission path may already hold several active jobs for a
    session; opening it under the new schema must demote all but the newest and create the index,
    not crash."""

    def test_v1_database_with_two_active_jobs_is_migrated(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r05mig-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        db = tmp / "legacy.db"
        # Build a v1 store, then force two active jobs for one session (create_job no longer has a
        # caller that would, but the raw table did allow it at v1).
        store = SovereignStore(db)
        session = store.create_session(title="New chat")["session_id"]
        a = store.create_job(session, "QUICK", "a")["job_id"]
        # Insert a second active job directly, as the buggy path used to.
        connection = sqlite3.connect(db)
        try:
            connection.execute("PRAGMA user_version=1")  # pretend we are pre-migration
            connection.execute("DROP INDEX IF EXISTS idx_jobs_one_active_per_session")
            connection.execute(
                """INSERT INTO jobs(job_id, session_id, route, status, input_text,
                   created_at, updated_at) VALUES('job_second', ?, 'QUICK', 'running', 'b',
                   '2024-01-01T00:00:01Z', '2024-01-01T00:00:01Z')""",
                (session,),
            )
            connection.commit()
        finally:
            connection.close()
        # Reopen: migration runs.
        migrated = SovereignStore(db)
        active = migrated.list_jobs(status=("queued", "running"), session_id=session)
        self.assertEqual(len(active), 1, active)
        # The newest active job per session is kept; `a` carries a real (2026) created_at, so the
        # backdated 'job_second' (2024) is the one demoted.
        self.assertEqual(active[0]["job_id"], a)
        demoted = migrated.get_job("job_second")
        self.assertEqual(demoted["status"], "failed")
        self.assertIn("superseded", str(demoted["error"]))


class CompletionIsAtomic(_StoreCase):
    def _running_job(self) -> str:
        job = self.store.admit_job(
            self.session, route="QUICK", input_text="q", user_content="q")["job"]
        self.store.transition_job(job["job_id"], "running", expected_status="queued")
        return job["job_id"]

    def test_completion_writes_the_answer_and_transitions_together(self) -> None:
        job_id = self._running_job()
        out = self.store.complete_job_with_answer(
            job_id, content="the answer", evidence_pointer="sovereign-state://e.json")
        self.assertEqual(out["outcome"], "completed")
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["output_message_id"], out["message"]["message_id"])
        self.assertEqual(job["progress"].get("percent"), 100)
        msg = self.store.get_message(out["message"]["message_id"])
        self.assertEqual(msg["status"], "accepted")
        self.assertEqual(msg["content"], "the answer")

    def test_a_cancel_that_lands_before_commit_discards_the_answer(self) -> None:
        job_id = self._running_job()
        self.store.request_cancel(job_id)  # cancel_requested=1, still running
        out = self.store.complete_job_with_answer(job_id, content="the answer")
        self.assertEqual(out["outcome"], "cancelled")
        self.assertIsNone(out["message"])
        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "cancelled")
        # No accepted sovereign message was written.
        sovereign_msgs = [m for m in self.store.list_messages(self.session)
                          if m["role"] == "sovereign"]
        self.assertEqual(sovereign_msgs, [])

    def test_a_fault_at_the_transition_rolls_back_the_answer_message(self) -> None:
        """The property R07 protects: if the completion transition cannot be persisted, the
        accepted message written earlier in the same transaction must NOT survive -- otherwise an
        accepted answer would hang off a job still marked running."""
        job_id = self._running_job()
        real = SovereignStore.__dict__["_append_event"].__func__  # unwrap the staticmethod

        def flaky(connection, entity_type, entity_id, action, payload=None):
            if action == "transitioned" and isinstance(payload, dict) and payload.get("to") == "completed":
                raise sqlite3.OperationalError("injected fault at the completion boundary")
            return real(connection, entity_type, entity_id, action, payload)

        with mock.patch.object(SovereignStore, "_append_event", side_effect=flaky):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.complete_job_with_answer(job_id, content="the answer")

        job = self.store.get_job(job_id)
        self.assertEqual(job["status"], "running", "the job must remain running after a rollback")
        self.assertIsNone(job["output_message_id"])
        sovereign_msgs = [m for m in self.store.list_messages(self.session)
                          if m["role"] == "sovereign"]
        self.assertEqual(sovereign_msgs, [], "the answer message must have rolled back")

    def test_completing_a_non_running_job_is_refused(self) -> None:
        job = self.store.admit_job(
            self.session, route="QUICK", input_text="q", user_content="q")["job"]
        # Still queued, not running.
        with self.assertRaises(InvalidTransition):
            self.store.complete_job_with_answer(job["job_id"], content="answer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
