"""Qualification harness: a flaky product API or a failing sampler must not end a long measurement."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sovereign"))

from sovereign_product import qualification_harness as QH  # noqa: E402


class FakeProduct(QH.ProductClient):
    """The product API with scripted failures: ``job_failures`` OSErrors before the job completes."""

    def __init__(self, job_failures=0, submit_error=None):
        super().__init__("http://127.0.0.1:1")
        self.job_failures = job_failures
        self.submit_error = submit_error
        self.cancelled = []

    def _call(self, method, path, body=None):
        if path == "/v1/sessions":
            return 201, {"session": {"session_id": "s1"}}
        if path == "/v1/message":
            if self.submit_error:
                raise self.submit_error
            return 202, {"job_id": "j1", "status": "queued"}
        if path == "/v1/self-state":
            return 200, {}
        if path.endswith("/cancel"):
            self.cancelled.append(path)
            return 200, {}
        if path == "/v1/jobs/j1":
            if self.job_failures > 0:
                self.job_failures -= 1
                raise ConnectionResetError("product restarting")
            return 200, {"status": "completed", "metrics": {"tokens": 7}}
        raise AssertionError(path)


def _run(client, **kwargs):
    ticks = iter(range(10_000))
    return QH.run_job(client, "hello", "QUICK", timeout=10_000, clock=lambda: float(next(ticks)),
                      sleep=lambda seconds: None, **kwargs)


def test_transient_api_errors_while_polling_do_not_abort_the_job():
    record = _run(FakeProduct(job_failures=2))
    assert record["status"] == "completed" and record["tokens"] == 7


def test_a_product_that_stays_unreachable_is_recorded_as_a_failed_run():
    record = _run(FakeProduct(job_failures=10_000))
    assert record["status"] == "failed"
    assert "unreachable" in record["error"] and "ConnectionResetError" in record["error"]


def test_a_submit_error_is_recorded_not_raised():
    record = _run(FakeProduct(submit_error=ConnectionRefusedError("down")))
    assert record["status"] == "failed" and "ConnectionRefusedError" in record["error"]


def test_a_non_json_self_state_means_residency_unknown():
    class Garbled(FakeProduct):
        def _call(self, method, path, body=None):
            raise ValueError("not json")

    assert QH.llama_loaded_models(Garbled()) is None


def test_the_sampler_keeps_sampling_after_one_bad_reading():
    sampler = QH.ResourceSampler(interval=0.0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("[N/A]")  # nvidia-smi prints N/A when it has no reading
        if len(calls) >= 3:
            sampler._stop.set()

    sampler._sample_gpu = flaky
    sampler._sample_ram = lambda: None
    thread = threading.Thread(target=sampler._loop, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive() and len(calls) >= 3

