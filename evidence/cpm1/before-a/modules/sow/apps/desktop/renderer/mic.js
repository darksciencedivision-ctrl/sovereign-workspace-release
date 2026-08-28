"use strict";
/**
 * Push-to-talk microphone capture — Phase 17C `.mic` (directive §16 track 17C; OP-8 §13.5).
 *
 * The operator holds the talk button, speaks, and releases; this produces the WAV bytes of what they
 * said. It is the ONLY place in the product that touches an audio device, and it is deliberately thin:
 * every byte-level decision lives in the shared `SovereignWav` encoder (`../voice/wav.js`), which is
 * headlessly tested, because a microphone cannot be.
 *
 * WHY NOT `MediaRecorder`. It yields WebM/Opus, and the WSL Parakeet path feeds a file straight to
 * `ASRModel.transcribe`, which wants PCM. Decoding Opus would add a dependency and a failure mode
 * between the operator's voice and the model for no gain. `getUserMedia` + a `ScriptProcessorNode` hands
 * us the raw Float32 frames the encoder already knows how to package. `ScriptProcessorNode` is formally
 * deprecated in favour of `AudioWorklet`; it is used knowingly — the worklet variant needs a separately
 * fetched module file, which is friction on a `file://` origin, and this node runs for the seconds an
 * operator holds a button. Recorded as a limitation, not hidden.
 *
 * HONESTY, fail-closed (invariant 3; directive §16 track 17C — *never silently pretend to hear*):
 * a denied permission, an absent device, a zero-length hold, or an encoder refusal all `throw` with the
 * reason NAMED. Nothing here ever falls back to the scripted stand-in ref: a mock transcript returned
 * from a press where the operator really spoke would be the exact pretend-to-hear the visible-mock rule
 * exists to prevent. The caller surfaces the reason in the chrome.
 *
 * The recorder holds the device open only between `start()` and `stop()`, and `stop()` releases every
 * track — a shell that left the mic hot after a talk press would be recording the operator's room.
 * NO playback and NO synthesis anywhere in this file (I-V2/D-VOICE-02 — STT-only).
 */
(function () {
const Wav = window.SovereignWav;

//: A hold shorter than this is a mis-click, not an utterance; sending it costs a 20 s WSL round trip
//: to transcribe silence and comes back "not understood", which reads as a broken mic.
const MIN_CAPTURE_MS = 250;
//: Matches CaptureStore's disk cap (5 minutes). Enforced here too so a stuck button is stopped at the
//: source rather than after the bytes have crossed IPC.
const MAX_CAPTURE_MS = 300000;
const FRAME_SIZE = 4096;

class MicError extends Error {}

class MicRecorder {
  /** @param {object} opts {getUserMedia?, AudioContextCtor?, now?} — injected in tests; real defaults here. */
  constructor(opts = {}) {
    this._getUserMedia = opts.getUserMedia
      || ((c) => (navigator.mediaDevices ? navigator.mediaDevices.getUserMedia(c) : Promise.reject(new MicError("this runtime exposes no microphone API"))));
    this._AudioContextCtor = opts.AudioContextCtor || window.AudioContext || window.webkitAudioContext;
    this._now = opts.now || (() => Date.now());
    this._reset();
  }

  _reset() {
    this._stream = null;
    this._ctx = null;
    this._node = null;
    this._source = null;
    this._chunks = [];
    this._startedAt = null;
    this._inputRate = null;
    this._open = false;
  }

  /**
   * Is a capture SESSION open? Deliberately not "is the device open": hitting `MAX_CAPTURE_MS` closes
   * the device but the session stays open so `stop()` still encodes what was already captured. An
   * earlier revision keyed this off the stream, so a long hold released the device, `recording` went
   * false, and the caller treated it as "the mic never opened" — silently discarding the operator's
   * speech (spec-audit MINOR-2). A cap is a bound on how much we keep, never a reason to lose it.
   */
  get recording() { return this._open === true; }

  /**
   * Open the device and begin buffering frames. Throws (device denied/absent/unsupported) rather than
   * returning a silent failure — the caller must be able to tell the operator why nothing is listening.
   */
  async start() {
    if (this.recording) return;
    if (!this._AudioContextCtor) throw new MicError("this runtime has no Web Audio API — microphone capture is unavailable");
    let stream;
    try {
      // 16 kHz mono is a HINT; browsers routinely hand back the device's native rate instead, which is
      // why the encoder resamples from `ctx.sampleRate` (what we actually got) rather than from what we
      // asked for. Echo cancellation and noise suppression are on: the operator is speaking at a desktop
      // with the shell's own panes around them.
      stream = await this._getUserMedia({
        audio: { channelCount: 1, sampleRate: Wav.TARGET_SAMPLE_RATE, echoCancellation: true, noiseSuppression: true },
        video: false,
      });
    } catch (e) {
      throw new MicError(`microphone unavailable: ${(e && (e.name === "NotAllowedError" ? "permission denied" : e.message)) || e}`);
    }
    try {
      this._stream = stream;
      this._ctx = new this._AudioContextCtor({ sampleRate: Wav.TARGET_SAMPLE_RATE });
      this._inputRate = this._ctx.sampleRate;   // the REAL rate, not the requested one
      this._source = this._ctx.createMediaStreamSource(stream);
      this._node = this._ctx.createScriptProcessor(FRAME_SIZE, 1, 1);
      this._chunks = [];
      this._startedAt = this._now();
      this._open = true;
      this._node.onaudioprocess = (ev) => {
        if (!this._stream) return;
        // The event buffer is REUSED by the audio thread — copy or the frames all read as the last one.
        this._chunks.push(new Float32Array(ev.inputBuffer.getChannelData(0)));
        // Close the DEVICE at the cap, but leave the session open: `stop()` still encodes what was
        // captured. Discarding it would lose real speech to a bound that exists only to bound.
        if (this._now() - this._startedAt > MAX_CAPTURE_MS) { this._capped = true; this._releaseDevice(); }
      };
      this._source.connect(this._node);
      // A ScriptProcessorNode only fires while it is part of a rendering graph. Connecting it to the
      // destination is what pulls it — and it emits nothing itself, so this is not an output path
      // (I-V2 stands): the shell still never plays audio.
      this._node.connect(this._ctx.destination);
    } catch (e) {
      this._releaseDevice();
      this._reset();
      throw new MicError(`could not start capture: ${(e && e.message) || e}`);
    }
  }

  // Close the device and the graph. Idempotent, never throws — releasing the mic must always succeed.
  _releaseDevice() {
    try { if (this._node) { this._node.onaudioprocess = null; this._node.disconnect(); } } catch { /* gone */ }
    try { if (this._source) this._source.disconnect(); } catch { /* gone */ }
    try { if (this._stream) this._stream.getTracks().forEach((t) => t.stop()); } catch { /* gone */ }
    try { if (this._ctx && this._ctx.state !== "closed") this._ctx.close(); } catch { /* gone */ }
    this._stream = null;
  }

  /**
   * Stop, release the device, and encode. Throws on a too-short hold or an empty buffer — a capture we
   * cannot honestly transcribe is a fault to report, never an empty utterance to send.
   * @returns {{pcm: Uint8Array, sampleRate: number, seconds: number, samples: number, inputRate: number}}
   */
  stop() {
    if (!this._startedAt) throw new MicError("no capture is running");
    const heldMs = this._now() - this._startedAt;
    const chunks = this._chunks;
    const inputRate = this._inputRate;
    const capped = this._capped === true;
    this._releaseDevice();
    this._reset();
    this._capped = false;
    if (heldMs < MIN_CAPTURE_MS) throw new MicError(`hold the talk button to speak (released after ${Math.round(heldMs)}ms)`);
    let encoded;
    try {
      encoded = Wav.encodeCapture(chunks, inputRate);
    } catch (e) {
      throw new MicError(`nothing was recorded: ${(e && e.message) || e}`);
    }
    if (encoded.seconds * 1000 < MIN_CAPTURE_MS) throw new MicError("the microphone produced no audible input");
    return { pcm: encoded.bytes, sampleRate: encoded.sampleRate, seconds: encoded.seconds, samples: encoded.samples,
             inputRate, capped };
  }

  /** Abandon a capture without encoding (a cancelled hold, a teardown). Never throws. */
  cancel() { this._releaseDevice(); this._reset(); }

  /** True if the capture hit `MAX_CAPTURE_MS` and the device was closed early — the caller should say
   *  so, because the encoded audio is the first N minutes and not the whole hold. */
  get capped() { return this._capped === true; }
}

const API = { MicRecorder, MicError, MIN_CAPTURE_MS, MAX_CAPTURE_MS, FRAME_SIZE };
if (typeof module !== "undefined" && module.exports) module.exports = API;
if (typeof window !== "undefined") window.SovereignMic = API;
})();
