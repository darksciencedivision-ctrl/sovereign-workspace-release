# PHASE 18E `.live.electron` — CHECKPOINT EVIDENCE (no gate)

**Unit:** `phase-18e.live.electron` — directive §17.2(1)'s per-provider LIVE in-Electron acceptance
leg. The sub-step that runs it, after `.wiring` built the pane's node record for it.
**Status:** COMPLETE as a checkpoint. **`gate/phase-18e` does not exist and this unit did not create
it. `product/multi-frontier-v2` is not applied.** The typed live round trip — one prompt, one live
answer, per provider — is **NOT evidenced and is not claimed**, for a reason that is now measured,
named, and owned by the operator (**U317**).
**Authorization:** OP-12 / OP-12.2 (directive §17, §17.2). **Live model exchanges spent by this
unit: ZERO** — across three live in-Electron runs. Both providers stop before a prompt is drawn.
**Work commit:** `8ea6555`. **Receipt:** `docs/evidence/receipts/PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json`
(`source.commit: 8ea6555`, clean tracked product tree, `ok:false`).

---

## 1. Entry state and reconciliation

`git tag -l` at entry: latest gate tag `gate/phase-18d`, product tag `product/multi-frontier`.
`LOOP_STATE.json`: `next_step: phase-18e.live.electron`, iteration 116. **Tags and state agreed** —
no reconciliation commit owed.

`HEAD` was `697ea23`, a commit made **after** the iteration-116 state commit: a prior turn BUILT the
live-acceptance target (`op12-live-acceptance-selfcheck.js` + `-verdict.js`, 707 + 485 lines, tests
and 18 mutation rows) and its own message says *"the live run is the next act of this unit, against
this tree."* That turn then died. This unit is that next act. The working tree was clean at entry;
no half-finished edits were inherited, and no reviews were owed from the dead turn (it had run its
own on what it committed).

## 2. What this unit did

1. **Ran the leg, live, in Electron, on this Windows host** (`node selfcheck/run.js
   op12-live-acceptance`). First run: 2026-08-02T06:35Z.
2. **Found what stops it** — and it is not the product.
3. **Fixed what the receipt was allowed to SAY about it**, in the pure verdict module where
   `node --test` can falsify each rule (U296, the 18D lesson).
4. **Re-ran it twice more** (06:54Z, and the final 07:19Z run against the committed tree), the
   second re-run because the first re-run's own fail-closed credential rule caught a hole this
   unit had just introduced.

## 3. The finding (U317) — the pane was alive and waiting for a human

Everything §17.2(1) asks for **before** the typed prompt was measured and passed, for **both**
providers, on every run:

| Leg | `grok_build` | `google_antigravity` |
|---|---|---|
| governed picker spawn through `spawnFromSelection` (the operator's own click path) | ✅ | ✅ |
| exact provider + model verified off the spawned binary and the argv | ✅ `grok-4.5` | ✅ `gemini-3.6-flash-low` |
| supervised ConPTY pane, `RUNNING`, in the governed workspace | ✅ | ✅ |
| durable I-X3 terminal on its OWN allowance-1 resource, seen from a separate process | ✅ 1 → 0 | ✅ 1 → 0 |
| `node@1.1` record on the OPERATOR's durable log: SPAWNING → READY(pid) → TERMINATED + exit | ✅ | ✅ |
| §2.2 child-environment scrub (10 names dropped, PATH intact, no credential name) | ✅ | ✅ |
| pane painted and settled (not black — the 16A defect does not recur) | ✅ | ✅ |
| **ONE harmless prompt → ONE live answer** | **NOT RUN** | **NOT RUN** |

The typed round trip did not run because both CLIs sit on their **own first-run directory-trust
modal**:

* `grok`: *"Grok Build may run or modify contents in this directory, posing security risks.
  Yes, proceed y / No, quit n"*
* `agy`: *"Do you trust the contents of this project? Antigravity CLI requires permission to read,
  edit, and execute files here. > Yes, I trust this folder / No, exit"*

A modal consumes typed text and does not echo it. **The first receipt reported this as "the
keystrokes are not reaching the live session"** — a dead-terminal finding about a session that was
alive and waiting for a human, and precisely the failure-wearing-another's-clothes shape this build
has a standing rule about (17A; U310; the `.live.shape` unit's own closing warning). That misreport
is fixed. The gate is not, and cannot be, by this loop.

### 3.1 Why the loop did not press yes

Answering grants a frontier CLI directory-scoped authority to **read, edit and execute** in the
operator's workspace — agy's modal says so verbatim. That is a protected action:

* **invariant 1** — the app never self-authorizes a protected action;
* **OP-12 operator directive §11** — tool permission is subordinate to launch tickets, "no
  always-approve, no unsandboxed defaults", and *"a provider CLI's own 'always approve' setting is
  never operator approval"*;
* **OP-12's own authorization object** — it authorizes live **sessions** under the operator's
  subscriptions, a statement about subscription terms. Reading it as also delegating a
  filesystem-trust decision over the operator's own repository is an expansion the operator never
  wrote, and invariant 1 is the rule against the app performing that expansion for itself;
* **fail closed on ambiguity** (§4) settles the residual doubt the same way.

It is **not** a permission-mode problem: both panes already launch with the mode this build pins
(`--permission-mode plan` / `--mode plan`) and are asked anyway — directory trust is orthogonal to
the tool-permission mode. No **permitted** argv flag dismisses it; the two that might
(`--always-approve`, `--dangerously-skip-permissions`, both recorded in this repo's own 18A host
reconnaissance) are exactly what §11 forbids, and neither was tried.

Both mandatory reviewers were explicitly asked to attack this reading as possibly over-strict. Both
judged it correct — the gate-validator adding that the asymmetry settles it ("answering is an
unrecorded, irreversible grant; refusing costs the operator one keystroke and is fully recorded"),
the spec-auditor adding that answering **would have been** the invariant-1 violation.

### 3.2 What the operator does, once

```
grok                     # in this workspace → answer "Yes, proceed"
agy                      # in this workspace → answer "Yes, I trust this folder"
node apps/desktop/selfcheck/run.js op12-live-acceptance
```

The directive's live budget is untouched: this unit spent **zero** live exchanges, so the re-run
starts with the full one-prompt-one-answer-per-provider allowance.

## 4. What was built, and how each rule can go red

In `apps/desktop/selfcheck/op12-live-acceptance-verdict.js` (pure; `node --test` falsifiable):

* **`paneConsentGate(provider, text)`** — requires **ALL** of a provider's phrases and forbids the
  state a `none` phrase describes. One phrase would match a model that merely *said* "yes, proceed"
  (the same error pointing the other way); the `none` guard is why a CLI reporting *"Signing in…"*
  is not reported as waiting on the operator. Fixtures in the test are the **real captured pane
  text** from the live runs, cross-checked by the validator against the receipt's own excerpts.
* **`consentOutcomeIsHonest(leg)`** — a gated leg is never green, never reports an answer, always
  names the operator step, and is never typed into once the gate has been seen. A gate that rose
  **after** quiescence (which is what `agy` did on run 1) does not convict the check of a decision
  it could not have made.
* **The late-gate reclassification cannot bury a U310** (spec-audit M-6, fixed): the pane text is
  the whole xterm buffer, scrollback included, so stale trust text could have re-labelled a session
  that took the keystrokes and then said nothing as a consent skip. A modal does not echo what you
  type, so a late gate may only explain a leg whose prompt **never echoed**.

In the check: the gate is tested before a probe is drawn and again after an echo failure; the
receipt gains `providers_consent_gated`, `operator_steps`, `live_exchanges_spent`, `source_after`
and `repo_unchanged_by_the_run`; and `receipt.ok` carries an independent conjunct that no gated leg
can pass.

## 5. Reviews — both mandatory, both FOREGROUND and in-turn (D-LOOP-2), run concurrently

**They converged INDEPENDENTLY on the same MAJOR, and it was real.** The receipt's *static prose*
asserted, unconditionally, that *"a live model **ANSWERED** one arithmetic probe"* and that *"**TWO
live exchanges** in total"* had been spent — on a run that got no answer and spent zero — while a
sibling field in the same artifact said the opposite. This is the iteration-115 inversion recurring
one layer up: in prose instead of in a field. Every outcome sentence is now **computed from the
legs**, and `live_exchanges_spent` is counted from the legs that actually submitted rather than from
the plan.

Everything else each reviewer raised was fixed here with a test **and** a mutation row, or recorded:

| Finding | Disposition |
|---|---|
| validator claim 7 / auditor M-1,M-2,M-3 — prose claims an answer that did not happen | **FIXED** (computed) |
| auditor M-6 — a late gate could bury a U310 | **FIXED** (echo guard, M26) |
| auditor m-1 — a missing `authorized` key read as consent (fail-OPEN on the live switch) | **FIXED** (M27) |
| auditor m-11 — READY never checked to come FROM SPAWNING | **FIXED** (M28) |
| auditor M-5 — §17's repo-status line measured only before the live sessions | **FIXED** (`repo_unchanged_by_the_run`) |
| auditor M-4 — "the least-authority mode each CLI offers" reversed `grok_build.py`'s own recorded refusal to rank an unordered enum | **FIXED** (wording) |
| validator MINOR-1 — "no argv flag dismisses it" was an unverified empirical negative | **FIXED** ("no **permitted** flag", with the §11 citation that carries it) |
| validator MINOR-2 — fixture provenance cited an overwritten receipt | **FIXED** (re-pointed) |
| validator MINOR-3 — four-sink enumeration did not match `sinks_checked` | **FIXED** |
| auditor m-5 — "did NOT fail" contradicted the leg's own `ok:false` | **FIXED** |
| auditor m-10 — the operator step named the keystroke, not what consenting grants | **FIXED** |
| auditor m-2 / m-3+m-4 / validator MINOR-5 / MINOR-4+m-7,m-8,m-9 | **RECORDED**: U318 / U319 / U320 / U321 |
| validator MINOR-6 — receipt emitted against a dirty tree | **FIXED** by re-running after the work commit: final receipt reads `source.commit: 8ea6555`, `tracked_product_tree_clean: true` |

**A defect this unit found in itself, before the reviewers.** The second run's credential scan
**failed closed**: a consent-gated leg threw before the line that captures its PTY transcript, so
one of §17's four sink classes was left unread — and `noCredentialMaterial` correctly refuses an
unread sink rather than passing it. The transcript is captured at teardown on every path now. The
check's own fail-closed rule caught a hole the same unit had introduced, which is the rule working.

## 6. Verification (this host, real output)

| Check | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | **2208 passed, 1 skipped** |
| `apps/desktop` → `npm test` | **813 pass, 0 fail** |
| `terminal/test` → `node --test *.test.js` | **216 pass, 0 fail** |
| `py -3.12 tools/mutation/_op18e_live_acceptance_mutations.py` | **28/28 RED, byte-identical restores** |
| `py -3.12 tools/manifest/compute_manifest.py --check` | **freeze check OK: no drift in FROZEN set** |
| Live in-Electron runs | **3** (06:35Z, 06:54Z, 07:19Z) — all `ok:false`, all honest |

**Final receipt, machine-checked negatives:** `sessions_before === sessions_after === 0`;
`lease_zero.ok`; `real_ledger_leases_empty: true`; `node_log_chain.ok` over 47 rows (39 → 47: four
per pane per provider); `credential_scan.ok` over 4 sinks with 5 sentinels; `owed_named.ok`;
`repo_unchanged_by_the_run.ok`; `live_exchanges_spent: 0`.

**D-LOOP-1:** every run measured lease 1 → 0 per provider, `leases: []` on the durable ledger, and
the validator's independent `tasklist` sweep for `grok|agy|electron|sovereign` found **no** surviving
process. Nothing this unit started outlived it.

## 7. What is NOT done, and is not claimed

* **The live typed round trip, for either provider.** Blocked on U317, the operator's one-time
  consent. `providers_live` is empty and every outcome sentence in the receipt says so.
* **`gate/phase-18e` and `product/multi-frontier-v2`** — neither exists; this is a checkpoint.
* **`.close`** — the whole-track reviews, `PHASE18E_EVIDENCE_REPORT.md`, the Phase-18 addendum
  supplement, and the tags remain the next unit's work.
* **U318–U321** — recorded, not fixed: the hash chain is verified as a linked list rather than
  recomputed; the observed spawn is bound to a pane by binary path alone; the self-check module's
  own orchestration has no falsifiable coverage; and four presentation residuals.
* **U310** stands untested on the interactive channel: grok's headless `-p` exits zero saying
  nothing, and whether an interactive pane shares that defect **cannot be known until the consent
  gate is cleared**. This unit did not learn anything about it and does not pretend to have.

---

*Checkpoint written 2026-08-02 at `phase-18e.live.electron`. Work commit `8ea6555`; this evidence
commit carries it. No gate closed, no tag applied.*
