"""Regressions for the post-run audit fixes (2026-08-07).

Every test here uses PRODUCTION-LENGTH turns. The v1.1 argument-memory test
passed on two 15-word sentences while the mechanism was mathematically
incapable of firing on the 188-word mean it shipped against. That is the
specific failure mode this file exists to prevent, so the fixtures below are
deliberately 150-250 words, matching observed live output.

Sources for the fixtures:
  * REPEAT_A / REPEAT_B  -- Neo turns 5 and 6 of a live session, the same
    argument ("hybrid models" + a historical-precedent analogy) restated.
  * DISTINCT             -- Neo turn 1 of the same session, a genuinely
    different argument by the same seat.
  * The two merge_continuation fixtures are verbatim artifacts that reached
    the public stage in v1.1.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from debate import argument_memory, prompt_contract  # noqa: E402
from debate import turn_completion as tc  # noqa: E402


REPEAT_A = (
    "Clue, you're highlighting a crucial scenario where AI-driven quantum predictions "
    "could expose inconsistencies in classical logic, particularly concerning causality "
    "or determinism. While this presents a significant challenge, such contradictions do "
    "not automatically necessitate an overhaul of our epistemic standards but rather "
    "invite us to expand and refine them. Historically, science has navigated paradigm "
    "shifts by reinterpreting anomalies within broader frameworks; quantum mechanics "
    "itself was once seen as an anomaly under classical physics but eventually integrated "
    "into a larger understanding without discarding the utility of Newtonian principles "
    "for many applications. If quantum algorithms consistently produce results that defy "
    "traditional verification yet align with empirical observations, this could push us "
    "toward developing hybrid models. These models would incorporate both probabilistic "
    "and deterministic approaches to better account for complex phenomena."
)

REPEAT_B = (
    "Clue, you're diving deep into how AI systems using quantum algorithms might force us "
    "to rethink our foundational principles of causality and determinism due to persistent "
    "logical contradictions. While these challenges are formidable, they don't necessarily "
    "mandate a complete overhaul of epistemic standards but rather an expansion of them. "
    "Historically, science has shown remarkable resilience by adapting and integrating new "
    "insights; for instance, how quantum mechanics was reconciled with classical physics "
    "through a broader understanding, not by discarding Newtonian principles entirely. If "
    "AI predictions consistently reveal outcomes that are logically contradictory in "
    "classical terms but consistent within quantum logic, the solution might lie in "
    "developing hybrid models. These models would incorporate both probabilistic and "
    "deterministic elements to account for complex phenomena."
)

DISTINCT = (
    "Clue, you've raised an intriguing point about how AI might shift our understanding of "
    "knowledge. However, I'd argue that this potential alteration doesn't fundamentally "
    "disrupt our conception of truth and belief. A system's architecture is what enables it "
    "to process information in ways that may seem novel, but those capabilities stem from "
    "its underlying structure rather than any inherent wisdom. For instance, AI can analyze "
    "vast datasets and identify patterns far beyond human capacity, yet this reflects the "
    "power of well-designed algorithms rather than an epistemic transformation. The "
    "evidence needed to overturn my position would have to show that AI's processing "
    "mechanisms lead to a fundamentally different form of understanding, a kind of machine "
    "consciousness capable of insights unattainable by humans."
)


# ---------------------------------------------------------------------------
# Argument memory at production length
# ---------------------------------------------------------------------------


def test_fixtures_are_production_length():
    """Guard the guard: if these shrink to toy size the suite stops testing
    the thing that actually broke."""
    for name, text in (("REPEAT_A", REPEAT_A), ("REPEAT_B", REPEAT_B), ("DISTINCT", DISTINCT)):
        assert 100 <= len(text.split()) <= 300, f"{name} is not production-length"


def test_identical_production_length_turn_is_detected():
    """The exact v1.1 failure: recording a full turn and feeding the identical
    turn back scored 0.0000 and never fired."""
    memory = argument_memory.ArgumentMemory(["Neo"])
    assert memory.check_and_record("Neo", REPEAT_A) is None  # empty memory
    assert memory.check_and_record("Neo", REPEAT_A) is not None
    assert memory.last_score("Neo") == pytest.approx(1.0)


def test_near_verbatim_paraphrase_is_detected():
    """Real recycled pair from a live run. Scored 0.047 under the old metric."""
    memory = argument_memory.ArgumentMemory(["Neo"])
    memory.check_and_record("Neo", REPEAT_A)
    matched = memory.check_and_record("Neo", REPEAT_B)
    assert matched is not None
    assert memory.last_score("Neo") >= argument_memory.REPETITION_THRESHOLD


def test_distinct_argument_same_seat_not_flagged():
    memory = argument_memory.ArgumentMemory(["Neo"])
    memory.check_and_record("Neo", REPEAT_A)
    assert memory.check_and_record("Neo", DISTINCT) is None
    assert memory.last_score("Neo") < argument_memory.REPETITION_THRESHOLD


def test_deprecated_shingle_metric_would_still_miss():
    """Documents why the metric changed, so nobody reverts it as 'simpler'."""
    old = argument_memory.phrase_overlap([REPEAT_A], REPEAT_B)
    new = argument_memory.containment([REPEAT_A], REPEAT_B)
    assert old < 0.10, "old Jaccard-on-shingles unexpectedly high"
    assert new >= argument_memory.REPETITION_THRESHOLD
    assert new > old * 4


def test_threshold_is_above_the_calibrated_baseline():
    """Two seats on one topic share vocabulary; the acceptance corpus median
    for this metric is 0.336. A threshold at or below that fires on ~half of
    all turns."""
    assert argument_memory.REPETITION_THRESHOLD > 0.40


def test_recent_returns_compact_labels_not_full_turns():
    """`recent()` feeds the seat's prompt -- storing full turns there would
    balloon the prompt. Comparison text is kept separately."""
    memory = argument_memory.ArgumentMemory(["Neo"])
    memory.check_and_record("Neo", REPEAT_A)
    for label in memory.recent("Neo"):
        assert len(label.split()) <= 12


def test_memory_depth_bounded_and_per_seat_isolated():
    memory = argument_memory.ArgumentMemory(["Neo", "Clue"], depth=3)
    for index in range(6):
        memory.check_and_record("Neo", f"argument number {index} " + DISTINCT)
    assert len(memory.recent("Neo")) == 3
    memory.check_and_record("Clue", REPEAT_A)
    memory.check_and_record("Neo", REPEAT_A)
    assert memory.check_and_record("Clue", REPEAT_A) is not None
    assert len(memory.recent("Clue")) == 2


def test_scores_are_per_instance_not_shared():
    a = argument_memory.ArgumentMemory(["Neo"])
    b = argument_memory.ArgumentMemory(["Neo"])
    a.check_and_record("Neo", REPEAT_A)
    a.check_and_record("Neo", REPEAT_A)
    assert a.last_score("Neo") == pytest.approx(1.0)
    assert b.last_score("Neo") == 0.0


# ---------------------------------------------------------------------------
# Continuation merge seam
# ---------------------------------------------------------------------------


def test_merge_trims_reordered_restatement():
    """Verbatim artifact that reached the public stage in v1.1."""
    tail = (
        "Ultimately, if we observe persistent contradictions that cannot be reconciled "
        "through methodological innovation or interdisciplinary approaches, only then "
        "might we need to consider revising our foundational standards"
    )
    continuation = (
        "then we might need to consider revising our foundational standards of truth "
        "and belief."
    )
    merged = tc.merge_continuation(tail, continuation)
    assert merged.count("foundational standards") == 1
    assert merged.endswith("of truth and belief.")


def test_merge_trims_single_word_duplicate():
    """The observed 'that that' artifact."""
    merged = tc.merge_continuation(
        "it's not necessarily an indication that",
        "that our foundational standards need overhauling.",
    )
    assert " that that " not in f" {merged} "
    assert merged.endswith("need overhauling.")


def test_merge_leaves_clean_continuation_intact():
    tail = "The mechanism here is not just computational power but how these are"
    continuation = "reconciled with empirical evidence and integrated into human understanding."
    merged = tc.merge_continuation(tail, continuation)
    assert merged == f"{tail} {continuation}"


def test_merge_does_not_trim_unrelated_common_opening_word():
    """False-positive guard: a continuation opening with a common word that
    merely appears earlier in the tail must survive."""
    merged = tc.merge_continuation("the system is", "the answer lies in bounded verification.")
    assert "the answer lies in bounded verification." in merged


def test_merge_handles_full_restatement_of_tail():
    merged = tc.merge_continuation(
        "This approach ensures the system is adaptable",
        "This approach ensures the system is adaptable and resilient.",
    )
    assert merged.count("This approach ensures") == 1
    assert merged.endswith("and resilient.")


def test_merge_handles_empty_sides():
    assert tc.merge_continuation("a tail", "") == "a tail"
    assert tc.merge_continuation("", "a continuation") == "a continuation"
    assert tc.merge_continuation("all of it", "all of it") == "all of it"


# ---------------------------------------------------------------------------
# Turn contract: measurable, not aspirational
# ---------------------------------------------------------------------------


def test_word_count_status_classifies_all_three_bands():
    assert prompt_contract.word_count_status(" ".join(["w"] * 40), 110, 160)[1] == "under"
    assert prompt_contract.word_count_status(" ".join(["w"] * 130), 110, 160)[1] == "within"
    count, status = prompt_contract.word_count_status(" ".join(["w"] * 305), 110, 160)
    assert (count, status) == (305, "over")


def test_contract_instructions_honour_configured_bounds():
    text = prompt_contract.contract_instructions(90, 140)
    assert "90-140 words" in text
    assert "hard limit" in text.lower()


def test_agreement_openers_catch_the_v1_1_evasions():
    """v1.1 banned five literal phrases; the models moved to these. 31 of 59
    live turns (53%) opened this way and none were detected."""
    observed = [
        "Clue, you're right that pilot programs help.",
        "Clue, you're correct that granting advisory boards power is crucial.",
        "Clue, you make an essential point about representation.",
        "Clue, you raise an important point about funding.",
        "Neo, I agree that a resilient system is crucial.",
        "Neo, you've highlighted the potential of integrating public health.",
        "Clue, your concerns are valid.",
    ]
    for line in observed:
        assert prompt_contract.opens_with_agreement(line) is not None, line


def test_substantive_opening_is_not_flagged_as_agreement():
    for line in (
        "Clue, that framing fails because it assumes causality it never establishes.",
        "Neo, the mechanism you describe cannot survive a funding shock.",
        "Restriction is an admission of design failure, and here is why.",
    ):
        assert prompt_contract.opens_with_agreement(line) is None, line


# ---------------------------------------------------------------------------
# Opening-move constraint (v1.1 closeout)
#
# The blocklist approach failed three times: unlisted synonyms (v1.1),
# new synonyms after the list was extended, and -- decisively -- the
# literally-banned phrase "your point is well taken" with six words
# inserted mid-string ("your point ON CO-OPTING DECISION-MAKING PLATFORMS
# is well taken"), which defeated startswith matching. These fixtures are
# the historical openers observed live, verbatim, plus the boundary cases
# the directive calls out by name.
# ---------------------------------------------------------------------------

HISTORICAL_OPENERS = (
    "Clue, you make a compelling case about...",
    "Clue, you pinpoint an important issue...",
    "Clue, you highlight a crucial point about...",
    "Clue, the concern about rapid mobilization during crises is valid.",
    "Clue, you raise an insightful point about...",
    "Clue, I acknowledge the challenge posed by...",
    "Clue, the concern about powerful actors co-opting decision-making is legitimate.",
    "Clue, your point on co-opting decision-making platforms is well taken.",
)

OPPONENT_NAMES = ["Neo", "Clue"]


def test_all_eight_historical_openers_detected():
    """Task 3 re-measurement: the new structural detector must catch all 8
    of the historically observed openers that defeated three blocklist
    generations. If this drops below 8/8, Task 1 is not complete."""
    for opener in HISTORICAL_OPENERS:
        assert prompt_contract.opening_move_violation(opener, OPPONENT_NAMES) is not None, opener


def test_inserted_words_do_not_defeat_detection():
    """The case that killed the blocklist: the literally-banned phrase
    with six words inserted mid-string, defeating startswith."""
    text = "Clue, your point on co-opting decision-making platforms is well taken."
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is not None


def test_legitimate_openings_are_not_flagged():
    """A detector that flags legitimate speech is worse than no detector.
    The multi-sentence case is load-bearing: it proves second-person
    engagement is permitted from sentence 2 onward -- revision 1 of this
    directive got this fixture wrong by putting "you" in sentence 1."""
    legitimate = (
        "Restriction is an admission of design failure, and here is why.",
        "Autonomous systems cannot hold accountability, which is the whole problem.",
        "The evidence for structural resilience is compelling.",
        "The mechanism fails under a funding shock. The mechanism you would "
        "need does not survive one.",
    )
    for text in legitimate:
        assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None, text


def test_clean_sentence_one_opponent_named_in_sentence_two_not_flagged():
    """The desired shape: state your position, then engage by name. A
    detector that punishes this defeats the product."""
    text = (
        "My position is that restriction fails without enforcement. "
        "Clue, that view collapses under scrutiny."
    )
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None


def test_opponent_name_matching_is_case_insensitive():
    text = "clue, your framing is backwards."
    result = prompt_contract.opening_move_violation(text, OPPONENT_NAMES)
    assert result is not None and result.startswith("opponent_name")


def test_opponent_name_embedded_in_another_word_not_matched():
    """'Neo' must not match inside 'Neon'."""
    text = "Neon particles diffuse quickly in this simulation of the reactor."
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None


def test_second_person_embedded_in_another_word_not_matched():
    """'you' must not match inside 'young'."""
    text = "Young voters are shaping this debate more than pollsters expected."
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None


def test_curly_apostrophes_normalize():
    straight = prompt_contract.opening_move_violation(
        "you're missing the core mechanism here.", OPPONENT_NAMES
    )
    curly = prompt_contract.opening_move_violation(
        "you’re missing the core mechanism here.", OPPONENT_NAMES
    )
    assert straight is not None
    assert curly is not None
    assert straight == curly


def test_leading_markdown_or_quotation_punctuation_does_not_bypass_detection():
    for text in (
        "**Clue**, that framing is backwards.",
        '"Clue, that framing is backwards," Neo said.',
        "> Clue, that framing is backwards.",
    ):
        assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is not None, text


def test_standalone_validation_words_do_not_trigger():
    """valid / compelling / fair / challenge / concern alone, with no
    opponent name, second-person reference, or discourse-reference
    construction, are legitimate and must not be flagged."""
    text = (
        "The challenge here is structural: a valid, compelling, and fair "
        "accounting of the concern requires more than intuition."
    )
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None


def test_discourse_reference_validation_without_naming_opponent():
    """'That concern is valid' validates a preceding opponent argument by
    discourse reference, without naming them or using 'you'."""
    text = "That concern is valid, but it does not follow that oversight must be human."
    result = prompt_contract.opening_move_violation(text, OPPONENT_NAMES)
    assert result == "discourse_reference_validation"


def test_single_sentence_turn_handled_without_error():
    text = "This is a single sentence turn with no terminal punctuation"
    assert prompt_contract.opening_move_violation(text, OPPONENT_NAMES) is None


def test_empty_text_handled_without_error():
    assert prompt_contract.opening_move_violation("", OPPONENT_NAMES) is None


# ---------------------------------------------------------------------------
# Seat theses must be opposed positions, not roles
# ---------------------------------------------------------------------------


def test_seat_theses_are_present_and_distinct():
    """The v1.1 defaults were compatible stances ('durability comes from
    structure' vs 'claims owe a mechanism') -- both true at once, so nothing
    to debate. Clue's was a method, which can only react, never advance."""
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
    theses = [seat.get("thesis", "") for seat in config["seats"]]
    assert all(len(thesis.split()) >= 15 for thesis in theses), "thesis too thin to hold"
    assert len(set(theses)) == len(theses), "seats share a thesis"
    for thesis in theses:
        assert "I hold that" in thesis, "thesis should assert a position, not describe a role"
