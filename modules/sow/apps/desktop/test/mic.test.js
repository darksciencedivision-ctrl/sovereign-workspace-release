"use strict";
/**
 * Phase 17C `.mic` — the push-to-talk recorder (apps/desktop/renderer/mic.js).
 *
 * The microphone is operator hardware, so `getUserMedia` and the AudioContext are injected and the
 * device is a double. What that leaves testable is exactly what matters: that the recorder always
 * RELEASES the device, that it refuses to hand back a capture it cannot honestly transcribe, and — the
 * property both reviews of this unit turned on — that no failure path ever yields something the caller
 * could mistake for real speech.
 *
 * `mic.js` is a browser script (UMD over `window`), so the globals it reads are stubbed here before it
 * is required.
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

// --- browser globals the module reads at load time ---
const Wav = require("../voice/wav");

class FakeTrack {
  constructor(bag) { this.bag = bag; this.stopped = false; }
  stop() { this.stopped = true; this.bag.stopped += 1; }
}
class FakeStream {
  constructor(bag) { this.tracks = [new FakeTrack(bag)]; }
  getTracks() { return this.tracks; }
}
class FakeAudioContext {
  constructor(opts, bag) { this.sampleRate = bag.deviceRate; this.state = "running"; this.bag = bag; this.destination = { id: "dest" }; }
  createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  createScriptProcessor() {
    const node = { onaudioprocess: null, connect: () => {}, disconnect: () => {} };
    this.bag.node = node;
    return node;
  }
  close() { this.state = "closed"; this.bag.ctxClosed += 1; }
}

function load({ deviceRate = 48000, getUserMedia = null } = {}) {
  const bag = { stopped: 0, ctxClosed: 0, node: null, deviceRate, now: 1000 };
  const win = {
    AudioContext: function (opts) { return new FakeAudioContext(opts, bag); },
    SovereignWav: Wav,
  };
  global.window = win;
  // Node ≥21 defines a getter-only `navigator`, so it is replaced rather than assigned.
  Object.defineProperty(global, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia: getUserMedia || (async () => new FakeStream(bag)) } },
  });
  delete require.cache[require.resolve("../renderer/mic.js")];
  require("../renderer/mic.js");
  const api = win.SovereignMic;
  bag.api = api;
  bag.make = (over = {}) => new api.MicRecorder({
    getUserMedia: getUserMedia || (async () => new FakeStream(bag)),
    AudioContextCtor: function (opts) { return new FakeAudioContext(opts, bag); },
    now: () => bag.now,
    ...over,
  });
  return bag;
}

// Fire ONE frame through the node the recorder installed, if it is still listening. (`_releaseDevice`
// nulls the handler, so this is a no-op once the device has been closed — as on a real device.)
function frame(bag) {
  if (typeof bag.node.onaudioprocess !== "function") return false;
  const data = new Float32Array(4096);
  for (let j = 0; j < data.length; j += 1) data[j] = 0.3 * Math.sin(j / 8);
  bag.node.onaudioprocess({ inputBuffer: { getChannelData: () => data } });
  return true;
}

// Push `seconds` worth of audible frames through, advancing the fake clock.
function speak(bag, seconds = 1) {
  const frames = Math.max(1, Math.round((bag.deviceRate * seconds) / 4096));
  for (let i = 0; i < frames; i += 1) frame(bag);
  bag.now += seconds * 1000;
}

test("a normal hold yields a transcribable 16 kHz WAV and releases the device", async () => {
  const bag = load({ deviceRate: 48000 });
  const rec = bag.make();
  await rec.start();
  assert.equal(rec.recording, true);
  speak(bag, 1);
  const out = rec.stop();
  assert.equal(rec.recording, false);
  assert.equal(out.sampleRate, 16000);
  assert.equal(out.inputRate, 48000, "the DEVICE's real rate, not the 16 kHz we asked for");
  const decoded = Wav.decodeWav(out.pcm);
  assert.equal(decoded.sampleRate, 16000);
  assert.equal(decoded.channels, 1);
  assert.ok(decoded.seconds > 0.9 && decoded.seconds < 1.1, `got ${decoded.seconds}s`);
  assert.equal(bag.stopped, 1, "every mic track stopped — the shell must not leave the device hot");
  assert.equal(bag.ctxClosed, 1);
});

test("a too-short hold THROWS rather than returning something routable", async () => {
  // the caller must have nothing it could mistake for speech: a mis-click is not an utterance
  const bag = load();
  const rec = bag.make();
  await rec.start();
  speak(bag, 0.05);
  assert.throws(() => rec.stop(), /hold the talk button/);
  assert.equal(rec.recording, false);
  assert.equal(bag.stopped, 1, "and the device is still released");
});

test("a hold that captured NOTHING throws rather than encoding silence", async () => {
  const bag = load();
  const rec = bag.make();
  await rec.start();
  bag.now += 2000;              // held long enough, but no frames ever arrived
  assert.throws(() => rec.stop(), /nothing was recorded/);
  assert.equal(bag.stopped, 1);
});

test("a denied permission throws with the reason NAMED and opens nothing", async () => {
  const denied = async () => { const e = new Error("denied"); e.name = "NotAllowedError"; throw e; };
  const bag = load({ getUserMedia: denied });
  const rec = bag.make({ getUserMedia: denied });
  await assert.rejects(rec.start(), /permission denied/);
  assert.equal(rec.recording, false);
  assert.equal(bag.stopped, 0);
});

test("a runtime with no Web Audio refuses instead of half-starting", async () => {
  const bag = load();
  delete global.window.AudioContext;                // the constructor falls back to the window global
  const rec = new bag.api.MicRecorder({ getUserMedia: async () => new FakeStream(bag), now: () => bag.now });
  await assert.rejects(rec.start(), /no Web Audio API/);
  assert.equal(rec.recording, false);
  assert.equal(bag.stopped, 0, "and no device was opened");
});

test("hitting the length cap KEEPS the audio captured so far (it does not discard the operator)", async () => {
  // The cap closes the DEVICE; an earlier revision keyed `recording` off the stream, so the caller
  // read the capped session as "the mic never opened" and silently dropped minutes of real speech.
  const bag = load({ deviceRate: 16000 });
  const rec = bag.make();
  await rec.start();
  speak(bag, 1);
  bag.now += bag.api.MAX_CAPTURE_MS + 1;
  assert.equal(frame(bag), true, "one more frame arrives and trips the cap");
  assert.equal(frame(bag), false, "after which the device is closed and no frame can arrive");
  assert.equal(bag.stopped, 1, "the device was closed at the cap");
  assert.equal(rec.recording, true, "but the capture SESSION is still open");
  const out = rec.stop();
  assert.equal(out.capped, true, "and the caller is told the audio is truncated, not whole");
  assert.ok(Wav.decodeWav(out.pcm).seconds > 0.5, "the speech captured before the cap survives");
});

test("cancel releases the device and yields nothing", async () => {
  const bag = load();
  const rec = bag.make();
  await rec.start();
  speak(bag, 1);
  rec.cancel();
  assert.equal(rec.recording, false);
  assert.equal(bag.stopped, 1);
  assert.throws(() => rec.stop(), /no capture is running/);
});

test("start() on an already-recording instance is a no-op, not a second device", async () => {
  const bag = load();
  const rec = bag.make();
  await rec.start();
  await rec.start();
  rec.cancel();
  assert.equal(bag.stopped, 1);
});

test("the module exposes NO synthesis or playback (I-V2/D-VOICE-02)", () => {
  const bag = load();
  const rec = bag.make();
  for (const name of ["speak", "say", "synthesize", "play", "playback"]) {
    assert.equal(typeof rec[name], "undefined", `MicRecorder must expose no ${name}()`);
  }
  const src = require("fs").readFileSync(path.resolve(__dirname, "..", "renderer", "mic.js"), "utf8");
  assert.ok(!/speechSynthesis|SpeechSynthesis|new Audio\(|\.play\(\)/.test(src), "no audio output path");
});
