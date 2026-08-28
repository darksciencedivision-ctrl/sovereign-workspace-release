# OX-ALPHA-DIRECTIVE-CP-01 — Sovereign Control-Plane Integration Loop, SWS-UI-001 v1.2 + ADD-01

| Field | Value |
|---|---|
| Contract | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2, unchanged. `AGENTS.md` binds in full. |
| Envelope | `docs/SWS-UI-001-v1.2-ADDENDUM-01.md` (ADD-01 v1.0). It defines what may be touched, the caps, the architectural constraints, and the two premise corrections. This directive defines what must become **true**. Where the two appear to conflict, ADD-01 governs and you report the conflict. |
| Authorization | The operator sentence in ADD-01 §9, logged verbatim with its UTC in `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation. Absent → STOP `PRECONDITION_UNSIGNED`. |
| Supersedes | Nothing. Gates 7a/7b remain `CANDIDATE` and untouched; the reviewer's verdict on them is independent of this work. |
| Loop state | `evidence/cp01/LOOP-LEDGER.jsonl`, append-only, one JSON line per iteration. A fresh session resumes by running the oracle and reading this file — never from memory of a prior session. |
| Oracle | `evidence/cp01/tools/goalcheck.py` — `py -3.12`, stdlib only, read-only against the workspace. Written once at G0. It is the loop's only judge of truth. |
| Product version | SWS-UI-001 v1.2 as promoted at Gate 6. This work does not bump the product version; it extends the control plane inside it. |

---

## 1. Operating principle

Verify, then act, then verify.

Every iteration: run the oracle against disk. Take the **single smallest authorized action** that flips the **first** failing goal. Run the oracle again. Append one ledger line. Nothing is done that a currently-failing goal does not require. No goal is ever marked done by recollection, by a passing test alone, or by the apparent completeness of an implementation — only by the oracle re-reading disk.

Goals are **strictly ordered**. G(n) is not acted on while G(n-1) is FALSE. The bands exist because the dependencies are real: you cannot prove a Conductor round-trip through a session container that still traps the operator in PowerShell, and you cannot prove a session container's state machine while the shell reports fake RUNNING states above it.

The loop ends in exactly one of two states: every goal TRUE (submit candidates, write the report, emit the claim line) or a STOP report. There is no third exit. Do not end your turn at a band boundary. If the harness ends it anyway, resume from the first failing goal without re-deriving the plan.

**Surgical, not architectural.** Prefer the smallest correction that makes a goal true inside the existing architecture. The SOW control plane already has a worker registry, an MCP tool surface, a governed spawn path, and an OpenCode harness. You are wiring, proving, and correcting those — not replacing them. A rewrite is a defect in this loop, not a strategy.

---

## 2. Requirement traceability — every R-ID, its classification, its gate

Classification is the reviewer's read of the reconnaissance in ADD-01 §2. You re-establish each at Gate 8a from disk. **A classification that disk contradicts is `PREMISE_CONTRADICTED` — record the new fact and STOP; do not pick the reading that lets work continue.**

| R | Requirement | Classification on entry | Gate |
|---|---|---|---|
| R-01 | Debate Table does not autostart | **Already true, unproven.** No autostart exists anywhere in the shell. The real defect is legibility: `EXTERNAL` is not visibly distinct from "we started this". | 8b |
| R-02 | Module runtime / browser lifecycle corrected | **Implemented but defective.** SOW readiness is a 1-second liveness check; browser handles are discarded; nothing closes on stop. | 8b |
| R-03 | Terminal / model-selector defect corrected | **Implemented but defective.** PTY defaults to PowerShell; model selection is refused while a live session exists. | 8c |
| R-04 | Human can communicate with the Conductor | **Absent.** No text input surface exists in the SOW renderer or on any route. | 8d |
| R-05 | Conductor can communicate with workers | **Implemented, unproven.** MCP tools + pane-writer exist; the rendered dispatch feed is mock-first. | 8e |
| R-06 | Worker results return to the Conductor | **Implemented, unproven.** Same surface; no live round-trip is in evidence. | 8e |
| R-07 | OpenCode direct integration works | **Partial.** Governed spawn path and harness exist; roster ships `harness=None`; no Sovereign-side access point. | 8f |
| R-08 | Conductor can delegate to an OpenCode worker | **Absent.** OpenCode is not in the picker option set, so no worker of that backend can be created. | 8f |
| R-09 | Local model library discovery works | **Partial.** `build_pane_picker()` aggregates live `ollama list`; 14 hard-coded lists duplicate the preferences around it. | 8g |
| R-10 | Grok provider/model integration where configured | **Partial.** `grok_build` is configured. `grok-4.6` has three runtime spawn records, all stuck `SPAWNING`, `pid: null`. `grok-4.5` has none — fixtures and telemetry only. Selectability is attested; availability is not. | 8g |
| R-11 | Distillery runtime / entry point works | **Absent.** 125 lines of markdown parsing with a literal status string. | 8h |
| R-12 | Distillery UI works | **Absent.** Card exists; every control is hard-disabled. | 8h |
| R-13 | Token Center integrated into the main UI | **Absent from the shell.** The Token Center itself exists and runs standalone on :8765. | 8i |
| R-14 | Token Center reflects real backend state | **Partially satisfiable, and misframed.** Usage/model/provider telemetry is real and live. Credential and endpoint management **do not exist and are not in scope** (ADD-01 §2.1b). | 8i |
| R-15 | Existing functionality regression-safe | **Standing obligation.** Re-proven at every gate, not once at the end. | all |

---

## 3. Goal state — every predicate must be TRUE on disk

Read `TRUE when` as a conjunction. Where a hash is required it is full, lowercase, 64-hex, taken immediately after the final write of the file it names, with `Test-Path` verified first. Where a test is required it must have a captured **fails-before** artifact and a **passes-after** artifact; a test that never failed proves nothing.

### Band 0 — Session precondition

| # | Goal | TRUE when |
|---|---|---|
| G0 | Session start | `evidence/cp01/session-start.txt` exists with `# utc:` / `# producer: ox-alpha CP-01` headers, recording: true UTC; which shell your bash tool runs; sha256 of `docs/DECISIONS.md`, `AGENTS.md`, `CLAUDE.md` (the latter two equal); sha256 of `docs/SWS-UI-001-v1.2-ADDENDUM-01.md` and of this file; ports 5175/8700/8765/5180 listen-state as found; any module process under `modules\*`. The ADD-01 §9 sentence quoted verbatim with its UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. `evidence/cp01/tools/goalcheck.py` exists and runs clean. |
| G0.1 | Quiescent protected trees | `evidence/cp01/manifests/manifest-cp01-before-*.txt` captured for all five protected roots (`D:\Product Software\` outside the workspace, `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, `D:\Sov 1\`, `D:\Token Piggy Bank\`) using the pinned tool `evidence/tools/manifest.py` (its sha256 is recorded in `evidence/GATE-LEDGER.json` under `manifest_tool_sha256`; assert the match before use). SOW upstream git HEAD and `status --porcelain` byte-identical across two read-only inspections ≥ 60 s apart, `GIT_OPTIONAL_LOCKS=0`. |
| G0.2 | Baseline captured | `evidence/cp01/before/` holds copies + hashes of every file the caps in ADD-01 §3.2 permit you to touch, taken before the first mutation. `evidence/cp01/test-run-before.txt` from the README command ends `OK` with the count recorded; the entry baseline is **122 tests** (FACT[`evidence/GATE-LEDGER.json` gate 7a note: "Suite 122 tests OK"]) and a lower count at entry is itself a finding, not a starting point. `shell/BUILD-MANIFEST.txt` entries equal live hashes. `app.css` `:root` matches `docs/THEME-BASELINE-v3.md` exactly. |

### Band A — Gate 8a · Implementation map (read-only; no mutation outside `evidence/` and `docs/CP-MAP-01.md`)

| # | Goal | TRUE when |
|---|---|---|
| G1 | Runtime inventory | `docs/CP-MAP-01.md` §1 names, from disk: every module runtime and its launch path; the shell's launcher architecture; every place a browser is opened or could be; the SOW terminal implementation and its PTY boundary; the Conductor implementation and its input surfaces; every model-registry and provider-configuration source; the Token Center's architecture; the Distillery's entry points as they exist; OpenCode's installed state on this host. Every claim tagged `FACT[path:line]`. |
| G2 | Requirement classification | `docs/CP-MAP-01.md` §2 reproduces the §2 table above with **your own** disk evidence in place of the reviewer's, one row per R-ID, each cell citing a path and line. Any row where your evidence disagrees with §2 is flagged and triggers G2.1. |
| G3 | Divergence resolved | Either no row disagrees, or every disagreement is recorded in `evidence/cp01/premise-divergence.txt` with both readings and a STOP report written. A disagreement is never resolved by choosing. |
| G3.1 | Gate 8a submitted | Ledger key `"8a"`: `CANDIDATE`, evidence list with full lowercase sha256 for `docs/CP-MAP-01.md` and every `evidence/cp01/` artifact so far. Gates 0–7b asserted byte-identical before the write. |

### Band B — Gate 8b · Module lifecycle and runtime truth (R-01, R-02)

| # | Goal | TRUE when |
|---|---|---|
| G4 | No-autostart proved | A recorded cold start of the shell — `evidence/cp01/8b/cold-start.txt` — shows `GET /api/state` immediately after `serve_forever()` reporting **no module in `STARTING` or `READY` by shell action**, and a test `test_cold_start_starts_nothing` that fails against an artificially autostarting fixture and passes against the product. The external :8700 process, if present, appears as `EXTERNAL` — and the artifact records that it was **not** touched. |
| G5 | EXTERNAL is legible | The card for a module in `EXTERNAL` is visually and textually distinct from `READY`, states that the process is not shell-owned, and its Stop control either is disabled or is labelled as releasing only the shell's view. Proven by a headless-Edge `--dump-dom` artifact `evidence/cp01/8b/external-dom.txt` captured against a live `EXTERNAL` state. H-9 non-interference re-proven: the external pid is alive and unchanged after the shell's Stop. |
| G6 | READY requires evidence | `shell/modules/sow.json` no longer uses `readiness.kind = "process_window"`. SOW exposes a real readiness signal and the adapter polls it; `evidence/cp01/8b/sow-readiness.txt` shows the probe failing while the app is mid-boot and succeeding only once the app answers. `STOPPED` is likewise evidenced: `evidence/cp01/8b/stop-evidence.txt` shows the pid gone and the port free after Stop, for every module that binds a port. |
| G7 | Failure classes reach the operator | `start()`'s `err` is no longer discarded. Each of these is separately distinguishable in `/api/state` and rendered on the card: process failed to start · port unavailable · health check failed · identity mismatch · model unavailable · provider unavailable · OpenCode unavailable · configuration failure · worker failure · Conductor communication failure. A port-conflict pre-check runs before spawn and yields `FAILED(PORT_UNAVAILABLE)` naming the owning pid — not `TIMEOUT`. Tests `test_failure_classes` and `test_port_conflict_is_its_own_class` fail-before, pass-after. Artifact `evidence/hardening/h18-failure-classes.txt` lists every class with the induced condition that produced it. |
| G7.1 | Browser lifecycle bounded | The per-module window handle returned by `window.open` is retained, reused on a second Open, and closed when that module leaves `READY`/`EXTERNAL`. **No process kill, no `taskkill`, nothing that touches a browser the shell did not open.** Proven by `evidence/cp01/8b/browser-lifecycle.txt` and a test asserting the handle map's transitions. |
| G7.2 | Gate 8b submitted | Ledger `"8b"` `CANDIDATE`; suite green, count ≥ baseline; `BUILD-MANIFEST.txt` regenerated; manifests re-verified `fc /b` clean; changed-line totals for `shell/**` recorded and within cap. |

### Band C — Gate 8c · Session container and model selection (R-03)

| # | Goal | TRUE when |
|---|---|---|
| G8 | Container without process | Creating a terminal/workspace slot spawns **no PTY**. The new session is `EMPTY`, `backend = none`, `model_ref = null`, `pid = null`. The PowerShell default at the PTY boundary (`apps/desktop/main.js:474-491`) is removed as an implicit fallback. Test `test_new_session_spawns_no_process` fails-before against the current default, passes-after. Artifact `evidence/cp01/8c/empty-session.json` captures the record verbatim. |
| G9 | Backend selection precedes initialization | The operator selects `Execution Type` from `{Local Model, API Model, OpenCode, PowerShell}` while the session is `EMPTY`/`CONFIGURING`. Selection succeeds with no prior `exit`, no prior process, and no refusal referencing a live session. Model selection is presented only for backends that take one. Artifact `evidence/cp01/8c/selection-flow.txt` records the full sequence Create → Select → Initialize → Use with timestamps and the session record after each step. |
| G10 | Replacement is governed, not refused | Changing backend or model on a session past `STARTING` presents an explicit terminate-and-reinitialize affordance and, on confirmation, performs it. The refusal string *"already holds a live session — close it before launching another model into it"* no longer reaches the operator as the outcome of an ordinary selection. A running session is still never killed by an unconfirmed click. Test `test_governed_replacement` covers both branches, fails-before, passes-after. |
| G11 | PowerShell is an option, not a state | `backend = powershell` is reachable only by explicit selection, carries `model_ref = null`, and is labelled as an execution type in the UI. `grep` proof `evidence/cp01/8c/powershell-not-default.txt`: no code path spawns a shell for a session whose backend was not explicitly set to `powershell`. |
| G11.1 | Gate 8c submitted | Ledger `"8c"` `CANDIDATE`; SOW suite green; `modules/sow/**` changed-line total recorded and within cap; R-15 obligations re-proven. |

### Band D — Gate 8d · Conductor operator channel (R-04)

| # | Goal | TRUE when |
|---|---|---|
| G12 | A persistent typing surface exists | The SOW workspace carries a persistent, always-visible Conductor conversation surface: a text input, a submit affordance, and a transcript that retains prior turns across pane operations. It is not a status panel with a box bolted on; the transcript is the primary content. Proven by a headless `--dump-dom` artifact `evidence/cp01/8d/conductor-dom.txt` asserting the input element, the submit control, and ≥ 2 retained turns. |
| G13 | Round-trip: human → Conductor → human | `evidence/cp01/8d/conductor-roundtrip.txt` records: a directive typed into the surface; the Conductor's response returned into the transcript; a follow-up in the same thread that demonstrably carries prior context; and an interrupt or redirect exercised where the backend supports it, or recorded `UNSUPPORTED(<reason>)` where it does not. The Conductor leg runs on a **local** model per ADD-01 §3.4 unless spend is authorized. A Conductor communication failure surfaces as its own failure class (G7), not as silence. |
| G13.1 | Gate 8d submitted | Ledger `"8d"` `CANDIDATE` with the round-trip artifact hashed. |

### Band E — Gate 8e · Conductor ↔ worker control plane (R-05, R-06)

| # | Goal | TRUE when |
|---|---|---|
| G14 | Machine-readable worker registry | A single registry projection exposes, for every active session: `session_id` · `assigned model` (`provider_id` + `model_id`, or explicit null) · `execution backend` · `current state` · `task state` · `communication endpoint/channel` · **`created_utc`** · `error state`. `created_utc` is the C-6 gap and must now be projected. The projection is dumped verbatim to `evidence/cp01/8e/worker-registry.json` with ≥ 2 live workers present, and a test asserts every listed field is non-absent for each. |
| G15 | Conductor → worker delivery | `evidence/cp01/8e/directive-delivery.txt` shows a task issued by the Conductor arriving at a named worker: the task id, the target `session_id`, the delivery mechanism, and the worker's own record showing the task bound to it. Task ownership is tracked, not inferred. |
| G16 | Worker → Conductor return, and synthesis | The same artifact chain shows the worker's result returning to the Conductor, the Conductor reporting it to the operator in the G12 transcript, and — with **two** workers on different models — a consolidated synthesis naming both sources. A deliberately failed worker is identified as failed by the Conductor rather than silently dropped: `evidence/cp01/8e/worker-failure.txt`. The mock-first dispatch feed either now renders live data or is visibly labelled as mock in the UI; a mock rendered as live is `FAKE_STATE`, a STOP. |
| G16.1 | Gate 8e submitted | Ledger `"8e"` `CANDIDATE`. The gate note states plainly which legs ran live and which were `NOT_RUN`, with the reason. |

### Band F — Gate 8f · OpenCode execution backend (R-07, R-08)

| # | Goal | TRUE when |
|---|---|---|
| G17 | OpenCode presence is a discovered fact | `evidence/cp01/8f/opencode-detect.txt` records the actual result of the host's detection path (`shutil.which("opencode")` / `opencode.ps1`) and, if present, `opencode --version`. Absent → every G17–G19 goal is satisfied by a truthful `UNAVAILABLE` record plus a `FAILED(OPENCODE_UNAVAILABLE)` surfaced through G7, and Gate 8f is submitted as `CANDIDATE` with that limitation stated. Fabricating availability is a session-ending violation. |
| G18 | Direct Sovereign access | An OpenCode-backed session is reachable from the Sovereign surface through an **integrated** terminal/workspace panel — not a popup window architecture. The operator initiates it and performs one agentic file operation inside a scratch directory under the workspace. `evidence/cp01/8f/opencode-direct.txt` records the command, the working directory, the operation, and the resulting file's before/after hash. |
| G19 | OpenCode as a worker backend, delegated to | `OpenCode` appears in the Execution Type list and instantiates a real OpenCode-backed session — **not** an entry in a model list (ADD-01 §4.2). Its worker record shows `backend: opencode` with `model_ref` separate and populated by a compatible model. The Conductor sends it a bounded agentic task through the same worker-control abstraction used for other backends, and the result returns. Full chain captured in `evidence/cp01/8f/opencode-delegation.txt`: Human → Conductor → OpenCode worker → repository/file work → result → Conductor → Human. |
| G19.1 | No model/backend confusion | `grep` proof `evidence/cp01/8f/backend-not-model.txt`: `opencode` appears in no model enumeration, no `model_id` field, and no model registry row. Zero new `if backend == "opencode"` special cases in dispatch, selection, or rendering paths — behaviour differences are carried by backend descriptors, not by branches. Any such branch introduced is `SPECIAL_CASE_ACCUMULATION`, a STOP. |
| G19.2 | Gate 8f submitted | Ledger `"8f"` `CANDIDATE`. |

### Band G — Gate 8g · Model / execution registry (R-09, R-10)

| # | Goal | TRUE when |
|---|---|---|
| G20 | One canonical registry | A single canonical registry serves the Conductor selector and every worker selector. The 14 hard-coded lists inventoried at G1 are either consumed by it as declared seed data with `discovered_by` recorded, or removed. `evidence/cp01/8g/registry-dump.json` is the registry's own output; `evidence/cp01/8g/duplication-audit.txt` shows, per inventoried list, its disposition. No UI component holds its own model list. |
| G21 | Metadata prevents incompatible selection | Each registry row carries, where determinable: `provider` · `runtime` · `model_id` · `locality` · `context` · `tools` · `vision` · `reasoning` · `agent_compatible` · `availability` · `health` · `discovered_by`. A field the host cannot report is recorded `unknown`, never guessed. A selection the compatibility relation forbids is refused with a stated reason before any process is spawned; test `test_incompatible_selection_refused` fails-before, passes-after. |
| G22 | Discovery is live and honest | `evidence/cp01/8g/discovery.txt` records the actual command output for each source: local runtime inventory, `ollama list` (or `GET /api/tags`), each configured provider CLI's own `models` enumeration including `grok_build`, and OpenCode's detection. **Grok:** whatever the host's `grok_build` CLI enumerates at discovery time is what the registry contains — verbatim, nothing added. Neither `grok-4.5` nor `grok-4.6` is written into any list, config, fixture, or UI string on the strength of this directive mentioning it, of the operator's request, or of the three historical `SPAWNING` records in `.sovereign_store` (ADD-01 §4.3 — a spawn attempt is selectability, not availability). If the CLI enumerates them they appear with `discovered_by` and a live `availability`; if it does not, the artifact records the enumeration as returned and that is the passing result. Any entry without a discovery artifact is `FABRICATED_AVAILABILITY`, a session-ending violation. |
| G22.0 | Grok reachability recorded either way | `evidence/cp01/8g/grok-status.txt` records, for each Grok model the CLI enumerates: whether a session was successfully established, or the exact failure. The three prior `SPAWNING`/`pid: null` records are cited as the prior state so the reviewer can see whether this loop changed it. `NOT_RUN(NO_SPEND_AUTHORIZATION)` is a valid and expected outcome here — `grok_build` is a frontier provider and ADD-01 §3.4 authorizes no spend. |
| G22.1 | Gate 8g submitted | Ledger `"8g"` `CANDIDATE`, note stating exactly which providers and models the host actually exposed. |

### Band H — Gate 8h · Distillery runtime and UI (R-11, R-12)

| # | Goal | TRUE when |
|---|---|---|
| G23 | Installed under Option A | `modules/distillery/` exists, seeded per ADD-01 §3.3 from the enterprise snapshot, with `INSTALL-PROVENANCE.json` and a manifest. `D:\Sovereign Distillery\` byte-identical to its G0.1 baseline. The Distillery's existing architecture and purpose are **not** redesigned — only made operable. |
| G24 | Runtime, entry point, lifecycle, health | `shell/modules/distillery.json` declares a real `launch`, `readiness` (`http`), `identity` (`http_json`), `stop` (`job_object`), and `runtime_writes`. `state_class` is no longer `not_started`. Start → `READY` via an observed health response; Stop → pid gone, port free. Independently startable and stoppable from the shell, integrated into the same module lifecycle as the others. Artifacts `evidence/cp01/8h/distillery-start.txt`, `distillery-stop.txt`. Local-first: no network egress is required to reach `READY`, proven by the readiness probe target being loopback. |
| G25 | UI is a console, not a second OS | The Distillery surface exposes: Runtime Status · Student Model · Teacher/Source Models · Pipeline State · Current Stage · Queue · Hardware/Compute Status · Start/Pause/Stop · Logs/Evidence · Artifacts/Outputs. Advanced configuration is secondary or absent. Sovereign theme tokens only; no new hex outside `docs/THEME-BASELINE-v3.md`. C-5 is fixed: no bare `D:/...` path appears in an `href`. Proven by `evidence/cp01/8h/distillery-dom.txt` asserting each named surface. |
| G25.1 | **No compute on open** | Starting the Distillery runtime and opening its UI initiates **no training, distillation, merge, or other expensive compute**. Proven by `evidence/cp01/8h/no-autocompute.txt`: process/GPU/CPU observation across a start → open → idle → stop window showing no training process spawned and no artifact written to the outputs path; plus a test asserting the start path invokes no pipeline entry point. UI startup and compute execution are separate operator actions. A single training step begun automatically is `AUTO_COMPUTE`, a STOP. |
| G25.2 | Gate 8h submitted | Ledger `"8h"` `CANDIDATE`. |

### Band I — Gate 8i · Token Center integration (R-13, R-14)

| # | Goal | TRUE when |
|---|---|---|
| G26 | Installed under Option A | `modules/tokencenter/` exists as a copy of `D:\Token Piggy Bank\` excluding `data/` and `.git/`, with provenance and manifest. `D:\Token Piggy Bank\` byte-identical to its G0.1 baseline. C-7 fixed **in the copy only**: the bind host is pinned to loopback with no CLI override, and `POST /api/refresh` carries the same Origin/Host/CSRF guard set the shell already enforces. Tests cover both. |
| G27 | A module like any other | `shell/modules/tokencenter.json` declares `readiness` `http` → `http://127.0.0.1:8765/healthz` expecting 200, `identity` `http_json` requiring the keys `/healthz` actually returns, `open` → its own URL, `stop` `job_object`. It starts, reaches `READY` on an observed health response, stops cleanly, and obeys every rule the other three modules obey. |
| G28 | Central in the main control surface | The main Sovereign UI places the Token Center centrally with the four modules arranged around it — SOVEREIGN, Orchestration Workspace, Debate Table, Distillery. Conceptual layout, not literal geometry; it collapses to a single column below the existing 720 px breakpoint. Sovereign theme tokens only: the Token Center's own `--gold #f3b43f` / `--cyan #79e5f4` palette does **not** enter `shell/static`. Its standalone page keeps its own identity untouched. Proven by `evidence/cp01/8i/main-ui-dom.txt` (structure) and `evidence/cp01/8i/main-ui-*.png` in both themes, non-blank. |
| G29 | It reflects real backend state | The surfaced panel renders values read live from the module's own `GET /api/summary`, with every key path it reads asserted to resolve in the live payload (the H-15 contract-test pattern, artifact `evidence/hardening/h19-tokencenter-contract.txt`). Displayed: configured/observed providers, model availability, local vs remote classification, usage/token information, collector health, and `collected_at` staleness. When the module is not `READY` the panel says so rather than showing stale numbers as current. |
| G29.1 | No credential surface is created | `evidence/cp01/8i/no-credentials.txt`: a grep of `modules/tokencenter/**` and `shell/**` proving no credential store, key entry field, secret value, or provider authentication was introduced. Per ADD-01 §2.1b this requirement is satisfied by the **absence** of such a surface, not by redacting one into existence. Endpoint/authentication management is out of scope; the gate note records that plainly. |
| G29.2 | Gate 8i submitted | Ledger `"8i"` `CANDIDATE`. |

### Band J — Gate 8j · End-to-end acceptance (scenario A–H)

One recorded run, in this order, in one session, against the real system. Not eight isolated button tests. Everything lands in `evidence/cp01/8j/`.

| Step | Passes when |
|---|---|
| A · Cold start | Sovereign starts. Debate Table and Distillery consume no runtime. `state-after-coldstart.json` shows nothing running by shell action. |
| B · Debate Table | Select → runtime starts → health observed → browser opens. Return, Stop → runtime stops, port free, the shell-opened browser surface closes. An external :8700 owner, if present, is `EXTERNAL` and untouched throughout. |
| C · Orchestration Workspace | Open it. Create a worker terminal. **The operator is not in PowerShell.** Select a local model. It initializes. Send a prompt. A response returns. Recorded end to end with the session record at each transition. |
| D · Conductor | Message the Conductor directly; response returns. Create multiple workers. The Conductor issues a directive to one; the worker receives it; the result returns to the Conductor; the Conductor reports and synthesizes to the operator. |
| E · OpenCode | Create an OpenCode worker, configure its model, give the Conductor a bounded agentic task. `Human → Conductor → OpenCode → execution → result → Conductor → Human` captured whole. If OpenCode is absent on the host, recorded `NOT_RUN(OPENCODE_UNAVAILABLE)` with the G17 detection artifact. |
| F · Model agnosticism | Discovery exposes compatible local models dynamically. Configured Grok models appear **where actually configured**. `grep` proof that no dispatch, selection, or rendering path branches on a model family. |
| G · Distillery | Start → runtime up → UI up → status visible → **no training begun** → Stop → clean termination, verified. |
| H · Token Center | Main UI shows it integrated centrally, reflecting real configured provider/model state, with no secret rendered. |
| — | Every step's artifact carries the `# utc:` / `# producer:` headers, and any step recorded `NOT_RUN` names its blocking condition. A step "passing" without an artifact is not passing. |

| # | Goal | TRUE when |
|---|---|---|
| G30 | Scenario recorded | Every row above has its artifact, in order, from one session. |
| G31 | The proof chain holds | `evidence/cp01/8j/proof-chain.txt` shows `Human → Conductor → {local LLM · API model · OpenCode} → result → Conductor → Human` with each leg either exercised or recorded `NOT_RUN(<reason>)`. The API-model leg is `NOT_RUN(NO_SPEND_AUTHORIZATION)` unless the operator authorized spend. |
| G32 | Regression clean | Full suite `OK`, count ≥ baseline; `BUILD-MANIFEST.txt` regenerated and equal to live hashes; all five protected manifests `fc /b` clean against G0.1; `app.css` `:root` unchanged from v3; fs-watch artifact `events: 0` bracketing G0.2 → G32. |
| G33 | Envelope honoured | `evidence/cp01/linecount.txt` shows the per-area and absolute changed-line totals, all within ADD-01 §3.2, computed by `difflib` against `evidence/cp01/before/`. |
| G34 | Clean closeout | Every builder-started process stopped through its own path; `Get-Process` shows nothing under `modules\*`; ports 5175/8700/8765/5180 free; orphan artifact captured; no debugging left behind as finished work. |
| G35 | Ledger `"8j"` | `CANDIDATE`, listing every 8j artifact plus the standing evidence, hashes full and lowercase. Gates 0–7b and 8a–8i asserted byte-identical where already written. |
| G36 | Report | `docs/CP-01-REPORT.md` exists with, per requirement R-01…R-15: **Requirement ID · Implementation location · Files changed · Behavior before · Behavior after · Validation performed · Result · Remaining limitations.** Every substantive sentence tagged `FACT[path]` / `ASSUMPTION` / `INTERPRETATION` / `RECOMMENDATION`. It ends with the §8 claim line. |

---

## 4. The loop

```
i = 0
while i < 120:
    i += 1
    state = goalcheck()                  # reads disk only; writes evidence/cp01/goalcheck-<i>.txt
    if all TRUE: break
    g = first failing goal in declared order
    act(g)                               # the ONE smallest authorized action for g
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, goal, action, changed_lines, flipped, notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS
submit: ledger keys + docs/CP-01-REPORT.md + claim line
```

`goalcheck()` is `evidence/cp01/tools/goalcheck.py` — `py -3.12`, stdlib only, read-only, PNG background decode included, one line per goal: `G<n>: TRUE|FALSE  <reason>`. Write it at G0; it is the only oracle. If the oracle itself errors, repairing it is a permitted action logged as `goal: G-oracle`. The oracle never reports a goal TRUE on the strength of something it did not read from disk this iteration.

Every mutation is preceded by a `before/` capture of the file and followed by a `linecount.txt` append. Any transient failure (HTTP timeout, Edge non-zero exit, PTY race) gets exactly **one** retry; the second failure is logged and counts toward no-progress.

**Single writer.** Nothing else writes to this workspace while the loop runs. If a file you did not write changes under you, that is `CONCURRENT_WRITER` — stop and name the file.

---

## 5. Action envelope per band — nothing outside it

- **G0–G0.2**: evidence writes, the oracle, read-only inspections. No product edits.
- **G1–G3.1**: read-only inspection plus `docs/CP-MAP-01.md` and `evidence/cp01/**`. **No product edits in Band A at all.**
- **G4–G7.2**: `shell/src/**`, `shell/static/**`, `shell/modules/*.json` within cap; `shell/tests/**` uncapped. Module launches through the shell's own routes only.
- **G8–G11.1**: `modules/sow/apps/desktop/**` within cap; SOW's own tests. Launch SOW through the shell; the selfcheck path for deterministic assertions, the normal path only where a goal requires live operator flow.
- **G12–G16.1**: same tree, plus `control_plane/**` and `mcp_server/**` where the round-trip requires it. Local models only absent a spend authorization.
- **G17–G19.2**: OpenCode adapter, roster, picker, supervisor spawn path. Agentic file operations confined to a scratch directory under `Production Workspace\`; never a protected tree, never `modules/sovereign`, `modules/debate`.
- **G20–G22.1**: registry sources and their consumers. Discovery commands are read-only; no `ollama pull`, no provider authentication, no config writes to a provider CLI's own store.
- **G23–G25.2**: `modules/distillery/**` and its manifest. Read `D:\Sovereign Distillery\` only.
- **G26–G29.2**: `modules/tokencenter/**`, its manifest, and the shell surfaces that render it. Read `D:\Token Piggy Bank\` only.
- **G30–G36**: no source edits. A product defect discovered during acceptance is `LOOP_PRODUCT_DEFECT` — a STOP, not a repair, unless it falls inside a still-failing goal's own envelope.

All evidence files carry `# utc: <(Get-Date).ToUniversalTime().ToString("o")>` and `# producer: ox-alpha CP-01`. Hashes are full 64-hex lowercase, taken after the final write, `Test-Path`-verified. Hand-authored evidence is append-only: a wrong artifact is superseded by a new one naming it, with both hashes and the reason.

---

## 6. STOP conditions

`AGENTS.md` §13 in full, plus ADD-01 §8, plus:

`LOOP_NO_PROGRESS` · `LOOP_PRODUCT_DEFECT` · `ENVELOPE_EXCEEDED` · `PREMISE_CONTRADICTED` · `FAKE_STATE` (a mock, a stub, or an unverified condition rendered as real) · `SPECIAL_CASE_ACCUMULATION` (a backend- or model-family branch introduced into a dispatch, selection, or rendering path) · `AUTO_COMPUTE` (any expensive Distillery workload begun by a UI or runtime start) · `FABRICATED_AVAILABILITY` (any provider, model, or capability asserted without a discovery artifact) · `CONCURRENT_WRITER` · `INSTALL_REQUIRED` · `SPEND_REQUIRED` · `PROTECTED_SOURCE_CHANGED` · `ARCHITECTURE_CONSTRAINT_UNSATISFIABLE` · iteration 120 reached.

A STOP writes `docs/STOP-REPORT-CP-01.md` containing: the loop-ledger tail; the `FACT[...]` condition; the exact requirement or conflict; why proceeding would require interpretation; **2–3 bounded operator options**; no unauthorized implementation. Then closes out per §7 and ends with the no-gate claim line.

---

## 7. What this loop may never do

Write `PASS` anywhere. Edit `AGENTS.md`, `CLAUDE.md`, the contract, ADD-01, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, or `docs/DECISIONS.md`. Alter a reviewer-evaluated ledger entry. Touch a protected tree except read-only. Redesign a working module because another framework is preferred. Alter the Sovereign visual identity without a goal requiring it. Hard-code the system around today's models. Make cloud connectivity mandatory. Make OpenCode the only agentic backend. Represent OpenCode as an LLM. Start Distillery compute automatically. Kill an unrelated browser or process. Create a `RUNNING` state without a health observation. Ship a placeholder control and call it integrated. Declare Conductor orchestration operational without an actual worker round-trip in evidence. Broaden into Sovereign components no goal names. Re-interpret a goal so it passes — "close enough" is FALSE. Treat oracle output as evidence of anything the oracle did not read from disk this iteration.

---

## 8. Exit

On every goal TRUE: write `docs/CP-01-REPORT.md` per G36, then a final message carrying — iteration count · the goal table with the artifact and hash proving each · the R-01…R-15 evidence table · per-area and absolute changed-line totals · which acceptance legs ran live and which were `NOT_RUN` with reasons · deviations · remaining limitations · carried defects C-1, C-2, C-3, and any of C-4 not repaired. Ending with exactly:

```
BUILDER CLAIM: Gates 8a through 8j are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder.
```

On any STOP, ending with exactly:

```
BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
```

Never reworded. A message containing "passed", "complete", "done", or "✓" beside a gate number is a violation. Say **candidate**.

The reviewer evaluates 8a–8j against this directive and ADD-01. Promotion is the operator's, and follows the reviewer's verdict.
