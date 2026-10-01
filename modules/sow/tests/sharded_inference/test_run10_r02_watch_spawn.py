"""Failed watcher spawning must release its lock and parent log handle."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import supervisor_service


def test_failed_watch_spawn_cleans_lock_and_log_handle(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    root.mkdir()
    service = tmp_path / 'service'
    monkeypatch.setattr(supervisor_service, 'service_dir', lambda _root: service)
    monkeypatch.setattr(supervisor_service, '_watch_alive', lambda _root: False)
    monkeypatch.setattr(supervisor_service, '_python_for_tasks',
                        lambda _root, **_kwargs: tmp_path / 'python.exe')
    handles = []
    original_open = Path.open

    def track_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if path.name == 'watch.spawn.log':
            handles.append(handle)
        return handle

    monkeypatch.setattr(Path, 'open', track_open)
    monkeypatch.setattr(supervisor_service.subprocess, 'Popen',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            OSError('simulated spawn failure')))
    with pytest.raises(OSError, match='simulated spawn failure'):
        supervisor_service._spawn_watch(root)
    assert not (service / 'watch.spawn.lock').exists()
    assert handles and handles[0].closed
