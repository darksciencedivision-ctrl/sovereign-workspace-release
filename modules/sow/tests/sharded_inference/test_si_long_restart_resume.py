"""H1: a LONG job left running by a product restart resumes from its checkpoints.

Live (2026-09-27), a product restart marked a running LONG job ``interrupted`` although its
hash-chained checkpoints could resume it. Now the startup recovery re-queues a running LONG job
whose run verifies (or has not started writing), and the executor continues at the first
unfinished task. Failure injection: a crash mid-run (resumes, no task re-run, no duplicate task
ids), a tampered chain, a missing stored output, a requested cancel and a restart loop (each stays
interrupted with the reason), and non-LONG jobs (unchanged).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402

from test_si_p6_long_route import FakeLlama, _executor, _small_root, clean_env  # noqa: E402,F401

MATERIAL = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(40))


class Crash(BaseException):
    """The process dying mid-run: nothing after it is recorded (not even a cancel)."""


def _service(evidence_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(paths=SimpleNamespace(evidence_dir=evidence_dir))


def _recover(store: SovereignStore, evidence_dir: Path) -> dict:
    """What ProductService.__init__ does at startup."""
    service = _service(evidence_dir)
    return store.recover_incomplete_jobs(
        resume=lambda job: ProductService._restart_decision(service, job))


def _running_long_job(store: SovereignStore, text: str) -> str:
    session = store.create_session()
    job = store.create_job(session["session_id"], "LONG", text)
    store.transition_job(job["job_id"], "running")
    store.update_job_progress(job["job_id"], {"percent": 57, "stage": "task_completed"})
    return job["job_id"]


def _crash_mid_run(root: Path, job_id: str, text: str, after_calls: int) -> FakeLlama:
    client = FakeLlama()
    real_chat = client.chat

    def chat(**kw):
        if len(client.chats) >= after_calls:
            raise Crash()
        return real_chat(**kw)

    client.chat = chat
    try:
        _executor(root, client).run(job_id, text, cancel_requested=lambda: False,
                                    progress_callback=lambda p: None)
    except Crash:
        pass
    else:
        raise AssertionError("the run should have crashed")
    return client


def _last_event(db: Path, job_id: str) -> str:
    connection = sqlite3.connect(db)
    try:
        return connection.execute("SELECT action FROM event_log WHERE entity_id=? "
                                  "ORDER BY sequence DESC LIMIT 1", (job_id,)).fetchone()[0]
    finally:
        connection.close()


def _completed_task_ids(run_dir: Path) -> list[str]:
    ids = []
    for path in sorted((run_dir / "checkpoints").glob("*_task_completed.json")):
        ids.append(json.loads(path.read_text(encoding="utf-8"))["payload"]["task_id"])
    return ids


def test_h1_a_restart_mid_run_resumes_the_long_job_and_it_completes(clean_env, tmp_path):
    root = _small_root(tmp_path)
    evidence = root / "ev"
    store = SovereignStore(tmp_path / "state.db")
    text = f"Count entries.\n---\n{MATERIAL}"
    job_id = _running_long_job(store, text)
    _crash_mid_run(root, job_id, text, after_calls=3)
    done_before = _completed_task_ids(evidence / "long" / job_id)
    assert len(done_before) == 3

    recovery = _recover(store, evidence)
    assert recovery == {"queued": [job_id], "interrupted": []}
    job = store.get_job(job_id)
    assert job["status"] == "queued" and job["error"] is None
    assert job["metadata"]["recovery"]["classification"] == "resumed_on_service_restart"
    assert _last_event(tmp_path / "state.db", job_id) == "recovered_for_resume"
    store.verify_event_chain()
    # The worker's own start path must still work: running, then progress from 1 percent
    # (a leftover 57 percent would make the store refuse it and strand the job).
    store.transition_job(job_id, "running", expected_status="queued")
    store.update_job_progress(job_id, {"percent": 1, "stage": "running"})

    again = FakeLlama()
    result = _executor(root, again).run(job_id, text, cancel_requested=lambda: False,
                                        progress_callback=lambda p: None)
    assert result["status"] == "completed"
    ids = _completed_task_ids(evidence / "long" / job_id)
    assert len(ids) == len(set(ids)), "no task ran twice"
    assert ids[:3] == done_before
    assert len(again.chats) == result["telemetry"]["model_calls"] - 3


def test_h1_a_job_that_had_not_written_checkpoints_starts_again(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    job_id = _running_long_job(store, "Draft a rollout plan.")
    assert _recover(store, root / "ev")["queued"] == [job_id]
    assert not (root / "ev" / "long" / job_id).exists(), "the check never creates run state"


def test_h1_a_tampered_chain_stays_interrupted_with_the_reason(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    text = f"Count entries.\n---\n{MATERIAL}"
    job_id = _running_long_job(store, text)
    _crash_mid_run(root, job_id, text, after_calls=2)
    checkpoint = sorted((root / "ev" / "long" / job_id / "checkpoints").glob("*.json"))[1]
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    record["payload"]["summary"] = "tampered"
    checkpoint.write_text(json.dumps(record), encoding="utf-8")

    assert _recover(store, root / "ev") == {"queued": [], "interrupted": [job_id]}
    job = store.get_job(job_id)
    assert job["status"] == "interrupted"
    assert "checkpoints cannot be resumed" in job["error"]
    assert "chain is broken" in job["error"]


def test_h1_a_missing_stored_output_stays_interrupted(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    text = f"Count entries.\n---\n{MATERIAL}"
    job_id = _running_long_job(store, text)
    _crash_mid_run(root, job_id, text, after_calls=2)
    next(iter((root / "ev" / "long" / job_id / "outputs").glob("*.txt"))).unlink()

    assert _recover(store, root / "ev")["interrupted"] == [job_id]
    assert "missing or altered" in store.get_job(job_id)["error"]


def test_h1_a_requested_cancel_or_a_restart_loop_is_not_resumed(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    cancelled = _running_long_job(store, "Draft a rollout plan.")
    store.request_cancel(cancelled)
    looping = _running_long_job(store, "Draft a rollout plan.")
    for _ in range(LW.RESTART_ATTEMPTS - 1):  # started RESTART_ATTEMPTS times in all
        store.transition_job(looping, "interrupted")
        store.transition_job(looping, "queued")
        store.transition_job(looping, "running")

    recovery = _recover(store, root / "ev")
    assert recovery["queued"] == [] and set(recovery["interrupted"]) == {cancelled, looping}
    assert "cancellation had been requested" in store.get_job(cancelled)["error"]
    assert f"already started {LW.RESTART_ATTEMPTS} times" in store.get_job(looping)["error"]


def test_h1_other_routes_are_still_interrupted_as_before(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    session = store.create_session()
    job = store.create_job(session["session_id"], "DEEP", "think hard")
    store.transition_job(job["job_id"], "running")

    assert _recover(store, root / "ev") == {"queued": [], "interrupted": [job["job_id"]]}
    assert store.get_job(job["job_id"])["error"] == "service restarted while job was running"
