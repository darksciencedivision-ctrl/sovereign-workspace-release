# ROUND-2-PLAN

## Problem
Operator-supplied structural configuration and runtime payloads lack schema/bounds: seats can be duplicated/truncated/invented, numeric keys can contradict each other, and interjection/thesis/reason/model inputs are unbounded or absent-limited; frontend reflects none of the backend limits.

## Root cause
No single source of truth for input limits; load_config "repairs" malformed structure instead of rejecting it; no relational invariant stage after numeric coercion.

## Change surface
- app.py: add INPUT_LIMITS dict; redefine PUBLIC_TITLE_MAX_CHARS/DEBATE_BRIEF_MAX_CHARS from it; add _validate_seats() (cardinality 2..4, unique casefolded names, name<=100 non-empty, model non-empty <=200, persona<=4000, thesis<=8000, color ^#[0-9a-fA-F]{6}$, path-specific ConfigurationError messages); call from load_config replacing truncation/invention block; add relation check turn_word_min<=turn_word_max (post-coercion) with explicit error; enforce INPUT_LIMITS on api_interject(4000), api_seat_thesis thesis(8000)/reason(2000), api_seat_model model<=200 non-empty; extend ws snapshot with new limit fields for frontend.
- static/index.html: maxlength on in-topic/in-title(300)/in-brief(20000)/in-interject(4000); apply stored maxChars on snapshot; thesis drawer textarea maxLength=8000.
- tests/test_v1_2_1_input_boundaries.py (new).

## Non-change surface
Stream protocol, output guard, move logic, hub, persistence helpers' semantics, bootstrap scripts, visual styling.

## Implementation method
Validation-only delta: reject with typed ConfigurationError carrying `config.<path>` context; API rejections remain 400 JSON errors (consistent with existing endpoints). No silent repair remains for structural defects; per-key range coercion stays as documented fallback.

## Tests first
T1 duplicate seat identities rejected (exact + whitespace/case variants)
T2 invalid cardinality rejected (1 seat, 5 seats)
T3 invalid seat fields rejected (empty model / oversized name / bad color / oversized persona+thesis) parametrized with field-path assertions
T4 contradictory numerics rejected (min>max), message names both keys
T5 oversized interjection -> 400; multiline + 1-char interjection ACCEPTED by bounds layer (AC-03 floor items routed through same endpoint contract)
T6 oversized revision reason -> 400; oversized seat-model string -> 400
T7 frontend reflection: index.html contains maxlength attrs matching INPUT_LIMITS values (parse html)

## Failure modes
Hidden fixture reliance on lenient seats (mitigated by full suite); frontend maxlength blocking legitimate paste flows (maxlength matches documented envelope; acceptable).

## Rollback
Revert single commit.

## Acceptance
T1..T7 green; full suite green (87 + new = expected 95+); git diff --check clean.

This delta moves the Distillery Module closer to completion by closing P0-16, P0-17 and P0-18 and adding regression tests for duplicate seats, seat cardinality, seat field schema, contradictory numerics, oversized interjection/thesis/reason, and frontend bound reflection.
