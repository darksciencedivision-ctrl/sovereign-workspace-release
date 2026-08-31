"""The operator's 8B local-model ceiling (ENTRY 017) — `adapters.local.model_ceiling`.

LOCAL-01 F-1. Pure over `/api/tags` records; no daemon is contacted and no model is loaded.

The measured defects these pin, all reproduced live at the parent seal `8d9f5d24` before the fix:

  * `phi4:14b` (14.7B) was **authorized to spawn** — the picker offered it and
    `emit_worker_launch` returned `authorized: true`. There was no ceiling anywhere.
  * `deepseek-r1:70b` rendered `available: true` and was refused only later, at `vram_admission`,
    after the operator had already chosen it (S-17: a rendered control that is not a performable
    action).
  * `sam860/dolphin3-llama3.2:3b` — a 3.2B model well inside the ceiling — was never offered at
    all, silently dropped with 6 other namespaced tags (S-19).

EPC-02 B-2 (ENTRY 030/032): these tests describe the ceiling as a REFUSAL, which is now the
TESTING audience's contract rather than everyone's. The operator ruled that the ceiling binds
automated testing and not him - implemented globally it locked him out of 52 of his own 60
installed models - so an over-ceiling model is now ADMITTED WITH AN ADVISORY for the operator
and REFUSED for testing.

Every assertion below is unchanged and still exactly right; the audience is pinned explicitly
in setup_module so this file keeps pinning the defects it was written to pin. The operator
side, and the mutation proof that the Ollama Cloud refusal survives ANY ceiling setting, are
in test_model_ceiling_audience.py.
"""
from __future__ import annotations

import pytest

import os

from adapters.local.model_ceiling import (
    AUDIENCE_ENV,
    AUDIENCE_TESTING,
    CEILING_NAMEPLATE_B,
    admitted_names,
    classify_local_model,
    classify_local_models,
    format_parameter_count,
    parse_parameter_count,
    reasons_by_name,
)


_SAVED_AUDIENCE = None


def setup_module(module):
    """Pin this file to the audience whose contract it describes: refusal above the ceiling."""
    global _SAVED_AUDIENCE
    _SAVED_AUDIENCE = os.environ.get(AUDIENCE_ENV)
    os.environ[AUDIENCE_ENV] = AUDIENCE_TESTING


def teardown_module(module):
    """Never leak the pin. A neighbouring file inheriting it would silently narrow what it
    believes the operator can reach - which is the failure this whole change is about."""
    if _SAVED_AUDIENCE is None:
        os.environ.pop(AUDIENCE_ENV, None)
    else:
        os.environ[AUDIENCE_ENV] = _SAVED_AUDIENCE


def record(name, *, params="8.2B", caps=("completion",), size=5_000_000_000,
           family="qwen3", quant="Q4_K_M"):
    """A `/api/tags` row in the shape the daemon really emits (verified against ollama 0.33.2)."""
    return {
        "name": name,
        "size": size,
        "capabilities": list(caps),
        "details": {"parameter_size": params, "family": family, "quantization_level": quant},
    }


class TestParseParameterCount:
    @pytest.mark.parametrize("raw,expected", [
        ("8.2B", 8.2e9), ("8B", 8e9), ("137M", 137e6), ("566.70M", 566.70e6),
        ("1.65T", 1.65e12), ("70.6B", 70.6e9), ("  14.7B  ", 14.7e9), ("3.2b", 3.2e9),
    ])
    def test_reads_the_daemons_own_strings(self, raw, expected):
        assert parse_parameter_count(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", [None, "", "unknown", "eight billion", [], {}, True, "0B", 0, -5])
    def test_unreadable_is_none_never_zero(self, raw):
        """None, never 0. A 0 would be indistinguishable from a very small model and would sail
        under the ceiling; None is refused explicitly by the classifier."""
        assert parse_parameter_count(raw) is None

    def test_formats_for_a_human(self):
        assert format_parameter_count(8.2e9) == "8.2B"
        assert format_parameter_count(137e6) == "137M"
        assert format_parameter_count(None) == "an unknown number of"


class TestTheCeiling:
    def test_the_model_the_operator_named_is_admitted(self):
        """`qwen3:8b` is 8.2B. ENTRY 017 sets an 8B ceiling AND directs "use the eight billion
        parameters one". Read as a strict bound on the true count it would exclude the very model
        the operator named, so the ceiling is the 8B NAMEPLATE class. This test is the record of
        that reading: if someone tightens it to a strict 8.0e9, this fails and they must go back to
        ENTRY 017 rather than silently drop the operator's model."""
        v = classify_local_model(record("qwen3:8b", params="8.2B"))
        assert v.admitted is True
        assert v.reason == ""

    @pytest.mark.parametrize("name,params", [
        ("granite4.2:8b", "8.8B"), ("dolphin3:8b", "8.0B"), ("dolphin-llama3:8b", "8B"),
        ("deepseek-r1:8b", "8.2B"), ("sam860/dolphin3-llama3.2:3b", "3.2B"),
    ])
    def test_the_rest_of_the_8b_class_is_admitted(self, name, params):
        assert classify_local_model(record(name, params=params)).admitted is True

    @pytest.mark.parametrize("name,params", [
        ("phi4:14b", "14.7B"),          # was AUTHORIZED to spawn before F-1
        ("gemma4:12b", "11.9B"),
        ("ornith:9b", "9.0B"),          # the first nameplate class above the ceiling
        ("deepseek-r1:70b", "70.6B"),   # was offered available:true before F-1
        ("mistral-medium-3.5:latest", "127.7B"),
    ])
    def test_over_the_ceiling_is_refused(self, name, params):
        v = classify_local_model(record(name, params=params))
        assert v.admitted is False
        assert params in v.reason, "the refusal must name the model's TRUE parameter count"
        assert f"{CEILING_NAMEPLATE_B}B ceiling" in v.reason
        assert "ENTRY 017" in v.reason, "the operator must see whose rule refused it"

    def test_an_over_ceiling_model_is_refused_not_hidden(self):
        """ENTRY 017: "excluded from selection with a stated reason, not silently hidden."
        A refusal must therefore always carry text; an empty reason is the silent-absence defect."""
        for v in classify_local_models([record("phi4:14b", params="14.7B")]):
            assert v.reason.strip(), "a refused model with no reason is a silent absence (S-19)"


class TestNotLocalWeights:
    def test_ollama_cloud_rows_are_refused_as_remote(self):
        """`deepseek-v4-pro:cloud` is a 323-byte pointer that executes on ollama.com. It is not
        local operation and falls under the frontier authorization the operator DENIED (OD-31)."""
        v = classify_local_model(
            record("deepseek-v4-pro:cloud", params="1.65T", size=323, family=""))
        assert v.admitted is False
        assert "no model weights on this machine" in v.reason
        assert "remotely" in v.reason

    def test_a_cloud_row_is_refused_for_being_remote_before_being_large(self):
        """Order matters. A cloud pointer is refused because it leaves the host, not because of its
        size — a small remote model would still be remote."""
        v = classify_local_model(record("small:cloud", params="1B", size=290, family=""))
        assert v.admitted is False
        assert "no model weights on this machine" in v.reason

    def test_a_model_whose_blobs_are_gone_is_refused(self):
        v = classify_local_model(record("half-pulled:8b", params="8B", size=1024))
        assert v.admitted is False


class TestCannotHoldAConversation:
    @pytest.mark.parametrize("name,params,family", [
        ("nomic-embed-text:latest", "137M", "nomic-bert"),
        ("bge-m3:latest", "566.70M", "bert"),
        ("mxbai-embed-large:latest", "334M", "bert"),
    ])
    def test_embedding_models_are_refused_though_they_fit(self, name, params, family):
        """All three are far under the ceiling. They emit vectors, not replies, so offering one as
        something to talk to breaches S-19's "no model offered that cannot run"."""
        v = classify_local_model(
            record(name, params=params, caps=("embedding",), family=family, size=300_000_000))
        assert v.admitted is False
        assert "cannot answer a typed message" in v.reason

    def test_the_daemons_own_capability_list_is_the_authority(self):
        """Not a family-name heuristic: the daemon declares capabilities and we read its answer.
        A bert-family model that DOES report completion is admitted."""
        v = classify_local_model(
            record("odd:8b", params="8B", caps=("completion",), family="bert"))
        assert v.admitted is True

    def test_a_row_with_no_capability_list_is_judged_on_size_alone(self):
        """Absent is not the same as empty-of-completion — an older daemon reports no capabilities
        at all, and refusing every model on that basis would black out the whole library."""
        rec = record("legacy:8b", params="8B")
        rec.pop("capabilities")
        assert classify_local_model(rec).admitted is True


class TestFailClosed:
    @pytest.mark.parametrize("params", [None, "unknown", ""])
    def test_an_unreadable_parameter_count_is_refused(self, params):
        v = classify_local_model(record("mystery:latest", params=params))
        assert v.admitted is False
        assert "cannot be shown to be within" in v.reason

    def test_a_nameless_row_is_refused_and_does_not_raise(self):
        assert classify_local_model({"name": ""}).admitted is False

    @pytest.mark.parametrize("junk", [{}, {"name": "x", "details": "not-a-mapping"},
                                      {"name": "y", "size": "huge"},
                                      {"name": "z", "capabilities": "completion"}])
    def test_malformed_rows_never_raise(self, junk):
        """This runs on the operator's display path. A detection helper must not be able to take a
        selector down — the same W-36 rule `ollama_models` follows."""
        assert classify_local_model(junk).admitted in (True, False)


class TestTheHelpers:
    def test_admitted_and_reasons_partition_the_library(self):
        verdicts = classify_local_models([
            record("qwen3:8b", params="8.2B"),
            record("phi4:14b", params="14.7B"),
            record("nomic-embed-text:latest", params="137M", caps=("embedding",),
                   family="nomic-bert", size=274_302_450),
            record("deepseek-v4-pro:cloud", params="1.65T", size=323, family=""),
        ])
        assert admitted_names(verdicts) == ["qwen3:8b"]
        refused = reasons_by_name(verdicts)
        assert set(refused) == {"phi4:14b", "nomic-embed-text:latest", "deepseek-v4-pro:cloud"}
        assert all(text.strip() for text in refused.values())

    def test_reasons_map_omits_admitted_models(self):
        """`reasons.get(name) is None` must mean exactly "offered" — that is the shape
        `_local_options` folds over to decide `available`."""
        verdicts = classify_local_models([record("qwen3:8b", params="8.2B")])
        assert reasons_by_name(verdicts).get("qwen3:8b") is None

    def test_classification_is_deterministically_ordered(self):
        names = ["zeta:8b", "alpha:8b", "mid:8b"]
        verdicts = classify_local_models([record(n, params="8B") for n in names])
        assert [v.name for v in verdicts] == sorted(names)

    def test_verdict_serialises_for_the_operator_report(self):
        d = classify_local_model(record("qwen3:8b", params="8.2B")).as_dict()
        assert d["name"] == "qwen3:8b" and d["admitted"] is True
        assert d["parameter_size"] == "8.2B"
