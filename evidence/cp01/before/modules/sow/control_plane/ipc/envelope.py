"""Control-protocol envelope: schema validation + hmac-sha256 integrity (Plan 9.2, TB-2).

Envelopes are the ONLY control channel. Two independent checks make a message trustworthy,
and BOTH must pass before anything acts on it (fail-closed):

  1. structural: it validates against ``schemas/message.schema.json`` (``envelope@1.0``);
  2. integrity: ``integrity == hmac_sha256(shared_key, canonical(payload))`` — verified with
     a constant-time compare so a wrong signature cannot advance.

The message schema pins ``integrity`` to 64 hex chars but nothing in the tree computed the
HMAC until now; this module is that missing compute/verify pair. Canonicalization mirrors the
succession-snapshot convention (sorted keys, UTF-8) so signer and verifier agree byte-for-byte.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_ENVELOPE_SCHEMA = json.loads((_SCHEMA_DIR / "message.schema.json").read_text(encoding="utf-8"))
_FMT = jsonschema.FormatChecker()  # enforce uuid/date-time formats (spec-audit F12 convention)
_VALIDATOR = jsonschema.Draft7Validator(_ENVELOPE_SCHEMA, format_checker=_FMT)


class EnvelopeError(Exception):
    """Envelope failed structural validation or integrity — fail closed, do not act on it."""


def canonical_payload(payload: dict[str, Any]) -> bytes:
    """Byte form the HMAC is taken over. Deterministic: sorted keys, compact, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


#: How long a signed envelope may be acted on. W-41: the `ts` is INSIDE the signature, so this is a
#: bound and not merely a claim the sender makes about itself. It is also what lets the replay cache
#: be bounded — an entry older than this can be dropped, because a replay of it now fails here.
FRESHNESS_WINDOW_S = 300


def canonical_envelope(envelope: dict[str, Any]) -> bytes:
    """Byte form the HMAC is taken over: the WHOLE envelope except `integrity` itself.

    W-41. This used to sign `payload` alone, so `from_node`, `type`, `task_id`, `msg_id` and `ts`
    were all rewritable in flight while the HMAC still verified — the routing and identity of a
    message were unauthenticated.

    It reuses `canonical_payload` rather than serialising separately. Two canonicalizations that
    disagree is a signature bypass, so there is exactly one serializer in this module and this
    function only decides WHAT is handed to it.
    """
    return canonical_payload({k: v for k, v in envelope.items() if k != "integrity"})


def compute_integrity(key: bytes, envelope: dict[str, Any]) -> str:
    return hmac.new(key, canonical_envelope(envelope), hashlib.sha256).hexdigest()


def verify_integrity(key: bytes, envelope: dict[str, Any]) -> bool:
    expected = compute_integrity(key, envelope)
    return hmac.compare_digest(expected, str(envelope.get("integrity", "")))


def envelope_is_fresh(envelope: dict[str, Any], *, now: datetime | None = None,
                      window_s: int = FRESHNESS_WINDOW_S) -> bool:
    """Is the SIGNED `ts` inside the freshness window? Fail closed on anything unparseable.

    Checked in BOTH directions: an envelope from the future is as suspect as a stale one, and a
    sender whose clock runs fast would otherwise mint envelopes with an arbitrarily long life.
    """
    raw = envelope.get("ts")
    if not isinstance(raw, str):
        return False
    try:
        stamped = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if stamped.tzinfo is None:
        return False                      # a naive timestamp has no defined instant; refuse it
    reference = now or datetime.now(timezone.utc)
    return abs((reference - stamped).total_seconds()) <= window_s


def validate_structure(envelope: dict[str, Any]) -> None:
    """Raise EnvelopeError unless the object is a well-formed envelope@1.0."""
    errors = sorted(_VALIDATOR.iter_errors(envelope), key=lambda e: e.path)
    if errors:
        raise EnvelopeError(f"envelope failed schema: {errors[0].message}")


def make_envelope(
    *,
    from_node: str,
    to: list[str],
    msg_type: str,
    payload: dict[str, Any],
    node_credential: str,
    scope: str,
    key: bytes,
    task_id: str | None = None,
    payload_schema: str = "control_event@1.0",
) -> dict[str, Any]:
    """Build a fully-signed envelope. The integrity field is computed here, not by callers."""
    envelope = {
        "msg_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "schema": "envelope@1.0",
        "from_node": from_node,
        "to": to,
        "type": msg_type,
        "task_id": task_id,
        "payload_schema": payload_schema,
        "payload": payload,
        "auth": {"node_credential": node_credential, "scope": scope},
    }
    # W-41: signed AFTER assembly, over the whole envelope. Computing it inline above would have
    # signed a dict that did not yet contain the fields the signature is supposed to cover.
    envelope["integrity"] = compute_integrity(key, envelope)
    validate_structure(envelope)  # never emit a malformed envelope
    return envelope
