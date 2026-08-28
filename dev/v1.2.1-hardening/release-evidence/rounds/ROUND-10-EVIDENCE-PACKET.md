# Round 10 Evidence Packet

## Delta
- IDs: Phase 7 heuristics (AC-03 #22/#23; baseline D1 mechanism + D2 closure)
- Commit: (HEAD)
- Files changed: app.py, config.json, tests/test_v1_2_1_heuristics.py (new), tests/test_v1_logic.py (1 documented adaptation)
- Functions changed: DISAGREEMENT_MARKERS narrowed to 7 explicit phrases + _MARKER_RES word-boundary patterns; disagreement_present uses them; detect_directed_questions requires ?+target+(second-person OR vocative); min_turn_chars removed from DEFAULTS/numeric_rules/config.json

## Root Cause
Substring markers over a 4-turn window saturated on register-noise singletons (but/however/challenge: 83/41/52% hit rates; breaker fired 0/53 in acceptance corpus). Directed-question rule matched narrative mentions via bare interrogatives. min_turn_chars had zero readers since v1.1.

## Implementation
Evidence-backed narrowing keeps genuine disagreement cues only; boundaries prevent attribute/distributed-style false hits while standalone But still matches as its own word where relevant to remaining phrases. Directed-question now demands an actual question aimed at the target. Dead knob retired per S17.4(2): wiring enforcingly at default 120 would flip numerous original-suite fixtures into skips, colliding with AC-02.

## Tests Added or Modified
6 new: vocative-question detection; narrative-why rejection; named-question w/o second-person rejection; boundary matrix incl However-now-non-marker; consensus ON(weight x3=9.0)/OFF with explicit phrase; dead-knob absence + loader tolerance.
Adaptation under AC-02 exception: v1_logic OFF-path fixture switched from "However, this fails." to "I disagree with that step." preserving breaker-off and weight assertions exactly (bare however encoded the disproved saturation behavior).

## Verification
full suite 162 passed / 0 failed in 44.66s; lifecycle PASS clean shutdown; diff clean.

## Performance Impact
measured: none beyond 7 compiled regexes vs substring scan (suite unchanged within noise).

## Security Impact
improvement: move-selection can no longer be trivially pinned by common words; diagnostics honest.
residual: marker list is lexical by design; paraphrased disagreement without cue words is out of scope (documented).

## Open P0
0. Remaining P1s: P1-logs only; then Phase 8 context/perf, gates, distillation.

## Scope Control
Heuristic tables + one detection function + one config key removal; no architecture change.

## Completion Effect
Phase 7 exit satisfied: S17.1-S17.4 all resolved with regression locks and honest decisions recorded.