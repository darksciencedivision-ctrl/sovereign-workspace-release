"""F-106 — event-chain verification is incremental from a checkpoint, not a full re-hash per boot.

Re-hashing every event_log row on every startup made startup time grow linearly with the install's
lifetime until the service missed the shell's readiness window. Verification now checkpoints the
last-verified (sequence, hash) in meta and, on the next open, verifies only the rows appended
since. A full audit is still available on demand, and a mismatch on a checked row still raises.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.store import (  # noqa: E402
    EVENT_CHAIN_CHECKPOINT_KEY, SovereignStore, StoreIntegrityError,
)


class IncrementalVerification(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="f106-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.db = self.tmp / "s.db"

    def test_restart_verifies_only_new_rows(self) -> None:
        store = SovereignStore(self.db)
        for i in range(3):
            store.create_session(title="New chat")
        first = store.verify_event_chain()
        self.assertGreater(store.get_meta(EVENT_CHAIN_CHECKPOINT_KEY)["sequence"], 0)
        # Reopen (a restart): verification starts from AFTER the checkpoint, not sequence 1.
        reopened = SovereignStore(self.db)
        result = reopened.verify_event_chain()
        self.assertTrue(result["incremental"])
        self.assertGreater(result["verified_from_sequence"], 1,
                           "restart re-hashed the whole chain instead of verifying incrementally")

    def test_full_recheck_verifies_from_genesis(self) -> None:
        store = SovereignStore(self.db)
        store.create_session(title="New chat")
        store.verify_event_chain()
        full = store.recheckpoint_event_chain()
        self.assertEqual(full["verified_from_sequence"], 1)
        self.assertFalse(full["incremental"])

    def test_a_tampered_new_row_is_still_detected(self) -> None:
        store = SovereignStore(self.db)
        store.create_session(title="New chat")
        store.verify_event_chain()   # checkpoint now at the current head
        # Append a new event, then corrupt it directly. Verification (from checkpoint+1) must catch
        # the mismatch on this newly-appended row.
        store.create_session(title="Another")
        conn = sqlite3.connect(self.db)
        try:
            head = conn.execute("SELECT MAX(sequence) FROM event_log").fetchone()[0]
            conn.execute("UPDATE event_log SET payload_json='{\"tampered\":true}' WHERE sequence=?",
                         (head,))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(StoreIntegrityError):
            SovereignStore(self.db)  # __init__ runs verify_event_chain


if __name__ == "__main__":
    unittest.main(verbosity=2)
