"""Bound malformed local model streams before they can exhaust client memory."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import model_client, llama_cpp_client
from sovereign_product.model_client import GenerationOverLimit


def test_unterminated_stream_line_is_bounded(monkeypatch):
    monkeypatch.setattr(model_client, '_MAX_STREAM_LINE_BYTES', 16, raising=False)

    class Response:
        def iter_content(self, **_kwargs):
            yield b'x' * 10
            yield b'x' * 10

    with pytest.raises(GenerationOverLimit):
        list(model_client.stream_lines(Response()))


class Stream:
    status_code = 200
    closed = False

    def iter_lines(self, **_kwargs):
        for _ in range(3):
            yield 'data: ' + json.dumps({'model': 'test', 'choices': [
                {'delta': {'content': 'answer'}}]})
        yield 'data: [DONE]'

    def raise_for_status(self):
        pass

    def close(self):
        self.closed = True


@pytest.mark.parametrize('limit_name,limit', [('_MAX_STREAM_EVENTS', 2),
                                            ('_MAX_STREAM_BYTES', 4)])
def test_llama_stream_limits_close_response_and_keep_partial(monkeypatch, limit_name, limit):
    monkeypatch.setattr(llama_cpp_client, limit_name, limit, raising=False)
    stream = Stream()

    class Session:
        def request(self, *_args, **_kwargs):
            return stream

    client = llama_cpp_client.LlamaCppClient(session=Session())
    with pytest.raises(GenerationOverLimit) as caught:
        client.chat(model='test', messages=[{'role': 'user', 'content': 'hello'}])
    assert stream.closed
    assert isinstance(caught.value.partial_response, dict)


def test_tool_call_index_cannot_expand_an_unbounded_sparse_list():
    calls = []
    with pytest.raises(GenerationOverLimit):
        llama_cpp_client._merge_tool_calls(calls, [{'index': 129, 'function': {}}])
    assert calls == []
