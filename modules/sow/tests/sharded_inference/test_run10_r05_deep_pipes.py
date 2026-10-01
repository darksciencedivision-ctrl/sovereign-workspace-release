"""DEEP executor: a finished engine whose pipes stay open (an orphaned child) must not hang the job."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sovereign"))

from sovereign_product.executors import DeepExecutor, ExecutionStatus  # noqa: E402


class _OpenPipe:
    """A pipe a surviving grandchild still holds: readline blocks until released."""

    def __init__(self, release: threading.Event):
        self.release = release

    def readline(self):
        self.release.wait(timeout=30)
        return ""


class _ClosedPipe:
    def readline(self):
        return ""


class _ExitedEngine:
    pid = 4242
    returncode = 0

    def __init__(self, release):
        self.stdout, self.stderr = _OpenPipe(release), _ClosedPipe()

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_exited_engine_with_open_pipes_does_not_hang(tmp_path):
    release = threading.Event()
    executor = DeepExecutor(tmp_path, popen_factory=lambda *a, **k: _ExitedEngine(release),
                            poll_interval=0.01, exit_drain_seconds=0.2)
    box = {}
    worker = threading.Thread(
        target=lambda: box.update(result=executor.execute("session-1", "a topic")), daemon=True)
    worker.start()
    worker.join(timeout=10)
    hung = worker.is_alive()
    release.set()  # let the reader thread finish whichever way the test went
    worker.join(timeout=10)
    assert not hung, "execute() did not return after the engine exited"
    result = box["result"]
    assert result.status is ExecutionStatus.FAILED
    assert result.exit_code == 0
    assert result.telemetry["output_drain_abandoned"] is True


def test_closed_pipes_are_not_reported_as_abandoned(tmp_path):
    class Closed(_ExitedEngine):
        def __init__(self):
            self.stdout, self.stderr = _ClosedPipe(), _ClosedPipe()

    executor = DeepExecutor(tmp_path, popen_factory=lambda *a, **k: Closed(), poll_interval=0.01)
    result = executor.execute("session-2", "a topic")
    assert result.telemetry["output_drain_abandoned"] is False
