"""R27 — the full-session history pages, attributes per page, and surfaces truncation.

public_session used list_jobs(limit=500) to attribute messages and list_messages (first 2000) to
enumerate them. A session with more than 500 jobs silently dropped any completed answer whose job
fell outside that window, and a session with more than 2000 messages was truncated with no signal.

Attribution is now joined to exactly the rendered page via get_jobs_by_ids (no fixed job cap), and
page_recent_messages returns the most recent page plus the true total and an older-messages cursor.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product import server as server_mod  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402


class _FakeService:
    """Only what public_session touches; the real methods are bound off ProductService."""

    def __init__(self, store: SovereignStore) -> None:
        self.store = store

    public_session = ProductService.public_session
    public_message = ProductService.public_message
    public_job = ProductService.public_job
    active_job = ProductService.active_job
    _evidence_reference = staticmethod(ProductService._evidence_reference)


def _complete_turn(store: SovereignStore, session: str, n: int) -> str:
    """Admit one turn, run it and complete it; return the accepted answer's message id."""
    job = store.admit_job(session, route="QUICK", input_text=f"q{n}", user_content=f"q{n}")["job"]
    store.transition_job(job["job_id"], "running", expected_status="queued")
    out = store.complete_job_with_answer(job["job_id"], content=f"answer {n}")
    return out["message"]["message_id"]


class StoreLevelPagination(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r27-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.store = SovereignStore(self.tmp / "sovereign.db")
        self.session = self.store.create_session(title="New chat")["session_id"]

    def test_page_surfaces_total_and_cursor_when_truncated(self) -> None:
        for i in range(3):                      # 3 turns => 6 messages
            _complete_turn(self.store, self.session, i)
        page = self.store.page_recent_messages(self.session, limit=4)
        self.assertEqual(page["total"], 6)
        self.assertTrue(page["has_more_older"])
        self.assertIsNotNone(page["older_cursor"])
        self.assertEqual(len(page["messages"]), 4)
        # The page holds the MOST RECENT messages, in ascending order.
        self.assertEqual(page["messages"][-1]["content"], "answer 2")
        # Following the cursor reaches the older messages, with no overlap.
        older = self.store.page_recent_messages(self.session, limit=4, before=page["older_cursor"])
        self.assertEqual(len(older["messages"]), 2)
        self.assertFalse(older["has_more_older"])

    def test_get_jobs_by_ids_is_not_capped_and_dedups(self) -> None:
        ids = [_complete_turn_job(self.store, self.session, i) for i in range(5)]
        fetched = self.store.get_jobs_by_ids(ids + ids + ["job_missing"])  # dups + a miss
        self.assertEqual(set(fetched), set(ids))


def _complete_turn_job(store: SovereignStore, session: str, n: int) -> str:
    job = store.admit_job(session, route="QUICK", input_text=f"q{n}", user_content=f"q{n}")["job"]
    store.transition_job(job["job_id"], "running", expected_status="queued")
    store.complete_job_with_answer(job["job_id"], content=f"answer {n}")
    return job["job_id"]


class PublicSessionAttributesEveryPageMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r27svc-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.store = SovereignStore(self.tmp / "sovereign.db")
        self.session = self.store.create_session(title="New chat")["session_id"]
        self.svc = _FakeService(self.store)

    def test_an_answer_whose_job_is_older_than_the_old_500_cap_is_not_dropped(self) -> None:
        # 501 completed turns: the very first answer's job is well outside the old 500-job window.
        first_answer_id = _complete_turn(self.store, self.session, 0)
        for i in range(1, 501):
            _complete_turn(self.store, self.session, i)
        raw = self.store.get_session(self.session)  # sanity: many messages exist
        self.assertGreater(len(raw["messages"]), 1000)
        view = self.svc.public_session(raw)
        rendered_ids = {m["message_id"] for m in view["messages"]}
        self.assertIn(first_answer_id, rendered_ids,
                      "the oldest completed answer was dropped by a capped job lookup")
        self.assertEqual(view["total_messages"], 1002)

    def test_public_session_surfaces_truncation(self) -> None:
        for i in range(3):
            _complete_turn(self.store, self.session, i)
        raw = self.store.get_session(self.session)
        with mock.patch.object(server_mod, "SESSION_MESSAGE_PAGE", 2):
            view = self.svc.public_session(raw)
        self.assertTrue(view["messages_truncated"])
        self.assertEqual(view["total_messages"], 6)
        self.assertIsNotNone(view["older_messages_cursor"])
        self.assertEqual(len(view["messages"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
