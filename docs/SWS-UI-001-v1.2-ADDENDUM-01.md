# SWS-UI-001 v1.2 — ADDENDUM 01: Control-Plane Integration Envelope

| Field | Value |
|---|---|
| Amends | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2 "Contract Closure", 2026-08-21. The contract text is **unchanged**. This addendum widens the mutation envelope and adds gates; it removes no constraint the contract states. |
| Addendum ID / version | `SWS-UI-001-ADD-01 v1.0`, 2026-08-25. |
| Issuer / final authority | Human operator (sam). Nothing in this file is authorization until the operator's issuing sentence (§9) is logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. |
| Scope class | **Scope extension.** v1.2 froze the *shell* architecture. This addendum opens a bounded envelope across `shell/**`, `modules/**`, and two new module installs, for control-plane integration only. |
| Entry state | Gates 0–4c, 5b `PASS`; Gate 6 `PASS` (operator promotion 2026-08-24T17:05:14Z); Gates 7a, 7b `CANDIDATE`, awaiting reviewer. FACT[`evidence/GATE-LEDGER.json`] |
| Work order | `docs/OX-ALPHA-DIRECTIVE-CP-01.md`. This addendum defines *what may be touched*; the directive defines *what must become true*. |
| Precedence | Slots into `AGENTS.md` §1 item 2 (operator-authored envelope), beneath the contract and above reviewer verdicts. `AGENTS.md` binds in full and unamended. |

---

## 1. Why this addendum exists

v1.2 §2 caps `shell/**` mutation at the Gate 4b/Gate 5 envelopes (≤ 80 and ≤ 40 changed lines) and declares `modules/**` untouched except through the shell. The operator's Control-Plane directive requires work that cannot fit inside either cap and that necessarily edits `modules/sow/**`. Proceeding under the v1.2 envelope would be an `ENVELOPE_EXCEEDED` STOP on iteration 1. This addendum is the operator's answer to that STOP.

It does **not** reopen v1.2's architecture. The shell's adapter contract (§7.2), state machine (§7.4), hardening set (§7.6), theme baseline (`docs/THEME-BASELINE-v3.md`), and isolation rules (§4) remain normative and binding on all work performed under it.

---

## 2. Reconnaissance already performed — the builder inherits these facts, and re-verifies them

Read-only reconnaissance was performed by the reviewer on 2026-08-25 across four trees. The builder does **not** take these as given; Gate 8a re-establishes each from disk. They are recorded here so the builder does not re-derive scope, and so any divergence is visible as a change rather than a discovery.

| Area | Finding | Evidence |
|---|---|---|
| Debate autostart | **No autostart exists anywhere in `shell/**`.** `main()` constructs runners and polls; no runner is started. Every module begins `STOPPED`/`NOT_STARTED`/`CONFIG_ERROR`. | FACT[`shell/src/server.py:462-482`], FACT[`shell/src/states.py:80-86`] |
| What actually opens a browser | `Start-Shell.ps1` opens a browser **for the shell itself**, not for a module. | FACT[`Start-Shell.ps1:110,126`] |
| The Debate on :8700 | An operator-side process at `D:/Debate table/app.py` (pid recorded 2026-08-25) holds 8700. The shell can only report it `EXTERNAL`, and by H-9 must never touch it. | FACT[`evidence/GATE-LEDGER.json` gate 7b note], FACT[`shell/src/states.py:194-197`] |
| Module browser lifecycle | `window.open(rec._url, "_blank", "noopener")`; the returned handle is discarded. Nothing is closed on stop. Orphan tabs are guaranteed. | FACT[`shell/static/app.js:626-631`] |
| SOW readiness | `readiness.kind = "process_window"` — READY means "the Electron process was still alive one second after spawn". No window, port, or IPC is checked. This is a fake RUNNING state under the operator's §16. | FACT[`shell/modules/sow.json`], FACT[`shell/src/states.py:113-123`] |
| Failure detail | `start()` returns `(display, err)`; `err` carries the real diagnostic and is discarded by `_start_worker`. The operator sees `Failed: TIMEOUT` and never the cause. | FACT[`shell/src/server.py:324-329`], FACT[`shell/src/states.py:177-187`] |
| Port conflict | No bind-conflict detection exists at start. `preflight_ports` exists but `start()` never consults it. | FACT[`shell/src/probe.py:136-149`], FACT[`shell/src/states.py:148-190`] |
| Terminal ≡ PowerShell | The one PTY boundary defaults to PowerShell whenever the spec carries no `file`, which is exactly the plain "+ Terminal" path. | FACT[`modules/sow/apps/desktop/main.js:474-491`], FACT[`main.js:1539-1540`] |
| The `exit` trap | Selecting a model on a pane that already holds a live session is refused: *"pane N already holds a live session — close it before launching another model into it"*. `hasLiveSession` is true for a PowerShell pane. The conductor pane refuses equivalently. | FACT[`modules/sow/apps/desktop/picker/worker-spawn.js:234-243`], FACT[`main.js:2003-2004`], FACT[`main.js:1495-1498`] |
| Conductor operator channel | **Absent.** No `<input>`, `<textarea>`, or `contenteditable` exists in the SOW renderer. Operator text reaches the Conductor only as raw PTY keystrokes or push-to-talk. No HTTP/WS route accepts operator text. | FACT[`modules/sow/apps/desktop/renderer/index.html:191-225`], FACT[`renderer.js:65`], FACT[`control/sovereign-control-server.js:285,301-302`] |
| Worker registry | **Exists**, and is richer than the directive requires: `node_id, pane_id, session_id, pid, provider_id, model_id, role, node_state, task_status, mcp_state, mcp_fresh, last_seen, structured_failure, lease_id`. Gap: `startedAt` exists on the internal record but is not projected to the control surface. | FACT[`modules/sow/apps/desktop/picker/worker-spawn.js:61-82`], FACT[`control/operational-state.js:36-66`] |
| Conductor→worker messaging | **Exists** as MCP tools (`assign_task`, `send_message`, `read_messages`, `spawn_worker`, `get_worker_status`) over a loopback control server; delivery into a worker is a typed prompt via `pane-writer`. | FACT[`modules/sow/mcp_server/sovereign_tools.py:642-658`], FACT[`apps/desktop/main.js:2358-2362`], FACT[`control/pane-writer.js`] |
| …but unproven | The Python `conductor_dispatch` feed the UI renders is MOCK-first and carries `LIVE_WORKERS_OWED = {"owed": True, "issue": "U58"}`. No live worker round-trip is in evidence. | FACT[`modules/sow/control_plane/orchestration/conductor_dispatch.py:11-20,63-69`] |
| OpenCode | Governed spawn path, harness, driver, and candidate modules all exist. The roster ships `harness=None` ("OpenCode programmatic drive deferred") and OpenCode is **not** in the pane-picker option set. | FACT[`modules/sow/node_runtime/supervisor/opencode_spawn.py:1`], FACT[`adapters/roster.py:88-92`], FACT[`control_plane/nodes/pane_picker.py:40-56`] |
| Model registry | No `models.json` exists. `build_pane_picker()` is the de-facto aggregator. **14 hard-coded model/provider lists** are duplicated across Python modules; the renderer duplicates none. | FACT[`modules/sow/control_plane/nodes/pane_picker.py:449,495-510`], FACT[`adapters/roster.py:23-24`], FACT[`control_plane/conductor/registry.py:80-105`] |
| Grok | `grok_build` is a configured provider. **Both families are attested, differently.** `grok-4.6` appears as a real runtime node record — three `spawn` events, `adapter: grok_build`, `locality: frontier`, `model_ref: "grok-4.6"`, capabilities reasoning + synthesis, `min_context: 128000` — all three stuck at `state: SPAWNING` with `pid: null`. `grok-4.5` appears **zero** times in that runtime log; it exists only in selfcheck/test fixtures, and once in observed Token Center telemetry. Neither is hard-coded in a source model list; both arrive from `grok_build` CLI enumeration at runtime. | FACT[`modules/sow/config/live_operation.json:7-12`], FACT[`modules/sow/.sovereign_store/nodes/node_events.jsonl`, ts 2026-08-22T20:21:02Z / 20:29:05Z / 21:35:44Z], FACT[`apps/desktop/selfcheck/op12-live-acceptance-selfcheck.js:128-129`], FACT[`D:\Token Piggy Bank\data\piggybank.sqlite` latest snapshot: `xAI / Grok` → `grok-4.5`, 1 event, coverage `PARTIAL`] |
| Distillery | `shell/src/distillery.py` is 125 lines of read-only markdown parsing. Status is a literal: `status = "not started"`. No runtime, entry point, health, or lifecycle exists. Card buttons are hard-disabled client-side and refused server-side. | FACT[`shell/src/distillery.py:38-39,103-126`], FACT[`shell/static/app.js:474,522-529`], FACT[`shell/src/states.py:274-275`] |
| Token Center | **Exists and runs**, at `D:\Token Piggy Bank\`: stdlib Python, single file `piggybank.py` (871 lines), `ThreadingHTTPServer` on `127.0.0.1:8765`, `GET /api/summary?days=N`, `GET /healthz`, `POST /api/refresh`, schema `token-piggy-bank.summary.v1`, SQLite snapshot ring. | FACT[`D:\Token Piggy Bank\piggybank.py:757-831,858,679`] |
| Token Center — credentials | **It holds none.** No key store, no keyring, no DPAPI, no `.env`, no auth to any provider. It reads local usage ledgers off disk and lifts only numeric counters and model/provider identifiers. | ABSENT (searched `api_key`, `secret`, `password`, `credential`, `keyring`, `dpapi`, `bearer`, `authorization`, `.env`, `getenv`) |

### 2.1 Two operator premises this evidence corrects

The builder must not implement against a premise the evidence contradicts. Both corrections are binding.

**(a) "Debate Table autostarts."** It does not — nothing in the shell starts any module. The observable the operator saw is an *operator-side* Debate process holding :8700, which the shell correctly reports as `EXTERNAL`. R-01 is therefore not a repair; it is a **proof obligation plus a legibility defect**: the shell must make "someone else's process is on this port" visibly distinct from "we started this". Building an autostart-suppression switch would be building a fix for a defect that does not exist.

**(b) "The Token Center is an access-management surface."** It is not. It is a read-only *usage-telemetry* reader that never authenticates to anything. Requirement 14's "sensitive credentials must not be rendered into the UI" is therefore satisfied vacuously, and **must not be read as license to build a credential store.** Introducing one would create the exact leak surface the requirement forbids. Provider/model **availability** and **connection health** are in scope; provider **authentication and secret storage** are out of scope for this addendum and require a separate operator decision.

---

## 3. Mutation envelope

### 3.1 Trees and their new status

| Tree | Status under this addendum |
|---|---|
| `D:\Product Software\Production Workspace\shell\**` | **Writable**, per the caps in §3.2. |
| `D:\Product Software\Production Workspace\modules\sow\**` | **Writable**, per the caps in §3.2. First mutation of this tree since v1.2. |
| `D:\Product Software\Production Workspace\modules\distillery\**` | **Creatable** (new install, §3.3). |
| `D:\Product Software\Production Workspace\modules\tokencenter\**` | **Creatable** (new install, §3.3). |
| `D:\Product Software\Production Workspace\modules\sovereign\**`, `modules\debate\**` | **Unchanged.** Read-only. Not in scope. |
| `D:\Sovereign Distillery\` | **Protected, read-only.** Unchanged from `AGENTS.md` §6. Source of record for Distillery design only. |
| `D:\Token Piggy Bank\` | **Protected, read-only.** Added to the `AGENTS.md` §6 protected set by this addendum. It is the operator's live Token Center; it is a copy source, never an edit target. |
| `D:\Sov 1\`, `D:\multi model terminal app\` | **Protected, read-only.** Unchanged. Never launched. |
| `D:\Product Software\` outside `Production Workspace\` | **Read-only**, with one exception: the Distillery enterprise snapshot directory named in §3.3 may be read as a copy source. |

### 3.2 Changed-line caps — per file area, and an absolute total

Counted as added + removed via `difflib.unified_diff` against the Gate 8a `before/` capture, summed per area. Test files are **excluded** from every cap; new tests are evidence, not product.

| Area | Cap | Notes |
|---|---:|---|
| `shell/src/**` | 320 | server routes, states, distillery, probe, adapter |
| `shell/static/**` | 300 | layout, Token Center panel, browser handles, failure surface |
| `shell/modules/*.json` | 140 | two new manifests, two edits, schema |
| `modules/sow/apps/desktop/**` | 700 | session container, conductor channel, picker |
| `modules/sow/control_plane/**`, `adapters/**`, `node_runtime/**` | 400 | registry, OpenCode backend |
| `modules/distillery/**` | 500 | new install; runtime + entry point only |
| `modules/tokencenter/**` | 60 | new install; the copy itself is not "changed lines" |
| **Absolute total, all areas** | **1,850** | Exceeding it is `ENVELOPE_EXCEEDED`, a STOP — never a split into smaller edits |

Splitting one logical change across several sub-cap edits to evade a cap is a violation, not a technique. The `AGENTS.md` §7 prohibition on that is carried forward verbatim.

### 3.3 New module installs — v1.2 §6 Option A, unchanged

Both new modules install **under `Production Workspace\modules\`**, exactly as `sovereign`, `debate`, and `sow` did. The upstream tree is copied, never referenced in place and never edited.

- `modules/tokencenter/` ← copy of `D:\Token Piggy Bank\` **excluding** `data/` and `.git/`. Zero third-party dependencies; runs on `py -3.12` stdlib. Its data directory is a `runtime_writes` entry, created fresh.
- `modules/distillery/` ← seeded from `D:\Product Software\SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e\`, read-only copy source. `D:\Sovereign Distillery\` is read for design intent and is never a copy source or an edit target.

Dependency closure (v1.2 §6.1) applies to both. `pip`/`npm` installs remain prohibited except where §3.4 authorizes them.

### 3.4 Installs and provider spend

- `pip` and `npm install` remain **prohibited** except for one case: creating `modules/tokencenter/`'s virtual environment, which requires no third-party package and therefore requires no index access. If any step is found to need a package download, that is a STOP (`INSTALL_REQUIRED`), not a decision the builder makes.
- Ollama install/pull/delete/config remains **prohibited**. Local model availability is discovered, never provisioned.
- **Provider spend remains a mandatory STOP.** The Conductor is currently configured to a paid frontier CLI (`openai_codex_cli` / `gpt-5.6-sol`, FACT[`modules/sow/config/live_operation.json:15-22`]). Every acceptance run under the work order defaults to **local Ollama models on both the Conductor leg and the worker leg**. A frontier or hosted-API leg is executed only if the operator issues a separate spend authorization naming the provider and the bound; absent that, the API-model leg of the acceptance scenario is recorded `NOT_RUN(NO_SPEND_AUTHORIZATION)` — which is a truthful result, not a failure.

### 3.5 What remains untouchable

Unchanged from `AGENTS.md` §3: the builder may not edit `AGENTS.md`, `CLAUDE.md`, `BUILD-DIRECTIVE-SWS-UI-001.md`, this addendum, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, or `docs/DECISIONS.md`. The builder never writes `"status": "PASS"`. Gates 0–7b are byte-identical before and after every ledger write.

---

## 4. Architectural constraints — binding, not advisory

These exist because the directive's requirements can be satisfied in a way that is correct today and structurally wrong. They are the parts of the architecture the operator is fixing, not the parts the builder may choose.

### 4.1 A terminal is a session container

`Session` is the unit. A session exists before any process does.

```
Session
├── session_id            stable, minted at container creation
├── backend               local_model | api_model | opencode | powershell | none
├── model_ref             {provider_id, model_id} | null
├── state                 EMPTY → CONFIGURING → STARTING → READY → BUSY → DEGRADED|FAILED → ENDED
├── task                  {task_id, status} | null
├── channel               {kind: mcp|pty|none, endpoint, last_seen, fresh}
├── cwd, permission_profile
├── created_utc, pid, exit_code, error
```

Invariants:

1. Creating a session container spawns **no process**. A new container is `EMPTY` with `backend = none` and no PTY. The PowerShell default at the PTY boundary is removed as a default and retained only as `backend = powershell`.
2. Backend and model are selected while the session is `EMPTY` or `CONFIGURING` — before initialization. Selection is never refused on the ground that a process is running, because in the corrected flow no process is running yet.
3. Changing the backend or model of a session already past `STARTING` is a **governed replacement**: an explicit operator affordance that terminates and re-initializes, with a visible confirmation. It is never a silent refusal, and it never kills a running session to make room for a stray click.
4. `backend = powershell` is an ordinary execution option with no model. It is never a fallback, never implicit, and never a state the operator arrives in without choosing it.

### 4.2 A model is not an execution backend

Two registries, joined by a compatibility relation. Never one table with a vendor `if`.

```
ExecutionBackend {backend_id, kind: agent_runtime|model_runtime|shell, available, detect_evidence}
ModelRef         {provider_id, model_id, runtime, locality, context, tools, vision,
                  reasoning, agent_compatible, availability, health, discovered_by}
Worker           = ExecutionBackend × (ModelRef | null) × {session_id, cwd, permissions, state}
```

OpenCode is `kind = agent_runtime`. It is never represented as a model, never given a `model_id` of its own, and never enumerated in a model list. It may appear beside models in the operator's picker — that is presentation. The record underneath keeps `backend: opencode` and `model_ref` separate. A `null` `model_ref` is legal only for `backend ∈ {powershell, none}`.

### 4.3 Discovery is never fabrication

Every entry in either registry carries `discovered_by` naming the command or file that produced it, and `availability` reflecting an actual probe. A model that the host does not expose is absent from the registry — not present-and-greyed, not present-and-hopeful.

Grok specifically: **whatever the host's configured `grok_build` CLI enumerates at discovery time is what the registry contains, and nothing else.** A prior spawn record is not availability — the three `grok-4.6` records in §2 are `SPAWNING` with `pid: null`, which attests that the model reference was *selectable*, not that a session ever ran on it. Neither `grok-4.5` nor `grok-4.6` is written into a source list on the strength of this document, of the operator's request, or of a historical event log. If the CLI enumerates them, they appear; if it does not, the discovery artifact records what it actually returned and the corresponding goal is satisfied by that truthful record.

### 4.4 RUNNING requires evidence

For every module the shell manages, `READY` requires a readiness probe that observes the module answering, and `STOPPED` requires evidence the runtime terminated. `process_window` — "the process was alive one second after spawn" — does not satisfy this and is retired for SOW under the work order. Distillery and Token Center are installed with real `http` readiness and `http_json` identity from the outset.

### 4.5 Human authority is unchanged

`HUMAN OPERATOR → CONDUCTOR → ORCHESTRATION → WORKERS`. The Conductor coordinates within operator-set bounds. Worker creation, model selection, execution authorization, interruption, termination, and acceptance remain operator-controlled. Nothing in this addendum grants an agent authority to promote a gate, accept a result, authorize spend, or widen its own envelope.

### 4.6 Visual identity is pinned

`docs/THEME-BASELINE-v3.md` governs everything rendered in the shell, including the Token Center surface. The Sovereign token set (`--accent: #7fc8e8`, `--bg: #0b0e14`, the 4/8/12/16/24 spacing scale, no gradients, no glow, outline-only focus) is not negotiable. The standalone Token Center at `D:\Token Piggy Bank\` keeps its own identity; the copy surfaced inside Sovereign is re-skinned to Sovereign tokens. Every text pairing introduced holds ≥ 4.5:1 in both themes, proven by the existing H-16 machinery.

---

## 5. Gates added

Appended to `evidence/GATE-LEDGER.json` as new keys. Gates 0–7b are never altered. Builder-writable statuses remain `CANDIDATE`, `NOT_REACHED`, `STOP`.

| Gate | Name | Requirements |
|---|---|---|
| `8a` | Implementation map (read-only) | Phase 1 |
| `8b` | Module lifecycle and runtime truth | R-01, R-02, R-15 |
| `8c` | Session container and model selection | R-03 |
| `8d` | Conductor operator channel | R-04 |
| `8e` | Conductor ↔ worker round-trip | R-05, R-06 |
| `8f` | OpenCode execution backend | R-07, R-08 |
| `8g` | Model / execution registry | R-09, R-10 |
| `8h` | Distillery runtime and UI | R-11, R-12 |
| `8i` | Token Center integration | R-13, R-14 |
| `8j` | End-to-end acceptance | scenario A–H, R-15 |

Gate 8a is a precondition of every other gate in the band. Gates 8b–8i may be submitted as they complete. Gate 8j requires 8b–8i to be `CANDIDATE` or better and is the only gate whose evidence is a recorded live run rather than an artifact set. Promotion beyond `CANDIDATE` remains reviewer and operator business.

---

## 6. Regression safety

R-15 is not a checkbox at the end. It is a standing obligation:

- The full README test suite passes at every gate submission, ending `OK`, with a count ≥ the 122 recorded at Gate 7a. A test that must change to keep passing is a design change and requires its own justification in the gate note.
- `shell/BUILD-MANIFEST.txt` is regenerated per the suite's own rule and its entries equal live file hashes.
- Protected-tree manifests are captured before the first mutation and re-verified at every gate, `fc /b` clean.
- `app.css` v3 identity holds: any drift in the pinned `:root` token values is a STOP, not a fix.
- The four modules' existing behaviours — SOVEREIGN on :5175, Debate on :8700, EXTERNAL non-interference (H-9), job-object containment, CSRF/Origin/Host guards, the H-3 header set, redaction at all four surfaces — are unchanged and re-proven.

---

## 7. Carried defects — visible, deliberately not in scope

Recorded so they are not silently absorbed, and not silently fixed:

| # | Defect | Evidence | Disposition |
|---|---|---|---|
| C-1 | `to_dict()` hardcodes `"port": ""`; `urlForPort` and the port-display branches are dead code | FACT[`shell/src/states.py:300`], FACT[`shell/static/app.js:183-191`] | Carried. May be repaired only if a CP-01 goal requires port display, and then counted against the cap. |
| C-2 | `GET /api/logs/<id>` returns 200 + empty for an unknown id instead of 404 | FACT[`shell/src/server.py:286-288`] | Carried. |
| C-3 | Malformed adapter JSON is keyed by filename, so it vanishes from the UI instead of showing `CONFIG_ERROR` | FACT[`shell/src/adapter.py:398-409`] | Carried. |
| C-4 | Light theme does not redefine `--input`, `--radius`, `--font`, `--mono` | FACT[`shell/static/app.css:33-48`] | **Conditionally in scope.** `--input` becomes load-bearing the moment an input surface enters `shell/static`. If CP-01 introduces one, defining `--input` in the light block is authorized, capped at 1 line, and requires a contrast proof. The other three stay carried. |
| C-5 | Distillery card's links are bare `D:/...` paths in `href`, unresolvable from an http page | FACT[`shell/src/distillery.py:121-125`] | In scope under Gate 8h — the Distillery surface is being rebuilt. |
| C-6 | `startedAt` is not projected onto `operationalNodeStatus` | FACT[`modules/sow/apps/desktop/control/operational-state.js:36-66`] | In scope under Gate 8e — the directive requires creation time on the worker registry. |
| C-7 | Token Center `--host` is CLI-overridable with no loopback enforcement; `POST /api/refresh` has no CSRF guard | FACT[`D:\Token Piggy Bank\piggybank.py:844-845,820-829`] | In scope under Gate 8i for the `modules/tokencenter/` copy only. The operator's original is never edited. |

---

## 8. Stop conditions this addendum adds

Beyond `AGENTS.md` §13 in full: `ENVELOPE_EXCEEDED` (any §3.2 cap) · `INSTALL_REQUIRED` (a step needs a package download) · `SPEND_REQUIRED` (a step needs a paid provider without authorization) · `PROTECTED_SOURCE_CHANGED` (any §3.1 protected tree moves) · `PREMISE_CONTRADICTED` (§2.1 evidence is found to be wrong on disk — the builder records the new fact and stops rather than choosing a premise) · `ARCHITECTURE_CONSTRAINT_UNSATISFIABLE` (a §4 constraint cannot be met without violating another).

Every STOP writes the report path the work order names, with the `FACT[...]` condition, the exact conflict, why proceeding requires interpretation, and 2–3 bounded operator options. Then stops.

---

## 9. Issuance

This addendum carries no authority until the operator sends the following sentence in session, and the builder logs it verbatim with the UTC of receipt into `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation:

```
OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-01 v1.0 is issued as written; the CP-01 envelope, the two module installs, and gates 8a-8j are authorized; stage pauses waived; no provider spend authorized.
```

If that sentence is absent from the message delivering the work order, the builder STOPs `PRECONDITION_UNSIGNED` and does nothing else. The addendum's §2.1 corrections and §4 constraints bind from the moment it is issued and are not waivable by anything short of a versioned successor to this file.
