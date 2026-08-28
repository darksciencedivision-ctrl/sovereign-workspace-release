# Phase 19 · unit 19.3 — U328: nothing writes into a pane that may be showing a modal

**Unit:** `phase-19.3` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, U328 / cold-audit finding B2).
**Work commits:** `b3c343a` (the gate and its wiring — committed by a PRIOR turn that then died
before any review, see §0), `073f322` (the in-Electron receipt and its own falsification),
`0f51e8c` (U360 — the repair the receipt forced), `1440b84` (the round-1 review remediation),
`5ec4213` (U364 — the race the remediation's own receipt run exposed).
**Gate:** none. Phase 19 closes at unit 19.10 with `gate/phase-19`; this is a sub-step. **No tag
was created or moved by this unit** — `gate/phase-19` does not exist and `product/multi-frontier-v2`
still points at `cd08878`.
**Round-2 commits:** `fa35797` (the falsification the reviewers showed was ungraded, plus one
observability repair) and `eada45c` (which reverts a behaviour change `fa35797` should not have
carried, and fixes a mutation that graded itself — see §5.4).
**Docs/loop commits in the range** (named so the enumeration is complete): `7cc2115` (the round-1
evidence and rows) and `89f6f2c` (loop state).
**Reviewers:** gate-validator and spec-auditor, foreground and in-turn (D-LOOP-2), **two rounds**.
Round 1 on `0f51e8c`: **gate-validator FAIL** (1 BLOCKING, 2 MAJOR, 3 MEDIUM, 2 MINOR);
**spec-auditor PROHIBITED DRIFT NONE** (0 BLOCKING, 4 MAJOR, 4 MEDIUM, 6 MINOR). Round 2 on
`1440b84` + `5ec4213` + this document: **gate-validator FAIL** (0 BLOCKING, 1 MAJOR, 4 MEDIUM,
4 MINOR); **spec-auditor PROHIBITED DRIFT NONE** (0 BLOCKING, 2 MAJOR, 7 MEDIUM, 10 MINOR), with the
explicit conclusion **"does anything require a code-behaviour change? No."** §5.3 is what they found
and what was done about it.
**Delta truth-check:** a read-only pass over §5.3 and the rows round 2 had just written — the pass
unit 19.2 learned to run, after its own corrections proved false six times. It returned **13 false
sentences, one disqualifying**, and §5.4 is that account: the sentence this unit meant to close on was
false, and the repair was to revert a behaviour change rather than to reword it.
**THIS DOCUMENT CLOSES THE UNIT**, on the rule unit 19.2 adopted at its own round 5 and this unit
applies unchanged: a round whose findings need no code-behaviour change closes the unit, its
documentation and falsification corrections are made, and every falsification claim they touch is
**re-established by measurement on the closing tree** (§4) rather than by a further review round. §7
states what is owed after that; §5.4 states plainly what a strict reading of §18 would owe instead,
and what was given up to make the closing argument true rather than merely defensible.
**Live provider calls:** zero. Nothing in this unit needs one.

---

## 0. Reconciliation at entry — this unit inherited a dead turn's work

`git tag -l` showed `gate/phase-18e` + `product/multi-frontier-v2` as the latest, and LOOP_STATE
said `next_step: phase-19.3`. Those agree, so no reconciliation commit was owed for the tags. The
**tree** disagreed with the state: `HEAD` was `b3c343a`, a 19.3 work commit LOOP_STATE did not know
about (`last_commit: 74a8c6f`, iteration 121, which closed 19.2), and an untracked
`PHASE16A_SELFCHECK_phase-19.3_20260810T102802Z.json` sat beside it. So a prior turn implemented
19.3, committed it, ran a 16A pane-I/O regression, and died before any review or evidence.

Under D-LOOP-2 everything that turn had "in flight" is dead. This unit therefore re-ran every
falsification and every suite fresh and foreground, and treated `b3c343a` as CANDIDATE material to
be reviewed here rather than as work already blessed. The 16A receipt it left is a **regression**
receipt — it proves the refactored shell still boots and still takes operator keystrokes — and it is
**not** evidence about the U328 gate. Nothing in this unit relies on it; it is committed as what it
is, alongside this unit's own receipts.

## 1. What was asked, and what was done

Directive §18 unit 19.3 ordered:

> Gate `notifyNode` and `runConductorReadiness` on `classifyProviderScreen` returning null before
> any `writePanePrompt`, as `controlAssignTask` (`main.js:2458`) already does for assignment. […]
> Extend the mutation harness to the **system→pane** direction […]. Invariant 1 and D-P18-13 are the
> acceptance standard: the loop must be *unable* to answer a trust or permission modal, not merely
> unlikely to.

**Half of the ordered standard is met, and the review established which half.** The unit's standard
is invariant 1's "unable, not unlikely". What IS unable: reaching a pane's PTY from the system side
without being classified. What is NOT: the verdict itself — `classifyProviderScreen` is a denylist
of six phrase families, the gate-validator drove ten realistic permission screens past the shipped
module and **nine were allowed through**, and this document's first draft claimed otherwise. That
residual is **U363**, recorded rather than absorbed, and §3.1 says why this unit did not close it by
widening the patterns.

**The gate went one level below the two callers the order named.** A trust/permission/auth modal is
a numbered menu whose answer is one carriage return; gating two named call sites leaves a third to
forget. `apps/desktop/control/pane-writer.js` now owns every system→pane byte, and `main.js` holds
exactly **three** PTY write sites — the voice conductor-write binding (operator→pane, gated since
17C), the `pane:input` handler (the operator's own keystrokes, with the caveat below), and the
pane-writer io.

Two limits on that sentence, both put there by round 2 and neither cosmetic. **The wiring suite counts
spellings, not paths:** it matches a write on the `manager` identifier — `manager?.write(` included,
since the round-2 validator demonstrated a fourth site slipping past the previous pattern with every
suite green (M7 pins it now) — but a write reached through an alias is invisible to any regex over
this file and is *not* claimed to be caught. That residual is U366(a)/U369, and what stands behind it
is unit 19.9's extraction of `main.js` into requirable modules. **And "the operator's own keystrokes"
is an assumption `main.js` denies six lines above the write itself** (`main.js:1434`, the comment on
the write at `:1440`): xterm.js emits `onData` for terminal replies it generates by itself, so only
`before-input-event` is operator provenance. No exploit follows — the replies a child can elicit are CSI sequences, not a bare carriage return, and a numbered
menu needs the Enter — but the structural claim is bounded by it, and the spec-auditor was right that
stating the claim without its bound is exactly how this phase keeps going wrong.

Four properties, each of which is the answer to a specific way of getting this wrong:

1. **Every write is classified, the submit keys included.** The provider draws its permission prompt
   IN RESPONSE to the body just pasted. Checking once, before the body, leaves precisely the window
   the modal opens in — and the body is harmless noise while the Enter behind it is the answer.
   Codex's second (confirm) Enter is a keystroke like any other and is gated like any other.
2. **A pane whose screen cannot be read is refused, not assumed empty.** An empty screen classifies
   clean, so "no session" must not read as "nothing on the screen" (fail closed, Buildout §4).
3. **The pane's echo of our own body is excluded before the submit key is judged**, or a notice
   quoting a structured failure would withhold its own Enter forever. §3 is what that cost.
4. **A refusal is reported as the provider state it is.** `runConductorReadiness` and
   `waitForWorkerReadinessTurn` consult the refusal *before* they type, so a pane sitting on a setup
   screen is reported as `WORKSPACE_TRUST_REQUIRED`/`AUTH_REQUIRED`/… rather than as a delivery
   failure — and a withheld submit returns `residue_possible: true`, because the body is then in the
   provider's input box and "nothing happened" would be false.

The conductor pane is the priority case the order names: it is pane 1, the pane the operator
converses in (OP-8 §13), its readiness prompt is the first thing the shell sends after launch — the
exact moment a first-run trust modal is up — and before this it was written to blind.

## 2. The in-Electron receipt (D-P16-0), and why the inherited one did not count

D-P16-0 is per-track and binding: a shell change is exercised by an automated check **inside the
packaged Electron runtime on this host**. The headless suite drives the gate through injected
doubles; what no double can prove is the *wiring* — that main.js hands the receipt its production
write path and that the screen reader is reading a real ConPTY.

`apps/desktop/selfcheck/system-pane-write-selfcheck.js` (kind `system-pane-write`, launcher bound
300 s) drives the REAL bindings against REAL panes:

| Leg | What it measures |
|---|---|
| A1 `clean_pane_write` | a clean supervised pane: refusal `null`, production `writePanePrompt` true, and the body **observed executing** — the refactor still delivers body *and* submit key, not merely "stopped refusing" |
| A2 `modal_pane_refused` | the same pane driven to a trust-modal screen **through the operator's own input bridge**, so the classification is independent of the path it gates: refusal `WORKSPACE_TRUST_REQUIRED`, write `false`, and the withheld body **never observed on the screen**. That absence is the invariant-1 leg — a shell that reported a refusal while the bytes went out anyway passes everything else and fails this |
| B `own_echo_not_self_refusing` | a second fresh pane: a body containing modal-shaped text is still delivered |
| C `sessionless_pane_unreadable` | a pane id with no session is `PANE_SCREEN_UNREADABLE`, not clean |

Both panes are killed inside the check (D-LOOP-1); no model starts; `live_exchanges: 0`; no
credential is touched. The receipt carries the provenance every machine-emitted receipt in
`docs/evidence/receipts/` should (`check`, `unit`, `source.commit`, `tracked_product_tree_clean`,
`started`/`finished`, `electron_main_pid`) and is run-stamped, so no earlier receipt is overwritten.

**The check is itself falsifiable.** `apps/desktop/test/system-pane-write-selfcheck.test.js` drives
the real check function against a simulated runtime and requires it to go red for each of the four
defects it exists to catch — a gate that never refuses, a refusal reported while the bytes go out
anyway, a missing echo exclusion, and a sessionless pane read as clean — plus a leg proving nothing
is spawned when the wiring is absent, and one asserting the trust line it types is one
`classifyProviderScreen` really classifies (otherwise A2 could go green for the wrong reason).
That is a behavioural test of the evidence, not a string match on it.

## 3. What the runtime found that the tests could not (U360)

The first in-Electron run **FAILED**:
`PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_20260810T111123Z.json` — legs A1, A2 and C
green, leg B `written: false`, `body_observed_executing: false`.

The own-echo exclusion split the screen on the **exact** body string. The screen it searches is
`buffer.snapshot()` — the raw PTY stream — so PSReadLine's syntax colouring puts escape sequences
*inside* the echoed line and the terminal wraps it wherever the column runs out. There was no exact
substring to remove; the pane's echo of our own prompt classified the pane against us; the notice
withheld its own submit key. The module header had claimed only line-wrapping could do this and that
the direction was fail-closed. The direction **was** fail-closed — nothing answered a modal — but a
message that never arrives is still a defect, and the 15 headless tests and 15 mutations that
existed at that moment could not see it, because every one of them fed the gate a screen with no
escape sequences in it.

Repaired in `0f51e8c`: normalise with `plainScreen` (the classifier's own normaliser) first, then
match the body character by character with whitespace allowed between characters, covering a wrap
anywhere including mid-token. It removes strictly more than the exact match did — so any screen it
accepts, the old one accepted too — and only ever our own body, since the character sequence must
still be present in order. An unbuildable pattern falls back rather than throwing on the write path.
Two behavioural tests were added (a coloured, wrapped echo is excluded; a real modal beside it still
refuses; `withoutOwnEcho` removes our body and nothing else) and two mutations, one per half of the
repair — P10 (back to exact matching) and P11 (screen left un-normalised) — because either alone
restores the shipped defect. Recorded as **U360**, CLOSED by the receipt that found it.

The transferable finding, recorded in the register rather than left in a commit message: a guard
that reads a PTY screen must be falsified against **raw terminal bytes**, not hand-written strings.

### 3.1 Why this unit did not close U363 by widening the patterns

The obvious response to "nine of ten permission screens survive" is to add nine more patterns. This
unit did not, and the reason is a dependency rather than a preference.

The gate's signal is a **whole-buffer** read (U329): 256 KB of scrollback, and the pre-body check
excludes nothing from it. So text that trips a pattern stays in the signal until it is evicted — one
delivered body containing trigger words pins that pane into refusal for **every subsequent system
write**, not one. A task's `objective` and a debate's `proposition` reach those bodies verbatim, so a
model's own words can do it. Widening the denylist over that window trades an unanswered modal for a
permanently mute pane, and it would do so on the eve of the unit (19.4) whose entire job is to bound
the window with `RingBuffer.sliceFrom()` — which returns `null` for an unanswerable window rather
than guessing.

The order is therefore: **window first (19.4), then verdict** — and the verdict the repo already has
a shape for is `voice/pane-state.js`'s positive-evidence test, not a longer list of phrases. This is
the loop's engineering judgement, recorded as such in U363; the operator sees it at the Phase 19 gate
ledger. What the loop will not do is let a green sentence stand in for a criterion that is not met.

## 4. Evidence — real command output

Every command below was run in the foreground, in this turn, on this Windows host. **Lines marked DIGEST are a summary of a receipt JSON or of a long CAUGHT list, not literal stdout** (validator MEDIUM-1: a transcript block that mixes the two is the hygiene failure this phase keeps repeating). Everything unmarked is copied output.

```
$ node --test terminal/test/*.test.js
ℹ tests 216   ℹ pass 216   ℹ fail 0

$ npm test            # apps/desktop, on the closing tree (eada45c)
ℹ tests 873   ℹ pass 873   ℹ fail 0

$ node tools/mutation/system_pane_write_mutations.js        # closing tree (eada45c)
base apps/desktop/control/pane-writer.js SHA-256 15511BB832C4DEE1CF31CF6309173DE56AAD2E863F7A23DE7BA13978B1C0CB85
base apps/desktop/main.js SHA-256 148C29B6F77B98677A1C37E17678E66E46FC06434C166D6CF20B6817D9423513
CAUGHT P1..P17, M1..M7   (24 mutations)   [DIGEST of the per-mutation lines]
restored apps/desktop/control/pane-writer.js SHA-256 15511BB8… — BYTE-IDENTICAL   [DIGEST — two lines]
restored apps/desktop/main.js SHA-256 148C29B6… — BYTE-IDENTICAL
ALL 24 SYSTEM→PANE MUTATIONS CAUGHT

$ node tools/mutation/.grading_isolation_check.js   # scratch, deleted after: WHICH single test
                                                    # grades each mutation? (§5.3, §5.4)
P13  HALF-rendered -> RED   |   codex second Enter -> RED   |   echo-settle wait is BOUNDED -> green
P15  HALF-rendered -> RED   |   codex second Enter -> green |   echo-settle wait is BOUNDED -> green
M7   exactly three PTY write sites -> RED  |  conductor readiness ... refusal -> green  |  gate module -> green
restored pane-writer.js — BYTE-IDENTICAL
restored main.js — BYTE-IDENTICAL

$ node tools/mutation/pane_input_bypass_mutations.js
[DIGEST — 36 CAUGHT lines, then two literal lines:]
restored main.js SHA-256 148C29B6… — BYTE-IDENTICAL
ALL MUTATIONS CAUGHT

$ node tools/mutation/orchestration_mutations.js
[DIGEST — 5 CAUGHT lines, then:]
ALL 5 ORCHESTRATION MUTATIONS CAUGHT; every file restored BYTE-IDENTICALLY

$ node selfcheck/run.js system-pane-write --unit phase-19.3.close     # run 1, on 073f322
[selfcheck/run] shell exited code=1        → leg B FAILED (U360, §3)

$ node selfcheck/run.js system-pane-write --unit phase-19.3.close     # run 2, on 0f51e8c
[selfcheck/run] shell exited code=0
  [DIGEST of the receipt] ok true · commit 0f51e8c · tracked_product_tree_clean true
  clean_pane_write true · modal_pane_refused true (WORKSPACE_TRUST_REQUIRED)
  own_echo_not_self_refusing true · sessionless_pane_unreadable true

$ node selfcheck/run.js system-pane-write --unit phase-19.3.round1   # run 3, on 1440b84
[selfcheck/run] shell exited code=1        → leg B FAILED AGAIN (U364, §5.2 — the race)

$ node selfcheck/run.js system-pane-write --unit phase-19.3.round1   # run 4, on 5ec4213
[selfcheck/run] shell exited code=0
  [DIGEST of the receipt] ok true · commit 5ec4213 · tracked_product_tree_clean true
  clean_pane_write true · own_echo_not_self_refusing true · sessionless_pane_unreadable true
  modal_pane_refused true (WORKSPACE_TRUST_REQUIRED) · written false · body_observed false
    submits_before 3 → submits_after 3 · stray_submit_observed false · bridge_alive true
  sessions_killed_in_unit [pane-2, pane-3] · live_exchanges 0

$ node selfcheck/run.js system-pane-write --unit phase-19.3.round2   # run 7, on eada45c (closing)
[selfcheck/run] shell exited code=0
  [DIGEST of the receipt] ok true · commit eada45c · tracked_product_tree_clean true
  all four legs true · submits_before 3 → submits_after 3 · stray_submit_observed false
  bridge_alive_after_window true · sessions_killed_in_unit [pane-2, pane-3] · live_exchanges 0

$ tasklist /FI "IMAGENAME eq electron.exe"
INFO: No tasks are running which match the specified criteria.        (D-LOOP-1)
```

**Round 2 took the receipt three times and all three are committed with this document**, which is the
honest record rather than the tidy one:

| Receipt | Commit | Tree clean | Why it exists |
|---|---|---|---|
| `…round2_20260810T125304Z.json` | `89f6f2c` | **false** | taken before the round-2 work was committed — a real run of the same code, kept rather than deleted |
| `…round2_20260810T125417Z.json` | `fa35797` | true | the first closing candidate, superseded when §5.4's revert landed |
| `…round2_20260810T131740Z.json` | `eada45c` | true | **the receipt this unit closes on** |

A receipt directory that only ever contains the flattering runs is worth less than one that shows what
was actually run.

**The pins.** `pane-writer.js`'s baseline moved four times across this unit and the harness header
carries a narrative for each: the self-check branch and its two ctx bindings, the U360 repair, the
U364 wait with P13/P14, and the round-2 remediation with P15/P16/P17/M7. `main.js`'s moved three
times and **ends where round 1 left it** (`148C29B6…`) — §5.4's revert put it back, so the
`pane_input_bypass` and `orchestration` pins that had moved with it were reverted too, and neither
harness carries a round-2 change. Every time, each mutation was re-read against the new bytes before
the pin moved, then re-run. The pin is a claim, not bookkeeping (`orchestration_mutations` had been
exiting 3 unnoticed since 19.2 for exactly that reason; `b3c343a` repaired it).

Round 2 added the sharper version of the same discipline, and it is the one worth carrying forward: a
harness that prints CAUGHT tells you a suite went red, not that the test you meant graded it. So P13,
P15 and M7 were each run against candidate tests **one at a time** — which is how the round-2 finding
was confirmed, how the repair was verified, and how M7's own mis-grading was caught (§5.4).

**The Python suite was NOT run in this unit, and that is a deliberate, disclosed omission.** No commit
in the range `66189f4..HEAD` touches a `.py` file (verified over the whole range, not a subset of the
commits). The
Python that this unit's tooling does touch is exercised by `orchestration_mutations.js`, which
mutates `mcp_server/collaboration_service.py` and `control_plane/policy.py` and grades them with
their own pytest suites — all CAUGHT, restores byte-identical. The last full-suite figure remains
iteration 121's on `3fa401a`+`8ac5bf4` (2331 passed, 1 skipped, three-way split); the phase gate at
unit 19.10 owns the full-suite run and the pytest configuration that makes its skips visible (U339).

## 5. What the mandatory reviewers found

### 5.1 Round 1 — gate-validator **FAIL**, spec-auditor **PROHIBITED DRIFT NONE / 4 MAJOR**

Both ran foreground, in-turn, concurrently, on `0f51e8c`. They converged, independently, on the same
class this phase keeps producing: **documentation asserting absolutes the code falsifies** — and this
time one of those absolutes was inside a machine-emitted receipt, which outlives the prose around it.

**BLOCKING-1 (validator) / MAJOR-2 (auditor) — the "unable" standard is not met, and was claimed.**
The validator wrote its own probe against the shipped module and ran ten realistic permission screens
through it at two provider values: **nine survived at every value**, including "Do you want to
proceed? > 1. Yes 2. Yes, and do not ask again", a codex "Allow command? (y = yes, a = always,
n = no)", an elevation password prompt and a bare numbered menu. Only the workspace-trust wording
refused. It also named the asymmetry: `voice/pane-state.js` already gates the OPERATOR's own voice on
POSITIVE evidence ("absence is not consent"), so a system notice is currently held to a weaker
standard than the operator is. Disposition: **accepted in full.** The module header, the receipt's
`finding` field, the register row and this report now state the achieved property; the residual is
**U363** with the reason it is not closed here (§3.1). The unit's acceptance criterion is recorded
NOT MET on unrecognised screens and carried to the Phase 19 gate ledger per U358 — not absorbed.

**MAJOR-1 (auditor) — the safety argument for the U360 repair was backwards, in three places.**
"It removes strictly more … so a screen this accepts is one the exact version accepted too" is the
reverse of the truth: removing more text before classification accepts MORE screens, and leg B is
itself a screen the exact version refused. "What it may NOT do is remove text that is not our own
body" is enforced by nothing — removal is by pattern, not provenance. The auditor argued the widening
both ways and concluded the change should stand while its justification is rewritten. Disposition:
**accepted.** Rewritten in the module, the register and here; the unenforced half is now pinned by a
test showing that a body equal to a modal's own words erases them.

**MAJOR-3 (auditor) — the receipt never observed the byte the unit exists to withhold.** Leg A2
watched for the withheld BODY. A defect that withholds the body and still emits the bare carriage
return leaves no needle on a PowerShell pane and passed every leg — and the falsification test
inherited the same blind spot. It also noted the absence had no post-window positive control.
Disposition: **accepted.** The pane's prompt is now a unique token, submitted lines are counted, and
two new falsification tests cover exactly those two defects.

**MAJOR-2 (validator) — a demonstrated survivor.** Splicing `if (provider === null) return null` into
the gate left all 866 desktop tests green: every behavioural test ran with a known provider, while
`paneProviderResolver` answers null for any pane without governed chrome — the common case. (The
in-Electron A2 leg does discriminate it, which is why the validator graded it MAJOR rather than
BLOCKING.) Disposition: **accepted** — a provider-less pane is now gated explicitly by test, and
mutation **P12** keeps it that way.

**MAJOR-4 (auditor) — the cost of a false positive was understated.** "A false positive here
withholds one message and is retried by the next notification" is false: the PRE-BODY read excludes
nothing, so one delivered body containing trigger text pins that pane into refusal for every
subsequent system write, for the life of its 256 KB scrollback — and `debate.proposition` and a
task's objective reach those bodies verbatim. Disposition: **accepted**, corrected in the module and
the register; it is also the reason §3.1 gives for not widening the denylist before unit 19.4.

**MEDIUM/MINOR, dispositions in brief.** Silent fallback to the exact matcher when the regex cannot
be built → now logged (auditor MEDIUM-4). `writePrompt`'s "never conflated" docstring → corrected,
and the discard at three call sites recorded as **U365** (auditor MEDIUM-1/MEDIUM-2). A pane that
spawned and then failed to banner escaped teardown → fixed (MEDIUM-3). `notifyNode`'s no-pane branch
missing `residue_possible` → fixed (MINOR-5). §4's transcript block mixing literal output with
digests → the digest lines are labelled as digests (validator MEDIUM-1). U362 reframed (validator
MEDIUM-2). The substring write-site count, `PANE_SCREEN_UNREADABLE` sitting outside
`PROVIDER_STATES`, the `openai_codex_cli` literal in the shared write path, and the missing
falsification for "the operator path stays open" → recorded together as **U366**, not fixed here.

**What both reviewers confirmed, having tried to break it.** No ungated system→pane path remains —
the validator enumerated every PTY write site in the repo and classified each as operator-path or
system-path. The mutation harness is real: it re-ran it (17/17 then, 20/20 now) with byte-identical
restores. The D-P16-0 receipt is evidence about the gate rather than a boot regression, and is itself
falsifiable. The FAILING first receipt is the unit's strongest artifact and was preserved rather than
deleted. The fix preceded the passing run, so no fix-after-validation at that point. Scope and
prohibitions clean; no tag created or moved; register append-only; zero CR bytes. The auditor found
**PROHIBITED DRIFT NONE**, with the operator→pane path untouched and still ungated, as invariant 1
requires in that direction.

### 5.2 What the remediation itself then found — U364

The round-1 remediation's own in-Electron run **failed leg B again**, at `1440b84`, on a leg the
remediation does not touch and which had been green at `0f51e8c`. Two runs with opposite outcomes on
the same behaviour is a race, and it was one: the submit-key read can catch the pane mid-render, and
a FRAGMENT of our own body is not removable by a matcher for the whole of it. Fixed in `5ec4213`
with a bounded echo-settle wait, falsified in both directions (P13 deletes it, P14 unbounds it), and
recorded as **U364**. The receipt at `5ec4213` is green on all four legs, including the new
submit-key count. That is the second time in this unit that the runtime found what the headless
tests could not — the argument for D-P16-0, not a criticism of it.

### 5.3 Round 2 — and the finding that the falsification was itself unfalsified

Both reviewers ran foreground and in-turn on `1440b84` + `5ec4213` + this document. **Sequentially,
not concurrently**, which is a deviation from the round-1 method and from the note that ordered this
round: the gate-validator writes its own mutations into the working tree, the spec-auditor is
read-only over the same tree, and U359 records what a suite taken while another agent works the same
tree is worth. The validator ran first with the tree to itself and returned it byte-identical
(`git status --porcelain` empty, verified by it and again here); the auditor read the same bytes
afterwards. Foreground and in-turn are the binding constraints (D-LOOP-2); concurrency was a
wall-clock preference and it was the wrong one.

**Verdicts: gate-validator FAIL** — 0 BLOCKING, 1 MAJOR, 4 MEDIUM, 4 MINOR. **spec-auditor
PROHIBITED DRIFT NONE** — 0 BLOCKING, 2 MAJOR, 7 MEDIUM, 10 MINOR, concluding in its own words:
*"Does anything require a code-behaviour change? No. … The shipped product code is correct as it
stands, including the U364 loop, which I traced and found decision-safe in both directions."*

**MAJOR (both, found independently, traced identically) — the fixture that graded the U364 fix never
built its own scenario.** The half-rendered echo stopped at `yes, pro`, one character before
`classifyProviderScreen`'s `/yes,? proceed/i` matches, so the screen the test called half-rendered
was CLEAN. The test passed with the settle wait deleted; P13 was graded CAUGHT by an unrelated
read-index shift in the codex test; and `echoIsWhole → true`, which nullifies U364's fix exactly,
survived all 871 desktop tests and all 20 mutations. **This is round 1's MAJOR-2 class reproduced on
the remediation for it**, and it is the third unit in a row to produce it. Disposition: **accepted in
full**, and repaired where the defect was — in the fixture. It now ends at `yes, proceed NOD`, and it
asserts that its own fragment classifies, so it cannot quietly stop discriminating again. Verified per
mutation rather than inferred from a green harness (§4): P13 and P15 each turn the U364 test **alone**
RED, and P15 is caught by nothing else in the suite. Recorded as **U367**, with the transferable
lesson: a mutation is worth exactly what the fixture grading it is worth.

**MEDIUM ×2 (validator) — two fail-open directions nothing graded.** The pre-body `refusalOn(paneId,
null)` (passing the prompt there erases a modal our body's words match, *before* the first byte) and
fail-closed-on-unreadable at the **submit** key (pinned before the body, nowhere after it — the test
harness could not even flip `readable` between reads). Both **accepted**: two behavioural tests, a
harness that takes `readable` per read as `screen` already did, and mutations **P16** and **P17**.
Recorded as **U368**.

**MEDIUM (both) — the write-site counter matched one spelling.** `manager?.write(` adds a fourth PTY
write and keeps the count at three; what actually caught it was a SHA-256 baseline detector, which is
a change detector, not a guard. **Accepted**: the counter matches the identifier, **M7** pins it, and
the claim above it now states its own limit (§1). Recorded as **U369**; the aliased-write residual
stays U366(a) and is owned by unit 19.9.

**MAJOR (auditor) — a machine artifact outliving its prose.** The U328 closure row cites a receipt
whose `finding` field carries the absolute round 1 retracted. Receipts are immutable and were **not**
edited: the citation moves to the receipt at the closing commit and the two superseded ones are
recorded as carrying a retracted string (U370 item 4).

**The remaining MEDIUMs and MINORs** are corrections to this unit's own records plus one
observability repair, itemised as **U370**: the mutation count (17 → 24), the `pane:input` provenance
assumption (§1), the "pays nothing" comment now priced at what the validator measured, and
`echoIsWhole`'s silent fallback (fixed — a log argument, the unit's only product change at round 2).
Three items do **not** close there. The auditor's append-only MEDIUM turned out to be **false** and is
corrected rather than accepted (§5.4, U370(5)). Nothing times the settle loop, so §4 carries no
measurement of it — an evidence debt on the Phase 19 gate ledger (U358), not a defect. And the
`Number("x") → NaN → 0 ms` settle parse, which U364's wait had made load-bearing, was fixed and then
**deliberately reverted**: it is a behaviour change on the decision path, a round-2 remediation may not
carry one, and it is now **U371** — open, owned, and not smuggled (§5.4).

### 5.4 The delta truth-check, and the sentence it stopped this unit writing

Unit 19.2 ended by learning that a correction written to repair false prose can be false itself — its
round-5 fix was, in six places, caught only by a read-only pass over the correction. That pass was run
here on everything §5.3 and the U367–U371 rows had just asserted. **It returned 13 false sentences,
one of them disqualifying**, and it is the reason this document says what it now says.

**The disqualifying one was the sentence this unit closes on.** The draft read: *"the product decision
path is byte-identical to what they reviewed apart from a logger argument."* False. `fa35797` also
rewrote the two settle-interval constants to parse rather than coerce their env overrides, and
`PROVIDER_PASTE_SETTLE_MS` feeds `pasteSettleMs()` into `writePrompt`'s settle loop. Worse than
cosmetic: a malformed override deletes U364's wait, deleting that wait **is** mutation P13, and P13 is
graded CAUGHT precisely because it flips a write from delivered to withheld. So the repair could change
a write verdict in the one configuration it exists for — inside a remediation whose entire argument is
that no code-behaviour change was required. Two honest options: keep it and owe round 3, or revert it
and keep the argument true. **Reverted** in `eada45c`, carried as **U371** (real, unfixed, owned by a
unit that is already changing `main.js`), and the pins it moved returned to where round 1 left them.

**The second finding was a mutation grading itself.** M7 was anchored inside `writePanePrompt`, where
that function's own `doesNotMatch` guard catches it as well as the counter — U367's lesson unapplied to
the mutation written in response to U367, in the same commit. Re-anchored into `runConductorReadiness`,
and then all three were run one test at a time (§4): **M7 reds the write-site counter alone; P15 reds
the U364 test alone; P13 reds the U364 and codex tests.**

**The third was a hidden dependency stated as a property.** "A permanently-false `echoIsWhole` changes
only latency, never a verdict" holds *only* because the whole-buffer read (U329) is append-only, which
makes a refusal monotone inside the settle window — and unit 19.4 exists to remove that window. Stated
now, in the harness and in U367, as something 19.4 must re-derive rather than inherit.

**And one of the round-2 auditor's own MAJORs was false, which this document had already repeated as
fact.** It found that this unit broke the register's correction-by-new-text convention by editing rows
"in place at `1440b84`". Checked against git rather than believed: neither `0f51e8c` nor `1440b84`
touches the register at all, every row of this unit landed in one commit (`7cc2115`) at 181 insertions
and 0 deletions, and the self-referential sentences it read as evidence of rewriting are a draft
revised before its single commit — which that commit's own message states. The convention was not
broken. Corrected in U370(5). A reviewer's finding is evidence, not a verdict; this document repeated
one without checking, which is the same failure it exists to record.

The remaining nine were smaller and are all fixed here: the commit list (§0/§4 named five and six of
the eight in the range), two §4 lines presented as literal stdout that were paraphrases (now marked
DIGEST — validator MEDIUM-1's class, reintroduced in the paragraph written to fix it), "thirty lines
away" where the distance is six, "both are committed" of two then-untracked receipts, U370(4) not
naming the receipt it moved the citation to, U369's state (closed **in part**) reported as closed, and
a re-pin count the harness header did not carry.

**Why this closes the unit rather than buying round 3.** After the revert, what changed since the
reviewers read the tree is: (a) a test fixture, four mutations and a counter regex — the falsification
evidence itself, whose only honest re-establishment is *measurement*, and it was re-measured in full on
the closing tree including the per-mutation single-test runs the findings demanded; (b) **one** product
change, the fallback logger on `pane-writer.js`'s echo-completeness path, which writes a log line and
cannot reach a verdict; and (c) prose. Unit 19.2 adopted this stopping rule at its own round 5 after
four rounds of one class; this unit applies it at round 2 rather than paying the same tread again, and
pays for it with a delta pass instead. What the loop does **not** do is soften anything to get there:
the unmet half of the acceptance standard is still recorded as unmet (§7), U370(10) and U371 are open,
and every finding above is in the register whether it was fixed or not.

**What both reviewers confirmed at round 2, having tried to break it.** The product code is correct,
including the U364 loop, which the validator attacked for slow renders, hangs, spins, masked refusals
and green-for-the-wrong-reason, and the auditor traced through all four screen orderings. The
in-Electron receipt reads exactly as §4 digests it, and the failing predecessor at `1440b84` really
does carry the leg-B failure §5.2 describes. Prohibitions clean: canonical docs, both frozen schemas,
`tools/loop/run_loop.ps1` and `config/` untouched; `config/live_operation.json` untracked and unread;
`gate/phase-19` absent and `product/multi-frontier-v2` still `cd08878`; register append-only across
the range (181 insertions and 0 deletions at round 2's reading, and this document's companion rows add
only insertions to that); zero CR bytes; no `mcp_server/` change, so invariant 7 is untouched; the
operator→pane path still ungated, as invariant 1 requires in that direction.

## 6. Scope, prohibitions, substitutions

- **Prohibitions:** no push, no remote, no credential read/write, nothing outside the repo root,
  `docs/canonical/` and both frozen schemas untouched, `config/live_operation.json` not committed and
  not read.
- **Registers: append-only, and verified rather than asserted.** Thirteen rows added across the unit —
  U328's successor row and U360–U366 at round 1 (one commit, `7cc2115`, **181 insertions, 0
  deletions**), U367–U371 at round 2 — and no row deleted or rewritten anywhere in the range. The
  round-2 spec-auditor graded MEDIUM that the convention *had* been broken, reading the rows'
  self-referential sentences as evidence that `1440b84` edited committed rows in place. Checked
  against git: neither `1440b84` nor `0f51e8c` touches the register at all. Those sentences are a
  draft corrected before its single commit — the distinction the convention actually cares about.
  Corrected in U370(5); §5.4 says why this document had repeated the finding before checking it.
- **Substitutions:** none. Every criterion this unit owns was executable on this host.
- **Untouchable set (§18):** `tools/loop/run_loop.ps1` not modified; loop-state semantics unchanged;
  no gate tag created, moved or deleted; MCP authority untouched (this unit is Electron-side only).
- **CRLF hazard (U274):** every file written by tooling in this unit was verified to carry zero CR
  bytes before staging.
- **What was NOT done:** the whole-buffer screen read stays (U329, unit 19.4 narrows it — the gate
  consults `classifyProviderScreen`, and narrowing the window belongs with the finding that owns
  it); residue tracking is recorded as U361, not built; and no provider TUI was launched, so the
  classifier's patterns meet no real provider screen here (U362).

## 7. Commands, hashes, and what this unit does NOT claim

**Reproduce:**

```
node --test terminal/test/*.test.js
cd apps/desktop && npm test
node tools/mutation/system_pane_write_mutations.js
node tools/mutation/pane_input_bypass_mutations.js
node tools/mutation/orchestration_mutations.js
cd apps/desktop && node selfcheck/run.js system-pane-write --unit <your-label>
```

The self-check writes a **run-stamped** receipt, so an operator re-run cannot overwrite the one this
document cites (U322's lesson). To keep a re-run out of the evidence directory entirely, set
`SHELL_SELFCHECK_RECEIPT_DIR`.

**Hashes at close:** `pane-writer.js` `15511BB8…` (was `FC65D4C7…` before round 2), `main.js`
`148C29B6…` (**unchanged** by round 2, per §5.4's revert) — the mutation pins as of `eada45c`,
verified byte-identical after every harness run.

**This unit does NOT claim:**

- that the classifier is right about real provider screens (U362) — it claims the gate consults the
  classifier and honours its verdict;
- that a modal cannot be answered by the *operator's* keystrokes — it must be answerable by them;
  that is the whole point of invariant 1, and the operator→pane path is deliberately untouched;
- that the whole-buffer read is sound (U329) — and the earlier draft of this line was wrong about its
  cost: a false positive does not withhold one message, it pins that pane for the life of its
  scrollback, because the pre-body read excludes nothing;
- **that the acceptance standard is met.** It is met structurally and not in verdict: an unrecognised
  screen is still written into (U363), demonstrated by the round-1 gate-validator against this module,
  nine survivors out of ten screens — and re-demonstrated at round 2, nine of ten at four provider
  values, against the shipped module;
- that no ungated system→pane path *can* exist — only that none does, that the three that write are
  the three named, and that the wiring suite catches a fourth spelled on the `manager` identifier. An
  aliased write is not claimed to be caught (U369/U366(a));
- that anything was proven about live providers, budgets, or leases: zero live calls were made.

**WHAT IS OWED, and by whom.**

1. **Round 2 is done (§5.3, §5.4); the unit closes and unit 19.4 (U329) is next.** Of the rows it
   opened: **U367, U368 and U370 are CLOSED**; **U369 is CLOSED IN PART** (the counter now sees a
   `manager?.write(`; an aliased write is not claimed to be caught, residual on U366(a), owned by
   19.9); and two are **OPEN** — **U370(10)**, nothing times the settle loop, so its cost is bounded
   and argued but not measured, and **U371**, the settle-interval parse, reverted out of this unit on
   purpose and owned by a unit already changing `main.js`. Both go to the Phase 19 gate ledger (U358).
2. **U363** — the verdict half of the standard. Sequenced behind unit 19.4's bounded window, with
   the reason stated (§3.1) rather than the conclusion asserted. It goes to the Phase 19 gate ledger
   (U358) whether or not it is closed by then.
3. **U361, U365, U366** — residue tracking, the discarded provider state at three call sites, and
   the four small ones. None is fixed here; all are carried.
4. **The full Python suite and the pytest configuration** — unit 19.10's, per §4's disclosure.
