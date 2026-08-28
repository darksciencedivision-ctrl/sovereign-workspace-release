"use strict";
/**
 * Node mirror of control_plane/ipc/envelope.py — the shell side of the D-IPC-01 contract.
 *
 * The Python reference is authoritative; this file exists ONLY so the desktop shell
 * (a Node/Chromium main process) computes byte-identical envelopes and integrity tags.
 * Two independent checks must pass before anything acts on a message (fail-closed):
 *   1. structural: it is a well-formed envelope@1.0 (the gateway re-validates against
 *      schemas/message.schema.json — we build to that shape, never trust our own claim);
 *   2. integrity: integrity === hmac_sha256(shared_key, canonical(envelope minus integrity)).
 *
 * U458 — WHY (2) NOW SAYS "envelope" AND NOT "payload". W-41 widened the signed input in the Python
 * reference from `payload` to the whole envelope, so `from_node`, `type`, `task_id`, `msg_id` and
 * `ts` stopped being rewritable in flight. THIS FILE WAS NOT CHANGED WITH IT. Both halves passed
 * their own tests and the channel was dead in both directions: every envelope the shell sent was
 * refused by the gateway, and every reply the gateway sent was refused here. The serializer was
 * never wrong — `canonicalPayload` and Python's `canonical_payload` agree byte-for-byte on nested
 * objects, non-ASCII and key order. What was wrong was WHAT GOT HANDED TO IT.
 *
 * The lesson is written down here because this file is where it will be needed again: this module
 * is one half of a two-sided protocol, and a change to either half is a change to the contract.
 * `tests/unit/test_envelope_cross_language_parity.py` is the instrument that now fails when they
 * drift — it compares these functions' real output against the Python reference's on a fixed
 * hostile vector, so agreement is measured rather than assumed.
 *
 * Canonicalization matches Python's json.dumps(payload, sort_keys=True,
 * separators=(",",":"), ensure_ascii=False) for the payloads this channel actually carries:
 * objects with string keys and string/bool/int-or-null values (control ops). It is verified
 * byte-for-byte against the real Python gateway by the round-trip test (a Node-signed
 * envelope is accepted, and the gateway's reply verifies under the same key).
 *
 * Known, deliberately-unrelied-on edges where JS and Python could differ — and where the
 * difference is SAFE because it only makes a signature fail to verify (fail-closed): floats
 * (Python emits "1.0", JS "1") and astral-plane object keys (UTF-16 vs code-point sort).
 * This channel sends neither; if a future op needs them, add a cross-language numeric test
 * before relying on the tag rather than trusting these two encoders to agree.
 */
const crypto = require("node:crypto");

/** Deterministic canonical form the HMAC is taken over. Mirrors Python's sorted-key,
 *  compact, UTF-8 encoding exactly (recursively sorted object keys). */
function canonicalPayload(payload) {
  return Buffer.from(_canonicalize(payload), "utf8");
}

function _canonicalize(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(_canonicalize).join(",") + "]";
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + _canonicalize(value[k])).join(",") + "}";
}

/**
 * The bytes the HMAC is taken over: the WHOLE envelope except `integrity` itself. Mirrors Python's
 * `canonical_envelope`, including the decision to REUSE the one serializer rather than write a
 * second — two canonicalizations that can disagree is a signature bypass, and having two of them
 * per language would be four.
 */
function canonicalEnvelope(envelope) {
  const body = { ...(envelope || {}) };
  delete body.integrity;
  return canonicalPayload(body);
}

/** Mirrors Python's `compute_integrity(key, envelope)` — note the argument is the ENVELOPE. */
function computeIntegrity(key, envelope) {
  return crypto.createHmac("sha256", key).update(canonicalEnvelope(envelope)).digest("hex");
}

/** Constant-time verification — a wrong signature cannot advance (mirrors hmac.compare_digest). */
function verifyIntegrity(key, envelope) {
  const expected = computeIntegrity(key, envelope);
  const got = String((envelope && envelope.integrity) || "");
  if (expected.length !== got.length) return false;
  return crypto.timingSafeEqual(Buffer.from(expected, "utf8"), Buffer.from(got, "utf8"));
}

/**
 * How long a signed envelope may be acted on. Mirrors Python's `FRESHNESS_WINDOW_S`; the two are
 * pinned equal MECHANICALLY by the cross-language test, which reads both rather than trusting this
 * comment. Two integers do not need a configuration subsystem to stay in step — they need something
 * that fails when they stop being in step.
 */
const FRESHNESS_WINDOW_S = 300;

//: A timestamp with no zone designator has no defined instant, and JS would silently read it as
//: LOCAL time — so the window would mean whatever zone the reader happens to sit in. Python's
//: `fromisoformat` path refuses naive timestamps explicitly; this is that refusal, and it has to be
//: a syntax check because `Date.parse` will happily invent an answer. Accepts what Python 3.12
//: accepts: `Z`, `+HH`, `+HHMM`, `+HH:MM`.
const HAS_ZONE = /(?:[Zz]|[+-]\d{2}(?::?\d{2})?)$/;

/**
 * Is the SIGNED `ts` inside the freshness window? Fail closed on anything unparseable.
 *
 * Checked in BOTH directions, as Python does: an envelope from the future is as suspect as a stale
 * one, since a sender whose clock runs fast would otherwise mint envelopes with an arbitrarily long
 * life.
 */
function envelopeIsFresh(envelope, { now = null, windowS = FRESHNESS_WINDOW_S } = {}) {
  const raw = envelope && envelope.ts;
  if (typeof raw !== "string" || !HAS_ZONE.test(raw)) return false;
  const stamped = Date.parse(raw);
  if (Number.isNaN(stamped)) return false;
  const reference = now instanceof Date ? now.getTime() : Date.now();
  if (Number.isNaN(reference)) return false;
  return Math.abs(reference - stamped) <= windowS * 1000;
}

/** The envelope's fields, before it is signed. Split out so the signature is taken over the
 *  assembled object rather than computed inside the literal that builds it. */
function _unsignedEnvelope({ fromNode, to, msgType, payload, nodeCredential, scope,
                             taskId = null, payloadSchema = "control_event@1.0" }) {
  return {
    msg_id: crypto.randomUUID(),
    ts: new Date().toISOString(),
    schema: "envelope@1.0",
    from_node: fromNode,
    to,
    type: msgType,
    task_id: taskId,
    payload_schema: payloadSchema,
    payload,
    auth: { node_credential: nodeCredential, scope },
  };
}

/** Build a fully-signed envelope. integrity is computed here, never by callers. */
function makeEnvelope(spec) {
  // U458: assembled FIRST, then signed over itself. Computing the tag inline in the literal above
  // is what made the payload-only signature so easy to write and so hard to see — the object being
  // signed did not yet contain the fields the signature is supposed to cover. Python's
  // `make_envelope` was restructured the same way for the same reason.
  const envelope = _unsignedEnvelope(spec);
  envelope.integrity = computeIntegrity(spec.key, envelope);
  return envelope;
}

module.exports = {
  canonicalPayload, canonicalEnvelope, computeIntegrity, verifyIntegrity, makeEnvelope,
  envelopeIsFresh, FRESHNESS_WINDOW_S,
};
