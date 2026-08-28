# PHASE 15A GATE EVIDENCE — Live activation + concurrency governor (`gate/phase-15a`, HIGH-STAKES)
Autonomous loop iteration 35 · 2026-07-19Z · **phase-gate close** · mandatory independent gate-validator
(directive §11 track 15A is a high-stakes gate — independent gate-validator confirmation required —
**and** the subscription-governor deep re-inspection is named as part of this gate).

## Objective
Close Phase 15A (directive §11 track 15A, §12 OP-7; register **OP-6**): move live activation from the
OP-4 single-provider restraint to the OP-6 two-provider scope and stand up the enforced concurrency
governor for it. The chain to prove: **enforced `LIVE_OPERATION_AUTHORIZED` two-provider config
(fail-closed, code-pinned, loop-created under OP-6) → per-subscription allowance=2 governor
(operator-ordered, governor-capped, reversible) → dated R8 records for both providers → the live `n/2`
count surfaced in the shell status bar.** No live CLI call is made at this gate; the config being
present enables a live *path*, but the gate itself spawns nothing and handles no credential (§2.2).

15A was decomposed (directive §3.2, large phase) into four named sub-steps, one per iteration:
`.liveauth` → `.governor` → `.r8` → `.statusbar` → `.gate` (this). No gate tag for a sub-step; the
high-stakes phase gate closes here.

## Sub-step ledger (each self-checked, gate-validated, evidenced)
| Sub-step | Content | Work | Evidence | Verdict |
|---|---|---|---|---|
| `.liveauth` | `control_plane/profiles/live_authorization.py` rewritten to the OP-6 two-provider scope `{providers:[claude_code, openai_codex_cli], terminals_per_subscription:2}`, `config_version 1.1`, authorizing row **OP-6**; scope **code-pinned** so a present config can only match-or-narrow, never widen (3rd provider raises, `terminals >2/<1/bool True` raises, wrong row raises, old 1.0 config raises, absence⇒DENIED). Real `config/live_operation.json` **CREATED by the loop** (OP-6 §11(c) authorizes it — cites OP-6, gitignored, authorization switch not a credential §2.2). `codex` shorthand normalizes to `openai_codex_cli`. | `1fb8b30` | `PHASE15A_LIVEAUTH_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.governor` | `node_runtime/supervisor/subscription_governor.py` upgraded to per-subscription allowance=2 with hard cap `MAX_ALLOWANCE=2` (`register_subscription(allowance>2)` RAISES, registers nothing); default stays 1 (never raised on inference); re-registration reconciles the stored allowance (a narrowing binds without evicting a mid-generation holder, inv 22-analogue). `frontier_spawn.py` gate (5) reads `allowance=live_auth.terminals_per_subscription`, not hardcoded (inv 1). | `e6886b0` | `PHASE15A_GOVERNOR_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.r8` | Dated R8 ToS records for BOTH OP-6 providers on file: NEW `R8_TOS_VERIFICATION_OPENAI_CODEX.md` (`openai_codex_cli`) + existing `R8_TOS_VERIFICATION_CLAUDE_CODE.md` (`claude_code`, from `phase-14b.r8tos`) + NEW `R8_OP6_CONCURRENCY_BASIS_NOTE.md` recording allowance=2 as **operator-ordered (OP-6 §11(b))**, not an inferred per-account concurrency finding (both providers verified-at-1). | `078f612` | `PHASE15A_R8_EVIDENCE_REPORT.md` | PASS (sub-step) |
| `.statusbar` | The OP-6 `n/2` count RENDERED in the shell status bar. NEW `terminal/statusbar/statusbar-model.js` (pure fail-closed fold — unreadable ⇒ em-dash `—/2`, never a fabricated `0/2`) + `apps/desktop/statusbar/source.js` (read-only IPC read) + read-only `SubscriptionStatusControlSurface` in `control_plane/ipc/gateway.py` (holds no authorization, I-M2). D-P14-1 substitution: rendered bar is an operator-run metric; the governance-bearing logic is proven headlessly incl. 2 LIVE tests. | `05d140d` | `PHASE15A_STATUSBAR_EVIDENCE_REPORT.md` | PASS (sub-step) |

## Gate exit criteria (directive §11 track 15A) — disposition
- **Rewrite `live_authorization` scope per OP-6 (two providers, 2 terminals/subscription, cites OP-6):**
  DELIVERED (`.liveauth`). Gate-validator re-executed the fail-closed matrix by direct call:
  absence⇒`authorized=False`; `gemini_cli` (3rd provider)⇒raises; `terminals=True`⇒raises (bool
  guard fires before the int check); `terminals=3`⇒raises; `register_row=OP-4`⇒raises; valid config⇒
  `terminals_per_subscription=2`, both providers live. Builder re-ran the loader live this session:
  `is_provider_live` True for `claude_code`/`openai_codex_cli`/`codex` alias; `gemini`⇒
  `LiveAuthorizationError`.
- **Create `config/live_operation.json`:** DELIVERED (`.liveauth`). Present on disk, gitignored
  (`.gitignore:19`), only `config/live_operation.example.json` is tracked (`git ls-files config/`);
  content is `{config_version:"1.1", register_row:"OP-6", scope:{providers:[claude_code,
  openai_codex_cli], terminals_per_subscription:2}}` — an authorization switch carrying no secret
  (§2.2). OP-6 §11(c) is the authorization the 14B restraint (inv 1: the loop must not write this
  file under OP-4) was waiting for; scope is code-pinned so the file can only match-or-narrow.
- **Dated R8 records for both providers (documented basis + operator direction):** DELIVERED (`.r8`).
  Both provider records present and dated; the concurrency-basis note records allowance=2 as
  operator-ordered (OP-6 §11(b)), with R8's own concurrency finding remaining verified-at-1 for both.
- **Subscription governor upgraded to per-subscription allowance=2 with the `n/2` count live in the
  shell status bar:** DELIVERED (`.governor` + `.statusbar`). `MAX_ALLOWANCE=2` hard cap;
  `frontier_spawn` reads the allowance from the enforced authorization; `status()` yields the `n/2`
  data; the pure fold + read-only IPC source render it fail-closed. The rendered Electron bar is an
  operator-run metric (owed receipt, below).
- **Fail-closed paths re-tested (absence⇒DENIED unchanged):** VERIFIED by the gate-validator's own
  execution — absence⇒DENIED preserved through the scope rewrite.

## Subscription-governor DEEP RE-INSPECTION (directive names this as part of the 15A gate)
Verified in code and by the gate-validator's own execution against
`node_runtime/supervisor/subscription_governor.py`:
- **Allowance stays ≤2, never raised on inference/silence.** `MAX_ALLOWANCE=2`; the default is 1;
  `register_subscription(allowance=3)` raises `ValueError` and registers nothing (validator probe:
  `subx registered? False`); a widen re-register (`allowance=5`) raises and leaves the stored
  allowance at 2. Only an explicit OP-6-scoped config value (`terminals_per_subscription`, clamped
  `[1,2]`) can set 2 — nothing raises on inference.
- **Three independent fail-closed layers keep concurrency ≤2:** config clamp `[1,2]` + bool guard
  (`LiveAuthorization._validate_terminals`), spawn gates (1)/(2) refuse a DENIED auth before the
  governor is consulted (+`allowance<1` guard), and the governor hard cap.
- **I-X3 holds, fail-closed.** `acquire` refuses the 3rd terminal (`SubscriptionLimitExceeded`,
  active stays `['n1','n2']`); an unregistered subscription is refused.
- **Release-before-acquire on succession, owned by succession code.**
  `control_plane/recovery/succession.py::perform_handoff` calls `release()` (line 165) then
  `acquire()` (line 166) and returns `["release","acquire"]`; only the successor remains active.
- **Byte-unchanged since `.governor` (`e6886b0`)** (native git): `git diff --stat e6886b0 HEAD --
  …/subscription_governor.py` → **empty**. `.statusbar` added only the display path.

## D-P14-1 owed operator-run receipt (honestly recorded, substitution pattern §6)
The Electron-main JS added at `.statusbar` — the `statusbar:fetch` handler + third read channel
`statusClient` in `apps/desktop/main.js`, `preload.js` `statusBar()` intent, and the renderer
painting — cannot be exercised under Electron's embedded runtime in this non-interactive session
(ConPTY/Electron do not execute headlessly here; a painted GUI bar is inherently an operator-run
metric, as with the Phase-1 spike and the 14A window). It is recorded as an **OWED operator-run
receipt**, not claimed as a produced rendered surface. The governance-bearing logic *is* proven
headlessly: the pure fold (`statusbar-model.js`) and the read-only IPC source (`source.js`) are
covered by the JS suite including **2 LIVE tests** in which a real Node `IpcClient` read a REAL seeded
`SubscriptionGovernor` (`apps/desktop/test/fixtures/serve_seeded_governor.py`) through the REAL Python
gateway (`claude_code 1/2 active`, `openai_codex_cli 0/2 idle`). §6/§10.4 honesty: the shipped shell's
default Echo gateway returns `ok:false` for `subscription_status`, so the bar shows the fail-closed
em-dash today; the governor feed wires to the live spawn path at **15E** — no live production count is
claimed. The gate-validator confirmed the builder is not overclaiming a rendered Electron surface.

## §2.2 / §2.4 (no credential, no live call by the gate)
Both `claude` and `codex` ARE present and authenticated on host, and the live config IS on disk, so
live auth resolves AUTHORIZED. Despite that, the gate makes **no live CLI call**: the two non-mock
`attempt_live_smoke` tests use DENIED-by-absence (tmp path) and unconfirmed-terms — both raise at the
supervised spawn gates before any backend/CLI invocation; the real backend `generate()` is never
called (only its pure command/env builders are tested). The env-scrub test proves no
`ANTHROPIC_API_KEY`/OAuth token transits to a child env; `holds_provider_credential()` is False; the
config file carries no secret. Verified by the gate-validator independently.

## Native-git re-confirm (tag lineage, frozen canonical, config tracking)
- **subscription_governor.py byte-unchanged since `e6886b0`** (empty `git diff --stat`).
- **`config/live_operation.json` untracked + absent-from-index** — `git ls-files config/` returns
  **only** `config/live_operation.example.json`; the real config is gitignored (`.gitignore:19`) and
  present only on disk. (The gate-validator's Bash denied `git check-ignore`; it substituted direct
  `.gitignore` line-19 inspection + `git ls-files config/` — equivalent evidence.)
- **`docs/canonical/` untouched** — `git status --porcelain docs/canonical/` **empty**; the four
  CLAUDE.md-cited SHA-256 prefixes recomputed and matched byte-for-byte: Buildout `CC414372`, Plan
  v1.0.1 `8C9B7240`, Plan v1.0 `668089B5`, Canonical Handoff `6D3FD03B`.
- **Tags:** `gate/phase-14a`/`14b`/`14c`/`14e` present, **`gate/phase-14d` ABSENT** (correct — WSL/NeMo
  entry unmet, skip-with-record), **`gate/phase-15a` not yet tagged** (this gate closes it).
- **`.gate` adds no new source** — the only untracked working-tree entry is
  `apps/desktop/package-lock.json` (a generated npm lockfile from an operator host `npm install`, not
  product source, not a canonical edit); it is left untracked and out of the gate commits.

## Mandatory independent gate-validator (high-stakes) — VERDICT: PASS
Isolated context, every command re-run and every load-bearing claim verified by the validator's own
execution (not the builder's report). It attempted to refute the central claims and found **no
bypass**: no path that raises concurrency past the OP-6 cap of 2, no path to live authorization
without an authorized config, and the fail-closed refutations (absence⇒DENIED, 3rd provider raises,
`terminals=True` cannot masquerade as 1) all held. Observed tallies (validator-run): **491 pytest
passed / 0 failed / 0 skipped**; **149 JS pass / 0 fail / 0 skipped** (product suites: apps/desktop +
terminal); **180 JS** including the explicitly-throwaway Phase-1 spike rig (also green).

Reservations (both **non-blocking**):
- **R1 — Owed Electron-runtime receipt (D-P14-1).** The `statusbar:fetch` handler, `statusClient`,
  preload `statusBar()`, and renderer painting are not exercisable under Electron in this
  non-interactive session and are correctly deferred to an operator run (§6 substitution). Honestly
  recorded, not overclaimed; the governance-bearing logic is proven headlessly. Owned by the builder;
  the operator run remains OWED (carried to the final live report).
- **R2 — JS count transparency.** "149 JS" is the product-code count; total including the throwaway
  spike rig is 180. Not a substantive discrepancy — the spike rig is explicitly throwaway — noted so
  the number is unambiguous.

Precedent: high-stakes gates P3A, P11, 14A, 14B, 14E closed with documented non-blocking reservations;
15A closes **PASS** with the two reservations above.

## spec-auditor
**N/A for `.gate`** — this work unit adds no substantive new source code (evidence report + register
rows + loop state only). spec-auditor ran on every substantive `.liveauth`/`.governor`/`.statusbar`
sub-step (CLEAN on all load-bearing invariants; the MINOR/NIT findings were fixed pre-commit and
re-tested at each sub-step, per those sub-step reports).

## Delegated decisions / register closures at this gate
- **OP-6** (directive §11) is the authorizing row for two-provider live activation
  (`claude_code` + `openai_codex_cli`), 2 terminals/subscription, loop-created `config/live_operation.json`.
  **OP-7** (§12) sets the revised track order 15A → 15C → 15B → 15D → 15E.
- **D-P14-1** (any new JS touching Electron main is exercised under Electron's embedded runtime before
  its gate closes) is honored by substitution: the governance logic is headless-proven; the rendered
  bar is the owed operator-run receipt (R1). No decision is force-closed on an un-produced surface.

## Substitutions / deferrals (directive §6/§10.4; honest record — carried to the final live report)
- **The rendered Electron status bar is an operator-run metric** (D-P14-1 substitution); the pure fold
  + live IPC read are headless-proven. No live production `n/2` count is claimed — the governor feed
  wires to the live spawn path at 15E.
- **No live CLI call at this gate** — the live path is enabled (config present, CLIs authenticated) but
  the first live `claude`/`codex` smokes are owed to 15B/15C (per-model probes + smokes). No
  live-capability claim is made here.
- Everything else in §2 stands: no push, no credential handling, nothing outside repo root, canonical
  frozen, registers/evidence append-only.

## Open items carried past the gate (recorded, not failures)
- **D-P14-1 R1** — one operator Electron run to exercise the `.statusbar` shell wiring (owed receipt).
- **Live smokes** — per-model live `claude` / `codex` calls owed to 15B / 15C before any live-model
  capability claim.
- **U5** — provider per-account concurrency (both verified-at-1; the raise to 2 is operator-ordered,
  not an inferred finding; governor-capped and reversible).
- **U29** — adapter env-scrub bare `_KEY` suffix (non-blocking; the `.statusbar` cross-language
  constants pin and the frontier scrub superset remain in force).

## Test totals (whole repo, this iteration)
- Python: **491 passed / 0 skipped** (`py -3.12 -m pytest tests/ -q`, ~112 s) — builder self-check and
  independent gate-validator agree.
- JS (product): **149 passed / 0 failed / 0 skipped** (`node --test` on the 10 `terminal/test/*` + 7
  `apps/desktop/test/*` files; includes the 2 LIVE status-bar IPC-read tests). Total incl. the
  throwaway spike rig: **180 passed / 0 failed**.

## Gate verdict
**`gate/phase-15a` — PASS.** The full 15A chain (OP-6 two-provider `LIVE_OPERATION_AUTHORIZED` enforced
first + `config/live_operation.json` created → per-subscription allowance=2 governor, governor-capped
→ dated R8 records for both providers → live `n/2` status bar) is real and independently confirmed;
the subscription-governor deep re-inspection holds (allowance ≤2, no raise-on-inference,
release-before-acquire, byte-unchanged since `.governor`); the credential invariant (§2.2) is enforced
and probed; no live CLI call is made. Reservations R1–R2 are documented and non-blocking.

## Commits
Sub-step work already committed (`.liveauth` `1fb8b30`, `.governor` `e6886b0`, `.statusbar` `05d140d`;
`.r8` was a documentation unit `078f612`). This gate adds the phase-level evidence report + register
row (no new source): evidence/register commit → **tag `gate/phase-15a`** → loop-state commit.
Two-commit convention.

## Next
`phase-15c` — OpenAI adapter (Codex CLI) (directive §11 track 15C, §12 OP-7 revised order 15A → 15C).
Entry condition: `codex` CLI installed + authenticated by the operator (per OP-8 the operator ran
`codex login` this session). If unauthenticated at 15C, poll / skip-with-record with the exact
operator step (OpenAI legs OWED), continue to 15B/15D, re-attempt 15C before 15D closes.
