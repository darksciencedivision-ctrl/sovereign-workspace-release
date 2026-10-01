"""Supervisor launch failures must not retain parent-side log handles."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.freetoken_supervisor import (
    FreeTokenSupervisor, FreeTokenSupervisorConfig,
)
from sovereign_product.runtime_registry import RuntimeRegistry
from sovereign_product.runtime_supervisor import LlamaCppSupervisor, SupervisorConfig


@pytest.mark.parametrize('backend', ['llama', 'freetoken'])
def test_failed_runtime_spawn_closes_log(tmp_path, monkeypatch, backend):
    def fail_spawn(*_args, **_kwargs):
        raise OSError('simulated runtime spawn failure')

    if backend == 'llama':
        supervisor = LlamaCppSupervisor(
            SupervisorConfig(executable='missing', work_dir=str(tmp_path)),
            RuntimeRegistry(), popen=fail_spawn)
        monkeypatch.setattr(supervisor, 'render_preset', lambda: 'version = 1')
    else:
        supervisor = FreeTokenSupervisor(
            FreeTokenSupervisorConfig(executable='missing', model_path='model',
                                      work_dir=str(tmp_path)), popen=fail_spawn)
    monkeypatch.setattr(supervisor, '_assert_port_free', lambda: None)
    with pytest.raises(OSError, match='simulated runtime spawn failure'):
        supervisor.start()
    assert supervisor._log_handle is None or supervisor._log_handle.closed
    assert supervisor.process is None
