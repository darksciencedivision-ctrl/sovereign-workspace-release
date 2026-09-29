"""D5: a LONG job runs uninterrupted; the other model routes wait behind it.

Before: a QUICK/DEEP/RESEARCH job submitted during a LONG run started at once, so the model
server (one resident model) swapped the LONG model out (about 50 s each way, and the LONG run
paused) - the UI could only warn. Now a model job stays ``queued`` with the stage "waiting for
LONG job <id>" until no LONG job is queued or running, then runs, in submission order. STATUS
(no model) is answered at once; a cancelled waiting job leaves the queue; an interrupted LONG
job does not block; shutdown releases every waiter.
"""
from __future__ import annotations

import inspect
import queue
import sys
import threading
import time
import types
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.router import Route  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402

WORKER_METHODS = ("_worker_loop", "_wait_out_long_job", "long_active_job", "_enqueue")


def _service(store, workers=2, ran=None):
    service = SimpleNamespace(
        store=store, _queue=queue.Queue(), _long_queue=queue.Queue(),
        _queue_lock=threading.RLock(), _enqueued=set(), _closed=threading.Event(),
        long_wait_poll_seconds=0.01, _workers=[])
    for name in WORKER_METHODS:
        if not hasattr(ProductService, name):
            continue  # the code before D5 has no waiting step
        member = inspect.getattr_static(ProductService, name)
        setattr(service, name, types.MethodType(member, service))
    ran = [] if ran is None else ran

    def run_job(job_id):  # stands in for the model call: runs the job, then records it
        if store.get_job(job_id)["status"] != "queued":
            return  # as ProductService._run_job: a cancelled job is not run
        store.transition_job(job_id, "running", expected_status="queued", worker_id="w")
        store.transition_job(job_id, "completed", expected_status="running")
        ran.append(job_id)

    service._run_job = run_job
    service.ran = ran
    for index in range(workers):
        thread = threading.Thread(target=service._worker_loop, daemon=True,
                                  name=f"test-worker-{index}")
        thread.start()
        service._workers.append(thread)
    return service


def _stop(service):
    service._closed.set()
    for _ in service._workers:
        service._queue.put(None)
    for thread in service._workers:
        thread.join(timeout=5)


def _until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _job(store, route, text="x"):
    return store.create_job(store.create_session()["session_id"], route, text)["job_id"]


def test_a_model_job_waits_for_a_running_long_job_then_runs(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    long_id = _job(store, "LONG")
    store.transition_job(long_id, "running", expected_status="queued", worker_id="lw")
    service = _service(store)
    try:
        quick = _job(store, "QUICK")
        service._enqueue(quick)
        assert _until(lambda: store.get_job(quick)["progress"].get("stage", "").startswith("waiting"))
        assert store.get_job(quick)["progress"]["stage"] == f"waiting for LONG job {long_id}"
        time.sleep(0.2)
        assert service.ran == [] and store.get_job(quick)["status"] == "queued"

        store.transition_job(long_id, "completed", expected_status="running")
        assert _until(lambda: service.ran == [quick])
        assert store.get_job(quick)["status"] == "completed"
    finally:
        _stop(service)


def test_waiting_jobs_run_in_submission_order_with_two_workers(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    long_id = _job(store, "LONG")
    service = _service(store, workers=2)
    try:
        ids = [_job(store, route) for route in ("QUICK", "DEEP", "RESEARCH", "CONTINUITY")]
        for job_id in ids:
            service._enqueue(job_id)
        time.sleep(0.2)
        assert service.ran == []
        store.transition_job(long_id, "cancelled", expected_status="queued")
        assert _until(lambda: len(service.ran) == 4)
        assert sorted(service.ran) == sorted(ids)  # none lost, none run twice, no deadlock
        assert len(set(service.ran)) == 4
    finally:
        _stop(service)


def test_a_cancelled_waiting_job_leaves_the_queue_without_running(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    long_id = _job(store, "LONG")
    service = _service(store)
    try:
        quick = _job(store, "QUICK")
        service._enqueue(quick)
        assert _until(lambda: store.get_job(quick)["progress"].get("stage", "").startswith("waiting"))
        store.request_cancel(quick)
        assert store.get_job(quick)["status"] == "cancelled"
        second = _job(store, "QUICK")
        store.transition_job(long_id, "cancelled", expected_status="queued")
        service._enqueue(second)
        assert _until(lambda: service.ran == [second])
        assert store.get_job(quick)["status"] == "cancelled"
    finally:
        _stop(service)


def test_an_interrupted_long_job_does_not_block_the_queue(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    long_id = _job(store, "LONG")
    store.transition_job(long_id, "running", expected_status="queued", worker_id="lw")
    store.transition_job(long_id, "interrupted", expected_status="running")
    service = _service(store)
    try:
        quick = _job(store, "QUICK")
        service._enqueue(quick)
        assert _until(lambda: service.ran == [quick])
    finally:
        _stop(service)


def test_shutdown_releases_a_waiting_worker(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    _job(store, "LONG")
    service = _service(store, workers=1)
    quick = _job(store, "QUICK")
    service._enqueue(quick)
    assert _until(lambda: store.get_job(quick)["progress"].get("stage", "").startswith("waiting"))
    _stop(service)
    assert not service._workers[0].is_alive()
    assert service.ran == [] and store.get_job(quick)["status"] == "queued"


def test_a_long_job_is_never_held_and_status_is_answered_at_once(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    long_id = _job(store, "LONG")
    service = _service(store)
    try:
        # the LONG lane is a separate queue: its own worker takes the job straight away
        long_worker = threading.Thread(target=service._worker_loop, args=(service._long_queue,),
                                       daemon=True)
        long_worker.start()
        service._enqueue(long_id)
        assert _until(lambda: service.ran == [long_id])
        service._long_queue.put(None)
        long_worker.join(timeout=5)

        # STATUS never reaches a worker: submit() answers it inline
        session = store.create_session()["session_id"]
        blocked = _job(store, "LONG")  # a LONG job is queued again
        answered = []
        svc = SimpleNamespace(
            store=store, route=lambda text, override: SimpleNamespace(
                route=Route.STATUS, normalized_query=text, as_dict=lambda: {}),
            active_job=lambda sid: None,
            _run_status_job=lambda job_id, query: answered.append(job_id) or {"ok": True})
        body, status = ProductService.submit(svc, session, "what is your status?")
        assert status == 200 and len(answered) == 1 and store.get_job(blocked)["status"] == "queued"
    finally:
        _stop(service)
