# PHASE 17E — EVIDENCE REPORT: fully-live assembled validation (`gate/phase-17e` · `product/fully-live`)

**Track:** 17E, AUTONOMOUS_BUILD_DIRECTIVE.md §16 (OP-11, operator ruling 2026-07-25) — **high-stakes
gate**, mandatory `gate-validator` + `spec-auditor`.
**Date:** 2026-07-31 · **Iteration:** 103 · **Unit:** `phase-17e.close`
**Predecessor tag:** `gate/phase-17d` · **Work commits on this track:** `b292783` → `f470533` →
`8919a1f` → `676362b` → `a64779d` → *(this unit's work commit)*.
**Gate evidence:** `docs/evidence/receipts/PHASE17E_FULLY_LIVE_SELFCHECK.json`, `source.commit`
`fa3e1a14bab07827f7985dda02962ce9c781a688`.

> **Read the scope sentence first.** `product/fully-live` names **a composition**: every
> machine-checkable leg of the operator's DEFINITION OF DONE holding **at once, in one Electron
> process**, with every un-evidenced half named. It does **not** mean the owed register is closed.
> Directive §16's premise that Phase 17 closes the entire remaining owed register is **not met** —
> this track alone opened U213–U226, and U116–U119 / U210–U212 carry forward. §8 states this plainly.

---

## 1. Exit criteria and how each was met

Directive §16 track 17E: *"One in-Electron assembled receipt covering the machine-checkable DONE legs
(a, c, d, e + fixture-voice), honest OWED markers for anything not evidenced; FINAL report addendum;
terminal tag `product/fully-live`; operator addressed ONCE. Mandatory gate-validator + spec-auditor
on the composition."*

| Exit criterion | Met by | Verdict |
|---|---|---|
| One in-Electron assembled receipt (D-P16-0) | `node selfcheck/run.js fully-live` from `apps/desktop`, Electron 31.7.7 / Node 20.18.0 / Chrome 126.0.6478.234, main pid 98044, `2026-07-31T19:57:43.340Z` → `20:00:47.819Z` | **PASS** — `ok: true`, **36/36 checks**, `failed_checks: []`, `error: null` |
| Receipt sources from the gated tree | `source.commit fa3e1a1` = HEAD at run time; `tracked_product_tree_clean: true`; no unexpected untracked product files | **PASS** — and proven by CONTENT independently (§4) |
| DONE leg (a) typed → live answer | pane 1's live `claude --model claude-fable-5`; prompt through the renderer's real `term.input → pane:input → SessionManager.write`; `written/echoed/submitted` all true; `● 87` | **PASS** |
| DONE leg (b) speech → real Parakeet → the SAME session | 6.715 s / 16 kHz / 214 926-byte fixture WAV injected at `MicRecorder.stop()`'s hand-off → **real WSL Parakeet** (`mock: false`, `real_available: true`, `transcribe_ms: 62 193`) → bridge → pane 1's live session → `● 73` in 5 044 ms; `capture_files_after: []` | **PASS** (fixture half; spoken-mic half OWED to operator first use, §7) |
| DONE leg (c) picker selection → governed live worker | 49 options enumerated from the host's own Ollama daemon; `qwen3:8b` spawned as `worker-pane-2`, pid 102296, RUNNING, `chrome_governed: true`, `subscription_governed: false` (inv 19) | **PASS** |
| DONE leg (d) live workers → gates → conductor synthesis | live `claude_code` worker `worker-claude-live` (`claude-opus-5[1m]`) executed, published a CANDIDATE over loopback MCP, real gate engine: plan `PASS`, stage `1/1`, acceptance `PASS`, `accepted_count: 1`, `operator_disposition: "pending"`, `torn_down: true` | **PASS on the worker half; the synthesizing conductor was MOCK** — §5 MF-A/MF-B |
| DONE leg (e) drawer shows only real session events | source `session_events`, `launch_badge_count: 0`, one row, provenance `event_id ev-1` / `channel voice:capture` / `feed_schema conductor_voice_feed@1.0`; protected verb **queued, not delivered**; decided through the governed authority (`selfAuthorized: false`); re-decision **refused** | **PASS** (n=1 — §6 R3) |
| I-X3 concurrency, the leg no earlier receipt could show | two live frontier terminals held **at once** against ONE allowance: `max_in_use_observed: 2`, `allowance: 2`, `baseline_in_use: 0`, sampled from a separate process while both were live | **PASS** |
| Honest OWED markers for anything not evidenced | 7 enforced `receipt.owed` keys + 6 `substitutions`, each carrying its U-reference; a missing key turns the receipt red | **PASS** |
| Teardown (D-LOOP-1) | conductor + worker killed, lease released, `in_use_after_release: 0`, `sessions_alive_after: []`, scratch ledger removed, operator's durable ledger digest **unchanged** (`317a684a…d68e92` before = after) | **PASS** — host process list confirmed afterwards: no `electron.exe`, and pids 98044 / 77736 / 102296 all gone |
| Mandatory gate-validator | ran **foreground, this turn**, isolated context, on this receipt | **PASS_WITH_RESERVATIONS** (§5) |
| Mandatory spec-auditor | ran **foreground, this turn**, on the composition | **FINDINGS** — no invariant violated, **prohibited drift NONE** (§5) |
| FINAL report addendum · terminal tag · operator addressed once | Phase-17 addendum in `FINAL_LIVE_REPORT.md`; `gate/phase-17e` + `product/fully-live` on this report's commit; §8 is the one operator message | **PASS** |

## 2. Self-check, foreground, this host, this tree

| Suite | Command | Result |
|---|---|---|
| Python | `py -3.12 -m pytest tests/ -q` | **1484 passed**, 0 failed, 0 skipped, 376.42 s |
| Desktop | `npm test` (`apps/desktop`) | **640 passed**, 0 failed |
| Terminal | `node --test test/*.test.js` (`terminal`) | **212 passed**, 0 failed |
| Mutation — pane input | `npm run test:falsify` | **ALL MUTATIONS CAUGHT**; `main.js` restored `50F31A9C…F29873D` **byte-identical** |
| Mutation — disarm authority | `npm run test:falsify:authority` | **ALL 11 CAUGHT**; 5 files restored **byte-identical** |
| Hermeticity (audit R4) | `py -3.12 tools/mutation/wsl_path_hermeticity_check.py` | **PASS** — 54 of 57 hermetic, 3 declared host skips |
| Canonical freeze | `py -3.12 tools/manifest/compute_manifest.py --check` | **"freeze check OK: no drift in FROZEN set"** |

Harnesses were run **one at a time** and restoration verified against HEAD, not against the harness's
own report. `--check` was used for the freeze deliberately: the regeneration command `CLAUDE.md`
advertises destroys the operator signature (**U222**). Plain `python` on this host is 3.14 without
`jsonschema`; the recorded interpreter (D-LANG-01) is **3.12**.

**Total: 2336 tests green, 0 failed, 0 skipped.**

## 3. Live spend, stated

**Three live exchanges**, all inside the receipt: the spoken prompt (`73`), the typed prompt (`87`),
and the dispatch worker. No diagnostic runs were needed this unit. The previous unit spent five and
ended at 92 % of the session limit; the allowance reset at 14:00 America/Chicago (19:00Z) and this
run started at 19:57Z, which is why the re-run was this unit's **first** act (§16 minimal-live
discipline).

## 4. Exact-sourcing — proven by content, not by timestamp

A 7-second gap between commit and run is not proof. The gate-validator refused to accept one and
proved sourcing by content instead; four fields in the receipt exist **only** in this tree:

- `receipt.scope_note` (4 135 chars) — present verbatim in HEAD's `fully-live-selfcheck.js`, **absent** from `676362b`;
- `receipt.owed.diagnostic_ledger_scope` and `receipt.owed.vendor_session_store_retention` — present in HEAD, **absent** from `676362b`;
- `receipt.dispatch.objective` — **byte-identical** to `tools/live/emit_conductor_dispatch.LIVE_WORKER_OBJECTIVE` at HEAD, compared by import;
- `approvals.protected_capture.engine.reason` — the **cause-first** string introduced by `a64779d`.

Also verified: the source contains 35 `receipt.checks.X =` assignments and the receipt carries all 35
plus the committed-tree check = **36 keys, zero missing** — no check was skipped by an early throw.
Host facts re-read live during validation matched the receipt field-for-field (residency `used 0 MB`,
pinned budget `55248`, 49 picker options, the `qwen3:8b` block, and the durable ledger digest on disk).

`0b0ea32` and `fa3e1a1` touched **docs only**, so product code at HEAD ≡ product code at `a64779d`.

## 5. The two mandatory reviews — both foreground, both on THIS receipt

Neither previous round's verdict carried over. Both reviewers ran in this turn, in the foreground,
against `fa3e1a1` and the 19:57Z receipt.

| Reviewer | Verdict | Findings |
|---|---|---|
| **gate-validator** (isolated context) | **PASS_WITH_RESERVATIONS** — "may be tagged… in the same commit that lands MF-A…MF-E" | 5 must-fix (**all documentation-level**), 10 reservations, 5 minors |
| **spec-auditor** (30 invariants + drift list) | **FINDINGS** — 1 MAJOR, 5 MINOR, 4 NIT. **No invariant violated. PROHIBITED DRIFT: NONE.** | tag blocked on F1 + F2 only |

**The decisive difference from the previous two rounds: every blocking remedy is in `docs/`, outside
`source.product_paths`.** Both reviewers said so independently. A documentation fix does not void the
falsifications the validation rests on, so the receipt survives and the gate can close in this unit.

### Independent verification the reviewers performed (not the builder's claims)

The gate-validator wrote its **own ~40-mutant adversarial harness** against `fully-live-verdict.js`:
`liveDispatchIsHonest` 16/16 conjuncts falsifiable; `approvalDrawerIsRealSessionEvents` 13/13, and it
**re-reproduced the iteration-100 drawer defect in both orderings** (refused now);
`twoTerminalsOnOneAllowance` 6/6; `owedMarkersAreComplete` red on a dropped key. It re-derived both
live legs from the receipt's own excerpts with this tree's matcher, re-ran every suite and both
mutation harnesses itself, and **executed the real `no_placeholders` criterion** to answer the
gate-softening question independently — its answer: **the gate is not softened**
(`_PLACEHOLDER_RE.search(LIVE_WORKER_OBJECTIVE)` → `False`; the same regex on a worker answer
containing "todo" → `True`). The spec-auditor re-verified each prior HIGH and MAJOR against this tree
by reading the code that emits each artifact, not the prose describing it.

### Disposition of every must-fix and blocking finding

| Item | Raised by | Disposition |
|---|---|---|
| **MF-C / F1** — the published refusal exhibit still asserts the gate accepted an artifact it refused | both | **DISCHARGED, in this commit.** `docs/evidence/live/PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.CORRECTION.md` is a sibling note carrying the correction, what remains true, and the lesson. The artifact is **not** rewritten (inv 12). `PHASE17B_LEGS_DISPATCH_FEED.json` carries the same literal but there it is true (stage 1/1, PASS) — named, untouched. |
| **F2** — commit attribution in the gate's own provenance contradicts the log | spec-auditor | **DISPROVED, by the exact command the auditor (which had no shell) asked for.** `git show --stat 676362b` → adds the four diagnostic fields and the gate-criteria brief ("judged by a deterministic gate whose criteria are") = the **reviewed** tree. `git show --stat a64779d` → changes `conductor_dispatch.py`, removing `"gate engine accepted it"` = the **H2 fix**. The auditor had the two hashes swapped. **The checkpoint's attribution and the exact-sourcing proof stand.** Recorded because a disproved finding on a high-stakes gate's provenance must be shown, not silently dropped. |
| **MF-A** — the check name `…and_the_conductor_synthesized` is backed only by a fixed adapter literal | gate-validator | **DISCHARGED as a disclosure, not a rename.** Stated here in the builder's own words: `dispatch.legs.conductor` was **`"mock"`**. `synthesized_by` reads `"conductor_fable5"` — a hard-coded literal at `adapters/conductor/adapter.py:51` emitted by *every* `ConductorAdapter` ever built, **not a measurement of which backend folded the accepted set**. The LIVE half of leg (d) is the **worker**. Registered as **U225**; the rename waits for a unit that already forces a re-run, because renaming it now would void this receipt for a wording change. |
| **MF-B** — `owed.conductor_initiated_dispatch` calls a mock-conductor synthesis "real" | gate-validator | **DISCHARGED as a disclosure.** That text lists "the synthesis" among things that "are real" without the qualifier. It is the flattering half. Corrected here: the worker, its CANDIDATE and the gate were real; **the synthesis was performed by the mock ConductorAdapter, not by the live Fable-5 session in pane 1.** Registered as **U225** with MF-A (same root). |
| **MF-D** — round-2 must-fix **MF2** has no recorded disposition anywhere | gate-validator | **CONFIRMED as a real hole in the evidence trail, and recorded rather than papered over.** `grep -rn "MF2" docs/` returns nothing. The round-2 report was **summarized** ("MF1–MF4 must-fix (all documentation/state)") instead of preserved verbatim, so MF2's text is **unrecoverable from this tree**. It is *plausible* it was "write the evidence report" — the fourth bookkeeping item — but that is an inference and is not asserted as fact. All four analogous items of **this** round are discharged in this commit and enumerated in this table. Registered as **U226** with the process lesson: a mandatory reviewer's must-fix list must be preserved verbatim in the evidence, never compressed to a count. |
| **MF-E** — the gate-closing artifacts do not exist | gate-validator | **DISCHARGED.** This report, the Phase-17 addendum to `FINAL_LIVE_REPORT.md`, the `DECISION_REGISTER` row, the register rows, `LOOP_STATE`, the two-commit convention, and both tags — all in this unit. |
| **F3** — `emit_conductor_dispatch.py:66` states the negation of what the code does | spec-auditor | **ACCEPTED, deferred with a reason.** The objective *is* published as a scoped MCP entry (`live_flow.py:841-846`) and read back (`model_adapter.py:75-76`); it is **also** concatenated verbatim into the graded body (`:94-95`) — the true statement is the second clause only. The comment errs in the **fail-safe** direction (it understates the system). Fixing it edits a `source.product_paths` file and would void this receipt for a comment. Registered under **U219**, fixed at the next unit that already re-runs. |
| **F4 / R1** — 3–4 of the 36 checks cannot go red, and the receipt does not denominate them | both | **ACCEPTED and stated here.** `the_capture_result_asserts_no_tts` and `the_capture_result_asserts_no_self_authorization` read constants (`deliver.js:112`, `main.js:1557`) — honestly *named* "asserts", and the invariants behind them are enforced elsewhere (mutation U185, `selfcheck-guards.test.js`, `test_conductor_voice.py`). `every_known_unevidenced_leg_is_named_with_its_reference` is literal-vs-literal, a static assertion. `the_protected_verb_leg_names_the_engine_that_produced_it` is near-tautological. **So "36/36" contains 3–4 static assertions**; a receipt-only reader is not told this, and could not be without a product edit. Registered under **U214/U216** and stated here instead. |
| **F5** — U220's check name asserts governing authority; the measurement is a label | spec-auditor | **ACCEPTED**, already open as **U220**; the M2-style rename is deferred with F3 for the same reason. |
| **F6** — the `substitutions` array omits the mock-conductor substitution | spec-auditor | **ACCEPTED** — that is exactly MF-A/MF-B, discharged as a disclosure here and registered as **U225**. |
| **N1–N4, m1–m5, R2–R10** | both | Accepted, non-blocking, recorded in the register (§7 and the round-3 rows). None changes a verdict. |

## 6. Reservations carried, in the reviewers' own terms

R1 the 36/36 denominator (above). R2 `composeVerdict` has no expected-key manifest — a silently
dropped check would shrink the denominator with `ok` still true; **did not manifest here**, all 35
assignments verified present. R3 leg (e)'s "ONLY" is exercised over **n=1** row of one kind; the
multi-row reproduction lives in `fully-live-verdict.test.js` (44 tests), not in the receipt.
R4 drawer provenance is a **shape** check — a canned row carrying a fabricated event id and a real
channel would pass it; what actually keeps the demonstration trio out of the product path is that
`tests/support/demo_approval_queue.py` is unreachable from it and `session_approvals` re-derives
every row's classification and fails closed. R5 (**U220**) the I-X3 check reads a label. R6
(**U223**) the empty-drawer check is partly self-guaranteed by `SHELL_SELFCHECK` log isolation.
R7 leg (c) evidences a **spawn**, not a usable model — no prompt is sent to `qwen3:8b` (live-budget
discipline), and the receipt does not say so; only the source comment does. R8 `scope_note`'s topic
sentence is stronger than the qualified body that follows it. R9 the receipt omits `feed.schema`,
`dispatched`, `by_descriptor`, `live_workers_owed` and the full drawer `rows`, so both verdicts are
recorded as conclusions a receipt-only reader cannot re-derive. R10 is discharged by this commit.

## 7. Substitutions (directive §6) — every one recorded, none presented as the real thing

1. **The physical microphone.** The fixture WAV's samples are injected at exactly the point
   `MicRecorder.stop()` hands its encoded bytes to `S.captureVoice`; **everything below that is the
   unmodified production path** — IPC payload, `CaptureStore` validation + write, real-engine
   selection, WSL Parakeet transcription, bridge routing, delivery into pane 1's LIVE ConPTY, the
   guaranteed discard. The fixture is OS-synthesized **test input** (the 16E carve-out); the product
   has no TTS. *Why:* operator hardware cannot be driven by an automated check; §16 puts the
   spoken-mic half in the operator's first use and the loop never blocks on the operator (§1).
2. **OS key delivery**, for the typed prompt and the disarming keystroke. Typed text reaches the
   session through the renderer's real `term.input → pane:input → SessionManager.write`; the disarm
   drives main's production `before-input-event` handler with a synthesized keyDown. *Why:* **U69** —
   17D drove 28 trusted keydowns into the focused xterm with no terminal data resulting, and no
   mechanism was isolated. The operator's own keyboard is the remaining witness.
3. **The operator's own objective**, for the governed dispatch — the same emitter the conductor
   chrome sources, asked for `--live-workers` once. *Why:* **U58** — the live conductor CLI does not
   itself choose to delegate over MCP.
4. **Real speech, for the PROTECTED-VERB half** of the approval leg: a scripted `audio:` stand-in
   that carries no PCM and is therefore routed through the **visible mock** engine
   (`protected_capture.engine.mock: true`, `real_pcm: false`) — recorded explicitly, because this
   receipt's `voice.engine` says `mock:false` about the **spoken** leg and a reader must not carry
   that across. Everything after the transcript is the production path.
5. **The host's real GPU capacity**, for the picker leg's admission budget: `SOW_VRAM_BUDGET_MB`
   pinned by arithmetic on the host's **real** residency snapshot (recorded verbatim in
   `worker.budget_source`) — never verified against actual GPU capacity.
6. **A frontier worker pane from the picker**: this leg launches the host's real **local** `qwen3:8b`
   (which holds no subscription terminal, inv 19). The frontier picker spawn is 17B `.spawn`'s own
   gated leg (`PHASE17B_SPAWN_SELFCHECK.json`).

**Genuinely OWED, in `receipt.owed` where the check enforces it:** the spoken microphone; physical
key delivery (**U69**); conductor-initiated dispatch (**U58**); speech-out TTS (**I-V2 / D-VOICE-02**
— a spoken answer would be an operator reversal of a frozen invariant, never built silently); cloud
Kimi K3 / Qwen 3.8 (**OP-10 16B**, needs a new provider authorization); the diagnostic-ledger scope
(**U111/U215**); and vendor session-store retention (**U146** — the audio is discarded, but the
delivered *transcript* becomes durable text in the vendor CLI's own session store, outside this
workspace and outside any retention this system controls).

## 8. Invariants and prohibitions

**No violation of any of the 30 canonical invariants; PROHIBITED DRIFT: NONE** — both reviewers,
independently. Spot-verified this round: inv 1 (`operator_disposition` stays `pending`; re-decision
refused; `selfAuthorized:false`), inv 2/29 (nothing born before `supervision_ready`; the live worker
passes the full gate chain — roster/`LIVE_OPERATION_AUTHORIZED`, provider-live, R8 §6 terms, CLI
presence *detected* not hardcoded, I-X3 acquire — with a credential-scrubbed child env; no naked
session path), inv 3 (model slug asserted only where the probe confirmed it, tri-state preserved),
inv 4 (`by_descriptor !== true` is a refusal), inv 7 (`mcp_server/` unchanged, every decision
delegated to `control_plane.policy`), inv 8 (objective routed as a scoped MCP entry; the brief's
channel defect owed as U219), inv 10 (workers publish CANDIDATE; no worker path reaches ACCEPTED),
inv 11/12/13 (provenance required of every drawer row; CAS head with an explicit conflict object,
never silent last-write-wins), inv 16 (failed artifact transitioned REJECTED; no override path),
inv 18, inv 19/21/I-X3, inv 24/25/26 (STT-only; protected verb queued not delivered, measured against
the live pane's own text; `capture_files_after: []`; the fixture synthesizer is `SHELL_SELFCHECK`-
guarded **and** file-only by construction), inv 30 (no new governance layer). Money/units: `Decimal`,
no float on these paths.

Standing prohibitions (§2) held: no push, no remotes, no publication; **no credential read, stored or
transmitted** (the CLIs use their own host-native auth); nothing modified outside the repo root;
`docs/canonical/` untouched and the freeze clean; registers and evidence append-only — the corrected
exhibit was **annotated, not rewritten**; `config/live_operation.json` not committed. Live sessions
were confined to this work unit and torn down inside it (**D-LOOP-1**). Both reviewers, the receipt
run, and every suite ran **in the foreground inside this turn** (**D-LOOP-2**).

## 9. Verdict

**`gate/phase-17e` PASSES.** The composition holds: one Electron process in which a live Fable-5
conductor in pane 1 answered both a spoken prompt (through real WSL Parakeet) and a typed prompt, a
picker selection started a live local worker, a live frontier worker's CANDIDATE went through the
real gate engine into an acceptance packet, the approval drawer carried only this session's own
event, and two live frontier terminals were held at once against one allowance — with every
un-evidenced half named in an enforced OWED block, and the two disclosure findings (the mock
synthesizing conductor; the un-denominated static checks) stated plainly above rather than left to a
reader to discover.

Tags applied on this report's commit: **`gate/phase-17e`**, **`product/fully-live`**.

*Written after both mandatory reviews completed, on this tree, in this turn — never before them.*
