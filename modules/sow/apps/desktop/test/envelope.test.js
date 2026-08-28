"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const crypto = require("node:crypto");
const env = require("../ipc/envelope");

const KEY = Buffer.from("0".repeat(64), "hex");

test("canonicalization is key-order independent (matches Python sort_keys)", () => {
  const a = env.canonicalPayload({ op: "ping", nonce: "x", z: 1 });
  const b = env.canonicalPayload({ z: 1, nonce: "x", op: "ping" });
  assert.strictEqual(a.toString("utf8"), b.toString("utf8"));
  assert.strictEqual(a.toString("utf8"), '{"nonce":"x","op":"ping","z":1}');
});

test("nested objects and arrays canonicalize deterministically", () => {
  const s = env.canonicalPayload({ b: [3, { y: 1, x: 2 }], a: "s" }).toString("utf8");
  assert.strictEqual(s, '{"a":"s","b":[3,{"x":2,"y":1}]}');
});

test("U458: integrity is a 64-hex hmac over the WHOLE envelope except integrity itself", () => {
  // This test used to read "over the canonical payload", and it passed for the whole time the
  // channel was dead: signing `{op,nonce}` alone and signing an envelope-shaped object with no
  // `integrity` key produce the same bytes, so the old assertion could not tell the two apart.
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping", nonce: "abc" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  assert.match(e.integrity, /^[0-9a-f]{64}$/);
  const body = { ...e };
  delete body.integrity;
  const expected = crypto.createHmac("sha256", KEY)
    .update(env.canonicalPayload(body)).digest("hex");
  assert.strictEqual(e.integrity, expected);
  // …and the payload-only tag is a DIFFERENT value, which is the thing the old test could not say.
  const payloadOnly = crypto.createHmac("sha256", KEY)
    .update('{"nonce":"abc","op":"ping"}').digest("hex");
  assert.notStrictEqual(e.integrity, payloadOnly,
    "the envelope tag equals the payload-only tag — the signature covers nothing but the payload");
});

test("canonicalEnvelope excludes integrity and nothing else", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  const canon = JSON.parse(env.canonicalEnvelope(e).toString("utf8"));
  assert.ok(!("integrity" in canon), "integrity must not sign itself");
  for (const k of ["msg_id", "ts", "schema", "from_node", "to", "type", "task_id",
    "payload_schema", "payload", "auth"]) {
    assert.ok(k in canon, `${k} is outside the signature — W-41's whole finding, on the Node side`);
  }
});

test("verifyIntegrity accepts a good tag and rejects a tampered payload (fail-closed)", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping", nonce: "n1" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  assert.strictEqual(env.verifyIntegrity(KEY, e), true);
  e.payload.nonce = "tampered";
  assert.strictEqual(env.verifyIntegrity(KEY, e), false);
});

// ---- U458: per-field tamper, on the NODE VERIFIER ------------------------------------------
// W-41 proved these six fields on the Python receiver. That was not enough: the shell is also a
// receiver — it verifies every gateway reply — and its verifier covered `payload` alone. So the
// same six are proven here, against the Node implementation, rather than counted as inherited.
for (const [field, value] of [
  ["from_node", "attacker"],
  ["type", "control_reply"],
  ["task_id", "t-99"],
  ["msg_id", "00000000-0000-4000-8000-000000000000"],
  ["ts", "2020-01-01T00:00:00.000Z"],
  ["payload_schema", "other@1.0"],
  ["schema", "envelope@2.0"],
]) {
  test(`U458: the Node verifier REFUSES an envelope whose ${field} was rewritten`, () => {
    const e = env.makeEnvelope({
      fromNode: "shell", to: ["control-plane"], msgType: "control_event",
      payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY, taskId: "t-1",
    });
    assert.strictEqual(env.verifyIntegrity(KEY, e), true,
      "the untampered envelope must verify, or the refusal below proves nothing");
    e[field] = value;
    assert.strictEqual(env.verifyIntegrity(KEY, e), false,
      `${field} was rewritten and the Node signature still verified`);
  });
}

test("U458: the Node verifier REFUSES an envelope whose auth block was rewritten", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  assert.strictEqual(env.verifyIntegrity(KEY, e), true);
  e.auth.scope = "everything";
  assert.strictEqual(env.verifyIntegrity(KEY, e), false);
});

test("U458: a missing or malformed integrity field is refused, never thrown on", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  for (const bad of [undefined, null, "", "zz", "0".repeat(64), 12345, {}]) {
    const t = { ...e, integrity: bad };
    assert.strictEqual(env.verifyIntegrity(KEY, t), false, `integrity=${JSON.stringify(bad)}`);
  }
  assert.strictEqual(env.verifyIntegrity(KEY, null), false);
});

// ---- U458: freshness, and its agreement with Python -----------------------------------------
test("U458: the freshness window is the value the Python reference uses", () => {
  assert.strictEqual(env.FRESHNESS_WINDOW_S, 300);
});

test("U458: a fresh, a stale and a future timestamp are read the way Python reads them", () => {
  const now = new Date("2026-08-17T12:00:00.000Z");
  const at = (offsetS) => new Date(now.getTime() - offsetS * 1000).toISOString();
  assert.strictEqual(env.envelopeIsFresh({ ts: at(0) }, { now }), true);
  assert.strictEqual(env.envelopeIsFresh({ ts: at(env.FRESHNESS_WINDOW_S - 5) }, { now }), true);
  assert.strictEqual(env.envelopeIsFresh({ ts: at(-(env.FRESHNESS_WINDOW_S - 5)) }, { now }), true);
  assert.strictEqual(env.envelopeIsFresh({ ts: at(env.FRESHNESS_WINDOW_S + 60) }, { now }), false);
  // A clock running fast is as suspect as a stale one — otherwise a sender mints envelopes with an
  // arbitrarily long life just by being wrong about the time in the convenient direction.
  assert.strictEqual(env.envelopeIsFresh({ ts: at(-(env.FRESHNESS_WINDOW_S + 60)) }, { now }), false);
});

test("U458: a NAIVE timestamp is refused — JS would otherwise read it as local time", () => {
  const now = new Date("2026-08-17T12:00:00.000Z");
  // Date.parse would happily answer for this, in whatever zone the reader sits in, so the window
  // would mean something different on every host. Python refuses it; so must this.
  assert.strictEqual(env.envelopeIsFresh({ ts: "2026-08-17T12:00:00" }, { now }), false);
});

test("U458: an absent or unparseable timestamp is refused", () => {
  const now = new Date("2026-08-17T12:00:00.000Z");
  for (const bad of [undefined, null, "", "not-a-date", 1755432000000,
    "2026-13-45T99:99:99+00:00"]) {
    assert.strictEqual(env.envelopeIsFresh({ ts: bad }, { now }), false, `ts=${JSON.stringify(bad)}`);
  }
  assert.strictEqual(env.envelopeIsFresh(null, { now }), false);
});

test("U458: both offset spellings Python accepts are accepted here too", () => {
  const now = new Date("2026-08-17T12:00:00.000Z");
  for (const ts of ["2026-08-17T12:00:00Z", "2026-08-17T12:00:00+00:00",
    "2026-08-17T12:00:00.123456+00:00", "2026-08-17T13:00:00+01:00"]) {
    assert.strictEqual(env.envelopeIsFresh({ ts }, { now }), true, ts);
  }
});

test("a wrong key does not verify", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY,
  });
  assert.strictEqual(env.verifyIntegrity(crypto.randomBytes(32), e), false);
});

test("makeEnvelope produces a schema-shaped envelope@1.0", () => {
  const e = env.makeEnvelope({
    fromNode: "shell", to: ["control-plane"], msgType: "control_event",
    payload: { op: "ping" }, nodeCredential: "tok", scope: "project", key: KEY, taskId: null,
  });
  assert.strictEqual(e.schema, "envelope@1.0");
  assert.match(e.msg_id, /^[0-9a-f-]{36}$/);
  assert.match(e.payload_schema, /^[a-z_]+@[0-9]+\.[0-9]+$/);
  assert.deepStrictEqual(e.to, ["control-plane"]);
  assert.deepStrictEqual(Object.keys(e.auth).sort(), ["node_credential", "scope"]);
  assert.match(e.integrity, /^[0-9a-f]{64}$/);
});
