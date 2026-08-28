# Round 2 Evidence Packet

## Delta
- P0/P1 IDs: P0-16, P0-17, P0-18
- Commit: 9a890e8
- Files changed: app.py, static/index.html, tests/test_v1_2_1_input_boundaries.py (new)
- Functions changed: new INPUT_LIMITS table; new _validate_seats(); load_config seats block replaced; turn_word relation check added; api_interject / api_seat_thesis / api_seat_model bounds enforced; ws snapshot carries input_limits; index.html maxlength attrs + snapshot-driven maxLength sync + thesis drawer bound

## Root Cause
No single limits source and no schema stage: load_config repaired malformed seat structure (truncate/skip/invent), numeric keys had no relational invariant, runtime endpoints accepted unbounded operator text.

## Implementation
Reject-with-diagnostic everywhere structural: path-specific ConfigurationError messages (config.seats[i].field), 400 JSON errors at API layer. Per-key range coercion intentionally retained (documented product fallback); relations checked post-coercion so contradictions cannot silently produce inverted prompt ranges. Frontend derives bounds from the same envelope via static maxlength + snapshot input_limits sync (G-03 compliant: no styling change).

## Tests Added or Modified
14 tests: duplicate identities (exact + normalized), cardinality 1/5 with received-count assertions, parametrized seat-field schema (empty model/name, oversized name/persona/thesis, two invalid colors), contradictory min>max naming both keys, oversized interjection 400 + multiline & single-char accepted, oversized revision reason / oversized+blank model 400, frontend reflection of backend limits.
All red before implementation; green after.

Mid-round defect caught by Tier A: INPUT_LIMITS referenced before definition (NameError on module exec) - fixed by relocating constants table above first use.

Also caught and fixed during Round 1 close-out (recorded D-06): PowerShell ANSI decoding corrupted non-ASCII source bytes; all edits now binary-safe Python; app.py non_ascii byte count verified unchanged (32) after every patch this round.

## Verification
- narrow: 17/17 across both v1.2.1 test files
- component suite: full run
- hostile probe: lifecycle re-run PASS (http 200 @1.059s, ws snapshot incl. input_limits, clean shutdown, zero orphans); JS inline script syntax-checked via node Function constructor
- full suite: 101 passed / 0 failed in 24.21s (84 original preserved)

## Performance Impact
- measured: boot 1.059s (baseline 1.077s, R1 1.073s - within noise); suite 24.21s vs 15.78s baseline (14 new tests account for the delta)
- expected: regex color check + dict lookups per seat: negligible
- unknown: none

## Security Impact
- improvement: unbounded interjection/thesis/reason/model inputs now capped before reaching prompts or state; duplicate/invalid seat identities rejected instead of silently merged/truncated/invented
- new attack surface: none (validation only)
- residual risk: per-key range coercion still silent for individual numerics (documented behavior; revisit only if Director overrides README contract)

## Residual Risk
Frontend maxlength relies on JS sync for thesis drawer before first snapshot arrives (static default 8000 matches backend).

## Open P0
13 remaining: P0-04..P0-09, P0-10..P0-15, P0-19, P0-20

## Scope Control
Same FastAPI single-process app; validation-only delta; UI touched solely through behavioral maxlength attributes and one JS bound-sync block.

## Completion Effect
Phase 1 input-boundary cluster complete: configuration structure, payload sizes, and numeric relations are all enforced at one boundary with regression locks; remaining Phase 1 items are P0-04 (canonical resolver) and P0-05 (loopback policy).
