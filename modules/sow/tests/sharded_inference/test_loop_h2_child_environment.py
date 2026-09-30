"""A legacy runner receives configuration, never arbitrary parent credentials."""
from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.executors import DeepExecutor


@pytest.mark.parametrize('secret', ['OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY',
                                    'SOVEREIGN_LLAMA_CPP_API_KEY', 'SOVEREIGN_UNKNOWN_TOKEN',
                                    'PYTHON_PRIVATE_SECRET'])
def test_parent_secret_not_in_runner_environment(tmp_path, monkeypatch, secret):
    monkeypatch.setattr(os, 'environ', {})
    monkeypatch.setenv(secret, 'synthetic-secret-do-not-inherit')
    calls = []
    executor = DeepExecutor(tmp_path, popen_factory=lambda *args, **kwargs: calls.append(kwargs))
    executor._launch(['python', 'runner.py'])
    assert secret not in calls[0]['env']
    assert 'synthetic-secret-do-not-inherit' not in calls[0]['env'].values()


def test_required_launch_and_runner_configuration_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'environ', {})
    expected = {'PATH': 'test-path', 'SystemRoot': 'test-system', 'TEMP': str(tmp_path),
                'PYTHONPATH': 'test-python-path', 'PYTHONDONTWRITEBYTECODE': '1',
                'SOVEREIGN_STATE_HOME': str(tmp_path / 'state'),
                'SOVEREIGN_TURN_TIMEOUT_SEC': '120', 'SOVEREIGN_COGNITION_ROOT': str(tmp_path)}
    for key, value in expected.items():
        monkeypatch.setenv(key, value)
    calls = []
    executor = DeepExecutor(tmp_path, popen_factory=lambda *args, **kwargs: calls.append(kwargs))
    executor._launch(['python', 'runner.py'])
    environment = {key.upper(): value for key, value in calls[0]['env'].items()}
    assert all(environment[key.upper()] == value for key, value in expected.items())
    assert environment['PYTHONUNBUFFERED'] == '1'
