# PHASE 14C SUB-STEP EVIDENCE — `.harness` (supervised OpenCode spawn + presence/version gate)
Autonomous loop iteration 24 · 2026-07-18Z · **sub-step, NOT the phase gate**
(`gate/phase-14c` closes later at sub-step `.gate`, after `.worktree`, mirroring the
14A/14B decomposition pattern. No gate tag for a sub-step.)

## Objective (directive §9 table 14C, §10.2; invariant 23; Plan §7-P6 / §12.2)
Prove **OpenCode itself** as a first-class, supervisor-spawned coding harness — closing the
Phase 6 gap (spec-audit F1: the `coding_node` was a *direct* single-shot Ollama coder that
advertised **no** `harness_class` because "OpenCode's programmatic drive is deferred (interactive
TUI)"). This `.harness` sub-step delivers the harness contract, a deterministic **presence/version
gate**, and the **supervised spawn path** (no naked session). The code-editing drive (scoped MCP
context → isolated worktree edit → tests → CANDIDATE → controlled merge) is the `.worktree`/`.gate`
sub-steps.

14C decomposition (directive §3.2): **`.harness` (this, iter 24)** → `.worktree` → `.gate`.

## Entry condition (directive §9 table 14C / §10.2) — MET
- **OpenCode binary present on host** ✓ — `opencode --version` → **`1.17.13`** (real subprocess,
  rc 0). Resolved executable `C:\Users\Sslaw\AppData\Roaming\npm\opencode.CMD`
  (sha256 `b53b698473bfa46e09487e485a7f1ad5b4881f8a8b319d3619aa251f3be8ae10`, 148-byte npm shim).
- **Local coder model present** ✓ — Ollama daemon up; `ollama list` includes `devstral-small-2:latest`
  (Mistral's coding model), `qwen3:14b`, `gpt-oss:20b`, `deepseek-r1:14b`. The harness probe
  selects `devstral-small-2:latest` as the coder model.
- **§10.2 download authorization UNUSED (honest record):** the OpenCode binary and the coder model
  were **already installed by the operator**; **NO download or install was performed this session**
  (verified: the new code performs no network fetch/install — `version()` only spawns
  `opencode --version`). §10.2's "verify download integrity, record source URL + hash" is therefore
  moot for a download that did not occur; the installed-binary hash + authoritative version above
  are recorded for provenance.

## What was produced
- **`adapters/coding/opencode/harness.py` (NEW)** — the OpenCode side of the coding-harness
  contract (invariant 23), split exactly like the frontier backend:
  - `CodingHarness` Protocol (`name`, `version()`) — harness-agnostic so the gate serves
    OpenCode now and Aider/Codex later.
  - `MockOpenCodeHarness` — deterministic, spawns nothing; reports a parseable, clearly-mock
    version (`0.99.0-mock`) so the mock-first proof exercises the SAME presence/version gate.
  - `OpenCodeCliHarness` — the REAL harness. `version()` spawns `opencode --version` (benign,
    local, credential-free). Its pure builders carry the two load-bearing safety properties:
    - **`build_env` — §2.2 (no credential handling):** scrubs every provider credential/API-key
      var from the child env (exact documented keys `OPENAI_/ANTHROPIC_/OPENROUTER_/GROQ_/GEMINI_/
      GOOGLE_/MISTRAL_/DEEPSEEK_/XAI_/AZURE_/AWS_/OPENCODE_` families **plus** a fail-closed
      prefix + `*TOKEN*/*SECRET*/*API_KEY*/*APIKEY*/*PASSWORD*` substring superset). Non-secret +
      local vars (PATH, HOME, locale, temp, `OLLAMA_HOST`) preserved so the CLI still runs.
    - **`build_run_command` — §2.3 (no paid services):** pins `opencode run -m ollama/<model>
      --format json <prompt>` — a LOCAL model; with cloud keys scrubbed, the local Ollama daemon
      is the only reachable backend. No `--api-key`, no `--share`.
  - `parse_semver` (fail-closed: garbage → `OpenCodeVersionError`), `HarnessProbe`,
    `OpenCodeUnavailable` / `OpenCodeVersionError`, `coding_capability_descriptors()` advertising
    `harness_class: "coding_tui"` — the descriptor Phase 6 F1 said would appear only once OpenCode
    is really driven.
- **`node_runtime/supervisor/opencode_spawn.py` (NEW)** — the real supervised spawn path
  (local analogue of `frontier_spawn.py`). `probe_opencode(...)` returns evidence (never raises);
  `spawn_opencode_harness(...)` applies THREE ordered fail-closed gates before issuing a
  supervisor-owned identity: (1) **presence** (`OpenCodeUnavailable`), (2) **version** parseable
  ∧ ≥ minimum (`OpenCodeVersionError`), (3) **supervised identity** — missing permission
  profile/node id ⇒ `NakedLaunchRefused` (invariant 2). Only then is
  `AdapterContext(spawned_by_supervisor=True, subscription_ref=None)` constructed.
  **Deliberately absent, recorded:** NO `LIVE_OPERATION_AUTHORIZED` gate (frontier-only, §10.1)
  and NO `SubscriptionGovernor` (local terminals are never subscription-bounded) — local, not a
  missing control.
- **`adapters/coding/opencode/__init__.py` (NEW)** — package docstring.
- **Tests (NEW):** `tests/unit/test_opencode_harness.py` (23, deterministic, no subprocess);
  `tests/integration/test_opencode_harness_live.py` (3, REAL `opencode --version` spawn).

## Self-check — every criterion vs real output
- **Presence gate fails closed (A):** ✓ absent-CLI harness → `probe.present=False`;
  `spawn_opencode_harness` raises `OpenCodeUnavailable`
  (`test_spawn_refuses_absent_cli`, `test_probe_reports_absent_when_cli_missing`).
- **Version gate deterministic + fail-closed (B):** ✓ `parse_semver("not-a-version")` raises;
  below-minimum (`0.0.1`) and unparseable (`dev-build`) versions set `meets_minimum=False` and
  `spawn_opencode_harness` refuses with `OpenCodeVersionError`
  (`test_parse_semver_raises_on_unparseable`, `test_probe_flags_below_minimum`,
  `test_probe_flags_unparseable_version`, `test_spawn_refuses_below_min_version`).
- **No naked session — invariant 2 (C):** ✓ empty `permission_profile_id` or empty `node_id` ⇒
  `NakedLaunchRefused`; a supervised spawn sets `spawned_by_supervisor=True`
  (`test_spawn_refuses_naked_no_permission_profile`, `test_spawn_refuses_naked_no_node_identity`,
  `test_spawn_issues_supervised_identity`, live `test_live_naked_launch_still_refused_even_when_present`).
- **§2.2 credential scrub (D):** ✓ `build_env` strips every documented provider key + a
  future `*_API_KEY`/`*TOKEN*` var; PATH/HOME/`OLLAMA_HOST` survive; no secret VALUE remains in
  the child env (`test_real_harness_env_scrubs_all_provider_credentials`).
- **§2.3 no paid path (E):** ✓ run command pins `ollama/<model>`, carries no api-key/share flag
  (`test_real_harness_run_command_pins_local_model_and_no_auth_flags`).
- **LIVE presence/version (F):** ✓ `test_opencode_harness_live.py` **actually spawns**
  `opencode --version` and admits a supervised harness with the real version — **3 passed, 0
  skipped** on this host (verbose run confirmed not a skip). Skip-with-record path is honest when
  the CLI is absent.
- **No install/download (G):** ✓ the new code has no network/install call; `version()` only
  spawns `opencode --version`.

## LIVE outcome this session (honest)
Unlike the frontier live smoke (skip-with-record, no credential), the OpenCode presence/version
probe is **local + credential-free and RAN LIVE**: a real `opencode --version` subprocess (1.17.13)
admitted through the real supervised gate. The heavy **drive** (opencode editing an isolated
worktree against `ollama/devstral-small-2`, running tests, submitting a CANDIDATE) is the
`.worktree` sub-step — deferred, not faked.

## Independent review (this iteration)
- **gate-validator (sub-step confirmation): PASS_WITH_RESERVATIONS.** Criteria A–G verified
  against real artifacts + real command output in an isolated context (all 3 live tests ran, not
  skipped; independent live probe returned `present=True, version='1.17.13', coder_model=
  'qwen2.5-coder:7b'`; full suite 420 green at review time). Confirmed the ABSENCE of the
  `LIVE_OPERATION_AUTHORIZED` gate + `SubscriptionGovernor` is CORRECT for a local path, not a
  missing control. Reservations — **ALL now addressed this iteration** (see below): R1 (bare
  `_KEY` scrub gap), R2 (model pin unenforced by the builder), R3 (version-floor override knob —
  accepted: non-default, exercised only via an explicit test-only `require_min_version=False`).
- **spec-auditor: 2 MAJOR + 3 MINOR — ALL FIXED this iteration, re-tested green (427 passed):**
  - **MAJOR-1 / R2** (§2.3 local-model pin was unenforced convention): FIXED —
    `build_run_command` (real + mock) now calls `_require_local_model`, raising `ModelNotLocal`
    on any non-`ollama/*` model; `local_model_ref()` bridges the bare probe name to the pin.
    New `test_run_command_refuses_non_local_model`, `test_local_model_ref_prefixes_bare_name`.
  - **MAJOR-2** (`OLLAMA_HOST` preserved unconditionally could route off-box to a paid endpoint):
    FIXED — `build_env` drops a non-loopback `OLLAMA_HOST` (loopback preserved). New
    `test_build_env_drops_non_loopback_ollama_host`.
  - **MINOR-1** (`subprocess.TimeoutExpired` uncaught ⇒ probe crashes instead of failing closed):
    FIXED — `version()` catches it → `OpenCodeUnavailable`. New `test_version_fails_closed_on_timeout`.
  - **MINOR-2 / R1** (scrub missed bare `<VENDOR>_KEY`): FIXED — substring net now includes
    `KEY`/`AUTH`/`CREDENTIAL` (closes, for THIS adapter, the bare-`_KEY` class recorded as U29 on
    the frontier adapter). New `test_credential_scrub_catches_bare_key_and_auth_suffixes`.
  - **MINOR-3** (spawn admitted a harness with `coder_model=None`): FIXED — `spawn_opencode_harness`
    now fail-closed refuses when no local coder model is detected (`require_coder_model=True`
    default; explicit override only for a mock drive). New `test_spawn_refuses_when_no_local_coder_model`,
    `test_spawn_allows_no_coder_model_only_with_explicit_override`.
  - spec-auditor confirmed CLEAN on the load-bearing invariants (inv 2 no naked session; inv 23
    one contract; §10.2 no download this session — only `shutil.which` + a `--version` probe; §4
    deterministic fail-closed gate logic).
- **Forward note (recorded, non-blocking):** OpenCode also reads provider config from its own
  config file (`opencode.json` / `OPENCODE_CONFIG`), not only env vars; the env scrub does not
  reach that, so the §2.3 guarantee ultimately rests on the enforced `ollama/*` model pin (now in
  code). `.worktree` should additionally pin/scope the OpenCode config (or `--pure`) as
  defence-in-depth — tracked **U30**.

## Test results (real command output, py -3.12 / node)
- `pytest tests/unit/test_opencode_harness.py tests/integration/test_opencode_harness_live.py -q`
  → **26 passed** (23 unit + 3 LIVE, 0 skipped).
- Full suite `pytest tests/ -q` → **427 passed, 36 warnings** (was 401 at 14B; +26 net new;
  pre-existing `jsonschema.RefResolver` deprecations only).
- JS suite `node --test` → **165 passed, 0 failed, 0 skipped** (no JS touched this iteration).

## Substitutions / deferrals (directive §6; honest record)
- **`MockOpenCodeHarness`** is the mock-first substitution for the deterministic suite; the REAL
  harness is exercised live for presence/version and will be driven in `.worktree`.
- **The code-editing drive is deferred to `.worktree`** — this sub-step gates presence/version +
  supervised identity only. Recorded, not overclaimed: no rendered/edited artifact is asserted yet.
- **§10.2 download unused** — binary + model already installed; no download performed (see Entry
  condition).

## Invariant touchpoints
- **Inv 2 (no naked session):** harness spawnable only with a supervisor-issued identity.
- **Inv 23 (coding harnesses interchangeable behind one contract):** `CodingHarness` protocol +
  `harness_class: coding_tui` descriptor; OpenCode is the first concrete driver.
- **§2.2 (no credential handling):** `build_env` scrubs every provider key; nothing read/stored.
- **§2.3 (no paid services):** local `ollama/*` pin + cloud-key scrub ⇒ no reachable paid backend.
- **§4 (deterministic fail-closed gate logic):** presence/version gate is pure Python, never model
  output; refuses on any missing precondition.

## Disposition
`phase-14c.harness` PASSED as a **sub-step** (not the phase gate). `gate/phase-14c` remains
**UNTAGGED** — awaits `.worktree` then `.gate`. Next: `phase-14c.worktree`.
