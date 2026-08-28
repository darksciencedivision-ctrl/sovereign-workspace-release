# Round 3 Evidence Packet

## Delta
- P0/P1 IDs: P0-04, P0-05
- Commit: d3b60dd
- Files changed: debate/config_policy.py (new), scripts/effective_config.py (new), app.py, scripts/bootstrap.sh, scripts/bootstrap.ps1, tests/test_v1_2_1_config_policy.py (new)
- Functions changed: ConfigurationError/_read_config_text/_parse_config_document moved to policy module (app re-imports); new classify_ollama_endpoint/resolve_ollama_base/effective_summary; startup guard now covers endpoint resolution; DEFAULTS.allow_remote_ollama; ws snapshot diagnostics expose ollama_endpoint_class

## Root Cause
Effective configuration had three independent derivations (runtime constants, ps1 inline parser, sh inline parser + silent port fallback) and no component modeled the endpoint CLASS, so env overrides silently bypassed intent and remote endpoints were unguarded.

## Implementation
One canonical policy module consumed by runtime and by a new CLI helper that both bootstrap scripts call. Policy: loopback {127.0.0.1, localhost, ::1} default; non-loopback requires allow_remote_ollama=true; the env var is a source for the value, never a bypass; opt-in prints warnings and is exposed in snapshot diagnostics. sh silent "|| echo 8700" removed.

## Tests Added or Modified
8 tests: loopback acceptance x3 (incl bracketed IPv6); remote rejection without opt-in; explicit opt-in accepted (endpoint_class=remote); env override cannot bypass; bootstrap/runtime equivalence incl BOM config via real CLI subprocess; source assertions that both bootstraps use the resolver and the silent fallback is gone.
Tier A red state exposed a defect in this round's own first implementation: endpoint resolution sat outside the guarded block, so policy violations escaped as raw tracebacks (exit 1) instead of FATAL/exit 2. Fixed by folding resolution into the guarded startup sequence.

## Verification
- narrow: 8/8 policy tests
- full suite: 109 passed / 0 failed in 25.84s (84 original preserved)
- hostile probe: lifecycle re-run PASS (http 200 @1.064s, ws snapshot, clean shutdown)
- diff hygiene: git diff --check clean

## Performance Impact
- measured: boot 1.064s (noise-equal); suite delta from 9 new tests
- expected: one urlsplit per startup - negligible
- unknown: none

## Security Impact
- improvement: remote Ollama impossible without deliberate named opt-in; env cannot bypass; explicit operator warnings; single parse path removes divergence surface
- new attack surface: none identified
- residual risk: allow_remote_ollama lives in config.json like other keys; runtime seat-mutation writes preserve unknown keys, so the flag survives operator edits

## Residual Risk
bootstrap.sh remains unexecuted on a POSIX host (carried baseline limitation); equivalence proven at unit level.

## Open P0
12 remaining: P0-06..P0-15, P0-19, P0-20

## Scope Control
New files follow existing debate/ package + scripts/ conventions; no architecture change; bootstrap output semantics preserved.

## Completion Effect
Phase 1 exit gate satisfied: malformed JSON preserved, BOM consistent, canonical resolver live in all three consumers, loopback policy enforced, payload bounds + seat schema + numeric relations locked, full suite green.

## Evidence incident note
Round tool scripts for R1-R3 were misplaced under dev\\release-evidence (wrong relative base) and lost during cleanup consolidation. Product impact none (patches captured in git history). Process fix recorded as DECISIONS D-07.