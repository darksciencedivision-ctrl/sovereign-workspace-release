"use strict";
/**
 * Phase 17C `.mic` — the microphone encoder (apps/desktop/voice/wav.js).
 *
 * The microphone is operator hardware; it cannot be exercised here. So everything AROUND it is: the
 * exact byte layout NeMo will read, the clip behaviour of a hot mic, the resample that reconciles a
 * device that ignored our 16 kHz request, and every fail-closed refusal. A drifted header does not
 * crash — it transcribes to noise, and the operator reads that as "Parakeet cannot understand me".
 */
const test = require("node:test");
const assert = require("node:assert");
const {
  WavError, TARGET_SAMPLE_RATE, WAV_HEADER_BYTES,
  concatFloat32, resampleTo, floatToPcm16, pcm16ToFloat, encodeWav, decodeWav, encodeCapture, durationSeconds,
} = require("../voice/wav");

const ascii = (u8, at) => String.fromCharCode(u8[at], u8[at + 1], u8[at + 2], u8[at + 3]);
const u32 = (u8, at) => new DataView(u8.buffer, u8.byteOffset, u8.byteLength).getUint32(at, true);
const u16 = (u8, at) => new DataView(u8.buffer, u8.byteOffset, u8.byteLength).getUint16(at, true);

// A short tone — deterministic, and shaped like real speech input (continuous, in range).
function tone(samples, freq = 440, rate = TARGET_SAMPLE_RATE) {
  const out = new Float32Array(samples);
  for (let i = 0; i < samples; i += 1) out[i] = 0.5 * Math.sin((2 * Math.PI * freq * i) / rate);
  return out;
}

test("encodeWav writes a canonical 44-byte PCM mono header NeMo can read", () => {
  const pcm = floatToPcm16(tone(1600));
  const wav = encodeWav(pcm, TARGET_SAMPLE_RATE);
  assert.equal(ascii(wav, 0), "RIFF");
  assert.equal(ascii(wav, 8), "WAVE");
  assert.equal(ascii(wav, 12), "fmt ");
  assert.equal(u32(wav, 16), 16, "PCM fmt chunk size");
  assert.equal(u16(wav, 20), 1, "format 1 = uncompressed PCM");
  assert.equal(u16(wav, 22), 1, "mono");
  assert.equal(u32(wav, 24), TARGET_SAMPLE_RATE);
  assert.equal(u32(wav, 28), TARGET_SAMPLE_RATE * 2, "byte rate = rate * channels * bytes/sample");
  assert.equal(u16(wav, 32), 2, "block align");
  assert.equal(u16(wav, 34), 16, "bits per sample");
  assert.equal(ascii(wav, 36), "data");
  assert.equal(u32(wav, 40), pcm.length * 2, "data chunk size");
  assert.equal(u32(wav, 4), wav.length - 8, "RIFF size = file size - 8");
  assert.equal(wav.length, WAV_HEADER_BYTES + pcm.length * 2);
});

test("encode → decode round-trips the samples exactly (little-endian both ways)", () => {
  const pcm = Int16Array.from([0, 1, -1, 32767, -32768, 1234, -4321]);
  const decoded = decodeWav(encodeWav(pcm, TARGET_SAMPLE_RATE));
  assert.deepEqual(Array.from(decoded.pcm16), Array.from(pcm));
  assert.equal(decoded.sampleRate, TARGET_SAMPLE_RATE);
  assert.equal(decoded.channels, 1);
  assert.equal(decoded.bitsPerSample, 16);
});

test("floatToPcm16 CLAMPS a hot mic instead of wrapping it", () => {
  // wrapping would turn a loud syllable into a full-scale square-wave crack the model hears as noise
  const out = floatToPcm16(Float32Array.from([2, -2, 1, -1, 0]));
  assert.equal(out[0], 32767);
  assert.equal(out[1], -32768);
  assert.equal(out[2], 32767);
  assert.equal(out[3], -32768);
  assert.equal(out[4], 0);
});

test("floatToPcm16 turns a NaN from a glitched device buffer into silence, not a throw", () => {
  const out = floatToPcm16(Float32Array.from([NaN, Infinity, 0.5]));
  assert.equal(out[0], 0);
  assert.equal(out[1], 0);
  assert.ok(out[2] > 16000, "the good sample survives — one bad frame must not discard the utterance");
});

test("pcm16ToFloat inverts floatToPcm16 to within a quantisation step", () => {
  const original = tone(512);
  const back = pcm16ToFloat(floatToPcm16(original));
  for (let i = 0; i < original.length; i += 1) {
    assert.ok(Math.abs(back[i] - original[i]) < 1e-4, `sample ${i} drifted by ${Math.abs(back[i] - original[i])}`);
  }
});

test("resampleTo reconciles a device that ignored the 16 kHz request", () => {
  // the common real case: the browser hands back 48 kHz. Sending those frames under a 16 kHz header
  // would play at a third speed and transcribe to nonsense.
  const at48k = tone(4800, 440, 48000);
  const at16k = resampleTo(at48k, 48000, 16000);
  assert.equal(at16k.length, 1600, "3:1 decimation");
  assert.ok(Math.max(...at16k.map(Math.abs)) > 0.4, "the signal survives, it is not zeroed");
});

test("resampleTo is identity when the rates already agree, and on empty input", () => {
  const s = tone(100);
  assert.strictEqual(resampleTo(s, 16000, 16000), s);
  assert.equal(resampleTo(new Float32Array(0), 48000, 16000).length, 0);
});

test("encodeCapture is the whole renderer encode: frames + device rate → transcribable WAV", () => {
  const frames = [tone(4096, 440, 48000), tone(4096, 440, 48000), tone(2048, 440, 48000)];
  const enc = encodeCapture(frames, 48000);
  assert.equal(enc.sampleRate, TARGET_SAMPLE_RATE);
  assert.equal(enc.samples, Math.floor((4096 + 4096 + 2048) / 3));
  assert.ok(Math.abs(enc.seconds - enc.samples / TARGET_SAMPLE_RATE) < 1e-9);
  const decoded = decodeWav(enc.bytes);
  assert.equal(decoded.sampleRate, TARGET_SAMPLE_RATE);
  assert.equal(decoded.samples, enc.samples);
});

test("encodeCapture REFUSES an empty hold rather than emitting silence", () => {
  // silence would cost a 20 s WSL round trip and come back "not understood" — reading as a broken mic
  assert.throws(() => encodeCapture([], 48000), WavError);
  assert.throws(() => encodeCapture([new Float32Array(0)], 48000), WavError);
});

test("every malformed input is refused, never guessed at", () => {
  assert.throws(() => concatFloat32("nope"), WavError);
  assert.throws(() => concatFloat32([{ length: 3 }]), WavError);
  assert.throws(() => resampleTo(Float32Array.from([1]), 0, 16000), WavError);
  assert.throws(() => resampleTo(Float32Array.from([1]), NaN, 16000), WavError);
  assert.throws(() => resampleTo([1, 2], 48000, 16000), WavError);
  assert.throws(() => floatToPcm16([0.5]), WavError);
  assert.throws(() => encodeWav(Float32Array.from([0.5])), WavError);
  assert.throws(() => encodeWav(Int16Array.from([1]), -1), WavError);
});

test("decodeWav refuses everything that is not mono 16-bit PCM", () => {
  assert.throws(() => decodeWav(new Uint8Array(4)), /fewer than 12/);
  const notRiff = encodeWav(Int16Array.from([1, 2]));
  notRiff[0] = 0x58;
  assert.throws(() => decodeWav(notRiff), /not a RIFF/);

  const stereo = encodeWav(Int16Array.from([1, 2, 3, 4]));
  new DataView(stereo.buffer).setUint16(22, 2, true);  // claim 2 channels
  assert.throws(() => decodeWav(stereo), /mono/);

  const eightBit = encodeWav(Int16Array.from([1, 2]));
  new DataView(eightBit.buffer).setUint16(34, 8, true);
  assert.throws(() => decodeWav(eightBit), /16-bit/);

  const compressed = encodeWav(Int16Array.from([1, 2]));
  new DataView(compressed.buffer).setUint16(20, 0x0011, true); // ADPCM
  assert.throws(() => decodeWav(compressed), /uncompressed PCM/);
});

test("decodeWav walks chunks — a synthesizer's LIST chunk before `data` is not read as audio", () => {
  // System.Speech (the fixture generator) commonly emits a LIST/fact chunk; assuming the canonical
  // 44-byte offset would feed metadata bytes to the model as samples.
  const pcm = Int16Array.from([100, -100, 200, -200]);
  const base = encodeWav(pcm, TARGET_SAMPLE_RATE);
  const listBody = new Uint8Array(8); // 8 bytes of metadata
  const out = new Uint8Array(base.length + 8 + listBody.length);
  out.set(base.subarray(0, 36), 0);                       // RIFF..fmt chunk
  const dv = new DataView(out.buffer);
  out.set([0x4c, 0x49, 0x53, 0x54], 36);                  // "LIST"
  dv.setUint32(40, listBody.length, true);
  out.set(listBody, 44);
  out.set(base.subarray(36), 44 + listBody.length);       // the real data chunk after it
  dv.setUint32(4, out.length - 8, true);
  const decoded = decodeWav(out);
  assert.deepEqual(Array.from(decoded.pcm16), Array.from(pcm), "the audio, not the metadata");
});

test("decodeWav takes what is really there when the data chunk is truncated", () => {
  // a few missing bytes at the tail must not discard the operator's whole utterance
  const full = encodeWav(Int16Array.from([1, 2, 3, 4, 5, 6]));
  const cut = full.subarray(0, full.length - 4);
  const decoded = decodeWav(cut);
  assert.equal(decoded.samples, 4);
});

test("decodeWav refuses a chunk that declares bytes past the end of the file", () => {
  const wav = encodeWav(Int16Array.from([1, 2]));
  new DataView(wav.buffer).setUint32(16, 9999, true); // fmt chunk claims 9999 bytes
  assert.throws(() => decodeWav(wav), /past the end/);
});

test("durationSeconds reads the payload, not the header, and never goes negative", () => {
  assert.ok(Math.abs(durationSeconds(WAV_HEADER_BYTES + 16000 * 2) - 1) < 1e-9);
  assert.equal(durationSeconds(0), 0);
  assert.equal(durationSeconds(10), 0);
});
