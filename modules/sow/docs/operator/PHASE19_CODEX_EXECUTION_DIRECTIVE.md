# PHASE 19 — EXECUTION DIRECTIVE FOR CODEX

**Repository:** `D:\multi model terminal app\sovereign-orchestration-workspace`
**Written:** 2026-08-14 · by the validator session, for operator Sam
**Entry HEAD:** `1774c8add3e8279a642d44d1812e78417b8e99b7`
**Entry loop state:** `status: RUNNING` · `iteration: 135` · `next_step: phase-19.8`
**Your scope:** units **19.8, 19.9, 19.10** — the last three. Then the Phase 19 gate.

> **Rule zero: the disk outranks this document.** Every fact below was verified against the
> repository on 2026-08-14. If the disk disagrees, the disk is right and this file is stale.
> Verify before you assert. That discipline is the culture of this project and you are being
> graded against it.

---

## 0. HOW YOU ARE RUN — READ THIS FIRST

You are **not** driven by `tools/loop/run_loop.ps1`. That runner declares
`[ValidateSet("claude")] [string]$Builder = "claude"` and cannot invoke you. You run as your own
agent session in this repository, executing this document.

**Because you are not under `claude -p`, the PRINT-MODE FACT (D-LOOP-2) does not bind you.** Your
process does not end with your turn. You may run long test suites and review passes across turns.
That is a real advantage and you should use it.

**What still binds you is the checkpoint discipline.** Work in units. Each unit ends with commits
on disk and `docs/loop/LOOP_STATE.json` updated. A unit that dies mid-flight leaves CANDIDATE
material only — under this project's recovery-provenance rule, any receipt produced by a run that
did not commit must be **re-run fresh**, never adopted. Do not batch three units into one heroic
push.

### 0.1 A prerequisite only the operator can satisfy

Decision **D-LOOP-2** records that the loop runner is Claude-only and that the Codex builder branch
was deliberately removed (**U159**). Reintroducing a Codex builder path requires an explicit
operator ruling. Sam has directed this work verbally; **your first act is to check
`docs/registers/DECISION_REGISTER.md` for a row authorizing Codex as builder (expected id
OP-13.2).** If no such row exists, append one recording that the operator directed it on
2026-08-14, and say so in your first report. Do not proceed silently past a missing authorization —
silently reversing a recorded decision is the exact defect this whole phase exists to remediate.

### 0.2 `AGENTS.md` in this repo is NOT addressed to you

You will read `AGENTS.md` by convention. **It is not builder policy.** It is the operating policy
for provider *worker nodes* running inside the Sovereign Electron application — "use the connected
`sovereign` MCP server", "never create provider workers through `Start-Process`", "publish progress
through MCP". None of that applies to you building the product. Do not connect to the Sovereign MCP
server. Do not launch the application. Ignore `AGENTS.md` for the duration of this work.

---

## 1. AUTHORITY

Sam (Samuel Lawson) is the operator and the final authority on objectives, scope, promotions,
protected actions, and acceptance. You propose; he decides. Record his rulings in
`docs/registers/DECISION_REGISTER.md` before acting on them, never after.

---

## 2. ABSOLUTE PROHIBITIONS — none of these is waived

1. **No `git push`, no remotes, no PRs, no publication.** Ever. This repository is local-only.
2. **No credentials.** Never create, read, store, print, or transmit an API key, token, or secret.
   The adapters invoke the host's already-authenticated CLIs; that is the whole design.
3. **No purchases, sign-ups, or paid services.**
4. **Nothing modified or deleted outside the repository root.** `docs/canonical/` is frozen and is
   never edited. `schemas/node.schema.json` @1.0 is frozen; the successor `@1.1` is the amendment path.
5. **Registers and evidence are append-only.** Never delete or rewrite a line in
   `docs/registers/*.md` or `docs/evidence/**`. Never rewrite git history. Never amend a commit whose
   hash is recorded anywhere.
6. **`config/live_operation.json` is the operator's fail-closed switch** — gitignored, never
   committed. Only `config/live_operation.example.json` is tracked.
7. **No TTS / spoken answers.** Frozen invariant I-V2 / D-VOICE-02. It requires an explicit
   operator reversal that does not exist.
8. **Never self-authorize a protected action.** You do not answer a provider CLI's trust or
   permission modal. Doing so grants a frontier CLI read/edit/execute authority over the operator's
   workspace, which is his to grant (D-P18-13, U317).
9. **MCP is access, not authority** — no authorization logic inside `mcp_server/`. Unit 19.2 just
   spent an entire unit restoring this. Do not undo it.
10. **Do not launch the Electron app casually, and never while a loop run is in progress.** The
    self-check runner is the supported way to exercise the runtime.

---

## 3. CURRENT STATE — VERIFIED 2026-08-14

```
HEAD            1774c8add3e8279a642d44d1812e78417b8e99b7
loop state      status RUNNING · iteration 135 · last_commit 2ee1c5a · next_step phase-19.8
tags            50 — NO gate/phase-19 tag exists yet
register        newest row U440
```

Units 19.1–19.7 are **closed**, and these were confirmed in the code, not in the notes:

| Unit | Owed | Verified state on disk |
|---|---|---|
| 19.1 | OP-13 revert | `adapters/frontier/antigravity.py:78` = `"plan"`; `antigravity_execution` carve-out removed from `provider_cli_common.py` |
| 19.2 | U326 policy delegation | `mcp_server/collaboration_service.py` makes 20 `self._policy.*` calls (previously 0) |
| 19.3 | U328 system→pane write gate | evidence at `docs/evidence/PHASE19_UNIT3_U328_SYSTEM_PANE_WRITE_GATE.md` |
| 19.4 | U329 readiness signal order | classifier bounded by `RingBuffer.sliceFrom()`; `snapshot()` retired from that path (see `main.js:2296-2298`) |
| 19.5 | U330/U332 write path + debate gate | closed after four reviewer rounds |
| 19.6 | U331/U333 provider-agnostic runtime | conductor vendor pin deleted; historical note at `main.js:2401` |
| 19.7 | U334/U335/U336 runtime honesty | closed after four gate-validator and three spec-audit rounds |

**Re-verify this yourself before starting.** Read the head of `docs/loop/LOOP_STATE.json`, the tag
list, and the newest rows of both registers. If tags and state disagree, **tags are truth** —
reconcile state to tags first and commit that reconciliation as its own act.

---

## 4. YOUR THREE UNITS

The authoritative text is `AUTONOMOUS_BUILD_DIRECTIVE.md` §18, rows 19.8, 19.9 and 19.10. Read it.
What follows is the same work with the carried findings attached.

### UNIT 19.8 — U337: evidence that says what it is

The two files `docs/evidence/receipts/FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json` and
`FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json` declare schemas that **no code in this repository
produces**. They sit beside 36 machine-emitted receipts with nothing distinguishing measured from
asserted. Deliverables:

1. Add an in-runtime self-check kind to `apps/desktop/selfcheck/run.js` covering the
   orchestration/collaboration path. Its receipt must carry the provenance fields every
   machine-emitted receipt in that directory already carries: `check`, `source.commit`,
   `tracked_product_tree_clean`, `started`/`finished`, and the Electron main PID. Use
   `docs/evidence/receipts/PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json` as the shape reference.
   **D-P16-0 is currently unmet for every change in the audited range** — headless tests alone once
   shipped a runtime that failed at first launch, which is why this rule exists.
2. Stop deriving `process_supervised` and the six readiness booleans (historically
   `main.js:2310-2313`) from literal assignment. Each must trace to an observed signal or be
   **absent**. An absent field is honest; a fabricated `true` is not.
3. **Carried into this unit from 19.7's close:** `U437(e)` — `worker-readiness.js:614` sets
   `mcp_connected` to a literal `true`, and it is now reachable for a stale session. It is one of
   U337's booleans and it belongs here.
4. Then either regenerate the two `FINAL_*.json` receipts from a real emitter, **or** relabel them
   so operator testimony is distinguishable from measurement. **Neither file may be deleted or
   rewritten in place** — evidence is append-only. A sibling note or a superseding emitted receipt
   is the path.

### UNIT 19.9 — U338: coverage that can fail

`apps/desktop/main.js` cannot be `require`d under `node --test` because it imports `electron`, so
its orchestration additions are "covered" only by `fs.readFileSync(main.js)` string matches that
cannot distinguish working code from a syntax error. Deliverables:

1. Extract the orchestration logic from `main.js` into `require`-able modules, the way
   `apps/desktop/control/` and `apps/desktop/picker/` already are. **Check what 19.2, 19.4 and 19.7
   already extracted before you plan this** — the surface may be materially smaller than the audit
   described, and re-extracting something already moved wastes a unit.
2. Give `mcp_server/sovereign_tools.py` real coverage: at least one end-to-end `tools/call` per
   handler, and direct tests of the `publish_candidate` / `publish_synthesis` authorization gates.
   Today it is tested against a two-line echo fake, and **no `tools/call` is issued end to end
   anywhere in the repository.**
3. Replace mutation **O1** in `tools/mutation/orchestration_mutations.js`. It mutates a `main.js`
   source line and grades that mutation with a test that greps the same line — it is circular and
   proves nothing. O2–O5 are genuine falsifications against real HTTP and real SQLite; leave them.
   When you re-pin any harness baseline, **state what changed and why in the pin comment** — that
   file already carries seven such notes and the convention is load-bearing.
4. Make silent skips visible. 28 desktop tests gate on
   `spawnSync("py", ["-3.12", "--version"]).status === 0` and skip silently, so a green suite cannot
   distinguish "all live coverage ran" from "none of it did". Independently measured on a host
   without `py -3.12`: **836 tests → 808 passed, 28 skipped, 0 failed.** Surface the skip count in a
   way a run summary shows.

### UNIT 19.10 — U339: the suite, and the gate

1. Commit a pytest configuration. There is **no `pytest.ini`, `pyproject.toml`, `setup.cfg` or
   `tox.ini`** in this repository, and both `conftest.py` files are `sys.path` anchors only. The
   600-second ceiling is imposed by the operator's invocation, and `"focused_python: 363 passed"`
   names a subset with no committed definition. Make the ceiling, the markers and the subset
   inspectable in the repo.
2. Diagnose the full-suite timeout on the host: `py -3.12 -m pytest tests/ -q --durations=20` first;
   if it hangs rather than crawls, `--timeout=120 --timeout-method=thread` to name the stuck test.
   Installing `pytest-timeout` is a package install — **ask the operator before installing
   anything.**
3. Close the gate: evidence report, **two independent cold review passes** (see §6), tag
   `gate/phase-19`, and apply a **successor** product tag. **`product/multi-frontier-v2` is never
   moved** — existing tags are never moved in this project, ever.

---

## 5. CARRIED OPEN ITEMS

These are OPEN in `docs/registers/UNRESOLVED_ISSUE_REGISTER.md` and were opened by the units ahead
of you. Read each row in full before deciding its disposition. You are not required to close all of
them, but you **are** required to state, for each, whether it closes in Phase 19 or is re-recorded
with an owner and a reason.

- **U432** — what the two reviewers found across seven rounds in 19.7, and what remains
- **U434** — a node cannot be VERIFIED on demand, only provoked
- **U435** — `voice/turn-authority.js:687` is a second unbounded await on the quit path (same class
  as U334, which 19.7 just closed; this one is still open)
- **U436** — refusing an assignment is costless for the worker and not for the project
- **U437** — the round-3 residuals; **item (e) belongs to unit 19.8**, the rest need dispositions
- **U438** — a `tests/unit` test that fails under concurrent host load
- **U439** — a mutation harness cannot tell an assertion failure from a setup failure

---

## 6. WORKING DISCIPLINE — you are graded on this as much as on the code

**Two-commit convention.** Work commit first, then an evidence/register commit that carries the
work commit's hash in its body. Gate tags are applied on the second commit. Never amend.

**Evidence report per unit**, under `docs/evidence/`, following the existing naming:
`PHASE19_UNIT8_...md`, `PHASE19_UNIT9_...md`, `PHASE19_UNIT10_...md`. Look at
`PHASE19_UNIT3_U328_SYSTEM_PANE_WRITE_GATE.md` for the expected depth. Every exit criterion is
self-checked with **real command output pasted in**, not asserted.

**Two independent cold review passes before any gate tag.** The Claude loop used `gate-validator`
and `spec-auditor` subagents. You must produce the equivalent: two reviews by agents that did not
write the code, one checking exit criteria and evidence integrity, one checking prohibited drift
against the invariants in §2 and `CLAUDE.md`. Run them to completion and record their verdicts
verbatim in the evidence report — including verdicts that go against you. **A FAIL verdict stops
the tag.** For calibration: 19.7 needed four validator rounds and three audit rounds, and both
reviewers repeatedly found real defects. That is the system working. Budget for it.

**`docs/loop/LOOP_STATE.json` is yours to maintain.** Continue the iteration count from 135.
Update `next_step` and `last_commit` at every unit boundary and append a note describing what you
did, what you verified, and what you left owed. It currently says `RUNNING`; if you finish Phase 19,
set it per directive §8 — and if you stop for any other reason, leave it accurately describing where
you actually are. **Do not leave it saying RUNNING when nothing is running.**

**Register rows are append-only prose**, matching the existing style:
`### U441 - **OPEN: <title>**` followed by paragraphs of what, why it matters, owner, and
`State: **OPEN**.`

---

## 7. HOST AND FILE HAZARDS

**CRLF (U274).** `.gitattributes` pins LF. Windows PowerShell 5.1's `Set-Content -Encoding UTF8`
writes a BOM and converts every line ending to CRLF, which leaves `git status` clean while the bytes
differ and silently breaks hash pins and mutation harnesses. Use
`[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))`. After
any scripted edit, check `git diff --numstat` — if a small edit reports the whole file changed, you
have translated line endings.

**Stale `.git` locks.** If git reports `Unable to create '.git/index.lock': File exists` with no git
process running, the lock is stale; remove it. There are also leftover `tmp_obj_*` files and
`*.stale-20260806` renames in `.git/` from an earlier session — harmless, safe to delete.

**Exit-code-first classification** is binding for every provider
(`tools/providers/frontier_provider_recon.py:44-49`). A process that exits 0 is a success, full
stop; its transcript is never re-read for "login" or "usage limit" to demote it. Unit 19.4 exists
because that rule was violated. Do not reintroduce keyword classification anywhere.

**Tear down every child process inside the unit that spawned it (D-LOOP-1).** No orphans, no
lingering leases.

**A fix applied after validation voids the falsifications that validation rested on.** Either
re-validate, or split the unit. This project has enforced that three separate times.

---

## 8. STOP AND ASK THE OPERATOR

Do not decide these yourself. Stop, write down the options and your recommendation, and wait.

- Any package install, dependency addition, or tool the repo does not already vendor.
- Any change to `tools/loop/run_loop.ps1` — the runner has never been modified by build work.
- Any reversal of a recorded decision, or anything touching `docs/canonical/` or the frozen schema.
- Any protected action: a provider trust modal, a permission prompt, a live provider login.
- Any live provider run. Gemini is `AUTH_REQUIRED` and Grok is `USAGE_LIMIT`; both unblocks are the
  operator's accounts and his keystrokes, and they are **Path A, which comes after Phase 19**.
- A reviewer returning FAIL that you believe is wrong. Argue it in writing; do not overrule it.

---

## 9. DEFINITION OF DONE FOR PHASE 19

Units 19.8, 19.9 and 19.10 complete. Every carried row in §5 either closed with evidence or
re-recorded with an owner and an honest reason. Both cold reviews passed. Desktop, terminal and
**full Python** suites all reported with their skip counts visible. An evidence report per unit. Tag
`gate/phase-19` applied, plus a successor product tag with no existing tag moved. `LOOP_STATE.json`
accurate. Then, and only then, Phase 19 closes and Path A — the provider unblocks and the three-node
live acceptance, per `docs/operator/PATH_A_PROVIDER_UNBLOCK_SHEET.md` — becomes the next work, run
against a **committed** HEAD so its result is reproducible.

**What you must not do is declare completion you cannot evidence.** The audit that created this
phase found four blocking findings in seven commits whose author overclaimed nothing but recorded
nothing either. The failure mode here is not lying; it is finishing quietly. Write down what you
owe.

*Directive ends. Verify everything.*
