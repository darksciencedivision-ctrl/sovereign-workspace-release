"use strict";
/**
 * The captured-utterance file lifecycle — Phase 17C `.mic` (invariant 26: transcribe-then-discard).
 *
 * WSL Parakeet transcribes a FILE (`ASRModel.transcribe([wav])` over a `/mnt/...` path), so real mic
 * capture necessarily puts the operator's speech on disk for a few seconds. Invariant 26 says audio is
 * discarded after transcription by default, and an invariant that depends on the happy path is not an
 * invariant — so the discard lives HERE, in a `finally`, around the whole transcription, rather than
 * being a step the caller is trusted to remember.
 *
 * WHERE. Under the repo root (`apps/desktop/.voice-captures/`), never the system temp dir: directive
 * §2.5 forbids this build from writing outside the repo, and a self-check that scattered WAVs into
 * `%TEMP%` would be doing exactly that. It is git-ignored — recorded speech is never committed.
 *
 * FAIL-CLOSED, and the renderer is the LEAST-TRUSTED surface (invariant 29). The bytes arrive over IPC
 * from the sandboxed renderer, so this module refuses anything that is not a plausible WAV before it
 * touches the disk: empty, over the size cap, or without a RIFF/WAVE magic. The cap is a real bound —
 * a compromised or looping renderer must not be able to fill the disk through the voice path.
 *
 * `purgeCaptures` exists because a `finally` cannot run if the process is killed mid-transcription.
 * The shell purges at startup, periodically, and at teardown. A recent file is spared for the
 * cross-instance safety window, then the janitor reaps it even during a long-running replacement
 * session — stated honestly rather than claimed impossible.
 *
 * Pure-ish and injectable (`fs`, `now`, `dir`): apps/desktop/test/capture-store.test.js covers every
 * refusal, the guaranteed discard on both the success and throw paths, and the purge — with no audio
 * device and no Electron.
 */
const realFs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { decodeWav } = require("./wav");

//: 5 minutes of 16 kHz mono 16-bit audio (+ header slack). A push-to-talk utterance is seconds long;
//: this is a disk-safety bound on the least-trusted surface, not an expected size.
const MAX_CAPTURE_BYTES = 16000 * 2 * 300 + 1024;
//: Below this there is no audio worth sending to a 20 s WSL round trip (a header alone is 44 bytes).
const MIN_CAPTURE_BYTES = 45;
//: git-ignored; the operator's recorded speech never enters version control.
const CAPTURE_DIR_NAME = ".voice-captures";
const CAPTURE_PREFIX = "capture-";
const CAPTURE_SUFFIX = ".wav";
//: A purge leaves anything newer than this alone — the capture directory is repo-relative and shared
//: between shell instances, and a transcription runs for tens of seconds. Comfortably past the JS
//: capture ceiling (transcribe budget + margin), so nothing live is ever reaped.
const PURGE_MIN_AGE_MS = 600000;

class CaptureStoreError extends Error {}

function defaultCaptureDir(appDir) {
  return path.join(appDir || path.resolve(__dirname, ".."), CAPTURE_DIR_NAME);
}

/**
 * Replace any capture-file path in a message with a stable placeholder. Applied to every string that
 * can leave this module for a log, a feed, the renderer, or a committed receipt — the fs error text
 * that names a retained recording is exactly the string that must not be published.
 */
function redactCapturePaths(text) {
  return String(text == null ? "" : text)
    .replace(new RegExp(`[^'"\\s]*${CAPTURE_PREFIX}[\\w.-]*${CAPTURE_SUFFIX.replace(".", "\\.")}`, "gi"),
      "<capture>");
}

function _isRiffWave(bytes) {
  if (bytes.length < 12) return false;
  const s = (o) => String.fromCharCode(bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]);
  return s(0) === "RIFF" && s(8) === "WAVE";
}

/**
 * Coerce whatever crossed the IPC boundary into a Uint8Array. Electron structured-clones a
 * Uint8Array faithfully, but a renderer may also send an ArrayBuffer, a Buffer, or (if something
 * upstream JSON-round-tripped it) a plain `{0:..,1:..}` object — all handled, all validated after.
 */
function toBytes(input, maxBytes = MAX_CAPTURE_BYTES) {
  if (input == null) throw new CaptureStoreError("no captured audio was supplied");
  // The DECLARED length is checked BEFORE anything is materialised. The cap used to be enforced in
  // `write()`, after conversion — so `{length: 2e9}` (a few bytes over IPC, structured-cloned into the
  // array-like branch below) made main allocate 2 GB and then run a two-billion-iteration loop ON THE
  // MAIN EVENT LOOP before the bound was ever consulted: every pane's data pump, the supervision
  // heartbeat and the layout scheduler stalled, or the process died. The cap bounded the disk and
  // nothing else (invariant 29 — the renderer declares this number).
  const declared = typeof input === "number" ? NaN
    : input.byteLength != null ? input.byteLength
      : Number.isFinite(input.length) ? input.length : NaN;
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new CaptureStoreError(`captured audio declares ${declared} bytes, over the ${maxBytes}-byte cap`);
  }
  if (input instanceof Uint8Array) return input;
  if (input instanceof ArrayBuffer) return new Uint8Array(input);
  if (ArrayBuffer.isView(input)) return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
  if (Array.isArray(input)) return Uint8Array.from(input);
  if (typeof input === "object" && Number.isFinite(input.length)) {
    // an array-like that survived a structured clone as a plain object
    if (input.length < 0) throw new CaptureStoreError("captured audio declares a negative length");
    const out = new Uint8Array(input.length);
    for (let i = 0; i < out.length; i += 1) out[i] = Number(input[i]) & 0xff;
    return out;
  }
  throw new CaptureStoreError(`captured audio is not byte data (${typeof input})`);
}

class CaptureStore {
  /** @param {object} opts {dir?, appDir?, fs?, now?, maxBytes?} */
  constructor(opts = {}) {
    this.dir = opts.dir || defaultCaptureDir(opts.appDir);
    this.fs = opts.fs || realFs;
    this._now = opts.now || (() => Date.now());
    this.maxBytes = Number.isFinite(opts.maxBytes) && opts.maxBytes > 0 ? opts.maxBytes : MAX_CAPTURE_BYTES;
    this.instanceId = String(opts.instanceId || crypto.randomUUID()).toLowerCase();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(this.instanceId)) {
      throw new CaptureStoreError("capture store instance identity must be a UUID");
    }
    this._seq = 0;
    this._owned = new Set();
  }

  /**
   * Validate + persist one captured utterance. Throws `CaptureStoreError` (never writes) on anything
   * the shell should not be handing to a transcription engine.
   * @returns {{path: string, bytes: number}}
   */
  write(input) {
    const bytes = toBytes(input, this.maxBytes);
    if (bytes.length < MIN_CAPTURE_BYTES) {
      throw new CaptureStoreError(`captured audio is too small to be a WAV (${bytes.length} bytes)`);
    }
    if (bytes.length > this.maxBytes) {
      throw new CaptureStoreError(`captured audio is ${bytes.length} bytes, over the ${this.maxBytes}-byte cap`);
    }
    if (!_isRiffWave(bytes)) {
      throw new CaptureStoreError("captured audio is not a RIFF/WAVE file (refused before it touched disk)");
    }
    // Structural validation, not just the 8-byte magic: the decoder that the transcription path relies
    // on already exists here, so a RIFF-headed blob of arbitrary content is refused at the trust
    // boundary rather than shipped to a WSL NeMo process to fail there (spec-audit MINOR-9). It also
    // yields the TRUE sample rate, so nothing downstream has to believe the renderer's claim.
    let decoded;
    try {
      decoded = decodeWav(bytes);
    } catch (e) {
      throw new CaptureStoreError(`captured audio is not usable PCM: ${e.message}`);
    }
    this.fs.mkdirSync(this.dir, { recursive: true });
    this._seq += 1;
    const file = path.join(this.dir,
      `${CAPTURE_PREFIX}${this.instanceId}-${this._now()}-${this._seq}${CAPTURE_SUFFIX}`);
    try {
      // Exclusive creation is the final ownership boundary. The UUID makes cross-instance collision
      // cryptographically remote; `wx` makes even a forced/injected collision fail closed instead of
      // overwriting another shell's in-flight recording and then claiming it as ours.
      this.fs.writeFileSync(file, bytes, { flag: "wx", mode: 0o600 });
    } catch (e) {
      if (e && e.code === "EEXIST") {
        throw new CaptureStoreError("exclusive capture path collision — refusing to overwrite audio");
      }
      throw e;
    }
    this._owned.add(file);
    // `sampleRate`/`seconds` are the DECODED facts, never the renderer's claim about its own payload.
    return { path: file, bytes: bytes.length, sampleRate: decoded.sampleRate, seconds: decoded.seconds };
  }

  /**
   * Delete one capture. Never throws: a discard that fails is REPORTED (so the receipt and the log can
   * carry it) but must not turn a successful transcription into an error the operator sees.
   * @returns {{discarded: boolean, path: string, reason?: string}}
   */
  discard(file) {
    if (!file) return { discarded: false, path: null, reason: "no capture path" };
    try {
      this.fs.unlinkSync(file);
      this._owned.delete(file);
      return { discarded: true, path: file };
    } catch (e) {
      if (e && e.code === "ENOENT") {
        this._owned.delete(file);
        return { discarded: true, path: file, reason: "already gone" };
      }
      // REDACTED: Node embeds the full path in an fs error ("EPERM: ... unlink 'D:\...\capture-N.wav'"),
      // and this reason travels into the renderer, the shell log and the COMMITTED receipt — on the one
      // branch where the file still exists, so the artifact would name a live recording of the
      // operator's speech. The error CODE is what a reader needs; the location is not.
      return { discarded: false, path: file, reason: redactCapturePaths(`${e.name || "Error"}: ${e.message}`) };
    }
  }

  /**
   * Persist, run `fn(path)`, and discard — the discard guaranteed on BOTH the return and the throw
   * path. This is where invariant 26 is actually enforced; every caller goes through it.
   * @returns {Promise<{result:any, capture:{path, bytes}, discard:{discarded, reason?}}>}
   */
  async withCapture(input, fn) {
    const capture = this.write(input);
    let result;
    try {
      result = await fn(capture.path, capture);
    } finally {
      // eslint-disable-next-line no-unsafe-finally -- assignment only; nothing returns/throws here
      this._lastDiscard = this.discard(capture.path);
    }
    return { result, capture, discard: this._lastDiscard };
  }

  /** The discard record from the most recent `withCapture` — readable after a throw propagated. */
  get lastDiscard() { return this._lastDiscard || null; }

  /**
   * Quit-time cleanup for captures created by THIS store instance. Unlike purge(), this may safely
   * remove fresh files: it cannot touch another shell instance's in-flight transcription.
   */
  purgeOwned() {
    let removed = 0;
    let failed = 0;
    for (const file of [...this._owned]) {
      try {
        this.fs.unlinkSync(file);
        this._owned.delete(file);
        removed += 1;
      } catch (e) {
        if (e && e.code === "ENOENT") {
          this._owned.delete(file);
          removed += 1;
        } else {
          failed += 1;
        }
      }
    }
    return { removed, failed, dir: this.dir };
  }

  /**
   * Periodically reap crash residue once it is older than the cross-instance safety window. Startup
   * purge alone can skip a fresh orphan and then leave it for an arbitrarily long shell session.
   */
  startJanitor(opts = {}) {
    const intervalMs = Number.isFinite(opts.intervalMs) && opts.intervalMs > 0
      ? opts.intervalMs : 60_000;
    const setIntervalFn = opts.setIntervalFn || setInterval;
    const clearIntervalFn = opts.clearIntervalFn || clearInterval;
    const timer = setIntervalFn(() => this.purge(), intervalMs);
    timer.unref?.();
    return () => clearIntervalFn(timer);
  }

  /**
   * Remove capture files left behind by a kill mid-transcription (a `finally` cannot run if the
   * process is gone). Called at startup and at teardown. Never throws — a missing directory is the
   * normal case. Only files matching this store's own naming are touched.
   * @returns {{removed: number, failed: number, dir: string}}
   */
  purge({ minAgeMs = PURGE_MIN_AGE_MS } = {}) {
    let names = [];
    try { names = this.fs.readdirSync(this.dir); } catch { return { removed: 0, failed: 0, skipped: 0, dir: this.dir }; }
    let removed = 0;
    let failed = 0;
    let skipped = 0;
    const now = this._now();
    for (const n of names) {
      if (!n.startsWith(CAPTURE_PREFIX) || !n.endsWith(CAPTURE_SUFFIX)) continue;
      const file = path.join(this.dir, n);
      // The directory is repo-relative and therefore SHARED between shell instances. A blind purge
      // would delete a second instance's in-flight capture mid-transcription, and the operator would
      // see an unexplained "voice unavailable" for an utterance they completed. Residue is by
      // definition old; anything recent is presumed live and left alone.
      if (minAgeMs > 0) {
        let mtime = 0;
        try { mtime = this.fs.statSync(file).mtimeMs; } catch { mtime = 0; }
        if (mtime && now - mtime < minAgeMs) { skipped += 1; continue; }
      }
      try {
        this.fs.unlinkSync(file);
        this._owned.delete(file);
        removed += 1;
      } catch { failed += 1; }
    }
    return { removed, failed, skipped, dir: this.dir };
  }
}

module.exports = {
  CaptureStore,
  CaptureStoreError,
  toBytes,
  redactCapturePaths,
  defaultCaptureDir,
  MAX_CAPTURE_BYTES,
  MIN_CAPTURE_BYTES,
  PURGE_MIN_AGE_MS,
  CAPTURE_DIR_NAME,
};
