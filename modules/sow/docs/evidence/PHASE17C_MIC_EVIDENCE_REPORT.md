# Phase 17C `.mic` — evidence report

**Work unit:** `phase-17c.mic` (directive §16 track 17C) · **Iteration:** 84 · **Date:** 2026-07-26
**Work commit:** `cfb9b5c` · **Review-fix commit:** `ce0e831` · **Evidence commit:** this one
**Tag:** none — `.mic` is a SUB-STEP. `gate/phase-17c` lands at the track close, not here.

---

## 1. What this unit closes, and the defect underneath it

Every voice path shipped before this one was driven by a scripted `audio:` ref that carries no PCM.
That was not a stylistic choice, it was a structural wall: `WslParakeetSTT.transcribe` refuses an
`audio:` ref by construction, and `select_engine` only reaches for the real engine `for_capture`. So on
a host with WSL Parakeet installed and verified, **no path existed by which the operator's actual voice
could reach the real engine.** `.probe` (iteration 83) fixed the badge that lied about the engine; the
engine still had nothing real to hear.

`.mic` supplies the missing thing — operator speech, as bytes NeMo can read — and proves it end to end
on this host.

**On this host, in the packaged Electron runtime, real PCM was transcribed by the real engine:**

```
[shell] [selfcheck:voice-mic] fixture 105326 bytes / 3.29s @ 16000Hz
[shell] [voice:probe] available in 7607ms — real Parakeet/NeMo detected in WSL
[shell] voice: operator push-to-talk (audio 105326 bytes of live PCM) → chat ... [audio discarded]
[shell] [selfcheck:voice-mic] engine=parakeet-wsl mock=false
                              transcript="The conductor should summarize the build status."
[shell] renderer permission GRANTED: media [audio]
[shell] [selfcheck:voice-mic] PASS
```

Receipt: `docs/evidence/receipts/PHASE17C_MIC_SELFCHECK.json` — **27/27 checks, `failed_checks: []`**.

## 2. What shipped

**The encode path.** `apps/desktop/voice/wav.js` is a pure UMD encoder/decoder — 16 kHz mono 16-bit
RIFF — used by *both* main and the sandboxed renderer, because two copies of a byte layout drift and a
drifted header does not crash, it transcribes to noise, which an operator reads as "Parakeet cannot
understand me". It resamples from the AudioContext's **own reported rate**, not the 16 kHz we asked
for: browsers routinely ignore that hint, and 48 kHz frames under a 16 kHz header play at a third speed.
Samples are clamped, not wrapped, so a hot mic distorts quietly instead of cracking into square waves.

**The capture.** `apps/desktop/renderer/mic.js` opens the device on press and releases it on every exit
path. `apps/desktop/voice/capture-store.js` owns the file: validate → write under the repo → transcribe
→ **discard in a `finally`**, on the return path and the throw path alike, plus a purge at startup and
teardown for the kill that outruns a `finally`.

**The seam (U134).** The emitter is a one-shot process, so its probe cache is always cold. A real
capture arriving there would either re-probe for 7–22 s *on top of* the transcription the operator is
already waiting through, or — non-blocking — see `unprobed`, decline the real engine, and route real
speech to the MOCK. That is U74's failure re-staged at the process boundary. `seed_probe_result` carries
the shell's established answer across. **Measured effect in the receipt: transcription fell from 44.2 s
unseeded to 20–24 s seeded.**

The seed is safe because of what it *cannot* do: it populates a cache, and `WslParakeetSTT.transcribe`
still performs the real WSL round trip and still fails closed. The validator attacked this directly with
a fabricated reason string against a nonexistent WAV and got `sourced:false`, a CLARIFY outcome and
`mock:true` — an honest error, never a fabricated transcript. And the trust runs one way only: any value
other than the literal `available` is discarded and a real blocking probe runs, so a negative can never
cross the seam to suppress the real engine.

## 3. The register items this discharges

| Item | State | Basis |
|---|---|---|
| **U137** — no leg establishes that a green probe implies a successful transcription | **RESOLVED** | Real PCM through the production path → `ASRModel.from_pretrained` → a transcript that recognises the spoken phrase. Reproduced by the validator independently, inside and outside Electron. |
| **U133** — a talk press has no in-progress affordance | **RESOLVED** | `capturing` is true while a capture is genuinely in flight; the receipt observes it *during* the round trip and clear after. Falsified: reverting to the hard-coded `false` fails exactly one check. |
| **U134** — `--cached-only` is a constant function across processes | **RESOLVED** | `seed_probe_result` + `--engine-state`. Provenance (`SEEDED_REASON_PREFIX`) rides into the receipt. |
| **U136** — the self-check reference probe forwards the full parent environment | **RESOLVED** | Scrubbed — *and* the launch probe in `voice/probe.js`, which the first attempt missed (validator MAJOR-2) and which is the one that runs on every shell start. |

## 4. Falsification — three mutations, each reproduced by the validator, each restored byte-identically

| Mutation | Result |
|---|---|
| `emit_conductor_voice.py`: `for_capture=True` → `False` | exit 1; `real_engine_transcribed`, `transcript_recognised_the_phrase`, `routed_as_chat`, `owed_record_honest`, `write_reported_written`, `write_echoed_into_pty` fail. Log: `engine=mock-stt mock=true transcript=null`. |
| `capture-store.js`: the discard record made to LIE (`{discarded:true}` without unlinking) | exit 1; **only** `audio_discarded_after` fails — because the check reads the filesystem, not the flag. The validator additionally found `npm test` catches it (4 failures). |
| `main.js`: `capturing: capturesInFlight > 0` → `false` | exit 1; **only** `capturing_visible_during` fails. |

Restoration verified by sha256 on all five load-bearing files, by me and independently by the validator.

An honest by-product: under the lying-discard mutation the orphaned WAV *was* reaped — by the teardown
purge. The safety net works, and it is the reason invariant 26 survives a mutation that defeats the
primary mechanism.

## 5. Both mandatory reviews ran IN THIS UNIT, foreground (D-LOOP-2). Every finding is fixed.

**gate-validator: PASS_WITH_RESERVATIONS.** Re-ran all three suites, re-ran the receipt itself,
reproduced all three falsifications, re-derived the freeze manifest by hashing (42/42 clean, drift 0),
and confirmed no `gate/phase-17c` tag exists.
**spec-auditor: 1 BLOCKING, 5 MAJOR, 9 MINOR. PROHIBITED DRIFT: none.**

### The BLOCKING one was mine, and both reviews found it independently

The talk button fell back to the scripted stand-in ref whenever capture failed or never began.
`captureVoice(null)` → `DEFAULT_AUDIO_REF` → MockSTT → `"show status"` → a CHAT verdict →
**a real write into the conductor's ConPTY.** An operator who pressed, *spoke*, and happened to have a
muted mic, a denied permission, or a 240 ms hold would have had a command they never uttered typed into
a live conductor session, with a transient label as the only sign.

I had written the safeguard into `mic.js`'s own header — *"Nothing here ever falls back to the scripted
stand-in ref"* — and it was true of `mic.js` and false of its only caller. I had also justified the
fallback in `renderer.js` as safe *because it was visible*. It is not: the visibility of a label does not
make a fabricated command in the conductor's input honest, and the label is transient while the injected
text is not. This violates invariant 1 (unauthored content in the command path) and invariant 3, and it
is precisely the pretend-to-hear the whole track exists to end.

**Fixed:** the talk button routes ONLY the operator's own recorded speech. A capture that fails is
reported and routes nothing. The stand-in path still exists for the indicator poll and the honesty
negatives — it is simply no longer reachable from the operator's button. Three receipt legs pin it
(`stray_release_routes_nothing`, `press_without_a_mic_routes_nothing`, `talk_button_never_fabricates`).

### Fixing it surfaced a defect neither review nor I had

`getUserMedia` is asynchronous, so a quick tap resolves the release handler *first*; the device then
opened behind it and **stayed open** — a hot microphone with no press holding it and the chrome reading
"listening…" indefinitely. Caught because the new receipt leg reported the button's label as
`🔴 listening…` after a completed tap. Fixed and pinned (`device_not_left_hot_after_a_tap`); the receipt
now reads `🎤 talk`.

### The other MAJORs, each fixed

- **The `media` permission grants the camera.** Electron's `media` covers audio *and* video; my handler
  granted it wholesale while its own comment called it "an allow-list of one". A renderer compromise —
  and this shell renders untrusted PTY output into its DOM — would have turned on the operator's webcam.
  Now `details.mediaTypes` is inspected, audio only, the synchronous check path gets the same rule, and
  **grants are logged as well as denials** (a capability taken invisibly is not observable state, inv 27).
- **`toBytes` allocated renderer-declared length before checking the cap.** `{length: 2e9}` — a few bytes
  over IPC — meant a 2 GB allocation and a two-billion-iteration loop *on the main event loop*, before
  the bound was consulted. The cap bounded the disk and nothing else. Declared length is checked first.
- **`voice:capture` was unmetered** while the far cheaper `voice:probe` is explicitly rate-limited for
  exactly this reason. Each capture writes megabytes and spawns py → wsl → a 0.6b model load; the only
  serialiser was a flag in the renderer, the surface invariant 29 says never to trust. Hard cap of one.
- **The "startup purge" did not run at startup.** The store was built lazily on first capture, so an
  orphan from a crash could survive weeks of sessions in which the operator never pressed talk — while
  the comment claimed a one-session bound. Constructed at bootstrap.
- **`REAL_CAPTURE_OWED` said the microphone was the ONLY remaining debt** on a feed whose own `note`
  reported the conductor ConPTY write as owed: one object asserting both. An OWED that *understates* is
  the more dangerous error, because nobody re-checks a debt declared paid — it is how a gate closes over
  incomplete work. Both debts are now named.
- **U136 was half closed.** `env-scrub.js`'s header listed three diagnostic children; two were fixed and
  the first on its own list — the **launch probe**, which runs on every shell start — still inherited the
  environment wholesale. Scrubbed, pinned by test.

### The one that could actually have broken a frozen invariant

`make_voice_fixture.py` **could have spoken aloud.** Under PowerShell's default non-terminating error
mode, a failing `SetOutputToWaveFile` (an antivirus lock, a handle from a crashed run, a read-only dir)
would fall through to the next statement and `$s.Speak(...)` would render **to the default audio
device** — the machine talking back, I-V2/D-VOICE-02 broken — while `powershell.exe` still exited 0 and
this tool reported "wrote no file", sending a reader hunting a filesystem problem. Inherited from the
16E smoke tool, but `.mic` raised the exposure materially by invoking it automatically on every receipt.

Fixed by construction: `$ErrorActionPreference='Stop'`, a try/catch that exits non-zero, and the file
sink verified present before `Speak` is called at all. **Verified by forcing the throw:**

```
$ py -3.12 tools/live/make_voice_fixture.py 'tools/live/_voice_fixture_bad<>name.wav' "this must never be spoken aloud"
exit 1  "error": "System.Speech exited 1: Exception calling \"SetOutputToWaveFile\" ... \"Illegal characters in path.\""
```
Nothing was spoken.

### The TTS carve-out itself — both reviews judged it independently

The fixture generator uses the Windows OS speech synthesizer. **Both reviews concluded, separately, that
this is not drift**: I-V2/D-VOICE-02 governs the *product's* voice-output surface, and this writes a
transcription *input* for a test. Both verified the containment rather than accepting it — a repo-wide
grep for synthesis APIs returns hits only in `tools/live/make_voice_fixture.py`, the pre-existing
`tools/live/real_parakeet_smoke.py`, one test comment, and prose. Nothing in `apps/`, `adapters/`,
`voice_bridge/`, `control_plane/`, `terminal/`, `mcp_server/`. The identical carve-out was recorded at
16E (`PHASE16E_REAL_PARAKEET_SMOKE.json`: *"OS System.Speech (test input only; NOT product TTS)"*).

The MINOR findings — a receipt leg measuring the shell's intent rather than the far side of the seam, a
stale probe answer seeded as current, `sampleRate` recorded from the renderer's claim rather than the
decoded fact, an 8-byte magic check where a full decode was available, a non-boolean reachable in the
invariant-26 field, a cross-instance purge race, the env-scrub pin covering data but not rule shape, a
stray fixture WAV, stale comments — are all fixed in `ce0e831`.

## 6. Suites

| Suite | Before | After |
|---|---|---|
| `py -3.12 -m pytest tests/ -q` | 1395 | **1411 passed** (272.23s) |
| `apps/desktop` `npm test` | 301 | **356 passed** |
| `node --test terminal/test/*.test.js` | 183 | **183 passed** |

`pyflakes` clean over the five Python files touched. `ruff` remains genuinely unavailable (§2.7 forbids
installing it). U108 re-confirmed: plain `python` is 3.14 here and fails collection — only `py -3.12`
runs the suite. The terminal suite needs the **glob** form; `node --test terminal/test/` reports
`pass 0 / fail 1` (validator note, recorded).

## 7. Substitutions (directive §6)

**One, and it is the directive's own.** A physical microphone cannot be driven by an automated check —
§16 track 17C says so: *"the spoken-mic half is operator first use"*. The fixture WAV's samples are
injected at exactly the point `MicRecorder.stop()` hands its encoded bytes to `S.captureVoice`. Every
step below that is the unmodified production path: the IPC payload shape, `CaptureStore` validation and
write, real-engine selection, the WSL Parakeet transcription, bridge routing, ConPTY delivery, the
guaranteed discard. The receipt carries this statement in its own `substitution` field.

Worth recording: the receipt's stray-event legs **did** open the real microphone on this host
(`renderer permission GRANTED: media [audio]`, and `mic.js`'s ScriptProcessorNode warning in the
renderer console), so the `getUserMedia` path is not merely written — it runs here. What is unproven is
a human speaking into it.

The bounded `py -3.12` emitter as the shell's read-source is the same recorded substitution the 16B
picker and the 16C/16D/16E feeds use, for the same reason.

## 8. Honest limits — what this unit does NOT claim

- **It does not close 17C.** Directive §16 requires *"→ the LIVE 17A conductor session"*. The receipt
  delivers a routed CHAT transcript into an **admitted supervised pane standing in for** the conductor,
  because the self-check's conductor pane is `awaiting_live_conductor` with admission SHUT. That is the
  same `manager.write` path, but it is not the same claim. Owed to `.close`, and now named in
  `REAL_CAPTURE_OWED` so it cannot be forgotten. **No `gate/phase-17c` tag was created.**
- **The spoken-mic half is the operator's first use.** Nobody spoke into a microphone here.
- **Confidence is not calibrated** (carried forward from 16E `.real`, restated because `.mic` makes it
  operator-facing for the first time). NeMo's hypothesis score is a log-probability, not a 0..1
  confidence; feeding it to the bridge's threshold would route *every* real utterance to CLARIFY. So
  confidence is derived from recognition: non-empty ⇒ 1.0, empty ⇒ 0.0. **Consequence, stated plainly:
  a confidently-wrong transcription is indistinguishable from a correct one at the routing layer.** The
  clarify path therefore protects against silence, not against mishearing. A genuinely calibrated
  confidence needs per-token scores the current WSL program does not emit (**U140**).
- **The resampler is linear interpolation**, not a windowed-sinc. Adequate for 16 kHz speech into a 0.6b
  model, and honest about being the simple choice.
- **`ScriptProcessorNode` is deprecated** in favour of `AudioWorklet`; used knowingly (a worklet needs a
  separately fetched module file, which is friction on a `file://` origin) and recorded (**U141**).
- **A crash mid-transcription can retain one capture** until the next startup purge. Bounded, not
  impossible — and the bound is only real now that the store is constructed at bootstrap.
- **The receipt's own stray-event legs are the only coverage of `wirePushToTalk`.** It lives in the
  monolithic renderer script and has no unit test; `mic.js` does (`apps/desktop/test/mic.test.js`).
- **`node-pty`'s `conpty_console_list_agent` intermittently crashes at teardown** with `AttachConsole
  failed`, printing a stack trace *after* the receipt is written. Cosmetic here — but the launcher
  mirrors the child's exit code, so a shell that died *before* writing a receipt could report success
  (**U142**). The validator hit the same flake once.
- **`apps/desktop/package-lock.json` remains untracked**, as for several prior iterations. Not an
  artifact of this unit; no package was added.

## 9. Prohibitions (§2) — verified, and independently re-verified by the gate-validator

No push, no remotes, no publication (`.git/config` has no remote section — push is structurally
impossible). No credential created, read, stored or transmitted; this unit *adds* a scrub. Nothing
modified outside the repo root — every write path is repo-local (`apps/desktop/.voice-captures/`,
`tools/live/_voice_fixture_selfcheck.wav`, `docs/evidence/receipts/`). `docs/canonical/` and `schemas/`
untouched: the validator re-derived all **42** freeze-manifest entries by hashing (not by regenerating)
with **drift 0**, and `git diff gate/phase-17b..HEAD -- docs/canonical schemas conductor .claude` is
empty. **No live `claude`/`codex` process** on any path this unit adds — the only children are `py.exe`,
`wsl.exe` and `powershell.exe`, and every shell run logged `node_state=awaiting_live_conductor`,
`legs mock/mock`. Recorded audio cannot be committed (`.gitignore`). **No TTS in the product**
(I-V2/D-VOICE-02 stands, and is now enforced by construction in the one tool that could have broken it).
