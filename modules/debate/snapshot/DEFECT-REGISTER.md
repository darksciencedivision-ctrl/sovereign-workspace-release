# Defect and Non-Goal Register — v1.2-phase1-baseline (`d03a1b7`)

A baseline that hides its known faults invites them to be rediscovered as
surprises. Each candidate below was **verified at `d03a1b7` in this session**, not
transcribed. Verdicts: **CONFIRMED**, **CONFIRMED WITH CORRECTION**, or
**NOT REPRODUCED**.

Nothing in this register was fixed. This is a snapshot, not a repair.

---

## D1 — Consensus-breaker never fires — **CONFIRMED (more severe than stated)**

**Claim under test:** `DISAGREEMENT_MARKERS` (`app.py:232-245`) contains `"however"`
and `"but"`; `disagreement_present()` (`app.py:304-306`) returns true if any marker
appears anywhere in the joined last-4-turn window, so common words make the window
almost always "disagreeing" and the consensus-breaker never fires.

**Mechanism, read from source (OBSERVATION):** `app.py:743-753` — the breaker
triggers only when `len(recent_turns) >= window and not disagreement_present(...)`.
When it fires it multiplies the `challenge` and `cross-examine` weights by
`consensus_challenge_weight` (3.0) and sets `move_reason` to
`consensus_breaker:no_disagreement_in_4_turns`. `state.recent_turns` is a deque of
`maxlen = consensus_window_turns = 4` holding `{"name", "text"}`
(`app.py:352-353`, `383`).

**Verification method:** replayed the 59 completed turns of the committed corpus
through the exact `disagreement_present()` logic and the exact
`DISAGREEMENT_MARKERS` tuple, reconstructing `recent_turns` as a rolling window of
4. A drift guard asserted every marker string is still present in `app.py` so a
stale copy would fail loudly.

**MEASUREMENT — per-marker hit rate across 59 completed turns:**

| Marker | Turns containing it | Rate |
|---|---:|---:|
| `but` | 49 | **83.1%** |
| `challenge` | 31 | **52.5%** |
| `however` | 24 | **40.7%** |
| `incorrect` | 2 | 3.4% |
| `what evidence` | 1 | 1.7% |
| `disagree` | 0 | 0.0% |
| `counterpoint` | 0 | 0.0% |
| `doubt` | 0 | 0.0% |
| `i reject` | 0 | 0.0% |
| `not convinced` | 0 | 0.0% |
| `on the contrary` | 0 | 0.0% |
| `fails because` | 0 | 0.0% |

**MEASUREMENT — windows of 4 consecutive completed turns: 53 total**

```
disagreement_present() -> True   : 53 / 53  (100.0%)
consensus-breaker would fire     :  0 / 53  (  0.0%)
```

**The consensus-breaker fired zero times in the entire acceptance corpus.**
Consistent with §5 of `snapshot/BEHAVIOURAL-BASELINE.md`, where no `move_reason`
of `consensus_breaker:*` could be attributed.

**MEASUREMENT — counterfactuals**, to locate the cause rather than assume it:

| Marker set | Breaker would fire |
|---|---:|
| As shipped | 0 / 53 (0.0%) |
| Without `but` | 0 / 53 (0.0%) |
| Without `however` | 0 / 53 (0.0%) |
| Without **both** `but` and `however` | 5 / 53 (**9.4%**) |

**Correction to the candidate as stated:** the candidate names `however` and `but`
as the cause. Removing *either one alone* changes nothing — the other still
saturates. Removing both still only recovers 9.4%, because `challenge` (52.5%)
then dominates. The problem is **broader than the two words named**: a
substring-match over a 4-turn window of ~750 words is saturated by ordinary debate
vocabulary, and `challenge` is a debate term of art that appears in the app's own
move vocabulary.

**Additional MEASUREMENT — matching is substring, not word-boundary.**
`disagreement_present()` uses `marker in joined`, so `but` matches inside
`attribute`, `distributed`, `contributed`. In **6 of 59 turns**, `but` matched
*only* as a substring and never as a standalone word. Those 6 turns register as
"disagreeing" on the strength of words like `distributed` — in a corpus whose
opening topic was distributed databases.

**Severity:** the feature is inert. `consensus_challenge_weight` (3.0) and
`consensus_window_turns` (4) are live, validated config keys that have no observed
effect. Not user-visible as a failure; the debate proceeds on the weighted
fallback path.

---

## D2 — `min_turn_chars` is a dead config key — **CONFIRMED**

**Verification method:** `git grep -n "min_turn_chars"` across the whole tracked
tree at `HEAD`. Every reference reported, as required.

**MEASUREMENT — all 13 references:**

| Location | Kind |
|---|---|
| `app.py:40` | default value `120` in `DEFAULTS` |
| `app.py:105` | range validation `(0, 10000, True)` |
| `config.json:24` | value `120` |
| `tests/live_qualify.py:95` | sets it to `0` in a generated test config |
| `spike/spike_b_design.py:254` | `120` in a generated spike config |
| `spike/spike_b_preregistration.json:69` | `120`, frozen pre-registration record |
| `spike/spike_b_run.py:52` | `MIN_TURN_CHARS = PREREG["min_turn_chars"]` |
| `CANONICAL-HANDOFF.md:86` | documentation |
| `DIRECTIVE-V1.1-CLAUDE-CODE.md:114, 460, 481` | prior directive, already flagged it |
| `archive/directives/superseded_v1_1/OPENCODE-DIRECTIVE-V1.1.md:135, 563, 583` | superseded directive |
| `audit/v1_1_final_status.md:37` | records wiring it as explicitly out of v1.1 scope |

**Verdict: CONFIRMED.** In `app.py` the key is defaulted and range-validated and
**never read again**. There is no consumer. The only place the value is *used* is
`spike/spike_b_run.py:52`, which is a spike harness reading its own frozen
pre-registration, not the engine.

**MEASUREMENT — `app.py:105` validates it over `(0, 10000)`, meaning `0` is a
legal value.** A key that is inert cannot be distinguished from one set to zero.

**Known and deliberately not fixed:** `DIRECTIVE-V1.1-CLAUDE-CODE.md:460` said
"Either wire it or remove it; do not leave it inert." `audit/v1_1_final_status.md:37`
records that v1.1 confirmed by direct grep that it was *not* wired, as an
in-scope-limitation decision. It has been inert across at least two directive
cycles.

---

## D3 — Structural repetition is undetected — **CONFIRMED**

**Claim under test:** seven similarity metrics have failed to separate "same
argument, different examples" from "different argument, same topic".

**Verification method:** read `audit/v1_2_spike_a_embeddings.md`,
`audit/v1_2_phase1_decision.md`, and the calibration record in
`debate/argument_memory.py:1-70`.

**MEASUREMENT — the "seven" reconciles across two separate efforts**, which is
worth stating because neither document alone lists seven.

*Four pre-registered in Spike A* (`v1_2_spike_a_embeddings.md:14-24`), scored on
holdout against an adoption bar of **recall ≥ 70%, FPR ≤ 10%**:

| Metric | Cal threshold | Holdout micro recall | Macro recall | FPR | Verdict |
|---|---|---|---|---|---|
| `metric_whole_turn_cosine` | 0.9150 | 0/9 (0%) | 0% | 1/12 (8.3%) | NO_USEFUL_SEPARATION |
| `metric_max_sentence_cosine` | 0.8915 | 0/9 (0%) | 0% | 1/12 (8.3%) | NO_USEFUL_SEPARATION |
| `metric_top2_nonoverlap_mean` | 0.8423 | 1/9 (11.1%) | 10% | 3/12 (25%) | NO_USEFUL_SEPARATION |
| `metric_incumbent_containment` | 0.4727 | 1/9 (11.1%) | 10% | 0/12 (0%) | NO_USEFUL_SEPARATION |

*Four more from the 2026-08-07 `argument_memory` rewrite probe*
(`argument_memory.py:20-30`), measured on a real recycled pair:

```
Jaccard 3-5gram (the original shipped metric)  0.047   unusable
Containment 3-5gram                            0.093   unusable
Containment 2gram                              0.227
Containment content-words                      0.535   usable -> adopted
```

The incumbent content-word containment metric appears in both lists, so the
distinct total is **7**. The candidate's count is correct.

**MEASUREMENT — root cause, from `v1_2_phase1_decision.md:29-37`:**
`same_topic_distinct` pair scores overlap almost the entire `structural_recycle`
range on every metric. A separate unregistered finding: `cross_topic_control`
pairs — genuinely unrelated topics — still average **0.599** whole-turn cosine,
indicating shared debate *register*, not topic or claim, substantially drives this
embedding model's similarity on this text style.

**Verdict: CONFIRMED.** Every metric misses the bar by roughly a factor of six on
recall. `v1_2_spike_a_embeddings.md:58` states this is not a marginal miss, and
the holdout's independent-group minimums were met, so this is a genuine
`NO_USEFUL_SEPARATION` rather than an invalid-holdout non-result.

**Note on what was found *behind* the original defect:** the first shipped
implementation was *mathematically incapable of firing* — recording a 130-word
turn and feeding the identical turn back scored **0.0000** against a threshold of
0.35 (`argument_memory.py:5-17`). Its unit test passed only because it used two
15-word sentences. That specific defect was fixed at v1.1; what remains confirmed
here is the broader detection problem.

---

## D4 — Models disregard the opening-move rule — **CONFIRMED**

**Claim under test:** the detector works; compliance does not follow.

**Detector location (OBSERVATION):** `debate/prompt_contract.py:88`
`opens_with_agreement()`; called at `app.py:1148-1150`, which writes
`one_attempt["agreement_opener"]`. Companion detector
`opens_with_stock_phrase()` at `prompt_contract.py:78`. Source comment at
`prompt_contract.py:35-36`: *"Detection is diagnostic only -- speech is never
rejected or rewritten on this basis."*

**Rule text (OBSERVATION), `contract_instructions()`:** *"OPENING REQUIREMENT:
Sentence 1 must directly state your own position... Do not address, name,
summarize, praise, validate, concede to, or characterize another seat in
sentence 1. Engagement with another seat begins in sentence 2."*

**MEASUREMENT — measured opener rate, all 59 completed turns through the real
detector:**

| | Run 1 | Run 2 | Combined |
|---|---:|---:|---:|
| Agreement openers | 11 / 35 (31.4%) | 6 / 24 (25.0%) | **17 / 59 = 28.8%** |
| Stock-phrase openings | 0 | 0 | **0** |

Phrases: `you've highlighted` ×5, `you've raised` ×4, `i appreciate` ×2, then
`you raise an important`, `you're correct`, `you're right`, `you rightly`,
`i agree`, `i see your point` ×1 each.

**Verdict: CONFIRMED, with a useful nuance.** Roughly **three turns in ten** open by
acknowledging the other seat despite an explicit, emphatic prohibition. But the
*named* stock phrases were used **zero** times — the models avoided exactly what
the prompt quoted and violated the rule in a form it did not enumerate.

**Corroboration:** v1.2 Spike B independently found **51 of 52** opening-rule
violations to be the identical opponent-name-in-sentence-1 pattern
(`v1_2_phase1_decision.md:99-103`), and separately found the rule *does* measurably
work — blinded stance-first YES rate roughly doubles when the rule is present
(18.75–37.5% without vs 75–87.5% with). So the rule helps substantially and is
still violated about 29% of the time. `v1_2_phase1_decision.md` classes this as
"an instruction-compliance problem, not a detection problem."

---

## D5 — Live-run harnesses are Windows-only — **CONFIRMED**

**Verification method:** read the named lines; searched both files for `os.name`,
`sys.platform` and `platform.system` guards.

**MEASUREMENT — `tests/live_soak.py:75`** (`process_memory`), **unguarded**:

```python
command = ["powershell", "-NoProfile", "-Command",
           f"(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64"]
```

**MEASUREMENT — `tests/live_soak.py:85-91`** (`ollama_processes`), **unguarded**:

```python
command = ["powershell", "-NoProfile", "-Command",
           "Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | "
           "Select-Object Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress"]
```

**Are the `powershell` calls guarded by an `os.name` check? No.** Neither call site
has one. `os.name` *is* checked in the same file, but for two unrelated concerns:

- `live_soak.py:103` — `subprocess.CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` flags
- `live_soak.py:119-121` — `signal.CTRL_BREAK_EVENT` on shutdown

**INFERENCE** (rests on those four line readings): whoever wrote this file was
aware of cross-platform process handling and guarded the process-creation and
signal paths, then invoked `powershell` unguarded twice. On a non-Windows host
these two calls raise `FileNotFoundError` rather than degrading — `process_memory`
catches only `ValueError`, and `ollama_processes` catches nothing.

**MEASUREMENT — `tests/live_qualify.py:22`:** `PYTHON = Path(r"C:\Python314\python.exe")`
— a hardcoded interpreter, used at `live_qualify.py:129` to spawn the app.

**Deliberately not fixed.** These are development harnesses, outside the §0.5
portability boundary (install deps, start app, run unit tests). See
`snapshot/PORTABILITY.md` findings P4 and P5 for the proposed minimal fixes, which
are proposals for the operator, not actions taken.

**Scope note (MEASUREMENT):** the *unit* test suite is unaffected.
`tests/test_smoke.py:94` and `:104` spawn subprocesses via `sys.executable`, not a
hardcoded path, and no `powershell` call exists anywhere outside `live_soak.py`.
This is why 84 tests can pass on a non-Windows host while the live harnesses cannot
run at all.

---

## Non-goals

Carried from `README.md:5` and the v1.1 / v1.2 ledgers. Debate Table is **not**:

- a truth-scoring system
- a claim ledger
- an autonomous tool agent
- an audience-chat service
- a voice app
- an avatar system
- an account platform
- a cloud service

To which the baseline adds, from measured scope decisions: it is not a
cross-platform application (`README.md:9` — "Windows"), and it makes no cloud model
API calls of any kind.

---

## v1.2 backlog — not started

Recorded so it is not mistaken for missing work in the snapshot. **None of this is
implemented at `d03a1b7`**, and none of it was implemented by this snapshot run.

| Item | Status at `d03a1b7` |
|---|---|
| Structural / semantic repetition detection | Phase 1 spikes complete; **NOT_JUSTIFIED** for a Phase 2 build — all 7 metrics returned `NO_USEFUL_SEPARATION` (D3) |
| Opener-rule compliance architecture | Open. Detector exists and works; compliance is ~71% (D4). Classified as instruction-compliance, not detection |
| Within-turn redundancy detection | Open, unaffected by either spike's outcome |
| Topic-scoped thesis generation | Open, unaffected by either spike's outcome |
| Debate modes | Open, not started |
| Six-phase agenda | Open, not started |
| Model health and fallback | Open, not started |
| Local voice (Kokoro → Piper) | Open, unaffected by either spike's outcome. No TTS code exists in this branch |

**Phase 1's own conclusion** (`audit/v1_2_phase1_decision.md:73-93`): a runtime
embedding implementation is not justified, and neither is a prompt redesign aimed
at constraint interference — Spike B returned `INCONCLUSIVE` on `OVERALL_H1`, with
the two seats moving in opposite directions on the opening-rule comparison.

---

## Open items carried forward, not defects

- **Raw first-public latency rose against the v1 baseline** and is unexplained.
  v1: min 0.545 / mean 1.565 / max 7.850 s. v1.1: min 0.618 / **mean 5.974** / max
  12.979 s, same model pair (`v1_1_text_acceptance.md:78`). The longer v1.1 prompt
  is a *hypothesis, not a measured cause* — no v1 `prompt_eval_count` baseline
  exists to compare against. It produced no dead air (0 gaps > 10 s in both runs)
  and no acceptance criterion depends on it.
- **`app_exit_code` / `restart_exit_code` are `1`** in both runs. Not a regression:
  the pre-existing v1 soak recorded the same `1` on the same Windows
  `CTRL_BREAK_EVENT` shutdown path, traceback-free and with empty stderr
  (`v1_1_text_acceptance.md:102`).
- **`move_reason` was not captured** in either run's raw event log — a harness
  oversight fixed in `tests/live_soak.py` after run 2 but never re-run. This is why
  D1's zero-firing result had to be established by replay rather than read directly
  from the log.


---

# v1.2.1-hardening P0/P1 closure record (2026-08-23)

Independent adversarial review enumerated P0-02..P0-20. Every item below is
CLOSED with implementation evidence, regression tests and residual notes in
the release evidence tree. History above is preserved unchanged.

| ID | Defect | Fix | Regression tests | Status |
|----|--------|-----|------------------|--------|
| P0-02 | Malformed config silently replaced by defaults and rewritten over original bytes | Typed parse boundary; ConfigurationError; fail-closed startup (exit 2); structural preservation | test_v1_2_1_config_integrity.py | CLOSED |
| P0-03 | Three divergent config interpretations incl BOM handling | Single utf-8-sig reader shared by runtime + bootstrap checkers | same + policy suite | CLOSED |
| P0-04 | Effective config derived independently by three components | canonical debate/config_policy.py + scripts/effective_config.py CLI consumed by both bootstraps | equivalence tests | CLOSED |
| P0-05 | Any Ollama URL accepted; env silently bypassed intent | loopback-default policy; allow_remote_ollama opt-in; env cannot bypass; warnings+diagnostics | policy suite | CLOSED |
| P0-06 | Dynamic anti-echo prefix-only, mid-line leaks missed | containment-anywhere matching of registered literals | output-guard suite | CLOSED |
| P0-07 | Tiny words ("I") suppressed ordinary sentences | MIN_DYNAMIC_LENGTH=12 gate | same | CLOSED |
| P0-08 | Multiline control values effectively unprotected | per-line segmentation >= threshold | same | CLOSED |
| P0-09 | Reasoning sanitizer matched only exact literal tags; stray closers leaked | tolerant tag grammar (whitespace/attributes/case) streaming-safe; stray closers dropped | filter+clean variant tests; e2e reasoning | CLOSED |
| P0-10 | WS accepted any Origin pre-accept | ASGI entry guard closes foreign origins before snapshot | control-plane e2e | CLOSED |
| P0-11 | No Host validation | loopback-host/port rule (421/close) | same | CLOSED |
| P0-12 | Mutations lacked cross-site defense | Sec-Fetch-Site + Origin rules on POST /api/* (403) | same | CLOSED |
| P0-13 | EOF without terminal done treated as success | done_seen tracking; StreamIncomplete -> protocol_incomplete skip | stream protocol suite; hostile e2e no_done | CLOSED |
| P0-14 | Pause waited on stalled upstream; topic/anchor uncancellable | concurrent race (line vs interrupt vs 30s inactivity); non-streaming branch races event; measured cancel latency | stream suite (measured) ; hostile stall-pause e2e | CLOSED |
| P0-15 | Failed turns advanced rotation/speaker counters | TurnOutcome enum; completed-only cadence; accounting helper | turn-accounting suite | CLOSED |
| P0-16 | Interjection/thesis/reason unbounded; limits not reflected in UI | INPUT_LIMITS central table enforced backend + maxlength sync | boundaries suite | CLOSED |
| P0-17 | Seats truncated/invented silently | strict schema 2..4 unique names, bounds, color format, path-specific errors | same | CLOSED |
| P0-18 | Contradictory numerics accepted (min>max) | post-coercion relation checks rejecting contradictions | same | CLOSED |
| P0-19 | Empty public output counted as advanced turn | SKIPPED_EMPTY_PUBLIC outcome; excluded from completed counters | turn-accounting | CLOSED |
| P0-20 | Queued interjection crossed topic resets | reset_debate_state clears it (single hygiene point) | hygiene test | CLOSED |

Baseline D1 (consensus-breaker inert): markers narrowed to explicit phrases
with token boundaries; breaker now fires only without genuine disagreement
markers (measured saturation evidence honored). Baseline D2 (min_turn_chars
dead key): removed entirely per directive S17.4 option 2. D3/D4/D5 remain
recorded limitations outside this release's scope, as before.
