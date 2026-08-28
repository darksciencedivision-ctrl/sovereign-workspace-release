# Round 6 Evidence Packet

## Delta
- P0/P1 IDs: P0-15, P0-19, P0-20 (+G-09 enforcement)
- Commit: 83c1e04
- Files changed: debate/turn_completion.py (TurnOutcome enum), app.py, tests/test_v1_2_1_turn_accounting.py (new), tests/test_v1_logic.py (2 documented adaptations)
- Functions changed: State counters + per-seat repetition_pending dict; reset_debate_state clears interject + completed_turns; observe_public_turn keys remediation by speaker; pick_move pops own seat only; run_turn returns TurnOutcome on all paths; new _account_turn_outcome; orchestrator rotation/anchor use completed counter

## Root Cause
run_turn had no outcome channel and orchestrator advanced state.turn/speaker unconditionally - failures counted as debates turns. Empty-public emitted a skip event but still advanced counters (P0-19). Interjection queue survived topic resets. Repetition remediation was one global float consumed by whoever spoke next (G-09 violation).

## Implementation
Only COMPLETED advances completed_public_turns/completed_turns; rotation triggers on completed_turns >= TOPIC_ROTATE_TURNS; anchor on completed_turns % ANCHOR_EVERY_TURNS with zero-guard; microphone always rotates so a broken seat cannot stall the table (documented D-08). Display state.turn semantics unchanged for UI continuity.

## Tests Added or Modified
8 new tests: outcome mapping x4 (completed/gen-error/empty/protocol), accounting math, rotation+anchor follow completed counter, interjection cleared by topic reset, seat-attribution (Clue does not inherit Neo; Neo consumes exactly once), interrupted propagation.
Original-suite adaptations under AC-02 exception (behavior prohibited by G-09): test_v1_logic directed-question precedence fixture now keys pending remediation to the picked seat; alternation test re-keyed to same seat while preserving alternation/consumption/reason assertions exactly.

## Verification
narrow 9/9 incl v1_logic; full suite 135 passed / 0 failed in 29.78s; lifecycle PASS; diff clean. Self-caught: success-path return initially placed before turn_metrics send (dead metrics) - caught by original continuation test, fixed by moving return after metrics emission.

## Performance Impact
measured: none beyond enum comparisons; suite unchanged within noise.

## Security Impact
improvement: protocol/failure turns can no longer inflate completed-turn-based rotation to skip content; remediation cannot be weaponized cross-seat.
residual: none new.

## Open P0
4 remaining: P0-06, P0-07, P0-08, P0-09 (output-guard cluster, Phase 5)

## Scope Control
Accounting lives in existing orchestrator/state; no architecture change; UI untouched.

## Completion Effect
Phase 4 exit satisfied: typed outcomes, completed-only cadence, speaker advancement policy explicit, topic-epoch hygiene incl interjection, per-seat repetition attribution with regression locks.