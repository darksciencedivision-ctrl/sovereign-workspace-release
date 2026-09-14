"""F-092: benchmark output lock, identity, resume and cleanup."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOVEREIGN = REPO / "modules" / "sovereign"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SOVEREIGN))

import analyze  # noqa: E402
import run_benchmark  # noqa: E402

CHILD = r"""
import os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["SWS_BENCH"])
sys.path.insert(0, os.environ["SWS_SOVEREIGN"])
from run_benchmark import OutputLock
lock = OutputLock(Path(os.environ["SWS_LOCK"]))
ok = lock.acquire()
print("ACQUIRE", int(bool(ok)), flush=True)
if ok:
    time.sleep(int(os.environ.get("SWS_HOLD", "20")))
    if os.environ.get("SWS_RELEASE") == "1":
        lock.release()
        print("RELEASED", flush=True)
"""


def _env_for_child(lock_path: Path, hold: int = 20, release: bool = False) -> dict:
    env = os.environ.copy()
    env["SWS_BENCH"] = str(HERE)
    env["SWS_SOVEREIGN"] = str(SOVEREIGN)
    env["SWS_LOCK"] = str(lock_path)
    env["SWS_HOLD"] = str(hold)
    if release:
        env["SWS_RELEASE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(HERE), str(SOVEREIGN), env.get("PYTHONPATH", "")])
    return env


def _wait_acquire(proc: subprocess.Popen, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    buf = ""
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line:
            buf += line
            if "ACQUIRE" in line:
                return buf
        elif proc.poll() is not None:
            rest = proc.stdout.read() or ""
            buf += rest
            return buf
        else:
            time.sleep(0.05)
    return buf


class OutputLockTests(unittest.TestCase):
    def test_concurrent_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl.lock"
            a = run_benchmark.OutputLock(path)
            self.assertTrue(a.acquire())
            b = run_benchmark.OutputLock(path)
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()

    def test_wrong_owner_release_does_not_drop_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl.lock"
            holder = run_benchmark.OutputLock(path)
            self.assertTrue(holder.acquire())
            other = run_benchmark.OutputLock(path)
            other.release()
            self.assertTrue(holder.held)
            self.assertFalse(other.acquire())
            try:
                path.unlink()
                stolen = True
            except OSError:
                stolen = False
            self.assertFalse(stolen, "wrong owner must not delete a held lock")
            third = run_benchmark.OutputLock(path)
            self.assertFalse(third.acquire())
            holder.release()

    def test_crash_then_restart_can_acquire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl.lock"
            proc = subprocess.Popen(
                [sys.executable, "-c", CHILD],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(REPO), env=_env_for_child(path, hold=30))
            self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
            out = _wait_acquire(proc)
            self.assertIn("ACQUIRE 1", out, out)
            rival = run_benchmark.OutputLock(path)
            self.assertFalse(rival.acquire())
            proc.kill()
            proc.wait(timeout=10)
            deadline = time.monotonic() + 5
            got = False
            while time.monotonic() < deadline:
                if rival.acquire():
                    got = True
                    break
                time.sleep(0.05)
            self.assertTrue(got, "crash must release OS lock so a restart can acquire")
            rival.release()

    def test_stale_lock_file_without_holder_is_acquirable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl.lock"
            path.write_text("999999 1970-01-01T00:00:00Z\n", encoding="utf-8")
            lock = run_benchmark.OutputLock(path)
            self.assertTrue(lock.acquire())
            lock.release()


class ResumeAndIdentityTests(unittest.TestCase):
    def test_malformed_resume_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            path.write_text("{not json\n", encoding="utf-8")
            env, cells, err = run_benchmark.load_existing_output(path)
            self.assertIsNone(env)
            self.assertIn("malformed JSON", err)
            path.write_text("", encoding="utf-8")
            _, _, err = run_benchmark.load_existing_output(path)
            self.assertIn("empty", err)
            path.write_text(json.dumps({"record_kind": "run", "task_id": "t"}) + "\n",
                            encoding="utf-8")
            _, _, err = run_benchmark.load_existing_output(path)
            self.assertIn("incomplete run record", err)

    def test_failed_git_does_not_imply_clean(self) -> None:
        manifest = SOVEREIGN / "SYSTEM_MANIFEST.json"
        models = {"PRIMARY_REASONER": "x"}
        with patch.object(run_benchmark, "_git", return_value=(1, "")):
            ident = run_benchmark.collect_candidate_identity(REPO, manifest, models)
        self.assertTrue(ident["identity_uncertain"])
        self.assertTrue(ident["worktree_dirty"])
        self.assertIsNone(ident["git_head"])
        self.assertIsNone(ident["worktree_status_sha256"])
        self.assertFalse(ident["git_head_ok"])
        self.assertFalse(ident["git_status_ok"])

    def test_dirty_identity_is_more_than_a_boolean(self) -> None:
        ident = run_benchmark.collect_candidate_identity(
            REPO, SOVEREIGN / "SYSTEM_MANIFEST.json", {"PRIMARY_REASONER": "x"})
        self.assertIn("worktree_status_sha256", ident)
        self.assertIn("manifest_sha256", ident)
        self.assertEqual(len(ident["manifest_sha256"]), 64)
        if ident["worktree_dirty"] and ident["git_status_ok"]:
            self.assertTrue(ident["dirty_paths"])
            self.assertEqual(len(ident["worktree_status_sha256"]), 64)

    def test_incompatible_resume(self) -> None:
        base = {
            "dataset_sha256": "d", "sources_sha256": "s", "harness_sha256": "h",
            "protocol_sha256": "p", "candidate_sha": "c", "worktree_status_sha256": "w",
            "manifest_sha256": "m", "runs_per_cell": 3, "protocol": "SWS-BENCH-02",
            "conditions": ["A_single"], "models": {"PRIMARY_REASONER": "a"},
            "runtime_options": {"num_ctx": 1},
        }
        other = dict(base)
        self.assertIsNone(run_benchmark.resume_incompatible(base, other, ["A_single"]))
        other = dict(base, models={"PRIMARY_REASONER": "b"})
        self.assertIn("models", run_benchmark.resume_incompatible(base, other, ["A_single"]))
        other = dict(base, protocol="SWS-BENCH-01")
        self.assertIn("protocol", run_benchmark.resume_incompatible(base, other, ["A_single"]))
        other = dict(base, candidate_sha="other")
        self.assertIn("candidate_sha", run_benchmark.resume_incompatible(base, other, ["A_single"]))
        self.assertIn("conditions", run_benchmark.resume_incompatible(base, base, ["B_full"]))


class MainLifecycleTests(unittest.TestCase):
    def _patch_execution(self):
        patches = [
            patch.object(run_benchmark, "ollama_digests", return_value={}),
            patch.object(run_benchmark, "run_condition",
                         return_value=("the answer mentions nothing", {"status": "ok"}, None)),
            patch("sovereign_product.model_client.OllamaClient", return_value=object()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_existing_output_refusal_does_not_empty_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            out.write_text('{"record_kind":"environment","candidate_sha":"keep"}\n',
                           encoding="utf-8")
            rc = run_benchmark.main(
                ["--out", str(out), "--runs", "1", "--tasks", "gf-01",
                 "--conditions", "A_single"])
            self.assertEqual(rc, 2)
            self.assertIn("keep", out.read_text(encoding="utf-8"))

    def test_setup_failure_does_not_leave_empty_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            lock_path = Path(str(out) + ".lock")
            with patch.object(run_benchmark, "HERE", Path(tmp)):
                rc = run_benchmark.main(
                    ["--out", str(out), "--runs", "1", "--tasks", "gf-01",
                     "--conditions", "A_single"])
            self.assertEqual(rc, 2)
            self.assertFalse(out.exists(), "empty refused/failed output must be removed")
            after = run_benchmark.OutputLock(lock_path)
            self.assertTrue(after.acquire(), "setup failure must release the lock")
            after.release()

    def test_malformed_resume_refuses_without_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            out.write_text("{bad\n", encoding="utf-8")
            rc = run_benchmark.main(
                ["--out", str(out), "--resume", "--runs", "1", "--tasks", "gf-01",
                 "--conditions", "A_single"])
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(encoding="utf-8"), "{bad\n")

    def test_worktree_dirty_is_emitted_and_artifact_root_uses_run_id(self) -> None:
        self._patch_execution()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            run_id = "run-f092ident01"
            rc = run_benchmark.main(
                ["--out", str(out), "--runs", "1", "--tasks", "gf-01",
                 "--conditions", "A_single", "--run-id", run_id])
            self.assertEqual(rc, 0, "mocked run should succeed")
            env = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("worktree_dirty", env)
            self.assertIsInstance(env["worktree_dirty"], bool)
            self.assertEqual(len(env["manifest_sha256"]), 64)
            self.assertEqual(env["run_id"], run_id)
            self.assertTrue((Path(tmp) / run_id / "artifacts").is_dir())
            self.assertTrue(any(k in env for k in ("worktree_status_sha256", "identity_uncertain")))

    def test_resume_rejects_incompatible_models(self) -> None:
        self._patch_execution()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            rc = run_benchmark.main(
                ["--out", str(out), "--runs", "1", "--tasks", "gf-01",
                 "--conditions", "A_single", "--run-id", "run-f092r1"])
            self.assertEqual(rc, 0)
            lines = out.read_text(encoding="utf-8").splitlines()
            env = json.loads(lines[0])
            env["models"] = dict(env["models"], PRIMARY_REASONER="definitely-not-this-model")
            out.write_text(json.dumps(env) + "\n", encoding="utf-8")
            rc = run_benchmark.main(
                ["--out", str(out), "--resume", "--runs", "1", "--tasks", "gf-01",
                 "--conditions", "A_single"])
            self.assertEqual(rc, 2)

    def test_concurrent_main_second_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            lock_path = Path(str(out) + ".lock")
            holder = run_benchmark.OutputLock(lock_path)
            self.assertTrue(holder.acquire())
            try:
                rc = run_benchmark.main(
                    ["--out", str(out), "--runs", "1", "--tasks", "gf-01",
                     "--conditions", "A_single"])
                self.assertEqual(rc, 2)
                self.assertFalse(out.exists())
            finally:
                holder.release()


class AnalyzeIdentityTests(unittest.TestCase):
    def test_env_run_sha_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            path.write_text(
                json.dumps({"record_kind": "environment", "candidate_sha": "aaa"}) + "\n"
                + json.dumps({"record_kind": "run", "candidate_sha": "bbb",
                              "task_id": "t", "condition": "A_single", "run_index": 0}) + "\n",
                encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze.load(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
