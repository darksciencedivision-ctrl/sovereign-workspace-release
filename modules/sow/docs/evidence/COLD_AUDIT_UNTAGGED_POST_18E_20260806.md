# COLD AUDIT — THE SEVEN UNTAGGED POST-18E COMMITS

**Repo:** `D:\multi model terminal app\sovereign-orchestration-workspace`
**Range audited:** `b68a22e..b109f02` — 7 commits, 59 files, +3,771 / −245
**HEAD at audit:** `b109f0287bdcbad628a8a9db9adc4576cdb42a38`
**Audit date:** 2026-08-06
**Operator ruling this executes:** Path C, then Path A (2026-08-06)
**Method:** four independent cold readers, each given a single lens and no shared context, followed by
direct re-verification of every finding ranked BLOCKING or above by the orchestrating session.

> **Status of this document.** It is an audit finding, not an authority. Nothing in the repository was
> modified, and no commit, tag, or register row was written. Every recommendation below is subject to
> operator acceptance.

---

## 1. OBJECTIVES

Determine whether the seven untagged commits are fit to be gated, and settle — on evidence rather than
theory — whether the proposed shared-JSON orchestration refactor should proceed.

## 2. SCOPE

In scope: the diff `b68a22e..b109f02`, the two receipts it added, the test and mutation coverage of the
code it added, and its compliance with the project's recorded invariants and operator rulings.

Out of scope: everything gated at or before `gate/phase-18e`; the provider-account blockers themselves;
the shared-JSON directive's own internal design (addressed only where this audit's evidence bears on it).

## 3. WHAT WAS VERIFIED, AND HOW

Directly re-verified by the orchestrating session, by reading the named lines on disk: the dead policy
delegation, the permission-mode carve-out, the conductor vendor pin, the unguarded pane writer, the
store-writer split, the full text of the provider classifier, the absence of any emitter for the new
receipt schemas, and the receipt's own provenance fields.

Independently executed: `node --test apps/desktop/test/*.test.js` → **836 tests, 808 passed, 28 skipped,
0 failed**. `node --test terminal/test/*.test.js` → **216 passed, 0 skipped, 0 failed**.

Not executed, and stated plainly: the Python suite. This session reaches the repo through a Linux bridge
VM with no network access, Python 3.10, and no `pytest` installed; the repo targets `py -3.12` on
Windows. Running it there would prove nothing about the Windows host. **The Python suite remains
unverified by this audit** and must be run by the operator.

---

## 4. THE FOUR BLOCKING FINDINGS

All four share one root: this range moved decision-making authority into places eighteen phases of work
had deliberately kept it out of. Each is a fact read on disk, with the line quoted.

### B1 — Authorization logic moved into `mcp_server/`, and the delegation hook was wired then left dead

`mcp_server/collaboration_service.py:44-46` accepts a `SovereignPolicy`:

```python
def __init__(self, store: SovereignStore, policy: SovereignPolicy) -> None:
    self._store = store
    self._policy = policy
```

**FACT:** `grep -n "_policy" mcp_server/collaboration_service.py` returns exactly one line — line 46, the
assignment. There is no read anywhere in the file. In its place, twelve role and permission decisions are
made inline (lines 53, 83, 98, 113, 132, 141, 201, 228, 259, 276, 282, 290), for example
`if identity.role not in ("conductor", "operator"): raise CollaborationError(...)`.

**FACT:** the sibling module in the same package does it correctly. `mcp_server/memory_service.py` calls
`self._policy.authorize_*` on nine separate write paths, and its header states the contract: *"every write
path asks the policy first (I-M2 delegation)."*

**FACT:** `control_plane/policy.py` already exposes `authorize_debate` (line 140). `open_debate` performs
its own role check instead of calling it.

This is invariant 7 — *"MCP is access, not authority — no authorization logic inside `mcp_server/`"* — and
it is violated. **Failure scenario:** the operator changes debate-closing authority in
`control_plane/policy.py`. Memory operations honour it; every task, message, debate, candidate and
synthesis operation does not, because a second divergent copy of the rules now lives in the one package
the invariant names. Authority has forked.

### B2 — A provider's own auto-approval mode was enabled by cutting a hole in the guard that forbids it

`adapters/frontier/provider_cli_common.py:245` declares `FORBIDDEN_PERMISSION_MODES` including
`"acceptedits"` and `"accept-edits"`, with the refusal text *"never auto-approved (operator directive
§11, fail closed)."* This range added an exception to that guard at lines 310-312:

```python
antigravity_execution = (execution_profile == "google_antigravity" and name == "mode"
                         and value == "accept-edits")
if name in _MODE_FLAG_NAMES and value in FORBIDDEN_PERMISSION_MODES and not antigravity_execution:
    raise ValueError(...)
```

and used it: `adapters/frontier/antigravity.py:72` — `ANTIGRAVITY_HEADLESS_MODE = "accept-edits"`, changed
from `"plan"`. The receipt records it went live: `"gemini": { "execution_mode": "accept-edits" }`.

The comment that recorded *why* the narrower value was pinned — *"pinned so a node-controlled config
cannot supply the permissive one instead (§11)"* — was deleted and replaced with an unverified assertion
about the third-party CLI's own native settings. Invariant 29 (*"never trust the harness"*) forbids
exactly that basis.

**This directly reverses `D-P18-13` / `U317`**, recorded four days before this range and twice defended
against reviewers asked to attack it as over-strict: *"a provider CLI's own always-approve setting is
never operator approval."* No register row records the reversal.

**Failure scenario:** an Antigravity worker is assigned a task in the operator's worktree and proposes a
file edit. Under `--mode plan` that surfaced for a decision. Under this range `agy` applies it. No
approval-drawer item is created; no operator sees it.

A parallel widening moved Grok from `--permission-mode plan` to `default`
(`adapters/frontier/grok_build.py:90`), deleting a comment that recorded the previous iteration's explicit
refusal to make that exact change on the grounds that the hypothesis behind it had been refuted. Grok's
`default` is its ask-first mode, so the security delta is smaller; the erased reasoning is the finding.

### B3 — Unattended Enter-keystroke injection into live provider panes, unguarded on three of five paths

`apps/desktop/main.js:2476-2497` — `writePanePrompt` writes a prompt, waits, writes `"\r"`, and for Codex
waits again and writes a second `"\r"`. `notifyNode` (lines 2499-2508) calls it with no guard beyond
"is the pane running":

```js
async function notifyNode(nodeId, prompt) {
  if (nodeId === conductorLaunch.nodeId && conductorLaunch.state === "running") {
    return { ..., written: await writePanePrompt(conductorPaneId, prompt) };
  }
  const rec = workerRecordFor({ node_id: nodeId });
  return rec ? { ..., written: await writePanePrompt(rec.paneId, prompt) } : ...;
}
```

`controlAssignTask` does check readiness (`main.js:2458`). `runConductorReadiness` does not classify the
conductor pane's screen at all before writing to it. `notifyNode` — reached from `controlNotifyMessage`,
`controlNotifyDebate`, `controlNotifyDebateTurn`, and both deadline/stall notifications — does not either.

**Failure scenario, using the project's own recorded modal text:** `U317` records that `grok` and `agy`
raise a directory-trust modal whose affirmative option is *"Yes, proceed"* / *"Do you trust the contents of
this project?"*, and that answering it grants read/edit/execute over the workspace. If a pane is showing
that modal — a mid-session re-prompt, a new directory, a CLI upgrade that re-asks — when a peer message
arrives, the injected `\r` selects the highlighted default. The loop has answered the modal invariant 1
forbids it to answer. For a Codex pane the second `\r` confirms it.

The existing mutation harness `tools/mutation/pane_input_bypass_mutations.js` guards the operator→pane
direction. Nothing guards the system→pane direction this range created.

### B4 — Live provider state is decided by keyword-matching the terminal scrollback

`apps/desktop/control/provider-readiness.js:17-46` is six regexes over scraped screen text. Every state the
acceptance run reported — `AUTH_REQUIRED`, `WORKSPACE_TRUST_REQUIRED`, `MCP_PERMISSION_REQUIRED`,
`USAGE_LIMIT`, `AWAITING_PROVIDER_SETUP` — is produced this way, on a **still-running** process where no
exit code exists to consult, from `paneScreen()` which returns the whole retained ring buffer
(`main.js:2225-2228`), and it is checked *before* the MCP connection check (`main.js:2287` precedes `2295`).

The project's own rule, at `tools/providers/frontier_provider_recon.py:44-49`:

> *"**Exit-code-first classification.** A process that exits 0 is a SUCCESS, full stop. Its transcript is
> never re-read for the words 'login', 'quota', or 'rate limit' to demote it. This is the Codex-period
> lesson made binding for every provider: keyword matching on a successful transcript once turned working
> providers into phantom auth failures."*

**Three concrete failure modes.** *Sticky state:* Grok's startup promo overlay matches line 41; once
dismissed and fully functional, the text is still in the ring buffer, so every subsequent readiness pass
returns `PROVIDER_SETUP_REQUIRED` and never reaches the connection check. There is no transition out
except a fresh pane. *Self-inflicted false positive:* Sovereign writes the operator's objective into the
pane verbatim (`main.js:2440`), so an objective reading *"investigate why we keep hitting the usage limit
on Grok"* trips line 33 against Sovereign's own echoed text and marks a healthy worker `USAGE_LIMIT`.
Line 37 (`/\bplan\b[^\n]{0,80}\bgemini\b/i`) fires on *"plan the Gemini migration."* *Instrument
disagreement, already on the record:* the receipt states the headless exit-code-first probe **passed**
while the scraper said `AUTH_REQUIRED`, and adopts the scraper's verdict — the phantom auth failure,
reproduced.

`apps/desktop/test/provider-readiness.test.js` asserts the positive case. There is no negative control
asserting that a healthy worker whose transcript merely *mentions* a usage limit stays READY.

---

## 5. MAJOR FINDINGS

**M1 — The conductor is hard-pinned to one vendor and one model, in the range whose lead commit claims the
opposite.** `apps/desktop/main.js:2344-2348` fails readiness unless
`provider_id === "openai_codex_cli" && model_id === "gpt-5.6-sol"`. Commit `3587cbd` is titled *"generalize
provider-agnostic conductor selection"* and the selection layer genuinely was generalized; the Electron
readiness layer then re-pins it. Meanwhile `control_plane/conductor/registry.py:154-162` defaults to
`claude_code`/`fable-5` whenever `config/live_operation.json` is absent — and that file is gitignored. Any
clone without the operator's local config spawns the default conductor and then fails readiness permanently
with a message that reads like a config error. This also makes conductor succession onto a different
backend — a Phase 15D exit criterion — unreachable.

**M2 — Lost updates: three of five orchestration writers bypass the transactional path built alongside
them.** `persistence/store.py:332` provides `mutate_operational_task` with `BEGIN IMMEDIATE`, mutator,
`UPDATE`, `COMMIT`, and a docstring naming the exact hazard: *"Gemini and Grok publish candidates
concurrently. A Python-process-local lock cannot stop one candidate from overwriting the other."* Only
`record_candidate` (line 255) and `record_synthesis` (line 270) use it. `create_task` (70), `update_task`
(90), `open_debate` (163), `post_debate_turn` (186) and `close_debate` (223) all do an unprotected
read-modify-write through `put_operational_task` / `put_operational_debate`, which rewrite the whole JSON
blob. The `threading.Lock` guarding them is process-local, and each node runs its own MCP process, so it
guards nothing across nodes. Concurrent `post_debate_turn` calls silently discard one turn and then
`close_debate` refuses forever, because it requires a turn from every participant.

**M3 — The synthesis debate gate is bypassable by omission.** `mcp_server/sovereign_tools.py:249-253`
iterates `debate_ids` and rejects any that is not `CLOSED`, but `_string_list` accepts `[]` without error
and nothing cross-checks against `list_debates(task_id)`. Passing `debate_ids: []` completes the task with
the debate still `OPEN` — defeating the stated purpose of commit `02639d4`.

**M4 — Synthesis is structurally vendor-bound.** `sovereign_tools.py` requires non-empty
`gemini_contribution` and `grok_contribution` on every `publish_synthesis`. A task run by any other worker
pair cannot be closed. This sits awkwardly beside the range's provider-agnostic framing and against the
"dispatch by capability descriptor, never by model name" principle.

**M5 — The control server's shutdown is the one unbounded await in the quit path.**
`apps/desktop/control/sovereign-control-server.js:109-118` awaits `server.close()` with no timeout and no
`closeAllConnections()`. Every other teardown step is bounded at 15 s. `main.js` calls
`event.preventDefault()` before this chain, so an MCP client holding a request open (client timeout 180 s)
can leave Electron never exiting and never logging why.

**M6 — `connectionState` is a latch, not a liveness check.** `_lastSeen` is set on every request and
cleared only on PTY exit, with no staleness window. A worker whose Python MCP subprocess dies while the PTY
survives reports `connected` forever, and `controlAssignTask` checks no MCP freshness — so the conductor
assigns work to a node that cannot make a single tool call.

**M7 — The inspector converts read failures into healthy-looking empty state.**
`apps/desktop/inspector/operational-source.js:60-69` returns a fully-shaped success object with all counts
zero on any error, and `main.js:1726-1735` returns top-level `ok: true` regardless. A locked database
renders as "0 tasks, 0 messages, 0 debates" — a read failure indistinguishable from a clean idle system.

**M8 — No gate, no evidence report, no register row.** `git tag --contains` is empty for all seven commits.
`git diff b68a22e b109f02 -- docs/registers/` is empty. No `PHASE*_EVIDENCE_REPORT.md` was added. Two
recorded decisions were reversed in code (B2, and the vendor pin in M1) with nothing written down, which is
precisely why nothing flagged the reversal.

---

## 6. THE EVIDENCE LAYER

**FACT:** the schema strings `final_three_node_orchestration_acceptance@1.0` and
`final_talk_worker_spawn_acceptance@1.0` appear nowhere in the repository except inside the two receipt
files themselves. A bounded grep across `apps/`, `tools/`, `mcp_server/`, `persistence/`, `control_plane/`,
`node_runtime/`, and `adapters/` returns no producer. The fields `mcp_connection_evidence` and
`worker_spawn_result` have no emitter. `apps/desktop/selfcheck/run.js` was not touched by this range and
has no orchestration, collaboration, MCP, debate, candidate, or synthesis check kind.

**FACT:** both receipts carry the identical `recorded_at_utc` of `2026-08-03T13:59:09.3815283Z` — to the
100-nanosecond tick — despite documenting two different exercises, one of which records
`"live_microphone_utterance_completed": false`. Machine-emitted receipts in the same directory (e.g.
`PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json`) carry `check`, `source.commit`,
`tracked_product_tree_clean`, `started`/`finished`, and a PID. The two new ones carry none of these.

**INFERENCE (high confidence):** these are hand-authored operator testimony, not machine measurement. That
is not in itself dishonest — and the content is markedly candid, recording `PARTIAL_ACCEPTANCE`,
`requirement_mock_legs_equals_zero: false`, `external_windows.requirement_equals_zero: false`, and
`full_python: "timed out … not counted as passed"`. The defect is that they sit in
`docs/evidence/receipts/` alongside 36 machine-emitted receipts with nothing distinguishing measured from
asserted, and the project's own rule requiring an in-runtime self-check receipt for shell changes is unmet
for every change in this range.

**Three specific fields assert more than any code path observes.** `process_supervised: true` traces to a
literal written on the spawn success branch, not a re-observation of the process tree. Six readiness
booleans — including `provider_authenticated`, `workspace_accepted`, `identity_validated`,
`permission_resolved` — are set by literal assignment at `main.js:2310-2313` behind a gate that tests
exactly one thing. `workspace_accepted` and `permission_resolved` represent the operator's own trust-modal
answers.

**One receipt claim is genuinely instrument-backed, and deserves saying so.** The conductor's `SUM=117` is
producible by real code: `apps/desktop/conductor/roundtrip-probe.js:40-48` draws two random integers in
[21,99] and forms `SUM=${a+b}`; 117 is inside the reachable range. `runConductorReadiness` requires both a
real tool-call count delta and an observed answer before declaring READY. The conductor leg is the one
part of the acceptance that rests on measurement.

**Provenance gap.** The receipt records `starting_head: a6dd83f` and
`tested_worktree: "uncommitted final-hardening changes over starting_head"`, with no tree hash and no file
list. `a6dd83f..b109f02` is 27 files, +1,195 / −147 — including `main.js` +457, the whole of
`provider-readiness.js`, all of `mutate_operational_task`, and the `publish_candidate` /
`publish_synthesis` authorization gates. **None of that code has runtime evidence of any kind, and what
*was* tested is unrecoverable.** The classifier whose verdicts the receipt reports was written after the
run it reports on.

---

## 7. TEST COVERAGE — MEASURED

Executed by this audit on the Linux bridge:

| Suite | Result |
|---|---|
| `apps/desktop/test/*.test.js` | 836 tests — **808 passed, 28 skipped, 0 failed** |
| `terminal/test/*.test.js` | 216 tests — **216 passed, 0 skipped, 0 failed** |
| Python (`tests/`, 1,772 test functions) | **not run** — no `py -3.12`, no `pytest`, no network on the bridge |

The terminal figure matches the receipt exactly. The desktop figure reconciles with the receipt's "836
passed" — on the Windows host `py -3.12` is present, so the 28 presumably ran there. **The receipt's
numbers are not contradicted.**

What the run does demonstrate is that **every one of the 28 real-subprocess tests, across 17 files, is
gated on `spawnSync("py", ["-3.12", "--version"]).status === 0` and skips silently**, and the suite still
reports zero failures. A green desktop suite cannot distinguish "all live coverage ran" from "none of it
did." That includes `sovereign-mcp-stdio.test.js` and `operational-source.test.js` — this range's only two
tests that touch a real process.

Coverage gaps identified by the coverage reader (reported as its findings; I verified the headline claims
by grep, not function by function):

- **`apps/desktop/main.js` +846 lines has no executed coverage.** The module cannot be `require`d under
  `node --test` because it imports `electron`. 26 of 39 new functions appear in no test file at all; the
  other 13 appear only inside `fs.readFileSync(main.js)` string matches — e.g.
  `assert.match(body, /spawnFromSelection\(/)`. Those tests cannot distinguish working code from a syntax
  error, and they pass on a file where the function is unreachable.
- **`mcp_server/sovereign_tools.py` (405 lines) is tested only against a two-line echo fake.** All twelve
  tool handlers, both new authorization gates, and every validator are unexercised. No `tools/call` is
  issued end to end anywhere in the range.
- **Zero concurrency coverage.** No test in the repository touches `operational_tasks`,
  `operational_messages`, or `operational_debates` from more than one thread or process.
  `mutate_operational_task` — the range's only concurrency-safety mechanism — has neither a unit test nor
  any runtime evidence.
- **Mutation O1 in `tools/mutation/orchestration_mutations.js` is circular:** it mutates a source line in
  `main.js` and grades the mutation with a test that greps that same source line. O2–O5 are genuine
  falsifications against real HTTP and real SQLite. The harness's "ALL 5 CAUGHT" banner overstates by
  exactly the module with the least coverage.
- **No committed pytest configuration exists** (no `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`;
  both `conftest.py` files are `sys.path` anchors). The 600 s ceiling is imposed by the operator's
  invocation, and `"focused_python: 363 passed"` names a subset with no committed definition — not
  reproducible by a reviewer.

---

## 8. WHAT WAS CHECKED AND FOUND INTACT

These are results, not omissions, and each was verified by command rather than assumption.

`config/live_operation.json` is not tracked; only the `.example.json` is. `docs/canonical/` and `schemas/`
were untouched by the range — the frozen `node.schema.json` @1.0 is unmodified. No file under `docs/` was
modified or deleted; the two receipts are pure additions, so append-only holds (the problem is that nothing
was appended to the registers, not that anything was rewritten). No credential value appears anywhere in
the range; the four new config files carry commands, args, and environment-variable *names* only. The
credential env-scrub list was not weakened — a rename to a provider-agnostic wrapper, no deletions. Every
other permission-bypass argv flag remains refused. No remote, push, or publication anywhere.

On the engineering side: `mutate_operational_task` itself is correct — `BEGIN IMMEDIATE`, identity
re-verification of the mutator's return, `ROLLBACK` on every exception path, `busy_timeout` set before WAL
negotiation. All SQL in the range is parameterised; no string-concatenated SQL was found. The control
server's auth is well built — `crypto.randomBytes(32)`, frozen identity copies, method+path allowlist,
1 MiB body cap enforced during streaming, loopback-only bind, credentials cleared on stop; only its
`stop()` is defective. `worker-spawn.js` releases node control on all three failure paths. The access
control inside `collaboration_service.py` is consistently *applied* — the defect is where it lives (B1),
not that it is missing. `tests/unit/test_mcp_collaboration.py` uses a real SQLite database with no mocks
and is the range's one piece of genuinely load-bearing coverage. `apps/desktop/test/worker-spawn.test.js`
is the best test file in the repository — 36 behavioural tests with recording fakes, several documenting
the defect they pin *and* why an earlier draft could not see it, and an honest declaration of its own
limits. No `TODO`, `FIXME`, `NotImplementedError`, or stub marker was found in the added product code.

**On the central honesty question:** nothing in this range claims the full three-node collaboration leg
executed. The receipt's `collaboration` block is null in every field with
`reason_not_executed: "the strict no-assignment-until-READY gate correctly held both workers at 0 READY."`
That gate is real code (`main.js:2458-2460`), and the mock-dispatch admission
(`startup_mock_dispatch_legs_logged: 2`, U58 owed) is accurate. **The project's stated position that no
collaboration leg has ever run end to end is confirmed.**

---

## 9. CONTRADICTIONS ON THE RECORD

1. Commit `3587cbd` says the conductor selection is provider-agnostic; `main.js:2344` fails readiness for
   every provider but one (M1).
2. `D-P18-13` / `U317` say a provider CLI's own always-approve setting is never operator approval;
   `antigravity.py:72` enables that CLI's accept-edits mode (B2).
3. `frontier_provider_recon.py:44-49` bans keyword classification of provider state;
   `provider-readiness.js:17-46` classifies provider state by keyword (B4).
4. `store.py:332`'s docstring says concurrent writers require the transactional path; five of seven writers
   do not use it (M2).
5. The headless exit-code-first probe passed for Gemini; the screen scraper said `AUTH_REQUIRED`; the
   receipt records both and adopts the scraper (B4).

## 10. RISKS

The highest-consequence risk is B2+B3 together: a live frontier CLI running in accept-edits mode inside the
operator's worktree, reachable by an unattended writer that can press Enter on a modal. Either alone is a
governance defect; together they are the specific outcome eighteen phases of invariant work were built to
prevent. The highest-likelihood risk is B4, which will misclassify healthy providers as blocked and has
arguably already done so once. M2 is latent — it cannot fire until a collaboration leg actually runs, which
is also why it will fire on the *first* successful three-node run rather than being caught before it.

## 11. MISSING INFORMATION

The Python suite result at HEAD, including whether the 600 s timeout is a hang or genuine slowness and
which tests are responsible. Whether Codex's `default_tools_approval_mode = "approve"` in `.codex/config.toml`
means *require* approval or *auto-approve* — no test or doc in the repo pins the semantics. Whether a
ConPTY kill without an OS job object reliably reaps the `py -3.12 -m mcp_server.sovereign_tools`
grandchild on Windows (U25 is already recorded as owed). And what the "uncommitted final-hardening
changes" in the acceptance worktree actually were — that is permanently unrecoverable.

---

## 12. RECOMMENDATION

**Do not tag this range.** It is not a rejection of the work — the engineering underneath is real, the
gating added by `02639d4` is substantive, the conductor readiness probe is properly instrumented, and the
range does not overclaim its results. But four blocking findings move authority into places the invariants
reserve, two of them reverse decisions recorded and twice-defended days earlier, and none of it was
written down.

Suggested sequence, for operator ruling:

1. **B2 is yours alone.** Whether Antigravity may run in accept-edits mode is a protected-action
   authorization that reverses `D-P18-13`. Either rule it and record the ruling, or revert
   `antigravity.py:72` to `"plan"` and close the guard carve-out. No one else can decide this.
2. **Remediate B1, B3, B4 and M2** — these are mechanical, not architectural. B1: route the twelve inline
   checks through `control_plane/policy.py` as `memory_service.py` already does. B3: gate `notifyNode` and
   `runConductorReadiness` on `classifyProviderScreen` returning null, as `controlAssignTask` already does.
   B4: consult exit codes and structured provider signals first, bound the screen window using the existing
   fail-closed `RingBuffer.sliceFrom()`, and add the negative-control test. M2: route the remaining five
   writers through `mutate_operational_task` and an equivalent for debates.
3. **Write the register rows** — for the two reversals, for the four blocking findings, and for the
   provider blockers and the Python timeout, which currently live only inside a JSON receipt.
4. **Relabel or regenerate the two receipts** so measured evidence and operator testimony are
   distinguishable in `docs/evidence/receipts/`.
5. **Then re-run acceptance against a committed HEAD** — not an uncommitted worktree — so the result is
   reproducible.

**On the shared-JSON refactor, the evidence now points one way.** The premise that a SQLite orchestration
store exists is correct. But the store is not the defect: `mutate_operational_task` is one of the
best-built things in this range, and the actual bug is that five of seven writers bypass it. Replacing that
store with whole-document JSON rewrites under an exclusive lock would take the one place with correct
transactional semantics and remove it, while making the `messages[]` and debate-turn contention worse — the
same four concurrent writers, now serialised on a whole-file lock with revision conflicts and retries. And
it would do so before a single collaboration leg has ever executed, so there is still no observed behaviour
to simplify *toward*.

The cheaper move that addresses the real complaint — that a model should be able to hold the orchestration
state in one tool call — is a read-side projection: keep the transactional store, and have
`emit_operational_state.py` (which already exists and already emits a versioned document) serve the
single-document view. That is additive, reversible, and does not touch the write path.

*Audit ends. Verify everything.*
