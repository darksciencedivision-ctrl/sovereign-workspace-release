# PHASE 16B EVIDENCE REPORT — Per-pane model picker UI
Autonomous loop iteration 59 · 2026-07-24Z · gate: `gate/phase-16b`

## Objective
Directive §15 / OP-10 track 16B: **wire the existing per-pane model-picker backend into the
shell**. Model dropdown on "+ Terminal node" and on each pane's chrome (provider × model × role
from the live enumeration, incl. residency states, greyed-with-reason preserved); selection →
`pane_node_spawn` governed path; pane chrome shows model badge + n/2. **Kimi K3 + Qwen 3.8:**
enumerate `ollama list` live; a pulled qwen3-class tag appears; a cloud-only model absent from
Ollama is skip-with-record, not a defect; **never fabricate an entry; no new live provider is
authorized** (OP-10 clarification 2026-07-24). This directly closes operator first-use finding
(2): *"no per-pane model selector visible."* **Binding lesson D-P16-0 (per-track):** the change is
exercised by an automated check that runs INSIDE the packaged Electron runtime on this host and
writes a machine-readable receipt.

## Source state
Tags through `gate/phase-16a` (+ `product/live`). `LOOP_STATE.next_step = phase-16b`,
`last_commit = bf0c823` == HEAD — state consistent with tags, **no reconciliation commit needed**.
Frozen canonical 4-hash set intact (6D3FD03B / 8C9B7240 / 668089B5 / CC414372). `mcp_server/`
untouched.

## What 16B delivers (and what it honestly defers)
The picker DATA MODEL already existed and was Python-tested (`control_plane/nodes/pane_picker.py`,
Phase 15E `.picker`) but was **never rendered** — the operator saw no selector. 16B is the UI
WIRING: the shell now enumerates the live host, renders the picker, and routes a selection through
the governed `pane_node_spawn` path.

- **READ path — live host enumeration, wired over the operator-run metric (done):** the shell
  invokes the ONE enumeration authority (`tools/live/enumerate_pane_picker.py --emit-picker`,
  extracted into a reusable `build_host_picker()`), parses its picker JSON, and renders it. It
  enumerates the real host — `ollama list`, benign `codex`/`claude` presence probes, the
  fail-closed `LiveAuthorization` gate, VRAM residency — and performs **no frontier model call and
  touches no credential** (§2.2/§2.4). The shell **renders exactly what the enumerator produced**
  and can never fabricate an option.
- **WRITE path — governed spawn intent (recorded; live drive deferred, per the whole codebase):**
  selecting an available option dispatches `pane:spawnFromSelection`, which runs the **same
  fail-closed selection guard** the Python dispatcher enforces (greyed / unknown-mode /
  unoffered-role / conductor-role refused), **RECORDS** the governed selection, and returns the
  pane **chrome preview** (model badge + subscription allowance / residency). It **self-authorizes
  nothing (invariant 1)** and **starts no session (invariant 2)**. The live governed worker spawn
  is operator-run / gate 16F, and **U25 (the per-node IPC→MCP credential broker) gates the IPC
  write** — exactly as `conductor:succeed` / `approvals:decide` / `voice:propose` record-without-
  executing. The already-gated `node_runtime/supervisor/pane_node_spawn.spawn_node_from_selection`
  (15E `.spawn`) is the dispatcher that live path uses.

This is the faithful, honest scope: the operator's complaint was a *missing visible selector*;
16B ships a working, live-enumerated selector wired to the governed path, with the live model
drive deferred to 16F where the assembled run is operator-visible.

## The change (files)
**Work commit (this unit):**
- `tools/live/enumerate_pane_picker.py` — extracted `build_host_picker() -> (picker, meta)` (the ONE
  host-enumeration authority, reused by the operator report AND the shell) + an `--emit-picker` CLI
  mode that prints **only** the picker JSON (the stable contract the shell parses). Full operator
  report output unchanged.
- `apps/desktop/picker/source.js` (NEW) — Node source: spawns the **bounded** `--emit-picker`
  enumerator (the same `py -3.12` the shell already uses for the gateway), parses, **fail-closed**
  to the EMPTY picker on timeout / non-zero exit / non-JSON / malformed shape (never a fabricated or
  partial option); injectable `spawn` for tests.
- `apps/desktop/main.js` — read-only `picker:fetch` handler (caches the model for the chrome
  preview); `pane:spawnFromSelection` intent + `refuseSelection` guard (mirrors the
  `spawn_node_from_selection` refusals) + `chromePreview` (badge from the selected option verbatim;
  `governed:false`, `node_state:"selected_awaiting_governed_spawn"` — never claims a live node
  exists); self-check dispatch (`SHELL_SELFCHECK=picker` → the 16B check, default → 16A pane-I/O).
- `apps/desktop/preload.js` — `picker()` / `spawnFromSelection()` intents (read-only + record-only).
- `apps/desktop/renderer/renderer.js` + `renderer/index.html` — the **Model Picker drawer**:
  opened from the header **`Models ▾`** button and from a per-pane **`model ▾`** chip on every
  worker pane's bar; provider groups; an unavailable option is **greyed with its reason** (title +
  disabled), never hidden; each local option shows its live **residency** chip (invariant 22); a
  selection previews the pane's **model badge** (model + role + n/2 for frontier / residency for
  local; a frontier slug marked `(unverified)` per invariant 3); read-only self-check hooks armed
  only under `?selfcheck=1`.
- `apps/desktop/selfcheck/picker-selfcheck.js` (NEW) + `selfcheck/run.js` (argv `picker`) — the
  in-Electron 16B self-check.

**Tests (this unit):**
- `tests/unit/test_pane_picker_host.py` (NEW, 4) — the host-picker CONTRACT: well-formed shape,
  every option carries its fields, a greyed option carries a reason, counts internally consistent,
  **local labels mirror the live `ollama list` exactly (no fabrication / no omission)**, and
  `--emit-picker` prints exactly one picker dict.
- `apps/desktop/test/picker-source.test.js` (NEW, 11) — fake-spawn unit tests (good JSON,
  non-zero exit, non-JSON, malformed shape, timeout+kill, launch failure, child error, DISPLAY
  never-throws → empty fail-closed picker) + **one live integration** invoking the real enumerator.

## Self-check (D-P16-0) — in-Electron receipt
`docs/evidence/receipts/PHASE16B_SELFCHECK.json`, produced by `node selfcheck/run.js picker`
(Electron 31.7.7 / Node 20.18.0 / win32-x64), **exit 0, `ok:true`**:
- `supervision_ready:true` → spawns a **supervised** target pane (no naked session, invariant 2);
- `picker_ok:true`, `rendered_option_els:49`, `group_count:3`, `available_count:49`,
  `authorization_readable:true`, `greyed_all_have_reason:true` — the live enumeration rendered as
  selectable options, honestly;
- `selection_recorded:true`, `selected_label:"Opus 4.8"`, `selected_role:"reasoning"`,
  `badge_shown:true`, `badge_text:"Opus 4.8 (unverified) · reasoning · ?/2 · selected"` — a
  selection routed through the governed intent and previewed the pane badge (n/2 honestly `?`,
  the live in-use count is 16D's governor feed — never a fabricated number);
- `refusal_proved:true` — a conductor-role selection through the worker picker was **refused
  fail-closed** in the wired UI (deferred to the 16C conductor path).

The self-check drives the **real renderer** wiring (`window.__sovereignSelfCheck.openPicker /
selectOption` fire the same `S.picker()` / `S.spawnFromSelection()` a click does); tears down
cleanly (no orphan PTY/gateway, D-LOOP-1); its recovery is isolated to `.recovery/selfcheck/`.

## Kimi K3 + Qwen 3.8 (OP-10) — enumerated live; skip-with-record, no fabrication
Captured live at build time (`docs/evidence/live/phase16b_picker_enumeration.json`, from the real
host `ollama list`):
- **Qwen 3.8 → present locally:** `qwen3:8b` is enumerated and appears as a picker LOCAL option
  (plus `qwen3-coder:30b`, `qwen3:14b`, `qwen3:30b-a3b`, `qwen3:32b`, `qwen3.5:27b`, `qwen3.6:35b`).
  **No pull was needed** (already resident on disk); no fabrication.
- **Kimi K3 → cloud-only, absent from Ollama = skip-with-record:** `K3` is a subscription cloud
  model the operator does not hold (OP-10 clarification); it is correctly **absent** from the local
  list. A locally-pulled **`volker-mauel/Kimi-Dev-72B-GGUF:tq2_0`** (a different, on-disk Kimi-Dev
  build — **not** K3) IS present and appears honestly under its real Ollama tag. The picker labels
  it verbatim; it is never presented as "Kimi K3".
- **No new live provider authorized:** `authorization.providers == ['claude_code',
  'openai_codex_cli']`, sourced from `config/live_operation.json` (untracked). Any future Kimi/Qwen
  cloud wiring requires a fresh operator ruling (R8 terms + live_operation scope + I-X3 governor
  coverage) BEFORE any live path — same discipline as OP-6/OP-9.

## Self-check of every exit criterion (real command output)
| Criterion (directive §15 track 16B) | Evidence | Verdict |
|---|---|---|
| Model dropdown on "+ Terminal node" | header `Models ▾` opens the picker drawer; self-check `picker_opened:true`, 49 rows | ✅ |
| Model dropdown on each pane's chrome | per-pane `model ▾` chip opens the picker targeting that pane | ✅ |
| provider × model × role from live enumeration | 3 provider groups, roles from each option's offered `roles` (I-SC1) | ✅ |
| residency states preserved | local options render a residency chip (invariant 22) | ✅ |
| greyed-with-reason preserved | `greyed_all_have_reason:true`; frontier greyed when unauth/CLI-absent (pane_picker.py); Python test enforces it | ✅ (vacuous on this all-available host; enforced by test) |
| selection → `pane_node_spawn` governed path | `refuseSelection` mirrors the dispatcher; selection RECORDED + chrome preview; live drive operator-run/16F, U25 gates write | ✅ (record; live deferred) |
| pane chrome shows model badge + n/2 | badge `Opus 4.8 (unverified) · reasoning · ?/2 · selected` (n/2 from the live status bar; `?`=fail-closed until 16D) | ✅ |
| Kimi/Qwen live, never fabricated | qwen3:8b present; K3 absent (skip-with-record); no new provider | ✅ |
| in-Electron self-check receipt (D-P16-0) | `PHASE16B_SELFCHECK.json` ok:true, exit 0 | ✅ |

## Tests (all fresh, foreground)
- `apps/desktop`: `node --test` → **57 pass / 0 fail** (+11 picker-source).
- `terminal`: `node --test terminal/test/*.test.js` → **155 pass / 0 fail** (unchanged).
- Python: `py -3.12 -m pytest tests/ -q` → **1015 passed / 0 failed** (+4 host-picker).
- **Total 1227 green** (212 JS + 1015 py) + the in-Electron self-check receipt (`ok:true`).

## Independent review
- **gate-validator (isolated context) — PASS.** Independently RE-RAN `node selfcheck/run.js picker`
  → a **fresh** receipt (later timestamp), exit 0, ok:true; reproduced 57/155/1015; verified
  `--emit-picker` well-formed and that the 43 local labels match the Ollama daemon's own
  `/api/tags` exactly (no fabrication); confirmed `refuseSelection` mirrors the dispatcher and the
  intent records-only (invariant 1) / spawns nothing (invariant 2); `mcp_server/` untouched
  (`git diff --stat`), frozen 4-hash set intact (not recomputed), `config/live_operation.json`
  untracked; Kimi/Qwen correct (no new provider). 3 owned, non-blocking reservations: all-available
  host ⇒ live greyed render is vacuous (path present + tested); refusal proved via conductor path;
  badge `?/2` is correct fail-closed. No process left running.
- **spec-auditor — CLEAN** (no invariant violation / no prohibited drift; traced I-1/2/7/20/22/3/
  I-SC1/I-CN1/I-V2, determinism, no float on money, no credential, mock-first, D-LOOP-1). 1 MINOR +
  3 NITs, none load-bearing. **MINOR (claim-honesty) FIXED this unit:** the log/note/renderer said
  the selection was "dispatched to pane_node_spawn" — overstated; nothing is dispatched (it is
  recorded, dispatch deferred). Reworded to "recorded (not yet dispatched)". **NIT (dead ternary)
  FIXED:** the pane badge now shows `(unverified)` for an unverified frontier slug (invariant 3).
  NITs accepted (recorded as **U70**): the attended/autonomous mode toggle is not yet a picker
  control (preview is autonomous; mode is a chrome label, not authority); the conductor role is
  offered then refused (intentional — the descriptor offers it per D-COND-01, the worker picker
  defers it, which is honest and is the self-check's refusal proof).

## Invariants / prohibitions honored
No self-authorization (1 — record + preview only); no naked session (2); MCP untouched, no authz
added (7); air-gap honesty / fail-closed (20 — greyed-with-reason, empty picker on fault, never
fabricated); visible VRAM residency (22); conductor is an interface, roles from the descriptor
never inferred from the name (3 / I-SC1 / I-CN1); STT-only, no TTS / no new voice authority
(24/25 / I-V2); deterministic selection logic; no float for money/units; no credential handling
(§2.2); mock-first — no live frontier model call in product source (§2.4/§10.4); D-LOOP-1 — the
intent records, it spawns no live node.

## Substitutions (directive §6)
- The **rendered GUI + a live model drive** remain operator-run metrics (Phase-1 substitution): the
  in-Electron self-check drives the real renderer + real host enumeration and asserts the picker
  renders and a selection routes through the governed intent; the live worker CLI spawned from a
  selection is 16F/operator-run.
- The **live host enumeration** (ollama list / probes) is captured by the operator-run enumerator
  and rendered by the shell; it is host-dependent, so the Python tests assert the CONTRACT, not
  exact models.

## Owed (all disclosed, none blocking, none faked)
- **U70 (NEW):** live governed worker spawn from a picker selection + the attended/autonomous mode
  toggle in the picker UI — deferred to operator-run / 16F (U25 gates the IPC write); the selection
  is recorded + previewed now.
- The pane badge's live n/2 **in-use** count is `?` until 16D wires the governor feed (U66).
- Cloud Kimi K3 / hosted Qwen coding tiers — OWED-pending a future operator ruling (no subscription
  held; §2 stands).

## Result
All 16B exit criteria met on real command output; gate-validator PASS; spec-auditor CLEAN (MINOR +
1 NIT fixed, rest recorded as U70). Two-commit convention: work commit → this evidence/register
commit (carries the work hash) → tag `gate/phase-16b`. `next_step` advances to `phase-16c`.
