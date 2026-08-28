"""W-36 (Python half) — a local daemon's reply is input, and `ollama_models` treated it as truth.

`adapters/detect.py:23-29` builds `[m["name"] for m in data.get("models", [])]` and catches only
`URLError`, `OSError` and `JSONDecodeError`. Two things follow:

  * a well-formed JSON reply whose entries are not dicts, or lack `name`, raises `TypeError` /
    `KeyError` STRAIGHT PAST the handler. Detection is supposed to answer "is a local backend
    available"; it is not supposed to be able to crash its caller.
  * whatever strings it does return are passed on unvalidated, and a model name eventually reaches
    a `--model` argument. `MODEL_SLUG_RE` already exists as the project's answer to what a model
    name may look like and was simply not applied here.

SCOPE, so this is not read as more than it is: the daemon is on loopback and this is not a remote
attacker. What it closes is a malformed or upgraded daemon taking the caller down with it, and an
unconstrained string travelling toward an argv. The related "no argv builder validates a `--model`
value" surface is W-51 and is NOT addressed here.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from adapters import detect
from adapters.frontier.provider_cli_common import MODEL_SLUG_RE


class _Reply:
    """The context-manager shape `urllib.request.urlopen` returns."""

    def __init__(self, payload: Any) -> None:
        self._raw = (payload if isinstance(payload, (bytes, str)) else json.dumps(payload))

    def __enter__(self) -> "_Reply":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        raw = self._raw
        return raw.encode("utf-8") if isinstance(raw, str) else raw


def _with_reply(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    monkeypatch.setattr(detect.urllib.request, "urlopen", lambda *_a, **_k: _Reply(payload))


def test_a_model_entry_that_is_not_an_object_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEGATIVE: `TypeError` from `m["name"]` on a string entry escaped the handler entirely."""
    _with_reply(monkeypatch, {"models": ["qwen3:8b", {"name": "phi4:14b"}]})
    assert detect.ollama_models() == ["phi4:14b"], (
        "a malformed entry must be dropped, not raised past the caller, and not silently taken as a "
        "name"
    )


def test_a_model_entry_missing_name_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEGATIVE: `KeyError` from a dict with no `name`."""
    _with_reply(monkeypatch, {"models": [{"model": "qwen3:8b"}, {"name": "phi4:14b"}]})
    assert detect.ollama_models() == ["phi4:14b"]


def test_a_reply_that_is_not_an_object_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEGATIVE: `data.get` on a list raises `AttributeError`, which the handler also missed."""
    _with_reply(monkeypatch, ["not", "an", "object"])
    assert detect.ollama_models() == []


def test_model_names_are_validated_against_the_project_slug_rule(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """NEGATIVE: an unconstrained name travels toward a `--model` argument.

    The rejected values are chosen to be things a name must never be able to carry: a flag, an
    argument separator, whitespace, and a shell metacharacter.
    """
    _with_reply(monkeypatch, {"models": [
        {"name": "qwen3:8b"},                 # legal
        {"name": "--version"},                # a flag, not a model
        {"name": "a b"},                      # whitespace splits an argv
        {"name": "x&calc"},                   # metacharacter
        {"name": ""},                         # empty
        {"name": "q" * 200},                  # past the length bound
    ]})
    assert detect.ollama_models() == ["qwen3:8b"]


def test_the_validation_is_the_projects_existing_rule_not_a_new_one() -> None:
    """The rule must be `MODEL_SLUG_RE`, not a second opinion about model names.

    A private regex here would be a fork of a decision the project already made once, and the two
    would drift the way the credential lists nearly did at W-32.
    """
    import inspect

    source = inspect.getsource(detect.ollama_models)
    assert "MODEL_SLUG_RE" in source, "validation must reuse the existing authority"


def test_a_well_formed_reply_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """POSITIVE: the ordinary path must be untouched — this passes before the repair too."""
    _with_reply(monkeypatch, {"models": [{"name": "qwen3:8b"}, {"name": "phi4:14b"}]})
    assert detect.ollama_models() == ["qwen3:8b", "phi4:14b"]


def test_every_returned_name_satisfies_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property stated directly, rather than only through examples."""
    _with_reply(monkeypatch, {"models": [
        {"name": "qwen3:8b"}, {"name": "bad name"}, {"name": "phi4:14b"}, {"name": "--flag"},
    ]})
    for name in detect.ollama_models():
        assert MODEL_SLUG_RE.match(name), f"{name!r} escaped the slug rule"
