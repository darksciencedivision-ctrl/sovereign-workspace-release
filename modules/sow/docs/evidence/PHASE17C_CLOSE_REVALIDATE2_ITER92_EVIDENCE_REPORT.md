# PHASE 17C — `.close-revalidate2`, iteration 92 — EVIDENCE REPORT

**Verdict: GATE FAILED. `gate/phase-17c` was NOT created.**
**Date:** 2026-07-30 · **Branch:** main · **Unit:** `phase-17c.close-revalidate2`
**Work commits:** `d963ffd` (this unit) carrying forward `f2e91f7`, `e231b17`, `bc8532a`,
`dfe6631` (iteration 92's earlier, un-stated-in-LOOP_STATE commits — see §1)
**Evidence/register commit:** this commit.

---

## 0. The one-line summary

**The live evidence this track has been waiting on since iteration 85 finally passed.** The
packaged in-Electron receipt is green — real microphone-path PCM → real WSL Parakeet → real
bridge → the LIVE Fable-5 conductor, which answered; the supervisor's tool denial measured
rather than inferred; audio discarded; session and I-X3 terminal handed back. U150 is resolved.

**And the gate still fails**, on a defect the mandatory spec-auditor found in the same tree and
the builder then confirmed against source: **an admitted voice turn never disarms (U166)**.
After the first spoken utterance, the operator's own typed prompts are blocked and every tool
call is denied for the rest of the conductor session. That is the opposite of the thing track
17C exists to deliver, so no tag.

---

## 1. Loop-protocol reconciliation (directive §3.1) — state and tags DISAGREED

At entry: `git tag -l` newest gate = `gate/phase-17b`; no `gate/phase-17c`.
`LOOP_STATE.json` read `iteration: 91`, `last_commit: 5713393`, `next_step:
phase-17c.close-revalidate2`.

HEAD was `dfe6631` — **four commits past the recorded `last_commit`**, all dated 2026-07-30
(`f2e91f7`, `e231b17`, `bc8532a`, `dfe6631`), with no iteration-92 note and no LOOP_STATE
update. An iteration-92 turn had done real work and ended before protocol step 6. The same
shape as iteration 83's abort, and reconciled the same way: **tags are the truth**, those
commits are real and are carried forward under this iteration's number, and this report states
what they were. No reconciliation commit was needed (no tag disagreed); the state file is
corrected by this unit's final commit.

The working tree also carried, uncommitted:

* `apps/desktop/conductor/launch-source.js` — modified at 14:05, **ten minutes after the
  receipt run finished**, removing two verification lines that `e231b17` had deliberately added
  (`hook_command_shell !== HOOK_DISPATCH_SHELL`, `hook_command_verified !== true`). An
  unexplained, untested, post-receipt weakening of a fail-closed check, inside a declared
  product path. **Reverted to `dfe6631`.** Whatever its author intended, it cannot ride into a
  gate as an anonymous diff, and keeping it would have invalidated the receipt's product tree.
* `.dump_receipt.py`, `.wait_receipt.sh` — prior-turn scratch. Deleted.

## 2. Exit criteria (directive §16 track 17C) — self-check with real output

| Criterion | Result | Evidence |
|---|---|---|
| U74 probe: budget ≥60 s | **PASS** | `wsl_parakeet.py:57` `PROBE_TIMEOUT_S = 90.0`; receipt `probe_at_capture.elapsed_ms = 39254` — a 39 s probe that the old 8 s budget would have failed |
| U74 probe: non-blocking | **PASS** | `apps/desktop/voice/probe.js` — instant `state()`, background `start()`/`refresh()`, four states incl. visible `probing` |
| U74 probe: no lifetime cache pin | **PASS** | `_PROBE_CACHE`/`_PROBE_LOCK` + TTLs (900 s positive / 30 s negative) replace `lru_cache`; `wsl_nemo_available(force=True)` re-probes; validator's `grep -rn "lru_cache"` found only comments |
| U74 probe: `SOW_*` overrides honored | **PASS** | `config_from_env()` `wsl_parakeet.py:120-131`; JS kill-ceiling derived from the same var (`probe.js:71`) |
| Real PCM → WSL Parakeet → bridge → LIVE conductor | **PASS** | Receipt `real_engine_transcribed`, `routed_as_chat`, `delivered_into_live_conductor`, `live_conductor_answered` (answer `77`, 5039 ms, from a live `Claude Code v2.1.220 · Fable 5 · Claude Max` pane) |
| Propose-never-execute (inv 25) | **PASS** | `protected_verb_queued_not_delivered`, `protected_verb_reached_no_live_pane`; `deliver.js:41-46` never re-classifies the bridge's verdict |
| Transcribe-then-discard (inv 26) | **PASS** | `capture_files_during: true` → `capture_files_after: []`, `discarded: true`; validator confirmed on the filesystem |
| NO TTS (I-V2 / D-VOICE-02) | **PASS** | Both reviewers grepped every product path independently; the only synthesis is the fixture author, which refuses to run outside `SHELL_SELFCHECK` |
| D-P16-0 in-Electron receipt | **PASS** | electron 31.7.7 / node 20.18.0 / chrome 126, real ConPTY pid 99212, real lease `lease-f4c7e1710834` 1/2 → 0 |
| Confidence-calibration limitation recorded | **PASS** | U140 in the register, in `owed_record.routing_limits`, in `scope_note`, and enforced by two receipt legs |
| **Operator can keep conversing after a voice turn** | **FAIL — U166** | `turn-authority.js:250-261` + `:198-207`; see §4 |

## 3. Suites — real command output, run foreground on `d963ffd`

| Suite | Command | Result |
|---|---|---|
| Desktop | `cd apps/desktop && npm test` | **502 pass, 0 fail** |
| Terminal | `node --test terminal/test/*.test.js` | **201 pass, 0 fail** |
| Python | `py -3.12 -m pytest tests/ -q` | **1441 passed** (367 s) |

Independently re-run by the gate-validator: 502 / 201 / 1441, same numbers.

Freeze/canonical: `pytest -k "freeze or manifest or canonical"` → 3 passed; validator's
`compute_manifest.py --check` → "freeze check OK: no drift in FROZEN set". `git diff --check`
clean. `git diff --stat HEAD -- docs/canonical schemas` empty.

**Regression found and fixed this unit (U165).** On entry the Python suite was **red: 1430
passed, 9 failed**. The U163 live-call guard added by `e231b17` refuses provider CLIs by
executable NAME, which also refuses `codex --version`, `codex login status` and
`codex exec --help` — the Phase 15C `.detect` probes, which reach no model and cost nothing —
breaking `test_codex_detect_live` and every test reaching `build_host_picker`. Fixed test-first
in `d963ffd`: the guard now refuses by *billable* invocation, via an enumerated whole-argv
allowlist matched whole and never as a prefix. Red-first evidence: the new
`test_a_credential_free_metadata_probe_is_allowed_through` failed against the old guard, passes
now; `test_a_metadata_form_carrying_anything_else_is_still_refused` pins `exec --help <prompt>`,
`exec hi`, `--version hi`, bare `login` and bare `codex` as refusals. Both reviewers scrutinised
the loosening specifically and accepted it; the U163 case (`claude -p …` through the adapter's
own `generate`) still raises.

## 4. Why the gate failed — U166, an admitted voice turn never disarms

Found by the mandatory spec-auditor (finding B2). **Confirmed by the builder against source
before acceptance**, because a finding that blocks a gate is worth reading the code for:

`apps/desktop/voice/turn-authority.js:250-261` treats `Stop`/`StopFailure`/`SessionEnd` as
observation only. That part is *right*, and hard-won: the supervised child holds the transport
bearer, so a vendor lifecycle event is not authority — treating `SessionEnd` as authoritative
produced a reproducible deny → forged `SessionEnd` → allow bypass, fixed at iteration 88. The
defect is that **nothing was put in its place**. `_active` is cleared only by `reset()` from the
observed OS-process exit (`main.js:840`) or the operator chord (`main.js:1763`). So after the
first voice utterance of a session:

* every later `UserPromptSubmit` — **including the operator physically typing into pane 1** —
  is blocked (`:198-207`);
* every `PreToolUse` / `PermissionRequest` is denied for the rest of the session (`:212-238`).

The pane goes mute to the keyboard until the session is killed or the operator presses
`Ctrl+Shift+Escape` — a chord present in no renderer string, no pane chrome and no operator
document, and on Windows also the Task Manager shortcut. This contradicts directive §13 (OP-8)
item 2 and §16's DEFINITION OF DONE legs (a) and (b), which require typed **and** spoken input
to reach the *same* live conductor session. Two artifacts additionally assert the behaviour the
code lacks (`turn-authority.js:193-194`; `conductor_permission_profile.py:171`).

The receipt passed 41/41 because its single voice turn was the last act before teardown —
nothing followed it that the restriction could block. The receipt is honest about what it ran;
it simply never exercises a second turn. **That is the missing leg, and it is now the next
unit's exit criterion.**

## 5. Mandatory reviews — both run FOREGROUND this turn on `d963ffd` (D-LOOP-2)

**gate-validator: FAIL — "may `gate/phase-17c` be tagged on d963ffd: NO."** It called this "a
paperwork FAIL sitting on top of a substantive PASS": every 17C criterion verified PASS, the
receipt verified as genuine exact-source evidence, and the tag refused because the evidence
commit did not yet exist (D-1 receipt uncommitted, D-2 no report, D-3 registers missing
U162–U165, D-4 stale LOOP_STATE, D-5 untracked lockfile). **All five are discharged by this
commit.** Reservations carried: R1 (the `voice_tool_call_denied_before_execution` leg name
promises more than it measures → U164), R2 (guard fail-open shapes → U168), R3 (a stale honesty
clause in `make_voice_fixture.py:12`), R4 (the `pane-state.js` ordering that must never be
reversed → U167), R5 (the `--settings` metacharacter exemption is safe, and why).

Its central judgement, which it verified four independent ways rather than taking on trust:
`git diff --stat dfe6631 HEAD` over the receipt's seven declared product paths is **empty**; the
entire `dfe6631..HEAD` delta is two `tests/`-only files; neither is reachable by the runtime;
and recomputing the receipt's `hook_sha256` (`69abdcdd…`) and `settings_sha256` (`f0317b88…`)
against the current tree reproduces them exactly. **The bytes that ran are the bytes at HEAD.**

**spec-auditor: CHANGES_REQUIRED.** B1 (receipt does not describe the tagged tree), B2 (U166,
above — the finding that actually blocks), B3 (U162–U165 unregistered, and U165 double-used).
MAJOR: M1 (the receipt calls the microphone "the only" substitution; three more exist — now
registered), M2 (the muting state is invisible and its recovery chord undiscoverable —
invariant 27; folded into U166), M3 (leg name → U164), M4 (profile string asserts a disarm that
does not happen → U166), M5 (register's last word on U144 falsified → superseded). MINOR
m1–m6 → U168/U169 and the U167 ordering note. It found **no TTS in any product path** and **no
authorization logic in `mcp_server/`**, and confirmed the iteration-85–88 blockers (vendor
chrome as authority, hook-only authority, supervisor-process enforcement, PTY/lease identity)
are genuinely fixed rather than renamed.

**Where the two reviewers disagreed** — whether a `tests/`-only delta invalidates the receipt as
exact-source evidence (auditor B1 vs validator's verified NO) — this report records both and
follows the gate-validator, that question being precisely its mandate, on the strength of the
cryptographic binding above. Half of B1 also rested on a stale working-tree snapshot showing
`M launch-source.js`; that edit was reverted before the work commit (§1), as the validator
independently confirmed.

## 6. Substitutions (directive §6)

1. **Microphone.** The fixture WAV's samples are injected exactly where `MicRecorder.stop()`
   hands encoded bytes to `S.captureVoice`; everything below is the unmodified production path.
   The spoken-mic half is operator first use, per §16 — the loop never blocks on the operator.
2. **Operator-recovery gesture** — synthesised input event, not an observed keystroke.
3. **Tool-denial payload** — self-authored `PreToolUse` with a fabricated `session_id`; no
   vendor-originated tool call occurred (`vendor_tool_attempt_observed: false`).
4. **"Physical typed path"** — `term.input(data, true)`, not OS key delivery.

(2)–(4) were disclosed in the receipt's `scope_note` but **not labelled substitutions**; the
receipt calls (1) "the only one". Corrected here and registered as disclosure debt.

## 7. Prohibitions (§2) — held

No push, no remote, no PR. No credential read, stored or transmitted — the CLI uses its own
host-native auth. No purchase. Nothing modified outside the repo root; `docs/canonical/`
untouched (verified). Registers and evidence append-only; no history rewritten, no commit
amended. Live exchange budget: **one** live conductor answer, in the packaged receipt, spent
before this unit began; **this unit spent none**. D-LOOP-1: no Electron, no leaked governed
session, lease ledger `leases: []`, `in_use_after_release: 0` — verified at entry and at exit.
`config/live_operation.json` not committed (`git ls-files config/` → example only).

`apps/desktop/package-lock.json` is now **tracked** (validator D-5): a gate tag on a product
tree that does not pin the lockfile which produced the receipt is a reproducibility hole. It is
committed here rather than at the next receipt so the next run's product tree is complete.

## 8. Exact next action — `phase-17c.disarm`

1. Implement a **supervisor-owned disarm** for an admitted voice turn (U166). The vendor must
   not regain authority: the window must be bounded by something Electron main measures itself.
   A supervisor-side deadline is the only such signal identified so far; an unmarked
   `UserPromptSubmit` is forgeable by the bearer-holding child and is **not** a candidate.
   Test-first, including the forged-`SessionEnd` bypass staying closed.
2. Make the armed state **visible** and its recovery control discoverable (invariant 27, M2).
3. Correct the two artifacts that assert a disarm that does not happen (M4), the
   `voice_tool_call_denied_before_execution` leg name (U164/R1), the `make_voice_fixture.py:12`
   clause (R3), and the receipt's substitution disclosure (M1).
4. Regenerate **one** minimal exact-source packaged receipt whose voice turn is followed by a
   **second typed prompt that is accepted and answered in the same session** — the leg whose
   absence hid this defect.
5. Re-run both mandatory reviewers foreground on that exact tree. **Tag only on PASS.**

This is not a directive §8 BLOCKED condition: no credential, purchase, hardware action,
operator decision or irreconcilable canonical contradiction is required. Status stays RUNNING;
`consecutive_failures` resets to 0 because this unit produced commits.
