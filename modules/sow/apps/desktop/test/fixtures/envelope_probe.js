"use strict";
/**
 * Cross-language probe for the envelope contract — the Node half of U458's parity evidence.
 *
 * WHY THIS EXISTS. `apps/desktop/ipc/envelope.js` is a second implementation of
 * `control_plane/ipc/envelope.py`. W-41 changed the Python reference to sign the WHOLE envelope and
 * did not change the Node mirror, which kept signing `payload` alone. Both sides passed their own
 * tests; the CHANNEL was dead. Nothing in the tree compared the two implementations' bytes, so
 * nothing could have caught it. This probe is that comparison's Node end.
 *
 * IT CALLS THE PRODUCTION SERIALIZER AND NOTHING ELSE. There is no canonicalization, no HMAC and no
 * freshness rule written in this file — every answer below is whatever `../../ipc/envelope` says
 * today. A probe that reimplemented any of it would agree with Python about a third thing and prove
 * nothing about the shell.
 *
 *   node envelope_probe.js <mode> <envelope.json> [key-hex] [now-iso]
 *
 * Modes, each printing ONE line of JSON on stdout:
 *   canonical  {"canonical": <utf8 string the production signer hashes>, "hex": ...}
 *   tag        {"tag": "<64 hex>"}            — production computeIntegrity over the given envelope
 *   verify     {"verified": true|false}       — production verifyIntegrity of the given envelope
 *   mint       {"envelope": {...}}            — production makeEnvelope, fully signed
 *   fresh      {"fresh": true|false}          — production freshness rule at `now-iso`
 *   constants  {"freshness_window_s": <n>}    — the shared constant, read not retyped
 *
 * A mode the production module cannot answer prints `null` for its field rather than throwing, so a
 * missing capability shows up in the comparing test as a VALUE that does not match, with the reason
 * beside it — not as a crash that could be mistaken for a broken probe.
 */
const fs = require("node:fs");
const env = require("../../ipc/envelope");

function main(argv) {
  const [mode, envPath, keyHex, nowIso] = argv;
  const key = Buffer.from(keyHex || "00".repeat(32), "hex");
  const envelope = envPath ? JSON.parse(fs.readFileSync(envPath, "utf8")) : null;
  let out;
  switch (mode) {
    case "canonical": {
      // The bytes the production signer actually hashes TODAY. Reported, never recomputed here.
      // The fallback is not a convenience: before U458 the module had no whole-envelope
      // canonicalizer at all, and answering `null` would make the comparing test fail on an absent
      // export rather than on the byte divergence that is the actual defect. Answering what the
      // signer really hashes makes the pre-repair failure show BOTH strings side by side.
      const whole = typeof env.canonicalEnvelope === "function";
      const bytes = whole ? env.canonicalEnvelope(envelope) : env.canonicalPayload(envelope.payload);
      out = { canonical: bytes.toString("utf8"), hex: bytes.toString("hex"),
        why: whole ? "canonicalEnvelope" : "no canonicalEnvelope — this is canonicalPayload(payload)" };
      break;
    }
    case "tag":
      out = { tag: env.computeIntegrity(key, envelope) };
      break;
    case "verify":
      out = { verified: env.verifyIntegrity(key, envelope) === true };
      break;
    case "mint":
      out = {
        envelope: env.makeEnvelope({
          fromNode: envelope.from_node, to: envelope.to, msgType: envelope.type,
          payload: envelope.payload, nodeCredential: envelope.auth.node_credential,
          scope: envelope.auth.scope, key, taskId: envelope.task_id,
          payloadSchema: envelope.payload_schema,
        }),
      };
      break;
    case "fresh":
      out = typeof env.envelopeIsFresh === "function"
        ? { fresh: env.envelopeIsFresh(envelope, { now: new Date(nowIso) }) === true }
        : { fresh: null, why: "the production module exports no envelopeIsFresh" };
      break;
    case "constants":
      out = { freshness_window_s: Object.prototype.hasOwnProperty.call(env, "FRESHNESS_WINDOW_S")
        ? env.FRESHNESS_WINDOW_S : null };
      break;
    default:
      process.stderr.write(`unknown probe mode ${String(mode)}\n`);
      return 2;
  }
  process.stdout.write(`${JSON.stringify(out)}\n`);
  return 0;
}

process.exitCode = main(process.argv.slice(2));
