# Behavioural Baseline — v1.2-phase1-baseline (`d03a1b7`)

**No live run was performed for this snapshot.** Every number below is carried
from the committed v1.1 acceptance corpus. This document's first job is to prove
that corpus legitimately describes `d03a1b7`; its second is to restate the numbers
with their limits intact.

These are a **reference point for comparison**, not an acceptance standard.

---

## 1. Provenance chain — does the v1.1 corpus describe `d03a1b7`?

The corpus was measured against the engine at `fb87ae9`. It only describes
`d03a1b7` if the engine did not change in between.

**MEASUREMENT**

```
git --no-optional-locks diff --stat fb87ae9..d03a1b7 -- app.py debate static config.json
```

→ **empty. No output. Zero files changed.**

**MEASUREMENT** — the full range `fb87ae9..d03a1b7` is 7 commits, 26 files,
12,479 insertions, **0 deletions**, touching only `spike/`, `audit/`,
`.gitignore`, and `DIRECTIVE-V1.2-PHASE1.md`. The commits are the v1.2 Phase 1
spike work (corpus build, Spike A, Spike B, decision memo).

**INFERENCE** (rests on the two measurements above): the engine — `app.py`,
`debate/`, `static/`, `config.json` — is **byte-identical** between `fb87ae9` and
`d03a1b7`. The v1.1 behavioural corpus therefore applies to `d03a1b7` unchanged.
The baseline is **APPLICABLE**, not `NOT APPLICABLE`.

### Evidence file identity

Numbers below are traceable to these exact bytes:

| File | sha256 (worktree) | Bytes |
|---|---|---|
| `audit/v1_1_soak_evidence_run1.json` | `42f0156b3504c9d5798bcc85c3c43062b4bfa5a2fe434a5f3d63d64d67f3d630` | 255,119 |
| `audit/v1_1_soak_evidence_run2.json` | `274a8c0dd8b2ca4fe591877aaa9f8a0a5291271786ca14f34ba31e1e78748d3a` | 160,240 |

Both files are byte-identical between worktree and git blob (no EOL divergence);
see `snapshot/MANIFEST.json` → `eol_differs_from_git: false` for both.

---

## 2. Turn counts

**The `turns` array is not the completed-turn count.** It includes skipped turns
as empty-text records. This exact error has been made twice in this project and is
documented as corrected in `audit/v1_1_text_acceptance.md:7-13`. The correct
denominator is `completed_turns`.

**MEASUREMENT** — recomputed from the raw evidence for this snapshot, filtering
`turns[*].text` on non-empty after strip:

| | Run 1 | Run 2 | Combined |
|---|---:|---:|---:|
| Turn records (`len(turns)`) | 37 | 26 | 63 |
| Empty-text records | 2 | 2 | 4 |
| **Completed turns** | **35** | **24** | **59** |
| `skipped_turns` entries | 2 | 2 | 4 |
| Started turns (`turn_start` events) | 38 | 27 | 65 |
| Duration after first successful turn | 1800.3 s | 1080.6 s | 2880.9 s (48.0 min) |

These reconcile exactly with `audit/v1_1_text_acceptance.md:44-51`. Skips were all
`operator_interruption` from scheduled pause/topic-replacement actions
(`skipped_turns[*].reason`), not model or transport failures.

> Started turns (65) exceed records (63) because each run had one turn in flight
> at shutdown. Three of the four skips had already streamed public text before
> being abandoned — 967, 953 and 497 characters
> (`skipped_after_streaming[*].characters_streamed_before_skip`).

---

## 3. Turn word-count distribution vs the contract

Contract: `config.json` `turn_word_min` **110** / `turn_word_max` **160**,
enforced in the prompt by `debate/prompt_contract.py` `contract_instructions()`
as "a hard limit, not a suggestion".

**MEASUREMENT** — every completed turn scored with the project's own
`prompt_contract.word_count_status(text, 110, 160)`:

| | Run 1 (n=35) | Run 2 (n=24) | Combined (n=59) |
|---|---:|---:|---:|
| min words | 131 | 110 | 110 |
| p25 | 178 | 147 | — |
| median | 198 | 169 | — |
| p75 | 234 | 187 | — |
| mean | 203.3 | 165.8 | — |
| max words | 305 | 232 | 305 |
| **within 110-160** | 6 (17.1%) | 9 (37.5%) | **15 (25.4%)** |
| **under 110** | 0 | 0 | **0 (0.0%)** |
| **over 160** | 29 (82.9%) | 15 (62.5%) | **44 (74.6%)** |

**OBSERVATION** — the floor is respected perfectly (0 turns under 110) and the
ceiling is missed in roughly three turns out of four. The combined mean (≈187
words) sits about 17% above the stated maximum; the worst turn is 305 words,
nearly double it. Run 1 overshoots substantially more than run 2.

**INFERENCE** (rests on the distribution above and on the §5 opener rate): word
ceiling compliance is the weakest measured contract behaviour in the baseline.
This figure is a comparison reference. It is **not** an accepted standard, and
nothing in v1.1 or v1.2 Phase 1 claimed the ceiling was met.

---

## 4. Agreement-opener rate

Contract: `contract_instructions()` states *"Sentence 1 must directly state your
own position... Do not address, name, summarize, praise, validate, concede to, or
characterize another seat in sentence 1."*

Detector: `debate/prompt_contract.py:88` `opens_with_agreement()` — bounded,
deterministic, no model call. Called from `app.py:1148-1150` and recorded as
`agreement_opener` in turn metrics. **Diagnostic only: speech is never rejected or
rewritten on this basis** (stated in the source at `prompt_contract.py:35-36`).

**MEASUREMENT** — every completed turn passed through the real detector:

| | Run 1 | Run 2 | Combined |
|---|---:|---:|---:|
| Agreement openers | 11 / 35 | 6 / 24 | **17 / 59 = 28.8%** |
| Stock-phrase openings (`opens_with_stock_phrase`) | 0 | 0 | **0** |

Phrases that fired: `you've highlighted` ×5, `you've raised` ×4, `i appreciate` ×2,
`you raise an important`, `you're correct`, `you're right`, `you rightly`,
`i agree`, `i see your point` ×1 each.

**OBSERVATION** — the explicitly-banned stock phrases ("That's an excellent
point", "I completely agree") were never used. The violations are all the subtler
"you've highlighted / you've raised" form.

---

## 5. Repetition and reframe

Two distinct mechanisms exist; they are frequently conflated and are kept separate
here.

| | Mechanism A — self-repetition overlap | Mechanism B — argument memory |
|---|---|---|
| Code | `app.py:295-301` `repetition_overlap()` | `debate/argument_memory.py:115` `containment()` |
| Metric | Jaccard over token sets (∩/∪) | Containment (∩ / smaller set) over content words |
| Threshold | `repetition_overlap_threshold` = **0.60** (`config.json:31`) | `REPETITION_THRESHOLD` = **0.45** (`argument_memory.py:76`) |
| Sets | `state.repetition_pending` (`app.py:381-382`) | `state.pending_reframe` (`app.py:1203-1205`) |
| Effect | alternates `challenge` / `reframe` (`app.py:737-741`) | forces `reframe` (`app.py:733-736`) |

**The 0.45 containment threshold in force** is documented with its calibration at
`argument_memory.py:36-70`. It was calibrated against all 55 same-seat comparisons
in this same 59-turn corpus:

```
p10 0.252  p25 0.293  p50 0.336  p75 0.384  p90 0.455  p95 0.557
min 0.188  mean 0.359  max 0.829
```

0.45 sits at p90 and flags **12.7% (7/55)** of the acceptance corpus. Reference
points: identical turn repeated verbatim **1.000**; the known recycled live pair
**0.471** (must fire); distinct argument, same seat **0.072** (must not fire).
The predecessor threshold of 0.35 sat at the corpus median and would have flagged
47% of turns.

**MEASUREMENT** — reframe firings, from `turn_start` event move distributions:

| Move | Run 1 (38 started) | Run 2 (27 started) |
|---|---:|---:|
| `answer-then-advance` | 20 | 13 |
| `analyze` | 5 | 4 |
| `cross-examine` | 4 | 1 |
| `challenge` | 2 | 3 |
| `concur-extend` | 2 | 4 |
| `escalate` | 2 | 1 |
| `evidence` | 2 | 0 |
| `synthesize` | 1 | 0 |
| **`reframe`** | **0** | **1** |

**OBSERVATION** — exactly **one** `reframe` fired across 65 started turns
(1.5%), in run 2.

**INFERENCE** (rests on the move distribution plus `audit/v1_1_text_acceptance.md:109`):
that single firing **cannot be attributed** to either repetition mechanism.
`move_reason` was not captured in the raw event log for either run (a harness
oversight, disclosed at `v1_1_text_acceptance.md:115`), and `reframe` carries
weight 1.0 in `MOVE_WEIGHTS`, so it can be drawn by the weighted fallback with no
repetition trigger at all. **There is no live evidence that either repetition
mechanism fired during the acceptance corpus.** Both are unit-tested directly, not
confirmed live.

Note the circularity worth keeping in view: the 0.45 threshold was calibrated *on
this same corpus*. The corpus cannot independently validate a threshold derived
from it.

---

## 6. Leak-guard results

The defect the acceptance stage exists to verify.

**MEASUREMENT** — counted directly from both evidence files:

| Key | Run 1 | Run 2 |
|---|---:|---:|
| `control_text_leaks_in_tokens` | **0** | **0** |
| `reasoning_tag_leaks` | **0** | **0** |
| `diagnostic_events` (`CONTROL_TEXT_LEAK_BLOCKED`) | **0** | **0** |
| `dead_air_gaps_over_10s` | 0 | 0 |
| `errors` | 0 | 0 |
| `retry_status_count` | 0 | 0 |

`checks.no_control_text_leak_in_token_events` and `checks.no_hidden_reasoning_leak`
are `true` in both runs, as are all 17 other entries in `checks`.

**INFERENCE** (stated as such at `v1_1_text_acceptance.md:58`, and it is the right
call): zero `diagnostic_events` means **the guard's drop path was never exercised
live**. `phi4:14b` and `qwen2.5:14b-instruct` simply never attempted to echo
control text in 63 turns. This is evidence that leakage did not occur; it is
**not** evidence that the guard works. The removal behaviour is verified by
`tests/test_v1_1_regressions.py` at unit level, deterministically — that is where
the guard's proof lives.

---

## 7. Limits of this baseline — INFERENCE

Recorded explicitly, as the directive requires.

1. **One model pair only.** Every number above was measured on `phi4:14b` (Neo) and
   `qwen2.5:14b-instruct` (Clue). Nothing here generalises to another pair. The
   v1.2 Spike B work found seat-level effects large enough to reverse sign between
   the two seats, and found topic choice to be the largest single source of
   variance observed (`audit/v1_2_phase1_decision.md:44-71`).

2. **A small number of topics.** Two segments, each starting on the CRDT/Raft
   topic, each replacing it mid-run with "Can robust systems distinguish
   interruption from failure?" — so the majority of turns discuss the second topic
   (`v1_1_text_acceptance.md:40`). Effectively two topics, not 59 independent ones.

3. **Two runs, deliberately combined.** Run 1 alone (35 completed) missed the
   directive's 40-turn floor; run 2 was run immediately after to clear it. This was
   disclosed rather than merged into a single fabricated timeline
   (`v1_1_text_acceptance.md:38`). Turns are **not** independent samples: they are
   two continuous conversations.

4. **The recycle-group independence caveat applies.** `audit/v1_2_ledger.md`
   records that the Spike A holdout's independent-group structure limits what can
   be generalised from this corpus. Any future claim that generalises these
   behavioural numbers must carry that caveat forward.

5. **These are reference points, not an acceptance standard.** In particular the
   74.6% word-ceiling overshoot (§3) and 28.8% agreement-opener rate (§4) are
   *measurements of known non-compliance*, recorded so a future change can be
   compared against them. They are not thresholds anything is required to meet.

6. **No live run was performed for this snapshot.** The restore rehearsal in
   Stages G and I proves the system starts and serves; it does **not** re-measure
   any behaviour in this document. No claim here is evidence about the restored
   copy's model behaviour.
