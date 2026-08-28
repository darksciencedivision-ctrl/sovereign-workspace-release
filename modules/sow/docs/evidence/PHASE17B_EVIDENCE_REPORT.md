# PHASE 17B — EVIDENCE REPORT (whole-track close)

**Work unit:** `phase-17b.close` (sub-step 4 of 4 — **`.ticket` → `.spawn` → `.legs` → `.close`**;
this unit closes the whole Phase-17B track).
**Date:** 2026-07-26 · **Iteration:** 82 · **Status:** PASS (mandatory independent `gate-validator`
confirmation obtained, foreground, this turn, plus an independent `spec-auditor` over the composition).
**Tag:** `gate/phase-17b` lands with this unit.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§16 track 17B** (OP-11), **§11/§14 (OP-6 /
OP-9 — the live-session authorization and its scope)**, loop protocol §3, substitution §6, honesty
§10.4, **D-P16-0** (every shell/UI change exercised by an in-Electron self-check writing a
machine-readable receipt), **D-LOOP-1** (live sessions spawned in a unit are torn down within it),
**D-LOOP-2** (print-mode: every suite and review run foreground, in-turn).
Load-bearing invariants: **1** (the operator holds final authority — the app never self-authorizes),
**2** (every terminal a Sovereign node — no naked/raw CLI session), **3** (the conductor/model is a
runtime selection, surfaced honestly), **4** (workers interchangeable behind adapter contracts),
**7** (no authorization logic inside `mcp_server/`), **10** (workers publish CANDIDATE, never
self-canonize), **11** (provenance on every shared entry), **19/21/I-X3** (locality per node; one
subscription terminal counted, allowance 2), **22** (local concurrency hardware-bounded; VRAM
residency scheduled and visible), **27** (the orchestra is visible), **29** (containment at the
OS/process layer), **30** (minimal necessary control).

---

## 1. What the track delivered, and what `.close` does

**Operator finding F3's second and third clauses — "a picker selection records + badges but launches
nothing (U70)" and "dispatch legs mock (U58)" — are closed as far as machine evidence can close them.**
Selecting a model on a worker pane now launches that live worker under the full governance chain, and
a live `claude_code` worker publishes a CANDIDATE that the real gate engine accepts and the conductor
synthesizes.

| Sub-step | Iter | Work | Evidence | What it shipped |
|---|---|---|---|---|
| `.ticket` | 75 | `e4d2911` | `8e0f773` | `tools/live/emit_worker_launch.py` (`worker_launch_ticket@1.0`) + `node_runtime/supervisor/worker_pane_spawn.authorize_worker_pane`: a picker selection obtains a **governed, executable, interactive launch authorization** — or a fail-closed refusal — for both localities, through the same gate chain the conductor pane runs, with the counting fact that matches the locality (durable I-X3 lease for frontier; a `ResidencyPlanner` decision for local). No session spawned. |
| `.ticket-revalidate` ×3 | 76–78 | `879292a`, `aacb065`, `d51cabb` | `f9d2771`, `576577c`, `d3bcb1c` | Three owed independent passes. Round 1 **FAILED**: the VRAM budget was still derivable from the resident set (every local pane refused on a 24 GB card with 8 GB free), and the fix for it crashed the whole picker. Fixed: the budget is a constant fixed **before** residency is read; a budget the host's own residency falsifies yields no planner + `established:false` + a reason; a seeding fault degrades the list instead of raising; `None` (no view) is distinct from `{}` and renders UNKNOWN; every refusal carries a machine-readable gate id; the binary allowlist survived ~30 wrapper/rename/UNC/ADS attack forms. |
| `.spawn` | 79 | `0b58e84` | `534b2e9` | `apps/desktop/picker/worker-spawn.js` — the **only** place the shell executes a launch ticket: admission before the ask, pane occupancy, session key chosen before the ask, authorization-only spawn under the Python-minted node id, the §2.2 scrub with a leftover ABORT, terminal handback on every failure path, release on exit/kill/quit. `spawnFromSelection` **launches** instead of recording. Closes **U70**'s spawn half and **U105** (a real fail-open: Windows `os.environ` upper-cases keys, Node does not, so a mixed-case credential var reached the child). |
| `.spawn-revalidate` | 80 | `aa9fb14` | `c8a45ce` | The owed pass. Both reviews independently found the same MAJOR that `.spawn` introduced: a death **without** teardown (SIGKILL, crash, power loss) left `{node_state:"running", governed:true}` on disk, and after restart the first new pane took that id and came up badged `live` for a process that died with the last shell. Fixed at the **fold** (`_sanitizeRestoredChrome`), the fact kept as a derived `interrupted_from`. Also extracted three main-process fixes to `picker/pane-wiring.js` so they are testable at all — eight headless mutations plus two in-Electron mutation runs, every one RED. |
| `.legs` | 81 | `12fc2e9` | `b3f513f` | `LiveGovernedFlow` accepts injected `WorkerHandle`s so the **same** governed loop runs the deterministic pool or a real supervisor-spawned vendor terminal with no branch (inv 4); a live handle is minted only from `spawn_claude_code_terminal`; a worker leg is **derived** from that node's own evidence row and `_assert_legs_honest` refuses a contradicting label in **both** directions. Three real defects found by live runs failing: `ModelWorkerAdapter` never returned `structured`; **U60's root cause** (the MCP server reaps a 60 s-idle handler under a multi-minute live call — prior "transient flakiness" diagnosis WITHDRAWN); and `claude -p` blocking on inherited stdin (150 s vs 3.5 s, measured). Closes **U58**'s worker half. |
| `.close` | **82** | *this unit* | *this report* | **No product code.** Re-ran both in-Electron receipts and all three suites fresh in the foreground; obtained the mandatory independent `gate-validator` over the whole track (which re-ran everything again itself, five falsifications included); ran `spec-auditor` over the **composition** — what the three sub-steps become together, which no per-sub-step audit could see; re-ran the `conductor-dispatch` check `.legs` had edited but not exercised; corrected two factual errors the validator found in this report; registered every remaining finding; tagged. |

## 2. Exit criteria (directive §16 row 17B) — self-check with real command output

All commands run on this Windows host, foreground, this turn (Electron 31.7.7 / Node 20.18.0 /
Chrome 126.0.6478.234 / win32-x64).

| # | Criterion (§16 17B) | Verdict | Evidence |
|---|---|---|---|
| 1 | A picker selection on a worker pane performs the **GOVERNED live spawn** | **PASS** | `PHASE17B_SPAWN_SELFCHECK.json` `ok:true`: `local_launched:true` (`ollama.EXE run qwen3:8b`, pane-2), `frontier_launched:true` (`claude.EXE --model claude-fable-5`, pane-4), both `session_state:"RUNNING"`, pid alive, bytes reaching the renderer (`*_pane_output_seen:true`) |
| 2 | …**supervisor** — no naked session (inv 2) | **PASS** | `supervision_ready:true`; the launcher requests no ticket at all while supervision is not READY; `SessionManager.spawn` refuses without an admitted node id; the node id is **Python-minted** (`local_node_id:"worker-pane-2"`, `frontier_node_id:"worker-pane-4"`); ConPTY bound to the governed workspace on both legs, matched to that pane's own binary at the node-pty boundary before its cwd/env is read as evidence |
| 3 | …**I-X3 governor** — subscription accounting | **PASS** | `frontier_lease_id` durable, `frontier_lease_session_keyed:true`, `frontier_lease_visible_cross_process:true`, `frontier_lease_in_use:1`, `frontier_lease_released_on_exit:true`, `frontier_in_use_after_exit:0`. The local leg takes **no** subscription terminal (`local_subscription_governed:false`) — locality is per node (inv 19) |
| 4 | **Refusals surfaced with reasons**, each naming its own gate | **PASS** | In-runtime: a fabricated option refused by `host_enumeration` with no session and chrome `launch_refused`; an occupied pane refused without disturbing the running session's process, record, held terminal or chrome; a selection targeting the CONDUCTOR pane refused by id (not by CSS). `.ticket`'s nine-refusal test reads the gate ids off the tickets rather than asserting a list |
| 5 | Frontier **per OP-6 scope only** (`claude_code` / `codex`) | **PASS** | The frontier branch runs the same live chain as 17A (`live_operation_authorized`, `operator_terms_confirmed`, `cli_present`, `ix3_counted`); the binary allowlist refuses any executable outside the scoped set, including wrapper/rename/UNC/ADS disguises, and refuses shell metacharacters in argv or executable |
| 6 | Local via the host runtime with **residency honesty** (U63/U64 narrowed as far as real evidence allows) | **PASS (bounded — see §6)** | The VRAM budget is a constant fixed **before** residency is read, never derived from the resident set; a budget the host's own snapshot falsifies produces no planner, `established:false` and a reason naming the contradiction; the local gate refuses on `established is not True` as well as on a missing planner; "no view" (`None`) renders UNKNOWN rather than "not loaded"; picker greying and the real gate are pinned to **agree** in both directions by a test that drives three host states through both. The pinned budget is a substitution, disclosed in the receipt (`local_budget_pinned_mb`, U96) |
| 7 | Conductor dispatch drives **≥1 LIVE worker publishing CANDIDATE over MCP → real gates → conductor synthesis** | **PASS** | `docs/evidence/live/PHASE17B_LEGS_DISPATCH_FEED.json`: `legs.workers:"live"`, `worker_legs {"worker:worker-claude-live":"live"}`, evidence row `executed/spent/verified` true with the CLI-reported checkpoint dated to a call spent in that run, `stage_pass 1/1`, `acceptance_verdict:"PASS"`, `accepted_count:1`, `live_workers_owed.owed:false` **derived** from the packet's own evidence. Reproduced three times (254 s / 318 s / 277 s) |
| 8 | Leg labels remain **unfakeable** (`_assert_legs_honest`) | **PASS (stated limit)** | A `live` claim with no verification record is unrepresentable, and an under-claim that would hide real spend is refused too. The guarantee is **caller-scoped** (U43/U119): instrumentation on a caller-supplied handle constrains its class, not its behaviour. Stated, not overstated |
| 9 | **Minimal live exchanges** | **PASS** | One subtask routes to the single live node ⇒ one exchange per dispatch run. Smoke-scale is guaranteed by **construction**, not by a token ceiling — **U116** records that honestly |
| 10 | **D-LOOP-1 in checks** | **PASS** | `.spawn` receipt **measures** it: `sessions_killed:true`, `surviving_pids:[]`, `frontier_in_use_after_exit:0`, `real_ledger_unchanged:true`, `scratch_ledger_removed:true`. The `.ticket` receipt spawns no session and carries the fields that apply to it — `terminals_released:true`, `in_use_after_release:0` (**validator M-4**: an earlier draft of this row claimed all three keys for "every receipt"; the `.ticket` receipt does not carry them, legitimately). `.legs` reports `torn_down:true`. The REAL durable ledger `.sovereign_store/leases/terminal_leases.json` is **empty, with every lease it took handed back** — it is **not** untouched: the `.legs` live run acquires and releases a durable lease **by design** (U111's fix), and its `updated: 2026-07-26T19:19:27.241072+00:00` stamp *is* that release, 25 ms after the packet `ts` (**validator M-5**; "untouched" is true only of the two in-Electron receipts, which use scratch ledgers — a substitution the receipt discloses itself) |
| 11 | **D-P16-0** — exercised inside the packaged Electron runtime | **PASS** | Both receipts carry `env:{electron:"31.7.7", node:"20.18.0", chrome:"126.0.6478.234", platform:"win32"}` |
| 12 | Independent **gate-validator** confirmation | **PASS_WITH_RESERVATIONS** | §3 |

**In-Electron receipts (D-P16-0) — regenerated twice this turn, independently, and then restored:**

```
cd apps/desktop && node selfcheck/run.js worker-launch → exit 0 · ok:true
    local ["…\ollama.EXE","run","qwen3:8b"] · frontier ["…\claude.EXE","--model","claude-fable-5"]
    lease-a2d18c9c8a2c held by pid 60340 · in_use_after_release 0
cd apps/desktop && node selfcheck/run.js worker-spawn  → exit 0 · ok:true
    pane-2 LIVE ollama run qwen3:8b (7 credential vars scrubbed, local — residency-governed)
    pane-4 LIVE claude --model claude-fable-5 (durable terminal lease-66c5f4874df8 1/2)
    conductor-pane selection REFUSED · fabricated option REFUSED (host_enumeration) · occupied pane REFUSED
    terminal released on session kill · surviving_pids []
```

The builder ran both; **the gate-validator then ran both itself** and restored the working tree, so the
tag points at the receipts **as committed at `.ticket`/`.spawn` and verified field-by-field by both
passes** (the 17A `.close` R0 condition, applied here without needing to be asked). Across the three
independent runs the only differences are run identity (timestamps, pids, lease ids, scratch-ledger
path, the pid-derived credential **name**) and genuine host state (`host_used_vram_mb` 4528 / 5319, the
pinned-budget arithmetic that follows, which local model is the squeeze target, and one
`local_pane_excerpt` that caught an `ollama` spinner frame instead of the REPL prompt while
`local_pane_output_seen` stayed `true`). **Every assertion field is identical in all three runs** —
including `local_budget_refused_by:"vram_admission"`, `forged_refused_by:"host_enumeration"`,
`conductor_refused_by:"worker_role"`, `terminals_released:true`, `in_use_after_release:0`. That the
checks are robust to daemon state, rather than passing because the host happened to be idle, is the
point of running them three times.

**One receipt IS regenerated and committed by this unit** — `PHASE16C_DISPATCH_SELFCHECK.json`, which
discharges validator **M-7**: `.legs` edited `apps/desktop/selfcheck/conductor-dispatch-selfcheck.js`
without re-running it. Re-run here in-Electron: `ok:true`, `legs {"conductor":"mock","workers":"mock"}`,
`U58 owed=true`, `torn_down:true` — i.e. the **shell's** dispatch path is still mock-first and still
says so out loud, which is the honest state until 17C/17E wire it. Diff vs. the committed receipt:
timestamps only.

**Test suites (foreground, this host, this turn):**

| Suite | Command | Result |
|---|---|---|
| Python control plane | `py -3.12 -m pytest tests/ -q` | **1370 passed / 0 failed** (234.03 s) |
| Electron shell | `node --test "test/*.test.js"` in `apps/desktop` | **277 pass / 0 fail** (6.25 s) |
| Terminal layer | `node --test "test/*.test.js"` in `terminal` | **179 pass / 0 fail** (0.19 s) |

(`python` on this host is 3.14 and cannot collect the suite — `py -3.12` is the recorded interpreter,
unchanged since Phase 2's D-LANG-01 closure. This is **U108**, and this unit hit it first-hand:
`python -m pytest tests/ -q` → `73 errors in 2.10s` before the run was repeated under `py -3.12`.)

**Lint (substitution for the unavailable `ruff`):** `git diff --name-only gate/phase-17a..HEAD -- "*.py"
| xargs py -3.12 -m pyflakes` → **no output** over all **28** Python files the track touched
(55 files changed in total, +11 847 / −206).

## 3. Mandatory independent gate-validator (whole track) — **PASS_WITH_RESERVATIONS**

Run in an isolated context, foreground, this turn (117 tool calls, ~16 min). It trusted no builder
claim and re-derived every criterion itself.

- **Re-ran all three suites itself:** pytest **1370 passed / 0 failed** (231.80 s), apps/desktop
  **277 pass**, terminal **179 pass** — matching this report's numbers independently.
- **Re-ran both in-Electron receipts itself** and compared field-by-field with the committed ones
  (§2). It also checked the builder's working-tree claim *before touching anything* and confirmed it.
- **FIVE load-bearing falsifications, two required**, every file restored and proven byte-identical by
  `git show HEAD:<path>` hash comparison:

  | # | Mutation | Result |
  |---|---|---|
  | F1 | `_sanitizeRestoredChrome` made a pass-through | **RED** — 3 tests (179 → 176/3), incl. "a snapshot written by a KILLED shell comes back INTERRUPTED, never `running`" |
  | F2 | `live_flow.py:532` contradiction check disabled | **RED** — `test_a_declared_worker_leg_that_contradicts_its_evidence_is_refused` DID NOT RAISE: a packet could then declare `live` on evidence deriving `attempted` |
  | F3 | the U105 `shell_env_names` union removed | **RED** — 3 tests across two files |
  | F4 | `LiveGovernedFlow.close` skips the worker `release()` | **RED** — 2 tests; the governor is left `in_use:1, active:['frontier-w1']` |
  | F5 | the conductor-pane guard disabled | **RED in two independent channels** — the desktop suite (277 → 276/1) **and the in-Electron receipt itself** (`ok:false`, shell exit 1, `"a worker model was not refused into the CONDUCTOR pane pane-1"`) |

- **Independent in-repo corroboration of the live run** (it could not read outside the repo root, so it
  found its own): the durable ledger's `updated` stamp lands **25 ms after** the packet `ts` — the
  acquire/release the `--live-workers` factory performs and the mock path never does — and 277 s of
  elapsed time is consistent with a real call and inconsistent with the ~2 s stub U119 describes.
- **Prohibitions:** no `[remote]` section in `.git/config`; `docs/canonical/` and `schemas/` diffs
  **empty**; `mcp_server/` limited to `protocol.py` (+101/−1), every line read — "pure
  transport/liveness, **zero authorization logic**", invariant 7 intact; `config/live_operation.json`
  untracked (`.gitignore:19`) and credential-free; a repo-wide sweep for `sk-ant-`/`sk-`/`ghp_`/
  `Bearer`/`AIza`/PEM headers returned **zero hits**; `git diff --numstat gate/phase-17a..HEAD --
  docs/registers docs/evidence` shows every file `N 0` — **additions, zero deletions** (append-only).
- **D-LOOP-1 after its own runs:** process table identical to the pre-run baseline, no `electron.exe`,
  no stranded scratch ledger, real ledger `updated` unmoved. **Its live spend: zero prompts.**
- **Register audit:** it verified U58/U60/U70/U105/U100/U109/U111–U119 against the code line by line and
  found **no claimed-resolved item unresolved** — "the register is, if anything, still erring toward
  understating progress". It confirmed U70's mode-toggle half is genuinely still open
  (`renderer.js:642` hard-codes `mode:"autonomous"`).

**Ruling: `gate/phase-17b` may land**, conditional on correcting two factually-wrong sentences in this
report (M-4, M-5) — both corrected in §2 row 10 above, with the correction shown rather than silently
applied. Reservations M-1/M-2 are carried forward visibly (§5, §6); M-3 and M-6…M-9 are dispositioned
in §5.

## 4. Independent spec-auditor over the composition — **PROHIBITED DRIFT: NONE**

Read-only, foreground, this turn (63 tool calls, ~11 min), aimed deliberately at what the three
sub-steps become **together** — the earlier passes audited each alone. **3 MAJOR, 11 MINOR, no
BLOCKING.**

Explicit rulings it returned, each with file:line evidence:

- **Invariant 7 — CLEAN.** `mcp_server/server.py` only routes and authenticates; every allow/deny stays
  in `control_plane/policy.py`. The `.legs` change is client-side transport (`protocol.py:97-158`), and
  the orphan-CANDIDATE rejection is **not in `mcp_server/` at all** — it is at `live_flow.py:996-1004`,
  issued by the *gate* node's credential, and it is a **shape** decision, with `MemoryService.transition`
  still running the real lifecycle + policy authorization.
- **Invariant 2 — one reachable gap, registered (U114 / §5 M-1).** The picker → ticket → SessionManager
  path is clean and recovery never reattaches.
- **Invariants 10/11/13 — CLEAN.** The worker publishes `CANDIDATE` with `provenance.author_node`;
  `policy.authorize_publish` denies any worker status ≠ CANDIDATE **and** a mismatched author; promotion
  is the gate's, and a gate may not promote what it authored; a lost CAS yields an explicit conflict
  object and the entry is excluded from `accepted`. The live packet dates what actually happened —
  `DISPATCH_TS` is now mock-only.
- **Invariant 21/22 — accounting sound on exit/kill/quit/refusal**, including the undelivered-ticket
  branch (U100); the residency budget is fixed **before** the resident set is read and never derived
  from it; unknown-vs-empty is fixed. One crash path is not covered (§5 A-MAJOR-2).
- **Invariant 30 — CLEAN**; **§2.2 — CLEAN** (names only; a `name=value` entry refused without echoing
  it; the sweep found only an arithmetic answer `SUM=174` and a literal placeholder).
- **No prohibited drift of any kind:** no TTS (I-V2 intact), no forced consensus, no new approval layer
  (`refuseSelection` is explicitly a UX mirror of the Python guard), no opaque-agent UI, no new provider,
  no float in policy/pricing (`Decimal` in `extract_reported_model`).

Its bottom line: *"the three sub-steps compose better than they read individually… The one place the
composition leaks is where a sub-step's own accounting boundary ends"* — MAJOR-1 (the mock pool sits
outside the evidence derivation `.legs` added), MAJOR-2 (the CLI child sits outside the containment
`.spawn` established), MAJOR-3 (`pane:new` sits outside the ticket path `.ticket` defined).

## 5. Findings and their disposition

**No finding from either review is BLOCKING, and none is softened.** Product code was deliberately
**not** touched after validation: fixing here would have voided the five falsifications and the
receipt comparisons the gate rests on — the same reasoning recorded at `phase-17a.close` §5. Every
finding is therefore either **corrected in this report**, **discharged with a real run**, or
**registered with an explicit failure scenario and a named owner**.

| # | Finding | Disposition |
|---|---|---|
| **V-M-4** | This report claimed three D-LOOP-1 keys for "every receipt"; the `.ticket` receipt carries none of them | **CORRECTED in §2 row 10**, with the error shown |
| **V-M-5** | This report called the real ledger "untouched" — false for `.legs`, which acquires and releases a durable lease by design | **CORRECTED in §2 row 10**: empty, with every lease handed back |
| **V-M-7** | `.legs` edited `conductor-dispatch-selfcheck.js` without re-running it | **DISCHARGED** — re-run in-Electron this turn, `ok:true`, receipt committed (§2) |
| **V-M-1 / A-MAJOR-3** | `pane:new` still accepts a renderer-supplied `file`/`args`: a **supervised but unticketed, unleased, unscrubbed** model process is reachable from the least-trusted surface | Already **U114** (pre-existing, owner 17E). Both reviews independently called it the track's largest carried risk, and the auditor required its bound to appear in the track's *does-NOT-claim* list — **done, §6**, because "the only place the shell executes a launch **ticket**" is not "the only place the shell starts a model process" |
| **V-M-2** | U60 is a race-narrowing, not a fix, and **every** live dispatch depends on it (420 s call vs. a 60 s handler timeout; TOCTOU between `select` and `sendall`) | Already **U60**'s recorded limit; the validator called the honesty "exemplary". Restated in §6; the structural fix (per-connection timeout or keepalive) is owed and unowned until a track needs multi-exchange live work |
| **A-MAJOR-1** | A `live` worker aggregate is derivable for a run in which the **legacy `LocalWorkerAdapter` pool** also produced accepted work: `_worker_evidence` emits rows only for injected handles, so `_assert_legs_honest` cannot see the mock contribution | **U120** — with the exact construction, and the honest note that it is unreachable on every shipped path today only because `emit()` passes `worker_ids=()` when live, i.e. the headline leg's honesty rests on a **caller argument** rather than on the derivation, which is what `_assert_legs_honest` exists to remove. Owner 17D/17E, where a mixed pool first becomes likely |
| **A-MAJOR-2** | A crash of the `.legs` emitter **orphans a live `claude` child** (bare `subprocess.run`, no job object) while its durable lease is reaped as dead-holder — an uncounted live terminal | **U121**. The shell path discloses its containment gap (`containment.still_owed`, U25); this path made no such disclosure. Owner: whichever track adds OS-level containment (U25) |
| **A-MINOR-1** | A local model with an **unknown** footprint is refused under the FIT gate with "does not fit", not under the footprint gate | **U122** — "we could not tell" rendered as "it does not fit"; the split exists (`GATE_VRAM_FOOTPRINT`) and was applied to the non-int branch but not the model-absent branch |
| **A-MINOR-2** | The MCP reconnect is **invisible** to every artifact, though the register says every live dispatch relies on it | **U123** (invariant 27 / Buildout §4) |
| **A-MINOR-3** | The orphan-CANDIDATE rejection's comment claims it leaves a gate record pointing at the entry; it does not (no `evidence=[orphan]`, no `entry_id`) | **U124** |
| **V-M-3 / A-MINOR-4** | "Reproduced three times" has **one** committed artifact | **Stated in §6.** Reproduction is the strongest available answer to U119 and it is the claim with no retained artifact — recorded, not re-asserted |
| **A-MINOR-5** | `torn_down:true` is a producer **self-report** set after `finally`, not a measurement like `.spawn`'s `real_ledger_unchanged` | **U125**, and stated in §6 |
| **A-MINOR-6** | The `.spawn` self-check derives its pinned VRAM budget **from the resident set** — the exact shape the product path forbids — and its scope note describes it neutrally | **U126.** Deliberate (it is what makes the fit gate reachable in a test), but it must be named as the forbidden shape used knowingly; the `.ticket` receipt is the one that carries a real VRAM refusal |
| **A-MINOR-7** | `main.js:171` interpolates the legs from the feed but hard-codes "live workers OWED (U58)" beside them | **U127** — true today (this unit's own dispatch receipt shows `owed=true`), but a governance claim as a literal in a file that elsewhere insists such lines be sourced |
| **A-MINOR-8** | A launched local pane's residency chip is frozen at authorization time (`· loading` for the pane's life) — the visible residue of **U64** | **U128**, and the auditor's demand for an explicit **U63/U64 disposition** is answered in §6 |
| **V-M-6** | The `.ticket` receipt *asserts* scratch scoping where `.spawn` *measures* it | **U129** (receipt-strength gap; empirically fine — both the builder and the validator verified the real ledger and lease dir after five in-Electron runs) |
| **A-MINOR-9** | `.ticket`'s "`mcp_server/` untouched" must not be carried forward | **Not carried.** §7 states the affirmative instead: the change is transport and carries no authorization — both reviews ruled on it independently |
| **A-MINOR-10** | The live worker leg is proven for **one vendor**; there is no codex live-worker factory though codex is in OP-6 scope | **U130**, and stated in §6 |
| **A-MINOR-11** | The live run's shared memory was a **tempdir**, discarded on exit — the CANDIDATE and its ACCEPTED promotion no longer exist | **U131**, and stated in §6. Correct under D-LOOP-1, but "U58 worker half RESOLVED" must not be read as "the project's shared memory now contains that artifact" |
| **V-M-8** | `emit_conductor_dispatch.py:180-182` cites §2.5 backwards | **U132** (comment-only; not fixed post-validation, by the §5 rule above) |
| **V-M-9** | `.legs` §4/§5 state the headline two sections before the U119 limitation | Structural note taken: **this** report states the limits in §6 and marks the bounded criteria in the table itself |

## 6. Substitutions, limitations and OWED (directive §6 / §10.4 — honest)

**What this track explicitly does NOT claim** (both reviews required these bounds to be stated here,
not only in the register):

- **"The only place the shell executes a launch TICKET" is not "the only place the shell starts a
  model process."** `pane:new` still passes a renderer-supplied `file`/`args` to a *supervised* session
  under the shell's own node id — no ticket, no I-X3 lease, no credential scrub (**U114**, pre-existing,
  owner 17E). `gate/phase-17b` asserts that the **picker path** is governed. It does not assert that
  every door to a model process is.
- **The live worker leg is proven for ONE vendor.** `--live-workers` can only spawn `claude_code`;
  there is no codex live-worker factory, though codex is in OP-6 scope and the picker enumerates it
  (**U130**). Invariant 4's interchangeability is demonstrated for one adapter, not two.
- **OpenCode is absent from the governed picker→launch path** (**U112**), so the track text's
  "local via the host runtime (Ollama/**OpenCode**)" is half met and disclosed as such — the validator
  accepted it as a disclosed coverage gap rather than a failed criterion.
- **The live run's shared memory was a tempdir, discarded on exit** (**U131**). "U58 worker half
  RESOLVED" means a live worker's CANDIDATE passed the real gates in a real store — **not** that the
  project's shared memory now contains that artifact. The surviving record is the JSON feed.
- **`torn_down:true` is a self-report, not a measurement** (**U125**), unlike `.spawn`'s
  `real_ledger_unchanged`, which is a byte comparison.
- **"Reproduced three times" has one committed artifact** (254 s / 318 s / 277 s; only the 277.4 s run
  is retained). Reproduction is the strongest available answer to U119, and it is the one claim with
  no retained evidence.

**Substitutions, limitations and OWED:**

- **U63/U64 — explicit disposition** (the track text asks for residency honesty "narrowed as far as
  real evidence allows"). **U63 is narrowed:** the picker's residency view is now sourced from the
  daemon's real `/api/ps`+`/api/tags` state, "no view" is distinct from "empty" and renders UNKNOWN,
  and picker greying is pinned to **agree** with the real gate in both directions. **U64 is NOT
  closed:** there is still no residency-**completion** gate before execute — a pane authorized while
  the model is loading renders `· loading` for the life of the pane and nothing refreshes it
  (**U128**). The honest summary: residency is now an *authorization* fact that is true when written,
  and not yet a *live* one.
- **The conductor leg of the live dispatch is still `mock`, and the feed says so.** 17B proves the
  *worker* half of U58. A live conductor **session** exists (17A) and a live conductor **dispatch**
  driving live workers end-to-end from that session is 17C/17E work. Nothing here claims otherwise.
  This unit's own `conductor-dispatch` receipt shows the shell path still reporting
  `legs mock/mock · U58 owed=true`.
- **`live` is caller-scoped, and the receipt cannot by itself prove liveness (U119).** The
  `.legs` validator demonstrated it by stubbing `subprocess.run` and reproducing the receipt in ~2 s
  with no spend. Narrowed by the `live_run` block (real `run_ts`, measured `elapsed_s`, `cli_present`,
  the bounds in force) and by stamping the packet with the real clock instead of the mock path's
  replayable `DISPATCH_TS` — **not eliminated**, and recorded as a limit rather than claimed as proof.
- **U60 is narrowed, not resolved-in-kind.** A reap landing between the liveness check and the
  `sendall` still fails closed, unrecovered; and a 420 s live call against the server's 60 s handler
  timeout means **every** live dispatch is reaped at least once and relies on the reconnect. That is a
  workaround for a timeout mismatch, and the code says so at the call site.
- **No enforceable token bound on a live exchange (U116)** — only the 420 s wall clock.
  `LIVE_WORKER_MAX_TOKENS` reaches a CLI that accepts no such flag and is inert.
- **No cost-to-accepted-output at the first worker spend site (U117)** — Buildout §4 asks for it from
  day one; `total_cost_usd` is parsed two functions away and simply not carried.
- **`worker_legs` / `worker_evidence` / `node_refusals` reach no UI surface (U118)** — invariant 27 is
  met at the feed and not at the operator's screen. Owner: 17D/17E.
- **The VRAM budget used by the checks is pinned, not this host's real capacity (U96) — and the
  `.spawn` check derives its pinned budget FROM the resident set (U126)**, which is precisely the shape
  the product path forbids. It is deliberate: it is what makes the fit gate reachable in a test at all.
  It is named here as the forbidden shape used knowingly, because the receipt's own scope note
  described it neutrally. Consequence: the `.spawn` local leg can never fail admission — the real VRAM
  refusal lives in the `.ticket` receipt (`local_budget_squeezed_mb` → `refused_by:"vram_admission"`).
- **Containment is authorization, not OS-level containment.** Permission-profile binding (U78(a)) and
  job objects / ACLs (U25) remain owed; the ticket itself discloses this rather than implying more.
- **The scratch lease ledger is a substitution, disclosed.** For the lifetime of a self-check's
  frontier session a live terminal exists that the REAL ledger does not count — stated in the
  receipt's `scope_note_live_terminal`.
- **`ruff` is not installed on this host** and §2.7 does not permit a pip install for it; `pyflakes`
  is the recorded substitute over every Python file the track touched. The `.ticket-revalidate3`
  validator independently confirmed the absence is genuine.
- **Not in this track (and not claimed):** voice/real Parakeet (U74 → **17C**), the approval drawer's
  demo trio and the sessionless-pane resize guard (F2 / U73 → **17D**), the assembled fully-live
  receipt (**17E**). No new provider; cloud Kimi/Qwen stay OWED-pending-operator.
- **The emitter's live child is uncontained (U121)** and the MCP **reconnect is unobservable** (U123);
  a live worker aggregate could in principle be declared over a partly-mock pool (U120). All three are
  composition findings — each sub-step's accounting was sound inside its own boundary.
- **Live-budget discipline honored:** the track's live spend is the three `.legs` dispatch runs (one
  exchange each). This unit added **zero** live prompts: the receipt spawns start real sessions and
  kill them without submitting anything, and the gate-validator independently reports **zero** prompts
  spent across its five falsifications and three in-Electron runs.

## 7. Invariants honored

1 (the shell can only *read* an authorization Python mints; every live lever — `config/live_operation.json`,
the ticket, the I-X3 cap — remains the operator's) · 2 (one supervised spawn path, governed identity,
admission-or-kill; a naked CLI is unreachable from the picker) · 3 (badges, chrome and leg labels state
the honest lesser fact — `interrupted_from` rather than `live`, UNKNOWN residency rather than
"not loaded", `attempted`/`skipped` rather than `live`) · 4 (mock and live workers run the same governed
loop with no branch) · 7 (the `mcp_server/` change is **client transport** in `protocol.py` — liveness
before a write — with no authorization logic added) · 10/11 (the live worker publishes CANDIDATE and
never self-canonizes; the packet is stamped with the real clock so provenance dates what happened) ·
19 (locality per node: local panes take no subscription terminal) · 21/I-X3 (durable, cross-process,
session-keyed, released on exit/kill/quit/failure/refusal) · 22 (residency is a scheduled, visible
authorization gate, never derived from what is already resident) · 27 (every refusal names its gate and
reaches the renderer; U118 records where visibility stops) · 29 (containment disclosed exactly as far as
it goes) · 30 (no invented governance layer — the lease and the residency gate enforce allowances the
system is *given*) · D-LOOP-1 (no session, lease or process outlived any unit; the operator's real
ledger untouched) · D-LOOP-2 (every suite and both reviews foreground, in-turn) · §2.2 (credential
**names** only — values never read, stored or transmitted; the CLIs use their own host-native auth).

## 8. Two-commit convention (this sub-step)

- **Work commit** (`.close` adds **no product code**): the regenerated `PHASE16C_DISPATCH_SELFCHECK.json`
  — the one receipt this unit is entitled to change, because re-running that check is what discharges
  validator M-7. The `.ticket`/`.spawn` receipts stay exactly as committed and validated (§2).
- **Evidence commit:** this report + the register rows (U120–U132 + the dispositions), carrying the
  work-commit hash → tag **`gate/phase-17b`**.
- Then the `LOOP_STATE.json` commit (iteration 82, `next_step: phase-17c`).

*End of `phase-17b.close` evidence report — Phase 17B whole-track close.*
