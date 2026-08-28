from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError
from ops.loop_state import StateFileLock, load_json, update_json_atomically, validate_loop_state, validate_punch_list


VALID_STATE = {
    "loop_id": "completion-loop-v1",
    "iteration": 9,
    "current_work_item": "F-03",
    "last_successful_item": "F-09-R2",
    "checkpoint_timestamp": "2026-08-23T07:00:00Z",
}


def punch_document() -> dict:
    return {
        "schema_version": "1.0",
        "recorded_at": "2026-08-23T07:00:00Z",
        "items": [
            {"id": "F-06", "title": "revocation", "priority": "P0", "status": "CLOSED"},
            {"id": "F-08", "title": "cycles", "priority": "P0", "status": "CLOSED"},
            {"id": "F-09", "title": "bridge", "priority": "P0", "status": "CLOSED"},
        ],
    }


class LoopStateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.directory = Path(self._directory.name)
        self.state_path = self.directory / "LOOP_STATE.json"
        self.punch_path = self.directory / "PUNCH_LIST.json"
        self.state_path.write_text(json.dumps(VALID_STATE, indent=2), encoding="utf-8")
        self.punch_path.write_text(json.dumps(punch_document(), indent=2), encoding="utf-8")

    def tearDown(self) -> None:
        self._directory.cleanup()

    @staticmethod
    def spawn_and_kill_victim() -> int:
        probe = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        pid = probe.pid
        probe.kill()
        probe.wait()
        del probe
        return pid

    def test_valid_documents_pass(self) -> None:
        self.assertEqual(validate_loop_state(load_json(self.state_path))["iteration"], 9)
        self.assertEqual(len(validate_punch_list(load_json(self.punch_path))["items"]), 3)

    def test_corrupt_or_missing_files_fail_closed(self) -> None:
        for path in (self.state_path, self.punch_path):
            original = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                path.write_text("{not json", encoding="utf-8")
                with self.assertRaises(ContractError):
                    load_json(path)
                path.unlink()
                with self.assertRaises(ContractError):
                    load_json(path)
            path.write_text(original, encoding="utf-8")

    def test_schema_violations_rejected(self) -> None:
        bad_state = {**VALID_STATE, "iteration": -1}
        with self.assertRaises(ContractError):
            validate_loop_state(bad_state)
        bad_status = punch_document()
        bad_status["items"][0]["status"] = "MAGICAL"
        with self.assertRaises(ContractError):
            validate_punch_list(bad_status)
        duplicate = punch_document()
        duplicate["items"][1]["id"] = "F-06"
        with self.assertRaises(ContractError):
            validate_punch_list(duplicate)
        missing_key = dict(VALID_STATE)
        missing_key.pop("checkpoint_timestamp")
        with self.assertRaises(ContractError):
            validate_loop_state(missing_key)
        naive = {**VALID_STATE, "checkpoint_timestamp": "2026-08-23T07:00:00"}
        with self.assertRaises(ContractError):
            validate_loop_state(naive)

    def test_failed_post_mutation_validation_leaves_file_untouched(self) -> None:
        before = self.state_path.read_text(encoding="utf-8")

        def invalid_mutator(state: dict) -> dict:
            return {**state, "iteration": "ten"}

        with self.assertRaises(ContractError):
            update_json_atomically(self.state_path, invalid_mutator, validator=validate_loop_state)
        self.assertEqual(self.state_path.read_text(encoding="utf-8"), before)

    def test_update_round_trip_is_atomic_and_validated(self) -> None:
        def bump(state: dict) -> dict:
            return {**state, "iteration": state["iteration"] + 1, "checkpoint_timestamp": "2026-08-23T08:00:00Z"}

        updated = update_json_atomically(self.state_path, bump, validator=validate_loop_state)
        self.assertEqual(updated["iteration"], 10)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8"))["iteration"], 10)
        self.assertFalse((self.directory / "LOOP_STATE.json.tmp").exists())
        self.assertFalse((self.directory / "LOOP_STATE.json.lock").exists())

    def test_live_competitor_lock_fails_closed(self) -> None:
        lock_path = self.directory / "LOOP_STATE.json.lock"
        lock_path.write_text(json.dumps({"pid": os.getpid(), "acquired_at": "2026-08-23T07:00:00Z"}), encoding="utf-8")
        with self.assertRaises(ContractError):
            update_json_atomically(self.state_path, lambda state: state, validator=validate_loop_state)

    def test_stale_dead_owner_lock_is_recovered(self) -> None:
        victim_pid = self.spawn_and_kill_victim()
        lock_path = self.directory / "LOOP_STATE.json.lock"
        lock_path.write_text(json.dumps({"pid": victim_pid, "acquired_at": "2026-08-23T07:00:00Z"}), encoding="utf-8")
        updated = update_json_atomically(self.state_path, lambda state: {**state, "iteration": 11}, validator=validate_loop_state)
        self.assertEqual(updated["iteration"], 11)
        self.assertFalse(lock_path.exists())

    def test_malformed_lock_payload_is_recovered(self) -> None:
        lock_path = self.directory / "LOOP_STATE.json.lock"
        lock_path.write_text("garbage", encoding="utf-8")
        updated = update_json_atomically(self.state_path, lambda state: {**state, "iteration": 12}, validator=validate_loop_state)
        self.assertEqual(updated["iteration"], 12)


class TerminalIdentityFieldTests(unittest.TestCase):
    def test_identity_fields_accept_sha_or_unbound(self) -> None:
        state = {
            **VALID_STATE,
            "implementation_seal_commit": "a" * 40,
            "evidence_commit": None,
            "verified_branch_head": None,
            "current_phase": "TERMINAL",
            "terminal_disposition": "BUILD_COMPLETE_EXPERIMENT_PENDING",
            "open_critical_findings": 0,
            "open_high_findings": 0,
            "terminal_verified_at": None,
        }
        self.assertEqual(validate_loop_state(state)["current_phase"], "TERMINAL")
        bound = {**state, "evidence_commit": "b" * 40, "verified_branch_head": "c" * 40}
        self.assertEqual(validate_loop_state(bound)["verified_branch_head"], "c" * 40)

    def test_malformed_identity_fields_fail_closed(self) -> None:
        short = {**VALID_STATE, "implementation_seal_commit": "cb26214"}
        with self.assertRaises(ContractError):
            validate_loop_state(short)
        uppercase = {**short, "implementation_seal_commit": "A" * 40}
        with self.assertRaises(ContractError):
            validate_loop_state(uppercase)
        with self.assertRaises(ContractError):
            validate_loop_state({**VALID_STATE, "evidence_commit": "TBD"})
        with self.assertRaises(ContractError):
            validate_loop_state({**VALID_STATE, "open_critical_findings": -1})
        with self.assertRaises(ContractError):
            validate_loop_state({**VALID_STATE, "open_critical_findings": True})
        with self.assertRaises(ContractError):
            validate_loop_state({**VALID_STATE, "terminal_disposition": ""})
        naive = {**VALID_STATE, "terminal_verified_at": "2026-08-23T09:00:00"}
        with self.assertRaises(ContractError):
            validate_loop_state(naive)


if __name__ == "__main__":
    unittest.main()
