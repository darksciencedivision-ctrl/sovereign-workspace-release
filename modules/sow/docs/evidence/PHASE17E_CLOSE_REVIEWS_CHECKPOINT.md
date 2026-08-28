# PHASE 17E — WORK-IN-PROGRESS CHECKPOINT: the second review round, and what it cost the receipt

**Unit:** `phase-17e.close` (iteration 102) · **Status: THE GATE IS NOT CLOSED. NO TAG.**
**Date:** 2026-07-31 · **Directive:** AUTONOMOUS_BUILD_DIRECTIVE.md §16 track 17E (high-stakes gate)
**Work commits carried in:** `b292783` → `f470533` → `8919a1f` → `676362b`. **This unit's work commit
is the one that carries this file.** **Predecessor tag:** `gate/phase-17d`.

`gate/phase-17e` and `product/fully-live` are **not** created by this unit and the loop stays RUNNING.
The reason is §3.

---

## 1. What this unit was asked to do, and how far it got

The iteration-100 checkpoint named the next unit's three acts exactly: (1) re-run the composition
against the fixed tree; (2) re-run both mandatory reviewers in the foreground on the new receipt;
(3) only then the evidence report, the FINAL addendum, the two tags, and the operator addressed once.

**(1) is done and it went green.** The turn that authored `676362b` ran
`SHELL_SELFCHECK=fully-live` in the Electron runtime on this host **7 seconds after that commit** and
got `ok:true`, 36/36 checks, `failed_checks: []`, `source.commit` = `676362b`,
`tracked_product_tree_clean: true`. That turn then ended (print-mode, D-LOOP-2) before it could write
any evidence, so this unit inherited an uncommitted green receipt.

**(2) is done, in the foreground, and the reviewers split.** §3.

**(3) did not happen, and must not have.** §4.

## 2. What the green receipt showed

`node selfcheck/run.js fully-live` · Electron 31.7.7 / Node 20.18.0 / Chrome 126 · main pid 107528 ·
`2026-07-31T15:27:19.998Z` → `15:30:47.811Z` · receipt
`docs/evidence/receipts/PHASE17E_FULLY_LIVE_SELFCHECK.json`.

| DONE leg (operator's own words, directive §16) | What the run recorded |
|---|---|
| **(a) typing to pane 1 gets a live answer** | `claude --model claude-fable-5` admitted into pane 1's ConPTY through the governed launch (session `pane-1#107528.1`, pid 107740, `model_is_fallback: false`, `model_probe_state: "available"`). Prompt written through the renderer's real `onData → pane:input → SessionManager.write` path; `written/echoed/submitted` true; `answer_number: 53`. |
| **(b) speak → real Parakeet → the SAME session** | A 6.99 s / 16 kHz / 223 726-byte fixture WAV injected at `MicRecorder.stop()`'s hand-off → **real WSL Parakeet** (`mock: false`, `transcribe_ms: 65388`) → bridge → pane 1's live session, which answered `81` in 6 005 ms. `capture_files_after: []`. |
| **(c) a picker selection launches a governed live worker** | 49 options enumerated from the host's own daemon; `qwen3:8b` spawned as `worker-pane-2`, pid 94120, RUNNING, `chrome_governed: true`, `subscription_governed: false` (inv 19). |
| **(d) live workers → gates → conductor synthesis** | Live `claude_code` worker `worker-claude-live` (`claude-opus-5[1m]`) executed, published a CANDIDATE over loopback MCP, real gate engine: `plan PASS`, `stage 1/1`, `acceptance PASS`, `accepted_count: 1`, `operator_disposition: "pending"`, `torn_down: true`. |
| **(e) the drawer shows only real session events** | Source `session_events`, one row, provenance `event_id ev-1` / `channel voice:capture` / `feed_schema conductor_voice_feed@1.0`; protected verb queued, **not delivered**, decided through the governed authority (`selfAuthorized: false`), re-decision refused. |
| **I-X3 (the leg no earlier receipt could show)** | Two live frontier terminals held **at once** against ONE allowance: `max_in_use_observed: 2`, `allowance: 2`, sampled from a separate process while both were live. |
| **Teardown (D-LOOP-1)** | Conductor and worker killed, lease released, `in_use_after_release: 0`, `sessions_alive_after: []`, scratch ledger removed, the operator's durable ledger digest unchanged (`317a684a…d68e92`). Confirmed afterwards from the host process list: no orphan `electron`, `claude` or `ollama run`. |

**That receipt is now SUPERSEDED**, by this unit's own product changes (§4). It stays in the tree, and
is being committed, so the history shows what was measured and when — but it is not gate evidence and
must not be read as such.

## 3. The two reviews — both foreground, both against `676362b` and that receipt

Neither iteration-100 verdict carried over; they reviewed superseded code, and the largest semantic
change in the unit (`676362b`'s gate-criteria brief) landed after them.

| Reviewer | Verdict | Findings |
|---|---|---|
| **gate-validator** (isolated context) | **PASS_WITH_RESERVATIONS** — "may be tagged, conditional on four bookkeeping items landing in the evidence commit" | MF1–MF4 must-fix (all documentation/state), 12 minor, 5 reservations |
| **spec-auditor** (30 invariants + drift list) | **FINDINGS — "do not tag as it stands"** | 2 HIGH, 5 MAJOR, 5 MINOR, 4 NIT. **Prohibited drift: NONE. No invariant violated by the code.** |

**What the gate-validator did that mattered.** It refused to accept the 7-second timestamp as proof of
exact-sourcing and proved it by content instead: `676362b` added four fields to the check
(`dispatch.failed_count`, `node_refusals`, `gate_summary`, `worker_legs`); the green receipt carries
all four populated, and the receipt committed *inside* `676362b` — the 14:58Z RED run — has none of
them, so the running code could only have been `676362b`'s. It re-ran every suite and both mutation
harnesses and reproduced the numbers; it wrote its own ~45-case adversarial harness against every rule
in `fully-live-verdict.js` and **re-reproduced the iteration-100 drawer defect in both orderings**
(now refused); it independently falsified the launch-path guard by inserting `liveWorkers: true` into
`main.js` and restored the file byte-identically; and it executed the real `no_placeholders` criterion
to test the softening question for itself. Its conclusion on that: **not softened** — the brief is
derived from the constant, the brief's own text passes the criterion (necessary, because the adapter
embeds the objective into the graded body), and a marker in a worker answer is still refused.

**Why the spec-auditor's HIGH findings block a tag the validator was willing to grant, and why the
auditor is right.** Its two HIGHs are both about artifacts asserting properties they do not carry —
which is the exact defect class this track exists to prevent, and the reason the previous round's
green receipt was thrown away.

* **H1 — the evidence report asserted, in the past tense, reviews it did not contain.** True: the
  draft written before the reviewers ran said "Both mandatory reviewers ran in the foreground" above
  an empty `<!--REVIEWS-->` placeholder. That draft has been deleted rather than patched; this
  checkpoint replaces it, and the real evidence report is written after the re-run.
* **H2 — a published evidence artifact carried a sentence its own data falsifies.**
  `LIVE_WORKERS_MET["note"]` read *"…the real gate engine accepted it"*, and `live_workers_record`
  emits it on `aggregate == "live" and verified` **without ever consulting the gate**. So it is
  present, and false, in `docs/evidence/live/PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.json` — the
  run this track publishes as proof that the gate refuses live work, whose `acceptance_verdict` is
  `FAIL`. Structurally identical to the D3/U216 defect the previous round caught, and worse, because
  the literal is not merely uninformative but wrong on the exhibit.

Its MAJORs: **M1** the composition dropped U146 (17C's own disclosure that the delivered utterance
becomes durable text in the vendor CLI's session store) while asserting `audio_..._discarded`;
**M2** two checks were renamed *upward* onto hard-coded literals that cannot go red; **M3** the
"not a softened gate" defence cited a refusal run produced under the *bare* objective, i.e. the
configuration before the change; **M4** the brief is not MCP-scoped context — the adapter embeds it
into the graded bytes; **M5** the U215 residual is a permanent one-way asymmetry, not the
read-to-write window it was described as.

Both reviewers independently confirmed: canonical freeze zero drift over 11 files, `mcp_server/`
transport-only (inv 7), no naked sessions (inv 2/29), voice STT-only with no TTS on any path
(inv 24/25/26, I-V2), and the durable lease ledger untouched on disk.

## 4. What shipped in this unit — and why it voids the receipt

Every blocking finding is fixed. Three of them are in `source.product_paths`, so the green receipt no
longer describes the tree; **that is precisely why no tag exists yet.** A fix applied after a
validation voids the falsifications the validation rests on — the third time this phase has enforced
that, and the second time on this track.

| Finding | Fix | Pinned by |
|---|---|---|
| H2 | `LIVE_WORKERS_MET["note"]` no longer narrates the gate; it names the worker leg (U58) and points at `gate_summary` / `acceptance_verdict` / `accepted_count` | `test_the_u58_record_never_narrates_the_gate` |
| M1 | `vendor_session_store_retention` is a **required** OWED key; the receipt cannot drop U146 again | `test("the vendor session store is an OWED key…")` |
| M2 | `no_tts_on_any_path` → `the_capture_result_asserts_no_tts`; `shell_self_authorized_nothing` → `the_capture_result_asserts_no_self_authorization` | the names now match the reads; the invariants stay enforced by the mutation harness and `selfcheck-guards.test.js` |
| M3 | The refusal run is stated as evidence about the gate FUNCTION, not the briefed path, in the code comment and here | `test_the_cited_refusal_run_was_produced_under_the_BARE_objective` |
| M4 | Described accurately (it is a brief inside the graded artifact, not MCP-routed context); the channel itself is **U219**, owed | the docstring, and U219 |
| M5 | `owed.diagnostic_ledger_scope` and `scope_note` state the one-way asymmetry in the present tense | U215 restated |
| m1 (audit) | The brief no longer claims `claims_cite_evidence` binds the node's wording — it reads the adapter's claim records | a test that varies the prose with the claim records held fixed |
| m3 (audit) | The stand-in's engine reason names the no-PCM cause first; the probe's state is context, not cause | `test_select_engine_standin_names_the_standin_as_the_cause_whatever_the_probe_says` |
| m2 (validator) | A broker `ref` is required of protected actions only — `operator_surface` builds genuine plan/clarification rows with `ref: None` | two new drawer tests, both directions |
| m3/m4/m6 (validator) | `dispatch.objective` recorded; the drawer leg's `"ONLY"` states its n=1 and that provenance is a shape check; the demo-trio fixture carries `ref: null` as the real builders do | `fully-live-verdict.test.js` |

Registers: **U219–U224 opened**, **U215 and U146 restated**, H2/M2/M3/m1/m3 and the validator's minors
recorded as fixed-without-a-row, and the previous round's F11 note explicitly superseded — it chose
continuity over accuracy and M2 is the bill for that.

**MF1/MF3/MF4** (the FINAL addendum, `LOOP_STATE`, the decision-register row) are deliberately **not**
done: they belong to the commit that closes the gate, and this is not it. `LOOP_STATE` is updated to
record the truth about where the unit stands.

## 5. Test output, this host, after the changes

| Suite | Command | Result |
|---|---|---|
| Python | `py -3.12 -m pytest tests/ -q` | **1484 passed**, 0 failed, 341.93 s (was 1481 — 3 new) |
| Desktop | `npm test` (`apps/desktop`) | **640 passed**, 0 failed (was 637 — 3 new) |
| Terminal | `node --test test/*.test.js` (`terminal`) | **212 passed**, 0 failed |
| Mutation (pane input) | `npm run test:falsify` | **ALL MUTATIONS CAUGHT**; `main.js` restored `50F31A9C…F29873D` BYTE-IDENTICAL |
| Mutation (disarm authority) | `npm run test:falsify:authority` | **ALL 11 CAUGHT**; five files restored BYTE-IDENTICAL |
| Hermeticity (audit R4) | `py -3.12 tools/mutation/wsl_path_hermeticity_check.py` | **PASS** — 54 of 57 hermetic, 3 declared host skips accounted |
| Canonical freeze | 11 canonical files hashed against the manifest | **zero drift** (`CC414372` / `8C9B7240` / `668089B5` / `6D3FD03B` + 7) |

Both reviewers reproduced the pre-change numbers (Python 1481, desktop 637, terminal 212) themselves.
Plain `python` on this host is 3.14 without `jsonschema` and yields 76 collection errors — an
environment artifact; the recorded interpreter (D-LANG-01) is 3.12.

## 6. Live spend, stated

This work unit has now spent **five** live exchanges: two diagnostic (the 15:06Z red re-run and the
15:13Z gate-refusal run, both published under `docs/evidence/live/`) and three inside the green
receipt (spoken prompt, typed prompt, dispatch worker). The conductor pane's own status line read
**92 % of the session limit consumed** at 15:30 UTC, resetting at 14:00 America/Chicago. §16's
minimal-live discipline is why the next re-run is the next unit's first act rather than this turn's
last: it needs three more exchanges and should start from a fresh allowance.

## 7. What remains before `gate/phase-17e` can close

Exactly this, as the next unit's acts, in order:

1. **Re-run the composition** (`SHELL_SELFCHECK=fully-live`, in Electron, on this host) against **this
   unit's** tree, producing a receipt whose `source.commit` is that tree. The current receipt is
   superseded and must not be read as the gate evidence.
2. **Re-run both reviewers in the foreground** on the new receipt. Neither verdict above carries over.
   The gate-validator's standing answer is already conditional-yes; the spec-auditor's is *no* until
   its HIGHs are re-checked against the fixed tree.
3. Only then: `PHASE17E_EVIDENCE_REPORT.md`, the Phase-17 addendum to `FINAL_LIVE_REPORT.md`
   (**MF1**), the decision-register row (**MF4**), the two-commit convention, `gate/phase-17e`,
   `product/fully-live`, `status: COMPLETE`, and the operator addressed once.

**And one instruction the final report must carry** (gate-validator r3, and this unit agrees):
`product/fully-live` names **a composition — every machine-checkable leg of the operator's DEFINITION
OF DONE holding at once in one Electron process, with the un-evidenced halves named**. It does
**not** mean the owed register is closed. Directive §16's premise that Phase 17 closes the entire
remaining owed register is not met: this track has opened U213–U224, and U116–U119 / U210–U212 carry
forward. Saying otherwise in the one message the operator gets would be the largest over-claim in the
build.
