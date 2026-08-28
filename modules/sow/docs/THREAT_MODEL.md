# THREAT MODEL — Sovereign Orchestration Workspace

Adopted at Phase 0 (2026-07-16) from Architecture Plan v1.0.1 §3.3 (trust boundaries) and
§11 (threats T1–T16, failure modes), which incorporate Canonical Handoff §2.6. This file is
the build's working copy; the canonical text governs on any divergence.

## Status vocabulary (W-83 — the honesty column)

Every mitigation below carries a status with its ENFORCEMENT LOCATION, in the shape
`containment.py` practises on itself: **IMPLEMENTED** (real enforcement, location named),
**PARTIAL** (some legs real, the absent ones named), **NOT IMPLEMENTED** (asserted, never built —
each is registered), **PLANNED** (deliberately deferred with a ruling), **SUPERSEDED** (the claim
moved elsewhere). A reader deciding what is safe to run live reads THIS column first.

## Trust boundaries

| TB | Boundary | Rule | Status |
|---|---|---|---|
| TB-1 | Operator ↔ system | Only surface where authority enters; text and voice converge on one command bus **before** the Permission Broker | **PARTIAL** — voice is broker-mediated (`voice_bridge/command_broker.py`); the operator's TYPED surface bypasses the bus entirely (`apps/desktop/main.js` `pane:input` writes straight to ConPTY) |
| TB-2 | Control protocol ↔ terminal text | Only signed, schema-validated envelopes are control; model/harness terminal output is untrusted and never parsed as a command | **IMPLEMENTED** — HMAC whole-envelope minus integrity (`control_plane/ipc/envelope.py`, Node mirror `apps/desktop/ipc/envelope.js`, parity test `test_envelope_cross_language_parity.py`) |
| TB-3 | Sovereign ↔ MCP | Requests carry authenticated node identity + role + task + scope; MCP holds **no** authorization logic; every write provenance-stamped, lands CANDIDATE unless role permits more | **IMPLEMENTED** — policy delegation `control_plane/policy.py` via `CollaborationService`; provenance stamps in `persistence/store.py` write fence |
| TB-4 | Node ↔ harness/model | Harness config (`AGENTS.md`, MCP config, model output) is node-controlled untrusted input; enforcement lives outside the harness (supervisor + broker + workspace isolation) | **PARTIAL** — supervisor + workspace isolation real (`node_runtime/supervisor/`, worktree isolation); harness-config-injection adversarial tests ABSENT (see T2) |
| TB-5 | Voice ↔ command bus | Transcripts are proposals (`propose_command`), never executions; broker + approval queue in between | **IMPLEMENTED** — `voice_bridge/command_broker.py` propose-only + approval queue (`approve()` refuses non-operator) |
| TB-6 | Profile boundary | Fail-closed loader; a cloud adapter requested under `offline_airgapped` aborts startup with a logged violation | **IMPLEMENTED** — `control_plane/profiles/loader.py` `ProfileViolation` fail-closed; wired into product path via `profile_loader_from_host()` |

## Threats and mitigations

| # | Threat | Boundary | Mitigation | Status |
|---|---|---|---|---|
| T1 | Terminal text parsed as control | TB-2 | Signed envelopes only (message@1.0); renderers never eval terminal output | **IMPLEMENTED** — envelope signing above; renderer never parses PTY output as control |
| T2 | Harness config injection (`AGENTS.md`, MCP config) | TB-4 | Node-controlled untrusted input; Sovereign policy never read from harness config; adversarial tests | **PARTIAL** — policy-from-harness-config refusal real (policy loads from repo `control_plane/` only); the named ADVERSARIAL TESTS are **NOT IMPLEMENTED** (registered) |
| T3 | Codex-class nested autonomy exceeding profile | TB-4 | Supervisor sandbox: worktree ACL, deny-by-default egress, broker-mediated exec; violations logged + node paused | **NOT IMPLEMENTED** as specified — of the three named legs only worktree isolation exists; deny-by-default EGRESS and broker-mediated exec with pause-on-violation were never built (registered) |
| T4 | Naked model/agent session joins orchestration | TB-4 | Registration refused unless supervisor-spawned (node@1.0); periodic process audit | **PARTIAL** — registration gate real (`provider_node_registration.py` `_OP12_PANE_NODE_ADAPTERS`); the PERIODIC PROCESS AUDIT is **NOT IMPLEMENTED** (registered) |
| T5 | Worker self-canonization / memory contamination | TB-3 | Server-side lifecycle enforcement (memory@1.0); CANDIDATE quarantined from ACCEPTED; gates only path to ACCEPTED | **IMPLEMENTED** — lifecycle legality in store fence + gates; candidate/synthesis separation enforced server-side |
| T6 | Silent last-write-wins on canonical memory | TB-3 | Immutable append + CAS + conflict_record objects | **IMPLEMENTED** — CAS publish path hardened by W-69 (`persistence/cas.py`: existence check, ordering, PID temp, fsync) |
| T7 | MCP server accumulates authority / compromised | TB-3 | No policy in MCP; Sovereign-signed authorization; separate process; read/append capability only | **PARTIAL** — no-policy + separate process + signed transport real; "read/append capability only" is not a mechanically enforced capability set (U349-family scope notes apply) |
| T8 | MCP outage mid-project | — | Fail-closed node behavior (F5); local checkpoints (checkpoint@1.0); reconciliation before resume | **PARTIAL** — F5 fail-closed + checkpoints real; W-55 degraded the STARTUP kill to structured faults (recovery-on-next-call), full mid-project reconciliation not exercised end-to-end |
| T9 | Voice mis-transcription → destructive action | TB-5 | Confidence threshold; propose-never-execute; clarification; approval queue; transcript log | **PARTIAL** — W-80 RETRACTION: the threshold detects SILENCE ONLY (`silence_only_confidence`; NeMo calibration PARK-R10/U140 OPEN). Propose-never-execute + approval queue + transcript log carry the boundary |
| T10 | Ambient/replayed audio issues commands | TB-5 | PTT/explicit trigger only; operator-presence assumption; protected actions always queued | **IMPLEMENTED** within its stated assumption — push-to-talk trigger + protected verbs always queued (`DESTRUCTIVE_VERBS`/`PROTECTED_VERBS` branch); the operator-presence ASSUMPTION is disclosed, not enforced |
| T11 | Cloud adapter under offline profile | TB-6 | Fail-closed profile loader aborts startup | **IMPLEMENTED** — invariant 20 branch reachable on the product path (`profile_loader_from_host`) |
| T12 | Voice audio exfiltration | TB-5/6 | Transcribe-then-discard; local-only TTL retention; zero egress offline (D-VOICE-04) | **IMPLEMENTED** — transcribe-then-discard in `wsl_parakeet.py` (retains nothing); offline egress rests on TB-6's fail-closed loader |
| T13 | Subscription over-concurrency (ToS breach) | — | I-X3 governor in supervisor + status-bar visibility; raise only after R8 verification | **IMPLEMENTED** — durable ledger `terminal_lease.py` (W-73-hardened) + in-process governor + durable baseline seeding; status-bar visibility pinned |
| T14 | CoWork silently modifies canonical files | TB-3 | Governed client class; canonical resources read-only to it; every access logged | **NOT IMPLEMENTED** — one docstring mention repo-wide; no governed CoWork client class exists (registered) |
| T15 | Stale conductor state after succession | — | Staleness checklist before first assignment (F4 / Plan §19.1) | **IMPLEMENTED** — succession staleness checks (`control_plane/recovery/succession.py`, age-within-limit pins) |
| T16 | Debate as unbounded token sink | — | Cost governor: per-debate budget, per-caller quota, global cap, hard ≤5 rounds | **PARTIAL** — ≤5 rounds enforced on BOTH paths; budget/quota/cap enforced ONLY on the `debate_service` path; the MCP collaboration path records `budget_units` and NEVER READS it ([[U349]]/[[U494]], W-61 CONSTRAINED) |

## Failure modes & recovery (Plan §11.2)

Status: **PARTIAL** as a set. Control-plane crash recovery (SQLite WAL + snapshots), node-crash
TERMINATED→READY, conductor succession (F4) and disk-full fail-closed event log are implemented
(`persistence/store.py`, `control_plane/nodes/`, `control_plane/recovery/`). The GPU-OOM residency
eviction leg is NOT IMPLEMENTED as stated — the planner exists
(`scheduler/residency_planner/residency_planner.py`) but eviction-under-pressure with visible
queuing was never demonstrated end-to-end (registered). WSL/Parakeet down → voice disabled, text
unaffected, holds (voice is never load-bearing).

## Build-time analogue (Buildout Directive §2.3)

The repo's own guardrails mirror T3/T4. Status: **PARTIAL**, and the original blanket sentence is
retracted. What holds: `.claude/hooks/guard.py`'s `docs/canonical/` protection survived all 15
recorded path tricks on the Write/Edit tools. What does NOT (review S-01..S-05): the protection is
not applied to the Bash tool at all (`echo > docs/canonical/<frozen>.md` is ALLOWED);
`guard.py` FAILS OPEN on four error paths; the outside-project-root check is dead code on Windows;
the BASH_BLOCK regexes are evadable (quoting, variable indirection, `git -c x=y push`). The freeze
is a write-tool-path control, not a content invariant — nothing runs the manifest check
automatically. Enforcement location that DOES hold: `tools/manifest/compute_manifest.py --check`
plus this loop's own per-commit discipline.
