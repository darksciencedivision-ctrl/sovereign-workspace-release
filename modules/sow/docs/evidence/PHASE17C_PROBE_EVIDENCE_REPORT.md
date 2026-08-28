# PHASE 17C `.probe` — EVIDENCE REPORT

**Work unit:** `phase-17c.probe` (first sub-step of directive §16 track **17C — voice: real engine (U74) + mic loop**)
**Date:** 2026-07-26 · **Host:** Windows 11, this build host · **Loop iteration:** 83
**Scope closed:** **U74** (OP-11 operator first-use finding **F1**) — the engine-state half of 17C.
**Scope explicitly NOT closed:** real microphone PCM capture into the live conductor session (`.mic`),
the operator's spoken-mic leg (operator first use), TTS (**still prohibited** — I-V2/D-VOICE-02).

---

## 1. The defect, and what was actually wrong

The operator launched the shipped shell on a host where WSL Parakeet **is installed and verified** —
this repo's own `docs/evidence/receipts/PHASE16E_REAL_PARAKEET_SMOKE.json` is a real transcription from
this machine — and the conductor pane badged the STT engine **"mock engine"**.

Every unit test passed, because each half was individually right: the probe returned false, and the
indicator faithfully rendered false as "mock engine". The defect existed only in the composition. Three
causes, the third of which the directive had not identified:

| # | Cause | Measured on this host, 2026-07-26 |
|---|---|---|
| 1 | **The probe asked the wrong question.** `_probe_nemo` ran `import nemo` | that is a **~0.04 s namespace-package import** (`nemo.__version__` 2.7.3) that succeeds whether or not ASR is usable — slow to fail, and weak when it passed |
| 2 | **The budget was below the real cost.** `PROBE_TIMEOUT_S = 8.0` | the import transcription actually performs, `from nemo.collections.asr.models import ASRModel`, costs **17.91 s cold / 7.02 s warm**; a cold `wsl.exe -- bash -c 'echo hello'` alone took **4.46 s** |
| 3 | **One answer decided the whole run.** `functools.lru_cache(maxsize=1)` | a single cold miss was pinned for the life of the process — the operator's install could finish, WSL could warm up, and the shell would still say no |
| 4 | **(found during this unit) the state was only ever learned as a side effect of a CAPTURE.** | so raising the budget to 90 s without moving the probe off the chrome's path would have traded a lie for a stall |

The independent gate-validator re-measured cause 2 itself and got **20.14 / 20.59 / 23.59 / 24.87 s cold**
and **7.09 / 7.31 / 7.48 / 8.05 / 8.25 s warm**.

**An honest negative result, recorded rather than buried.** Mutating the budget back to the original
**8.0 s did NOT fail the check** on a warm host — the probe completed in 7.3 s. Two of the validator's
five warm measurements (8.05 s, 8.25 s) *exceeded* 8.0 s. So 8 s sat **inside this host's noise band**:
the operator's "mock engine" was not a clean always-fail, it was a budget sitting in the measurement's
own variance, which is why it looked intermittent. The diagnosis stands — the cold measurements are
2.5–3× the old budget — but a falsification at 8.0 s is a coin flip and is not offered as evidence.
The load-bearing falsification below uses 3.0 s, below even the warm cost.

## 2. What was built

| Layer | Change |
|---|---|
| `adapters/voice_parakeet/wsl_parakeet.py` | probes `PROBE_IMPORT` = the exact import `WSL_TRANSCRIBE_SRC` performs; `PROBE_TIMEOUT_S` **8.0 → 90.0** (directive floor: ≥60 s); `lru_cache(1)` → a per-config **TTL cache** (`ProbeResult`, positive 900 s / negative 30 s) with `cached_probe` / `probe_state` / `reset_probe_cache` / `probe_nemo(force)`; **`SOW_NEMO_PROBE_TIMEOUT_S`** and **`SOW_NEMO_TRANSCRIBE_TIMEOUT_S`** honoured in `config_from_env` (a malformed value falls back to the measured default — a budget is a safety bound, never a reason to refuse) |
| `adapters/voice_parakeet/engine.py` | `detect_voice_stack(blocking, force)` gains **`nemo_state`** (`available`/`unavailable`/`unprobed`) + the `probe` record. `nemo` stays fail-closed (True only for a positive probe); new `real_parakeet_pending` |
| `control_plane/orchestration/conductor_voice_feed.py` | `select_engine` carries `probing`/`nemo_state`/`probe`; new **`run_voice_probe`** → `voice_probe_feed@1.0` (engine state ONLY — no bridge, no broker, no transcript) |
| `tools/live/emit_conductor_voice.py` | new `--emit-voice-probe [--cached-only] [--force]`; **the capture emitter no longer probes** (`blocking=False`) |
| `terminal/compositor/voice-indicator.js` | a **fourth** state: PROBING → `"probing…"`, never "mock engine" |
| `apps/desktop/voice/probe.js` (new) | the shell's asynchronous probe owner: instant `state()`, `ensureFresh()` (re-arms a stale answer), `refresh()` (force), `dispose()` (D-LOOP-1), ceiling derived from `SOW_NEMO_PROBE_TIMEOUT_S` |
| `apps/desktop/main.js` / `preload.js` / `renderer` | probe started in the background at first paint; `voice:probe` IPC (rate-limited); `shell:voice` push so the badge flips itself; **clicking the badge re-probes now**; teardown disposes the probe |
| `docs/OPERATOR_NEMO_INSTALL.md` | the probe, its measured cost, and both `SOW_*` knobs documented for the operator |

## 3. Self-check — every exit criterion, with real output

| Criterion (directive §16 track 17C, U74 half) | Result |
|---|---|
| Budget raised to **measured reality (≥60 s)** | `PROBE_TIMEOUT_S = 90.0`, set from the 17.91 s cold measurement with cold-VM headroom |
| Made **non-blocking** with a **visible "probing…"** state | receipt: `voice:state` read in **0 ms** while `probe_state:"probing"`, badge `🎙 probing…` |
| **Lifetime cache pin removed**; re-probe **on demand and after failure** | TTL cache + `ensureFresh()` re-arm + a clickable badge; receipt `rearm` leg: stale answer → `armed_probes 1→2` |
| **`SOW_*` env overrides honored** | receipt: reference probe ran with `timeout_s_in_force: 300` == `budget_s: 300`; the JS ceiling is derived from the same var |

**Suites (all foreground, this unit):**

| Suite | Command | Result |
|---|---|---|
| Python | `py -3.12 -m pytest tests/ -q` | **1395 pass / 0 fail** (270.77 s) — was 1370 before this unit |
| Electron shell | `node --test "test/*.test.js"` in `apps/desktop` | **301 pass / 0 fail** |
| Terminal layer | `node --test "test/*.test.js"` in `terminal` | **183 pass / 0 fail** |
| Lint | `py -3.12 -m pyflakes` over the 8 Python files touched | clean (ruff genuinely unavailable; §2.7 forbids installing it) |

> **U108 re-confirmed first-hand:** plain `python -m pytest` is Python 3.14 on this host and fails
> collection; only `py -3.12` runs the suite.

**In-Electron receipt (D-P16-0):** `node selfcheck/run.js voice-probe` → exit 0,
`docs/evidence/receipts/PHASE17C_VOICE_PROBE_SELFCHECK.json`, `ok:true`, **20/20 checks**. Measured on
this host: probe answered `available` in **21.86 s** at launch (cold) / **7.1 s** warm; badge
`🎙 probing…` → `🎙 parakeet-wsl ready` **with no operator action**; forced re-probe advanced the counter
1→2; `producer_never_claims_a_transcript` true; `expired_answer_is_not_advertised_as_probing` true.
The 16E receipt (`PHASE16E_REAL_SELFCHECK.json`) was regenerated and is **still green**.

**Load-bearing falsifications** — each applied alone, each restored **byte-identically** (sha256 verified),
each independently reproduced by the gate-validator:

| Mutation | Result |
|---|---|
| `PROBE_TIMEOUT_S → 3.0` (below even the warm cost) | receipt `ok:false`, shell **exit 1**, badge **`🎙 mock engine`** — the operator's exact F1 — with **one** failing check: `shell_verdict_matches_the_reference` (the 300 s-budget reference still said `available` at 14.5 s) |
| `voice-indicator.js` `probing` forced to `false` | receipt `ok:false`, **exit 1**, badge `🎙 mock engine` while probing, **two** failing checks: `unanswered_probe_is_never_labelled_mock`, `chrome_shows_the_open_question` |

Restored hashes: `wsl_parakeet.py` `c4cd2742…f2e0`, `voice-indicator.js` `63586c36…06d1`.

## 4. Both mandatory reviews ran FOREGROUND in this unit (D-LOOP-2 — nothing deferred)

**gate-validator: PASS_WITH_RESERVATIONS.** It re-ran all three suites itself (1394/301/183), took its
own cold and warm probe measurements, re-ran the receipt three times, and reproduced **both**
falsifications exactly with matching restore hashes. It confirmed the prohibitions swept clean: no
remotes, `docs/canonical` + `schemas` diffs empty with all 11 canonical SHA-256s recomputing to their
manifest values, no credential touched, nothing written outside the repo root, evidence append-only, and
**no live `claude`/`codex` process** on any path this unit adds.

**spec-auditor: PROHIBITED DRIFT — NONE**, with 1 BLOCKING / 6 MAJOR / 12 MINOR.

**Both found the same headline defect independently, and it was mine.** An earlier revision of
`VoiceProbe.state()` returned `probing:true` for **any** expired result while **nothing re-armed it** —
`voice:probe` had no renderer caller and there was no timer. So 15 minutes after launch (or 30 seconds,
on a host without NeMo) the badge would read `probing…` **forever, with nothing probing**: U74's own
shape — one answer decides the whole run — inverted into a permanently pinned "in progress". Worse, on
a no-NeMo host it *erased* the honest "mock engine" and its install pointer, which is the one actionable
thing that badge exists to say. My receipt could not see it: the whole run finishes in ~35 s, far inside
both TTLs.

**Every finding from both reviews is fixed in this unit**, except those recorded as new register items in
§5. The fixes:

- **BLOCKING/R1 — the false "probing…".** `state()` now claims `probing` only while a child is genuinely
  running. An expired answer is reported as **the last established fact, flagged `stale`** — never as a
  question the shell is not asking — and `ensureFresh()` (called by every chrome read) re-takes it, which
  is what finally delivers "re-probe **after failure**" in the product rather than in the API.
- **M-1 — the JS ceiling silently overrode `SOW_NEMO_PROBE_TIMEOUT_S`.** Python would wait 300 s and the
  JS owner would kill the child at its wired-in 120 s, badging "mock engine" on a host where Parakeet is
  installed: *U74 reproduced by applying the fix for U74.* Both ceilings are now **derived** from the env
  vars (`ceilingForEnv`, `captureCeilingForEnv`) and pinned by test.
- **M-2 — `voiceEngineDescriptor()` pinned a positive capture forever**, justified by a comment claiming a
  capture proves more because "a real transcription actually happened". That was **factually wrong**: the
  default capture path routes the stand-in mock and takes `real_available` from the same probe mechanism.
  It was the `lru_cache(1)` defect re-implemented one layer up. Availability now always comes from the
  probe (the maintained fact); the capture supplies only the engine identity, and only when a real engine
  genuinely transcribed **and** the probe still agrees it is reachable.
- **M-3 — producer/consumer disagreement about `mock`.** `run_voice_probe` emitted `mock:false` on an
  available host; only `probe.js` rewrote it. The honesty lived in the consumer, one new consumer away
  from an operator-visible false claim. `mock` is now **True at the producer**, with a test.
- **M-4 — the producer's "not asked yet" was flattened to `unavailable`** at the process seam and would
  have rendered "mock engine": F1 reintroduced between the two languages. Such an answer is now recorded
  as *nothing*, so the next read re-probes.
- **M-5/R3 — every talk press paid a full cold probe.** The emitter is a separate process with an empty
  cache, so the shell's background probe could never warm it, and the comment claiming otherwise was
  false. The capture emitter no longer probes at all (`blocking=False`): its stand-in ref always lands on
  the mock, so the probe bought a strictly unused answer for 7–22 s of the operator's time.
- **M-6/R2 — the badge upgraded "importable" to "transcribes your live speech".** Uncached weights, a
  broken CUDA/driver pairing or insufficient VRAM all leave the import green and transcription dead. The
  hint is narrowed to what the probe establishes, and the receipt now carries an explicit
  **`reference_scope`** stating that the "independent reference" is independent of the **budget only** —
  it shares `PROBE_IMPORT` and the config, so it cannot falsify a wrong probe *question*.
- **R5 — the self-check launcher ceiling (360 s) sat below the check's own internal sum (~640 s)**, so a
  cold host would be killed **before the receipt was written** (exit 124, no receipt) — exactly how U74
  stayed invisible. Raised to 900 s.
- **m-1 — orphan risk.** `teardown()` now disposes the probe. Honest limit: killing `py.exe` on Windows
  does not reap the `wsl.exe` grandchild, which exits on its own within the budget (**U135**).
- **m-2 — "re-probe on demand" had no operator surface.** The engine badge is now the re-probe control
  (click to re-check), which is what an operator who just finished the NeMo install needs.
- **m-3 — tautological receipt checks.** `no_tts` now also reads the **producer's** `tts` field.
- **m-5 — cross-language constants** are now pinned by a test that reads them out of the Python source.
- **m-6 — host-dependent probe tests** are hermetic (`shutil.which` pinned by fixture).
- **m-7 — undiscoverable knobs.** Both `SOW_*` budgets are documented in `docs/OPERATOR_NEMO_INSTALL.md`.
- **m-9 — unmetered forced re-probes** from the least-trusted surface are rate-limited (5 s), degrading
  to a cached read rather than an error.
- **m-10 — GPU cost at launch, which neither the auditor nor I had measured. Now measured:** the probe's
  ASR import reports `torch.cuda.is_initialized() == False` and `nvidia-smi` shows VRAM **unchanged at
  2240 MiB** across it. The launch probe consumes **no VRAM** and is not a hidden residency-planner
  bypass (invariant 22 intact).

## 5. Honest limits, and what this unit does NOT claim

- **It does not close 17C.** Real mic PCM → WSL Parakeet → the live conductor session is `.mic`. The
  spoken-mic leg is validated by the operator's first use; the loop never blocks on the operator (§1).
- **A green probe is not a proven transcription** (**U137**). The probe establishes that the NeMo ASR
  stack imports in the venv. Nothing here exercises `ASRModel.from_pretrained`. The nearest existing
  evidence that transcription works on this host is `PHASE16E_REAL_PARAKEET_SMOKE.json`.
- **The non-blocking leg is host-dependent in principle**: if a probe settled before the read, the check
  would short-circuit. It did not — `probe_state` was `"probing"` with `probes_started: 1` in every
  passing run, so the measurement is not vacuous, but the receipt is honest about the disjunction.
- **A positive answer is reused for up to 15 minutes**, so a venv removed mid-session is not noticed
  until the TTL expires or the next capture fails closed with its reason.
- **`voice_probe_feed@1.0` has no file in `schemas/`** (**U139**) — the same status as the existing
  `conductor_voice_feed@1.0`; shell-internal envelopes guarded by `isWellFormed*`. Recorded, not drift.
- **`apps/desktop/package-lock.json` remains untracked**, as it has been for several prior iterations; it
  is not an artifact of this unit and no new package was added.

## 6. Substitutions (directive §6)

The bounded `py -3.12` emitter is used as the shell's read-source rather than the authenticated WS-IPC
channel — the same recorded substitution the 16B picker and the 16C/16D/16E feeds use, for the same
reason (swapping the shell's `EchoControlSurface` gateway would displace the supervisor's liveness path).
No other substitution: the probe, the WSL invocation, the measurements, the badge and the receipt are all
real on this host.

## 7. Prohibitions (§2) — verified, and independently re-verified by the gate-validator

No push, no remotes, no publication. No credential created, read, stored or transmitted. Nothing modified
outside the repo root. `docs/canonical/` and `schemas/` untouched (all canonical SHA-256s recompute to
their manifest values). Registers and evidence append-only. **No live `claude`/`codex` process** on any
path this unit adds — the probe spawns `wsl.exe` and a local `py -3.12` only, and every shell run logged
`node_state=awaiting_live_conductor`, `legs mock/mock`. No TTS (I-V2/D-VOICE-02 stands).
