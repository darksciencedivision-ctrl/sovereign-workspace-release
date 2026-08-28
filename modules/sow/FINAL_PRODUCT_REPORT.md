# FINAL PRODUCT REPORT — Sovereign Orchestration Workspace (Phase 14: Product Shell & Live Adapter Integration)
**Autonomous staged build under AUTONOMOUS_BUILD_DIRECTIVE.md §9–§10 (operator authorization OP-4/OP-5, 2026-07-18).**
Phase-14 track completed 2026-07-19 · `gate/phase-14e` → `product/complete` · **471 Python tests + 131 JS tests green, 0 skipped** · canonical freeze clean throughout.

> **Operator (Sam):** this is the one moment the loop addresses you, per your ruling. Phase 14 ran
> Phase 14A → 14E as an unattended loop with independent per-gate validation on top of the completed
> Phase 0–13 core (`build/complete`, `FINAL_BUILD_REPORT.md`). Every standing prohibition held
> (no push, no credential handling, no purchases, nothing outside the repo, canonical set frozen),
> and the two operator-gated live items you authorized were exercised **only** within their exact
> scope. **14D (Real Parakeet/NeMo) was a failed-entry skip-with-record** (WSL inaccessible to this
> non-interactive session) and **14E degrades honestly** to the subset that proved live. **Nothing
> hit a BLOCKED state.** Two items remain genuinely OWED and are listed plainly in §5 — most
> importantly, **no live `claude` frontier call was ever made**, because making it requires a config
> file the loop is forbidden to create (that creation *is* the authorization).

---

## 1. Per-track gate table (tag · commit · verdict)

| Track | Gate tag | Tag commit | Verdict | What shipped |
|---|---|---|---|---|
| **14A — Product UI + IPC** | `gate/phase-14a` | `59528bb` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | Real Electron/xterm.js/node-pty workspace (`apps/desktop` + `terminal/`): authenticated loopback WebSocket IPC (D-IPC-01, RFC 6455 on stdlib, per-node auth + `envelope@1.0` + HMAC, fail-closed); supervised ConPTY sessions (no naked sessions, inv 2); deterministic pane/window model; dynamic tiling (Plan §10.2); read-only routing/artifact inspector over the D-IPC-01 channel; UI recovery after control-plane/process restart (`RecoveryMachine`/`RecoveryStore`, live gateway kill+restart proven). 5 sub-steps: `.ipc`/`.shell`/`.tiling`/`.inspector`/`.recovery`. |
| **14B — First live frontier adapter (exactly ONE provider = Claude Code)** | `gate/phase-14b` | `1f04a84` | **PASS_WITH_RESERVATIONS** (high-stakes, mandatory validator) | Enforced `LIVE_OPERATION_AUTHORIZED` config gate landed **first** (`control_plane/profiles/live_authorization.py`: absence⇒DENIED, out-of-scope⇒RAISE, scope pinned in code to OP-4/`claude_code`/1-terminal); R8 ToS verification recorded; live `claude_code` adapter behind the governed `ModelWorkerAdapter` contract, spawned only through the fail-closed supervised path (`node_runtime/supervisor/frontier_spawn.py`, 5 ordered gates + release-on-construct-fail). Credential invariant §2.2 enforced (env-scrub superset; `build_command` carries no key). Governor deep re-inspection: allowance stays 1 (I-X3). 3 sub-steps: `.liveflag`/`.r8tos`/`.adapter`. **The single live `claude` smoke is skip-with-record — OWED** (§5). |
| **14C — OpenCode live local harness** | `gate/phase-14c` | `fd3fbca` | **PASS** (high-stakes, mandatory validator) | First-class supervisor-spawned OpenCode harness (invariant 23; closes the Phase-6 F1 coding-harness gap): presence/version gate, `ollama/*` model pin enforced in code (§2.3), credential scrub + session-local `OPENCODE_CONFIG` isolation (U30 discharged). OpenCode **driven LIVE** in an isolated git worktree from scoped MCP context (real spawn, real tool-execution, worktree confinement `escaped=False`), tests run, driven result packaged as a governed CANDIDATE → node-local gate → controlled merge → ACCEPTED-by-a-different-node. 3 sub-steps: `.harness`/`.worktree`/`.gate`. **No live local-coder LANDED edit** (U31, §5) — chain closed with a seeded edit, recorded `from_live_model=False`. |
| **14D — Real Parakeet/NeMo** | *(none — correctly untagged)* | evidence `fdf3be8` | **SKIP-WITH-RECORD** (failed entry attempt, directive §10.3/§10.4 — NOT a failed gate) | Operator authorization was **present** (OP-4/OP-5 lifts §2.7 for the WSL pip/NeMo install), so this is an environment/executability gap, not an authorization gap. Decisive real probe: `detect_voice_stack()` → `{nvidia_gpu:true, wsl:true, nemo:false}`; every `wsl.exe` invocation is approval-denied in this non-interactive session ⇒ cannot enter WSL, install NeMo, or run a real transcription. Nothing faked; no source changed; the Phase-12 MockSTT path is **not** a valid substitution for a live-engine requirement. U1/U2/U4 open-for-hardware. |
| **14E — Product-level validation** | `gate/phase-14e` | *(this commit)* | **PASS** (high-stakes, mandatory validator) | The single **assembled end-to-end run** over live shared MCP: honest liveness matrix + item-7 Ollama smoke (`.roster`) → gated coding task + bounded debate + conductor replacement mid-run + full restart & recovery (`.run`) → this phase gate (`.gate`). Degrades honestly to exactly the subset that proved live. 3 sub-steps: `.roster`/`.run`/`.gate`. |

**Track order 14A → 14B → 14C → 14D → 14E** as directed; a failed entry on B/C/D does not block the
rest (§10.4). **14A, 14B, and 14E were mandatory high-stakes gates** and each got an independent
`gate-validator` re-validation in an isolated context; substantive sub-steps also got a
`spec-auditor` pass, with every MAJOR/MINOR fixed with pinning tests **before** the gate closed.

## 2. The assembled run — which legs were LIVE vs MOCK vs DETERMINISTIC_SUBSTITUTE (directive §10.4)

The assembled scenario (`tools/assembled/run.py`, driven over a real loopback MCP server) reports
exactly what proved live — the `.roster` liveness matrix is the single source of truth and `.run`
cannot upgrade a leg. Real receipt (`py -3.12 -m tools.assembled.run`):

```
coding:  PASS  merged=True  final=ACCEPTED  author=coder-A  promoted_by=gate-1  from_live_model=False
debate:  DISSENT_PRESERVED  rounds=5
succession: ok=True  pred=claude-mock  succ=fable-mock  zero_loss=True
restart: ok=True  coding=True  debate=True  snap=True
live_roles=['local_reasoning_worker']  owed=['frontier_worker']
smoke:   available=True  generated=True  model=qwen2.5:7b-instruct
```

| Assembled role | Classification | Why (honest) |
|---|---|---|
| **local_reasoning_worker** | **LIVE** | Real local Ollama model (`qwen2.5:7b-instruct`) on 127.0.0.1 — permitted under §2.4 (detected local model, no credentials). The item-7 smoke is the live receipt (`available=true`, `generated=true`). **The one genuinely-live model execution this session.** |
| **conductor** | **MOCK** | Phase-4 deterministic `MockReasoningBackend`, holds no credential. A live frontier conductor is out of scope — §2.4 was lifted for one live **worker** provider, not the conductor runtime. Succession is proven live at Phase 11. |
| **frontier_worker** | **MOCK + OWED** | The live `claude_code` adapter exists (gate/phase-14b); operator authorization is recorded (OP-4/OP-5); but the enforced `LIVE_OPERATION_AUTHORIZED` gate is **DENIED-by-absence** (`config/live_operation.json` intentionally unwritten, inv 1) and the single live `claude` smoke is skip-with-record. Governed output stays mock; **live is OWED, never claimed**. |
| **coding_worker** | **DETERMINISTIC_SUBSTITUTE** | OpenCode was driven LIVE at 14C (real spawn/tool-exec/confinement), but no live local-coder LANDED a schema-correct headless edit (U31, model-quality limit), so the CANDIDATE→gate→merge chain was closed with a deterministic seeded edit (`from_live_model=False`). Real component, substituted accepted content. *(Label edge: a host with a local coder but no OpenCode binary would read `coding_worker=LIVE` — the direct single-shot Ollama coder — but even there the assembled run's merged edit stays a seeded stand-in.)* |
| **voice** | **MOCK_STT** | 14D skip-with-record — no real Parakeet (WSL inaccessible). Voice stays the Phase-12 MockSTT path behind the same interface. |

What the assembled run **actually proves live** (headless): the governed **data path** end-to-end —
a coding task CANDIDATE → node-local gate → controlled `MergeCoordinator` merge → ACCEPTED promoted
by a **different** node (inv 18, enforced by policy and proven by a live negative test); one bounded
debate (≤5 rounds, dissent preserved verbatim, non-conductor caller); conductor replacement mid-run
into a different model with **zero project loss** (inv 28); and a **real MCP process restart** over
the same durable store after which the ACCEPTED artifact, debate record, and succession snapshot all
survive. The rendered/visible panes are an operator-run metric (like the Phase-1 spike and the 14A
window); the UI-side recovery machine is proven separately at `gate/phase-14a` by the 131-test Node
suite.

## 3. Totals
- **471 Python tests** pass on Python 3.12.10 (`py -3.12 -m pytest tests/ -q`, 0 skipped) — up from
  330 at `build/complete`; **+141** across Phase 14.
- **131 JavaScript tests** pass (`node --test`, 0 skipped): 103 in `terminal/` + 28 in `apps/desktop/`.
- New Phase-14 product surface: `apps/desktop/` + `terminal/` (Electron/xterm/node-pty shell,
  authenticated IPC, tiling, inspector, recovery), `control_plane/ipc/`, `adapters/frontier/`,
  `adapters/coding/opencode/`, `node_runtime/supervisor/frontier_spawn.py` + `opencode_spawn.py`,
  `control_plane/profiles/live_authorization.py`, `tools/assembled/`.

## 4. How to run

```powershell
# from the repo root, Python 3.12
py -3.12 -m pytest tests/ -q                          # full governance suite (471)
python tools/manifest/compute_manifest.py --check     # verify the canonical freeze

# the assembled end-to-end product run (headless governed data path + live Ollama receipt)
py -3.12 -m tools.assembled.run                        # prints the JSON receipt shown in §2

# the honest liveness matrix + item-7 Ollama smoke on its own
py -3.12 -m tools.assembled.roster_report

# MCP shared-memory server as a separate loopback process
py -3.12 -m mcp_server.run_server .\.sovereign_store 0 # prints MCP_PORT=<n>

# the product desktop shell (Windows host; requires `npm install` in apps/desktop — operator run)
cd apps/desktop; npm install; npm start                # Electron/xterm/node-pty workspace
cd apps/desktop; npm test                              # 28 JS tests (IPC/supervisor/recovery)
```
A local **Ollama** daemon (present on this host) enables the item-7 live smoke and the LIVE
`local_reasoning_worker` leg; without it those degrade to SKIP-WITH-RECORD and the mock reasoner is
used (never faked). **OpenCode** `1.17.13` on the host enables the 14C live harness drive.

## 5. Owed / deferred-live / open items (honest — nothing is silently closed)

| Item | Status | What it would take |
|---|---|---|
| **Single live `claude` frontier smoke** | **OWED** (skip-with-record at 14B) | Two operator preconditions the loop cannot self-satisfy: (a) the [OPERATOR] R8 §6 dated live-terms retrieval + confirmation that no clause prohibits first-party wrapped-CLI use under your own subscription; (b) `config/live_operation.json` present on the host — **the loop must NOT create it** (creating it *is* the authorization once a live path exists, inv 1). Then one operator-run live smoke through the already-built supervised spawn path. |
| **U31 — live local-coder LANDED edit** | **OPEN, non-blocking** | A better agentic local model / tool-schema shaping / larger multi-turn budget so a small local coder completes a schema-correct headless edit through OpenCode's tool path. The governed CANDIDATE→gate→merge chain is already proven with a seeded edit; only the edit *origin* is substituted. |
| **U1 / U2** — Parakeet latency/VRAM under concurrency; Windows mic→WSL bridge + PTT | **OPEN-FOR-HARDWARE** (14D) | Operator-run WSL2 setup with GPU passthrough, NeMo pip install, real audio; then the VoiceAdapter's mock engine swaps behind the same interface (I-A1), still STT-only, still propose-never-execute. |
| **U4** — CC-BY-4.0 attribution mechanics | **OPEN** (packaging) | Only relevant if the Parakeet checkpoint ships in a distributed product. |
| **U5 / U29** — provider per-account concurrency (verified-at-1, I-X3); env-scrub substring width | **OPEN, non-blocking** | Concurrency stays 1 until a verified per-account allowance (never raised on inference). U29 is defence-in-depth (not a §2.2 vector for the `claude` CLI). |
| **U10** — OS-level same-user filesystem/git-ref isolation | **DEFERRED-P-LATER** | Enforced today at the API + git-worktree + Job Object layers; a same-user raw-syscall bypass needs restricted tokens or separate accounts. Not exposed in single-operator use (the shipped posture). |

## 6. What live-provider enablement would require (not done — the loop is forbidden to self-authorize)
1. **Live Claude Code frontier worker** — discharge the two [OPERATOR] preconditions in §5, place
   `config/live_operation.json` (`{provider: claude_code, terminals: 1}`, cites OP-4) on the host,
   then run one live smoke. The adapter (built, gated) wraps the already-authenticated `claude` CLI;
   credentials stay in the host-native store and never transit MCP or the repo (§2.2). No second
   provider without a new operator authorization.
2. **Live local-coder edits** — resolve U31 (agentic model/tool-schema/budget) so OpenCode lands a
   gate-clean edit; the governed chain is already in place.
3. **Real Parakeet voice** — operator-run WSL2/NeMo install (§10.3) with mic bridge; mock engine
   swaps out behind I-A1.
None of the above changes the Sovereign contract — they are adapter swaps and configuration behind
already-gated, already-tested paths.

## 7. Status
`IMPLEMENTATION` (Phase 0–13 core + Phase 14A/B/C/E product tracks): **COMPLETE**. 14D:
**SKIP-WITH-RECORD** (hardware/env, honestly recorded, correctly untagged). `LIVE_OPERATION_AUTHORIZED`:
**DENIED-by-absence** (operator-reserved — the loop will not write the config; §5/§6). The assembled
multi-terminal orchestration system is proven end-to-end on real governance code over live shared
MCP, with a real local model in the loop; the frontier live call and live local-coder edit are the
two honestly-owed items. `product/complete` tagged. Promotion to the
`SOVEREIGN_ORCHESTRATION_WORKSPACE_v1` naming is **operator-reserved**.

*Generated at `phase-14e.gate` by the autonomous build loop. This is the terminal Phase-14 report;
the loop state is now COMPLETE.*
