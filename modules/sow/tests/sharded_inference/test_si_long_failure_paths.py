"""H3: every LONG failure path ends as a readable job outcome, never a stuck job or a lost run.

Before: a model server that went away mid-run (a supervisor restart takes 1-2 minutes) made every
remaining chunk fail its three attempts within seconds, or crashed the run with a misleading "does
not fit the window" once exact token counting failed; a resumed run re-read an @input file that
might be gone; a full disk ended the job with a raw OSError. Now an outage pauses the run (bounded)
and it continues when the server answers; if it stays away, or the disk is full, the job ends
``interrupted`` with the reason and POST /v1/jobs/<id>/resume continues it from its checkpoints.
Failure injection: outage mid-run, 503-style outage during counting, outage past the wait,
@input deleted before a resume, disk full at a checkpoint, unwritable evidence folder,
malformed long_workload.json, a refused key.
"""
from __future__ import annotations

import errno
import inspect
import json
import queue
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import shard_runner as SR  # noqa: E402
from sovereign_product.model_client import ModelClientError  # noqa: E402
from sovereign_product.runtime_contracts import InferenceAuthError  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402

from test_si_p6_long_route import FakeLlama, _small_root, clean_env  # noqa: E402,F401

MATERIAL = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(40))
TEXT = f"Count entries.\n---\n{MATERIAL}"


class Clock:
    """A fake monotonic clock; sleeping advances it (so a 300 s wait takes no real time)."""

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


class FlakyLlama(FakeLlama):
    """The server goes away after ``down_after`` chats and comes back after ``down_for`` s."""

    def __init__(self, clock, *, down_after, down_for, how="refused"):
        super().__init__()
        self.clock, self.down_after, self.down_for, self.how = clock, down_after, down_for, how
        self.down_since = None
        self.went_down = False
        self.refused_calls = 0

    def _down(self):
        if self.down_since is None:
            return False
        if self.clock.now - self.down_since >= self.down_for:
            self.down_since = None
            return False
        return True

    def native_context_length(self, model):
        if self._down():
            raise ModelClientError("llama.cpp model probe returned an HTTP error: refused")
        return super().native_context_length(model)

    def count_text_tokens(self, model, text):
        return None if self._down() else super().count_text_tokens(model, text)

    def chat(self, **kw):
        if not self.went_down and len(self.chats) == self.down_after:
            self.went_down, self.down_since = True, self.clock.now
        if self._down():
            self.refused_calls += 1
            if self.how == "over_limit":  # what chat raises once its exact count fails
                raise ModelClientError("generation over limit: 32768-token context")
            raise ModelClientError("llama.cpp request failed: [WinError 10061] refused")
        return super().chat(**kw)


def _executor(root, client, clock):
    return LW.LongWorkloadExecutor(root=root, evidence_dir=root / "ev", client=client,
                                   config=LW.load_config(root), sleep=clock.sleep,
                                   monotonic=clock.monotonic)


def _events(root, job_id, name):
    return sorted((root / "ev" / "long" / job_id / "checkpoints").glob(f"*_{name}.json"))


def _run(executor, job_id, text=TEXT, progress=None):
    return executor.run(job_id, text, cancel_requested=lambda: False,
                        progress_callback=(progress.append if progress is not None
                                           else lambda p: None))


# --- the model server goes away mid-run ----------------------------------------------------------

@pytest.mark.parametrize("how", ["refused", "over_limit"])
def test_h3_a_supervisor_restart_mid_run_pauses_the_run_and_it_completes(clean_env, tmp_path,
                                                                        how):
    root = _small_root(tmp_path)
    clock = Clock()
    client = FlakyLlama(clock, down_after=3, down_for=90, how=how)  # a restart with a reload
    progress: list = []
    result = _run(_executor(root, client, clock), "job-o1", progress=progress)
    assert result["status"] == "completed", result
    assert client.refused_calls >= 1 and 90 <= clock.slept < 300
    assert _events(root, "job-o1", "task_failed") == [], "no chunk was failed by the outage"
    assert [p["stage"] for p in progress].count("model_unavailable") == 1
    assert "model_available" in [p["stage"] for p in progress]


def test_h3_an_outage_past_the_wait_interrupts_the_job_and_resume_finishes_it(clean_env,
                                                                             tmp_path):
    root = _small_root(tmp_path)
    clock = Clock()
    client = FlakyLlama(clock, down_after=3, down_for=10_000)
    result = _run(_executor(root, client, clock), "job-o2")
    assert result["status"] == "interrupted"
    assert "not answering" in result["reason"] and "still not answering after 300 s" in result[
        "reason"]
    assert "resume the job" in result["reason"] and result["telemetry"]["completed"] == 3
    assert _events(root, "job-o2", "task_failed") == []
    assert _events(root, "job-o2", "run_finished") == [], "the run stays resumable"

    again = FakeLlama()
    second = _run(_executor(root, again, Clock()), "job-o2")
    assert second["status"] == "completed"
    assert len(again.chats) == second["telemetry"]["model_calls"] - 3


def test_h3_the_server_down_at_the_start_interrupts_with_the_reason(clean_env, tmp_path):
    root = _small_root(tmp_path)
    clock = Clock()
    client = FlakyLlama(clock, down_after=0, down_for=10_000)
    client.went_down, client.down_since = True, clock.now
    result = _run(_executor(root, client, clock), "job-o3")
    assert result["status"] == "interrupted"
    assert "did not answer" in result["reason"] and "Start the llama.cpp supervisor" in result[
        "reason"]


def test_h3_a_refused_key_stops_the_run_instead_of_failing_every_chunk(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = FakeLlama()

    def refuse(**kw):
        client.chats.append(kw)
        raise InferenceAuthError("llama.cpp at http://127.0.0.1:18080 refused an API key "
                                 "(HTTP 401)")

    client.chat = refuse
    with pytest.raises(SR.ModelConfigurationError, match="refused an API key"):
        _run(_executor(root, client, Clock()), "job-o4")
    assert len(client.chats) == 1, "no retries, no other chunk tried"


def test_h3_an_outage_does_not_count_as_a_failed_attempt_at_runner_level(tmp_path):
    """The mechanism itself: ModelUnavailable waits and retries the same task, spending nothing."""
    clock = Clock()
    calls = {"n": 0}

    class Port:
        def generate(self, **kw):
            calls["n"] += 1
            if calls["n"] in (2, 3, 4, 5):
                raise SR.ModelUnavailable("down")
            return json.dumps({"result": "ok", "ledger_update": {}})

        def count_tokens(self, text):
            return len(text) // 4

    limits = SR.RunLimits(context_tokens=4096, ledger_budget_tokens=600, max_attempts=1)
    runner = SR.ShardRunner(tmp_path, Port(), limits, sleep=clock.sleep,
                            monotonic=clock.monotonic)
    tasks = [SR.ShardTask(task_id=f"t{i}", kind="step", instruction="do") for i in range(3)]
    state = runner.start("x", "plan_steps", tasks)
    assert state.status == "completed" and not state.failed  # with max_attempts=1
    assert calls["n"] == 7


# --- the @input file, the disk ------------------------------------------------------------------

class Crash(BaseException):
    pass


def test_h3_a_resume_does_not_need_the_input_file_any_more(clean_env, tmp_path):
    root = _small_root(tmp_path)
    inbox = P.resolve_state_home(root) / LW.INBOX_DIRNAME
    inbox.mkdir(parents=True)
    (inbox / "notes.txt").write_bytes(MATERIAL.encode())
    text = "Count entries.\n---\n@input: notes.txt"
    client = FakeLlama()
    real_chat = client.chat

    def crash_after_two(**kw):
        if len(client.chats) >= 2:
            raise Crash()
        return real_chat(**kw)

    client.chat = crash_after_two
    with pytest.raises(Crash):
        _run(_executor(root, client, Clock()), "job-i1", text)
    (inbox / "notes.txt").unlink()
    result = _run(_executor(root, FakeLlama(), Clock()), "job-i1", text)
    assert result["status"] == "completed"
    # a NEW job naming the missing file is still refused clearly
    with pytest.raises(LW.LongWorkloadError, match="is not a file in"):
        _run(_executor(root, FakeLlama(), Clock()), "job-i2", text)


def test_h3_a_full_disk_at_a_checkpoint_interrupts_and_leaves_the_chain_valid(clean_env,
                                                                             tmp_path,
                                                                             monkeypatch):
    root = _small_root(tmp_path)
    real_replace = SR.os.replace
    writes = {"n": 0}

    def replace(src, dst):
        writes["n"] += 1
        if writes["n"] == 4:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_replace(src, dst)

    monkeypatch.setattr(SR.os, "replace", replace)
    result = _run(_executor(root, FakeLlama(), Clock()), "job-d1")
    monkeypatch.setattr(SR.os, "replace", real_replace)
    assert result["status"] == "interrupted"
    assert "could not write its checkpoints" in result["reason"]
    assert "No space left on device" in result["reason"] and "Free disk space" in result["reason"]
    checkpoints = root / "ev" / "long" / "job-d1" / "checkpoints"
    assert not list(checkpoints.glob(".*.tmp")), "no stray temporary file"
    assert LW.checkpoint_problem(root / "ev", "job-d1") is None, "the chain still verifies"

    second = _run(_executor(root, FakeLlama(), Clock()), "job-d1")
    assert second["status"] == "completed"


def test_h3_an_unwritable_evidence_folder_interrupts_with_the_reason(clean_env, tmp_path,
                                                                     monkeypatch):
    root = _small_root(tmp_path)
    real_mkdir = Path.mkdir

    def mkdir(self, *args, **kwargs):
        if "long" in self.parts:
            raise PermissionError(errno.EACCES, "Access is denied", str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    result = _run(_executor(root, FakeLlama(), Clock()), "job-d2")
    assert result["status"] == "interrupted"
    assert "Access is denied" in result["reason"] and "make the folder writable" in result[
        "reason"]


# --- through the product's job lane ------------------------------------------------------------

def _service(root, store, client):
    service = SimpleNamespace(
        root=root, store=store, model_client=client,
        paths=SimpleNamespace(evidence_dir=root / "ev"),
        _queue_lock=threading.RLock(), _active_cancel={}, _active_executor={},
        _closed=threading.Event(), _enqueued=set(), _queue=queue.Queue(),
        _long_queue=queue.Queue())
    for name in ("_run_job", "_execute_job", "_long_executor", "_cancel_callback",
                 "_progress_callback", "_artifact_pointers", "_select_evidence_pointer",
                 "resume_long_job", "_enqueue", "public_job", "_evidence_reference"):
        member = inspect.getattr_static(ProductService, name)
        setattr(service, name, member.__func__ if isinstance(member, staticmethod)
                else types.MethodType(member, service))
    return service


def _long_job(store, text=TEXT):
    session = store.create_session()
    return store.create_job(session["session_id"], "LONG", text)["job_id"]


def test_h3_an_interrupted_job_is_resumed_through_the_product(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    clock = Clock()
    service = _service(root, store, FlakyLlama(clock, down_after=3, down_for=10_000))
    service._long_executor = lambda: _executor(root, service.model_client, clock)
    job_id = _long_job(store)
    service._run_job(job_id)
    job = store.get_job(job_id)
    assert job["status"] == "interrupted", job["error"]
    assert "still not answering" in job["error"] and "resume the job" in job["error"]

    service.model_client = FakeLlama()
    queued = service.resume_long_job(job_id)
    assert queued["status"] == "queued"
    assert service._long_queue.get_nowait() == job_id
    service._run_job(job_id)
    done = store.get_job(job_id)
    assert done["status"] == "completed", done
    assert done["attempts"] == 2


def test_h3_resume_refuses_what_it_cannot_resume(clean_env, tmp_path):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    service = _service(root, store, FakeLlama())
    quick = store.create_job(store.create_session()["session_id"], "QUICK", "hi")["job_id"]
    with pytest.raises(ValueError, match="only LONG jobs resume"):
        service.resume_long_job(quick)
    queued = _long_job(store)
    with pytest.raises(ValueError, match="only an interrupted LONG job"):
        service.resume_long_job(queued)


def test_h3_a_malformed_config_fails_the_job_with_the_reason(clean_env, tmp_path):
    root = _small_root(tmp_path)
    (root / LW.CONFIG_FILE).write_text("{ not json", encoding="utf-8")
    store = SovereignStore(tmp_path / "state.db")
    service = _service(root, store, FakeLlama())
    job_id = _long_job(store)
    service._run_job(job_id)
    job = store.get_job(job_id)
    assert job["status"] == "failed"
    assert LW.CONFIG_FILE in job["error"] and "internal" not in job["error"].lower()


# --- H10: a cancel while a large input is being sized ------------------------------------------

def test_h10_a_cancel_while_sizing_a_large_input_ends_the_job_promptly(clean_env, tmp_path):
    """Sizing a big @input is thousands of /tokenize calls before any chunk runs; the cancel
    used to wait for all of them."""
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    client = FakeLlama()
    counted = {"n": 0}
    real_count = client.count_text_tokens

    def count(model, text):
        counted["n"] += 1
        if counted["n"] == 5:
            store.request_cancel(job_id)  # the operator presses Cancel mid-sizing
        return real_count(model, text)

    client.count_text_tokens = count
    service = _service(root, store, client)
    big = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(400))
    job_id = _long_job(store, f"Count entries.\n---\n{big}")
    service._run_job(job_id)
    job = store.get_job(job_id)
    assert job["status"] == "cancelled", job["error"]
    assert counted["n"] <= 6, f"sizing went on for {counted['n']} counts after the cancel"
    assert client.chats == [], "no chunk ran"
