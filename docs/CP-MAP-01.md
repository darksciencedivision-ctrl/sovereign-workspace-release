# utc: 2026-08-25T18:05:00Z
# producer: ox-alpha CP-M1 Band 1

# CP-MAP-01 — Implementation map and requirement classification (Gate 8a)

Every citation below was verified by the builder reading the named file at the named lines
this session (2026-08-25T17:45-18:05Z), not inherited from any earlier reconnaissance.

## 1. Runtime inventory — what exists on disk (the implementation map)

### 1.1 Shell launcher architecture
- FACT[shell/src/server.py:452] `main(argv)` builds the HTTP server; FACT[shell/src/server.py:485] `server.serve_forever()` starts the listener; FACT[shell/src/server.py:379] `_poll_loop` polls runners on an interval. Nothing in `main()` calls `start()` on any runner — modules begin STOPPED/NOT_STARTED/CONFIG_ERROR per FACT[shell/src/states.py:80-86] (`error` -> CONFIG_ERROR; `state_class == "not_started"` -> NOT_STARTED; else STOPPED).
- Launch requests are executed by FACT[shell/src/server.py:321] a daemon thread targeting `_start_worker`, defined FACT[shell/src/server.py:325].
- The eight-state machine is declared at FACT[shell/src/states.py:18-25].

### 1.2 Every place a browser is or could be opened
- FACT[shell/static/app.js:628] `window.open(rec._url, "_blank", "noopener")` — the only module-browser open, handle discarded (orphan tabs possible).
- FACT[Start-Shell.ps1:100] `$url = "http://127.0.0.1:$Port"` — Start-Shell opens a browser FOR THE SHELL ITSELF.
- ABSENT: grep for `webbrowser` across shell/src returns zero hits — the Python backend never opens a browser.

### 1.3 Module runtimes and their launch paths
- SOVEREIGN: workspace-owned instance launched from `modules/sovereign` (adapter shell/modules/sovereign.json, compiled argv under `${root}/.venv/Scripts/python.exe`).
- Debate: FACT[shell/modules/debate.json:13-15] argv `${root}/.venv/Scripts/python.exe app.py`; readiness http GET `/` on 8700 (:26-31).
- SOW: Electron instance under `modules/sow/apps/desktop` (adapter shell/modules/sow.json); readiness today is FACT[shell/modules/sow.json:32] `"kind": "process_window"` with identity `process_image` (:37) — retired under G15.
- Distillery: no runtime; file parser only, see 1.8.

### 1.4 SOW terminal implementation and its PTY boundary
- FACT[modules/sow/apps/desktop/main.js:478] `const file = spec.file || (IS_WIN ? "powershell.exe" : "bash");` — the implicit PowerShell default at the PTY boundary.
- FACT[modules/sow/apps/desktop/main.js:483] `pty.spawn(file, spec.args || [], {...})` — the sole PTY creation point.
- FACT[modules/sow/apps/desktop/main.js:2750] the Conductor autolaunch gate: skipped under SHELL_SELFCHECK, refused unless `SOW_CONDUCTOR_AUTOLAUNCH === "0"` is absent — HC-7/H-10 boundary.

### 1.5 Conductor implementation and its input surfaces
- Operator text input: ABSENT. grep of `modules/sow/apps/desktop/renderer/index.html` for `<input|<textarea|contenteditable` returns zero element hits — only CSS classes for conductor panes (FACT[renderer/index.html:36-56], e.g. `.pane.conductor .cptt` push-to-talk styling at :52). Operator text reaches the Conductor only as PTY keystrokes/voice.
- Dispatch feed: FACT[modules/sow/control_plane/orchestration/conductor_dispatch.py:65] `LIVE_WORKERS_OWED` dict; mock-first dispatch documented at :13-19.
- Round-trip machinery: MCP tools over the loopback control server — FACT[modules/sow/mcp_server/sovereign_tools.py:244-249] (`spawn_worker`, `get_worker_status`, `assign_task`, `send_message`, `read_messages`); control-server surface listed at FACT[apps/desktop/control/sovereign-control-server.js:22-23]; server bind/listen flow at :184-194.
- Conductor model registry: FACT[modules/sow/control_plane/conductor/registry.py:80] `CONDUCTOR_MODEL_REGISTRY` with three registrations — `openai_codex_cli/gpt-5.6-sol` (:84-86), `claude_code/fable-5` (:92-94), `claude_code/opus-4.8` (:100-101); all `conductor_capable=True`, all frontier. No local conductor-capable entry exists (A-6 basis).

### 1.6 Worker registry and its projection gap
- Internal record: FACT[modules/sow/apps/desktop/picker/worker-spawn.js:61] `emptyRecord(paneId)`; occupancy rules `hasLiveSession` documented :92-95 and enforced :235-237 (`already holds a live session - close it before launching another model into it`).
- Control-surface projection: FACT[apps/desktop/control/operational-state.js:36] `operationalNodeStatus(record)` projects node_id/state/etc. (:40+) — `startedAt`/`created_utc` is not projected (defect C-6).

### 1.7 Model-registry and provider-configuration sources
- Roster (single place concrete models are named): FACT[modules/sow/adapters/roster.py:5] docstring claim; model tuples :23-24 (`_REASONING_MODELS`, `_CODER_MODELS`); `harness=None` deferred-OpenCode note :87-89.
- Picker aggregation: FACT[modules/sow/control_plane/nodes/pane_picker.py:130] `registered_providers()`; frontier subset :157-166.
- Provider authorization switch: `modules/sow/config/live_operation.json` — narrowed this session to `scope.providers = ["openai_codex_cli"]` (see evidence/cpm1/spend-reconciliation.txt). Code-pinned enforcement: FACT[modules/sow/control_plane/profiles/live_authorization.py:255-261] `load_live_authorization` -> `_validate_providers(scope.get("providers"), ..., row_scope)`; FACT[live_authorization.py:271-295] row-ceiling validation; `assert_provider_live` :170.

### 1.8 Distillery entry points as they exist
- FACT[shell/src/distillery.py:11] `HANDOFF_PATH = "D:/Sovereign Distillery/CANONICAL-HANDOFF.md"`; status literal FACT[distillery.py:38-39] `status = "not started"`; public surface FACT[distillery.py:103] `get_distillery_status()`. No runtime, no health route.

### 1.9 Token Center architecture (operator's live copy, protected)
- FACT[D:/Token Piggy Bank/piggybank.py:16] stdlib `ThreadingHTTPServer`; routes `GET /api/summary` :789, `GET /healthz` :797, `POST` handler :820; CLI-overridable bind :844-845 (`--host` default 127.0.0.1, `--port` default 8765); server construction :858. Live owner of 8765 identified at evidence/cpm1/baseline/port-8765-owner.txt (pid 30608, command line `piggybank.py --host 127.0.0.1 --port 8765`).

### 1.10 Inference stack (existing, to be widened not replaced)
- Backend Protocol: FACT[modules/sow/adapters/base/backend.py:26-29] `class Backend(Protocol)` with a single `generate()`; Ollama implementations at :60 and :82 (HTTP POST to the local Ollama endpoint).
- Capability vocabulary: FACT[modules/sow/schemas/node.schema@1.1.json:41-56] `capability_descriptor` with `tool_use`, `min_context`, `locality`, `harness_class`.
- Vendor-blind resolver: FACT[modules/sow/scheduler/resolver/resolver.py:3-6] descriptor-only doctrine; hard filters `min_context` :39-40 and `harness_class` :41-44.
- Residency planner: six states FACT[scheduler/residency_planner/residency_planner.py:33-38]; invariant-22 header :1-6; explicit no-GPU-handle limitation :10 ("holds NO GPU handle and makes NO real VRAM measurement").

### 1.11 OpenCode's installed state on this host
- PRESENT: `opencode.ps1` resolves on PATH at `C:\Users\Sslaw\AppData\Roaming\npm\opencode.ps1` (npm shim; both `opencode` and `opencode.ps1` resolve to the same shim). Governed spawn path already in-tree: FACT[modules/sow/node_runtime/supervisor/opencode_spawn.py:1] ("the ONE place a supervised OpenCode coding harness is born").

## 2. Requirement classification R-01..R-15 (builder's own disk evidence)

| ID | Requirement | Evidence (this session) | Classification |
|---|---|---|---|
| R-01 | No module autostarts; EXTERNAL is legible | server.py:452-485 builds+polls only; states.py:80-86 initial states; app.js:628 handle discarded | implemented-and-verified (autostart absence) / partial (EXTERNAL legibility: DOM rendering of EXTERNAL distinctness not yet captured) |
| R-02 | READY/STOPPED require observed evidence | sow.json:32 still `process_window` | implemented-but-defective |
| R-03 | Terminal is a session container; no implicit PowerShell | main.js:478 implicit default; worker-spawn.js:235-237 refusal string | absent |
| R-04 | Persistent operator->Conductor channel with transcript | index.html:36-56 CSS only, no input element; registry.py:80 three frontier entries | absent |
| R-05 | Machine-readable worker registry incl creation time | operational-state.js:36-66 lacks startedAt projection | partial |
| R-06 | Conductor->worker delivery proven live | sovereign_tools.py:244-249 tools exist; LIVE_WORKERS_OWED at conductor_dispatch.py:65 | implemented-but-defective (mock-first feed) |
| R-07 | OpenCode reachable as execution backend | opencode_spawn.py:1 governed path; roster harness=None :89 | partial |
| R-08 | Backend never confused with model | picker/roster keep separate kinds; no `model_id` for backends found in nodes/adapters grep | implemented-and-verified |
| R-09 | One canonical registry serves every selector | registry.py:80 + roster.py:23-24 + pane_picker.py:130 three separate sources | absent |
| R-10 | Discovery is never fabrication | live_operation.json + live_authorization.py:271-295 enforce scope; roster enumerations static | partial |
| R-11 | Distillery operable runtime under Option A | distillery.py:38-39 literal not_started; no launch block | absent |
| R-12 | Distillery UI console, theme-true | card buttons disabled client-side; no console surfaces exist | absent |
| R-13 | Token Center integrated centrally under Option A | piggybank.py:844-845 CLI-overridable host/port; runs from protected tree | absent |
| R-14 | No credential surface introduced | piggybank.py reads ledgers only; no auth code found :787-858 | implemented-and-verified (by absence, S-2) |
| R-15 | Standing regression obligation | test-run-before.txt Ran 122 OK this session; BUILD-MANIFEST 40/40 equal | implemented-and-verified |

## 3. Conformance with the settled facts (CP-M1 §3)

No row above conflicts with any settled fact S-1..S-12. Host-fact observations recorded this session that
update older captures without contradicting any settled premise: Ollama reports v0.32.14
(baseline evidence/cpm1/baseline/ollama-version.txt; older assessment cited 0.32.6); free
VRAM at fresh capture 6212 MiB of 8151 (host-hardware.json; S-5's ~5383 MiB was a stale
point-in-time value; GPU identity RTX 5060 Ti sm_120 matches S-5 exactly). Port 8765 owner
identified as the operator's Token Center (port-8765-owner.txt), matching assessment §6.1.

BUILDER NOTE: Band 1 is read-only; no product edit occurred. Artifacts: this file plus
evidence/cpm1/** only.