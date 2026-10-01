"""A stale watcher record must never authorize termination or prevent startup."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import supervisor_service as ss


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('SOVEREIGN_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('SOVEREIGN_STATE_DIR', str(tmp_path / 'state/runtime'))
    return tmp_path


def record(root, pid, identity=None):
    path = ss.watch_pid_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'pid': pid, 'started_at': 'stale'}
    if identity is not None:
        payload['pid_create_filetime'] = identity
    path.write_bytes(json.dumps(payload).encode())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PID identity')
def test_unrelated_live_child_survives_stop(root):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    try:
        record(root, child.pid)
        result = ss.cmd_stop(root, disable_autostart=False)
        assert child.poll() is None, 'stale watch.pid killed an unrelated live child'
        assert result['watch_refused'] is True
        assert not ss.watch_pid_path(root).exists()
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)


def test_reused_identity_does_not_authorize_kill(root, monkeypatch):
    record(root, 12345, 11)
    monkeypatch.setattr(ss, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: 22)
    monkeypatch.setattr(ss.subprocess, 'run', lambda *a, **k: pytest.fail('unowned kill'))
    assert ss._stop_watch_process(root)['watch_refused'] is True


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PID identity')
def test_real_watcher_is_stopped(root):
    source = str(Path(ss.__file__).parents[1])
    code = (
        f'import sys; sys.path.insert(0, {source!r}); '
        'from pathlib import Path; '
        'from sovereign_product import supervisor_service as ss; '
        'ss.cmd_ensure = lambda root, port: {"ensured": True}; '
        f'ss.cmd_watch(Path({str(root)!r}), interval=0.05)'
    )
    child = subprocess.Popen([sys.executable, '-c', code])
    try:
        deadline = time.monotonic() + 10
        while not ss._watch_alive(root) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ss._watch_alive(root), 'watcher did not record its OS identity'
        assert ss._stop_watch_process(root)['watch_stopped'] is True
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)


def test_matching_identity_is_stopped(root, monkeypatch):
    record(root, 12345, 22)
    monkeypatch.setattr(ss, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: 22)
    calls = []
    monkeypatch.setattr(ss.subprocess, 'run', lambda *a, **k: calls.append(a))
    monkeypatch.setattr(ss.os, 'kill', lambda *a: calls.append(a))
    assert ss._stop_watch_process(root)['watch_stopped'] is True
    assert len(calls) == 1


def test_stale_watch_does_not_prevent_start(root, monkeypatch):
    record(root, 12345, 11)
    monkeypatch.setattr(ss, 'pid_alive', lambda pid: True)
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: 22)
    assert ss._watch_alive(root) is False
    observed = []
    def ensure(root, port):
        observed.append(json.loads(ss.watch_pid_path(root).read_text()))
        return {'ensured': True}
    monkeypatch.setattr(ss, 'cmd_ensure', ensure)
    ss.cmd_watch(root, max_iterations=1)
    assert observed[0]['pid'] == os.getpid()
    assert observed[0]['pid_create_filetime'] == 22
