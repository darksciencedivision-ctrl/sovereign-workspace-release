# ROUND-1-PLAN

## Problem

1. (P0-02) A malformed config.json is silently replaced by defaults AND the normalized defaults are written back over the operator's file, destroying original bytes (app.py:88-94 + 169-170). Violates G-05 and AC-01.
2. (P0-03) Three components interpret the same file differently: runtime load_config strict utf-8 (BOM-intolerant), bootstrap ps1/sh model-checker utf-8-sig, sh port probe strict utf-8 with silent fallback.

## Root cause

load_config treats "cannot parse" identically to "key absent" (document = {}), conflating corruption with emptiness; no typed parse boundary exists. Encoding choice utf-8 vs utf-8-sig diverges between components because there is no shared parse function.

## Change surface

- app.py: add `import sys`; add ConfigurationError; add _read_config_text() (utf-8-sig, single interpretation) and _parse_config_document(); rewrite load_config to fail closed via ConfigurationError on parse failure / non-object root / non-FileNotFoundError OSError; keep per-key normalization + normalization-write ONLY for successfully parsed docs; wrap module-level CONFIG = load_config(CONFIG_PATH) to emit one-line FATAL diagnostic to stderr and SystemExit(2).
- app.py:602,618: persistence helpers switch their inline read/parse to the same _read/_parse pair (ConfigurationError propagates instead of raw JSONDecodeError).
- scripts/bootstrap.sh line 207: encoding utf-8 -> utf-8-sig (align with sibling checker).

## Non-change surface

Seats truncation/invention logic; _valid_number coercion; OLLAMA env resolution; uvicorn startup; output guard; stream protocol; all tests/ existing files; bootstrap.ps1 (already utf-8-sig).

## Implementation method

Parse boundary raises ConfigurationError(path-contextual message incl. line/col from JSONDecodeError). load_config never substitutes {} on parse failure, therefore never reaches the atomic_write_json(defaults-over-file) branch for corrupt input - preservation is structural, not a guarded copy. Module import fails fast with exit code 2.

## Tests first (tests/test_v1_2_1_config_integrity.py, new file)

T1 test_malformed_config_is_preserved_and_rejected - exact invalid bytes recorded; load_config raises ConfigurationError naming the path; bytes unchanged after the call.
T2 test_bom_config_parses_consistently - valid doc written as utf-8 and utf-8-sig; both parse equal; BOM file also survives a seat-thesis persist-helper round trip.
T3 test_invalid_config_does_not_write_defaults - malformed file; load_config raises; file bytes AND mtime unchanged; no *.tmp siblings; exec_module with CONFIG_PATH=malformed raises SystemExit code 2 and leaves file untouched.

## Failure modes / regression risk

- Hidden reliance on lenient whole-file behavior somewhere untested (mitigated: full suite Tier E).
- ConfigurationError name collision after repeated importlib exec_module (unique module names per existing convention).
- Windows mtime granularity in T3 (compare content hash + size, mtime secondary).

## Rollback

Single commit revert; change touches only app.py (3 regions), bootstrap.sh (1 byte-span), plus new test file.

## Acceptance (binary)

- T1..T3 green.
- Full accumulated suite: 84 original + 3 new = 87 passed, 0 failed.
- git diff --check clean.

This delta moves the Distillery Module closer to completion by closing P0-02 and P0-03 and adding regression tests test_malformed_config_is_preserved_and_rejected, test_bom_config_parses_consistently, test_invalid_config_does_not_write_defaults.
