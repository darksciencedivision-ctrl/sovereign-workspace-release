# PHASE 14C SUB-STEP EVIDENCE — `.worktree` (scoped MCP context → isolated worktree drive → tests run)
Autonomous loop iteration 25 · 2026-07-18Z · **sub-step, NOT the phase gate**
(`gate/phase-14c` closes next at sub-step `.gate`, after the CANDIDATE submission + controlled
merge, with the MANDATORY high-stakes gate-validator once `.harness`/`.worktree`/`.gate` all land.
No gate tag for a sub-step — mirrors the 14A/14B decomposition pattern.)

## Objective (directive §9 table 14C middle cell; invariant 23; Plan §7-P10 / §12.2)
Drive **OpenCode itself** for real against a **local** coder model, from **scoped MCP context**,
inside an **isolated git worktree**, and **run the worktree's tests** — the middle cell of the
14C chain:

    scoped MCP context  →  isolated worktree modification  →  tests run

The CANDIDATE artifact submission + controlled merge path is the **next** sub-step (`.gate`),
deliberately NOT done here.

14C decomposition (directive §3.2): `.harness` (iter 24) → **`.worktree` (this, iter 25)** → `.gate`.

## What was produced
- **`adapters/coding/opencode/driver.py` (NEW)** — `OpenCodeDriver`: deterministic ORCHESTRATION
  around a real `opencode run` subprocess. The subprocess call is the ONE injected seam (`Runner`),
  so the deterministic suite proves every governance property with a scripted fake while the live
  test passes the real `subprocess_runner` — the same mock-first/real-live split as the frontier
  backend and `.harness`. Load-bearing pieces:
  - `read_scoped_objective(entry_id)` — reads **exactly the one assigned MCP entry** via
    `get_content` (**invariant 8**: scoped context, never a store sweep / full-transcript forward);
    fail-closed on a missing/empty assignment.
  - `write_scoped_opencode_config(session_dir, model, base_url)` — **U30 discharge**: writes a
    SESSION-LOCAL `opencode.json` declaring ONLY the loopback Ollama provider + the pinned local
    model, returned so `OPENCODE_CONFIG` can point at it. Refuses a **non-loopback baseURL**
    (`DriveRefused`, §2.3 — no off-box/paid routing) and a **non-`ollama/` provider-qualified
    model** (`ModelNotLocal`, e.g. `openai/gpt-4o`, rather than silently re-prefixing it).
  - `build_command` — `opencode run [--pure] --auto --dir <worktree> -m ollama/<model>
    --format json <objective>`; the `ollama/*` model pin is enforced inside the harness builder
    (`_require_local_model`, fail-closed).
  - `build_env(config_path)` — the harness's credential-scrubbed env (**§2.2/§2.3**) with
    `OPENCODE_CONFIG` set **after** the scrub (so the config pointer can never be mistaken for a
    credential and dropped).
  - `drive(objective)` — writes the scoped config, runs OpenCode in the worktree (`cwd`+`--dir`),
    reads back the worktree's own `git status` changes, and computes `escaped` by checking the
    **base trunk** for any modification outside `worktrees/` (**isolated worktree modification**,
    Phase 10 / invariants 1, 29). Returns a `DriveResult`
    (`drove/returncode/timed_out/tool_events/changed_files/edit_completed/escaped/model/config_path`).
  - `run_worktree_tests(test_argv)` — runs the worktree's tests **inside the worktree** after the
    drive (**"tests run"**), reporting pass/fail honestly; refuses an empty command (no vacuous
    "tests run").
- **`adapters/coding/opencode/harness.py` (MODIFIED)** — `build_run_command` (real + mock) gained
  optional `workdir`/`auto`/`pure` flags via a shared `_opencode_run_argv` helper (backward
  compatible; the model pin is still enforced first). The existing `.harness` unit tests pass
  unchanged.
- **Tests (NEW):**
  - `tests/unit/test_opencode_driver.py` (12, deterministic, scripted fake runner — no real spawn).
  - `tests/integration/test_opencode_worktree_live.py` (1, **REAL** `opencode run` drive against
    the host's local model in a real git worktree; skip-with-record when absent).

## The live drive — what genuinely ran (honest, directive §6)
The OpenCode drive is **local + credential-free**, so — unlike the frontier live smoke (which is
skip-with-record) — it **RAN LIVE** this session, repeatedly, through the production driver API.

**Proven RELIABLY (asserted in the committed live test, and reproduced ~10× across
`qwen2.5-coder:7b`, `devstral-small-2:latest`, `qwen3-coder:30b`):** OpenCode itself is genuinely
driven headlessly — it spawns, is pinned to the **LOCAL** Ollama model, runs its agent loop, and
returns cleanly. One recorded committed-test `DriveResult`:
```
drove=True, returncode=0, timed_out=False, model='ollama/qwen2.5-coder:7b',
escaped=False, config_path=<session>/opencode.json,
stdout_tail=…"type":"step-finish","tokens":{"total":2068,"input":2050,"output":18,…},"cost":0}}
```
`"cost":0` in the real `--format json` event stream confirms a **local** model ran (a paid
frontier would be billed); `escaped=False` confirms the drive stayed confined to the worktree; the
`OPENCODE_CONFIG` session file (U30) was present and used.

**Real tool EXECUTION observed** (not just emitted) — a captured `devstral-small-2` event proves
OpenCode invoked its own `read` tool with the model's arguments and reported the result back:
```
{"type":"tool","tool":"read","state":{"status":"error",
 "input":{"filePath":"/greet.py"},"error":"File not found: C:\\greet.py", …}}
```
i.e. the tool machinery is real; here the **model** supplied a wrong absolute path.

**RECORDED, NOT faked (model-quality limitation, directive §6):** a small local coder reliably
**completing** a multi-step schema-correct edit headlessly was **not producible this session**.
Across the ~10 real drives the local models variously emitted tool JSON as text
(`qwen2.5-coder:7b` via the OpenAI-compatible path), called `read`/`edit` with wrong argument names
or absolute paths (`devstral`), stopped after a single turn, or acknowledged-and-stopped. `opencode
run` performs an agent loop but the local models did not converge on a landed edit. This is a
**model-quality** conclusion limited to local backends (§5 phase-13, §6) — **NOT** a
harness/governance/isolation defect (all of which are proven, deterministically and live). The
committed live test therefore asserts the drive + local-model + confinement facts and **RECORDS**
`edit_completed` (typically `False` this session) **without fabricating an edit**; when an edit
DOES land it runs the worktree test against it. **No rendered/edited artifact is claimed that was
not actually produced.**

## Self-check — every criterion vs real output
- **Scoped context, invariant 8 (A):** ✓ `test_drive_reads_only_scoped_entry_and_edits_worktree`
  asserts `mcp.fetched == ["m-obj"]` — only the assigned entry is read; `read_scoped_objective("")`
  and an empty-content entry both raise `DriveRefused` (`test_missing_or_empty_scoped_entry_fails_closed`).
- **Isolated worktree modification, Phase 10 (B):** ✓ changes are read from the worktree's own
  `git status`; `test_out_of_worktree_modification_flagged_escaped` writes a file OUTSIDE the
  worktree and the driver sets `escaped=True` + emits `drive_escape_detected`. The live drive ran
  with `escaped=False`. Honesty (U10): confinement here is worktree scoping (`--dir`+`cwd`) +
  WorkspaceBinding path containment + a base-trunk escape *check* — **not** an OS syscall sandbox
  around a rogue subprocess (same U10 caveat as Phase 10), stated in the module docstring.
- **Tests run (C):** ✓ `test_worktree_tests_run_and_pass_after_a_correct_edit` runs a real
  `python -c "import calc; assert calc.add(2,3)==5"` in the worktree after a scripted correct edit
  (passes); `test_worktree_tests_report_failure_honestly` proves a buggy edit yields
  `passed=False` (fail-closed, honest); empty command refused.
- **U30 discharged (D):** ✓ `test_scoped_config_written_loopback_only_and_pointed_to` confirms the
  session-local `opencode.json` has ONLY the `ollama` provider at the loopback baseURL and the
  pinned model; `test_config_refuses_non_loopback_baseurl_and_non_local_model` proves a
  non-loopback baseURL (`DriveRefused`) and a cloud model (`ModelNotLocal`) are refused.
- **§2.2/§2.3 (E):** ✓ `test_build_env_scrubs_credentials_and_sets_config` — `OPENAI_API_KEY`/
  `ANTHROPIC_API_KEY` scrubbed, no secret value survives, `OPENCODE_CONFIG` set; the model is
  pinned `ollama/*` fail-closed (inherited from the harness builder).
- **LIVE drive honesty (F):** ✓ `test_opencode_worktree_live.py` **actually spawns** `opencode run`
  (not skipped on this host), asserts the real drive facts + `cost:0` local model + `escaped=False`,
  and records `edit_completed` without faking. See "The live drive" above.
- **No edit invented (G):** ✓ `test_no_edit_is_honestly_reported_not_faked` — a no-op drive reports
  `edit_completed=False, changed_files=()`; a timeout reports `drove=False`
  (`test_timeout_marks_not_drove`).

## Test results (real command output, py -3.12 / node)
- `pytest tests/unit/test_opencode_driver.py -q` → **14 passed** (incl. the 2 fail-closed tests
  added for spec-audit MAJOR-1 + MINOR-4).
- `pytest tests/integration/test_opencode_worktree_live.py -q -s` → **1 passed** (live drive ran,
  not skipped; DriveResult recorded above).
- Full suite `pytest tests/ -q` → **442 passed, 36 warnings** (was 427 at `.harness`; +15 net new =
  14 driver unit + 1 live worktree; pre-existing `jsonschema.RefResolver` deprecations only).
- Product JS `node --test` → **131 passed, 0 failed** (apps/desktop 28 + terminal 103; **no JS
  touched** this iteration; the spike rig's 34 JS tests are unchanged/host-run).

## Substitutions / deferrals (directive §6; honest record)
- **Scripted fake `Runner`** is the mock-first substitution for the deterministic suite; the REAL
  `subprocess_runner` is exercised in the live integration test.
- **A landed live edit is RECORDED-ABSENT this session** (model-quality flakiness of local coders,
  see "The live drive"). The *modification-detection + tests-run* path is proven deterministically
  with a scripted correct edit; OpenCode's real drive + real tool execution are proven live. No
  edited artifact is overclaimed.
- **CANDIDATE submission + controlled merge deferred to `.gate`** — this sub-step stops at
  "worktree driven + tests run".

## Open items / notes
- **U30 — DISCHARGED for the drive** by the session-local `OPENCODE_CONFIG` + credential scrub +
  `ollama/*` pin (config isolation no longer rests on the pin alone). `--pure` remains an optional
  defence-in-depth knob; the isolation does not depend on it.
- **New forward note (recorded, non-blocking):** a reliable headless local-coder edit through
  OpenCode's Ollama/OpenAI-compatible tool path is a model/config-tuning item (better agentic
  model, tool-schema shaping, or multi-turn budget) — carried for `.gate`/14E, not a blocker for
  proving the governed drive. Recorded as **U31**.

## Invariant touchpoints
- **Inv 8 (scoped context):** exactly one MCP entry read; no store sweep / transcript forward.
- **Inv 1 & 29 (isolated worktree, controlled path):** drive pinned to the node's own worktree;
  out-of-worktree modification detected + logged; base trunk verified untouched.
- **Inv 23 (coding harnesses behind one contract):** the OpenCode harness is now DRIVEN, not just
  presence-gated.
- **§2.2 / §2.3:** credential-scrubbed child env + `ollama/*` local pin + loopback-only config.
- **§4 (deterministic fail-closed):** drive/test-run/pin/escape logic is pure Python, never model
  output.

## Independent review (this iteration)
- **spec-auditor: 1 MAJOR + 4 MINOR — ALL FIXED this iteration, re-tested green (442 passed).**
  Confirmed CLEAN on every load-bearing invariant it was asked to check (inv 8 scoped read; U30
  config set after the scrub so it isn't dropped; §2.2/§2.3 fail-closed pin + refusals; inv 16/§4
  determinism; no fabricated edit).
  - **MAJOR-1** (escape detection failed OPEN on a `git status` error — `_base_status_outside_worktree`
    swallowed the failure and returned an empty set, so an *unverifiable* drive read as "confined"):
    FIXED — the check now returns `None` on git failure and `drive()` forces `escaped=True` +
    `containment_verified=False` (fail closed, Buildout §4). New
    `test_unverifiable_containment_fails_closed`.
  - **MINOR-1** (docstring overclaimed containment — "any modification outside the worktree" + cited
    the `WorkspaceBinding` as subprocess containment): FIXED — scoped to the BASE-TRUNK working tree
    and clarified that the WorkspaceBinding guards the DRIVER's own fs calls, not the spawned
    `opencode` subprocess (U10 honesty).
  - **MINOR-2** (live test's `"cost":0` substring would also match `0.0012`): FIXED — the test now
    parses every `cost` from the event stream and asserts `== Decimal(0)` (money/units never float).
  - **MINOR-3** (stale comment describing a git identity on the timeout constant): FIXED.
  - **MINOR-4** (driver trusted the passed `SupervisedOpenCode` without re-checking provenance):
    FIXED — the constructor re-asserts `spawned_by_supervisor` (never trust the harness, inv 2/29;
    `DriveRefused` otherwise). New `test_driver_refuses_unsupervised_context`.
- **gate-validator (sub-step confirmation): PASS_WITH_RESERVATIONS.** Every criterion A–G
  re-executed in an isolated context against real artifacts + real command output: A scoped read
  (only `get_content`, `mcp.fetched == ["m-obj"]`), B genuine escape detection (writes at the base
  root, `escaped=True` + event), C honest pass/fail tests-run, D U30 loopback-only config +
  refusals, E credential scrub + `ollama/*` pin, F **the live drive genuinely spawned OpenCode**
  (real session, 2050 input tokens consumed, `"cost":0`, `escaped=False`, config on disk) with
  `edit_completed=False` recorded honestly (not faked), G full suite green. No invariant drift; no
  claimed-but-unproduced artifact.
  - **Reservation (owned, carried to `.gate`):** no live *landed edit* was demonstrated end-to-end
    this run — the "worktree modification" + post-edit "tests run" legs were exercised by a real
    model only up to a genuine drive+tool-execution, and completed only deterministically (scripted
    runner). **`.gate` must NOT claim a live landed edit / live controlled merge unless a real model
    edit is actually produced and shown.** Tracked as **U31** (local-coder headless-edit tuning).

## Disposition
`phase-14c.worktree` PASSED as a **sub-step** (not the phase gate). `gate/phase-14c` remains
**UNTAGGED** — awaits `.gate` (CANDIDATE + controlled merge + mandatory high-stakes gate-validator).
Next: `phase-14c.gate`.
