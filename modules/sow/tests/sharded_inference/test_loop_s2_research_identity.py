"""Research lock probes never signal Windows processes; PID reuse is not ownership."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SOV = Path(__file__).resolve().parents[4] / 'modules/sovereign'
sys.path.insert(0, str(SOV))
from sovereign_product import research as r
from sovereign_product import supervisor_service as ss


def test_probe_never_signals_windows(monkeypatch):
    if sys.platform != 'win32':
        pytest.skip('Windows non-signalling probe')
    monkeypatch.setattr(os, 'kill', lambda *a: pytest.fail('probe signalled a process'))
    assert r._ResearchLock._pid_alive(os.getpid())


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows process identity')
def test_live_child_is_alive():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        assert r._ResearchLock._pid_alive(child.pid)
        assert child.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)


def test_live_lock_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(r._ResearchLock, '_pid_alive', staticmethod(lambda pid: True))
    path = tmp_path / 'lock'
    with r._ResearchLock(path, lambda: 'now'):
        payload = json.loads(path.read_text())
        assert 'pid_create_filetime' in payload
        with pytest.raises(r.ResearchAlreadyRunning):
            with r._ResearchLock(path, lambda: 'later'):
                pytest.fail('stole live lock')


@pytest.mark.parametrize('alive,recorded', [(False, 22), (True, 11)])
def test_dead_or_reused_holder_reclaimed(tmp_path, monkeypatch, alive, recorded):
    path = tmp_path / 'lock'
    path.write_bytes(json.dumps({'pid': 12345, 'pid_create_filetime': recorded}).encode())
    monkeypatch.setattr(r._ResearchLock, '_pid_alive', staticmethod(lambda pid: alive))
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: 22)
    with r._ResearchLock(path, lambda: 'now'):
        assert json.loads(path.read_text())['pid'] == os.getpid()
    assert not path.exists()


def test_unknown_live_identity_is_not_stolen(tmp_path, monkeypatch):
    path = tmp_path / 'lock'
    path.write_bytes(json.dumps({'pid': 12345}).encode())
    monkeypatch.setattr(r._ResearchLock, '_pid_alive', staticmethod(lambda pid: True))
    monkeypatch.setattr(ss, 'pid_create_filetime', lambda pid: None)
    with pytest.raises(r.ResearchAlreadyRunning):
        with r._ResearchLock(path, lambda: 'now'):
            pytest.fail('unknown ownership must fail closed')


def test_windows_signal_zero_has_platform_guard():
    for path in (SOV / 'sovereign_product').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os'
                    and node.func.attr == 'kill' and len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value == 0):
                    guards = [n for n in ast.walk(function) if isinstance(n, ast.If)
                              and 'sys.platform' in ast.unparse(n.test)]
                    assert guards, f'{path.name}:{node.lineno} has no platform guard'
