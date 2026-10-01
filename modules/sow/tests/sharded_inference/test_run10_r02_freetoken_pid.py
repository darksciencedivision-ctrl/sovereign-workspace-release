"""Stale FreeToken state must never authorize killing or adopting a reused PID."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import freetoken_service, gpu_occupancy


def test_reused_freetoken_pid_is_not_killed_or_reported_running(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    root.mkdir()
    state = root / 'state.json'
    state.write_text('{}', encoding='utf-8')
    record = {'pid': 4242, 'pid_create_filetime': 123,
              'host': '127.0.0.1', 'port': 1919}
    monkeypatch.setattr(freetoken_service, 'read_state', lambda _root: record)
    monkeypatch.setattr(freetoken_service, 'state_path', lambda _root: state)
    monkeypatch.setattr(freetoken_service, 'pid_alive', lambda _pid: True)
    monkeypatch.setattr(freetoken_service, 'port_open', lambda *_args: True)
    monkeypatch.setattr(freetoken_service, 'pid_matches_recorded',
                        lambda _pid, _record: False, raising=False)
    monkeypatch.setattr(freetoken_service, 'build_supervisor',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError('unrelated process adopted')))
    monkeypatch.setattr(freetoken_service, '_disable_autostart', lambda _root: None)
    monkeypatch.setattr(gpu_occupancy, 'release_gpu', lambda *_args: None)

    assert freetoken_service.cmd_status(root)['running'] is False
    result = freetoken_service.cmd_stop(root)
    assert result['stopped'] is False
    assert result['pid_owned'] is False
    assert not state.exists()


def test_matching_freetoken_identity_keeps_owned_stop_path(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    root.mkdir()
    state = root / 'state.json'
    state.write_text('{}', encoding='utf-8')
    record = {'pid': 4243, 'pid_create_filetime': 124,
              'host': '127.0.0.1', 'port': 1919}
    monkeypatch.setattr(freetoken_service, 'read_state', lambda _root: record)
    monkeypatch.setattr(freetoken_service, 'state_path', lambda _root: state)
    monkeypatch.setattr(freetoken_service, 'pid_alive', lambda _pid: True)
    monkeypatch.setattr(freetoken_service, 'port_open', lambda *_args: True)
    monkeypatch.setattr(freetoken_service, 'pid_matches_recorded',
                        lambda _pid, _record: True, raising=False)
    stopped = []

    class FakeSupervisor:
        def stop(self):
            stopped.append(self.pid)

    monkeypatch.setattr(freetoken_service, 'build_supervisor',
                        lambda *_args, **_kwargs: FakeSupervisor())
    monkeypatch.setattr(freetoken_service, '_disable_autostart', lambda _root: None)
    monkeypatch.setattr(gpu_occupancy, 'release_gpu', lambda *_args: None)

    assert freetoken_service.cmd_status(root)['running'] is True
    result = freetoken_service.cmd_stop(root)
    assert result['stopped'] is True
    assert result['pid_owned'] is True
    assert stopped == [4243]
