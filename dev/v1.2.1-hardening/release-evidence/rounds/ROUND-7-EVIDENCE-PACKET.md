# Round 7 Evidence Packet - ALL P0s CLOSED

## Delta
- P0/P1 IDs: P0-06, P0-07, P0-08, P0-09
- Commit: b5783b6
- Files changed: debate/output_guard.py (rewritten), app.py (PublicStreamFilter + clean), tests/test_v1_2_1_output_guard.py (new)
- Functions changed: OutputGuard (protected-literal registry w/ MIN_DYNAMIC_LENGTH=12 gate, multiline segmentation, anywhere-containment matching, chunk-safe _ends_inside_dynamic); PublicStreamFilter (tolerant regex tag machine incl attribute/space variants + stray-closer stripping + bounded hold window); clean() tolerant regexes; shared patterns exported from output_guard

## Root Cause
Dynamic blocking was line-PREFIX only with no minimum length ("I" suppressed "I think..."), multiline values effectively unprotected beyond first line, and the reasoning sanitizer matched only three exact literal tags so "<think >", attributes and stray closers leaked.

## Implementation
Values >=12 chars (per segment) become protected literals matched ANYWHERE in a line case-insensitively; shorter segments deliberately unregistered (documented residual). Streaming filter uses compiled tolerant open/close patterns with a 48-char hold window for partial tags; stray closers dropped inline; static clean() mirrors the same grammar.

## Tests Added or Modified
8 tests: short-word non-blocking x3; mid-line long-value block; case/whitespace normalization; multiline later-line block + sub-threshold non-registration; streaming variant tags hidden; stray closer removed; cross-chunk split variants; static clean variants. All red-first where behavior was absent.

## Verification
narrow 8/8; FULL SUITE 143 passed / 0 failed in 29.29s; lifecycle PASS @1.091s; diff --check clean.

## Security Impact
improvement: verbatim long operator-control echoes blocked regardless of position/case/padding; reasoning-channel leakage closed across malformed tag forms.
residual (contract-mandated honesty): paraphrase/semantic leakage remains possible; guard is best-effort anti-echo, NOT confidentiality (documented here + Phase 12 README).

## Open P0
0 remaining. P0 register complete: P0-02..P0-20 all implemented + regression-locked.

## Scope Control
Guard internals + one filter class; prompt builders, routes, UI untouched.

## Completion Effect
Phase 5 exit satisfied; every P0 from the frozen contract now has implementation + regression evidence. Remaining work is P1 hardening (Phase 6-8), verification gates, and release distillation.