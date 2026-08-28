# PHASE 14B GATE EVIDENCE — First live frontier adapter, Claude Code (`gate/phase-14b`, HIGH-STAKES)
Autonomous loop iteration 23 · 2026-07-18Z · **phase-gate close** · mandatory independent gate-validator
(directive §9 track 14B is a high-stakes gate — independent gate-validator confirmation required —
**and** the subscription-governor deep re-inspection is named as part of this gate).

## Objective
Close Phase 14B (directive §9 table 14B, §10.1; register OP-4/OP-5): prove the chain
**operator-authenticated provider CLI → supervised terminal → Sovereign node identity → MCP
context/artifact access → scoped assignment → structured result → gate** for **exactly ONE**
provider — **Claude Code** (OP-5 delegated selection). Before any live call: an enforced,
fail-closed `LIVE_OPERATION_AUTHORIZED` config read by the roster/profile loader; R8 ToS
verification recorded; the credential never read/extracted/stored/transmitted (§2.2); I-X3 = one
terminal; subscription-governor deep re-inspection at this gate.

14B was decomposed (directive §3.2, large phase) into four named sub-steps, one per iteration:
`.liveflag` → `.r8tos` → `.adapter` → `.gate` (this). No gate tag for a sub-step; the high-stakes
phase gate closes here.

## Sub-step ledger (each self-checked, gate-validated, evidenced)
| Sub-step | Content | Work | Evidence | Verdict |
|---|---|---|---|---|
| `.liveflag` | Enforced `LIVE_OPERATION_AUTHORIZED` gate landed FIRST, before any live path (`control_plane/profiles/live_authorization.py`): absence⇒DENIED (enforcement-by-absence), malformed/out-of-scope⇒RAISE; scope pinned in code (register OP-4, provider claude_code, 1 terminal I-X3); `assert_provider_live` the gate every live-spawn must call; read by `ProfileLoader.assert_startup`/`build_roster` | `0bfc2ec` | `PHASE14B_LIVEFLAG_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.r8tos` | R8 ToS & concurrency verification RECORDED for Claude Code before any live call (Plan §18.3 six-item checklist): first-party headless CLI ⇒ supervised-subprocess spawn is its intended mode; no verified per-account concurrency ⇒ allowance stays 1 (I-X3), governor unchanged; live-terms dated retrieval = `[OPERATOR]` at `.adapter` | `4da702d` | `PHASE14B_R8TOS_EVIDENCE_REPORT.md`, `R8_TOS_VERIFICATION_CLAUDE_CODE.md` | PASS (sub-step) |
| `.adapter` | First LIVE adapter behind the governed `ModelWorkerAdapter` contract; fail-closed supervised spawn `node_runtime/supervisor/frontier_spawn.py` (5 ordered gates + release-on-construct-fail); `adapters/frontier/claude_code.py` (mock-first + real `ClaudeCliBackend` never in the default suite; §2.2 env scrub; `ClaudeCodeAuthError(BackendAuthPause)` re-raised by `execute()`); MOCK-FIRST proven end-to-end; single live smoke **skip-with-record** | `23158e3` | `PHASE14B_ADAPTER_EVIDENCE_REPORT.md` | PASS_WITH_RESERVATIONS (sub-step) |

## Gate exit criteria (directive §9 table 14B, §10.1) — disposition
- **Enforced `LIVE_OPERATION_AUTHORIZED` config, fail-closed, read by the roster/profile loader,
  before any live path:** DELIVERED (`.liveflag`). Verified by the gate-validator by execution:
  absence⇒DENIED; out-of-scope⇒RAISE; `terminals=True` cannot masquerade as `1` (bool guard fires).
- **R8 ToS verification recorded before the first live call:** DELIVERED (`.r8tos`,
  `R8_TOS_VERIFICATION_CLAUDE_CODE.md`). Conservative conclusion: stay at 1 terminal; the
  `[OPERATOR]` dated live-terms retrieval remains a hard gate for the live smoke.
- **Adapter behind the base contract, supervised terminal (no naked session, inv 2):** DELIVERED
  (`.adapter`). `build_claude_code_adapter` → `ModelWorkerAdapter`; a non-supervisor context is
  refused (`NakedLaunchRefused`). The real supervisor/startup path (`frontier_spawn`) enforces all
  five gates in order and releases the terminal on construct-fail so the I-X3 count never wedges.
- **Credential never read/extracted/stored/transmitted (§2.2):** ENFORCED. `holds_provider_credential()`
  is False; `build_command` carries no key/bypass flag; `build_env` scrubs the full documented key
  set **and** a fail-closed prefix/substring superset (validator independently probed
  `OPENAI_API_KEY`, `ANTHROPIC_FOO`, `claude_code_oauth_token`, `SESSION_TOKEN`, `VERTEX_TOKEN`,
  `CLAUDE_CODE_USE_*` endpoint-redirects — all scrubbed; `PATH`/`HOME` kept). No credential file read.
- **I-X3 = exactly one terminal; no second provider without new authorization:** ENFORCED and
  re-inspected (below). Governor `subscription_governor.py` **byte-unchanged since phase 4**.
- **Subscription-governor deep re-inspection (named part of this gate):** PERFORMED (below).
- **THE single live `claude` smoke:** **SKIP-WITH-RECORD this session (no live call), honestly**
  (directive §10.4) — two independent, each-sufficient reasons: (a) `config/live_operation.json` is
  absent by design and the loop must not create it (creating it IS self-authorization once a live
  path exists — inv 1); (b) the R8 §6 `[OPERATOR]` dated live-terms retrieval + support-confirmation
  are unmet in this non-interactive session. The mock-first proof exercises the exact same governed
  path end-to-end; only the live subprocess call is owed to an operator-authorized run. **No
  live-capability claim is made.**

## Subscription-governor DEEP RE-INSPECTION (directive names this as part of the 14B gate)
Verified in code and by the gate-validator's own execution against
`node_runtime/supervisor/subscription_governor.py`:
- **Allowance stays 1, never raised on inference/silence.** Default `allowance=1`; `frontier_spawn`
  registers `allowance=1`; `register_subscription` is idempotent (`setdefault`) so a present
  subscription cannot be widened (validator probe: re-registering the same ref with `allowance=99`
  left it **1**). Only an explicit `allowance=` on first registration can exceed 1 — the R8-verified
  path never passes >1.
- **I-X3 holds, fail-closed.** A second node on a subscription at allowance 1 raises
  `SubscriptionLimitExceeded` (`test_second_terminal_on_subscription_is_refused`); an unregistered
  subscription is refused ("refuse to spawn uncounted").
- **Release-before-acquire on succession, owned by succession code.**
  `control_plane/recovery/succession.py::perform_handoff` calls `release()` then `acquire()`
  (order asserted by `test_ix3_succession_handoff_owned_by_succession_code`; a successor acquire
  without the handoff fails).
- **Byte-unchanged since phase 4** (native git): `git log --oneline -- …/subscription_governor.py`
  → single line `78559ac feat(phase4)…`; `git diff 78559ac -- …/subscription_governor.py` → **empty**.

## Native-git re-confirm (the three items the `.adapter` sub-step validator's denied-git could not close)
The `.adapter` validator's Bash `git` was blocked by a permission-prefix mismatch (not a repo
problem); the `.gate` validator has native git and re-confirmed all three:
- `git ls-files config/` → **only** `config/live_operation.example.json`; the real
  `config/live_operation.json` is **untracked** (`.gitignore:19`) and **absent on disk**.
- `git status --porcelain docs/canonical/` → **empty** (frozen set untouched); validator also
  recomputed sha256 of the three governed docs and matched CLAUDE.md byte-for-byte
  (Plan v1.0.1 `8C9B7240`, Plan v1.0 `668089B5`, Directive `CC414372`).
- `subscription_governor.py` byte-unchanged (above).

## Mandatory independent gate-validator (high-stakes) — VERDICT: PASS_WITH_RESERVATIONS
Isolated context, every command re-run and every load-bearing claim verified by the validator's own
execution (not the builder's report). It additionally attempted to **refute** the central claims and
found **no bypass**: no path to a live `claude` call without an operator-authored config; allowance
cannot be raised without an explicit verified argument; no plausible credential var escapes the
scrub among the CLI's documented families. Observed tallies (validator-run): **401 pytest passed /
0 skipped**; **131 JS pass / 0 fail / 0 skipped**; frontier/live subset **34 passed** with the
skip-with-record tests green (no live process spawned).

Reservations (all non-blocking, honestly recorded):
- **R1 — real-CLI chain never exercised this session (by design, gate-accepted).** The end-to-end
  LIVE chain is proven only with `MockClaudeCliBackend`; the single live smoke is skip-with-record
  per §10.4. This is exactly what the criteria require ("skip-with-record … never faked"), not a
  defect. The first real call remains an operator-gated future event, correctly fenced. Owned;
  tracked (UNRESOLVED live-smoke deferral note).
- **R2 — env-scrub keys on `API_KEY`/`APIKEY`, not a bare `_KEY` suffix.** A hypothetical
  `*_KEY`-only secret survives scrubbing, but is **not a §2.2 vector for this adapter** — the
  `claude` CLI reads only `ANTHROPIC_*`/`CLAUDE_CODE_*` vars, all prefix-scrubbed. Recorded as
  **U29** (`HARDENING_BACKLOG.md`, `UNRESOLVED_ISSUE_REGISTER.md`); non-blocking.
- **R3 — `HTTP(S)_PROXY` intentionally preserved** for connectivity; a malicious host proxy is a
  host-trust concern outside this adapter's remit and does not reach the OAuth credential
  (host-native store, TLS). Accept; non-blocking.

Precedent: high-stakes gates P3A, P11, and 14A also closed **PASS_WITH_RESERVATIONS** with
documented non-blocking reservations — consistent with this disposition.

## spec-auditor
**N/A for `.gate`** — this work unit adds no substantive new source code (evidence report + register
rows + hardening-backlog row + loop state only). spec-auditor already ran on `.adapter`'s substantive
new code (`2 MAJOR + 2 MINOR ALL FIXED pre-commit`: credential env-scrub completeness + overclaim;
dead fail-closed auth-pause path → `BackendAuthPause` re-raised by `execute()`; auth-marker
specificity; bounded reason) and was CLEAN on the load-bearing invariants.

## Delegated decisions / register closures at this gate
- **OP-4 / OP-5** remain the authorizing rows (Phase 14 in full; live provider = Claude Code, 1
  terminal). No new authorization is created here; the loop does **not** write
  `config/live_operation.json`.
- The `[OPERATOR]` R8 §6 live-terms items stay open as an operator-owned precondition for the live
  smoke — carried to the final product report, not a build failure.

## Substitutions / deferrals (directive §6/§10.4; honest record — carried to the final product report)
- **The single live smoke is skip-with-record** (no `claude` subprocess ran): the real
  `ClaudeCliBackend.generate` path is proven only at the pure command/env layer; the end-to-end live
  subprocess is owed to an operator-authorized run (config present + `[OPERATOR]` live-terms
  discharged). Recorded, not faked. **No live-capability claim.**
- Everything else in §2 stands: no push, no credential handling, nothing outside repo root, canonical
  frozen, registers/evidence append-only.

## Open items carried past the gate (recorded, not failures)
- **[OPERATOR] R8 §6 live-terms** — dated Consumer Terms + Usage Policy + Claude Code headless docs
  retrieval; confirm no clause prohibits first-party wrapped-CLI under the operator's own
  subscription; support-confirmation for any concurrency raise.
- **U5** — provider per-account concurrency (verified-at-1; raise-branch moot until verified).
- **U29** — adapter env-scrub bare `_KEY` suffix (R2, non-blocking).
- **Live smoke** — one operator-authorized `claude` call owed before any live-capability claim.

## Test totals (whole repo, this iteration)
- Python: **401 passed / 0 skipped** (`py -3.12 -m pytest tests/ -q`, ~70 s) — builder self-check and
  independent gate-validator agree.
- JS: **131 passed / 0 failed / 0 skipped** (`node --test "terminal/**/*.test.js"
  "apps/desktop/**/*.test.js"`).
- Frontier/live subset: **34 passed** (`test_frontier_claude_code.py` + `test_claude_code_adapter.py`
  + `test_live_authorization.py`), including live-smoke skip-with-record (no live process spawned).

## Gate verdict
**`gate/phase-14b` — PASS_WITH_RESERVATIONS.** The full 14B chain (`LIVE_OPERATION_AUTHORIZED`
enforced first → R8 ToS recorded → live adapter behind the base contract + fail-closed supervised
spawn) is real, mock-proven end-to-end, and independently confirmed; the subscription-governor deep
re-inspection holds (allowance 1, I-X3, no raise-on-inference, release-before-acquire, byte-unchanged);
the credential invariant (§2.2) is enforced and probed. The single live `claude` call is honestly
skip-with-record (§10.4) — no live-capability claim. Reservations R1–R3 are documented and
non-blocking.

## Commits
Work already committed at `.adapter` (`23158e3`). This gate adds the evidence report + register rows +
hardening-backlog row (no new source): evidence/register commit → **tag `gate/phase-14b`** → loop-state
commit. Two-commit convention.

## Next
`phase-14c` — OpenCode live local harness (directive §9 table 14C, §10.2). Entry condition: OpenCode
binary present on host or its authorized download from the official distribution source (integrity
verified, source URL + hash recorded); a failed 14B/14C/14D entry attempt is recorded and does not
block the rest (§10.4).
