"use strict";
/**
 * Microphone PCM → 16 kHz mono 16-bit WAV — Phase 17C `.mic` (directive §16 track 17C).
 *
 * WHY THIS EXISTS. Everything about voice up to now has been driven by a scripted `audio:` ref that
 * carries no PCM (`MockSTT._SCRIPT`), so the real engine was structurally unreachable from the shell:
 * `WslParakeetSTT.transcribe` refuses an `audio:` ref by construction, and `select_engine` only picks
 * the real engine `for_capture`. `.mic` supplies the missing thing — actual operator speech, as bytes
 * NeMo can read. The renderer captures Float32 frames from `getUserMedia`; this module turns them into
 * the exact container the WSL Parakeet adapter feeds to `ASRModel.transcribe`: RIFF/WAVE, PCM, mono,
 * 16-bit, 16 kHz.
 *
 * It is PURE — no DOM, no `fs`, no Electron — for the same reason every other load-bearing piece of
 * this shell is: the microphone itself is operator hardware and cannot be exercised in a headless test,
 * so everything AROUND it must be. `apps/desktop/test/wav.test.js` covers the byte layout, the clip
 * behaviour, the resampler and every fail-closed refusal without an audio device.
 *
 * FAIL-CLOSED (invariant 3, and invariant 29 — the renderer is the least-trusted surface): a malformed
 * frame list, a non-finite sample rate, a non-PCM or non-mono WAV, a truncated header, or a declared
 * chunk size that overruns the buffer each raise `WavError`. Nothing here ever guesses at audio it
 * cannot read; a caller that cannot encode must report "voice unavailable", never a silent empty
 * capture that would transcribe to "" and read to the operator as "the system did not hear me".
 *
 * NO TTS (I-V2/D-VOICE-02): this module only ever ENCODES captured input and DECODES a fixture for a
 * test. There is no synthesis path here and no audio is ever played back.
 */

(function () {
//: What the WSL Parakeet adapter's model expects, and what the renderer resamples to before sending.
const TARGET_SAMPLE_RATE = 16000;
const BITS_PER_SAMPLE = 16;
const CHANNELS = 1;
const BYTES_PER_SAMPLE = BITS_PER_SAMPLE / 8;
const WAV_HEADER_BYTES = 44;
const WAVE_FORMAT_PCM = 1;

class WavError extends Error {}

function _finiteRate(rate, label) {
  const n = Number(rate);
  if (!Number.isFinite(n) || n <= 0) throw new WavError(`${label} must be a positive finite sample rate, got ${rate}`);
  return n;
}

/**
 * Join the renderer's captured Float32 frames into one contiguous buffer.
 * Accepts Float32Array | number[] frames; anything else is refused (fail-closed, never coerced to
 * silence — a frame we cannot read is a fault, not an empty utterance).
 * @returns {Float32Array}
 */
function concatFloat32(chunks) {
  if (!Array.isArray(chunks)) throw new WavError("expected an array of Float32 frames");
  let total = 0;
  for (const c of chunks) {
    if (!(c instanceof Float32Array) && !Array.isArray(c)) throw new WavError("every frame must be a Float32Array or number[]");
    total += c.length;
  }
  const out = new Float32Array(total);
  let at = 0;
  for (const c of chunks) { out.set(c instanceof Float32Array ? c : Float32Array.from(c), at); at += c.length; }
  return out;
}

/**
 * Linear resample to `toRate`. The renderer ASKS its AudioContext for 16 kHz but browsers are free to
 * ignore the hint and hand back the device rate (48 kHz is typical) — sending 48 kHz frames under a
 * 16 kHz header would play back at a third speed and transcribe to nonsense, which the operator would
 * read as "Parakeet does not understand me" rather than as a bug. So the rate is always reconciled
 * here, from the AudioContext's OWN reported rate.
 *
 * Linear interpolation (not a windowed-sinc) is deliberate: speech at 16 kHz through a 0.6b ASR model
 * is not sensitive to the difference, and an honest simple resampler beats a filter this file cannot
 * test against a reference. Recorded as a limitation in the evidence rather than dressed up.
 */
function resampleTo(samples, fromRate, toRate = TARGET_SAMPLE_RATE) {
  if (!(samples instanceof Float32Array)) throw new WavError("resampleTo expects a Float32Array");
  const from = _finiteRate(fromRate, "fromRate");
  const to = _finiteRate(toRate, "toRate");
  if (from === to || samples.length === 0) return samples;
  const ratio = from / to;
  const outLen = Math.max(1, Math.floor(samples.length / ratio));
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i += 1) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const i1 = Math.min(i0 + 1, samples.length - 1);
    const frac = src - i0;
    out[i] = samples[i0] * (1 - frac) + samples[i1] * frac;
  }
  return out;
}

/**
 * Float32 [-1, 1] → signed 16-bit PCM, CLAMPED. A sample outside the range is clipped rather than
 * wrapped: wrapping turns a loud syllable into a full-scale square-wave crack that the model hears as
 * noise, so the failure mode of a hot mic must be quiet distortion, not garbage.
 * A non-finite sample (a NaN from a glitched device buffer) becomes silence rather than a throw —
 * one bad sample must not discard the operator's whole utterance.
 */
function floatToPcm16(samples) {
  if (!(samples instanceof Float32Array)) throw new WavError("floatToPcm16 expects a Float32Array");
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const v = samples[i];
    if (!Number.isFinite(v)) { out[i] = 0; continue; }
    const clamped = v > 1 ? 1 : v < -1 ? -1 : v;
    out[i] = clamped < 0 ? Math.max(-32768, Math.round(clamped * 32768)) : Math.min(32767, Math.round(clamped * 32767));
  }
  return out;
}

function _writeAscii(view, offset, text) {
  for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
}

/**
 * Wrap 16-bit mono PCM in a canonical 44-byte RIFF/WAVE header. Little-endian throughout (the WAV
 * spec's byte order, and the only one NeMo's reader will interpret correctly).
 * @returns {Uint8Array} the complete .wav file bytes
 */
function encodeWav(pcm16, sampleRate = TARGET_SAMPLE_RATE) {
  if (!(pcm16 instanceof Int16Array)) throw new WavError("encodeWav expects an Int16Array of PCM samples");
  const rate = _finiteRate(sampleRate, "sampleRate");
  const dataBytes = pcm16.length * BYTES_PER_SAMPLE;
  const buf = new ArrayBuffer(WAV_HEADER_BYTES + dataBytes);
  const view = new DataView(buf);
  _writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);       // RIFF chunk size = file size - 8
  _writeAscii(view, 8, "WAVE");
  _writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);                  // PCM fmt chunk size
  view.setUint16(20, WAVE_FORMAT_PCM, true);
  view.setUint16(22, CHANNELS, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * CHANNELS * BYTES_PER_SAMPLE, true);  // byte rate
  view.setUint16(32, CHANNELS * BYTES_PER_SAMPLE, true);         // block align
  view.setUint16(34, BITS_PER_SAMPLE, true);
  _writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < pcm16.length; i += 1) view.setInt16(WAV_HEADER_BYTES + i * BYTES_PER_SAMPLE, pcm16[i], true);
  return new Uint8Array(buf);
}

/**
 * The renderer's whole encode in one call: raw device frames + the device's OWN sample rate → the WAV
 * bytes the shell hands to the transcription path.
 * @param {Array<Float32Array>} chunks frames as captured
 * @param {number} inputRate the AudioContext's reported sampleRate (NOT the requested one)
 * @returns {{bytes: Uint8Array, samples: number, sampleRate: number, seconds: number}}
 */
function encodeCapture(chunks, inputRate) {
  const joined = concatFloat32(chunks);
  if (joined.length === 0) throw new WavError("no audio frames were captured (nothing to transcribe)");
  const resampled = resampleTo(joined, inputRate, TARGET_SAMPLE_RATE);
  const pcm = floatToPcm16(resampled);
  return {
    bytes: encodeWav(pcm, TARGET_SAMPLE_RATE),
    samples: pcm.length,
    sampleRate: TARGET_SAMPLE_RATE,
    seconds: pcm.length / TARGET_SAMPLE_RATE,
  };
}

/** Seconds of 16-bit mono audio in a WAV of `byteLength` bytes at `sampleRate`. Never negative. */
function durationSeconds(byteLength, sampleRate = TARGET_SAMPLE_RATE) {
  const rate = _finiteRate(sampleRate, "sampleRate");
  return Math.max(0, (Number(byteLength) - WAV_HEADER_BYTES)) / (rate * BYTES_PER_SAMPLE);
}

/**
 * Parse a WAV far enough to hand its PCM back to the capture path. Used by the `.mic` in-Electron
 * self-check, which drives the REAL production capture handler with a fixture WAV's samples — the
 * whole chain below the microphone, on a host with no operator speaking into it.
 *
 * Chunk-walking (rather than assuming a 44-byte header) because a synthesizer-produced WAV commonly
 * carries a `LIST`/`fact` chunk before `data`; assuming the canonical offset would read metadata as
 * audio and transcribe to noise.
 *
 * @returns {{sampleRate, channels, bitsPerSample, pcm16: Int16Array, samples: number, seconds: number}}
 */
function decodeWav(bytes) {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
  if (u8.length < 12) throw new WavError("not a WAV: fewer than 12 bytes");
  const view = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  const tag = (off) => String.fromCharCode(u8[off], u8[off + 1], u8[off + 2], u8[off + 3]);
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new WavError("not a RIFF/WAVE file");
  let offset = 12;
  let fmt = null;
  let data = null;
  while (offset + 8 <= u8.length) {
    const id = tag(offset);
    const size = view.getUint32(offset + 4, true);
    const body = offset + 8;
    if (body + size > u8.length && id === "data") {
      // A truncated data chunk is recoverable — take what is really there rather than refusing the
      // operator's whole utterance over a few missing bytes at the tail.
      data = { at: body, size: u8.length - body };
      break;
    }
    if (body + size > u8.length) throw new WavError(`chunk ${id} declares ${size} bytes past the end of the file`);
    if (id === "fmt ") {
      fmt = {
        format: view.getUint16(body, true),
        channels: view.getUint16(body + 2, true),
        sampleRate: view.getUint32(body + 4, true),
        bitsPerSample: view.getUint16(body + 14, true),
      };
    } else if (id === "data") {
      data = { at: body, size };
    }
    offset = body + size + (size % 2); // RIFF chunks are word-aligned
  }
  if (!fmt) throw new WavError("WAV has no fmt chunk");
  if (!data) throw new WavError("WAV has no data chunk");
  if (fmt.format !== WAVE_FORMAT_PCM) throw new WavError(`WAV is not uncompressed PCM (format ${fmt.format})`);
  if (fmt.bitsPerSample !== BITS_PER_SAMPLE) throw new WavError(`WAV is ${fmt.bitsPerSample}-bit; only ${BITS_PER_SAMPLE}-bit is supported`);
  if (fmt.channels !== CHANNELS) throw new WavError(`WAV has ${fmt.channels} channels; only mono is supported`);
  const count = Math.floor(data.size / BYTES_PER_SAMPLE);
  const pcm16 = new Int16Array(count);
  for (let i = 0; i < count; i += 1) pcm16[i] = view.getInt16(data.at + i * BYTES_PER_SAMPLE, true);
  return {
    sampleRate: fmt.sampleRate,
    channels: fmt.channels,
    bitsPerSample: fmt.bitsPerSample,
    pcm16,
    samples: count,
    seconds: count / fmt.sampleRate,
  };
}

/** Signed 16-bit PCM → Float32 in [-1, 1]. The inverse of `floatToPcm16`, for replaying a fixture. */
function pcm16ToFloat(pcm16) {
  if (!(pcm16 instanceof Int16Array)) throw new WavError("pcm16ToFloat expects an Int16Array");
  const out = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i += 1) out[i] = pcm16[i] / (pcm16[i] < 0 ? 32768 : 32767);
  return out;
}

const API = {
  WavError,
  TARGET_SAMPLE_RATE,
  BITS_PER_SAMPLE,
  CHANNELS,
  BYTES_PER_SAMPLE,
  WAV_HEADER_BYTES,
  concatFloat32,
  resampleTo,
  floatToPcm16,
  pcm16ToFloat,
  encodeWav,
  decodeWav,
  encodeCapture,
  durationSeconds,
};

// UMD: the SAME encoder in main (which validates and writes the file) and in the sandboxed renderer
// (which produces the bytes). Two copies of a byte layout drift, and a drifted header is a WAV that
// transcribes to noise — the operator would read that as "Parakeet cannot understand me".
if (typeof module !== "undefined" && module.exports) module.exports = API;
if (typeof window !== "undefined") window.SovereignWav = API;
})();
