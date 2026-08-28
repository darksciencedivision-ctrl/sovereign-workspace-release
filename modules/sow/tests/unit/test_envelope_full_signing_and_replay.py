"""W-41 — the envelope's routing and identity fields were unauthenticated, and it replayed.

`compute_integrity` HMAC'd `canonical_payload(payload)` and NOTHING ELSE, and `verify_integrity`
recomputed over `envelope["payload"]` alone. The envelope carries `msg_id`, `ts`, `schema`,
`from_node`, `to`, `type`, `task_id`, `payload_schema`, `payload` and `auth` — so every routing and
identity field outside `payload` could be rewritten in flight and the HMAC still verified. With no
nonce or freshness bound, a captured envelope also replayed verbatim.

DESIGN (operator ruling): a SIGNED TIMESTAMP plus a BOUNDED REPLAY CACHE keyed on
`(from_node, msg_id)`. Not per-node monotonic sequences — those would add durable state,
rehydration, restart semantics, allocation and out-of-order handling, which is a distributed
protocol calling itself replay protection. The envelope already carries both primitives it needs:
`msg_id` for uniqueness and `ts` for bounded lifetime.

THE VERIFICATION ORDER IS THE RULING, and two steps in it are load-bearing:

  shape → HMAC over the whole envelope except `integrity` → constant-time compare → signed `ts`
  inside the freshness window → `(from_node, msg_id)` against the cache → RECORD → dispatch

  * Nothing may enter the cache before integrity AND timestamp pass, or unauthenticated traffic
    poisons it — an attacker could burn a `msg_id` the genuine sender is about to use.
  * Nothing may dispatch before the identity is recorded, or two concurrent copies each clear the
    lookup before either records.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.ipc import envelope as env
from control_plane.ipc.gateway import EchoControlSurface, IpcCredentialStore, IpcGateway

NODE = "worker-1"


@pytest.fixture()
def signed():
    store = IpcCredentialStore()
    token, key = store.issue(NODE, "worker", "proj")
    gateway = IpcGateway(store, EchoControlSurface())

    def make(**over):
        e = env.make_envelope(
            from_node=NODE, to=["control-plane"], msg_type="control_event",
            payload={"op": "ping"}, node_credential=token, scope="node", key=key,
        )
        e.update(over)
        return e

    return gateway, key, make


def _authenticate(gateway, e):
    return gateway._authenticate(env._json_dumps(e) if hasattr(env, "_json_dumps") else __import__("json").dumps(e))


# ---- 1-6: every signed field, mutated ----------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("from_node", "someone-else"),
    ("type", "control_event_evil"),
    ("task_id", "t-hijacked"),
    ("msg_id", "00000000-0000-4000-8000-000000000000"),
    ("ts", (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()),
])
def test_mutating_a_signed_field_is_REFUSED(signed, field, value) -> None:
    """NEGATIVE: each of these was rewritable in flight while the HMAC still verified."""
    gateway, _key, make = signed
    e = make()
    e[field] = value
    result = _authenticate(gateway, e)
    assert isinstance(result, str), f"a mutated {field} was ACCEPTED — it is outside the signature"


def test_mutating_the_payload_is_REFUSED(signed) -> None:
    """NEGATIVE: the one field the old HMAC did cover. It must stay covered."""
    gateway, _key, make = signed
    e = make()
    e["payload"] = {"op": "rm -rf"}
    assert isinstance(_authenticate(gateway, e), str)


# ---- 7-8: replay, and the valid case -----------------------------------------------------------

def test_a_valid_fresh_envelope_is_ACCEPTED(signed) -> None:
    """POSITIVE: the whole unit is worthless if it refuses legitimate traffic."""
    gateway, _key, make = signed
    result = _authenticate(gateway, make())
    assert not isinstance(result, str), f"a legitimate envelope was refused: {result}"


def test_replaying_an_IDENTICAL_authenticated_envelope_is_REFUSED(signed) -> None:
    """NEGATIVE: the captured-and-resent case. The first must pass, the second must not."""
    gateway, _key, make = signed
    e = make()
    first = _authenticate(gateway, e)
    assert not isinstance(first, str), f"the genuine first delivery was refused: {first}"
    second = _authenticate(gateway, copy.deepcopy(e))
    assert isinstance(second, str), "an identical authenticated envelope replayed successfully"


# ---- 9: freshness --------------------------------------------------------------------------

def test_an_envelope_outside_the_freshness_window_is_REFUSED(signed) -> None:
    """NEGATIVE: the `ts` is signed, so this is not merely a stale-looking claim — it is a bound.

    Without it the replay cache would have to remember every msg_id forever to stay correct.
    """
    gateway, key, make = signed
    old = (datetime.now(timezone.utc) - timedelta(seconds=env.FRESHNESS_WINDOW_S + 60)).isoformat()
    e = make()
    e["ts"] = old
    e["integrity"] = env.compute_integrity(key, e)      # correctly signed, genuinely old
    result = _authenticate(gateway, e)
    assert isinstance(result, str), "an envelope older than the freshness window was accepted"


# ---- 10: cache poisoning ---------------------------------------------------------------------

def test_a_BAD_HMAC_envelope_cannot_burn_a_msg_id_the_genuine_sender_will_use(signed) -> None:
    """NEGATIVE, the ordering property: nothing enters the cache before integrity passes.

    An attacker who can guess or observe a `msg_id` must not be able to pre-register it and have the
    genuine envelope refused as a replay. This is why the cache write sits AFTER verification in the
    ruled order, and it is the test that fails if someone 'optimises' by recording early.
    """
    gateway, _key, make = signed
    genuine = make()

    forged = copy.deepcopy(genuine)
    forged["integrity"] = "0" * 64                      # same msg_id, bad HMAC
    assert isinstance(_authenticate(gateway, forged), str), "a forged envelope authenticated"

    result = _authenticate(gateway, genuine)
    assert not isinstance(result, str), (
        "the genuine envelope was refused after a FORGED one used its msg_id — the replay cache "
        "was written before integrity was verified, so unauthenticated traffic can poison it"
    )


def test_the_signature_covers_the_envelope_via_ONE_canonical_serializer() -> None:
    """Two canonicalizations that disagree is a signature bypass, so there must only be one.

    Asserted structurally rather than by inspection: the envelope byte form must be produced by the
    same `canonical_payload` the project already had.
    """
    import inspect

    source = inspect.getsource(env.canonical_envelope)
    assert "canonical_payload" in source, (
        "canonical_envelope does not reuse canonical_payload — a second serializer was authored"
    )
    e = {"a": 1, "integrity": "deadbeef", "z": 2}
    assert b"integrity" not in env.canonical_envelope(e), "the integrity field must not sign itself"
