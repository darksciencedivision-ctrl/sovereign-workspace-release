# AUTONOMOUS BUILD DIRECTIVE — DIRECTED PROMPT LOOP
**Issued by:** the operator (Sam), 2026-07-16, in-session ruling.
**Executed by:** Claude Code, iteratively, via `tools/loop/run_loop.ps1`.
**Reader contract:** Claude Code re-reads THIS FILE + `docs/loop/LOOP_STATE.json` at the
start of every iteration, executes exactly one work unit, updates state, commits, exits.

---

## 1. OPERATOR RULING (supersedes all interactive-stop requirements)

Recorded 2026-07-16 (decision register OP-1..OP-3): the operator has rescinded per-phase
interactive stops. The build proceeds **phase 0 → 13 as a loop with no operator
involvement**. Gates that previously required operator sign-off (Phase 0 freeze signature,
D-UI-01 framework ratification, D-LANG-01, D-PERSIST-01, D-MCP-03, D-IPC-01, per-phase
approvals) are **delegated**: close them automatically on recorded evidence, using the
canonical plan's recommendation as the default. Log every such closure in the decision
register as `decided_by: operator-delegation (ruling 2026-07-16)`. The operator is
notified **only** at COMPLETE or BLOCKED. Do not ask the operator anything else. All
evidence, registers, and tags are still produced — for retrospective review, not approval.

## 2. STANDING PROHIBITIONS (NOT waived — these are the only hard stops)

1. No `git push`, remotes, PRs, publication of any kind.
2. No credentials/secrets/API keys — never create, read, store, or transmit.
3. No purchases, sign-ups, or paid services.
4. No live frontier-provider subscription sessions: **frontier adapters run in mock mode
   for the entire build.** A local model via already-installed Ollama MAY be used if
   detected (no credentials involved); otherwise mock local too and record it.
5. Nothing modified or deleted outside the repo root; `docs/canonical/` never modified.
6. Registers and evidence reports are append-only. Git history is never rewritten;
   never amend a commit whose hash is already recorded anywhere.
7. `npm install` from the public registry and reads of vendor docs are the only network
   use permitted.

If a phase exit criterion is impossible without violating one of these, apply §6
substitution rules; only if no substitution exists → BLOCKED (§8).

## 3. LOOP PROTOCOL (every iteration, in order)

1. `git log --oneline` + `git tag -l` + read `docs/loop/LOOP_STATE.json`. **Tags are the
   truth**; if state and tags disagree, reconcile state to tags first, commit that fix.
2. Identify the current work unit (state `next_step`). A work unit is one phase, or one
   named sub-step of a phase for large phases (state lists them).
3. Read the exit criteria for that phase from `docs/canonical/Claude_Code_Buildout_Directive_20260716.md`
   §5 and the Architecture Plan v1.0.1 §7 (+ §15–17 where applicable). Plan briefly
   (extended thinking for P1, P3A, and any concurrency/fencing work), then implement
   test-first. Respect every invariant in `CLAUDE.md` (all 30).
4. Self-check every exit criterion with real command output. Then run the
   **gate-validator** subagent (`.claude/agents/gate-validator.md`) in an isolated
   context for independent confirmation; run **spec-auditor** on substantive new code.
   Validator FAIL → fix in this or the next iteration; never soften, never skip.
5. On PASS: write `docs/evidence/PHASE<N>_EVIDENCE_REPORT.md` (Directive §6 format;
   substitutions per §6 below explicitly listed), then the **two-commit convention**:
   work commit → register/evidence commit carrying the work hash → tag `gate/phase-<N>`.
   Auto-close any delegated decision that phase owns (register row, decided_by
   operator-delegation).
6. Update `LOOP_STATE.json` (`next_step`, `iteration`, `last_commit`, timestamps),
   commit it, exit cleanly. One work unit per iteration — do not sprawl.
7. Failure accounting: 3 consecutive iterations with no new commit on the same step →
   set state BLOCKED with a precise diagnosis (§8).

## 4. STATE FILE (`docs/loop/LOOP_STATE.json`)

`status`: RUNNING | COMPLETE | BLOCKED · `next_step`: e.g. `phase-2` /
`phase-1-autorun` / `phase-3a.conflict-test` · `iteration`, `consecutive_failures`,
`last_commit`, `notes[]`, and when BLOCKED: `blocked_reason`, `smallest_unblocking_action`.

## 5. PHASE SEQUENCE (work units; exit criteria live in the canonical docs)

| Step | Content | Loop-specific notes |
|---|---|---|
| `phase-1-autorun` | Retrofit `SPIKE_AUTORUN=1` mode to `tools/spike_compositor` (main process runs the full guided sequence programmatically: standard-6 → 60 s stream → latency probe → resize storm → layout storm → panes 7–8 → 60 s → report → quit). Run `npm install`, `npm test`, then the autorun **on this Windows host**. Parse `results/SPIKE_REPORT_*.json`. | No kill criteria triggered → record **D-UI-01 = Electron** (operator-delegation) + tag `gate/phase-1`. Any triggered → build the identical Tauri+portable-pty rig, autorun it, record comparative evidence, select per plan §16, then ratify by delegation. Also close the Phase 0 signature item if not yet closed (see register OP-2) and tag/verify `gate/phase-0` lineage intact. |
| `phase-2` | Node process manager (`control_plane/nodes/`): registry, state machine (SPAWNING/READY/ASSIGNED/BUSY/PAUSED/DISCONNECTED/TERMINATED), heartbeat, append-only event log, crash detect/restart. | Plan §7-P2 wants a 24 h soak; substitute an accelerated soak (≥30 min wall, time-compressed heartbeats, induced kills, 8 simulated nodes) + record the substitution. Python: use 3.12 if on host, else newest available; record version (D-LANG-01 closes by delegation here). |
| `phase-3` | Sovereign node runtime (`node_runtime/`): directive/role/permission loaders, supervisor containment scaffold, local gate, structured-output validation, workspace binding. Mock-model node passes/fails seeded defects; cannot write outside its workspace. | Containment = process-level enforcement on Windows (job objects / ACL-scoped worktree paths as feasible); record exactly what is and is not enforced (U10 stays open for P10 hardening). |
| `phase-3a` | MCP shared-memory foundation (`mcp_server/` + `persistence/`): separate loopback process, per-node auth, resource+tool catalogs (Plan §9.5), server-enforced memory lifecycle, provenance on every write, CAS artifact store, immutable append + CAS heads, **concurrent-writer conflict test**, fail-closed disconnect, conductor-replacement support, no authorization logic inside MCP. | All Directive §5-3A gate bullets must pass. Record **D-MCP-03 verdict** (delegation) + **D-PERSIST-01** (SQLite WAL + CAS store). Use official Python MCP SDK if installable from the registry; else implement the loopback protocol per schemas and record it (transport is U6). Mandatory gate-validator confirmation (high-stakes). |
| `phase-4` | First conductor adapter (`adapters/conductor/` + `adapters/base`): loads the 12 conductor files via MCP in declared order, runs the conductor loop, holds no credential. Backend = **mock reasoning model**. | Contract conformance suite (Plan §12.2) green; I-X3 governor active with mock subscription refs. |
| `phase-5` | Conductor + two workers end-to-end: capability-based assignment via Scheduler (`scheduler/`), one artifact routed CANDIDATE→gate→ACCEPTED, zero manual transcript routing, every hop provenanced. | Mock nodes. Plan gate + acceptance packet artifacts produced. |
| `phase-6` | Multi-model adapters: ≥3 backends behind capability descriptors — mock-frontier (claude_code-shaped), coding node (OpenCode+Ollama if both detected, else mock-coder), ≥1 local reasoning (Ollama if detected, else mock). | Selection demonstrably by descriptor, never by name. Live-subscription work and R8 ToS verification are **out of scope by prohibition §2.4** — record as deferred-live items in the register, not failures. |
| `phase-7` | Debate Service (`debate_service/`): any authorized node may request; ≤5 rounds; evidence-cited assertions; dissent preserved verbatim; budgets/quotas/global cap; clean budget-exhaustion cutoff. | §2.8 debate acceptance tests incl. non-conductor caller. |
| `phase-8` | Gate engine (`control_plane/gates/`): declarative criteria, verdicts referencing evidence/debate, failed artifacts cannot advance, no conductor override path. | Seeded-defect artifacts blocked at every stage boundary. |
| `phase-9` | Scoped context compiler (`control_plane/routing/`): role+task+need-to-know assembly from MCP; no full-transcript forwarding; measured token reduction vs naive baseline on a reference project. | Token counts measured with a real tokenizer if available, else byte/word proxy — record which. |
| `phase-10` | Coding worktree isolation: per-node git worktrees, controlled merge path (worker branch → gate → merge), cross-node mutation attempts fail and are logged. | NTFS ACL depth per U10: enforce what Windows allows without admin elevation; record limits honestly. |
| `phase-11` | Persistence & succession: full snapshot/restore; kill-conductor-mid-project test → Resume→Select (different mock model) → zero-loss reconstruction; succession cadence finalized (U11). | Mandatory gate-validator confirmation (high-stakes). |
| `phase-12` | Voice input service (`adapters/voice_parakeet/` + `voice_bridge/`): full VoiceAdapter interface, propose-never-execute command safety through the real Permission Broker, transcribe-then-discard + TTL diagnostic retention, typed/voice control-event equivalence. Engine = **mock STT** by default. | If NVIDIA GPU + WSL + NeMo are already present, wire real Parakeet; otherwise mock engine behind the same interface (I-A1 makes the engine swappable) and record U1/U2 as open-for-hardware. All §2.8 voice acceptance tests run against the broker path. |
| `phase-13` | Evaluation & hardening: comparative harness (single model / conductor+raw / Sovereign no-debate / Sovereign+debate) on the reference project with mock models; cost-to-accepted-output instrumentation report; kill-matrix recovery tests; hardening backlog triaged. | Report losses honestly; model-quality conclusions are limited to mock/local backends and must say so. |
| `finalize` | `FINAL_BUILD_REPORT.md` at repo root: per-phase gate table (tag + commit + verdict), every delegated decision closed, every substitution/limitation/deferred-live item, test totals, how to run the system, and what live-provider enablement would require. Tag `build/complete`. Set state COMPLETE. | This is the only moment the operator is addressed. |

## 6. SUBSTITUTION RULES (keep the loop honest AND unblocked)

When an exit criterion assumes something prohibited (live subscriptions) or absent
(GPU/WSL/NeMo/Ollama/24 h wall-clock), substitute the nearest faithful equivalent (mock
adapter behind the real contract, accelerated soak, mock STT engine), **run the full
governance path around it** (broker, gates, provenance — those are the system under
test), and record the substitution in the phase evidence report AND the final report.
Never present a substituted result as the real-provider result. Never silently skip a
criterion.

## 7. QUALITY BARS (unchanged from the buildout directive)

Deterministic code for permission/gate/lifecycle logic; Decimal for money/units; fail
closed on ambiguity; everything observable; test-first with an anti-overfit check by
subagent on substantive units; conventional commits, local only; evidence before tag.

## 8. TERMINAL STATES

- **COMPLETE:** all steps through `finalize` done, all `gate/phase-*` tags present,
  full test suite green, `FINAL_BUILD_REPORT.md` written, tag `build/complete`.
- **BLOCKED (only for):** credential/purchase/hardware needs with no §6 substitution,
  or an irreconcilable canonical-spec contradiction. State must carry `blocked_reason`
  + `smallest_unblocking_action`. Nothing else is a legitimate BLOCKED.

*End of autonomous build directive.*

---

## 9. PHASE 14 — PRODUCT SHELL AND LIVE ADAPTER INTEGRATION (adopted 2026-07-18)

Operator-endorsed next track (STATUS_RECONCILIATION_20260718.md). Same loop protocol
(§3), same prohibitions (§2) except where a track's entry condition explicitly lifts one.
Tags: `gate/phase-14a` … `gate/phase-14e`. A track whose entry condition is unmet is
**skipped-with-record** (register row + evidence note), never faked. Terminal state:
all executable tracks done → FINAL_PRODUCT_REPORT.md + tag `product/complete`;
promotion to `SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming is then operator-reserved.

| Track | Content | Entry condition |
|---|---|---|
| **14A — Product UI + IPC** (high-stakes gate: validator mandatory) | Real Electron/xterm.js/node-pty workspace in `apps/desktop` + `terminal/`: terminal canvas, pane create/destroy, dynamic tiling per Plan §10.2, maximize/restore/minimize/pin, status cards, routing/artifact inspector, approval-queue drawer; **authenticated loopback IPC** (D-IPC-01 activates: schema-validated envelopes, per-plan recommendation) to the existing control plane; UI recovery after process restart; ConPTY sessions supervised by the real Node Runtime (no naked sessions — the spike rig stays throwaway). Re-verify U9 with a real console TUI in a pane. | None — executable now (npm registry allowed; Electron vendored; D-UI-01 evidence in place) |
| **14B — First live frontier adapter (exactly ONE provider)** | Chain to prove: operator-authenticated provider CLI → supervised terminal process → Sovereign node identity → MCP context/artifact access → scoped assignment → structured result → gate. Before any live call: R8 ToS verification for that provider recorded; **introduce `LIVE_OPERATION_AUTHORIZED` as an enforced config flag read by the roster/profile loader (fail-closed)** — enforcement-by-absence ends the moment a live path exists. I-X3 = 1 terminal. Credentials stay in host-native stores, never in repo, never transit MCP. Do not integrate a second provider until the first is gated. Subscription-governor deep re-inspection is part of this gate. | Operator provides subscription auth on the host **and** explicitly lifts prohibition §2.4 for that one provider |
| **14C — OpenCode live local harness** | Prove OpenCode itself (not just the Ollama backend): supervisor-spawned OpenCode + local coder model, scoped MCP context, isolated worktree modification, tests run, CANDIDATE artifact submitted, controlled merge path passed. | OpenCode binary present on host (operator installs, or authorizes its download — outside the npm-registry-only rule) |
| **14D — Real Parakeet/NeMo** | NeMo in WSL2, host WASAPI→WSL mic bridge, real transcription; measure U1 (latency/VRAM under concurrency) and U2 (bridge/PTT); verify transcript disposal + typed/voice equivalence with the real engine; TTS stays absent. Only after 14A is stable. | Operator authorizes the WSL pip/NeMo install (network-prohibition amendment) |
| **14E — Product-level validation** | Assembled run: one conductor + one frontier worker (if 14B enabled) + one OpenCode/local worker (if 14C) + one local reasoning worker; live shared MCP state; visible panes; conductor replacement mid-run; one bounded debate; one gated coding task; full restart + recovery. Includes the two open verification receipts: on-host Ollama smoke re-run (item 7) and the assembled-system evidence. Degrades honestly to local-only if 14B/14C are skipped — and says so. | 14A complete |


---

## 10. OPERATOR AUTHORIZATION 2026-07-18 — PHASE 14 ENTRY CONDITIONS MET (register OP-4/OP-5)

The operator has approved completion of **Phase 14 in full, including all three
operator-gated items**. Effect, scoped precisely:

**10.1 — 14B enabled (one live frontier provider).** Prohibition §2.4 is lifted **for
exactly one provider: Claude Code** (selected by delegation, OP-5 — rationale: already
installed and authenticated on this host; the plan's designated first conductor-path
adapter, D-COND-01; zero new credentials created). Rules that still bind: the adapter
invokes the host's already-authenticated `claude` CLI and **never reads, extracts,
stores, or transmits the credential itself** (§2.2 stands in full); I-X3 = one terminal
on this subscription; R8 ToS verification recorded before the first live call; the
**enforced `LIVE_OPERATION_AUTHORIZED` config** must exist first — fail-closed, read by
the roster/profile loader, citing register row OP-4, scoped to `{provider: claude_code,
terminals: 1}`; no second provider without a new operator authorization.

**10.2 — 14C enabled (OpenCode).** Network prohibition §2.7 is widened to permit
downloading the **OpenCode binary from its official distribution source only** (plus
Ollama model pulls from the local daemon's standard registry if a required local coder
model is absent). Verify the download's integrity (checksum where published), record
source URL + hash in evidence.

**10.3 — 14D enabled (Parakeet/NeMo).** §2.7 widened to permit **pip installs of the
NeMo/Parakeet stack inside WSL2** (PyPI/NVIDIA indexes; no paid services, no accounts,
no API keys — CC-BY-4.0 checkpoint from its official model source, hash recorded, U4
attribution noted). If the environment cannot support the install (driver/CUDA/WSL
constraints), record precisely what failed and skip-with-record — never fake.

**10.4 — Unchanged.** Everything else in §2 stands: no push/remotes/publication, no
purchases or sign-ups, no credential handling, nothing outside the repo root,
registers/evidence append-only, canonical set frozen. Track order 14A → 14B → 14C →
14D → 14E; a failed entry attempt on B/C/D is recorded and does not block the rest;
14E degrades honestly to whatever subset proved live. Terminal state per §9:
FINAL_PRODUCT_REPORT.md + `product/complete`, then the operator is addressed once.

---

## 11. PHASE 15 — LIVE MULTI-MODEL ORCHESTRATION (operator authorization OP-6, 2026-07-19)

**Operator instruction (verbatim basis, register OP-6):** adapters for ChatGPT 5.5 Sol,
ChatGPT 5.5, Codex, Opus 4.8, Claude Code, and Fable 5 as starting points; **two CLIs per
subscription** with the same model allowed; finish the work — all models communicating
through the orchestrator over MCP, with the **conductor (always Fable 5 by current
selection, but agnostic and interchangeable) orchestrating and synthesizing**.

**Effect of OP-6:** (a) prohibition §2.4 is lifted for **two providers** — `claude_code`
(Anthropic CLI) and `codex` (OpenAI CLI) — live sessions under the operator's existing
subscriptions; (b) I-X3 allowance is raised to **2 terminals per subscription** by explicit
operator direction (R8 note: formally verified-at-1; the raise is operator-ordered, cap
stays governor-enforced and reversible; never exceed 2 without a new ruling); (c) the loop
MAY now create and maintain `config/live_operation.json` — OP-6 is the authorization the
14B restraint was waiting for; the file cites OP-6 and pins scope
`{providers: [claude_code, codex], terminals_per_subscription: 2}`; (d) §2.2 stands
unchanged: the adapters invoke the host's already-authenticated CLIs and never read,
store, or transmit credentials. Architectural note recorded: the six named models map to
**two provider adapters × per-node model selection** (I-SC1 — models are roster entries
with capability descriptors, never separate control paths).

Same loop protocol (§3), tags `gate/phase-15a..15e`, terminal state:
FINAL_LIVE_REPORT.md + tag `product/live`, operator addressed once. Track order:

| Track | Content | Notes / entry conditions |
|---|---|---|
| **15A — Live activation + concurrency governor** | Rewrite `live_authorization` scope per OP-6 (two providers, 2 terminals/subscription, cites OP-6); **create `config/live_operation.json`**; dated R8 records for both providers (documented basis + operator direction); subscription governor upgraded to per-subscription allowance=2 with the n/2 count live in the shell status bar; fail-closed paths re-tested (absence⇒DENIED unchanged). | High-stakes gate (validator mandatory). |
| **15B — Anthropic adapter: multi-model + conductor-capable** | Extend the live `claude_code` adapter with per-node model selection (`--model`); **probe the CLI's actually-available model IDs** and record the mapping for `opus-4.8`, `fable-5`, and the CLI default (unavailable ⇒ recorded fallback, surfaced in the roster — never silent); make the backend conductor-capable (the Phase-4 ConductorAdapter can bind it); one short live smoke per available model ref, sequential, minimal tokens. | Loop itself occupies one Anthropic session — run live smokes one at a time; usage-limit waits already handled by the runner. |
| **15C — OpenAI adapter (Codex CLI)** | Detect `codex` CLI presence + auth on host. Build the live adapter behind the same governed contract: non-interactive exec, per-node model selection for the GPT-5.5 line (**probe accepted model IDs** — operator named "5.5" and "5.5 Sol"; record what the CLI really accepts), worker roles reasoning + coding-specialist, `AGENTS.md`/config treated as node-controlled untrusted input (T2), env-scrub superset, worktree isolation for coding role; live smoke per available model. | **Entry condition:** `codex` installed + authenticated by the operator. If absent/unauthenticated: skip-with-record printing the exact one-time operator step (install command + login), continue to 15D with OpenAI legs OWED. |
| **15D — Live conductor (Fable 5 selection) + inter-model flow** | Conductor runs on the live Anthropic backend, `model_ref` = fable-5 if available else recorded fallback; `current_conductor` = `{model: fable-5, reason: operator_selected, since: 2026-07-19}` (selection preserved even when the executing checkpoint differs — record both). Prove the full governed loop with LIVE models: conductor decomposes an objective → Scheduler assigns by capability to live worker nodes (Anthropic + OpenAI if 15C live + local Ollama) → workers publish CANDIDATE artifacts over MCP → gates → **conductor synthesizes the ACCEPTED set into an acceptance packet**; one bounded live debate (budgets enforced — real tokens now); **live conductor succession**: kill the Fable-5 conductor mid-run, resume on a different backend, zero loss, then restore selection. | High-stakes gate. Cost governor budgets are hard caps; smoke-scale objectives only. |
| **15E — Node-launcher UI + visible assembled run** | Shell toolbar gains **governed node spawn**: pick provider × model (from the live roster) × role; spawns only through supervisor + governor (naked sessions still refused); pane chrome shows model badge, subscription n/2, node state, gate status. Visible validation: conductor + live workers in panes, **including two panes on the same model/subscription** (allowance=2 proof), one debate, one synthesized acceptance packet, restart recovery with panes reattaching. FINAL_LIVE_REPORT.md (which legs live vs owed, usage consumed, honest limits) + `gate/phase-15e` + `product/live`. | High-stakes gate. |

**Budget discipline (unchanged, now with real money-time):** per-debate hard budgets,
per-caller quotas, global cap; smoke tasks minimal; the runner's usage-limit wait applies;
never present a throttled/failed live leg as anything but what it was.

---

## 12. OP-7 AMENDMENT TO PHASE 15 (operator, 2026-07-19) — ordering + product surface

Operator additions (register OP-7), amending §11's tracks. **Revised order:
15A → 15C (OpenAI first, per operator) → 15B → 15D → 15E.** New requirements folded in:

1. **OpenAI first.** 15C runs immediately after 15A. Its entry condition stands: `codex`
   CLI installed + authenticated by the operator (`npm install -g @openai/codex`,
   `codex login`). If not yet done when 15C starts, poll/skip-with-record and proceed;
   re-attempt 15C before 15D closes.
2. **Per-pane model picker (extends 15E).** Every pane gets a model selector offering:
   both live provider adapters with their probed model IDs (Anthropic: Opus 4.8 / Fable 5
   / CLI default; OpenAI: the GPT-5.5 line incl. Sol as probed), **and the operator's
   entire local model list enumerated live from `ollama list`**. Selecting spawns a
   governed node through supervisor + governor (naked sessions still refused). Local
   models route through the **VRAM residency planner**: the picker shows residency state
   (resident / loading / awaiting-eviction), swaps are visible, never mid-generation.
3. **Interactive panes are governed nodes via native MCP attachment.** A pane the
   operator types into is an *operator-attended node*: the CLI is launched with a
   per-node scoped attachment to the Sovereign MCP server (both CLIs speak MCP natively),
   its own credential, role-scoped read/write, publishes as CANDIDATE like any node.
   Distinguish in chrome: `attended` vs `autonomous` mode. Headless worker nodes remain
   the conductor's normal instrument.
4. **Conductor-first startup.** On app launch: pane 1 auto-spawns as the conductor node,
   labeled **CONDUCTOR** (model badge = current selection: fable-5 or recorded fallback),
   pinned by default. Succession control (Resume→Select) reachable from its chrome.
5. **Operator command surface (was missing; plan §10.3 requirement).** Add to the shell:
   an **objective input** (operator types an objective → conductor decomposes → plan
   surfaces for approval) and the **approval-queue drawer** (plan gates, protected
   actions, clarifications, badge count). Without this the conductor cannot receive
   work or ask the operator anything — it is a 15E exit criterion now.
6. **Memory model confirmed, not changed:** one shared governed memory over MCP for all
   nodes (attended and autonomous); scoped context routing stays (invariant 8 — no
   blanket transcript forwarding); CANDIDATE→gate→ACCEPTED lifecycle stays; the conductor
   is the synthesizer; the Inspector remains the operator's all-seeing view.

15E exit criteria therefore now include: conductor-first labeled pane; per-pane picker
with live Ollama enumeration + residency states; one attended node (operator-typed) and
one autonomous node on the SAME subscription (allowance=2 proof); an objective entered in
the UI flowing through decompose → assign → CANDIDATE → gate → **conductor synthesis** →
acceptance packet visible in the Inspector; approval-queue exercised at least once (plan
gate); restart recovery restoring the conductor-first layout.

---

## 13. OP-8 (operator, 2026-07-19) — THE CONDUCTOR IS A LIVE CONVERSATIONAL CLI (binding correction)

**This section is authoritative over any earlier framing (esp. §12.5's "objective input")
that implied the operator submits jobs to the conductor via a form or a loaded file. That
was wrong. Delete that mental model.** `config/live_operation.json` is ONLY a one-time
"live sessions allowed" security switch — it has nothing to do with operator↔conductor
interaction and is never the way work is given.

**Concrete, non-negotiable conductor behavior (15D/15E exit criteria):**

1. **The conductor pane is a real, live, interactive agentic chat session** — the actual
   Claude Code (or the operator-selected Anthropic backend for the fable-5 role) running
   interactively in a ConPTY pane, exactly like the operator's normal Claude Code / ChatGPT
   experience. It opens as pane 1 on launch, labeled **CONDUCTOR**, and is immediately ready
   for conversation. No file, no batch, no "start the system" — the operator opens it and
   talks.
2. **Full live operator↔conductor conversation, in the moment:** the operator types into
   the pane and the conductor answers in the pane in real time (text); the operator can ask
   questions, direct research, give instructions, change direction mid-task, converse
   back-and-forth continuously — a chatbot/coworker/research-partner experience, not a
   request queue.
3. **File & context injection on the spot:** the operator can inject files/paths/pasted
   text into the conductor at any time (drag-drop or an attach affordance on the conductor
   pane → delivered into the conductor's context and, when it becomes shared truth, through
   MCP as a provenance-stamped artifact). No pre-loading, no restart.
4. **It orchestrates WHILE conversing:** the same conductor session, as it talks with the
   operator, dispatches work to the other live model CLIs (Anthropic/OpenAI/local nodes)
   over the shared Sovereign MCP memory, pulls their CANDIDATE results back through the
   gates, and **synthesizes** them into its replies to the operator. The operator watches
   this happen in the other panes and the Inspector, and can interject at any point.
5. **Voice INPUT to the conductor (Parakeet):** the operator can speak to the conductor;
   transcribed text enters the conductor's input on the same command path as typing
   (propose→approve for destructive/protected actions per I-V3; ordinary chat flows
   directly). This is a 15D/15E criterion.
6. **Voice OUTPUT (TTS) — FLAGGED, operator decision required, NOT auto-built.** The operator
   asked that the conductor "answer me… through the voice app." Spoken replies require TTS,
   which the **frozen canonical invariant I-V2 / D-VOICE-02 prohibits** ("voice input only;
   the system does not talk back") — set by the operator's own original directive. The loop
   MUST NOT silently add TTS. Build voice-IN + text-answer now (core). Spoken-answer is an
   explicit operator reversal of I-V2: if/when the operator confirms, record it as OP-9
   (reversing D-VOICE-02), pick a local/offline-capable TTS engine behind a swappable
   adapter (symmetry with the STT VoiceAdapter), keep it operator-togg=le, and add it as a
   16th track. Until that confirmation: TTS is OWED-BY-OPERATOR-DECISION, recorded, not faked.
7. **The conductor remains an interface (I-CN1):** current selection fable-5, swappable
   mid-conversation, succession-tested — but from the operator's seat it is simply a live
   partner they talk to. Interchangeability is under the hood; the conversation is the point.

**15E is not COMPLETE until:** the operator can open the app, land in a live CONDUCTOR chat
pane, type OR speak a request, watch it farm work to the other model CLIs and synthesize the
result back into the conversation, inject a file mid-conversation, and continue talking —
with no file-load or restart anywhere in that flow.

---

## 14. OP-9 (operator, 2026-07-19) — LIVE-TERMS CONFIRMED; PHASE 15D GOES LIVE

**Operator decision (AskUserQuestion, "Go live — run it"):** the operator confirms that
their **current** Claude Code and OpenAI/Codex subscription terms permit a supervised local
process (the conductor node) to invoke the first-party `claude` and `codex` CLIs under the
operator's own subscription, for the operator's own use. This **discharges the R8 §6 item-2
[OPERATOR] entry condition** for both providers — the exact item that BLOCKED gate/phase-15D
(recorded U56). It is the operator's determination, recorded here and in both R8 evidence
files; the loop did not and could not make it (invariant 1).

**Effect — the block is lifted and 15D re-runs LIVE:**
1. Clear the BLOCKED state → RUNNING, `next_step = phase-15d.flow`. The mock-first flow /
   debate / succession sub-steps already committed are **superseded by live re-runs** (not
   deleted; they proved the governed path). 15D now executes with **live backends**:
   the conductor node spawns the real `claude` CLI (fable-5 selection / probed fallback),
   worker nodes spawn real `claude` / `codex` / local Ollama per capability — through the
   supervised, governor-capped (I-X3 = 2), fail-closed spawn path already built and gated
   at 15A/15B/15C. `LIVE_OPERATION_AUTHORIZED` stays enforced; this authorization is its
   basis, cited in `config/live_operation.json`.
2. **Prove, on real evidence:** live Fable-5 conductor backend; live governed loop
   (decompose → assign → live workers publish CANDIDATE over MCP → gates → **conductor
   synthesis** → acceptance packet); **one bounded live debate** (real tokens, budgets
   enforced); **live conductor succession** (kill the live Fable-5 conductor mid-run,
   resume on a different live/ local backend, zero project loss, restore selection). Then
   close `gate/phase-15d` on live evidence with the mandatory gate-validator.
3. **Resolve U45 in this pass** — the checkpoint-verification stamp defect the builder
   flagged in `live_flow._leg_for_backend`, `selection.bind_conductor_selection`, and
   `propose_plan` (feeds the ACCEPTED acceptance packet) must be fixed as part of the live
   flow work, since the acceptance path is now real.
4. **Then 15E + the OP-8 live conductor pane** (directive §13): the operator lands in a
   live CONDUCTOR chat, types/speaks/injects-files, and it orchestrates the live worker
   CLIs and synthesizes back — the whole point.

**Unchanged:** every §2 prohibition except the §11(a)/OP-6 live-session lift for
claude_code + codex; credentials never read/stored/transmitted (the CLIs use their own
host-native auth); I-X3 = 2; the D-LOOP-1 teardown constraint (live nodes spawned in a unit
are torn down within it) is now **critical** — live CLI processes must never be left running
past the work unit. Budgets are hard caps; smoke-scale objectives only. Terminal state:
FINAL_LIVE_REPORT.md + `product/live`, operator addressed once.

---

## 15. OP-10 (operator, 2026-07-24) — PHASE 16: SHELL LIVE-WIRING & FIRST-USE FIXES

**Basis:** the operator launched the shipped shell (screenshot-verified: window up,
SUPERVISION READY, 3 sessions, CONDUCTOR pane with talk/Resume→Select, subscriptions
claude −/2 codex −/2, "concurrency count unavailable (fail-closed)") and reported:
(1) cannot type in any terminal — and panes show no shell banner, so the PTY→xterm
output feed is also not rendering; (2) no per-pane model selector visible; (3) voice
unusable; (4) wants **Kimi K3** and **Qwen 3.8** available. This is the U65–U68 owed
live-feed family plus at least one real pane-I/O defect. Phase 16 closes the gap between
the tested engine and the operator's hands. OP-9 live authorization stands; same loop
protocol; tags `gate/phase-16a..16f`; terminal state: FINAL report addendum + tag
`product/usable`, operator addressed once.

**BINDING LESSON (D-P14-1/D-P16-0):** every shell/UI change in this phase MUST be
exercised by an automated check that runs INSIDE the packaged Electron runtime on this
host (autorun-style self-check writing a machine-readable receipt) — headless Node tests
alone closed 14A while shipping a runtime that failed at first launch. Never again.

| Track | Content |
|---|---|
| **16A — pane I/O (the defect)** | Diagnose+fix: supervised session output does not stream into xterm panes and keystrokes do not reach sessions in the running shell (screenshot: RUNNING sessions, blank panes, no banner). Reproduce inside Electron via an autorun self-check (spawn pane → expect banner text in the renderer buffer → type probe → expect echo), fix, receipt committed. High-stakes gate. |
| **16B — per-pane model picker UI** | Wire the existing picker backend into the shell: model dropdown on "+ Terminal node" and on each pane's chrome (provider × model × role from the live enumeration incl. residency states, greyed-with-reason preserved); selection → `pane_node_spawn` governed path; pane chrome shows model badge + n/2. **Kimi K3 + Qwen 3.8:** enumerate what the host's Ollama actually offers (`ollama list`/registry search); if pullable, pull them (local, no credentials — record sizes/VRAM in the residency planner); if only cloud, record OWED-pending-operator-authorization. Never fabricate an entry. |
| **16C — live conductor in pane 1** | End `awaiting_live_conductor`: on launch, pane 1 spawns the REAL interactive `claude` (fable-5 selection / recorded fallback) through the gated conductor spawn path, attached to Sovereign MCP; badge sources selection over IPC (closes U65); conductor dispatch of live workers per OP-9 (closes U58 as far as evidence allows — honest receipts). |
| **16D — status-bar + approvals live feeds** | Governor n/2 real count into the status bar (fixes "concurrency count unavailable"); approval-queue drawer fed over the read-only IPC (closes U66); recovery snapshot carries worker-pane chrome (closes U68). |
| **16E — voice wiring** | Talk button → capture → STT → bridge → conductor input, end-to-end (closes U67): real Parakeet if NeMo present, else mock STT with a VISIBLE "mock engine" indicator (never silently pretend to hear); write docs/OPERATOR_NEMO_INSTALL.md (the two-command WSL install, operator-run). TTS still NOT built (I-V2; operator reversal pending). |
| **16F — operator-visible validation** | Assembled run in the operator's shell: type to the live conductor, watch it spawn/drive picker-selected workers in panes, approval exercised, restart recovery — receipts + FINAL report addendum + `product/usable`. High-stakes gate. |

---

## 16. OP-11 (2026-07-25) — PHASE 17: FULLY-LIVE IN-SHELL → `product/fully-live`

**Operator ruling (Sam, in-session, 2026-07-25):** "Yes. Let's get seventeen started and
completed." Authorized after the product/usable audit (PRODUCT_USABLE_AUDIT_20260725) and the
operator's first use of the running shell. **Phase 17 closes the ENTIRE remaining owed
register. There is no construction phase behind it** — post-17 items are operator-optional
only (TTS reversal = would-be OP-9-TTS; cloud Kimi/Qwen = new provider authorization; v1
naming promotion).

**Operator first-use findings (2026-07-25 screenshot + code-read, recorded):**
- **F1 (opens U74):** voice badge "mock engine" despite the operator's VERIFIED WSL Parakeet.
  Root cause: `adapters/voice_parakeet/wsl_parakeet._probe_nemo` budget 8 s < the measured
  `import nemo` cost on this host (>8–11 s, worse on cold WSL), and `wsl_nemo_available`'s
  `lru_cache(1)` pins one cold miss for the app's lifetime.
- **F2:** the approval drawer renders the emitter's three DETERMINISTIC demonstration items
  (ap-1/ap-2/ap-3) as if they were pending operator work — real authority path, canned content.
- **F3:** conductor pane 1 `awaiting_live_conductor`, admission SHUT — typing gets no answer;
  a picker selection records + badges but launches nothing (U70); dispatch legs mock (U58).
  All previously disclosed as owed; now the work.

**DEFINITION OF DONE (operator-stated; binding for 17E):** at the operator's keyboard —
(a) typing to pane 1 gets a live answer from the Fable-5-selected conductor; (b) hold talk,
speak → real-Parakeet transcript reaches the SAME live conductor session → it answers;
(c) selecting a model on a pane (incl. local `qwen3:8b`) launches that live worker, governed;
(d) the conductor dispatches LIVE workers whose CANDIDATE results return through the gates
into its synthesis; (e) the approval drawer shows ONLY real session events. Every
machine-checkable leg gets a D-P16-0 in-Electron receipt; the spoken-mic half of (b) is
validated by the operator's first use — the loop NEVER blocks on the operator (§1).

| Track | Content |
|---|---|
| **17A — live conductor session in pane 1 (HIGH-STAKES gate)** | End the black pane. On launch (and via an explicit pane-1 control), the governed conductor spawn RUNS the real interactive `claude` (fable-5 selection; unavailable ⇒ recorded fallback, surfaced never silent) inside pane 1's ConPTY through the FULL live-gate chain (live_operation switch → provider-live → OP-9 terms → I-X3 slot), and the admission channel opens through the verified path (the recovery banner's SHUT state ends only on a genuinely admitted governed session — inv 2, no naked spawn). Type→answer round-trip proven by an in-Electron receipt using ONE minimal prompt (live-budget discipline). Badge honesty (inv 3): `live`/`verified` only via the existing verified-checkpoint machinery where an interactive session can actually yield it; otherwise the honest lesser state — never fabricated. Self-check live sessions torn down in-unit (D-LOOP-1); the OPERATOR's session persists by design. Mandatory gate-validator. |
| **17B — live workers: picker spawn (U70) + live legs (U58)** | A picker selection on a worker pane performs the GOVERNED live spawn (supervisor + I-X3 governor; refusals surfaced with reasons): frontier per OP-6 scope only (`claude_code`/`codex`), local via the host runtime (Ollama/OpenCode) with residency honesty (U63/U64 narrowed as far as real evidence allows). Conductor dispatch drives ≥1 LIVE worker publishing CANDIDATE over MCP → real gates → conductor synthesis; leg labels remain unfakeable (`_assert_legs_honest`). Minimal live exchanges; D-LOOP-1 in checks. |
| **17C — voice: real engine (U74) + mic loop** | Fix the probe: budget raised to measured reality (≥60 s) AND made non-blocking (async probe or probe-on-talk with a visible "probing…" state); remove the lifetime cache pin — re-probe on demand and after failure; `SOW_*` env overrides honored. Real microphone PCM capture in the shell → WSL Parakeet → bridge → the LIVE 17A conductor session. Propose-never-execute unchanged (inv 25); transcribe-then-discard (inv 26); **NO TTS** (I-V2/D-VOICE-02 stands). Machine-checkable half via fixture-WAV receipts; the spoken-mic half is operator first use. Confidence-calibration limitation recorded honestly. |
| **17D — real-events approvals + defect closure** | The approval drawer sources ONLY real session events (17A/17B produce them: protected verbs, gate promotions, voice clarifications); the deterministic demo trio becomes test-only — never rendered in the product path. Guard `pane:resize` for sessionless panes (U73). Discharge U69 via the assembled typed path + operator use. Fix the non-hermetic wsl-PATH test (audit R4, monkeypatch `shutil.which`). |
| **17E — fully-live assembled validation (HIGH-STAKES gate)** | One in-Electron assembled receipt covering the machine-checkable DONE legs (a, c, d, e + fixture-voice), honest OWED markers for anything not evidenced; FINAL report addendum; terminal tag **`product/fully-live`**; operator addressed ONCE. Mandatory gate-validator + spec-auditor on the composition. |

**Carried constraints:** §2 prohibitions minus the OP-6/OP-9-scoped live permission; live
exchanges MINIMAL (session limits are real — one prompt/one answer per receipt); PRINT-MODE
FACT (D-LOOP-2); D-LOOP-1 teardown; D-P16-0 per-track in-Electron receipts; two-commit
convention + tags `gate/phase-17a..17e`; registers append-only; canonical set frozen;
`config/live_operation.json` never committed; NO new live providers (cloud Kimi/Qwen stay
OWED-pending-operator).

---

## 17. OP-12 (2026-07-31) — PHASE 18: GROK BUILD + GEMINI/ANTIGRAVITY PROVIDERS → `product/multi-frontier`

**Operator ruling (Sam, in-session):** the operator holds active SuperGrok and Google AI Pro
subscriptions and authorizes two NEW live frontier providers: **`grok_build`** (CLI `grok`,
display "Grok Build") and **`google_antigravity`** (CLI `agy`, display "Gemini · Antigravity").
Terms basis: operator confirms both subscriptions permit supervised first-party-CLI use (same
R8 class as OP-9). The operator-adopted directive (ChatGPT-drafted) is preserved VERBATIM at
`docs/operator/OP12_PROVIDER_DIRECTIVE_GROK_ANTIGRAVITY.md` and BINDS for scope, credential
isolation, runner behavior, governor rules, UI behavior, tests, and live acceptance — except
where superseded here.

**Recorded supersessions (operator-approved, never silent):** (1) the operator directive's
"do not run the autonomous loop / do not commit" framing assumed a one-shot supervised session;
the execution vehicle IS this loop under the standing two-commit convention, gates, and
mandatory reviews. (2) Its "active Phase 17C state" boundary is stale — Phase 17 is complete.
The untouchable set is: `tools/loop/run_loop.ps1` (the RUNNER never modified by Phase-18 work),
loop-state SEMANTICS, existing gate tags, existing claude/codex/ollama/parakeet behavior,
canonical schemas, MCP authority, artifact/debate semantics, remotes/branches/credentials.
(3) Loop-state bookkeeping and register rows proceed normally; the OP-12 DECISION_REGISTER row
is the FIRST bookkeeping act of 18A.

| Track | Content |
|---|---|
| **18A — host reconnaissance + provider runner** | Reconnaissance FIRST: the installed `grok --help` / `agy --help` surface is AUTHORITATIVE — no flags from memory; a CLI not yet installed or not yet logged in is a recorded fact, not a failure (skip-with-record the dependent parts). Build `tools/providers/run_frontier_providers.ps1` exactly per operator directive §3–§7/§15/§18: status/install/login/probe/launch; fail-closed status states; **exit-code-first error classification — an exit-0 transcript containing historical error words is NEVER reclassified** (the Codex-period lesson, now binding for every provider); installs only under explicit `-InstallMissing`; no secret read/printed/stored ever; repeat-safe; never starts this loop. Deterministic tests per §16. |
| **18B — registry, adapters, governor, picker, UI (mandatory validator)** | Both providers through the EXISTING registries and contracts — no parallel registry, no second control plane. Interactive panes via the existing supervised ConPTY + launch-ticket path (§9; no detached spawns). Headless via the existing frontier adapter contract (§10; `grok agent stdio`/ACP only if an existing transport fits). I-X3: NEW subscription resources `grok_build_subscription` + `google_antigravity_subscription`, **allowance 1 each — never merged, never raised without a separate operator amendment**; lease release on every exit path (§12). Live model enumeration from `grok models` / `agy models`, fail-closed, never fabricated (§8). UI labels, badges, and provider-CORRECT failure text (§14). Tool permission subordinate to launch tickets (§11): no always-approve, no unsandboxed defaults. Credential isolation absolute (§13 + §2.2): env-scrub extended to `XAI_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_API_KEY`. |
| **18C — live acceptance (HIGH-STAKES gate)** | ENTRY CONDITIONS (unmet ⇒ skip-with-record, not failure): the operator has completed each CLI's own login, and the operator has extended `config/live_operation.json` to include both providers (absence ⇒ that provider's live legs DENIED — the fail-closed switch working as designed). Then per §17: ONE harmless live probe per provider (`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`; exit-code + structured-output + repo-status-unchanged acceptance) and ONE in-Electron receipt per provider (picker → supervised pane → exact provider+model verified → harmless prompt → live response → teardown → lease 0 → no credential material in any log → tree clean). No simultaneous same-provider sessions. Terminal: FINAL report addendum + tag **`product/multi-frontier`**; operator addressed ONCE. Mandatory gate-validator + spec-auditor. |

**Carried constraints:** §2 prohibitions minus the OP-scoped live permissions (now
OP-6/OP-9/OP-12); live exchanges MINIMAL (one prompt/one answer per receipt leg); PRINT-MODE
FACT (D-LOOP-2); D-LOOP-1 teardown; D-P16-0 per-track in-Electron receipts; two-commit
convention + tags `gate/phase-18a..18c`; registers append-only; canonical set frozen;
`config/live_operation.json` never committed (only the tracked `.example` is updated to show
the new shape); cloud Kimi K3 remains OWED-pending-operator; existing providers' allowances
unchanged (claude/codex at 2 per OP-6, operator-reaffirmed).

### 17.1 OP-12.1 (2026-08-01, operator ruling) — U227 RESOLUTION: SUCCESSOR SCHEMA v1.1

**The operator rules U227 by successor schema.** Authorized: a NEW versioned schema file
(`node@1.1` beside the frozen `@1.0` — e.g. `schemas/node.schema@1.1.json` per the repo's
versioning convention) whose adapter enum is the frozen `@1.0` list PLUS `grok_build` and
`google_antigravity`. The same amendment MAY admit the pre-existing local-adapter id drift
(U254, `ollama_local` vs `ollama_direct`) as its own recorded item. **The frozen `@1.0` files
and the frozen Architecture Plan are NEVER edited** — the amendment is additive; this section
is the operator authorization the Phase-0 freeze requires, and the DECISION_REGISTER row
(OP-12.1) is the first bookkeeping act of the unit that executes it. The freeze manifest is
extended ADDITIVELY to cover the new file, honoring U222: the operator signature on the
existing manifest must be preserved by hand, never regenerated away. `NodeRegistry.register`,
validators, and the U227 fence then admit node records validating against `@1.1`; the fence's
refusal-logging stays for ids in neither version. Registration under `@1.1`, supervised panes,
and the previously-skipped 18C legs become in-bounds once this lands.

### 17.2 OP-12.2 (2026-08-02, operator) — PHASE 18E: LIVE IN-ELECTRON ACCEPTANCE (the last owed leg)

**Standing at arming (operator-verified):** the operator completed both CLI logins, the live
switch now cites OP-12 naming all four providers, and the operator's own run of
`tools/providers/frontier_provider_recon.py --action probe --provider all` succeeded LIVE for
BOTH providers — governed gate PASS, real leases 1/1→0, supervised spawn, exact tokens
(`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`), structured output parsed, repo unchanged, and the
FIRST DURABLE node records for both providers written under `node@1.1`. The operator's
`op12-acceptance` self-check run then FAILED **by design**: that target is the fail-closed
skip-with-record evidencer, whose verdict module refuses to stand once the switch is open
(receipt `PHASE18C_ACCEPTANCE_SELFCHECK.json`, 2026-08-02T00:11Z — treat its error text as the
spec for this phase).

**Track 18E (HIGH-STAKES gate):** (1) Provide the LIVE acceptance path the open-switch world
demands — either a live mode of the existing target or a sibling target (e.g.
`op12-live-acceptance`) — running §17's per-provider in-Electron leg: real picker selection →
supervised ConPTY pane as a registered Sovereign node → verified exact provider+model → ONE
harmless prompt → live response → teardown → lease 0 → credential-sentinel scan of every sink
that now exists (PTY transcript + child env included — the skip-receipt's scan was narrow
because its world was) → durable ledger consistency. ONE live exchange per provider, no
simultaneous same-provider sessions. (2) Close **U238** (whitespace-deleting echo acceptance;
`extract_probe_text` whole-document fallback) BEFORE the live legs run, so the live verdict
cannot rest on either hole; note the operator's probe already returned exact tokens, so this is
hardening the acceptance, not repairing a result. (3) Sweep the small register debts this run
exposed as in-scope-if-cheap: U234/U283/U290 lineage is already recorded — verify, don't redo;
the `gates.operator_terms_confirmed` parameter-default (scope_note_gate_map) gets the U283-style
closure on the pane/worker emitter. (4) Mandatory gate-validator + spec-auditor; supplement the
Phase-18 addendum; per §17.1 the existing `product/multi-frontier` tag is never moved — apply
successor tag **`product/multi-frontier-v2`**. Operator addressed once. Voice-probe noise seen
during the operator's failed run (`voice probe exited null` during teardown) is expected reap
noise unless the live legs reproduce it in a healthy world — then it is a finding, not noise.

**Sequencing:** if track 18C closes with skip-with-record before this ruling is acted on, the
work continues as **`phase-18d` — U227 amendment + registration + skipped-leg completion
(HIGH-STAKES gate)**: execute the amendment above; register both providers as Sovereign nodes;
run every 18C leg previously skipped on the registration fence (and any still gated on the
operator's live switch or logins — entry conditions unchanged, skip-with-record still honest);
mandatory gate-validator + spec-auditor; supplement the FINAL report addendum; re-point
`product/multi-frontier` ONLY by adding a successor tag (e.g. `product/multi-frontier-v2`) if
the original was already applied — existing tags are never moved. Operator addressed once at
the end.

**Recorded clarification to the 18C entry condition (added 2026-07-31 at the 18A gate; the ruling
above is NOT rewritten).** The 18C row says the operator "has extended `config/live_operation.json`
to include both providers". As the code stands that instruction cannot be followed:
`control_plane/profiles/live_authorization._AUTHORIZED_PROVIDERS` is pinned to the OP-6 pair and
the loader **raises** on any other provider id, so naming `grok_build` or `google_antigravity` in
that file would deny **every** live provider, `claude_code` and `openai_codex_cli` included. The
direction of failure is safe and invariant 1 is upheld — a config file cannot widen a code-pinned
scope — but the printed instruction was wrong. The real entry condition is: the operator's OP-12
authorization (recorded) **plus** a code-pinned scope extension written in **18B**, **plus** the
operator's own edit to the (never-committed) live switch. Recorded as **U237**; found by the
round-3 spec-auditor at the 18A gate.

## 18. OP-13 (2026-08-06, operator) — PHASE 19: POST-18E REMEDIATION → `product/governed-live`

**Why this phase exists.** After Phase 18E closed (`b68a22e`, loop → COMPLETE), **seven further
commits landed outside the loop** — `3587cbd`, `04c2168`, `2dec849`, `a6dd83f`, `a7ae4c6`,
`02639d4`, `b109f02` — 59 files, +3,771/−245, **untagged, with no evidence report, no register
row, and no mandatory-reviewer pass**. A cold independent audit of that range was run on
2026-08-06 (four blind readers, each finding re-verified on disk, desktop and terminal suites
independently executed) and is recorded verbatim at
`docs/evidence/COLD_AUDIT_UNTAGGED_POST_18E_20260806.md`. Verdict: **DO NOT TAG** — 4 BLOCKING,
8 MAJOR, recorded as **U326–U339**. All mechanical prohibitions were verified **intact** (no
secrets, no `docs/canonical/` or `schemas/` edits, no register rewrites, `config/live_operation.json`
untracked, env-scrub not weakened, no remote contact), and the range does **not** overclaim —
nothing in it asserts the three-node collaboration leg ran. What it does is move authority into
places the invariants reserve, and record none of it.

**Operator rulings that bind this phase.**

**OP-13** — Antigravity's own `accept-edits` mode is **not** operator approval. `D-P18-13` /
`U317` stand unamended. `adapters/frontier/antigravity.py:72` returns to `"plan"` and the
`antigravity_execution` carve-out at `adapters/frontier/provider_cli_common.py:310-312` is
removed so the forbidden-mode guard is unconditional again.

**OP-13.1** — **remediation precedes the live run.** The four blocking findings are fixed
*before* the Gemini/Grok accounts are unblocked and the three-node acceptance is re-attempted.
Rationale recorded from the audit: U329 can pin a healthy worker as permanently blocked, and
U330 fires on the first genuinely concurrent moment — a run attempted before either is fixed
produces a result that cannot be attributed between provider and code.

**Untouchable set for this phase.** `tools/loop/run_loop.ps1`; loop-state semantics; every
existing gate tag (**tags are never moved** — Phase 19 closes on a NEW successor tag); the
canonical set and both frozen schemas; MCP authority (invariant 7 — this phase *restores* it,
never relocates it further); artifact/debate semantics; remotes, branches, credentials. Existing
provider allowances unchanged (claude/codex 2 each per OP-6; `grok_build` and
`google_antigravity` 1 each per OP-12).

| Unit | Content |
|---|---|
| **19.1 — OP-13 revert (do this first; it is the operator's ruling)** | Restore `ANTIGRAVITY_HEADLESS_MODE = "plan"` and delete the `antigravity_execution` exception so `FORBIDDEN_PERMISSION_MODES` is enforced unconditionally again; restore the deleted rationale comment rather than writing a new one. Then settle **U327**: either restore Grok's `"plan"` pin or keep `"default"` **with a register row stating why the earlier recorded refusal no longer applies** — silent is the one thing it may not be. Add a test that asserts the guard refuses `accept-edits` for *every* execution profile, so the carve-out cannot reappear untested. |
| **19.2 — U326: authority returns to `control_plane/policy.py`** | Route all twelve inline role/permission checks in `mcp_server/collaboration_service.py` (lines 53, 83, 98, 113, 132, 141, 201, 228, 259, 276, 282, 290) through the policy object it already holds, exactly as `mcp_server/memory_service.py` does on its nine write paths. `open_debate` uses the existing `control_plane/policy.py:140` `authorize_debate`. Extend the policy with whatever authorize_* entry points the remaining operations need — **the new surface goes in `control_plane/`, never in `mcp_server/`.** Falsification required: a mutation that changes a policy rule must be caught by a test that goes through the collaboration path, proving the delegation is live and not decorative. |
| **19.3 — U328: nothing writes into a pane that may be showing a modal** | Gate `notifyNode` and `runConductorReadiness` on `classifyProviderScreen` returning null before any `writePanePrompt`, as `controlAssignTask` (`main.js:2458`) already does for assignment. The conductor pane is the priority case: it is currently written to blind, and it is the pane the operator converses in (OP-8). Extend the mutation harness to the **system→pane** direction — `tools/mutation/pane_input_bypass_mutations.js` guards operator→pane only, which is why this went unnoticed. Invariant 1 and D-P18-13 are the acceptance standard: the loop must be *unable* to answer a trust or permission modal, not merely unlikely to. |
| **19.4 — U329: exit codes first, bounded window, negative control** | Consult process exit codes and structured provider signals **before** any screen text, per `tools/providers/frontier_provider_recon.py:44-49`, which is binding for every provider. Where screen text is genuinely the only signal available on a running process, bound the window with the existing fail-closed `RingBuffer.sliceFrom()` (`terminal/session/ring-buffer.js:45-50`) — which returns `null` for an unanswerable window rather than guessing — never `buffer.snapshot()`. Reorder `runWorkerReadiness` so the MCP connection check is not short-circuited by a classification (`main.js:2287` currently precedes `2295`). Ensure every classified state has an exit path: a dismissed overlay must not pin a worker forever. **Required test — the negative control that does not exist today:** a healthy, connected, exit-0 worker whose transcript merely *mentions* "usage limit" or "not signed in" stays READY. |
| **19.5 — U330 + U332: one write path, and a gate that cannot be skipped** | Route `create_task`, `update_task`, `open_debate`, `post_debate_turn` and `close_debate` through `mutate_operational_task` and an equivalent `mutate_operational_debate`, so all seven orchestration writers share the `BEGIN IMMEDIATE` boundary the store already provides. Give debates an abort path (**U331 note**: a participant whose pane dies currently leaves the debate `OPEN` permanently and its peers accumulating stall timers). Fix `publish_synthesis` so an empty `debate_ids` cannot bypass the closed-debate gate — use `_nonempty_strings` and cross-check against `list_debates(task_id)`. **Falsification required and currently absent everywhere in the repo: a genuinely concurrent test** — two processes, not two threads — publishing candidates and posting debate turns against the same task, proving neither is lost. |
| **19.6 — U331 + U333: provider-agnostic in the runtime, not only in the selector** | Remove the `openai_codex_cli`/`gpt-5.6-sol` pin at `apps/desktop/main.js:2344-2348` and derive conductor readiness from the descriptor, so the generalization `3587cbd` delivered at the selection layer survives into the Electron lifecycle and conductor succession onto a different backend (Phase 15D exit criterion) is reachable. Reconcile the default: `control_plane/conductor/registry.py:154-162` resolves `claude_code`/`fable-5` when the gitignored live switch is absent, which must not then fail readiness with what reads as a config error. Replace the hardcoded `gemini_contribution`/`grok_contribution` synthesis fields with contributions keyed by **node id or capability descriptor** (I-SC1: selection demonstrably by descriptor, never by name). |
| **19.7 — U334/U335/U336: the runtime tells the truth about its own failures** | Bound `sovereign-control-server.js` `stop()` with a timeout plus `closeAllConnections()`, and bring it inside `teardown()` where every other resource already is — it is currently the one unbounded await after `event.preventDefault()`. Give `connectionState` a `last_seen` staleness window so a dead MCP subprocess behind a live PTY cannot report `connected`, and have `controlAssignTask` check MCP freshness rather than pane state alone. Stop `inspector/operational-source.js` returning a fully-shaped zero-count success on error, and stop `main.js:1726-1735` reporting top-level `ok: true` when `operational.ok` is false — "I cannot see" must not render as "nothing happened". |
| **19.8 — U337: evidence that says what it is** | Add an in-runtime self-check kind to `apps/desktop/selfcheck/run.js` covering the orchestration/collaboration path, emitting a receipt with the same provenance fields every machine-emitted receipt in that directory already carries (`check`, `source.commit`, `tracked_product_tree_clean`, `started`/`finished`, PID) — **D-P16-0 is currently unmet for every change in the audited range.** Stop deriving `process_supervised` and the six readiness booleans (`main.js:2310-2313`) from literal assignment: each must trace to an observed signal or be absent. Then either regenerate `FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json` and `FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json` from a real emitter, or relabel them so operator testimony is distinguishable from measurement in `docs/evidence/receipts/`. Neither file is deleted or rewritten in place — the register is append-only and so is this. |
| **19.9 — U338: coverage that can fail** | Make `apps/desktop/main.js` testable — extract the orchestration logic added by the range (readiness state machine, deadline subsystem, `requireControlRole`, the control handlers) into `require`-able modules the way `apps/desktop/control/` and `apps/desktop/picker/` already are, so the +846 lines stop being guarded by `fs.readFileSync` string matches that cannot distinguish working code from a syntax error. Give `mcp_server/sovereign_tools.py` real coverage: at least one end-to-end `tools/call` per handler and a direct test of both new authorization gates, which are currently exercised only against a two-line echo fake. Replace mutation **O1** in `tools/mutation/orchestration_mutations.js` — it mutates a `main.js` source line and grades it with a test that greps that same line — with a behavioural mutation; O2–O5 are genuine and stay. **Make silent skips visible:** the 28 `py -3.12`-gated tests must report their skip in a way a run summary surfaces, so a green suite cannot mean "no live coverage ran". |
| **19.10 — U339: the suite, and the gate** | Commit a pytest configuration (`pytest.ini` or equivalent) so the ceiling, the marker set, and the "focused" subset are inspectable in the repository rather than living in an invocation. Diagnose the 600 s timeout on the **host** — `--durations=20` first, then `--timeout=120 --timeout-method=thread` if it hangs rather than crawls — and record the named test. Then the gate: evidence report, mandatory `gate-validator` **and** `spec-auditor` in the foreground, tag `gate/phase-19`, and the successor product tag. **`product/multi-frontier-v2` is never moved.** |

**Exit criteria for Phase 19.** Every one of U326–U339 either closed with evidence or re-recorded
with a reason it is not closing; the two mandatory reviewers passed in the foreground; the
desktop, terminal and **full Python** suites all reported with their skips visible; and the seven
untagged commits are, together with this remediation, covered by a gate tag and an evidence
report. **Only then does Path A begin** — the Gemini and Grok account unblocks and the three-node
live acceptance, per `docs/operator/PATH_A_PROVIDER_UNBLOCK_SHEET.md`, run against a **committed**
HEAD so the result is reproducible.

**Carried constraints.** §2 prohibitions minus the OP-scoped live permissions (OP-6/OP-9/OP-12);
**PRINT-MODE FACT (D-LOOP-2)** — under `claude -p` the process ends with the turn, so every review
and every child process is foreground, synchronous and in-turn, and a unit that will not fit
commits a WIP checkpoint rather than ending a turn "waiting"; **D-LOOP-1** teardown inside the
work unit, no orphans; **D-P16-0** in-runtime receipts; **exit-code-first** classification, which
this phase exists partly to restore; **recovery provenance** — anything left uncommitted by a
crashed iteration is CANDIDATE material and its receipts are re-run fresh; **fix-after-validation
voids it** — re-validate or split the unit; the **CRLF hazard (U274)** — `.gitattributes` pins LF
and a tool writing CRLF leaves `git status` clean while the bytes differ; two-commit convention;
registers append-only; canonical set frozen; `config/live_operation.json` never committed.

**What this phase does NOT decide.** The shared-JSON orchestration simplification directive
remains the operator's open question. The audit's recorded finding is that the SQLite store is not
the defect — `mutate_operational_task` is one of the better-built things in the audited range, and
the actual bug (U330) is that five of seven writers bypass it — so replacing that store with
whole-document JSON rewrites under an exclusive lock would remove the one place with correct
transactional semantics while making `messages[]` and debate-turn contention worse, and would do
so before a single collaboration leg has ever executed. The cheaper move that addresses the real
complaint, if the operator wants it, is a **read-side projection**: keep the transactional store
and have `tools/live/emit_operational_state.py`, which already emits a versioned document, serve
the single-document view. Additive, reversible, and it does not touch the write path. **No
implementation of either is authorized by this section.**
