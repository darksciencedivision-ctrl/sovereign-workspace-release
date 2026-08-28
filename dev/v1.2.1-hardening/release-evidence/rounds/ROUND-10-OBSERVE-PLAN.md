# ROUND-10 OBSERVE+PLAN (Phase 7 - control-heuristic corrections)

HEAD: 8227a30 | Cluster: S17 heuristics (baseline D1/D2 closures + AC-03 #22/#23)

## Observations
1. detect_directed_questions treats ANY clause containing target+(? OR interrogative word) as directed -> "Clue explained why X fails." false-positives via bare "why".
2. disagreement_present uses raw substring: 'but' matches attribute/distributed/contributed (6/59 corpus turns substring-only per baseline D1); singletons saturate windows so consensus-breaker fired 0/53 in acceptance corpus.
3. Baseline counterfactual: removing but+however alone recovers only 9.4% - 'challenge' (52.5%) dominates => narrowing to explicit-disagreement markers is the evidence-backed fix, not just boundary regexes.
4. min_turn_chars: defaulted+validated but NEVER read since v1.1 (13 refs, D2). Wiring it enforcingly at default=120 would flip many original-suite fixture turns (<120 chars) into skips -> collides with AC-02 preservation. Sanctioned alternative S17.4(2): remove the dead knob.
5. Existing v1_logic tests pin exactly the behaviors we keep: vocative-question detection, name-only rejection, consensus weight 9.0 path - both survive planned changes unchanged.

## Plan
### Change surface
app.py: DISAGREEMENT_MARKERS narrowed to explicit phrases {disagree, counterpoint, what evidence, i reject, not convinced, on the contrary, fails because}; _MARKER_RES word-boundary phrase patterns; disagreement_present uses them. detect_directed_questions requires (? AND target AND (second-person pronoun OR leading vocative "Name,")); INTERROGATIVE_WORDS retained for any other consumers. min_turn_chars REMOVED from DEFAULTS/numeric_rules/config.json (+README line in Phase 12 pass); unknown keys already tolerated by loader.
### Non-change surface
pick_move weights/alternator, move vocabulary, prompt builders, guard, UI.
### Tests first (tests/test_v1_2_1_heuristics.py)
T1 directed: "Clue, why does your mechanism survive that failure?" -> {Clue}; T2 narrative-why -> set(); T3 name+question w/o you/vocative -> set(); T4 boundary: "Butter improves texture." False; standalone "But the data shows otherwise." True; "I disagree entirely." True; T5 consensus breaker fires on neutral window (weight x3) and stays off with explicit disagreement (mirrors v1_logic style); T6 dead-knob removal: key absent from DEFAULTS+config.json while loader tolerates its presence.

## Acceptance
T1-T6 + untouched v1_logic/v1_1 suites green; full suite green; lifecycle PASS.
This delta advances Phase 7 by closing directed-question false positives, disagreement boundary saturation (baseline D1 mechanism), consensus-breaker honesty, and eliminating the inert min_turn_chars knob (D2) with regression locks.