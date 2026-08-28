# Round 1 Evidence Packet

## Delta
- P0/P1 IDs: P0-02, P0-03
- Commit: (this commit)
- Files changed: app.py, scripts/bootstrap.sh, tests/test_v1_2_1_config_integrity.py (new)
- Functions changed: load_config; new ConfigurationError/_read_config_text/_parse_config_document; module-level CONFIG init guarded; persist_seat_model/persist_seat_thesis parse via shared pair

## Root Cause
load_config conflated "cannot parse" with "no keys": any JSONDecodeError/non-dict/OSError set document={} and the pre-existing normalization-write then overwrote the operator file with defaults. Encoding policy diverged because each component parsed independently: runtime strict utf-8 vs bootstrap utf-8-sig vs sh port probe strict utf-8.

## Implementation
Typed parse boundary (_read_config_text utf-8-sig + _parse_config_document) raises ConfigurationError with path/line/col context. load_config now parses first and can never reach the defaults-write branch on corrupt input - preservation is structural, not a guarded copy. Module import emits two FATAL stderr lines and SystemExit(2). Persist helpers reuse the same boundary. bootstrap.sh port probe aligned to utf-8-sig.

## Tests Added or Modified
- test_malformed_config_is_preserved_and_rejected: corrupt bytes -> ConfigurationError naming path; digest unchanged.
- test_bom_config_parses_consistently: BOM and non-BOM docs parse equal; BOM config survives persist_seat_thesis round trip through a dedicated module instance.
- test_invalid_config_does_not_write_defaults: exec_module with corrupt config -> SystemExit(2); file bytes+mtime unchanged; no tmp leftovers.

## Verification
- narrow: 3/3 new tests green (red before fix - all three failed on baseline code)
- component suite: covered by full run
- hostile probe: python -c "import app" with CONFIG_PATH=corrupt -> exit 2, FATAL x2 on stderr, file preserved; normal boot lifecycle re-run PASS (http 200 1.073s, ws snapshot, clean shutdown, zero orphans)
- full suite: 87 passed / 0 failed in 15.39s (84 original preserved + 3 new)

## Performance Impact
- measured: boot 1.073s (unchanged vs baseline 1.077s); full suite 15.39s vs 15.78s baseline
- expected: none beyond one extra try/except frame
- unknown: none

## Security Impact
- improvement: corrupt-config no longer silently degrades to default security posture nor destroys evidence of tampering
- new attack surface: none (parse-only change)
- residual risk: per-key invalid values still silently coerce to defaults (documented product behavior; P0-17/P0-18 later rounds)

## Residual Risk
Missing-file config still boots leniently this round (pre-existing behavior, untouched); silent-fallback port probe fallback remains in bootstrap.sh pending P0-04 canonical resolver.

## Open P0
17 remaining: P0-04..P0-09, P0-10..P0-20 minus closed {P0-02,P0-03}

## Scope Control
No architecture change: same single-process FastAPI app; only the configuration parse boundary was typed and made strict; normalization semantics for valid configs unchanged.

## Completion Effect
Configuration integrity cluster core is closed: corruption is detected, diagnosed, preserved, and blocks unsafe startup; one documented encoding interpretation is shared by runtime and both bootstrap checkers.
