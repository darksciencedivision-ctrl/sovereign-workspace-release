# Phase 15A · sub-step `.statusbar` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 34 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** carried by this evidence/register commit (two-commit convention)
**Phase gate:** `gate/phase-15a` remains **UNTAGGED** — the high-stakes 15A gate closes at
`.gate` with the mandatory independent gate-validator once all 15A sub-steps land.

## 1. Scope of this work unit

Fourth sub-step of Phase 15A ("Live activation + concurrency governor", directive §11,
register **OP-6**). `.governor` (iter32) upgraded the subscription concurrency governor to
the OP-6 per-subscription allowance of 2 and exposed the `n/allowance` count via
`SubscriptionGovernor.status()`. This unit **renders that count in the shell status bar**
(directive §11 track 15A: *"the n/2 count live in the shell status bar"*).

The DATA already existed (`status()` yields `{provider, allowance, active, in_use}` per
subscription). This unit adds only the **display path**: a pure view model, a read-only IPC
source, a read-only IPC surface exposing the count, and the shell wiring + tests. **No
concurrency logic changed** — `subscription_governor.py` is byte-unchanged this unit.

**D-P14-1 substitution (14A pattern):** the actual painted status bar is an operator-run
metric like the 14A window; it is verified headlessly by (a) the **pure view model** and
(b) a **Node client mirroring the IPC read path** that reads a **real seeded governor** over
the **real Python IPC gateway**. The Electron-main JS additions (a read handler + a read
channel) are exercised under Electron only by the operator run; their governance-bearing
logic (the fold + the read source) is covered headlessly. Recorded per directive §6.

## 2. What changed (working tree; base HEAD `9c2e915`)

| File | Change |
|---|---|
| `terminal/statusbar/statusbar-model.js` *(new)* | PURE, deterministic view model: folds `status()` into per-provider `n/allowance` rows. Both OP-6 providers (`claude_code`, `openai_codex_cli`) always surfaced with the cap visible. **Fail-closed display:** an unreadable governor (null / non-object) ⇒ `readable:false`, every row `state:"unknown"` with an em-dash `—/2` and `inUse:null` — **never a fabricated `0/2`**. A read-but-empty governor is an honest `0/2 idle` (distinct). A single malformed subscription is `unknown` on its own row (does not poison the bar). An unsurfaced-provider subscription is still shown (inv 27). Renders nothing, no I/O. |
| `apps/desktop/statusbar/source.js` *(new)* | Node source reading `subscription_status` over the D-IPC-01 channel (same `IpcClient` the shell proves against the gateway). Two entry points: `fetchSubscriptionStatus` (STRICT — throws on `ok:false`, propagates transport faults) and `fetchStatusBarModel` (DISPLAY — NEVER throws; degrades to a fail-closed unknown model carrying `.error`, because the bar is always visible). |
| `control_plane/ipc/gateway.py` | Added `SubscriptionStatusControlSurface` (read-only): ops `{health, subscription_status}` only. Holds **no authorization** (I-M2) — it cannot register/acquire/release or raise an allowance; it only reports the count the governor already computed. Fail-closed: a provider fault ⇒ signed `{ok:False, error}`, no fabricated count. **The rest of the file is unchanged.** |
| `apps/desktop/main.js` | `statusbar:fetch` read handler (fail-closed unknown model before the channel is up); a third read channel `statusClient` (own connection, like the inspector's, so a periodic poll never contends with the supervisor heartbeat on the sequential `IpcClient`); teardown closes it. |
| `apps/desktop/preload.js` | `statusBar()` read-only intent added to the sandboxed bridge. |
| `apps/desktop/renderer/{index.html,renderer.js}` | Bottom `#statusbar` strip: one chip per live provider with `n/2` and the allowance cap; `at-capacity`/`idle`/`unknown` styling; a fail-closed "concurrency count unavailable" note when `readable:false`. Thin view — computes nothing; polls on its own channel every 5 s. `esc()` before `innerHTML`, CSP unchanged. |
| `apps/desktop/test/fixtures/serve_seeded_governor.py` *(new)* | Live-test fixture: a real `IpcGateway` over a REAL `SubscriptionGovernor` seeded via its real API (register at allowance 2, acquire one Anthropic terminal ⇒ `1/2`; register OpenAI, no acquire ⇒ `0/2`). Prints the IPC handshake like `run_gateway`. |
| `terminal/test/statusbar-model.test.js` *(new)* | 11 headless view-model tests (both providers surfaced; real fold; at-capacity; **fail-closed unknown ≠ 0/2**; malformed record isolation; unsurfaced provider not dropped; deterministic ordering; summary). |
| `apps/desktop/test/statusbar-source.test.js` *(new)* | 5 unit (fake client — strict throw + display fail-closed) + **2 LIVE** (real `IpcClient` → real gateway → real seeded governor: reads `1/2`/`0/2`; a wrong integrity key yields an unknown model, no fabricated count). |
| `tests/unit/test_subscription_status_surface.py` *(new)* | 5 tests: real governor count reported; health liveness; **write-shaped ops refused (read-only, I-M2)**; provider fault fails closed with no fabricated result; many reads never mutate the governor. |
| `tests/unit/test_statusbar_constants_pinned.py` *(new)* | 2 cross-language pin tests (spec-audit M1/M2): the JS `SUBSCRIPTION_CAP` / `LIVE_PROVIDERS` literals are parsed from source and asserted equal to `subscription_governor.MAX_ALLOWANCE` / `live_authorization._AUTHORIZED_PROVIDERS` — the JS mirror cannot silently drift from its Python authority. |

## 3. Exit-criterion self-check (real command output)

**A. n/2 for BOTH providers, cap visible, correct classification** — `node --test terminal/test/statusbar-model.test.js` → **11/11 pass**. Both `claude_code` and `openai_codex_cli` surfaced with `allowance` cap; `1/2`→active, `2/2`→at-capacity, `0/2`→idle.

**B. Fail-closed display (unknown ≠ fabricated 0/2)** — the model tests pin: `status:null` / non-object / `ok:false` / transport fault ⇒ `state:"unknown"`, `inUse:null`, label `—/2`, explicitly `assert.notEqual(label, "0/2")`. A read-but-empty governor shows `0/2 idle` (honest zero). Distinction verified in both the model and source suites.

**C. Read-only surface, no authority (inv 7 / I-M2)** — `py -3.12 -m pytest tests/unit/test_subscription_status_surface.py -q` → **5/5 pass**. Write-shaped ops (`acquire`/`register_subscription`/`release`/`raise_allowance`/`read_status`) all refused; the surface has no acquire/register method; N reads never change the count.

**D. LIVE read path (not skipped)** — `node --test apps/desktop/test/statusbar-source.test.js` → **7/7 pass, 0 skipped**. The two `LIVE:` tests ran: a real `IpcClient` read a real seeded `SubscriptionGovernor` through the real Python IPC gateway and got `claude_code 1/2 active` + `openai_codex_cli 0/2 idle`; a wrong integrity key degraded to a fail-closed unknown model.

**E. No frozen artifact touched** — `git status --short docs/canonical/ schemas/` → empty. `git diff --stat` shows `subscription_governor.py` NOT in the changeset (the concurrency DATA source is byte-unchanged; only a read-only surface + view + tests were added).

**F. Full suites green** —
- `py -3.12 -m pytest tests/ -q` → **491 passed / 0 skipped** (was 484 at `.governor`; +7 = 5 surface tests + 2 cross-language pin tests).
- `node --test terminal/test/*.test.js` → **114 pass / 0 fail / 0 skipped** (was 103; +11).
- `node --test apps/desktop/test/*.test.js` → **35 pass / 0 fail / 0 skipped** (was 28; +7, incl. 2 live).

## 4. Invariants & prohibitions

- **inv 7 / I-M2 (access, not authority):** the new IPC surface reports a count only; it holds no allow/deny logic and cannot mutate the governor. Verified by test + by grep (no role checks, no acquire).
- **inv 21 / I-X3 (allowance cap 2):** the view model shows each subscription's own governed allowance and, for idle/unknown rows, the OP-6 ceiling `2` — it never widens or fabricates an allowance. The governor's hard cap (`.governor`) is untouched.
- **§2.2 (credentials):** zero credential handling anywhere in this unit.
- **Buildout §4:** deterministic fold; fail-closed on ambiguity (unreadable ⇒ unknown, never a number); observable (the count is on-screen; faults are surfaced, not hidden).
- **§6 / §10.4 honesty:** the live count is proven via a **seeded** governor over a real gateway. The **real product shell's** live population (the running gateway sharing the spawn-path governor) wires at **15E** (node-launcher spawns through supervisor + governor); until then the real shell renders the fail-closed **unknown** model rather than a fabricated count. **No live production count is claimed.**

## 5. Substitutions (directive §6) recorded

1. **Rendered status bar = operator-run metric** (like the 14A window / Phase-1 spike). The governance-bearing logic beneath it (the pure fold + the IPC read source) is headlessly proven; the Electron-main handler + renderer painting are operator-verified. D-P14-1 satisfied for this sub-step; the phase gate (`.gate`) owns the final Electron-runtime confirmation.
2. **Seeded governor for the live read** (vs. a governor populated by a live spawn). No live provider session runs in this non-interactive loop; the seeded governor exercises the identical `status()` → surface → IPC → source → fold path. Real production population is a 15E concern, recorded not faked.

## 6. Validator + auditor

- **gate-validator (sub-step): PASS.** All six criteria reproduced in isolation against real
  output (view model folds real counts; fail-closed unknown ≠ `0/2`; read-only surface with no
  authority; both LIVE tests RAN and read the real seeded governor `1/2`/`0/2`; frozen files
  hash-clean — CC414372 / 8C9B7240 / 668089B5 / 6D3FD03B + `node.schema.json` AB8EDD5D; suites
  489/114/35 at validation time). Every refutation probe (fabricated-count path, authority grant,
  silently-dropped subscription, skipped-but-claimed-live test, frozen-file edit) failed to find a
  violation. It judged the substitution **honestly scoped, not overclaimed** (the real shell's Echo
  gateway returns `ok:false` for `subscription_status` ⇒ fail-closed em-dash today; the governor
  feed wires at 15E; the seeded live test proves the read path). Two non-blocking reservations:
  **R1** its Bash denied `git`, so it substituted a stronger direct-SHA-256 frozen-file check + a
  full read of `subscription_governor.py` — **CLOSED in this report by native git**: `git diff
  --stat e6886b0 -- node_runtime/supervisor/subscription_governor.py` is EMPTY (governor
  byte-unchanged since `.governor`), and `git status docs/canonical/ schemas/` is empty.
  **R2** D-P14-1: the new Electron-main JS (`statusbar:fetch` handler + `statusClient`, preload
  `statusBar()`, renderer painting) is not loaded by `node --test` and is correctly deferred to the
  operator Electron run owned by `.gate` (the substitution pattern for this sub-step).
- **spec-auditor: CLEAN** (no invariant violations, no prohibited drift). Load-bearing invariants
  all PASS: inv 7 / I-M2 (read-only surface, no authority); inv 21 / I-X3 (own governed allowance
  shown; cap never widened by the sandboxed renderer); §2.2 (zero credential handling); Buildout §4
  (deterministic, fail-closed, integer counts); §6/§10.4 (no live-production overclaim — real shell
  degrades honestly); inv 27 (unsurfaced provider still shown). **Findings addressed pre-commit:**
  - **M1** (`SUBSCRIPTION_CAP` a hand-copied governor-cap literal) + **M2** (`LIVE_PROVIDERS`
    re-hardcodes the OP-6 set) — the drift risk is now **structurally closed** by a new
    cross-language pin test `tests/unit/test_statusbar_constants_pinned.py` that parses the JS
    literals and asserts `SUBSCRIPTION_CAP == subscription_governor.MAX_ALLOWANCE` and
    `LIVE_PROVIDERS == live_authorization._AUTHORIZED_PROVIDERS`; a future cap raise / provider
    change fails this test until the JS mirror is updated. Comments strengthened to name the
    authorities and the coupling.
  - **N1** (comment conflated "no subscription registered" with "registered, zero active") —
    reworded in the module docstring and the idle-row branch; the `subscriptionRef:null` marker
    preserving the distinction is documented.
  - **N2** (fixture/test minted the shell credential as role `operator`) — changed to role `shell`
    in `serve_seeded_governor.py` and `test_subscription_status_surface.py`, matching the product
    invariant-1 posture (the surface is role-agnostic, so this is fidelity, not a policy change).

## 7. Next

`.gate` — HIGH-STAKES phase gate, MANDATORY independent gate-validator, subscription-governor
deep re-inspection; closes `gate/phase-15a` once `.statusbar` (this unit) is the last sub-step
in. All 15A sub-steps: `.liveauth` ✓ · `.governor` ✓ · `.r8` ✓ · `.statusbar` ✓ · `.gate` ←.
