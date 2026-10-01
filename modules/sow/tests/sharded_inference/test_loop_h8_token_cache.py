from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.llama_cpp_client import LlamaCppClient
from sovereign_product.model_client import ModelClientError


def instrument(monkeypatch):
    client = LlamaCppClient()
    calls = []
    def tokenize(path, body):
        calls.append((path, dict(body)))
        return {'tokens': list(range(len(body['content'])))}
    monkeypatch.setattr(client, '_post_json_timed', tokenize)
    return client, calls


def test_identical_text_avoids_http_and_preserves_endpoint_telemetry(monkeypatch):
    client, calls = instrument(monkeypatch)
    assert client.count_text_tokens('model', 'prefix') == 6
    assert client.count_text_tokens('model', 'prefix') == 6
    assert len(calls) == 1
    assert client.endpoint_stats['/tokenize'][0] == 1


def test_changed_text_or_model_is_not_reused(monkeypatch):
    client, calls = instrument(monkeypatch)
    assert client.count_text_tokens('one', 'prefix') == 6
    assert client.count_text_tokens('one', 'prefix changed') == 14
    assert client.count_text_tokens('two', 'prefix') == 6
    assert len(calls) == 3


def test_bounded_cache_evicts_oldest_and_reuses_recent(monkeypatch):
    client, calls = instrument(monkeypatch)
    for i in range(257):
        client.count_text_tokens('model', str(i))
    client.count_text_tokens('model', '256')
    assert len(calls) == 257
    client.count_text_tokens('model', '0')
    assert len(calls) == 258


def test_failed_tokenization_is_retried(monkeypatch):
    client, calls = instrument(monkeypatch)
    def fail(path, body):
        raise ModelClientError('offline test failure')
    original = client._post_json_timed
    monkeypatch.setattr(client, '_post_json_timed', fail)
    assert client.count_text_tokens('model', 'prefix') is None
    monkeypatch.setattr(client, '_post_json_timed', original)
    assert client.count_text_tokens('model', 'prefix') == 6
    assert len(calls) == 1


def test_invalid_result_is_retried_and_empty_text_count_is_cached(monkeypatch):
    client, calls = instrument(monkeypatch)
    original = client._post_json_timed
    monkeypatch.setattr(client, '_post_json_timed', lambda *args: {'tokens': None})
    assert client.count_text_tokens('model', '') is None
    monkeypatch.setattr(client, '_post_json_timed', original)
    assert client.count_text_tokens('model', '') == 0
    assert client.count_text_tokens('model', '') == 0
    assert len(calls) == 1
