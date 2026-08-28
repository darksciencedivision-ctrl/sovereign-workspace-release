# FINAL LIVE REPORT — Sovereign Orchestration Workspace (Phase 15: Live Multi-Model Orchestration)

**Autonomous staged build under `AUTONOMOUS_BUILD_DIRECTIVE.md` §11–§14 (operator authorizations
OP-6 / OP-7 / OP-8 / OP-9, 2026-07-19).** Phase-15 track completed 2026-07-24 ·
`gate/phase-15a` → … → `gate/phase-15e` → **`product/live`** ·
**1011 Python tests + 193 JS tests = 1204 green, 0 skipped** · canonical freeze clean throughout.

> **Operator (Sam) — this is the one moment the loop addresses you, per your ruling.**
> Phase 15 built the live multi-model track on top of the completed Phase 0–13 core
> (`build/complete`) and Phase 14 product shell (`product/complete`). Every standing prohibition
> held (no push, no credential handling, no purchases, nothing outside the repo, canonical set
> frozen). The live-session lift you authorized (OP-6: `claude_code` + `codex`, 2 terminals per
> subscription; OP-9: live-terms confirmed) is honored **only** within its exact governed, fail-closed
> scope. **Nothing hit a BLOCKED state.** What is genuinely OWED is listed plainly in §4 — the honest
> headline is: **this loop session made no live model call and rendered no GUI itself**; the live
> conversations, the on-screen panes, and the live worker legs are **operator-run metrics** (the same
> §6 substitution every GUI/live surface in this build has used), and the remaining live-feed IPC
> wirings are disclosed, owed, and never faked.

---

## 1. Per-track gate table (tag · commit · verdict)

| Track | Gate tag | Tag commit | Verdict | What shipped |
|---|---|---|---|---|
| **15A — Live activation + concurrency governor** | `gate/phase-15a` | `5dbc625` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | `live_authorization` rewritten to OP-6 scope (two providers, 2 terminals/subscription, cites OP-6); enforced `config/live_operation.json` switch (fail-closed, absence⇒DENIED, never committed); dated R8 records for both providers; subscription governor upgraded to per-subscription allowance=2 with the n/2 count surfaced in the shell status bar; fail-closed paths re-tested. |
| **15C — OpenAI adapter (Codex CLI)** | `gate/phase-15c` | `af6f4fb` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | Live `codex` adapter behind the governed contract (non-interactive exec, per-node model selection for the GPT-5.5 line with probed IDs, `AGENTS.md` as node-controlled untrusted input T2, env-scrub superset, worktree isolation for the coding role). Ordered first per OP-7. Live smoke owed to an operator `codex login` run where absent. |
| **15B — Anthropic adapter: multi-model + conductor-capable** | `gate/phase-15b` | `185da86` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | Live `claude_code` adapter extended with per-node `--model` selection; CLI model-ID probe + recorded mapping for `opus-4.8` / `fable-5` / CLI default (unavailable⇒recorded fallback, surfaced never silent); backend made conductor-capable (bindable by the Phase-4 ConductorAdapter). |
| **15D — Live conductor (Fable 5) + inter-model flow** | `gate/phase-15d` | `7d661c5` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | The full governed loop with a LIVE conductor backend: decompose → assign by capability → workers publish CANDIDATE over MCP → gates → **conductor synthesizes the ACCEPTED set into an acceptance packet**; one bounded live debate (budgets enforced); live conductor succession (kill mid-run → resume on a different backend → zero loss → restore selection). U45 checkpoint-stamp defect resolved. Workers still local (**U58** — live conductor proven, live workers owed). |
| **15E — Node-launcher UI + visible assembled run** | `gate/phase-15e` | *(this commit)* | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | Six sub-steps (`.picker`/`.spawn`/`.conductor-pane`/`.objective`/`.voice`/`.recovery`): per-pane model picker with live `ollama list` enumeration + VRAM residency states; governed node spawn (supervisor+governor, naked sessions refused, allowance=2 proof); conductor-first pinned CONDUCTOR pane-1; operator command surface (objective intake + unified approval-queue drawer); voice-IN to the conductor (propose-never-execute, NO TTS); conductor-first layout restart recovery. See `docs/evidence/PHASE15E_EVIDENCE_REPORT.md`. |

**Track order 15A → 15C → 15B → 15D → 15E** as directed by OP-7 (OpenAI first). Every 15x gate was a
high-stakes gate and received an independent `gate-validator` re-validation in an isolated context;
substantive sub-steps also got a `spec-auditor` pass, with every MAJOR/MINOR fixed with pinning tests
**before** the gate closed. All five closed **PASS_WITH_RESERVATIONS** on the §6 operator-run/live-feed
substitution pattern — precedent set by P3A, P11, and 14A.

## 2. What is LIVE vs MOCK-FIRST vs OPERATOR-RUN (directive §10.4 honesty)

| Capability | Classification | Why (honest) |
|---|---|---|
| **Governed data path** (objective → decompose → assign → CANDIDATE → MCP → gate → conductor synthesis → acceptance packet; approval queue; succession; restart recovery) | **PROVEN (headless, real MCP)** | Exercised end-to-end against a **real loopback MCP server** on 1204 green tests. This is the system under test and it holds. |
| **Live conductor backend** (Fable-5 selection) | **PROVEN LIVE at 15D** | The 15D `.flow`/`.debate`/`.succession` live re-runs (OP-9) drove a real Anthropic backend as the conductor. |
| **Live worker legs** (Anthropic/OpenAI workers publishing CANDIDATE) | **OWED (U58)** | 15D proved a live *conductor*, not live *workers*; worker legs remain asserted-only until the live-flow worker wiring lands. Disclosed, not claimed. |
| **This 15E session's model calls** | **MOCK-FIRST — none made** | No new 15E product source calls a live model/subprocess/socket/urllib. The governed spawn path is built and gated; running it live is an operator act. |
| **Rendered GUI** (window, panes, Inspector render, per-pane picker, visibly-reattaching panes, live conductor conversation) | **OPERATOR-RUN metric (§6)** | Produced by an operator run of `apps/desktop` on the Windows host — the Phase-1-spike substitution. The governance/data paths behind them are headless-tested. |
| **Voice-IN (Parakeet STT → conductor)** | **GOVERNED PATH built; engine operator-run** | `voice_bridge/conductor_voice.py` routes on the same command path as typing (propose-never-execute for protected/destructive; transcribe-then-discard). Real Parakeet needs GPU+WSL+NeMo (track 14D, unmet on this host) — mock STT behind the same interface; live STT→bridge→conductor-write wiring owed (**U67**). |
| **Voice-OUT (TTS)** | **NOT BUILT — owed by operator decision** | Frozen invariant I-V2 / D-VOICE-02 prohibits it. Per OP-8 §13.6 a spoken answer is an explicit operator reversal (would become OP-9-TTS + a 16th track). Recorded, never faked. |

## 3. Standing prohibitions — all held (directive §2)

No `git push` / remotes / PRs / publication of any kind; no credential created, read, stored, or
transmitted (the `claude` / `codex` CLIs use their own host-native auth — §2.2 intact); no purchases
or sign-ups; nothing modified outside the repo root; `docs/canonical/` frozen throughout (the 4
canonical SHA-256 re-verified against `PHASE0_FREEZE_MANIFEST.json`: `6D3FD03B`, `8C9B7240`,
`668089B5`, `CC414372`); registers and evidence append-only; `config/live_operation.json` gitignored
and **never committed** (only `config/live_operation.example.json` is tracked); no authorization logic
added inside `mcp_server/`; `Decimal` (never float) for money/units; D-LOOP-1 teardown honored.

## 4. Genuinely OWED — listed plainly (all disclosed in `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`)

1. **U58 — live worker legs.** 15D proved a live conductor; live Anthropic/OpenAI worker CANDIDATE
   publication over MCP is asserted-only. The single biggest owed live item.
2. **U65 / U66 / U67 / U68 — live-feed IPC wirings for the shell.** Conductor badge (U65), approval
   queue (U66), voice audio→bridge (U67), and worker-pane chrome in the recovery snapshot (U68) are
   rendered/recorded honestly by the shell (empty drawer, request-only, selection literal) but not yet
   fed over the read-only IPC the inspector/statusbar already use. Same owed live-feed pattern.
3. **U63 / U64 — local coder residency.** A local coding node reserves/badges the picker-selected tag
   but OpenCode may auto-resolve a different coder model (U63); a queued/loading (non-resident) local
   node is returned as a live handle with no residency-completion gate before `execute()` (U64).
4. **Live model runs + rendered GUI** — operator-run metrics (§6), not produced by this loop session.
5. **Voice-OUT / TTS** — owed by operator decision (OP-8 §13.6); I-V2 stands until you reverse it.
6. **15C OpenAI live smoke** where `codex` was not yet installed/authenticated — owed to the one-time
   operator step (`npm install -g @openai/codex`, `codex login`), per the 15C skip-with-record.

None of these is a correctness defect or a BLOCKED condition; each is disclosed and owed, never faked.

## 5. How to run the live system (operator, on the Windows host)

1. **Authorize live sessions:** create `config/live_operation.json` from the tracked example
   (`config/live_operation.example.json`), citing OP-6, scope
   `{providers:[claude_code, codex], terminals_per_subscription: 2}`. This file is the fail-closed
   switch; its absence keeps every live path DENIED. It is never committed.
2. **Providers:** ensure `claude` is authenticated (already is on this host); for the OpenAI legs run
   `npm install -g @openai/codex` then `codex login` once. For local models, have Ollama running
   (`ollama list` is enumerated live into the picker).
3. **Launch the shell:** from `apps/desktop/`, `npm install` (Electron/xterm/node-pty are operator-host
   installs) then `npm start`. Pane 1 opens as the pinned **CONDUCTOR** (fable-5 selection). Type or
   speak to it; it orchestrates the other live model CLIs over the shared Sovereign MCP memory, pulls
   CANDIDATE results through the gates, and synthesizes them back into the conversation.
4. **Tests (any host with `py -3.12` + Node):** `py -3.12 -m pytest tests/ -q`;
   `node --test terminal/test/*.test.js`; `node --test apps/desktop/test/*.test.js`.

## 6. Terminal state

All Phase-15 tracks 15A–15E are gated (`gate/phase-15a` … `gate/phase-15e`, each
PASS_WITH_RESERVATIONS on the §6 substitution pattern). This report is written; the terminal tag
**`product/live`** is applied. **Promotion to a `SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming, enabling
live TTS (I-V2 reversal), and running the assembled live system are operator-reserved.** The loop now
sets `status: COMPLETE` and stops addressing you until you direct it again.

*End of Phase-15 live track. — the autonomous build loop, 2026-07-24.*

---

# PHASE 16 ADDENDUM — SHELL LIVE-WIRING & FIRST-USE FIXES (`product/usable`)

**Autonomous staged build under `AUTONOMOUS_BUILD_DIRECTIVE.md` §15 (operator authorization OP-10,
2026-07-24).** Phase-16 track completed 2026-07-25 ·
`gate/phase-16a` → `gate/phase-16b` → `gate/phase-16c` → `gate/phase-16d` → `gate/phase-16e` →
`gate/phase-16f` → **`product/usable`** ·
**1109 Python tests + (158 apps/desktop + 173 terminal) JS tests = 1440 green, 0 skipped** ·
canonical 4-hash freeze clean throughout (`6D3FD03B` / `8C9B7240` / `668089B5` / `CC414372`).

> **Operator (Sam) — the one moment the loop addresses you for this track, per your ruling.**
> Phase 16 closes the gap between the tested engine and your hands. You launched the shipped shell and
> reported: (1) could not type in any pane and panes showed no banner (the PTY↔xterm feed was dead);
> (2) no per-pane model selector; (3) voice unusable; (4) wanted Kimi K3 / Qwen 3.8 available. Each was
> fixed and — per the **binding D-P16-0 lesson** (headless tests alone shipped a runtime that failed at
> first launch) — every shell/UI change is now exercised by an **autorun self-check that runs INSIDE the
> packaged Electron runtime on this host** and writes a machine-readable receipt.

## 1. Phase-16 gate table

| Track | Gate tag | What it fixed / proved | In-Electron receipt |
|---|---|---|---|
| **16A — pane I/O (the defect)** | `gate/phase-16a` (high-stakes) | Root-caused + fixed: output did not stream into xterm and keystrokes never reached sessions. Pure `PaneFeed` merges byte-exact scrollback with the live stream by monotonic seq (no gap/dup); main tags `pane:data` + read-only `pane:scrollback`; renderer gives the xterm textarea real DOM focus. | `PHASE16A_*_SELFCHECK.json` |
| **16B — per-pane model picker** | `gate/phase-16b` | Picker backend wired to the shell: provider × model × role from the live enumeration incl. residency; governed `pane_node_spawn`; badge + n/2 chrome. Kimi K3 / Qwen 3.8 enumerated honestly from what the host's Ollama actually offers (OWED-pending-operator where only cloud). | `PHASE16B_PICKER_SELFCHECK.json` |
| **16C — live conductor in pane 1** | `gate/phase-16c` | Pane 1 governed-born as the conductor spawn path; badge sources the selection over IPC (closes U65); governed worker dispatch (closes U58 as far as honest evidence allows). | `PHASE16C_*_SELFCHECK.json` |
| **16D — status-bar + approvals feeds** | `gate/phase-16d` | Governor n/2 real count into the status bar (fixes "concurrency count unavailable"); approval drawer over read-only IPC (closes U66); recovery snapshot carries worker-pane chrome (closes U68). | `PHASE16D_*_SELFCHECK.json` |
| **16E — voice wiring** | `gate/phase-16e` | Talk button → capture → STT → bridge → conductor input, end-to-end (closes U67). **Real WSL Parakeet** detection + adapter, transcription proven live on host ("Testing 1234", conf 1.0, ~40 s, nvidia/parakeet-tdt-0.6b-v3); fail-closed to a **visibly-labelled mock** engine otherwise. `docs/OPERATOR_NEMO_INSTALL.md` written. **No TTS** (I-V2 / D-VOICE-02 stands). | `PHASE16E_*_SELFCHECK.json` |
| **16F — operator-visible assembled validation** | `gate/phase-16f` (high-stakes) | One packaged Electron session composes the whole operator-visible run: conductor governed-born → **type-to-conductor delivered + echoed into an admitted supervised ConPTY** → picker-selected worker recorded + governed dispatch (BY DESCRIPTOR, gate-ACCEPTED) → **approval GOVERNED-REFUSED** (inv 16, `self_authorized:false`) → **restart recovery** (conductor-first + worker chrome repainted, not re-attached). | `PHASE16F_ASSEMBLED_SELFCHECK.json` |

16A and 16F are the directive-flagged high-stakes gates; both closed with **mandatory independent
`gate-validator` confirmation** (16F: PASS with 4 non-blocking reservations; a load-bearing falsification
was performed and the target restored byte-identical). `spec-auditor` CLEAN on the 16F composition.

## 2. What is genuinely live vs OWED (honest — §6 / §10.4)

- **Live, proven on this host:** the packaged Electron shell renders and is typeable (16A); the picker
  enumerates the host's real Ollama models (16B); **real WSL Parakeet STT transcribed a real WAV on the
  GPU** (16E); the assembled composition — type→echo, governed dispatch, governed-refused approval,
  restart recovery — ran end-to-end in one Electron session (16F).
- **OWED / operator-run (never faked):** the **live interactive `claude` conductor backend** (§6 — the
  operator starts the real session; the shell's delivery/echo path is proven against a supervised
  stand-in ConPTY); **live worker CLI legs** (U58 — dispatch ran mock-first, honestly); the **live
  governed worker SPAWN from a picker selection** (U70 — the recorded selection + its chrome survive a
  restart); **real microphone PCM into a live conductor session** for the full voice→conductor loop; and
  the real-STT **confidence-calibration** item (presence-based on the real path; inv 25 unaffected). Kimi
  K3 / Qwen 3.8 remain OWED-pending-operator where the host offers them only via a cloud path.

## 3. How to exercise it (operator, Windows host)

1. From `apps/desktop/`: `npm install` then `npm start` — pane 1 opens as the pinned **CONDUCTOR**.
2. Any in-Electron self-check, one command from `apps/desktop/`:
   `node selfcheck/run.js assembled` (16F), or `picker` / `conductor` / `statusbar` / `approvals` /
   `recovery` / `voice` for the individual tracks. Each writes its receipt under
   `docs/evidence/receipts/` and mirrors the shell's pass/fail exit code.
3. Real voice: install NeMo/Parakeet in WSL2 per `docs/OPERATOR_NEMO_INSTALL.md` (two commands,
   operator-run); the shell then shows the **real** engine badge instead of "mock engine".
4. Tests (any host with `py -3.12` + Node): `py -3.12 -m pytest tests/ -q`;
   `node --test terminal/test/*.test.js`; `node --test apps/desktop/test/*.test.js`.

## 4. Terminal state

All Phase-16 tracks 16A–16F are gated. This addendum is written; the terminal tag **`product/usable`**
is applied. **Promotion to a `SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming, enabling live TTS (the I-V2
reversal, OP-8 §13.6 — pending your explicit confirmation), and running the fully-live assembled system
(live conductor backend + live worker CLIs + mic-into-live-session) are operator-reserved.** The loop
sets `status: COMPLETE` and stops addressing you until you direct it again.

*End of Phase-16 addendum. — the autonomous build loop, 2026-07-25.*

---

# PHASE 17 ADDENDUM — FULLY-LIVE IN-SHELL (`product/fully-live`)

**Autonomous staged build under `AUTONOMOUS_BUILD_DIRECTIVE.md` §16 (operator ruling **OP-11**,
2026-07-25).** Phase-17 track completed 2026-07-31 ·
`gate/phase-17a` → `gate/phase-17b` → `gate/phase-17c` → `gate/phase-17d` → `gate/phase-17e` →
**`product/fully-live`** ·
**1484 Python + 640 apps/desktop + 212 terminal = 2336 tests green, 0 failed, 0 skipped** ·
canonical freeze clean throughout (`6D3FD03B` / `8C9B7240` / `668089B5` / `CC414372` + 7).

> **Operator (Sam) — the one moment the loop addresses you for this track, per your ruling.**
>
> **Read this first, because it is the thing most easily misread:** `product/fully-live` names **a
> composition — every machine-checkable leg of your stated DEFINITION OF DONE holding at once, in one
> Electron process, with every un-evidenced half named.** It does **not** mean the owed register is
> closed. Directive §16's premise that Phase 17 would close the entire remaining owed register is
> **not met**: this track alone opened U213–U226, and U116–U119 / U210–U212 carry forward. Both
> mandatory reviewers required that this sentence be the first one you read.
>
> Your three first-use findings are fixed. **F1** — the voice badge said "mock engine" despite your
> verified WSL Parakeet: the probe's 8 s budget was shorter than `import nemo` actually costs on this
> host and an `lru_cache(1)` pinned one cold miss for the app's lifetime; the budget is now measured
> reality, the probe is non-blocking and re-probes on demand, and **real Parakeet transcribed real
> PCM into your live conductor session** in the closing receipt. **F2** — the approval drawer
> rendered three canned demonstration items as if they were pending work; it now sources **only real
> session events**, and the demonstration trio is unreachable from the product path. **F3** — pane 1
> is no longer a black `awaiting_live_conductor` pane: it spawns the real interactive `claude`
> (Fable-5 selection) through the full live-gate chain, and it answers.

## 1. Phase-17 gate table

| Track | Gate tag | What it proved | In-Electron receipt |
|---|---|---|---|
| **17A — live conductor session in pane 1** | `gate/phase-17a` (high-stakes) | The black pane ended. The governed conductor spawn runs the real interactive `claude` (fable-5 selection; fallback recorded, never silent) in pane 1's ConPTY through the full live-gate chain (live_operation switch → provider-live → OP-9 terms → I-X3 slot); admission opens only on a genuinely admitted governed session (inv 2 — no naked spawn); type→answer round-trip proven live. | `PHASE17A_LAUNCH_TICKET_*` / `_PTY_` / `_ROUNDTRIP_SELFCHECK.json` |
| **17B — live workers: picker spawn + live legs** | `gate/phase-17b` | A picker selection performs the **governed live spawn** (supervisor + I-X3 governor, refusals surfaced with reasons) — closes **U70**; conductor dispatch drives a **live** worker publishing CANDIDATE over MCP → real gates → synthesis, with leg labels unfakeable (`_assert_legs_honest`) — narrows **U58**. | `PHASE17B_TICKET_*` / `_SPAWN_SELFCHECK.json` |
| **17C — voice: real engine + mic loop** | `gate/phase-17c` | **U74 fixed** (probe budget raised to measured reality, made non-blocking, lifetime cache pin removed, `SOW_*` overrides honored). Real PCM → **real WSL Parakeet** → bridge → the LIVE conductor session. Propose-never-execute (inv 25) and transcribe-then-discard (inv 26) intact. **No TTS** (I-V2 / D-VOICE-02 stands). | `PHASE17C_VOICE_PROBE_*` / `_MIC_` / `_CLOSE_SELFCHECK.json` |
| **17D — real-events approvals + defect closure** | `gate/phase-17d` | The drawer sources **only real session events**; the demonstration trio is test-only and unreachable from the product path. `pane:resize` guarded for sessionless panes (**U73** — the `TypeError` on every launch is gone). The non-hermetic WSL-PATH test fixed (54/57 hermetic, 3 declared skips). | `PHASE17D_APPROVALS_*` / `_CLOSE_SELFCHECK.json` |
| **17E — fully-live assembled validation** | `gate/phase-17e` (high-stakes) → **`product/fully-live`** | **One Electron process, 36/36 checks, `failed_checks: []`**: live Fable-5 conductor in pane 1 answering a **spoken** prompt (real Parakeet, 62 s) and a **typed** prompt; a picker selection starting live local `qwen3:8b` from 49 host-enumerated options; a live frontier worker's CANDIDATE through the real gate engine into an acceptance packet (`operator_disposition: pending`); a drawer carrying only this session's own provenance-stamped event with the protected verb **queued, not delivered**; and **two live frontier terminals held at once against one allowance** (I-X3 = 2). Torn down in-unit; your durable lease ledger untouched. | `PHASE17E_FULLY_LIVE_SELFCHECK.json` |

17A and 17E are the directive-flagged high-stakes gates; both closed with **mandatory independent
`gate-validator` confirmation**, and 17E additionally with `spec-auditor` on the composition.

## 2. What is genuinely live vs OWED (honest — §6 / §10.4)

- **Live, proven on this host, in one process:** the conductor pane runs the real `claude` CLI and
  answers you; **real WSL Parakeet** transcribes real PCM into that same session; the picker
  enumerates and **starts** the host's real local models; a live frontier worker really executes,
  really publishes a CANDIDATE over MCP, and the **real gate engine** really decides — including
  refusing one, which is published as its own exhibit; two live terminals are counted against one
  subscription allowance by the governor.
- **OWED, never faked, each with a register row:** the **spoken microphone** (a fixture WAV is
  injected at `MicRecorder.stop()`'s hand-off — everything below that point is the production path;
  your own first use is the remaining witness); **physical key delivery** (**U69** — 28 trusted
  keydowns into the focused xterm produced no terminal data on this host and no mechanism was
  isolated; the typed legs use the renderer's real input path, and your keyboard is the witness);
  **conductor-initiated dispatch** (**U58** — the dispatch is invoked by the shell, not chosen by the
  live conductor CLI over MCP; the worker, the CANDIDATE, the gate and the packet are real);
  **the synthesizing conductor was the MOCK adapter** in that leg (**U225** — `legs.conductor:
  "mock"`, and `synthesized_by` is a fixed adapter literal, not a measurement); **speech OUT / TTS**
  (**I-V2 / D-VOICE-02** — a spoken answer is a reversal of a frozen invariant and is yours to make,
  never built silently); **cloud Kimi K3 / Qwen 3.8** (needs a new provider authorization; the local
  leg runs your real `qwen3:8b`); **vendor session-store retention** (**U146** — the audio is
  discarded and the capture directory is empty afterwards, but the delivered *transcript* becomes
  durable text in the vendor CLI's own session store, outside this workspace and outside any
  retention this system controls); and the **diagnostic-ledger scope** (**U111 / U215** — the
  self-check's ledger reads your durable one as a baseline, but not the reverse: for the duration of
  a check run your own shell does not count the check's leases).
- **Honest about the count:** the closing receipt reports 36/36, and **3–4 of those 36 checks are
  static assertions that cannot go red** (they read constants such as `tts: false`). They are named
  "asserts", and the invariants behind them are enforced by the mutation harnesses instead — but a
  reader of "36/36" deserves to be told, so it is said here (**U214 / U216**).

## 3. How to exercise it (operator, Windows host)

1. From `apps/desktop/`: `npm install` then `npm start` — pane 1 opens as the pinned **CONDUCTOR**,
   live, ready to talk to. Type into it. Hold talk and speak into it. Pick a model on any other pane
   and it spawns as a governed worker.
2. Any in-Electron self-check, one command from `apps/desktop/`: `node selfcheck/run.js fully-live`
   (17E, the whole composition — **spends three live exchanges**), or `conductor-roundtrip` /
   `worker-spawn` / `voice-mic` / `voice-conductor` / `approvals` / `pane-guards` for the individual
   tracks. Each writes its receipt under `docs/evidence/receipts/` and mirrors the pass/fail code.
3. Real voice needs NeMo/Parakeet in WSL2 per `docs/OPERATOR_NEMO_INSTALL.md` (two commands,
   operator-run) — already installed and verified on this host.
4. Tests (any host with `py -3.12` + Node): `py -3.12 -m pytest tests/ -q`;
   `node --test apps/desktop/test/*.test.js`; `node --test terminal/test/*.test.js`.

## 4. Terminal state

All Phase-17 tracks 17A–17E are gated. This addendum is written; the terminal tag
**`product/fully-live`** is applied. The loop sets `status: COMPLETE` and stops addressing you until
you direct it again.

**Operator-reserved, and the only things left that are not owed defects:** enabling spoken answers
(the **I-V2 reversal**, would-be OP-9-TTS — you asked for it, a frozen invariant forbids it, and the
loop will not add it silently); authorizing **cloud Kimi K3 / Qwen 3.8** as a new provider; and
promotion to the `SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming. Everything else outstanding is in
`docs/registers/UNRESOLVED_ISSUE_REGISTER.md`, named, with the reason it is still open.

*End of Phase-17 addendum. — the autonomous build loop, 2026-07-31.*


---

# PHASE 18 ADDENDUM — GROK BUILD + GEMINI/ANTIGRAVITY PROVIDERS (`product/multi-frontier`)

**Authorization:** OP-12 (operator, 2026-07-31) and **OP-12.1** (operator, 2026-08-01) —
`AUTONOMOUS_BUILD_DIRECTIVE.md` §17 and §17.1; the operator-adopted provider directive is preserved
verbatim at `docs/operator/OP12_PROVIDER_DIRECTIVE_GROK_ANTIGRAVITY.md`.

You authorized two new live frontier providers — **`grok_build`** (CLI `grok`, "Grok Build") and
**`google_antigravity`** (CLI `agy`, "Gemini · Antigravity"). Phase 18 built them into the existing
governed system, and then, on your OP-12.1 ruling, gave the canonical node vocabulary a successor
schema so they can be Sovereign nodes rather than product-layer guests.

## 1. Phase-18 gate table

| Track | Tag | Verdict | Evidence |
|---|---|---|---|
| 18A — host reconnaissance + provider runner | `gate/phase-18a` | PASSED | `docs/evidence/PHASE18A_EVIDENCE_REPORT.md` |
| 18B — registry, adapters, governor, picker, UI | `gate/phase-18b` | PASSED (validator mandatory) | `docs/evidence/PHASE18B_EVIDENCE_REPORT.md` |
| 18C — live acceptance | `gate/phase-18c` | PASSED as **skip-with-record** | `docs/evidence/PHASE18C_EVIDENCE_REPORT.md` |
| 18D — U227 amendment + registration + skipped legs | `gate/phase-18d` | PASSED (high-stakes) | `docs/evidence/PHASE18D_EVIDENCE_REPORT.md` |

## 2. What is genuinely built vs what is OWED — honest (§6 / §17)

**Built and measured, on this host, inside the packaged shell:**

- both CLIs are detected, and the model lists in the picker are the **CLIs' own** (`grok models`,
  `agy models`) — 1 Grok option and 11 Antigravity options, never fabricated, greyed with the real
  reason;
- both providers ride the **existing** registries, adapter contract, supervised ConPTY path,
  launch-ticket path and cost governor. No parallel registry, no second control plane;
- **I-X3:** `grok_build_subscription` and `google_antigravity_subscription`, allowance **1 each**,
  never merged, enforced at three layers and released on every exit path;
- **credential isolation:** the env scrub covers `XAI_API_KEY`, `GROK_API_KEY`, `GEMINI_API_KEY`,
  `GOOGLE_API_KEY`, `ANTIGRAVITY_API_KEY`; nothing is read, stored or transmitted, and receipts scan
  their own payloads for planted sentinels before writing;
- **the fail-closed world is measured, not asserted** (18C): every gate before your live switch
  passes and the switch is what refuses — with zero sessions, zero leases, your ledger file
  byte-identical, and `grok 0/1 agy 0/1` painted where you read it;
- **U227 is resolved by your OP-12.1 ruling** (18D): `schemas/node.schema@1.1.json` sits beside the
  **never-edited** frozen `@1.0`, the freeze manifest is extended additively and your signature on it
  survived, and both providers now register as Sovereign nodes through the real registry onto a
  hash-chained append-only log, with the record closed when the session ends.

**OWED, and the reason is you, not the code:**

- **no live Grok or Antigravity model call has ever been made by this build.** The §17 probe and the
  live in-Electron pane receipt are both unperformed;
- **the entry condition is your own:** each CLI's login, plus adding both providers to
  `config/live_operation.json` — a file this build never writes (invariant 1). It currently cites
  `OP-6` and authorizes `claude_code` and `openai_codex_cli` only, so both OP-12 providers are
  DENIED. That is the switch working, not a defect;
- `agy` exposes no offline auth surface, so whether you are signed in there is unverifiable without
  a live call (U233);
- no node record exists on your **durable** node log (`.sovereign_store/nodes/`) — the 18D records
  were written on a scratch log under a fixture switch, which is the §6 substitution, disclosed in
  the receipt itself. A durable record lands with the first live probe;
- **cloud Kimi K3 remains OWED-pending-your-authorization** (a new provider decision, unchanged).

## 3. How to make it live (one file, yours)

1. Log in to each CLI as you normally would (`grok`, `agy` — their own auth, nothing this build
   touches);
2. add `"grok_build"` and `"google_antigravity"` to `scope.providers` in
   `config/live_operation.json` and cite `OP-12` in `register_row` (the code-pinned scope already
   covers both — that half shipped at 18B; see `config/live_operation.example.json`);
3. then: `py -3.12 tools/providers/frontier_provider_recon.py --action probe --provider all` for the
   one harmless probe per provider, and `cd apps/desktop && node selfcheck/run.js op12-acceptance`
   for the in-Electron leg. Both refuse, loudly and by gate id, if step 2 has not been done.

Nothing else changes: the panes, the picker, the governor and the approval drawer are already wired.

## 4. Terminal state

All Phase-18 tracks 18A–18D are gated. This addendum is written; the terminal tag
**`product/multi-frontier`** is applied. The loop sets `status: COMPLETE` and stops addressing you
until you direct it again.

**Operator-reserved, unchanged and still the only things that are not owed defects:** the live
switch above; spoken answers (**the I-V2 reversal**, would-be OP-9-TTS); cloud **Kimi K3 / Qwen 3.8**
as a new provider; and promotion to the `SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming. Everything
else outstanding is in `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`, named, with the reason it is
still open.

*End of Phase-18 addendum. — the autonomous build loop, 2026-08-01.*

---

# PHASE 18E SUPPLEMENT — THE LIVE ACCEPTANCE LEG (`product/multi-frontier-v2`)

**Authorization:** OP-12.2 (operator, 2026-08-02) — `AUTONOMOUS_BUILD_DIRECTIVE.md` §17.2.
**Written 2026-08-02 at the `gate/phase-18e` close.** This supplements the Phase-18 addendum above;
that text is left exactly as it was written on 2026-08-01, and the two lines your own actions have
since overtaken are named in §3 below.

## 1. What you asked for, and what happened

You opened the live switch, completed both CLI logins, and ran the §17 probe yourself. §17.2 then
asked the loop for the other half: the **in-Electron acceptance leg**, per provider — a real picker
selection, a supervised pane that is a Sovereign node, the exact provider and model verified, **one
harmless prompt, one live response**, teardown, lease 0, a credential scan of every sink this check
can read, and durable-ledger consistency.

**Everything up to the prompt is built, run live eight times on this host, and measured. The prompt
and the response did not happen, and the reason is a question only you can answer.**

**One correction to the record while we are here, because it matters for what you expect next.** Your
probe run was recorded as both providers answering; the loop's own later measurement says that is
true of only one of them:

* **Gemini · Antigravity has answered live** — a governed headless probe from this build returned a
  real document whose `response` field the strict reader accepts;
* **Grok Build has never verifiably answered this build.** Under the same governed probe its `-p`
  mode exits **zero having said nothing** (`text: ""`, `stopReason: "cancelled"`; the instruction is
  restated in a `thought` trace and nowhere else) — that is **U310**. The earlier acceptance recorded
  from your own probe rested on the pre-U238 reader, which counted a token anywhere in the document,
  so it was **withdrawn as unverifiable** (**U311**) rather than trusted or contradicted;
* **neither has answered through a pane**, which is the path this gate is about.

Both CLIs raise their **own first-run directory-trust modal** the moment they start in this
workspace:

* `grok` — *"Grok Build may run or modify contents in this directory, posing security risks.
  Yes, proceed / No, quit"*
* `agy` — *"Do you trust the contents of this project? Antigravity CLI requires permission to read,
  edit, and execute files here. > Yes, I trust this folder / No, exit"*

**The loop did not press yes.** Answering grants a frontier CLI read/edit/execute authority over your
workspace: a protected action the app may never self-authorize (invariant 1), which your own OP-12
provider directive §11 refuses as an unsandboxed default — *"a provider CLI's own 'always approve'
setting is never operator approval"* — and which OP-12, an authorization about **subscription
terms**, never delegated. It is not a permission-mode problem: both panes already launch in the
least-authority mode this build pins and are asked anyway. Both mandatory reviewers were told to
attack that reading as over-strict; both judged it correct.

## 2. One command, and then it can finish

```
grok                                   # in this workspace → answer "Yes, proceed", then exit
agy                                    # in this workspace → answer "Yes, I trust this folder", then exit
node apps/desktop/selfcheck/run.js op12-live-acceptance --unit operator-run
```

Re-running the check is safe for the record: each run now writes its own dated receipt and never
overwrites an existing one. Let each hand-run CLI **exit** before the third line: a CLI you start by
hand takes no I-X3 lease, so
the governor cannot see it, and §17's one-session-per-provider rule would be answered by an
accounting that cannot see the other session (U325). The live budget is **untouched** — every one of
the eight runs spent **zero** live exchanges, because a gated leg stops before a prompt is drawn — so
that run starts with the directive's full one-prompt-one-answer-per-provider allowance.

## 3. Phase-18 gate table, completed

| Track | Tag | Verdict | Evidence |
|---|---|---|---|
| 18A — host reconnaissance + provider runner | `gate/phase-18a` | PASSED | `docs/evidence/PHASE18A_EVIDENCE_REPORT.md` |
| 18B — registry, adapters, governor, picker, UI | `gate/phase-18b` | PASSED (validator mandatory) | `docs/evidence/PHASE18B_EVIDENCE_REPORT.md` |
| 18C — live acceptance | `gate/phase-18c` | PASSED as **skip-with-record** | `docs/evidence/PHASE18C_EVIDENCE_REPORT.md` |
| 18D — U227 amendment + registration + skipped legs | `gate/phase-18d` | PASSED (high-stakes) | `docs/evidence/PHASE18D_EVIDENCE_REPORT.md` |
| **18E — live in-Electron acceptance** | **`gate/phase-18e`** | **PASSED, with the typed live round trip skipped-with-record on U317** | `docs/evidence/PHASE18E_EVIDENCE_REPORT.md` |

**Three lines of the 2026-08-01 addendum are overtaken — two by your own actions, one by the loop's
later measurement — and are corrected here rather than edited there:** its §2 says `config/live_operation.json` "currently cites OP-6 and
authorizes claude_code and openai_codex_cli only, so both OP-12 providers are DENIED" — you have
since opened it, and the receipts read `register_row: OP-12` with both providers authorized; and it
says "no node record exists on your durable node log" — there are now **79 rows** on
`.sovereign_store/nodes/node_events.jsonl`, 64 of them written by these live pane sessions, chain
intact (the gate's second reviewer recomputed every hash in it). And its §2 line *"no live Grok or Antigravity model call has ever been made by this build"*
was true the day it was written and is not now: the `.live.shape` sub-step made two governed live
probes, one of which (Antigravity) answered — see §1.

## 4. What 18E proved, on your host, in the packaged shell

For **both** providers, on the final run (`source.commit f5f0c3f`, clean tracked product tree before
and after the live sessions ran with this repo as their working directory):

- a **governed picker selection** through the same click path you use — no refusal, no naked spawn;
- a **supervised ConPTY pane** running the exact binary and the exact model your host enumerated
  (`grok-4.5`, `gemini-3.6-flash-low`), verified off the spawned process and its argv;
- a **durable I-X3 terminal** on that provider's own allowance-1 resource, seen from a separate
  process, counted 1 and handed back to 0 — ledger `leases: []` afterwards;
- a **`node@1.1` Sovereign node record** living `SPAWNING → READY(pid) → TERMINATED + exit` on your
  durable append-only log — invariant 2 now holds for the OP-12 pane path, not only for probes;
- the **§2.2 environment scrub** (10 credential-bearing names removed from each child);
- a **credential-sentinel scan across six sinks**, including the two durable stores these runs write
  into and each pane's screen at teardown — which is **not** the PTY transcript §17.2(1) asks for,
  because these CLIs paint on a buffer that keeps no scrollback; that gap is recorded as U324 and is
  the second thing this gate leaves owed;
- **teardown to zero** with nothing left alive (D-LOOP-1), on every run.

## 5. What is still OWED, and by whom

- **the live typed round trip — yours, one keystroke per CLI** (U317, §2 above);
- **a real PTY-transcript credential sink** (U324): the scan reads each pane's screen at teardown,
  and these CLIs keep no scrollback, so anything printed and repainted over was never scanned;
- **whether Grok answers at all through an interactive pane is unknown** (U310, U311, §1): its
  headless `-p` mode exits zero having said nothing on this host, the one recorded acceptance was
  withdrawn as unverifiable, and the interactive channel cannot be tested until the trust modal is
  cleared. The loop learned nothing about it and claims nothing;
- **`agy`'s auth state is still unverifiable offline** (U233) — its pane shows "not signed in →
  signing in…" and then the trust modal, which tells you nothing conclusive;
- **U312 is yours to rule on:** the `.live.shape` sub-step spent three live exchanges where §17
  allows one per provider. It is recorded as an overrun, not rationalised;
- **cloud Kimi K3 / Qwen 3.8** remain a new-provider decision; **spoken answers** remain the I-V2
  reversal; **`SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming** remains yours;
- everything else is in `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`, named, with its reason —
  including the four rows this gate opened (U322–U325).

## 6. Terminal state

Tag **`product/multi-frontier-v2`** is applied as a **successor** by the commit that carries this
supplement; `product/multi-frontier` is not moved (§17.1). It certifies the **governed path** —
supervised, leased, registered, scrubbed, scanned, torn down — and explicitly **not** a model's
reply: no model of either provider has answered through a pane, and of the two only Gemini ·
Antigravity has answered this build at all (§1). The loop sets `status: COMPLETE` and stops
addressing you until you direct it again.

*End of Phase-18E supplement. — the autonomous build loop, 2026-08-02.*


---
## ERRATA (appended 2026-08-16 by the SOW remediation programme, unit W-09 — see docs/evidence/SOW_REMEDIATION_FINDINGS_20260816.md)

The body above is left exactly as written. These are corrections, not edits.

- **The live switch this report tells you to author is superseded.** §3/§5 instruct the operator to
  author **OP-6** with `{providers: [claude_code, codex], terminals_per_subscription: 2}` (see the
  §1 note and the §15A row). The authorization in force is **OP-12**: four providers
  (`openai_codex_cli`, `claude_code`, `grok_build`, `google_antigravity`) at
  **`terminals_per_subscription: 1`**, with `grok_build` and `google_antigravity` capped at one
  terminal each **in code** regardless of config. Authoring the OP-6 shape today does not merely
  under-provision — a provider id the code pin does not recognise makes the loader fail closed for
  **every** provider (U237).
- **"Two live frontier terminals held at once (I-X3 = 2)"** (§17E row, and the §1 summary) describes
  the OP-6 allowance. Under OP-12 the allowance is **1**. The 17E evidence remains true of the tree
  it was measured on; it is not a statement about what this build will now permit.
- **"The conductor answers you"** describes a measured 17E session. It is not a claim that the
  conductor path is currently verified end to end: the Sovereign MCP stdio transport was found not
  to be UTF-8 in either direction and was repaired on 2026-08-16 (W-04), and a second candidate for
  the same failure — the server module is cwd-dependent and no MCP config pins a `cwd` — remains
  **open**. No live conductor bring-up has re-verified the path since.

*Errata ends.*
