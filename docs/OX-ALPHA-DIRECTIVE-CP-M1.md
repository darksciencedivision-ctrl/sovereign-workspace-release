# OX-ALPHA-DIRECTIVE-CP-M1 — Sovereign Control-Plane and Local-Inference Loop

| Field | Value |
|---|---|
| Contract | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2, unchanged. `AGENTS.md` binds in full. |
| Envelope | `docs/SWS-UI-001-v1.2-ADDENDUM-03.md` v1.1. It amends ADD-01 and ADD-02; all three bind. Conflict → ADD-03 governs, and you report it. |
| Supersedes | `OX-ALPHA-DIRECTIVE-CP-01.md`, `OX-ALPHA-DIRECTIVE-CP-02.md`, `OX-ALPHA-DIRECTIVE-CP-MERGE-01.md`. **This file is self-contained.** Those three remain on disk as provenance and are not executed. |
| Goals | **G1 – G124**, one continuous ladder, strictly ordered. |
| Gates | `8a`–`8j`, then `9a`–`9j`. Twenty. Un-renumbered so the reviewer's frame of reference is unchanged. |
| Loop state | `evidence/cpm1/LOOP-LEDGER.jsonl` — append-only, one JSON line per iteration, written **before** the next iteration begins. |
| Oracle | `evidence/cpm1/tools/goalcheck.py`, seeded from the verified CP-01 oracle. Contract in §7. |
| Promotion | **Nothing is promoted.** Ollama remains the production default throughout. llama.cpp exits as a validated candidate. |

---

## 1. Operating principle

Verify, then act, then verify. Run the oracle against disk. Take the **single smallest authorized action** that flips the **first** failing goal. Run the oracle again. Append one ledger line. No action is taken that a currently-failing goal does not require.

Four rules override everything else in this file.

**Order is absolute.** G(n) is not acted on while G(n−1) is FALSE. The ladder is dependency-ordered, not thematic. You cannot prove a Conductor round-trip through a session container that still traps the operator in PowerShell; you cannot connect residency actuation to a router you have not proven; you cannot demote a context claim you have not measured. The sole exception is the oracle itself (`G-oracle`), repairable at any point.

**Surgical, not architectural.** Roughly 80 % of what this directive might tempt you to build already exists (§2). You are widening, connecting, and proving it. A rewrite is a defect in this loop, not a strategy. Prefer the smallest correction that makes a goal true inside the existing architecture.

**Nothing is true because it looks finished.** Not a passing test, not a complete-looking implementation, not a green oracle. A goal is TRUE when the artifact its row names exists on disk and says what the row requires. Where the oracle can only check structure, the row is marked ⚑ — those are the reviewer's, and you write them knowing a human will read them, not a regex.

**Truthful failure beats manufactured success.** `FAILED(...)`, `NOT_RUN(...)`, `NOT_MEASURED(...)` and `UNAVAILABLE` recorded accurately are valid, complete outcomes. An estimated measurement, a fabricated availability, or a mock rendered as live is a session-ending violation.

The loop ends in exactly one of two states: every goal TRUE, or a STOP report. There is no third exit. Do not end your turn at a band boundary. If the harness ends it anyway, resume from the first failing goal without re-deriving the plan.

---

## 2. What already exists — do not rebuild

Established by reviewer reconnaissance and re-verified at Band 1. Building any of these again is scope drift and will show up as `UNEXPECTED` in the final diff.

| Capability | Where | Note |
|---|---|---|
| Vendor-blind capability resolver | `modules/sow/scheduler/resolver/resolver.py:1-8,35-71` | filter-then-rank; *"Vendor/model names never enter this path"* |
| Capability vocabulary + schema | `modules/sow/schemas/node.schema@1.1.json:41-61` | 6 capabilities, `capability_descriptor` with `tool_use · min_context · structured_output · locality · harness_class · cost_class · priority`; jsonschema-validated at registration |
| Model roster (names confined to one file) | `modules/sow/adapters/roster.py:4-5,27-45` | *"the roster is the one place a concrete model is named"* |
| VRAM residency planner, 6 states | `modules/sow/scheduler/residency_planner/residency_planner.py:33-47` | `NOT_LOADED · LOADING · RESIDENT · AWAITING_EVICTION · QUEUED · EVICTED`; invariant 22 |
| Inference abstraction | `modules/sow/adapters/base/backend.py:26-29,82-92` | `Backend` Protocol; local path is HTTP POST to `127.0.0.1:11434/api/generate` |
| Context as a hard routing filter | `modules/sow/scheduler/resolver/resolver.py:39-40` | `min_context` already gates resolution |
| Worker registry + MCP control surface | `picker/worker-spawn.js:61-82`, `mcp_server/sovereign_tools.py:642-658` | `assign_task · send_message · read_messages · spawn_worker · get_worker_status` |
| Governed OpenCode spawn path | `node_runtime/supervisor/opencode_spawn.py:1` | *"the ONE place a supervised OpenCode coding harness is born"* |
| Shell lifecycle + job-object containment | `shell/src/states.py:18-27`, `shell/src/supervisor.py` | 8 states, reviewer-`PASS` at Gate 4 — **never modified by this package** |

### 2.1 What merging the two packages buys — take these, they are the point

| # | Optimization |
|---|---|
| **O-1** | **The registry is authored artifact-aware and context-aware in one pass.** Band 7 (Gate 8g) builds the canonical registry already carrying the model↔artifact split and the three context fields. Band 16 then only *populates* artifacts and adds the manifest and ingestion — **there is no migration of a registry we ourselves just wrote.** Run separately, Band 16 would have had to migrate 43 live entries with a `needs_operator_review` flag on every ambiguous tag. That whole risk class is deleted. |
| **O-2** | **One failure vocabulary.** The ten classes defined at G18 are the same vocabulary Band 14 normalizes runtime errors into at G85. Defined once, reused — not two taxonomies that drift. |
| **O-3** | **One main-UI layout pass.** Band 9 places the Token Center centrally knowing Band 18's resource-accounting surface is coming; both land in one edit to `app.js` / `app.css` instead of two. |
| **O-4** | **One adapter pattern, four consumers.** SOW readiness (G17), Distillery (G46), Token Center (G52), llama.cpp (G72) all take the same `http` readiness / `http_json` identity / `job_object` stop shape. Write it once at G17 and instantiate. |
| **O-5** | **Protected roots hashed twice, not four times.** sov-1 alone is 134,462 files / 7.4 GB (~30 min). Adopted once at G4, spot-checked at the handoff, fully re-verified once at G117. |
| **O-6** | **One fs-watch window** brackets the whole run (G5 → G117) instead of two. **One report**, `docs/CP-M1-REPORT.md`, in two parts. |

---

## 3. Settled — do not re-derive, do not re-open

Each of these was established with evidence and costs a STOP to contradict. If disk contradicts one, that is `PREMISE_CONTRADICTED`: record the new fact and stop; never pick the reading that lets work continue.

| # | Settled fact |
|---|---|
| **S-1** | **Debate Table does not autostart.** Nothing in the shell starts any module — `main()` builds runners and polls, and every runner begins `STOPPED`/`NOT_STARTED`/`CONFIG_ERROR`. R-01 is a **proof obligation plus a legibility fix**, not a repair. Building autostart suppression is building a fix for a defect that does not exist. |
| **S-2** | **The Token Center holds no credentials.** No key store, keyring, DPAPI, `.env`, or provider authentication. It reads local usage ledgers and lifts only counters and model/provider identifiers. Requirement 14 is satisfied by that **absence**. Introducing a credential store would create the exact leak surface the requirement forbids. |
| **S-3** | **The residency planner is the sole eviction authority.** llama.cpp's router runs `--no-models-autoload` with `--models-max` **strictly above** the planner's concurrency bound, so the router's own LRU is unreachable by construction. Band 13's `--models-max 1` is a validation setting and **must not survive into Band 15**. Two LRU evictors over one VRAM pool is `DUAL_EVICTOR_CONFLICT`. |
| **S-4** | **One VRAM budget authority accounts for both runtimes.** Ollama and llama.cpp draw on the same 8151 MiB and neither knows the other exists. Before any load is scheduled, adopt and record exactly one of: (a) a real VRAM reader (`nvidia-smi --query-gpu=memory.used,memory.total,memory.free` or NVML) as the planner's budget input, or (b) exclusive residency enforced in the backend contract. Neither → `VRAM_BUDGET_UNACCOUNTED`. |
| **S-5** | **The host is an 8 GiB machine.** RTX 5060 Ti, 8151 MiB VRAM (~5.26 GiB free at capture), Blackwell sm_120, 63.7 GiB system RAM, Windows 11, `py -3.12`. No torch, transformers, peft, bitsandbytes, or unsloth is installed. 27B-class models run through CPU/RAM offload. ExLlamaV3, speculative execution, Unsloth, training and broad quantization are **deferred behind a hardware decision** — see §9. |
| **S-6** | **Grok is discovered, never declared.** Whatever the host's `grok_build` CLI enumerates at discovery time is what the registry contains. The three historical `grok-4.6` records in `.sovereign_store` are `SPAWNING` with `pid: null` — that attests *selectability*, not availability. Neither `grok-4.5` nor `grok-4.6` is written into any list on the strength of this document. |
| **S-7** | **`D:\Token Piggy Bank\data\**` is excluded from the protected baseline** (ADD-03 A-1). Its sqlite drifts on a 300-second refresh ring: `391b8836…` at capture, `a7a28385…` 36 minutes later, same size. Runtime state, not source — and already excluded from the ADD-01 §3.3 copy. |
| **S-8** | **The SOW cap area includes `mcp_server/**` and `schemas/**`** (ADD-03 A-2), at the same 400-line cap. |
| **S-9** | **Port 8765 is freed by pid immediately before Band 9** (ADD-03 A-3), using `Stop-Process` — builder tooling. Nothing is executed from inside `D:\Token Piggy Bank\`. If already free, record and stop nothing. |
| **S-10** | **Model identity ≠ deployment artifact ≠ runtime backend ≠ model.** One model owns many artifacts. OpenCode and llama.cpp are `kind: agent_runtime` / `model_runtime`; neither is ever a `model_id` or a row in a model list. A `null` model reference is legal only for `backend ∈ {powershell, none}`. |
| **S-11** | **A terminal is a session container.** Creating one spawns no process. Backend and model are selected while the session is `EMPTY`/`CONFIGURING`. PowerShell is an explicit execution type, never a default and never a state the operator arrives in without choosing it. |
| **S-12** | **Promotion state is a third orthogonal axis** — distinct from node/process state and from VRAM residency. The three are never unified. |

---

## 4. Envelope

Per-area caps are **per package and never pooled**. Bands 1–10 measure against `evidence/cpm1/before-a/`; Bands 12–20 measure against `evidence/cpm1/before-b/` captured at the handoff. **A line changed in Bands 1–10 is Band 12–20's baseline, not its spend.** Test files are excluded from every cap.

| Area | Cap | Package |
|---|---:|---|
| `shell/src/**` | 320 | A |
| `shell/static/**` | 300 | A |
| `shell/modules/*.json` | 140 | A |
| `modules/sow/apps/desktop/**` | 700 | A |
| `modules/sow/{control_plane,adapters,node_runtime,mcp_server,schemas}/**` | 400 | A |
| `modules/distillery/**` | 500 | A |
| `modules/tokencenter/**` | 60 | A |
| **Package A absolute** | **1,850** | |
| `modules/sow/adapters/**` | 450 | B |
| `modules/sow/scheduler/**` | 200 | B |
| `modules/sow/{control_plane,schemas}/**` | 500 | B |
| `modules/sow/{tools,config}/**` | 150 | B |
| `shell/**` | 220 | B |
| `shell/modules/llamacpp.json` (new) | 45 | B |
| `runtime/**` (config only; binaries are artifacts) | 60 | B |
| **Package B absolute** | **1,625** | |
| **Merged absolute** | **3,475** | |

Splitting one logical change across sub-cap edits to evade a cap is a violation, not a technique. Protected trees, install rules, network rules and the **provider-spend prohibition** are ADD-01 §3 and ADD-02 §3 unchanged. **No provider spend is authorized.**

---

## 5. The goal ladder

Read `TRUE when` as a conjunction. Hashes are full lowercase 64-hex, taken after final write, `Test-Path`-verified. Every new behaviour needs a captured **fails-before** and **passes-after**; a test that never failed proves nothing. Every evidence file carries `# utc:` and `# producer: ox-alpha CP-M1`. ⚑ marks a goal whose oracle predicate is structural — the reviewer reads the artifact.

### Band 0 · Precondition and adoption

| # | Goal | TRUE when |
|---|---|---|
| G1 | Authorization | ADD-03 §7 sentence quoted verbatim with its UTC in `evidence/OPERATOR-INSTRUCTIONS.log`, logged before any other mutation. `evidence/cpm1/session-start.txt`: true UTC; which shell your bash tool runs; sha256 of `docs/DECISIONS.md`, `AGENTS.md`, `CLAUDE.md` (latter two equal), ADD-01/02/03 and this file. |
| G2 | **Provider-spend contradiction reconciled** | `evidence/cpm1/spend-reconciliation.txt` records `modules/sow/config/live_operation.json`'s `live_operation_authorized` and `providers` verbatim against the §7 authorization. Configuration permitting provider-backed paths while authorization says no spend → STOP `PROVIDER_SPEND_CONTRADICTION`. **No interpretation.** Operator authority only. |
| G3 | Host baseline | `evidence/cpm1/baseline/`: `git-head.txt`, `git-status.txt`, `host-hardware.json` (**fresh capture, not the 2026-08-19 file**), `runtime-inventory.json`, `ollama-version.txt`, `ollama-model-list.json`, `schema-hashes.json`, `ports.txt` (**5175 · 8700 · 8765 · 5180 · 5183**), `processes.txt`. |
| G4 | Protected roots adopted | The five `evidence/cp01/manifests/manifest-cp01-before-*.txt` exist and carry the pinned `# tool-sha256` matching `evidence/tools/manifest.py` and the ledger's `manifest_tool_sha256`. **Adopted on their 07:21Z capture — not re-hashed** (O-5). `manifest-cp01-before-token-piggy-bank.txt` re-captured excluding `data/**` per S-7, prior artifact preserved and named as superseded with both hashes and the drift reason. SOW upstream HEAD + `status --porcelain` identical across two read-only inspections ≥ 60 s apart, `GIT_OPTIONAL_LOCKS=0`. |
| G5 | Package-A baseline + watch window opens | `evidence/cpm1/before-a/` — copies and hashes of every file the Package-A caps permit touching, with `HASHES.txt` verifying each. `evidence/cpm1/test-run-before.txt` from the README command ends `OK`, count recorded (**entry baseline 122**; a lower count at entry is itself a finding). `shell/BUILD-MANIFEST.txt` entries equal live hashes. `app.css` `:root` matches `docs/THEME-BASELINE-v3.md` exactly. The fs-watch driver starts here and closes at G117 (O-6). |
| G6 | Oracle | `evidence/cpm1/tools/goalcheck.py` covers G1–G124 in order, satisfies the §7 contract, runs clean under `py -3.12`, stdlib only, read-only against the workspace. Seed it from `evidence/cp01/tools/goalcheck.py` — its predicates are verified — rather than writing from scratch. |
| G7 | Ledger opens | `evidence/cpm1/LOOP-LEDGER.jsonl` exists with one line per iteration so far, each `{i, utc, goal, action, changed_lines, flipped, notes}`. |
| G8 | Single writer | `evidence/cp01/` unchanged across two reads ≥ 60 s apart — the superseded CP-01 session is closed. Any live writer → `CONCURRENT_WRITER`. |

### Band 1 · Implementation map — read-only · **Gate 8a**

*No product edit occurs in this band. Any mutation outside `evidence/cpm1/**` and `docs/CP-MAP-01.md` is `BAND_ENVELOPE_VIOLATED`.*

| # | Goal | TRUE when |
|---|---|---|
| G9 ⚑ | Runtime inventory | `docs/CP-MAP-01.md` §1 names from disk: every module runtime and its launch path · the shell launcher architecture · every place a browser is or could be opened · the SOW terminal implementation and its PTY boundary · the Conductor implementation and its input surfaces · every model-registry and provider-configuration source · the Token Center architecture · the Distillery entry points as they exist · OpenCode's installed state on this host. ≥ 20 `FACT[path:line]` citations. |
| G10 ⚑ | Requirement classification | §2 reproduces R-01…R-15 with **your own** disk evidence, one row each, every cell citing `path:line`, each classified `implemented-and-verified` / `implemented-but-defective` / `partial` / `absent`. |
| G11 | Divergence resolved | Either no row disagrees with §3's settled facts, or every disagreement is recorded in `evidence/cpm1/premise-divergence.txt` with both readings and a STOP report written. A disagreement is never resolved by choosing. |
| G12 | Gate 8a | Ledger key `"8a"` `CANDIDATE`, `claimed_by: builder`, `evaluated_by: null`, evidence list with full lowercase sha256 for `docs/CP-MAP-01.md` and every `evidence/cpm1/` artifact so far. Gates 0–7b asserted byte-identical before and after the write. |

### Band 2 · Module lifecycle and runtime truth — R-01, R-02 · **Gate 8b**

| # | Goal | TRUE when |
|---|---|---|
| G13 | No-autostart proved | `evidence/cpm1/8b/cold-start.txt`: a recorded cold start showing `GET /api/state` immediately after `serve_forever()` with **no module in `STARTING` or `READY` by shell action**. Test `test_cold_start_starts_nothing` fails against an artificially autostarting fixture and passes against the product. An external :8700 owner, if present, appears as `EXTERNAL` and the artifact records it was **not** touched. |
| G14 ⚑ | EXTERNAL is legible | A module in `EXTERNAL` is visually and textually distinct from `READY`, states the process is not shell-owned, and its Stop control is disabled or labelled as releasing only the shell's view. Proven by headless-Edge `--dump-dom` → `evidence/cpm1/8b/external-dom.txt` captured against a **live** `EXTERNAL` state. H-9 re-proven: the external pid alive and unchanged after the shell's Stop. |
| G15 | READY requires evidence | `shell/modules/sow.json` no longer uses `readiness.kind = "process_window"`. SOW exposes a real readiness signal; `evidence/cpm1/8b/sow-readiness.txt` shows the probe **failing while the app is mid-boot** and succeeding only once it answers. A probe that has never been observed failing does not satisfy this goal. |
| G16 | STOPPED requires evidence | `evidence/cpm1/8b/stop-evidence.txt`: pid gone and port free after Stop, for every module that binds a port. |
| G17 | **Failure vocabulary — defined once** (O-2, O-4) | Ten classes, each separately distinguishable in `/api/state` and rendered on the card: `PROCESS_START_FAILED · PORT_UNAVAILABLE · HEALTH_CHECK_FAILED · IDENTITY_MISMATCH · MODEL_UNAVAILABLE · PROVIDER_UNAVAILABLE · OPENCODE_UNAVAILABLE · CONFIGURATION_FAILED · WORKER_FAILED · CONDUCTOR_COMMUNICATION_FAILED`. `start()`'s `err` is no longer discarded. A **port-conflict pre-check runs before spawn** and yields `FAILED(PORT_UNAVAILABLE)` naming the owning pid — never `TIMEOUT`. Tests `test_failure_classes` and `test_port_conflict_is_its_own_class` fail-before, pass-after. Artifact `evidence/hardening/h18-failure-classes.txt` lists every class **with the induced condition that produced it** — a class listed without a reproduction is not proven. This vocabulary is reused verbatim at G85. |
| G18 | Browser lifecycle bounded | The per-module handle returned by `window.open` is retained, reused on a second Open, and closed when that module leaves `READY`/`EXTERNAL`. **No process kill, no `taskkill`, nothing touching a browser the shell did not open.** `evidence/cpm1/8b/browser-lifecycle.txt` + a test asserting the handle map's transitions. |
| G19 | Gate 8b | Ledger `"8b"` `CANDIDATE`; suite `OK` count ≥ 122; `BUILD-MANIFEST.txt` regenerated and equal to live hashes; `evidence/cpm1/linecount-a.txt` shows `shell/**` within cap. |

### Band 3 · Session container and model selection — R-03 · **Gate 8c**

| # | Goal | TRUE when |
|---|---|---|
| G20 | Container without process | Creating a terminal/workspace slot spawns **no PTY**. The new session is `EMPTY`, backend `none`, model reference null, `pid` null. The implicit PowerShell fallback at the PTY boundary (`apps/desktop/main.js:474-491`) is removed as a default. `test_new_session_spawns_no_process` fails-before against the current default, passes-after. `evidence/cpm1/8c/empty-session.json` captures the record verbatim. |
| G21 ⚑ | Selection precedes initialization | The operator selects Execution Type from `{Local Model, API Model, OpenCode, PowerShell}` while the session is `EMPTY`/`CONFIGURING` — **with no prior `exit`, no prior process, and no refusal referencing a live session**. Model selection is offered only for backends that take one. `evidence/cpm1/8c/selection-flow.txt` records Create → Select → Initialize → Use with timestamps and the session record after each transition. |
| G22 | Replacement is governed, not refused | Changing backend or model on a session past `STARTING` presents an explicit terminate-and-reinitialize affordance and performs it on confirmation. The string *"already holds a live session — close it before launching another model into it"* no longer reaches the operator as the outcome of an ordinary selection, and `grep` finds it in no product path. A running session is still never killed by an unconfirmed click. `test_governed_replacement` covers both branches. |
| G23 | PowerShell is an option, not a state | `backend = powershell` is reachable only by explicit selection, carries a null model reference, and is labelled as an execution type. `evidence/cpm1/8c/powershell-not-default.txt`: grep-proof that no code path spawns a shell for a session whose backend was not explicitly set to `powershell`. |
| G24 | Gate 8c | Ledger `"8c"` `CANDIDATE`; SOW suite green (`evidence/cpm1/8c/sow-suite.txt` ends `OK`); `modules/sow/apps/desktop/**` within cap; regression per §8. |

### Band 4 · Conductor operator channel — R-04 · **Gate 8d**

| # | Goal | TRUE when |
|---|---|---|
| G25 ⚑ | A persistent typing surface exists | The SOW workspace carries a persistent, always-visible Conductor conversation surface: a text input **carrying no `disabled` attribute**, a submit affordance, and a transcript retaining prior turns across pane operations. The transcript is the primary content, not a caption on a status panel. `evidence/cpm1/8d/conductor-dom.txt` from a headless `--dump-dom` asserts the enabled input, the submit control, and **≥ 2 retained turns with distinct timestamps**. A fails-before capture against the current renderer (which has no input element at all) is required. |
| G26 ⚑ | Round-trip: human → Conductor → human | `evidence/cpm1/8d/conductor-roundtrip.txt`: a directive typed into the surface; the Conductor's response returned into the transcript; a follow-up in the same thread demonstrably carrying prior context; and an interrupt or redirect exercised, or recorded `UNSUPPORTED(<reason>)`. The Conductor leg runs on a **local** model — no spend is authorized. A Conductor communication failure surfaces as `CONDUCTOR_COMMUNICATION_FAILED` (G17), not as silence. |
| G27 | Gate 8d | Ledger `"8d"` `CANDIDATE` with the round-trip artifact hashed. |

### Band 5 · Conductor ↔ worker control plane — R-05, R-06 · **Gate 8e**

| # | Goal | TRUE when |
|---|---|---|
| G28 | Machine-readable worker registry | One projection exposes, for every active session: `session_id` · assigned model (`provider_id` + `model_id`, or explicit null) · execution backend · current state · task state · communication endpoint/channel · **`created_utc`** · error state. `created_utc` is the known projection gap (`control/operational-state.js:36-66`) and must now be projected. `evidence/cpm1/8e/worker-registry.json` dumps it verbatim with **≥ 2 live workers**; a test asserts every field non-absent for each. |
| G29 ⚑ | Conductor → worker delivery | `evidence/cpm1/8e/directive-delivery.txt`: a task issued by the Conductor arriving at a named worker — task id, target `session_id`, delivery mechanism, and the worker's own record showing the task bound to it. Ownership is tracked, not inferred. |
| G30 ⚑ | Worker → Conductor return and synthesis | The same chain shows the result returning to the Conductor, the Conductor reporting it to the operator in the G25 transcript, and — with **two workers on different models** — a consolidated synthesis naming both sources. |
| G31 | Failure is identified, not dropped | `evidence/cpm1/8e/worker-failure.txt`: a deliberately failed worker identified as failed by the Conductor. The mock-first dispatch feed (`conductor_dispatch.py:11-20,63-69`, `LIVE_WORKERS_OWED`) either renders live data or is **visibly labelled as mock in the UI**. A mock rendered as live is `FAKE_STATE`. |
| G32 | Gate 8e | Ledger `"8e"` `CANDIDATE`; the note states plainly which legs ran live and which were `NOT_RUN`, with reasons. |

### Band 6 · OpenCode execution backend — R-07, R-08 · **Gate 8f**

| # | Goal | TRUE when |
|---|---|---|
| G33 | Presence is a discovered fact | `evidence/cpm1/8f/opencode-detect.txt` records the actual result of the host's detection path (`shutil.which("opencode")` / `opencode.ps1`) and, if present, `opencode --version`. **Absent → G34–G36 are satisfied by truthful `NOT_RUN(OPENCODE_UNAVAILABLE)` records plus `FAILED(OPENCODE_UNAVAILABLE)` surfaced through G17**, and Gate 8f is submitted with that limitation stated. Fabricating availability is session-ending. |
| G34 ⚑ | Direct Sovereign access | An OpenCode-backed session is reachable from the Sovereign surface through an **integrated** terminal/workspace panel — not a popup-window architecture. One agentic file operation is performed in a scratch directory under the workspace. `evidence/cpm1/8f/opencode-direct.txt`: command, working directory, operation, and the resulting file's before/after hash. |
| G35 ⚑ | OpenCode as a worker backend, delegated to | `OpenCode` appears in the Execution Type list and instantiates a real OpenCode-backed session — **not** an entry in a model list (S-10). Its worker record shows `backend: opencode` with the model reference separate and populated by a compatible model. The Conductor sends it a bounded agentic task through the same worker-control abstraction other backends use, and the result returns. Full chain in `evidence/cpm1/8f/opencode-delegation.txt`. |
| G36 | No model/backend confusion | `evidence/cpm1/8f/backend-not-model.txt`: grep-proof that `opencode` appears in no model enumeration, no `model_id` field, and no model-registry row. **Zero new `if backend == …` / `if model == …` branches** in dispatch, selection, or rendering paths — behaviour differences ride on backend descriptors. Any such branch is `SPECIAL_CASE_ACCUMULATION`. |
| G37 | Gate 8f | Ledger `"8f"` `CANDIDATE`. |

### Band 7 · Canonical registry — authored artifact-aware and context-aware (O-1) · **Gate 8g**

*This band is where the merge pays. The registry is written once, in its final shape. Band 16 populates it; it does not migrate it.*

| # | Goal | TRUE when |
|---|---|---|
| G38 | One canonical registry | A single registry serves the Conductor selector and every worker selector. The hard-coded model/provider lists inventoried at G9 are either consumed by it as declared seed data with `discovered_by` recorded, or removed. `evidence/cpm1/8g/registry-dump.json` is the registry's own output; `evidence/cpm1/8g/duplication-audit.txt` gives each inventoried list its disposition. **No UI component holds its own model list.** |
| G39 | **Final shape from the start** | Registry rows carry, from this band onward and without later migration: `model_id · family · parameter_count · active_parameter_count · provider · runtime · locality · capabilities · advertised_context · validated_context · production_context · validation_evidence · artifacts[] · speculative_decoding{} · promotion_state · discovered_by · availability · health`. `artifacts[]` may be empty here — the **field exists** so Band 16 fills it rather than restructures. `validated_context` / `production_context` may be null here — Band 17 measures them. A field the host cannot report is `unknown`, never guessed. |
| G40 | Metadata prevents incompatible selection | A selection the compatibility relation forbids is refused **with a stated reason before any process is spawned**. `test_incompatible_selection_refused` fails-before, passes-after. |
| G41 | Discovery is live and honest | `evidence/cpm1/8g/discovery.txt` records actual command output per source: local runtime inventory, `ollama list` (or `GET /api/tags`), each configured provider CLI's own `models` enumeration including `grok_build`, and OpenCode detection. Per S-6, nothing is added that a command did not return. An entry without a discovery artifact is `FABRICATED_AVAILABILITY`. |
| G42 | Grok reachability recorded either way | `evidence/cpm1/8g/grok-status.txt`: per enumerated Grok model, whether a session was established or the exact failure, citing the three prior `SPAWNING`/`pid: null` records as prior state. `NOT_RUN(NO_SPEND_AUTHORIZATION)` is a valid and expected outcome — `grok_build` is a frontier provider. |
| G43 | Gate 8g | Ledger `"8g"` `CANDIDATE`, note stating exactly which providers and models the host actually exposed. |

### Band 8 · Distillery runtime and UI — R-11, R-12 · **Gate 8h**

| # | Goal | TRUE when |
|---|---|---|
| G44 | Installed under Option A | `modules/distillery/` seeded from `D:\Product Software\SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e\`, with `INSTALL-PROVENANCE.json` and a manifest. `D:\Sovereign Distillery\` byte-identical to its G4 baseline — read for design intent, never a copy source or edit target. The existing architecture and purpose are **not** redesigned, only made operable. |
| G45 | Runtime, entry point, lifecycle, health (O-4) | `shell/modules/distillery.json` declares a real `launch` (absolute `.exe` argv; never `.cmd`/`.bat`/`shell=True`), `readiness` `http`, `identity` `http_json`, `stop` `job_object`, and `runtime_writes`. `state_class` is no longer `not_started`. Start → `READY` on an observed health response; Stop → pid gone, port free. Local-first: the readiness target is loopback, so no network egress is required to reach `READY`. `evidence/cpm1/8h/distillery-start.txt`, `distillery-stop.txt`. |
| G46 ⚑ | UI is a console, not a second OS | The surface exposes Runtime Status · Student Model · Teacher/Source Models · Pipeline State · Current Stage · Queue · Hardware/Compute Status · Start/Pause/Stop · Logs/Evidence · Artifacts/Outputs. Advanced configuration is secondary or absent. Sovereign theme tokens only — **no new hex** outside `THEME-BASELINE-v3.md`. No bare `D:/…` path in any `href`. `evidence/cpm1/8h/distillery-dom.txt` asserts each named surface. |
| G47 | **No compute on open** | Starting the runtime and opening the UI initiates **no training, distillation, merge, or other expensive compute**. `evidence/cpm1/8h/no-autocompute.txt`: process/GPU/CPU observation across start → open → idle → stop showing no training process spawned and no artifact written to the outputs path, plus a test asserting the start path invokes no pipeline entry point. A single training step begun automatically is `AUTO_COMPUTE`. |
| G48 | Contrast holds | Any text pairing introduced holds ≥ 4.5:1 in both themes, proven through the existing H-16 machinery. `--input` may be defined in the light block **only if** an input surface enters `shell/static`, capped at 1 line, with a contrast proof. |
| G49 | Gate 8h | Ledger `"8h"` `CANDIDATE`. |

### Band 9 · Token Center integration — R-13, R-14 · **Gate 8i**

*S-9 applies immediately before this band: free :8765 by pid, or record that it was already free.*

| # | Goal | TRUE when |
|---|---|---|
| G50 | Port freed and recorded | `evidence/cpm1/8i/external-instance-stopped.txt`: the pid, its command line, and the port state before and after. Nothing executed from inside `D:\Token Piggy Bank\`. The Gate 8i note states the operator owns restarting whichever copy they want. |
| G51 | Installed under Option A | `modules/tokencenter/` is a copy of `D:\Token Piggy Bank\` **excluding `data/` and `.git/`**, with provenance and manifest. The original is byte-identical to its G4 baseline (with S-7's `data/**` exclusion). In the **copy only**: the bind host is pinned to loopback with no CLI override, and `POST /api/refresh` carries the Origin/Host/CSRF guard set the shell already enforces. Tests cover both. |
| G52 | A module like any other (O-4) | `shell/modules/tokencenter.json`: `readiness` `http` → `http://127.0.0.1:8765/healthz` expecting 200, `identity` `http_json` requiring the keys `/healthz` actually returns, `open` → its own URL, `stop` `job_object`. Starts, reaches `READY` on an observed health response, stops cleanly. `evidence/cpm1/8i/tokencenter-start.txt`, `-stop.txt`. |
| G53 ⚑ | Central in the main control surface (O-3) | The main UI places the Token Center centrally with the four modules around it — SOVEREIGN, Orchestration Workspace, Debate Table, Distillery. Conceptual layout, not literal geometry; collapses to one column below the existing 720 px breakpoint. **Sovereign tokens only** — the Token Center's own `--gold #f3b43f` / `--cyan #79e5f4` palette does not enter `shell/static`; its standalone page keeps its own identity. This edit anticipates Band 18's resource panel: lay the grid out once. `evidence/cpm1/8i/main-ui-dom.txt` + `main-ui-dark.png` and `main-ui-light.png`, both non-blank. |
| G54 | It reflects real backend state | The panel renders values read live from the module's own `GET /api/summary`, with every key path it reads asserted to resolve in the live payload (H-15 pattern) → `evidence/hardening/h19-tokencenter-contract.txt`. Displayed: configured/observed providers, model availability, local vs remote, usage/token information, collector health, `collected_at` staleness. **When the module is not `READY` the panel says so** rather than showing stale numbers as current. |
| G55 | No credential surface is created | `evidence/cpm1/8i/no-credentials.txt`: grep of `modules/tokencenter/**` and `shell/**` proving no credential store, key-entry field, secret value, or provider authentication was introduced. Per S-2 this requirement is satisfied by **absence**; the gate note records that endpoint/authentication management is out of scope. |
| G56 | Gate 8i | Ledger `"8i"` `CANDIDATE`. |

### Band 10 · Package-A acceptance — scenario A–H · **Gate 8j**

*One recorded run, in order, in one session, against the real system. Not eight isolated button tests.*

| # | Goal | TRUE when |
|---|---|---|
| G57 ⚑ | Scenario recorded | `evidence/cpm1/8j/`: `state-after-coldstart.json` (A — Debate and Distillery consume no runtime) · `stepB-debate.txt` (select → runtime starts → health observed → browser opens → Stop → runtime stops, port free, shell-opened surface closes; any external :8700 owner `EXTERNAL` and untouched) · `stepC-workspace.txt` (create a worker terminal — **the operator is not in PowerShell** — select a local model, it initializes, prompt, response, with the session record at each transition) · `stepD-conductor.txt` (message the Conductor; response; multiple workers; directive to one; result returns; Conductor reports and synthesizes) · `stepE-opencode.txt` (Human → Conductor → OpenCode → execution → result → Conductor → Human, or `NOT_RUN(OPENCODE_UNAVAILABLE)` with the G33 artifact) · `stepF-models.txt` (dynamic local discovery; Grok where actually configured; grep-proof no dispatch/selection/rendering path branches on a model family) · `stepG-distillery.txt` (start → runtime → UI → status → **no training begun** → stop → clean termination) · `stepH-tokencenter.txt` (integrated centrally, real provider/model state, no secret rendered). |
| G58 | The proof chain holds | `evidence/cpm1/8j/proof-chain.txt`: `Human → Conductor → {local LLM · API model · OpenCode} → result → Conductor → Human`, each leg exercised or `NOT_RUN(<reason>)`. The API-model leg is `NOT_RUN(NO_SPEND_AUTHORIZATION)`. |
| G59 | Regression clean | Suite `OK`, count ≥ 122; `BUILD-MANIFEST.txt` regenerated and equal; `app.css` `:root` unchanged from v3. |
| G60 | Envelope honoured | `evidence/cpm1/linecount-a.txt` shows per-area and absolute totals within the Package-A caps, computed by `difflib` against `evidence/cpm1/before-a/`. |
| G61 | Closeout | Every builder-started process stopped through its own path; nothing under `modules\*`; ports as found at G3, with any pre-existing external owner documented. |
| G62 | Gate 8j | Ledger `"8j"` `CANDIDATE`, listing every 8j artifact plus standing evidence. |
| G63 ⚑ | Part A of the report | `docs/CP-M1-REPORT.md` Part A exists: per requirement R-01…R-15 — **Requirement ID · Implementation location · Files changed · Behavior before · Behavior after · Validation performed · Result · Remaining limitations.** Every substantive sentence tagged `FACT[path]` / `ASSUMPTION` / `INTERPRETATION` / `RECOMMENDATION`. |

### Band 11 · Handoff

| # | Goal | TRUE when |
|---|---|---|
| G64 | Package-B baseline | `evidence/cpm1/before-b/` — copies and hashes of every file the Package-B caps permit touching, **as Bands 1–10 left it**. This is the sole baseline for every Package-B changed-line measurement. Measuring against `before-a/` would attribute Package A's spend to Package B. |
| G65 | Suite floor re-taken | `evidence/cpm1/test-run-handoff.txt` ends `OK`; its count becomes Package B's floor — not 122. |
| G66 | Protected spot-check | The five roots re-verified against G4 (with S-7's exclusion) → `evidence/cpm1/handoff-manifests.txt`, all "no differences". |
| G67 | Handoff recorded | `evidence/cpm1/handoff.txt` records G64–G66 with hashes and UTC. Band 12 does not begin before it exists. |

### Band 12 · Pinned llama.cpp beside Ollama · **Gate 9a**

| # | Goal | TRUE when |
|---|---|---|
| G68 | Pinned and provenanced | `runtime/llama.cpp/versions/<pinned>/` populated; `runtime/llama.cpp/current` resolves to it. `evidence/cpm1/9a/pin.txt`: release identifier, origin, SHA-256, binary inventory, CUDA backend identifier, build date. **No `latest` dependency.** Ollama unmodified; global PATH unchanged; no boot autostart; not registered as a production runtime. |
| G69 | Test artifacts staged | GGUF acquired **read-only from the Ollama blob store** — offline, no download, provenance traced to the originating tag — and copied into `runtime/llama.cpp/test-models/` with source tag, blob digest and destination sha256 matching. Ollama's store is never moved, renamed, or written. Unreadable store → STOP `GGUF_SOURCE_UNAVAILABLE`; an external download requires separate operator authorization with origin, size and SHA-256 recorded. |
| G70 | A1–A4 | `--version` for cli and server with exit status · **CPU-only** load/prompt/generate/clean-exit on a small model · **CUDA** run recording GPU detected, layers offloaded, VRAM before/after · **partial offload** explicitly exercised (S-5: 8 GiB host) recording layer placement, RAM, VRAM, load time, TTFT, prompt rate, generation rate. |
| G71 | A5–A8 | Single-model `llama-server`: health, model exposure, request, response, shutdown · OpenAI-compatible `POST /v1/chat/completions` non-streaming **and** streaming · cancellation of a long generation with the server still healthy and the model still usable · clean shutdown, port released, process gone, no orphan. |
| G72 | **Router mode asserted; the shell owns the process** (O-4) | `evidence/cpm1/9a/router-support.txt` positively demonstrates the pinned build enters router mode with no `-m` and answers `GET /models`, recording the flags **observed**. Absent → STOP `ROUTER_MODE_UNAVAILABLE`; Band 13 not attempted. `shell/modules/llamacpp.json` declares `readiness` `http` → `http://127.0.0.1:5183/models`, `identity` `http_json`, `stop` `job_object`, `runtime_writes` scoped to `runtime/llama.cpp/logs`, `open` `none`. Started and stopped **only** through the shell's routes; grep-proof that no adapter, planner, or backend spawns or kills it. Port **5183**, never `llama-server`'s default 8080. |
| G73 | Ollama unharmed | Ollama inference works after every step; version and model count equal G3. |
| G74 | Gate 9a | Ledger `"9a"` `CANDIDATE`; suite green; manifests clean. |

### Band 13 · Router mode as state and actuation source · **Gate 9b**

*Validation setting for this band only: `--models-max 1`. It does not survive into Band 15 (S-3).*

| # | Goal | TRUE when |
|---|---|---|
| G75 | Initial state | Router started with neither `MODEL_A` nor `MODEL_B` loaded; `GET /models` distinguishes states equivalent to `loaded` / `loading` / `unloaded`, recorded verbatim. |
| G76 | On-demand load | `MODEL_A` requested; `unloaded → loading → loaded` observed; wall-clock load time, VRAM delta, RAM delta recorded. |
| G77 | Explicit unload | `loaded → unloaded` observed; **VRAM actually returns**, not merely the state flag. |
| G78 | LRU | At `models-max 1`, `MODEL_A` loaded then `MODEL_B` requested; `MODEL_A` evicted and `MODEL_B` loaded with no manual intervention. |
| G79 | Failure behaviour | Invalid identifier, corrupt artifact and unsupported artifact each produce a clear failure; the router survives; an already-loaded model remains coherent. |
| G80 | Gate 9b | Ledger `"9b"` `CANDIDATE`. **No Sovereign integration exists yet.** |

### Band 14 · Widen the existing Backend Protocol · **Gate 9c**

| # | Goal | TRUE when |
|---|---|---|
| G81 | Contract widened, not replaced | The existing `Backend` Protocol exposes `list_models · load_model · unload_model · generate · cancel · health · capabilities`. **No `metrics()` yet** — it arrives at G109 where a consumer exists. No new parallel abstraction; `evidence/cpm1/9c/no-replacement.txt` grep-proof. |
| G82 | Ollama adapter conforms honestly | Where a capability is not natively available it returns an **explicit unsupported result with a reason** — never a faked success, never a silent no-op. A test asserts each unsupported path returns `supported: false` with a non-empty reason. |
| G83 | `LlamaCppBackend` added | Beside `OllamaBackend`. Translates existing internal request semantics to llama.cpp and **contains no routing policy**. Runtime, model and artifact identity stay separate — never `model: "llama.cpp/qwen3.8-q4"`. Grep-proof. |
| G84 ⚑ | Parity matrix | `evidence/cpm1/9c/parity-matrix.txt`: health · list models · generate · stream · cancel · load · unload · capabilities · error mapping · timeout, run against both backends, each cell `PASS` / `UNSUPPORTED(reason)` / `FAIL`. |
| G85 | Errors normalized to the G17 vocabulary (O-2) | Runtime errors from both backends map into the ten classes defined at G17 — not a second taxonomy. `evidence/cpm1/9c/error-mapping.txt` shows each backend's native failure and the class it becomes. |
| G86 | **Ollama remains the default** | `evidence/cpm1/9c/default-runtime.txt` proves the production path still resolves to Ollama. No promotion occurs. Ledger `"9c"` `CANDIDATE`; full regression. |

### Band 15 · Connect runtime residency to the existing planner · **Gate 9d**

| # | Goal | TRUE when |
|---|---|---|
| G87 | **Budget authority chosen and recorded** (S-4) | `evidence/cpm1/9d/vram-authority.txt` records which of (a) real VRAM reader or (b) exclusive residency was adopted, why, and how it is enforced. A load scheduled without it is `VRAM_BUDGET_UNACCOUNTED`. |
| G88 | **Router demoted to mechanism** (S-3) | Router runs `--no-models-autoload` with `--models-max` strictly above the planner's concurrency bound. `evidence/cpm1/9d/single-evictor.txt` records both numbers and the reasoning. A Band 13 `--models-max 1` surviving here is `DUAL_EVICTOR_CONFLICT`. |
| G89 | Mapping respects existing semantics | Router states map into the **existing** planner vocabulary (`NOT_LOADED · LOADING · RESIDENT · AWAITING_EVICTION · QUEUED · EVICTED`). No new canonical state is created because llama.cpp uses a different word. `evidence/cpm1/9d/state-map.txt`. |
| G90 | Layered actuation | The planner requests load/unload **through the backend contract** and never spawns or kills a llama.cpp process. Grep-proof that no process-control call exists in the planner. |
| G91 | Round-trip proved | `evidence/cpm1/9d/roundtrip.txt`: planner sees unloaded → requests load → router loads → planner reflects `RESIDENT`; planner selects eviction → runtime unloads → planner reflects `EVICTED`/`NOT_LOADED`. VRAM observed at each step. |
| G92 | **No mid-generation eviction, from either side** | Two tests, both fails-before against a deliberately mis-configured router: (i) the planner never evicts a generating model; (ii) **the router performs no unrequested transition** while the planner's bound is saturated and a generation is active. |
| G93 | Fail closed · Gate 9d | Router unavailable · stale response · load timeout · unload timeout · eviction requested during active generation — each a defined, recorded, non-corrupting outcome. Ledger `"9d"` `CANDIDATE`. |

### Band 16 · Populate artifacts, manifest, ingestion (O-1) · **Gate 9e**

*The registry already has the right shape from G39. This band fills it — it does not migrate it.*

| # | Goal | TRUE when |
|---|---|---|
| G94 | Artifacts populated | `artifacts[]` is filled for every registry row from live inventory. One model owns many artifacts, each retaining `format · quantization · runtime · path · sha256 · validated`. **One tag = one artifact, always.** `model_id` is assigned only where the tag unambiguously denotes a known base model; otherwise `model_id = artifact_id` with `needs_operator_review: true`. **No heuristic name-matching, no family inference — a fine-tune is a different logical model.** `evidence/cpm1/9e/population.txt` lists every live tag with its disposition. |
| G95 | Legacy references resolve | `legacy_alias` / `migration_source` / `migration_version` retained where a prior identifier existed; a test resolves every pre-Band-16 identifier. Nothing is destroyed. |
| G96 | Deployment manifest schema | Canonical schema with at minimum `artifact_id · model_id · source_identity · source_hash · artifact_hash · format · quantization · runtime_compatibility · creation_tool · creation_tool_version · creation_timestamp · validated_context · status`. |
| G97 | Ingestion, fail-closed | Manifest → validation → registry → `CANDIDATE`. **No automatic production promotion.** Rejects on missing artifact hash, hash mismatch, unknown `model_id`, invalid runtime, invalid format, invalid schema, duplicate `artifact_id` with conflicting hash, unsupported schema version. **Never partially ingests.** Each rejection has a fails-before artifact. |
| G98 | Three axes stay separate (S-12) | `evidence/cpm1/9e/three-axes.txt` states, and a test asserts, that promotion state is orthogonal to node/process state and to VRAM residency. |
| G99 | Gate 9e | Ledger `"9e"` `CANDIDATE`. |

### Band 17 · Context truthfulness · **Gate 9f**

| # | Goal | TRUE when |
|---|---|---|
| G100 | Three values distinguished | `advertised_context`, `validated_context`, `production_context`, `validation_evidence` — the fields exist from G39; this band gives them measured values. A tier label (`STANDARD`/`DEEP`/`EXTENDED`/`ULTRA`/`EXPERIMENTAL`) **never implies support**; the validation record governs eligibility. |
| G101 | Bounded measurement | At most **three** models (one 7–8B, one 12B, one 27B for the offload case) across four tiers: short baseline, medium, current declared production, next candidate. A per-run time budget is declared in advance. Never a 32K→256K jump. |
| G102 | Variables recorded | Per combination: context requested · context successfully initialized · prompt tokens processed · TTFT · prompt tok/s · generation tok/s · VRAM · RAM · KV-cache footprint · retrieval correctness · instruction retention · structured-output correctness · tool-call correctness where applicable · runtime errors · OOM. **`NOT_MEASURED(TIME_BUDGET)` is a valid outcome; an estimate is not.** |
| G103 | **Demotion does not strand requests** | Before writing any value lower than the current declared one, dry-run the resolver over recorded historical capability requests under both values; `evidence/cpm1/9f/demotion-impact.txt` lists every request class that would newly fail. Applying it requires **explicit operator acceptance quoted verbatim**. Unaccepted → STOP `CONTEXT_DEMOTION_STRANDS_REQUESTS`. |
| G104 | Resolver consumes truth · Gate 9f | After acceptance, `min_context` routing reads the validated/production value, not the advertised one. A model advertising 256K but validated to 64K advertises 64K to routing. Ledger `"9f"` `CANDIDATE`, note stating what was measured and what was `NOT_MEASURED`. |

### Band 18 · Fallback visibility and resource accounting · **Gate 9g**

| # | Goal | TRUE when |
|---|---|---|
| G105 | Fallback via the existing resolver | The ordered candidate list comes from the **existing descriptor-based resolver**. No separate role router is built; grep-proof of no new routing path. |
| G106 | **Visible, never silent** | Every fallback records original candidate · failure reason · replacement candidate · runtime · artifact · timestamp · task/request id, and surfaces a fallback indication where a user-facing state exists. A silent substitution is `FAKE_STATE`. |
| G107 | **Infrastructure ≠ reasoning** | Fallback triggers only on runtime unavailable, model load failure, OOM, timeout, backend health failure, artifact unavailable. A test asserts a bad answer, a failed reasoning step and an incorrect tool decision **do not** trigger fallback. |
| G108 | Resource accounting in existing surfaces (O-3) | Runtime · model · artifact · load state · VRAM used · system RAM used · context configured · KV-cache usage where available · `node = local host`, surfaced through the Band 9 layout. **No parallel UI application.** |
| G109 | Logging extends, never bypasses · `metrics()` lands | Existing `LogRing`, redaction surfaces and token accounting extended with `runtime · model_id · artifact_id · request_id · load_state · fallback_reason`; a test proves the new fields pass through redaction. A parallel logging path that bypasses redaction is a STOP. `metrics()` is added now, shaped by what G108 and this goal actually read. |
| G110 | Gate 9g | Ledger `"9g"` `CANDIDATE`. |

### Band 19 · Forward-compatibility metadata · **Gate 9h**

| # | Goal | TRUE when |
|---|---|---|
| G111 | Speculative metadata only | The `speculative_decoding{}` field from G39 carries `{supported, method, draft_model_id, draft_artifact_id, validated, evidence}`, defaulting false/null, accepting `MTP` / `DFlash` / `draft model` as future methods. |
| G112 | **No speculative execution** | Grep-proof: no target+draft simultaneous residency, no MTP execution, no DFlash execution, no speculative scheduler. S-5 — the 8 GiB host makes it inappropriate. |
| G113 | NVFP4 describable | An artifact may declare format/quantization `NVFP4`, hardware affinity Blackwell, correctness status, validation status, upstream reference. Creates no requirement to deploy. |
| G114 | Research lane, isolated · correctness gate holds | If run: known-source artifact with verified hash · pinned-build support verified · correctness, tool-use, repetition/looping and structured-output tests · VRAM, TTFT, prompt and generation throughput · compared against a Q4_K_M baseline. **No NVFP4 artifact reaches `CANDIDATE`** while the upstream GGML correctness question is unresolved or local evidence shows unexplained divergence — permitted state `RESEARCH` only. Not run is a valid recorded outcome. |
| G115 | Gate 9h | Ledger `"9h"` `CANDIDATE`. |

### Band 20 · Final regression, adversarial review, closeout · **Gate 9j**

| # | Goal | TRUE when |
|---|---|---|
| G116 | Regression clean | Capability descriptor validation · vendor-blind resolution · locality enforcement · **Ollama inference** · OpenCode harness environment filtering · residency-planner invariants · shell lifecycle contract · registry loading · debate participant descriptor rules · logging redaction — all unchanged and re-proven. Suite `OK`, count ≥ the G65 floor. `BUILD-MANIFEST.txt` equal to live hashes. `app.css` `:root` unchanged from v3. |
| G117 | Protected roots + watch window close (O-5, O-6) | All five roots re-verified against G4 with S-7's exclusion → `evidence/cpm1/9j/protected-manifests-clean.txt`, five "no differences". fs-watch artifact `events: 0`, window bracketing **G5 → here**. |
| G118 | Rollback proved | `evidence/cpm1/9j/rollback.txt` **demonstrates** — not asserts — that disabling the candidate backend and restoring the previous configuration leaves the Ollama path fully operational. |
| G119 ⚑ | Adversarial review | `evidence/cpm1/9j/adversarial-review.txt` searches for and finds **zero** of: duplicate architecture · new hardcoded model names · new vendor routing · silent fallback · fake residency state · fake context claims · new lifecycle states · remote-host leakage · provider-spend leakage · parallel logging bypass · unreviewed schema drift · Ollama regression · any goal marked TRUE whose artifact a human would not accept. Any instance blocks closure. |
| G120 | Diff classification | Every changed file classified `REQUIRED` / `SUPPORTING` / `EVIDENCE` / `UNEXPECTED`. **`UNEXPECTED` must equal zero.** |
| G121 | Envelopes honoured | `evidence/cpm1/linecount-a.txt` and `linecount-b.txt` show per-area and absolute totals within their own caps, computed against `before-a/` and `before-b/` respectively. Never one file, never one budget. |
| G122 | Final evidence manifest | `evidence/cpm1/9j/FINAL-EVIDENCE-MANIFEST.json`: baseline commit · final commit · modified files · schema changes · tests executed · **tests passed, tests failed** · runtime versions · artifact hashes · known limitations · deferred items · operator decisions still open. **No test omitted because it failed.** |
| G123 | Closeout | Every builder-started process stopped through its own path — llama.cpp through the shell's Stop route, never `taskkill`. Nothing under `runtime\` or `modules\`; **5183 free**; 5175/8700/8765/5180 as found at G3, with any pre-existing external owner documented. No debugging left behind as finished work. |
| G124 ⚑ | Gate 9j + Part B of the report | Ledger `"9j"` `CANDIDATE`. `docs/CP-M1-REPORT.md` Part B complete: per band — implementation location · files changed · behaviour before · behaviour after · validation performed · result · remaining limitations; the parity matrix; what was measured and what was not; §9's deferred blocks verbatim; carried defects C-1…C-7 with dispositions. Every substantive sentence tagged. Ends with the §10 claim line. Gates 0–7b byte-identical. **No gate asserts llama.cpp as production default.** |

---

## 6. The loop

```
i = 0
while i < 220:
    i += 1
    state = goalcheck()                  # reads disk only; writes evidence/cpm1/goalcheck-<i>.txt
    if all TRUE: break
    g = first failing goal in ladder order
    act(g)                               # the ONE smallest authorized action for g
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, goal, action, changed_lines, flipped, notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS
submit: gates 8a-8j + 9a-9j, docs/CP-M1-REPORT.md, claim line
```

Every mutation is preceded by a `before-a/` or `before-b/` capture of the file and followed by a `linecount-a.txt` or `linecount-b.txt` append — **to its own package's file**. Any transient failure gets exactly **one** retry; the second is logged and counts toward no-progress.

**Single writer.** Nothing else writes to this workspace while the loop runs. A file you did not write changing under you is `CONCURRENT_WRITER` — stop and name it.

---

## 7. Oracle contract

`evidence/cpm1/tools/goalcheck.py` — `py -3.12`, stdlib only, read-only against the workspace, writing only its own output. Seed it from `evidence/cp01/tools/goalcheck.py`, whose predicates are verified; do not rewrite from scratch.

Per goal it emits exactly one line: `G<n>: TRUE|FALSE  <reason>`, followed by `read: <path>[, <path>…]` naming **every file it opened to decide that goal this iteration**. A goal reported TRUE with an empty `read:` list is a malformed oracle and a STOP.

It never reports TRUE on the strength of anything it did not read from disk this iteration. It parses UTF-8 with BOM tolerance. It decodes PNGs far enough to reject a blank render. If the oracle itself errors, repairing it is a permitted action logged as `goal: G-oracle`.

**The oracle is yours, and that is its limitation.** You author its predicates, so passing it is not evidence of anything except that the artifacts you chose exist and parse. Goals marked ⚑ are structural in the oracle and semantic in reality; write those artifacts for the human who will read them.

---

## 8. STOP conditions

`AGENTS.md` §13 in full · ADD-01 §8 · ADD-02 §6 · ADD-03 §6, plus:

`LOOP_NO_PROGRESS` · `LOOP_PRODUCT_DEFECT` · `BAND_ENVELOPE_VIOLATED` · `ENVELOPE_EXCEEDED` · `PREMISE_CONTRADICTED` · `FAKE_STATE` · `SPECIAL_CASE_ACCUMULATION` · `AUTO_COMPUTE` · `FABRICATED_AVAILABILITY` · `CONCURRENT_WRITER` · `INSTALL_REQUIRED` · `SPEND_REQUIRED` · `PROVIDER_SPEND_CONTRADICTION` · `PROTECTED_SOURCE_CHANGED` · `VRAM_BUDGET_UNACCOUNTED` · `DUAL_EVICTOR_CONFLICT` · `ROUTER_MODE_UNAVAILABLE` · `GGUF_SOURCE_UNAVAILABLE` · `CONTEXT_DEMOTION_STRANDS_REQUESTS` · `TIME_BUDGET_EXCEEDED` · `ARCHITECTURE_CONSTRAINT_UNSATISFIABLE` · iteration 220 reached.

A STOP writes `docs/STOP-REPORT-CP-M1.md` naming the band and goal it fired in, with the loop-ledger tail, the `FACT[...]` condition, the exact requirement or conflict, why proceeding would require interpretation, **2–3 bounded operator options**, and no unauthorized implementation. Then closes out per G123 and ends with the no-gate claim line.

**A STOP cannot be waved away by the builder.** Only operator authority alters scope after a STOP. Failing to continue beats unauthorized success.

---

## 9. What this loop may never do

Write `PASS` anywhere. Edit `AGENTS.md`, `CLAUDE.md`, the contract, any addendum, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, or `docs/DECISIONS.md`. Alter a reviewer-evaluated ledger entry. Touch a protected tree except read-only. Reorder the ladder or begin a later band to "save time". Pool the two changed-line budgets or measure one package against the other's baseline. Regenerate Band 0 evidence that G4 adopts. Redesign a working module because another framework is preferred. Rebuild anything in §2. Alter the Sovereign visual identity without a goal requiring it. Hard-code the system around today's models. Make cloud connectivity mandatory. Make OpenCode the only agentic backend. Represent OpenCode or llama.cpp as an LLM. Start Distillery compute automatically. Kill an unrelated browser or process. Create a `RUNNING` state without a health observation. Ship a placeholder control and call it integrated. Declare orchestration operational without an actual worker round-trip in evidence. Promote llama.cpp to production default. Re-interpret a goal so it passes — "close enough" is FALSE.

**Deferred, recorded at closure, not attempted here** (S-5):

```
DEFERRED_HARDWARE:          ExLlamaV3 · EXL3 · Unsloth training · GRPO ·
                            speculative execution · broad quantization generation ·
                            large-student Distillery training
DEFERRED_OPERATOR_DECISION: remote-machine routing · loopback sovereignty invariant repeal ·
                            >=24 GiB trainer designation · named-role display aliases ·
                            Token Center ownership after Band 9
RESEARCH_ONLY:              NVFP4
```

Deferred is not failed. Deferred is not complete. Deferred means deliberately outside this package's authority.

---

## 10. Exit

On every goal TRUE: `docs/CP-M1-REPORT.md` complete in both parts, then a final message carrying — iteration count · the goal ladder with the artifact and hash proving each · the R-01…R-15 evidence table · per-package per-area and absolute changed-line totals · the parity matrix · which legs ran live and which were `NOT_RUN` / `NOT_MEASURED` with reasons · the three deferred blocks · carried defects C-1…C-7 · remaining limitations. Ending with exactly:

```
BUILDER CLAIM: Gates 8a through 8j and 9a through 9j are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder, and llama.cpp is not promoted to production default by this package.
```

On any STOP, ending with exactly:

```
BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
```

Never reworded. "Passed", "complete", "done", or "✓" beside a gate number is a violation. Say **candidate**.

---

## 11. Governing principle

```
Human operator → Sovereign governance → Capability resolver → Model identity
    → Deployment artifact → Runtime backend → Physical hardware
```

Do not invert it. A runtime does not own the model. A model does not own the router. The router does not own Sovereign. A benchmark does not own production promotion. And an oracle you wrote does not own the truth — it reports what is on disk, and nothing more.
