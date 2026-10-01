"""R-14: characterization of the deterministic DEEP guards (semantic_guards.py was 6% covered).

These pin the current behaviour of the narrow category-error checks on tamper-evidence and
crash-safety claims; each case names what it protects.
"""
import sys
from pathlib import Path

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.semantic_guards import mechanism_analysis_issues as issues  # noqa: E402

CRASH = "Is a transactional store crash safe?"
TAMPER = "Is a tamper-evident audit history trustworthy?"
GOOD_CRASH = ("Once a transaction commits, its durable state is recovered after a crash; work that "
              "was never committed is rolled back, which is expected and not a consistency failure.")
GOOD_TAMPER = ("A hash chain can detect an edit but does not prevent one. It needs a separately "
               "trusted anchor, because truncation or rollback of the history, and an omission, "
               "cannot be seen from the chain alone: completeness is a different property.")


def test_unrelated_topics_are_never_checked():
    assert issues("Summarize the quarterly plan.", "anything at all, immutable even") == []


def test_a_crash_answer_must_state_the_committed_boundary():
    assert any("committed-state boundary" in i for i in issues(CRASH, "It is fine and safe."))
    assert issues(CRASH, GOOD_CRASH) == []


def test_loss_of_uncommitted_work_is_not_a_crash_safety_failure():
    bad = ("Crash safety is not guaranteed because uncommitted work is lost. A committed "
           "transaction is durable and recovered.")
    assert any("uncommitted work is expected" in i for i in issues(CRASH, bad))


def test_tamper_evidence_must_not_be_called_immutable():
    assert any("immutable" in i for i in issues(TAMPER, GOOD_TAMPER + " The history is immutable."))
    assert not any("immutable" in i for i in issues(
        TAMPER, GOOD_TAMPER + " The history is not immutable; edits stay possible."))
    assert not any("immutable" in i for i in issues(
        TAMPER, GOOD_TAMPER + " Immutability is not guaranteed by a hash chain."))


def test_tamper_evidence_needs_detection_versus_prevention_anchor_and_limits():
    found = issues(TAMPER, "The chain is a hash chain.")
    assert any("detection from prevention" in i for i in found)
    assert any("trusted anchor" in i for i in found)
    assert any("truncation or rollback" in i for i in found)
    assert any("completeness/omission" in i for i in found)
    assert issues(TAMPER, GOOD_TAMPER) == []


def test_a_negated_or_dispensed_trusted_anchor_does_not_count():
    for sentence in ("There is no trusted anchor.", "A trusted anchor is not required.",
                     "A trusted anchor can be dispensed with."):
        text = GOOD_TAMPER.replace("It needs a separately trusted anchor, because", "However,")
        assert any("trusted anchor" in i for i in issues(TAMPER, text + " " + sentence)), sentence


def test_omission_detection_without_a_trusted_reference_is_refused():
    text = ("The chain can detect an omission. It does not prevent tampering but detects edits. "
            "Truncation and rollback of the history are possible; completeness is separate.")
    assert any("omission detection" in i for i in issues(TAMPER, text))


def test_the_combined_guarantee_must_address_the_atomic_commit_boundary():
    topic = CRASH + " " + TAMPER
    assert any("atomic commit boundary" in i for i in issues(topic, GOOD_CRASH + " " + GOOD_TAMPER))
    both = GOOD_CRASH + " " + GOOD_TAMPER + " The store and the chain share a single atomic commit boundary."
    assert issues(topic, both) == []


def test_an_omission_claim_is_fine_with_a_trusted_reference_and_absent_claims_are_not_flagged():
    with_anchor = GOOD_TAMPER + " With that trusted anchor the chain can detect an omission."
    assert not any("omission detection" in i for i in issues(TAMPER, with_anchor))
    no_claim = ("A hash chain can detect an edit but does not prevent one. Truncation or rollback "
                "of the history, and an omission, would go unseen; completeness is a separate "
                "property.")
    found = issues(TAMPER, no_claim)
    assert any("trusted anchor" in i for i in found)  # the missing anchor is still reported
    assert not any("omission detection" in i for i in found)  # but no omission-detection claim exists
