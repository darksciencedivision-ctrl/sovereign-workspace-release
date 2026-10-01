"""Injected hung Windows utilities fail boundedly without losing ownership records."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import supervisor_service as ss
from sovereign_product.runtime_contracts import RuntimeControlError
from sovereign_product.runtime_supervisor import LlamaCppSupervisor
from sovereign_product.freetoken_supervisor import FreeTokenSupervisor


@pytest.fixture
def hung(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs.get('timeout', 0))
    monkeypatch.setattr(subprocess, 'run', run)
    return calls


@pytest.mark.parametrize('operation', ['query', 'register', 'delete'])
def test_scheduler_timeout_is_bounded_and_reported(hung, tmp_path, caplog, operation):
    with pytest.raises(RuntimeControlError, match='timed out'):
        if operation == 'query':
            ss._task_exists('synthetic-task')
        elif operation == 'register':
            ss._register_task('synthetic-task', tmp_path / 'never-executed.xml')
        else:
            ss._delete_task('synthetic-task')
    assert 15 <= hung[0]['timeout'] <= 30
    assert 'schtasks' in caplog.text and 'timed out' in caplog.text


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows control commands')
def test_watch_timeout_keeps_record_for_retry(hung, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('SOVEREIGN_STATE_DIR', str(tmp_path))
    path = ss.watch_pid_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps({'pid': 12345, 'pid_create_filetime': 22}).encode())
    monkeypatch.setattr(ss, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: 22)
    with pytest.raises(RuntimeControlError, match='timed out'):
        ss._stop_watch_process(tmp_path)
    assert path.exists()
    assert 15 <= hung[0]['timeout'] <= 30
    assert 'taskkill' in caplog.text


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows control commands')
@pytest.mark.parametrize('cls', [LlamaCppSupervisor, FreeTokenSupervisor])
def test_supervisor_timeout_preserves_owned_handle(hung, cls, caplog):
    supervisor = object.__new__(cls)
    child = SimpleNamespace(pid=12345, poll=lambda: None)
    supervisor.process = child
    with pytest.raises(RuntimeControlError, match='timed out'):
        supervisor.stop()
    assert supervisor.process is child
    assert 15 <= hung[0]['timeout'] <= 30
    assert 'taskkill' in caplog.text
