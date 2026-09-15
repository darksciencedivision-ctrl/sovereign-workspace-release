"""U458 — the two implementations of the envelope contract must agree ON BYTES, not by luck.

W-41 widened the signed input in `control_plane/ipc/envelope.py` from `payload` to the whole
envelope. `apps/desktop/ipc/envelope.js` is a SECOND implementation of the same contract — its own
header says *"The Python reference is authoritative; this file exists ONLY so the desktop shell
computes byte-identical envelopes and integrity tags"* — and it was not changed with the reference.
Both halves passed their own tests. The channel was dead in both directions: every envelope the
shell sent was refused by the gateway, and every reply the gateway sent was refused by the shell.

**Nothing in the tree compared the two implementations.** That is the gap this file closes, and it is
why the fixed vector below matters more than any single live test. Two implementations can agree by
accident on the flat ASCII payload the channel happens to carry today and diverge the next time
somebody sends a nested object, a non-ASCII string, or keys in an order the sender did not sort.
So the vector is chosen to be hostile on purpose: nested objects, non-ASCII, an array, a boolean, a
null, and top-level keys deliberately out of lexical order.

WHAT IS DELIBERATELY NOT IN THE VECTOR, because the Node module documents both as unrelied-on and
they would pin an agreement neither side promises: floats (Python emits `1.0`, JS emits `1`) and
astral-plane characters in KEYS (JS sorts by UTF-16 code unit, Python by code point). Astral
characters in VALUES are fine — both emit raw UTF-8 — and one is included, because the difference
between "unsafe in keys" and "unsafe anywhere" is exactly the sort of thing that gets forgotten.

Every answer from the Node side comes from the PRODUCTION module via `test/fixtures/envelope_probe.js`.
Nothing here reimplements canonicalization, the HMAC or the freshness rule in JavaScript: a probe that
did would agree with Python about a third thing and prove nothing about the shell.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from control_plane.ipc import envelope as env

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "apps" / "desktop" / "test" / "fixtures" / "envelope_probe.js"

#: One fixed secret both sides use. A vector under a random key would still compare equal and would
#: stop being a VECTOR — the point is that this exact input has this exact answer, reproducibly.
KEY_HEX = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"
KEY = bytes.fromhex(KEY_HEX)

#: Fixed instant, so `ts` is part of the vector rather than a source of drift.
VECTOR_TS = "2026-08-17T12:00:00+00:00"

#: The hostile envelope. Top-level keys are NOT in lexical order in this literal — both
#: canonicalizers must sort them, and a reader should be able to see that they were not pre-sorted.
GOLDEN: dict = {
    "type": "control_event",
    "msg_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    "from_node": "shell-1",
    "ts": VECTOR_TS,
    "schema": "envelope@1.0",
    "to": ["control-plane"],
    "task_id": None,
    "payload_schema": "control_event@1.0",
    "payload": {
        "op": "ping",
        "note": "nächste übergabe — 会议记录 \U0001f9ed",
        "nested": {"z": 1, "a": {"deep": [1, 2, {"y": False, "x": None}]}, "m": "é"},
        "flags": [True, False, None],
        "count": 42,
    },
    "auth": {"scope": "project", "node_credential": "tok-abc"},
}


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("host prerequisite missing: node on PATH — install Node.js")
    return node


def _probe(mode: str, envelope: dict, tmp_path: Path, *, now: str = "") -> dict:
    """Ask the PRODUCTION Node module a question about `envelope`. UTF-8 through a file, never
    through argv: the shell's code page is not a thing this contract should depend on."""
    p = tmp_path / f"{mode}.json"
    p.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    argv = [_node(), str(PROBE), mode, str(p), KEY_HEX] + ([now] if now else [])
    proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert proc.returncode == 0, f"probe {mode} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip())


def _signed_golden() -> dict:
    """The vector, signed by the PYTHON reference. This is the authoritative artifact."""
    e = dict(GOLDEN)
    e["integrity"] = env.compute_integrity(KEY, e)
    return e


# ---------------------------------------------------------------------------------------
# 1. the vector — canonical bytes, then the tag over them
# ---------------------------------------------------------------------------------------

def test_the_two_canonicalizers_produce_IDENTICAL_BYTES_for_the_vector(tmp_path) -> None:
    """The whole contract in one assertion. If these bytes differ, every signature differs."""
    expected = env.canonical_envelope(_signed_golden())
    got = _probe("canonical", _signed_golden(), tmp_path)
    assert got["hex"] == expected.hex(), (
        f"the Node and Python canonical forms of the SAME envelope differ ({got['why']}).\n"
        f"  python: {expected.decode('utf-8')}\n"
        f"  node  : {got['canonical']}")


def test_the_two_implementations_produce_the_SAME_HMAC_for_the_vector(tmp_path) -> None:
    """Byte equality above implies this, but it is asserted separately because they are different
    claims: one is about serialization, one is about what gets hashed. W-41 broke the second while
    leaving the first correct — `canonical_payload` was never wrong, the input handed to it was."""
    signed = _signed_golden()
    assert self_tag(signed) == _probe("tag", signed, tmp_path)["tag"], (
        "the two implementations disagree on the HMAC of the fixed vector")


def self_tag(signed: dict) -> str:
    return env.compute_integrity(KEY, signed)


def test_the_vector_is_actually_hostile() -> None:
    """A vector that does not exercise the divergences is a vector that cannot catch one. Asserted
    so a later 'simplification' of the literal above fails here instead of silently weakening it."""
    body = json.dumps(GOLDEN["payload"], ensure_ascii=False)
    assert not body.isascii(), "the vector lost its non-ASCII content"
    assert "\U0001f9ed" in body, "the vector lost its astral-plane character"
    assert "null" in body and "true" in body and "false" in body, "the vector lost null/bool"
    assert isinstance(GOLDEN["payload"]["nested"]["a"]["deep"], list), "the vector lost its array"
    top = [k for k in GOLDEN if k != "integrity"]
    assert top != sorted(top), "the vector's top-level keys were pre-sorted — sorting is untested"


# ---------------------------------------------------------------------------------------
# 2. both directions, through the production entry points
# ---------------------------------------------------------------------------------------

def test_PYTHON_mints_and_NODE_verifies(tmp_path) -> None:
    """The direction that broke the shell's reading of every gateway REPLY."""
    assert _probe("verify", _signed_golden(), tmp_path)["verified"] is True


def test_NODE_mints_and_PYTHON_verifies(tmp_path) -> None:
    """The direction that broke every REQUEST the shell sent. `makeEnvelope` mints its own `msg_id`
    and `ts`, so this is not the fixed vector — it is the real production minting path."""
    minted = _probe("mint", GOLDEN, tmp_path)["envelope"]
    env.validate_structure(minted)          # the gateway's first gate, applied here too
    assert env.verify_integrity(KEY, minted) is True


def test_a_node_minted_envelope_carries_the_ROUTING_fields_inside_its_signature(tmp_path) -> None:
    """Not inherited from the test above: that one only shows a valid envelope validates. This one
    shows the fields W-41 widened the signature to cover are genuinely covered ON THE NODE SIDE, by
    mutating each and watching the PYTHON verifier refuse.

    THE FIRST ASSERTION IS LOAD-BEARING AND WAS ADDED AFTER THIS TEST FALSELY PASSED PRE-REPAIR.
    Without it, a Node-minted envelope that Python refuses for ANY reason satisfies every `is False`
    below — a signature covering nothing passes a test about what the signature covers. Refusing the
    tampered forms only means something once the untampered form is accepted."""
    minted = _probe("mint", GOLDEN, tmp_path)["envelope"]
    assert env.verify_integrity(KEY, minted) is True, (
        "the UNTAMPERED Node-minted envelope does not verify, so the refusals below prove nothing")
    for field, value in [("from_node", "attacker"), ("type", "control_reply"),
                         ("task_id", "t-99"), ("msg_id", "00000000-0000-4000-8000-000000000000"),
                         ("ts", "2020-01-01T00:00:00+00:00"), ("payload_schema", "other@1.0")]:
        tampered = dict(minted)
        tampered[field] = value
        assert env.verify_integrity(KEY, tampered) is False, (
            f"a Node-minted envelope verified after {field!r} was rewritten — the Node signature "
            f"does not cover it")


# ---------------------------------------------------------------------------------------
# 3. freshness parity — the same instant must mean the same thing on both sides
# ---------------------------------------------------------------------------------------

def test_the_freshness_WINDOW_is_the_same_number_on_both_sides(tmp_path) -> None:
    """Pinned mechanically, by reading each side's constant. Two integers do not need a configuration
    subsystem to be shared, but they do need something that fails when they drift."""
    got = _probe("constants", GOLDEN, tmp_path)["freshness_window_s"]
    assert got is not None, "the Node module exports no freshness window"
    assert got == env.FRESHNESS_WINDOW_S


@pytest.mark.parametrize("offset_s, expected", [
    (0, True),                                   # now
    (env.FRESHNESS_WINDOW_S - 5, True),          # nearly stale, still inside the window
    (-(env.FRESHNESS_WINDOW_S - 5), True),       # nearly-future, still inside
    (env.FRESHNESS_WINDOW_S + 60, False),        # stale
    (-(env.FRESHNESS_WINDOW_S + 60), False),     # a clock running fast is as suspect as a stale one
])
def test_both_sides_agree_on_whether_an_instant_is_fresh(tmp_path, offset_s, expected) -> None:
    """TWO assertions, and the difference between them matters. The first is that the two
    implementations AGREE; the second is that Python's answer is the one the window actually
    implies. Agreement alone would certify two identically-wrong readers, and a table alone would
    certify neither — so both are checked."""
    now = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    stamped = (now - timedelta(seconds=offset_s)).isoformat()
    e = dict(GOLDEN, ts=stamped)
    e["integrity"] = env.compute_integrity(KEY, e)
    py_fresh = env.envelope_is_fresh(e, now=now)
    node_fresh = _probe("fresh", e, tmp_path, now=now.isoformat())["fresh"]
    assert node_fresh is not None, "the Node module has no freshness rule to agree with"
    assert node_fresh == py_fresh, (
        f"at an offset of {offset_s}s python says fresh={py_fresh} and node says fresh={node_fresh}")
    assert py_fresh is expected


def test_a_naive_timestamp_is_refused_by_both(tmp_path) -> None:
    """A timestamp with no zone has no defined instant. Refusing it is not pedantry: accepting it
    would make the window mean whatever the reader's local zone happens to be."""
    e = dict(GOLDEN, ts="2026-08-17T12:00:00")
    e["integrity"] = env.compute_integrity(KEY, e)
    now = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert env.envelope_is_fresh(e, now=now) is False
    assert _probe("fresh", e, tmp_path, now=now.isoformat())["fresh"] is False


def test_a_malformed_timestamp_is_refused_by_both(tmp_path) -> None:
    now = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    for bad in ("", "not-a-date", "2026-13-45T99:99:99+00:00"):
        e = dict(GOLDEN, ts=bad)
        e["integrity"] = env.compute_integrity(KEY, e)
        assert env.envelope_is_fresh(e, now=now) is False
        assert _probe("fresh", e, tmp_path, now=now.isoformat())["fresh"] is False
