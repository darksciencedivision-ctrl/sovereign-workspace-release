# ROUND-6 OBSERVE+PLAN (Phase 4)

HEAD: 1647267 | Open P0: 7 | Cluster: P0-15, P0-19, P0-20 + G-09 attribution

## Observations
- orchestrator advances state.turn/speaker_idx unconditionally after run_turn returns; all three skip paths return early -> failed/empty/interrupted turns still advance rotation+anchor counters and speaker order (P0-15).
- Empty public output emits turn_skipped(empty_public_response) yet still counts as an advanced turn (P0-19).
- run_turn returns None - no outcome channel.
- set_topic->reset_debate_state clears questions/reframe/repetition/recent BUT NOT state.interject -> stale interjection crosses topics (P0-20).
- Repetition remediation is GLOBAL: observe_public_turn sets state.repetition_pending (float) from Neo-vs-Neo overlap; pick_move consumes it for WHOEVER IS NEXT (Clue inherits Neo remediation) violating G-09.
- Anchor cadence: state.turn % ANCHOR_EVERY_TURNS == 0 post-increment (attempt-based).

## Plan
### Change surface
1. debate/turn_completion.py: add TurnOutcome str-Enum {COMPLETED, SKIPPED_GENERATION_ERROR, SKIPPED_EMPTY_PUBLIC, INTERRUPTED, PROTOCOL_INCOMPLETE, PROTOCOL_ERROR} (+export through app namespace).
2. run_turn: return TurnOutcome on every exit (skips; completed at end). Interrupted still raises (orchestrator maps to INTERRUPTED).
3. State: add attempted_turns/completed_public_turns/skipped_turns counters + completed_turns int for rotation/anchor cadence; reset in __init__ + reset_debate_state.
4. New _account_turn(module-level async) called by orchestrator: increments per outcome; rotation condition -> completed_turns >= TOPIC_ROTATE_TURNS; anchor trigger -> completed_turns % ANCHOR_EVERY_TURNS == 0 (documented policy change DECISIONS D-08); display state.turn semantics unchanged for UI continuity.
5. reset_debate_state: also self.interject = None (single hygiene point).
6. Repetition attribution: previous_public already keyed by speaker; change repetition_pending to dict[str,float]; pick_move(seat) pops its OWN entry only.
### Tests first (tests/test_v1_2_1_turn_accounting.py)
T1 outcome mapping for generation-error/empty/incomplete/protocol-error/completed via monkeypatched ollama_chat; T2 counters via _account_turn incl rotation threshold using completed counter; T3 anchor cadence on completed counter; T4 interject cleared by reset/set_topic; T5 G-09 cross-seat non-attribution + same-seat attribution; T6 interrupted propagates.

## Acceptance
T1-T6 green; full suite green; lifecycle PASS. Rollback: single revert.

This delta moves the Distillery Module closer to completion by closing P0-15, P0-19, P0-20 and enforcing G-09, adding regression tests for outcome accounting, completed-counter cadence, stale-interjection reset, and repetition attribution.