"use strict";
/**
 * Phase 17C `.mic` — the captured-utterance lifecycle (apps/desktop/voice/capture-store.js).
 *
 * Invariant 26 (transcribe-then-discard) is the property under test, and the point of these cases is
 * that it must hold on the paths nobody exercises by hand: the transcription that throws, the WSL
 * timeout, the renderer that sends garbage. An invariant that holds only on the happy path is not one.
 *
 * Also invariant 29: the renderer is the least-trusted surface, so the bytes are validated BEFORE they
 * touch the disk — a refusal must leave no file at all, not a file that is later cleaned up.
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const {
  CaptureStore, CaptureStoreError, toBytes, redactCapturePaths, MIN_CAPTURE_BYTES, PURGE_MIN_AGE_MS,
} = require("../voice/capture-store");
const { encodeWav } = require("../voice/wav");

// An in-memory fs double: every write/unlink is observable, so "the file is gone" is a measurement.
function fakeFs({ mtimeMs = 0 } = {}) {
  const files = new Map();
  const dirs = new Set();
  const mtimes = new Map();
  return {
    files,
    dirs,
    mtimes,
    mkdirSync(d) { dirs.add(d); },
    writeFileSync(p, bytes, opts = {}) {
      if (opts.flag === "wx" && files.has(p)) {
        const e = new Error("EEXIST");
        e.code = "EEXIST";
        throw e;
      }
      files.set(p, bytes);
      mtimes.set(p, mtimeMs);
    },
    statSync(p) {
      if (!files.has(p)) { const e = new Error("ENOENT"); e.code = "ENOENT"; throw e; }
      return { mtimeMs: mtimes.get(p) || 0 };
    },
    unlinkSync(p) {
      if (!files.has(p)) { const e = new Error("ENOENT"); e.code = "ENOENT"; throw e; }
      files.delete(p);
    },
    readdirSync(d) {
      if (!dirs.has(d)) { const e = new Error("ENOENT"); e.code = "ENOENT"; throw e; }
      return [...files.keys()].filter((p) => path.dirname(p) === d).map((p) => path.basename(p));
    },
  };
}

const wav = (samples = 1600) => encodeWav(new Int16Array(samples), 16000);
const store = (over = {}) => new CaptureStore({
  dir: "D:\\repo\\.voice-captures",
  fs: over.fs || fakeFs(),
  now: () => 1000,
  instanceId: "11111111-1111-4111-8111-111111111111",
  ...over,
});

test("a valid capture is written under the repo-local capture dir", () => {
  const fs = fakeFs();
  const s = store({ fs });
  const rec = s.write(wav());
  assert.ok(fs.files.has(rec.path));
  assert.equal(path.dirname(rec.path), "D:\\repo\\.voice-captures");
  assert.ok(/^capture-11111111-1111-4111-8111-111111111111-1000-1\.wav$/.test(path.basename(rec.path)));
  assert.equal(rec.bytes, wav().length);
});

test("every capture gets a distinct path even within the same millisecond", () => {
  const s = store();
  assert.notEqual(s.write(wav()).path, s.write(wav()).path);
});

test("two shell instances at the same millisecond cannot collide or purge each other's capture", () => {
  const fs = fakeFs({ mtimeMs: 1000 });
  const first = store({ fs, instanceId: "11111111-1111-4111-8111-111111111111" });
  const second = store({ fs, instanceId: "22222222-2222-4222-8222-222222222222" });
  const a = first.write(wav());
  const b = second.write(wav());

  assert.notEqual(a.path, b.path);
  assert.equal(fs.files.size, 2);
  first.purgeOwned();
  assert.equal(fs.files.has(a.path), false);
  assert.equal(fs.files.has(b.path), true);
});

test("capture creation is exclusive even if a supplied instance identity collides", () => {
  const fs = fakeFs({ mtimeMs: 1000 });
  const a = store({ fs });
  const b = store({ fs });
  const first = a.write(wav());
  assert.throws(() => b.write(wav()), /exclusive capture path collision/);
  assert.equal(fs.files.get(first.path).length, wav().length,
    "the second store must not overwrite bytes owned by the first");
});

test("REFUSES non-WAV bytes before touching the disk (invariant 29)", () => {
  const fs = fakeFs();
  const s = store({ fs });
  const junk = new Uint8Array(2000).fill(7);
  assert.throws(() => s.write(junk), CaptureStoreError);
  assert.equal(fs.files.size, 0, "nothing was written — not written-then-cleaned-up");
});

test("REFUSES an empty or too-small payload", () => {
  const s = store();
  assert.throws(() => s.write(new Uint8Array(0)), CaptureStoreError);
  assert.throws(() => s.write(new Uint8Array(MIN_CAPTURE_BYTES - 1)), CaptureStoreError);
  assert.throws(() => s.write(null), CaptureStoreError);
  assert.throws(() => s.write("a string of audio"), CaptureStoreError);
});

test("REFUSES a payload over the cap — a looping renderer cannot fill the disk through voice", () => {
  const fs = fakeFs();
  const s = store({ fs, maxBytes: 1000 });
  assert.throws(() => s.write(wav(2000)), /over the 1000-byte cap/);
  assert.equal(fs.files.size, 0);
});

test("toBytes accepts every shape that can cross the IPC boundary", () => {
  const src = wav(8);
  assert.deepEqual(Array.from(toBytes(src)), Array.from(src));
  assert.deepEqual(Array.from(toBytes(src.buffer)), Array.from(src));
  assert.deepEqual(Array.from(toBytes(Array.from(src))), Array.from(src));
  // an array-like that survived a structured clone as a plain object
  const asObject = { length: src.length };
  src.forEach((b, i) => { asObject[i] = b; });
  assert.deepEqual(Array.from(toBytes(asObject)), Array.from(src));
});

test("withCapture DISCARDS the audio after a successful transcription (invariant 26)", async () => {
  const fs = fakeFs();
  const s = store({ fs });
  let seenPath = null;
  const out = await s.withCapture(wav(), async (p) => { seenPath = p; assert.ok(fs.files.has(p), "present during transcription"); return "transcript"; });
  assert.equal(out.result, "transcript");
  assert.equal(out.discard.discarded, true);
  assert.equal(fs.files.has(seenPath), false, "gone afterwards");
  assert.equal(fs.files.size, 0);
});

test("withCapture DISCARDS the audio when the transcription THROWS", async () => {
  // the path that actually matters: a WSL timeout, a NeMo fault, a killed emitter
  const fs = fakeFs();
  const s = store({ fs });
  await assert.rejects(
    s.withCapture(wav(), async () => { throw new Error("WSL Parakeet transcription timed out"); }),
    /timed out/,
  );
  assert.equal(fs.files.size, 0, "recorded speech is not left behind by a failure");
  assert.equal(s.lastDiscard.discarded, true, "and the discard is readable after the throw propagated");
});

test("withCapture discards when the transcription rejects asynchronously", async () => {
  const fs = fakeFs();
  const s = store({ fs });
  await assert.rejects(s.withCapture(wav(), () => Promise.reject(new Error("emitter exited 1"))), /exited 1/);
  assert.equal(fs.files.size, 0);
});

test("a failed discard is REPORTED, not swallowed and not thrown", async () => {
  // a locked file must not turn a good transcription into an error the operator sees — but the shell
  // has to be able to say that audio was retained, because invariant 26 says it should not have been.
  const fs = fakeFs();
  fs.unlinkSync = () => { throw Object.assign(new Error("EBUSY"), { code: "EBUSY" }); };
  const s = store({ fs });
  const out = await s.withCapture(wav(), async () => "ok");
  assert.equal(out.result, "ok");
  assert.equal(out.discard.discarded, false);
  assert.match(out.discard.reason, /EBUSY/);
});

test("discarding an already-gone file counts as discarded, and a null path never throws", () => {
  const s = store();
  const rec = s.write(wav());
  assert.equal(s.discard(rec.path).discarded, true);
  assert.equal(s.discard(rec.path).discarded, true, "second discard: already gone is still gone");
  assert.equal(s.discard(null).discarded, false);
});

test("purge removes capture residue a kill left behind — and nothing else", () => {
  // a `finally` cannot run if the process is gone, so a crash mid-transcription can retain audio.
  // Startup/teardown purge bounds that to one session.
  const fs = fakeFs();
  const s = store({ fs });
  s.write(wav());
  s.write(wav());
  fs.files.set(path.join("D:\\repo\\.voice-captures", "notes.txt"), new Uint8Array(1));
  const res = s.purge();
  assert.equal(res.removed, 2);
  assert.equal(res.failed, 0);
  assert.equal(fs.files.size, 1, "an unrelated file in the directory is untouched");
});

test("purge LEAVES a recent capture alone — it may be another instance's live transcription", () => {
  // the capture dir is repo-relative and therefore shared between shell instances; a blind purge
  // would delete an in-flight capture and the operator would see "voice unavailable" for an
  // utterance they completed.
  const now = 5_000_000;
  const fs = fakeFs({ mtimeMs: now - 1000 });          // written a second ago
  const s = store({ fs, now: () => now });
  s.write(wav());
  const res = s.purge();
  assert.equal(res.removed, 0);
  assert.equal(res.skipped, 1);
  assert.equal(fs.files.size, 1);

  // …and reaps it once it is unambiguously residue
  const old = fakeFs({ mtimeMs: now - PURGE_MIN_AGE_MS - 1 });
  const s2 = store({ fs: old, now: () => now });
  s2.write(wav());
  assert.equal(s2.purge().removed, 1);
});

test("the janitor reaps crash audio once the cross-instance safety age passes", () => {
  let now = 5_000_000;
  const fs = fakeFs({ mtimeMs: now });
  const crashed = store({ fs, now: () => now, instanceId: "22222222-2222-4222-8222-222222222222" });
  crashed.write(wav());
  let tick = null;
  let stopped = false;
  const current = store({ fs, now: () => now });
  const stop = current.startJanitor({
    intervalMs: 60_000,
    setIntervalFn: (fn, ms) => {
      assert.equal(ms, 60_000);
      tick = fn;
      return { unref() {}, close() { stopped = true; } };
    },
    clearIntervalFn: (timer) => timer.close(),
  });

  now += PURGE_MIN_AGE_MS + 1;
  assert.equal(tick().removed, 1);
  assert.equal(fs.files.size, 0, "recent crash residue may not survive a long-running replacement shell");
  stop();
  assert.equal(stopped, true);
});

test("purgeOwned removes this shell's fresh in-flight capture without touching another instance", () => {
  const now = 5_000_000;
  const fs = fakeFs({ mtimeMs: now });
  const ours = store({ fs, now: () => now });
  const theirs = store({ fs, now: () => now + 1 });
  const ourCapture = ours.write(wav());
  const theirCapture = theirs.write(wav());

  const result = ours.purgeOwned();
  assert.equal(result.removed, 1);
  assert.equal(result.failed, 0);
  assert.equal(fs.files.has(ourCapture.path), false);
  assert.equal(fs.files.has(theirCapture.path), true,
    "quit cleanup must not delete another shell instance's live transcription");
});

test("purge on a directory that was never created is a no-op, never a throw", () => {
  assert.deepEqual(store().purge().removed, 0);
});

// ---- the least-trusted surface: bounds enforced BEFORE anything is materialised ----
test("a hostile DECLARED length is refused before any allocation (invariant 29)", () => {
  // `{length: 2e9}` is a few bytes over IPC. Materialising it first meant a 2 GB allocation and a
  // two-billion-iteration loop ON THE MAIN EVENT LOOP before the cap was ever consulted — every pane's
  // data pump, the supervision heartbeat and the layout scheduler stalled. The cap bounded the disk
  // and nothing else.
  assert.throws(() => toBytes({ length: 2e9 }, 1000), /declares 2000000000 bytes, over the 1000-byte cap/);
  assert.throws(() => toBytes(new ArrayBuffer(5000), 1000), /over the 1000-byte cap/);
  assert.throws(() => toBytes({ length: -1 }, 1000), CaptureStoreError);
  const fs = fakeFs();
  assert.throws(() => store({ fs }).write({ length: 2e9 }), CaptureStoreError);
  assert.equal(fs.files.size, 0);
});

test("a RIFF-headed blob that is not usable PCM is refused at the boundary, not shipped to WSL", () => {
  const fs = fakeFs();
  const s = store({ fs });
  const stereo = encodeWav(new Int16Array(800), 16000);
  new DataView(stereo.buffer).setUint16(22, 2, true);   // claim 2 channels
  assert.throws(() => s.write(stereo), /not usable PCM/);
  assert.equal(fs.files.size, 0);
});

test("write reports the DECODED sample rate and duration, never the caller's claim", () => {
  const rec = store().write(encodeWav(new Int16Array(8000), 16000));
  assert.equal(rec.sampleRate, 16000);
  assert.ok(Math.abs(rec.seconds - 0.5) < 1e-9);
});

test("a failed discard's reason does NOT name the capture file (it is a live recording)", async () => {
  // Node embeds the full path in an fs error, and this reason reaches the renderer, the shell log and
  // the COMMITTED receipt — on the one branch where the audio still exists.
  const fs = fakeFs();
  fs.unlinkSync = (p) => { throw Object.assign(new Error(`EPERM: operation not permitted, unlink '${p}'`), { code: "EPERM" }); };
  const s = store({ fs });
  const out = await s.withCapture(wav(), async () => "ok");
  assert.equal(out.discard.discarded, false);
  assert.match(out.discard.reason, /EPERM/, "the error CODE is what a reader needs");
  assert.ok(!/capture-[\w-]+-\d/.test(out.discard.reason), `path leaked: ${out.discard.reason}`);
  assert.match(out.discard.reason, /<capture>/);
});

test("redactCapturePaths replaces capture filenames wherever they appear", () => {
  const msg = "EPERM: operation not permitted, unlink 'D:\\repo\\apps\\desktop\\.voice-captures\\capture-1769-1.wav'";
  const red = redactCapturePaths(msg);
  assert.ok(!red.includes("capture-1769-1.wav"));
  assert.ok(!red.includes(".voice-captures"));
  assert.match(red, /EPERM/);
  assert.equal(redactCapturePaths(null), "");
});
