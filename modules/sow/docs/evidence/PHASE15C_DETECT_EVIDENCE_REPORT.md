# Phase 15C · sub-step `.detect` — Evidence Report

**Date:** 2026-07-19 · **Iteration:** 36 · **Status:** PASS (sub-step; NOT the phase gate)
**Work commit:** `357df95` (carried by this evidence/register commit — two-commit convention)
**Phase gate:** `gate/phase-15c` remains **UNTAGGED** — the high-stakes 15C gate closes at
`.gate` with the mandatory independent gate-validator (+ subscription-governor deep
re-inspection, now two live providers under allowance=2) once `.adapter`/`.gate` land.

## 1. Scope of this work unit

First sub-step of Phase 15C ("OpenAI adapter — Codex CLI", directive §11 track 15C; §12
OP-7 revised order 15A→**15C**; register **OP-6**). This unit satisfies the 15C **entry
condition** by verifying the operator's `codex` CLI on the host, and delivers the
detection surface the `.adapter` supervised spawn gate will act on:

- **presence / version / auth probe** — non-destructive, benign, local, credential-free;
- **model-id probe** — records the operator-named GPT-5.5 line ("5.5", "5.5 Sol") and the
  structural `-m/--model` selector support (directive §11 15C: *"probe accepted model IDs …
  record what the CLI really accepts, unavailable ⇒ recorded fallback surfaced in the roster,
  never silent"*).

**Explicitly `.detect` ONLY — NO live model call.** `codex exec <prompt>` is never invoked.
The only subprocesses spawned are the three benign metadata calls: `codex --version`,
`codex login status`, `codex exec --help`. The live `CodexCliBackend`, the fail-closed
supervised spawn path (mirroring `frontier_spawn.py`), the env-scrub SUPERSET applied to the
`codex exec` child, the `AGENTS.md`/`~/.codex` untrusted-config pin (T2, like OpenCode's U30),
and the one live smoke per available model are all **deferred to `.adapter`/`.gate`** — recorded
here, not started.

## 2. What changed (working tree; base HEAD `7520878`)

| File | Change |
|---|---|
| `adapters/frontier/codex.py` *(new)* | The Codex detection/probe surface. `CODEX_ADAPTER = "openai_codex_cli"` (== frozen `node.schema.json` `adapter` enum value == a `live_authorization._AUTHORIZED_PROVIDERS` member, so the live gate keys on it exactly). `parse_codex_version` (fail-closed on garbage). `CandidateModelRef` + `CODEX_CANDIDATE_MODEL_REFS` = the operator-named `5.5` / `5.5 Sol`, both `verified=False` (no offline enumeration; accepted id resolved by a live `codex exec` smoke at `.adapter`). `CodexProbe` (present/version/meets_minimum/authenticated/auth_detail/noninteractive_exec_supported/model_flag_supported/candidate_models/detail; `as_dict`). `CodexCli` (real: spawns `codex --version`, `codex login status`, `codex exec --help` only) + `MockCodexCli` (deterministic; spawns nothing). `probe_codex(cli=None)` — **never raises**; every failure captured as fail-closed data. **§2.2:** never reads the OAuth token / `~/.codex/auth.json`, never uses `--with-api-key`/`--with-access-token`. |
| `adapters/detect.py` | Added `codex_available()` (PATH detection only, symmetry with `claude_code_available()`; detection never authenticates, §2.2). No other change. |
| `tests/unit/test_codex_detect.py` *(new)* | 14 deterministic tests: provider-id == frozen enum + in live-auth scope; version parse fail-closed; candidate models operator-named & unverified; probe present/authed/meets-min; below-minimum; unparseable; unauthenticated fail-closed; real `login_status` classifier (authed on ChatGPT / not-authed on "Not logged in"); **normalized auth_detail never echoes raw PII/email** (spec-audit MINOR-1 regression); absent CLI ⇒ data not exception; version timeout ⇒ fail closed; **probe never builds a credential-carrying command** (only the three benign metadata argvs; no `--with-api-key`/`--with-access-token`/`codex exec <prompt>`). |
| `tests/integration/test_codex_detect_live.py` *(new)* | 3 LIVE tests (real `codex` spawn; SKIP-WITH-RECORD with the exact operator remediation if absent): version meets the gate; structural non-interactive-exec + `-m/--model` support; auth state reported honestly (state line, never a token; candidates surfaced unverified). |

## 3. Exit-criterion self-check (real command output)

**A. Entry condition — codex present + authenticated (OP-7 item 1 / OP-8).** Live probe on this
host: `codex.CMD` at `C:\Users\Sslaw\AppData\Roaming\npm\codex.CMD`; `codex --version` →
`codex-cli 0.144.6`; `codex login status` → `Logged in using ChatGPT` (rc 0). So the 3 live
tests RUN (not skipped) and pass.

**B. Presence / version gate.** `probe.present is True`, `version_tuple == (0,144,6)`,
`meets_minimum is True` (≥ `MIN_CODEX_VERSION` = `(0,1,0)`). Unparseable/below-min are proven
fail-closed by the mock branches.

**C. Auth probe, fail-closed.** `authenticated is True` live ("Logged in using ChatGPT"); the
classifier fails closed on `Not logged in` / empty / non-zero rc (never assumes auth on silence).

**D. Model-id probe honesty (§6/§10.4).** `-m/--model` structural support confirmed from
`codex exec --help` (`model_flag_supported is True`); the operator-named `5.5` / `5.5 Sol` are
recorded as `CandidateModelRef(..., verified=False)` — the Codex CLI has **no offline model-list
command**, so the accepted slug is a live-smoke fact for `.adapter`; nothing is fabricated as a
confirmed CLI id, and the candidates are surfaced even when the CLI is absent (never silent).

**E. §2.2 — no credential handling.** The probe reads auth *state*, never the token; it never
touches `~/.codex/auth.json` and never uses `--with-api-key`/`--with-access-token`. Proven by
`test_probe_never_builds_a_credential_carrying_command` (only the three benign metadata argvs).

**F. Fail-closed (Buildout §4).** `probe_codex` never raises — absent CLI, timeout, unparseable
version, and unauthenticated status all resolve to captured negative data.

**G. `.detect` authorizes/widens NOTHING.** No change to `live_authorization.py`,
`subscription_governor.py`, or any config; no live call. Detection only.

**Suites:**
- `py -3.12 -m pytest tests/unit/test_codex_detect.py tests/integration/test_codex_detect_live.py -v`
  → **17 passed** (14 unit + 3 LIVE, 0 skipped).
- `py -3.12 -m pytest tests/ -q` → **508 passed / 0 skipped** (was 491 at `gate/phase-15a`; +17).
- JS untouched this unit (no Electron-main change; D-P14-1 not engaged).

## 4. Invariants & prohibitions

- **§2.2 (credentials):** zero credential handling. State-only auth read; token never read/stored/transmitted; no credential-input flag.
- **Buildout §4 / fail-closed:** deterministic probe; every failure mode is captured data, never an exception or an assumed-authed default.
- **§6 / §10.4 honesty:** operator-named models recorded UNVERIFIED (no offline enumeration); no live model call made; no live capability claimed — the live smoke is owed to `.adapter`.
- **inv 1 (operator authority) / inv 21 / I-X3:** `.detect` detects only; it authorizes nothing and widens no scope. The two-provider live authorization + allowance-2 governor already landed at 15A (`.liveauth`/`.governor`); `openai_codex_cli` is already an authorized provider — no new config write here.
- **Frozen schemas:** `CODEX_ADAPTER == "openai_codex_cli"` matches the frozen `node.schema.json` `adapter` enum and `live_authorization._AUTHORIZED_PROVIDERS`; no frozen artifact modified.

## 5. Substitutions (directive §6) recorded

1. **No offline model enumeration.** The Codex CLI exposes no `models list`; `-m/--model` accepts a slug validated only at `codex exec` time. The operator-named GPT-5.5 ids are therefore recorded as UNVERIFIED candidates; the accepted-id resolution (and any fallback) is a live `codex exec -m <slug>` smoke at `.adapter`/`.gate` — recorded, not faked.
2. **Env-scrub superset + `~/.codex`/`AGENTS.md` untrusted-config pin (T2) deferred to `.adapter`.** `.detect` runs only benign metadata probes; the credential/endpoint scrub applied to the actual `codex exec` child and the node-controlled-config scoping belong to the live-drive sub-step.

## 6. Validator + auditor

- **gate-validator (sub-step): PASS.** All four criteria re-executed in isolation against real
  output. It re-ran the live probe itself (`present:true`, `codex-cli 0.144.6`, `authenticated:
  true`, `detail:"ok"`) and confirmed the 3 live tests RAN (not skipped) — independently proving
  `codex` is installed + authenticated on this host. Every refutation attempt failed: (a) no
  `codex exec <prompt>` / credential flag anywhere — `exec_help()` runs `exec --help` only, the
  argv set is pinned to `{("--version",),("login","status"),("exec","--help")}`; (b) `authenticated`
  cannot be True on "not logged in"/empty (requires rc==0 AND positive marker AND no negative
  marker — silence ⇒ False); (c) the "5.5"/"5.5 Sol" slugs are `verified=False`, resolution
  deferred to a live smoke, never fabricated; (d) `.detect` authorizes/widens NOTHING —
  `live_authorization.py` is not in the diff (`openai_codex_cli` was authorized at 15A under OP-6),
  the only production change is a pure PATH-check `codex_available()`. Native git: `docs/canonical/`
  and `schemas/` porcelain empty; provider id `openai_codex_cli` genuinely in the frozen
  `node.schema.json` enum. Predecessor `gate/phase-15a` CLOSED (7520878) before 15C started — no
  out-of-order start. Suite confirmed **507 passed / 0 skipped** at validation time.
  Two owed-item notes (not defects): the live adapter / `codex exec` / env-scrub superset /
  `AGENTS.md`+`~/.codex` config pin / worktree isolation / model-id resolution smoke are OWED to
  `.adapter`/`.gate` (stated honestly in the code); and the finite `login_status` string classifier
  degrades **fail-closed** if OpenAI changes the CLI wording (the safe direction) — recorded for
  `.adapter`. *(The validator ran at the 507/16 state, i.e. before the spec-audit MINOR-1
  normalization below; that change only rewrites `auth_detail` from the raw line to the classified
  `"logged in (chatgpt)"` — the authed logic, fail-closed direction, and argv set are unchanged, so
  every load-bearing PASS claim still holds; final suite is 508/17.)*
- **spec-auditor: CLEAN** (no invariant violations, no prohibited drift). Load-bearing checks all
  PASS: §2.2 (only `--version`/`login status`/`exec --help` spawned; no `~/.codex/auth.json` read,
  no `--with-api-key`/`--with-access-token`, no token in `auth_detail`; the credential-argv guard
  is a real test, not a comment); Buildout §4 fail-closed (`probe_codex` never raises; absent /
  unparseable / timeout / unauthenticated all captured; auth requires positive marker AND rc==0 AND
  no negative marker, so silence fails closed); §6/§10.4 honesty (GPT-5.5 recorded `verified=False`,
  no fabricated slug, structural flags derived from `exec --help` not a model call); inv 1/21/I-X3
  (no authorization, no spawn, no governor acquisition, no scope widening — detection only); frozen
  schema pin (`CODEX_ADAPTER == "openai_codex_cli"` == `node.schema.json` enum ==
  `_AUTHORIZED_PROVIDERS`). **MINOR-1 FIXED pre-commit + regression-pinned:** `login_status` recorded
  the raw 200-char CLI line, which some `codex` builds print with the account email (PII, not a
  credential, but evidence-bound); it now records a **classified state + matched auth method**
  (`"logged in (chatgpt)"` / `"not logged in"` / `"unauthenticated (login status rc=N)"`) and never
  echoes the raw line — new `test_login_status_detail_is_normalized_not_raw_pii` asserts an injected
  email is dropped while the method survives. **MINOR-2 ACCEPTED/deferred:** the hard-coded operator
  candidate refs are honest for `.detect` (clearly `verified=False`); `.adapter`/`.gate` will resolve
  them into a roster/capability descriptor rather than a bare list.

## 7. Next

`.adapter` — build the live `openai_codex_cli` adapter behind the same governed
`ModelWorkerAdapter` contract as `claude_code` (mock-first, then one live smoke per available
model), spawned ONLY through the fail-closed supervised path (mirror `frontier_spawn.py`:
`assert_startup` + `assert_provider_live('openai_codex_cli')` at the spawn site + [OPERATOR]
live-terms + CLI-presence + I-X3 governor at `allowance=live_auth.terminals_per_subscription`),
env-scrub SUPERSET, `~/.codex`/`AGENTS.md` untrusted-config pin (T2), worktree isolation for the
coding role. Then `.gate` — HIGH-STAKES, MANDATORY gate-validator + subscription-governor deep
re-inspection — closes `gate/phase-15c`. 15C sub-steps: `.detect` ✓ · `.adapter` ← · `.gate`.
