"""SW-ORCH-001 F-20 — a local pane is verified against what it was priced at, or refused.

MEASURED ON THE OPERATOR'S HOST, 2026-09-05, RTX 5060 Ti with 8151 MiB, ollama 0.33.3, all three
from a confirmed-cold daemon and all three through the product's own `ollama run` path:

    unpinned                          : context 131072 | 13.0 GB | 56%/44% CPU/GPU
    `/set parameter num_ctx 4096`     : context 131072 | 13.0 GB | 56%/44% CPU/GPU   (no effect)
    daemon OLLAMA_CONTEXT_LENGTH=4096 : context   4096 |  2.5 GB | 100% GPU, resident

The product cannot command the context: `ollama run` has no context flag, `/set parameter` does not
resize a session that is already loading, and `OLLAMA_CONTEXT_LENGTH` belongs to `ollama serve` — a
daemon this product attaches to and never spawns. What it can do is prove the result per pane, and
refuse a session that is not what the admission gate priced.

These tests are pure over an `/api/ps` body. The field shapes are the real ones, copied from this
host's daemon rather than invented.
"""
from __future__ import annotations

from adapters.local.ollama_session import classify_session_residency

MODEL = "granite4.2:3b"

#: The real numbers this host reported, so a reader can check the fixtures against the receipt.
UNPINNED = {"models": [{"name": MODEL, "model": MODEL,
                        "size": 13550286271, "size_vram": 6005540781,
                        "context_length": 131072}]}
PINNED = {"models": [{"name": MODEL, "model": MODEL,
                      "size": 2501745048, "size_vram": 2501745048,
                      "context_length": 4096}]}


# --- the defect, refused -----------------------------------------------------------------------

def test_the_measured_defect_is_refused_with_both_numbers_named():
    v = classify_session_residency(UNPINNED, model=MODEL, expected_num_ctx=4096)
    assert v["ok"] is False
    assert v["context_length"] == 131072
    assert v["expected_num_ctx"] == 4096
    assert "131072" in v["reason"] and "4096" in v["reason"]
    # the operator must be told the one thing that fixes it, on the host
    assert "OLLAMA_CONTEXT_LENGTH=4096" in v["reason"]


def test_a_correctly_pinned_session_passes():
    v = classify_session_residency(PINNED, model=MODEL, expected_num_ctx=4096)
    assert v["ok"] is True
    assert v["cpu_split"] is False
    assert v["pct_in_vram"] == 100


# --- the silent spill --------------------------------------------------------------------------

def test_a_cpu_split_at_the_right_context_is_still_refused():
    """The state `ollama ps` calls 'loaded'. Right context, wrong residency, and it will crawl."""
    spilled = {"models": [{"name": MODEL, "size": 1000, "size_vram": 600,
                           "context_length": 4096}]}
    v = classify_session_residency(spilled, model=MODEL, expected_num_ctx=4096)
    assert v["ok"] is False
    assert v["cpu_split"] is True
    assert v["pct_in_vram"] == 60
    assert "60%" in v["reason"]
    assert "system RAM" in v["reason"]


def test_a_session_one_byte_short_of_resident_is_refused():
    """Exact, not a tolerance — 'nearly resident' is the state that produced the measurements."""
    nearly = {"models": [{"name": MODEL, "size": 2501745048, "size_vram": 2501745047,
                          "context_length": 4096}]}
    assert classify_session_residency(nearly, model=MODEL, expected_num_ctx=4096)["ok"] is False


# --- fail closed -------------------------------------------------------------------------------

def test_an_unpriced_pane_cannot_be_verified():
    """A verifier that passes when given nothing to check manufactures the assurance it provides."""
    for bad in (0, -1, None, "", "nonsense"):
        v = classify_session_residency(PINNED, model=MODEL, expected_num_ctx=bad)
        assert v["ok"] is False
        assert "priced" in v["reason"]


def test_a_model_the_daemon_is_not_running_is_refused():
    v = classify_session_residency({"models": []}, model=MODEL, expected_num_ctx=4096)
    assert v["ok"] is False
    assert v["found"] is False
    assert "no running session" in v["reason"]


def test_an_unreadable_daemon_answer_is_refused():
    for bad in (None, {}, {"models": None}, {"models": "nope"}, "not a mapping", []):
        v = classify_session_residency(bad, model=MODEL, expected_num_ctx=4096)
        assert v["ok"] is False
        assert v["found"] is False


def test_a_blank_model_tag_is_refused():
    assert classify_session_residency(PINNED, model="", expected_num_ctx=4096)["ok"] is False
    assert classify_session_residency(PINNED, model=None, expected_num_ctx=4096)["ok"] is False


def test_another_models_row_never_satisfies_this_one():
    """A busy daemon runs several models; the verdict must be about the pane's own session."""
    others = {"models": [{"name": "llama3.2:3b", "size": 10, "size_vram": 10,
                          "context_length": 4096}]}
    v = classify_session_residency(others, model=MODEL, expected_num_ctx=4096)
    assert v["ok"] is False
    assert v["found"] is False


def test_the_row_is_matched_on_either_name_or_model_field():
    """`/api/ps` carries both; a daemon that fills only one must still be readable."""
    by_model_only = {"models": [{"model": MODEL, "size": 10, "size_vram": 10,
                                 "context_length": 4096}]}
    assert classify_session_residency(by_model_only, model=MODEL, expected_num_ctx=4096)["ok"] is True
