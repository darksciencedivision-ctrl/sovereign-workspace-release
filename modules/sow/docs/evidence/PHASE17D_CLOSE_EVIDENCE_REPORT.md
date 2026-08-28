# PHASE 17D — EVIDENCE REPORT (`.close`: gate close)

**Track:** 17D — real-events approvals + defect closure (AUTONOMOUS_BUILD_DIRECTIVE.md §16, OP-11).
**Unit:** `phase-17d.close` — the last three items of the track, then the gate.
**Date:** 2026-07-31 · **Host:** this Windows 11 machine · **Loop iteration:** 99.
**Work commits:** `d742743` (the guard, the receipt, the R4 checker) → `85342c8` (the review fixes).
**Prior sub-step:** `.events` (`1282636` + `ea2332f`) — the drawer, already committed, not re-litigated
here except where this unit's own regression touched it.
**Receipt (D-P16-0):** `docs/evidence/receipts/PHASE17D_CLOSE_SELFCHECK.json` — `ok:true`, exit 0,
Electron 31.7.7, `node selfcheck/run.js pane-guards` from `apps/desktop`.
**Tag:** `gate/phase-17d`.

---

## 1. What this unit was for

The `.events` report ended by naming exactly what 17D still owed: the `pane:resize` guard (U73), the
non-hermetic wsl-PATH test (audit R4), the discharge of U69, and then the gate. This unit is those.

## 2. U73 — a pane with no session is answered, not dereferenced

**The defect, as the operator's log carried it on every single launch** (opened 2026-07-24 by the
gate-validator at `phase-16c.dispatch`):

```
Error occurred in handler for 'pane:resize': TypeError: Cannot read properties of null (reading 'resize')
```

The renderer fits pane 1 — the CONDUCTOR placeholder, which holds no ConPTY until the governed launch
admits one — and its first fit can arrive before `manager` exists at all. Electron's IPC layer caught
the throw, so nothing crashed and nothing got fixed. What was actually wrong is smaller and worse than
a crash: **a thrown handler returns no answer**, so "the shell refused this" and "the shell broke"
were the same observation from the renderer's side.

**What shipped.** The decision is a decision now, and it lives where a test can reach it —
`apps/desktop/panes/resize-intent.js`. It refuses, each with its own reason and none of them an
exception:

| Condition | Answer |
|---|---|
| no `SessionManager` yet (the fit beat supervision into existence) | `{resized:false, reason:"no admitted session"}` |
| the registry does not hold this pane (the placeholder — invariant 2) | same |
| geometry not a positive integer within a ConPTY `COORD` (invariant 29) | `{resized:false, reason:"invalid dimensions"}` |
| the SessionManager reports no live handle took it | `{resized:false, reason:"session not running"}` |
| the ConPTY throws (the session died mid-call) | `{resized:false, reason:"resize refused: …"}` |
| a live handle took the geometry | `{resized:true}` |

`apps/desktop/main.js` delegates to it and may not grow a guard of its own (a test reads the handler's
source and fails if it does — see §7/U211 for what that test can and cannot see). A refusal that is
NOT the ordinary placeholder one is logged once per pane and reason (invariant 27): a live pane whose
resizes are being turned away is a fault, and the renderer discards the answer object.

**Proof, in the packaged runtime** (`apps/desktop/selfcheck/pane-guards-selfcheck.js`, receipt above):
pane 1 is confirmed sessionless first (the check would be vacuous otherwise), then the REAL preload
bridge `window.sovereign.resize` — the same call `term.onResize` makes — is driven at the REAL handler:

```json
"placeholder_resize": {"rejected": false, "answer": {"resized": false, "reason": "no admitted session"}},
"live_resize":        {"rejected": false, "answer": {"resized": true}},
"bad_dimensions":     {"rejected": false, "answer": {"resized": false, "reason": "invalid dimensions"}},
"live_session_survived_bad_dimensions": true
```

**Falsification.** Re-inlining the pre-U73 dereference in `resize-intent.js` turns leg 3 into
`{"resized": true}` for a pane with no session and the receipt goes `ok:false`, exit 1, with
`error: "the sessionless pane's resize did not come back as a reasoned refusal (U73)"`. Restored
byte-identically (`3F089A49…961C2E` before the F1 fix) and re-run green. **The gate-validator
reproduced that green→red→green cycle independently**, having deleted the receipt first so the one it
read was provably from its own run.

**One honest limit.** The receipt cannot reproduce the null-`manager` moment: it waits for supervision
before it does anything, by which time `manager` exists. That branch — the operator's literal
`TypeError` — is covered by `pane-resize.test.js`, deterministically, for `null`, `undefined` and a
manager with no registry. The claim "no `pane:resize` handler error at startup" rests on the handler
being a total function (every throwing path caught, proven by the tests), not on a log observation
this unit made.

## 3. U69 — narrowed by one real layer, not closed

The receipt ATTEMPTS the physical-keystroke micro-link and RECORDS what happened. `receipt.ok`
excludes every `u69` field except the 16A control leg, so the gate never depends on synthetic key
delivery — a gate that did would be a gate on someone else's harness.

| Field | This host |
|---|---|
| `window_focus` | `{visible:true, window_focused:true, webcontents_focused:true}` |
| `active_element` / `focus_after_typing` | `xterm-helper-textarea` / `xterm-helper-textarea` |
| `keystroke_leg_events` | `{keydowns:28, first:{key:"e", code:"KeyE", isTrusted:true, target:"xterm-helper-textarea"}, textinput:1, beforeinput:1, input:1}` |
| `dom_keystroke_echo` | **false** |
| `dom_textinput_echo` | **true** |
| `xterm_oninput_echo` | true (the 16A control) |

So: 28 trusted keydowns arrived at the focused xterm textarea, focus was still there when the loop
finished, and no terminal data resulted. Driving that textarea's own text-input path plus a delivered
`Return` keydown DID echo through `xterm.onData → pane:input → PTY`.

**What that is worth, stated exactly.** The automated proof now starts one layer above 16A, whose
`term.input()` begins below the DOM entirely. What is not exercised is a real OS key event and
Chromium's handling of it. The first draft of this report and of the receipt asserted a mechanism for
that ("`sendInputEvent` does not perform the translation for printable characters"); **both reviewers
charged it and they were right** — no `textInput`/`beforeinput` observation had been recorded, and
`sendInputEvent` injects below the OS layer as well, so the "only one step left" framing understated
by one. The receipt now counts those events and says what was not exercised rather than why.

**U69 stays OPEN, narrowed, owned by 17E and the operator's own keyboard** — which is where directive
§16 puts operator-physical legs ("the loop NEVER blocks on the operator"). Calling it RESOLVED here
would be the dishonest version, and the gate-validator said so explicitly.

## 4. Audit item R4 — the wsl-PATH tests are hermetic, and it is measured

The `wsl_present` fixtures already pinned `shutil.which`; nothing had ever checked that pinning was
load-bearing. `tools/mutation/wsl_path_hermeticity_check.py` runs both probe files with a PATH that
contains no `wsl.exe` and compares them with the normal-PATH run:

```
child PATH resolves wsl to: None
normal PATH:   {'passed': 57, 'skipped': 0, 'failed': 0, 'error': 0}
stripped PATH: {'passed': 54, 'skipped': 3, 'failed': 0, 'error': 0}
SKIPPED [2] tests\integration\test_wsl_parakeet.py:149: Windows WSL-boundary induced-hang proof
SKIPPED [1] tests\integration\test_wsl_parakeet.py:189: real WSL managed-stdin proof
PASS: 54 of 57 probe tests are hermetic …
```

It fails if the collection differs, if any skip reason cannot be read, if a skip is not a declared
`skipif` host requirement, or if the pass count is not the baseline minus exactly those skips. The
**gate-validator falsified it** by removing the fixture's `monkeypatch.setattr`: 7 failed, checker red,
restored from git.

## 5. The reviews (both mandatory, both foreground this turn — D-LOOP-2)

**gate-validator — PASS_WITH_RESERVATIONS.** It re-ran all five suites itself, reproduced the
green→red→green receipt cycle with byte-identical restores, falsified the anti-inline test and the R4
checker on its own initiative, verified the canonical 4-hash set, `mcp_server/` untouched, no orphan
processes, and a clean tree. Its R1 was that the gate could not be tagged on `d742743` alone — no
evidence report, no register rows. That is this document and the register addendum.

**spec-auditor — FINDINGS (2 MAJOR, 5 MINOR, 3 NIT), no BLOCKING, no invariant violation, no
prohibited drift.**

| # | Finding | What was done |
|---|---|---|
| F1 (MAJOR) | `{resized:true}` was reported for resizes the SessionManager silently discarded — an ended session is still in the registry. The same over-claim class 17C fixed for `write()`. | `SessionManager.resize` now returns whether a live handle of the matching generation took it; the shell reports THAT. New tests in `terminal/test/session-manager.test.js` and a fake that can express the distinction. Residual: **U210** |
| F2 (MAJOR) | The R4 checker's skip-reason regex could never match real pytest output, so its anti-vacuity guard had never fired. | Regex fixed; the checker now REFUSES when it cannot read every skip it was told about, and the pass count must equal the baseline minus exactly those. Verified live: 3 skips read, 3 accounted. |
| F3 | A refused resize on a live pane was observable to nobody (invariant 27). | Logged once per pane and reason; the placeholder's ordinary refusal stays quiet. |
| F4 | No upper bound on renderer-supplied geometry while the comment claimed one. | Capped at a ConPTY `COORD` (32767), with the reason in the comment and both directions in the test table. |
| F5 | The U69 verdict asserted a mechanism it never measured, and sampled focus only before typing. | Events counted, focus re-read afterwards, verdict rewritten to say what was NOT exercised. §3. |
| F6 | The checker's premise was inverted ("all vacuous" — some would have FAILED) and "starts no WSL process" is true of the stripped leg only. | Both corrected, in the checker and in the two fixture docstrings. |
| N1 / N2 / N3 | id ownership; the fake over-approximated; a failed receipt write still reports ok. | N2 fixed with F1; N1 and N3 recorded in the register as answered-without-a-row. |

Validator reservations: R1 → this report + the register addendum; R2 → same defect as F1, fixed;
R3 → same as F5, fixed; R4 → §8 below; R5 → **U211**; R6 → **U212**; R7 → the checker docstring.

## 6. Full foreground evidence (this turn, on this host)

| Check | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | **1470 passed** (364.51 s) |
| `npm test` (apps/desktop) | **591 passed** (+10 this unit) |
| `node --test terminal/test/*.test.js` | **212 passed** (+3 this unit) |
| `node tools/mutation/pane_input_bypass_mutations.js` | ALL MUTATIONS CAUGHT, restore BYTE-IDENTICAL |
| `node tools/mutation/disarm_authority_mutations.js` | ALL 11 CAUGHT, five files BYTE-IDENTICAL |
| `py -3.12 tools/mutation/wsl_path_hermeticity_check.py` | PASS (§4) |
| `node selfcheck/run.js pane-guards` | receipt `ok:true`, exit 0, teardown `remaining=-` |
| canonical freeze | `6D3FD03B` / `8C9B7240` / `668089B5` / `CC414372`; all 11 canonical files match the manifest |
| `mcp_server/` | untouched across the whole track (invariant 7) |

The pane-input mutation harness's `PINNED_BASELINE` was updated **twice**, deliberately, as that
file's own rule requires — `main.js` changed shape twice in this unit — and mutation X3 was
re-anchored to the handler and back again when the handler regained a block body. Both runs above are
against the shipped bytes (`DEF73EBB…6DDD0`).

## 7. Substitutions and limits (directive §6, stated plainly)

* **The null-`manager` branch is unit-tested, not receipt-tested** — see the end of §2.
* **U69's last link is not machine-checkable here** — §3. Nothing in this unit closes it.
* **`resized:true` is a handle-level fact** (U210), the same caveat `write()` carries since 17C.
* **The delegation test is a drift alarm, not containment** (U211) — an aliased inline guard would
  pass it.
* **The R4 checker's allow-list is two literal strings over two files** (U212).
* No live model call, no credential, no network on any path in this unit. The self-check spawns one
  supervised PowerShell pane through the production path and tears it down in-unit (D-LOOP-1); the
  conductor auto-launch is suppressed under `SHELL_SELFCHECK`.

## 8. On the freeze manifest

`py -3.12 tools/manifest/compute_manifest.py` was run and its output **reverted**. Regenerating it is
not a no-op: it reorders `canonical_documents`, bumps `generated_ts` and `freeze_integrity_sha256`,
and adds ~40 accumulated `mutable_audit_files.evidence_reports` entries. No frozen canonical hash
moves. Re-signing a Phase-0 operator-signed attestation from inside a 17D unit would be worse than
leaving it, so the 11 canonical hashes were verified directly against the existing manifest instead —
zero drift. The gate-validator reviewed this decision and agreed with it (its R4).

## 9. Gate verdict

`gate/phase-17d` CLOSES. Track 17D's four items: the approval drawer sources only real session events
and the demonstration trio is test-only (`.events`, and the validator re-confirmed the trio appears
nowhere in the product tree); the `pane:resize` guard is shipped, pinned, falsified and restored
(U73 RESOLVED); audit R4 is discharged with a checker that itself goes red when the fixture is
removed; U69 is advanced by one measured layer and recorded honestly as OPEN-narrowed, owned by the
operator's keyboard at 17E.

Delegated closure per operator ruling 2026-07-16 (register OP-1..OP-3), basis OP-11 §16;
`decided_by: operator-delegation`.

**Next unit:** `phase-17e` — the fully-live assembled validation (HIGH-STAKES: mandatory
gate-validator + spec-auditor), then `product/fully-live` and the operator is addressed once.
