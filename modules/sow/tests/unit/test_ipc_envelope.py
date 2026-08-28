"""Phase 14A / D-IPC-01: envelope schema validation + hmac-sha256 integrity."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from control_plane.ipc import envelope as env

KEY = b"k" * 32


def _valid() -> dict:
    return env.make_envelope(
        from_node="shell-1", to=["control-plane"], msg_type="control_event",
        payload={"op": "ping", "nonce": "abc"}, node_credential="tok", scope="project", key=KEY,
    )


def test_make_envelope_is_schema_valid() -> None:
    env.validate_structure(_valid())  # must not raise


def test_integrity_matches_manual_hmac() -> None:
    payload = {"b": 2, "a": 1}
    expected = hmac.new(KEY, env.canonical_payload(payload), hashlib.sha256).hexdigest()
    assert env.compute_integrity(KEY, payload) == expected


def test_canonical_payload_is_key_order_independent() -> None:
    assert env.canonical_payload({"a": 1, "b": 2}) == env.canonical_payload({"b": 2, "a": 1})


def test_verify_integrity_true_for_correct_key() -> None:
    assert env.verify_integrity(KEY, _valid())


def test_verify_integrity_false_for_wrong_key() -> None:
    assert not env.verify_integrity(b"x" * 32, _valid())


def test_verify_integrity_false_when_payload_tampered() -> None:
    e = _valid()
    e["payload"]["op"] = "escalate"  # tamper after signing
    assert not env.verify_integrity(KEY, e)


def test_missing_required_field_rejected() -> None:
    e = _valid()
    del e["integrity"]
    with pytest.raises(env.EnvelopeError):
        env.validate_structure(e)


def test_bad_integrity_pattern_rejected() -> None:
    e = _valid()
    e["integrity"] = "NOT-HEX"
    with pytest.raises(env.EnvelopeError):
        env.validate_structure(e)


def test_additional_property_rejected() -> None:
    e = _valid()
    e["surprise"] = True
    with pytest.raises(env.EnvelopeError):
        env.validate_structure(e)


def test_bad_payload_schema_pattern_rejected() -> None:
    with pytest.raises(env.EnvelopeError):
        # make_envelope validates before returning, so a bad payload_schema must be caught
        env.make_envelope(
            from_node="n", to=["s"], msg_type="control_event", payload={}, node_credential="t",
            scope="p", key=KEY, payload_schema="BadSchema",  # violates ^[a-z_]+@[0-9]+\.[0-9]+$
        )
