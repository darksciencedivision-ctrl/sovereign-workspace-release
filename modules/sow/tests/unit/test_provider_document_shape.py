"""Phase 18E `.live.shape` — U305: what a provider's real `-p --output-format json` document
actually LOOKS like, measured rather than assumed.

U238 hole 2 was closed at 18E `.hardening` by making acceptance read
`extract_provider_response_field` — a RECOGNISED response field or nothing. That closure carried an
open assumption, recorded as U305 and stated in `accept_probe`'s own docstring: **neither provider's
real document had ever been read against that reader.** If a CLI nests its answer
(`{"response": {"text": …}}`) or emits content blocks, the strict reader returns `""` and acceptance
REFUSES a genuine live reply. The refusal direction is the safe one, and the ordering was ordered —
but a live acceptance leg that concluded "the provider did not answer" from it would be reporting a
reader defect as a provider fact.

`describe_provider_document` is the instrument that answers it. It reports the document's STRUCTURE
— key names, value types, dotted paths, where the probe token sits, and whether the strict reader
can see it — and never its VALUES. That is a credential-isolation property (§2.2/§13), not a
convenience: a shape record is published as evidence, and a describer that copied string values
would publish whatever the CLI put in them.

It also emits a `skeleton`: the same document with every string leaf replaced by a length
placeholder, EXCEPT strings carrying the probe token, which become the token itself. The skeleton is
therefore a replayable fixture of the real document's shape — the strict reader run against it
answers the same question it answered against the original — with no model prose and no
credential-bearing value in it.
"""
from __future__ import annotations

import json

import pytest

from adapters.frontier.provider_cli_common import (
    PROVIDER_RESPONSE_KEYS,
    describe_provider_document,
    extract_provider_response_field,
)

TOKEN = "GROK_PROVIDER_OK"


class TestTheFlatDocumentTheReaderWasBuiltFor:
    def test_a_recognised_top_level_field_is_visible_to_the_strict_reader(self):
        shape = describe_provider_document(json.dumps({"result": TOKEN}), token=TOKEN)
        assert shape.parsed is True
        assert shape.top_level_type == "object"
        assert shape.top_level_keys == ("result",)
        assert shape.response_key_matched == "result"
        assert shape.strict_response_found is True
        assert shape.token_paths == ("result",)
        assert shape.token_visible_to_strict_reader is True

    def test_a_bare_json_string_document_is_the_response(self):
        shape = describe_provider_document(json.dumps(TOKEN), token=TOKEN)
        assert shape.top_level_type == "string"
        assert shape.strict_response_found is True
        assert shape.token_visible_to_strict_reader is True
        assert shape.token_paths == ("(document)",)


class TestTheShapesU305WasOpenedFor:
    """Each of these is a document in which the model DID answer and the strict reader sees
    nothing. The describer's whole job is to make that distinguishable from a provider that said
    nothing — the two look identical in a verdict, and opposite in a shape."""

    def test_a_nested_answer_is_reported_as_invisible_to_the_strict_reader(self):
        doc = json.dumps({"response": {"text": TOKEN}, "status": "done"})
        shape = describe_provider_document(doc, token=TOKEN)
        assert shape.strict_response_found is False
        assert shape.token_paths == ("response.text",)
        assert shape.token_visible_to_strict_reader is False
        # and the reader itself agrees, which is the fact that would refuse a genuine reply
        assert extract_provider_response_field(doc) == ""

    def test_content_blocks_are_reported_with_their_index(self):
        doc = json.dumps({"content": [{"type": "text", "text": TOKEN}]})
        shape = describe_provider_document(doc, token=TOKEN)
        assert shape.token_paths == ("content[0].text",)
        assert shape.token_visible_to_strict_reader is False

    def test_token_paths_means_the_EXACT_token_not_a_lookalike(self):
        """`token_paths` is read as "where the model put the token", and a live acceptance leg
        makes provider-level decisions from it. A case-folded or punctuation-folded match would
        start naming places the token is not — and the two folds that DO exist for acceptance
        (`_token_answered`'s presence and subtraction folds) are deliberately laxer, so an
        instrument sharing them would report a path for `grok-provider-ok`. This reports structure,
        which means it reports what is there."""
        for lookalike in ("grok_provider_ok", "GROK-PROVIDER-OK", "GROK PROVIDER OK"):
            shape = describe_provider_document(json.dumps({"debug": lookalike}), token=TOKEN)
            assert shape.token_paths == (), lookalike

    def test_a_token_in_a_non_response_field_is_named_by_its_path(self):
        """The U238 hole-2 document. The token IS in the transcript; it is not an answer. A shape
        that only said "token present" would re-open the hole it is meant to make readable."""
        shape = describe_provider_document(
            json.dumps({"status": "done", "debug": TOKEN}), token=TOKEN)
        assert shape.token_paths == ("debug",)
        assert shape.token_visible_to_strict_reader is False
        assert shape.strict_response_found is False


class TestItReportsStructureAndNeverValues:
    """§2.2/§13. A shape record is written to evidence; a describer that copied string values would
    publish whatever the CLI wrote into them."""

    def test_no_string_value_survives_into_the_shape(self):
        secret = "sow-shape-sentinel-value"
        doc = json.dumps({"result": "hello", "session": {"account": secret}, "n": 7})
        shape = describe_provider_document(doc, token=TOKEN)
        assert secret not in json.dumps(shape.as_dict())
        assert "hello" not in json.dumps(shape.as_dict())

    def test_a_secret_shaped_KEY_is_scrubbed_and_a_long_one_is_bounded(self):
        """Key names are provider-controlled DATA, not schema — the published evidence proves it:
        `modelUsage.grok-4.5.costUSD` puts a model identifier in a key position, and a CLI is
        equally free to key a map by account or session. They survive into `top_level_keys`,
        `key_types`, both path lists and the skeleton, none of which passed through
        `redact_diagnostics` before. Found by the gate-validator (MEDIUM-5) and the spec-auditor
        (MEDIUM-1), whose measured example is reproduced here."""
        doc = json.dumps({"xai-api-key=sk-proj-DEADBEEFDEADBEEF": 1,
                          "Authorization: Bearer sk-live-ABCDEF1234567890": "x",
                          "k" * 500: "y", "result": TOKEN})
        shape = describe_provider_document(doc, token=TOKEN)
        blob = json.dumps(shape.as_dict())
        assert "sk-proj-DEADBEEFDEADBEEF" not in blob
        assert "sk-live-ABCDEF1234567890" not in blob
        assert all(len(k) <= 140 for k in shape.top_level_keys)
        assert shape.response_key_matched == "result"    # scrubbing never disturbs a real key

    def test_key_names_and_types_and_paths_are_reported(self):
        doc = json.dumps({"result": "hi", "usage": {"tokens": 12}, "ok": True, "items": ["a"]})
        shape = describe_provider_document(doc, token=TOKEN)
        assert shape.top_level_keys == ("items", "ok", "result", "usage")
        assert shape.key_types["usage"] == "object"
        assert shape.key_types["ok"] == "boolean"
        assert shape.key_types["items"] == "array"
        assert "usage.tokens" in shape.number_paths
        assert "items[0]" in shape.string_paths

    def test_the_skeleton_replaces_prose_and_preserves_the_token(self):
        doc = json.dumps({"response": {"text": f"Sure! {TOKEN}"}, "note": "some prose"})
        shape = describe_provider_document(doc, token=TOKEN)
        assert shape.skeleton == {"response": {"text": TOKEN}, "note": "<str:10>"}
        # replayable: the reader answers the same question about the skeleton as about the original
        assert (extract_provider_response_field(json.dumps(shape.skeleton))
                == extract_provider_response_field(doc))

    @pytest.mark.parametrize("doc", [
        {"result": "", "debug": TOKEN},                      # blankness decides the reader's answer
        {"result": "   ", "thought": f"say {TOKEN}"},
        {"text": "", "stopReason": "cancelled", "thought": TOKEN},
        {"response": {"text": TOKEN}},
        {"result": f"ok {TOKEN}"},
        TOKEN,
    ])
    def test_the_skeleton_replays_the_strict_reader_faithfully(self, doc):
        """The property the skeleton exists for: run the reader against the skeleton and you get
        the same ANSWER as against the original. It was broken for empty strings — `""` became
        `<str:0>`, so a document in which the CLI said nothing produced a skeleton in which it
        did."""
        raw = json.dumps(doc)
        shape = describe_provider_document(raw, token=TOKEN)
        replay = extract_provider_response_field(json.dumps(shape.skeleton))
        original = extract_provider_response_field(raw)
        assert bool(replay) == bool(original)
        assert (TOKEN in replay) == (TOKEN in original)

    def test_a_skeleton_is_NOT_a_fixture_for_echo_or_acceptance_tests(self):
        """The replay property is narrow and this is its far edge, pinned so a later unit finds it
        as a test rather than as a surprise.

        Replacing a token-BEARING string with the bare token deletes the prose `_token_answered`'s
        echo subtraction exists to remove. So a PURE ECHO — refused by acceptance — skeletonises
        into an ACCEPTED document. Found by the gate-validator (MEDIUM-7); it is exactly the
        U238-hole-1/U304 territory this phase closed, and a fixture that walks back into it would
        undo the closure quietly."""
        import tools.providers.frontier_provider_recon as R
        echo = json.dumps({"result": f"Reply with exactly: {TOKEN}"})
        shape = describe_provider_document(echo, token=TOKEN)
        kw = dict(exit_code=0, stderr="", git_status_before="x", git_status_after="x")
        assert R.accept_probe(R.GROK_PROVIDER, TOKEN, stdout=echo, **kw).accepted is False
        assert R.accept_probe(R.GROK_PROVIDER, TOKEN,
                              stdout=json.dumps(shape.skeleton), **kw).accepted is True
        # …while the property the skeleton DOES claim is unaffected: the strict reader agrees.
        assert bool(extract_provider_response_field(json.dumps(shape.skeleton)))
        assert bool(extract_provider_response_field(echo))

    def test_a_blank_string_stays_blank_and_a_full_one_is_measured(self):
        shape = describe_provider_document(json.dumps({"text": "", "note": "abc"}), token=TOKEN)
        assert shape.skeleton == {"text": "", "note": "<str:3>"}

    def test_numbers_are_flattened_and_booleans_are_kept(self):
        """Booleans are classification-relevant (`is_error` is read by `structured_error_of`) and
        carry nothing; a number could be an identifier, so it is reported as a type only."""
        shape = describe_provider_document(
            json.dumps({"is_error": False, "session_id": 981723, "result": TOKEN}), token=TOKEN)
        assert shape.skeleton == {"is_error": False, "session_id": 0, "result": TOKEN}


class TestItFailsClosedOnDocumentsItCannotRead:
    def test_unparseable_output_is_reported_as_unparseable_not_guessed_at(self):
        shape = describe_provider_document("plain text " + TOKEN, token=TOKEN)
        assert shape.parsed is False
        assert shape.top_level_type == "unparseable"
        assert shape.strict_response_found is False
        assert shape.token_visible_to_strict_reader is False
        # the token IS in the transcript and the shape says where it is not: nowhere structured
        assert shape.token_paths == ()

    def test_empty_output_is_not_a_document(self):
        shape = describe_provider_document("", token=TOKEN)
        assert shape.parsed is False
        assert shape.top_level_type == "empty"

    def test_a_pathological_document_is_truncated_rather_than_unbounded(self):
        doc = json.dumps({f"k{i}": f"v{i}" for i in range(5000)})
        shape = describe_provider_document(doc, token=TOKEN, max_nodes=50)
        assert shape.truncated is True
        assert len(shape.string_paths) <= 50

    def test_the_KEY_INVENTORY_is_bounded_by_the_same_budget_as_the_walk(self):
        """`top_level_keys`/`key_types` were built outside the walk, so a 50,000-key document
        enumerated every provider-chosen key beside `truncated: true` — a multi-megabyte record
        written into docs/evidence/live/ from untrusted input (T2), with no way for a reader to
        tell which half had been bounded. Found by the gate-validator (MEDIUM-4)."""
        doc = json.dumps({f"k{i}": i for i in range(5000)})
        shape = describe_provider_document(doc, max_nodes=50)
        assert shape.truncated is True
        assert len(shape.top_level_keys) <= 50
        assert len(shape.key_types) <= 50
        assert len(json.dumps(shape.as_dict())) < 20000

    def test_truncation_fails_CLOSED_and_never_invents_a_response(self):
        """The replay property does not survive truncation, and the direction it breaks in is the
        whole point. A `"<truncated>"` marker is a NON-EMPTY STRING: under a recognised key it read
        as a response the CLI never gave — the blankness inversion by another route. `null` matches
        no reader, so a truncated skeleton can LOSE a response and never invent one.

        Found by the gate-validator (MEDIUM-3), with `max_nodes=400` reachable for any CLI that
        emits a turn or message array."""
        pad = ["x"] * 60
        # case A: the real Grok shape — a blank recognised key that must not become a response
        blank = json.dumps({"pad": pad, "text": ""})
        shape = describe_provider_document(blank, token=TOKEN, max_nodes=50)
        assert shape.truncated is True
        assert shape.strict_response_found is False
        assert extract_provider_response_field(json.dumps(shape.skeleton)) == ""
        # case B: a real response IS lost rather than kept — unfaithful, in the safe direction
        answered = json.dumps({"pad": pad, "result": TOKEN})
        shape_b = describe_provider_document(answered, token=TOKEN, max_nodes=50)
        assert shape_b.truncated is True
        assert shape_b.strict_response_found is True          # the RECORD is right about the original
        assert extract_provider_response_field(json.dumps(shape_b.skeleton)) == ""   # the replay is not

    def test_a_deeply_nested_document_does_not_escape_as_a_RecursionError(self):
        """`json.loads` raises `RecursionError`, not `ValueError`, on deeply nested input. Escaping
        here would take out `run_probe`'s return statement AFTER the live call was spent and the
        lease released — losing the verdict document entirely (spec-audit MINOR-1)."""
        shape = describe_provider_document("[" * 20000 + "]" * 20000, token=TOKEN)
        assert shape.parsed is False
        assert shape.top_level_type == "unparseable"

    def test_depth_is_bounded(self):
        node: dict[str, object] = {"text": TOKEN}
        for _ in range(40):
            node = {"inner": node}
        shape = describe_provider_document(json.dumps(node), token=TOKEN, max_depth=5)
        assert shape.truncated is True
        assert all(p.count(".") <= 5 for p in shape.string_paths)

    def test_no_token_argument_reports_structure_without_a_token_claim(self):
        shape = describe_provider_document(json.dumps({"result": TOKEN}))
        assert shape.token_paths == ()
        assert shape.token_visible_to_strict_reader is None


class TestTheDescriberAgreesWithTheReaderItDescribes:
    @pytest.mark.parametrize("key", list(PROVIDER_RESPONSE_KEYS))
    def test_every_recognised_key_is_reported_as_the_match(self, key):
        shape = describe_provider_document(json.dumps({key: TOKEN}), token=TOKEN)
        assert shape.response_key_matched == key
        assert shape.strict_response_found is True

    def test_the_match_follows_the_readers_own_precedence(self):
        """One list, one order — the describer must not invent a second precedence."""
        doc = json.dumps({"output": "later", "result": "first"})
        shape = describe_provider_document(doc)
        assert shape.response_key_matched == "result"
        assert extract_provider_response_field(doc) == "first"

    def test_an_empty_recognised_field_is_not_a_match(self):
        shape = describe_provider_document(json.dumps({"result": "   ", "debug": TOKEN}),
                                           token=TOKEN)
        assert shape.response_key_matched is None
        assert shape.strict_response_found is False
        assert extract_provider_response_field(json.dumps({"result": "   "})) == ""

    def test_as_dict_is_json_serialisable(self):
        shape = describe_provider_document(json.dumps({"result": TOKEN}), token=TOKEN)
        json.dumps(shape.as_dict())


# ---------------------------------------------------------------------------------------------
# THE MEASUREMENT. U305 answered, 2026-08-02, by the governed live probe of both providers
# (docs/evidence/live/phase18e_probe_document_shape_20260802T0230Z.json).
#
# These two documents are the `skeleton` fields of the real run — the real shapes with every string
# value replaced by its length and the probe token preserved where the CLI put it. Nothing in them
# is model prose and nothing is credential-bearing; that is what the describer's leaf-value-free
# contract buys, and it is what makes a real document safe to keep as a fixture.
#
# PROVENANCE, exactly, because "verbatim" was claimed here and was false in one byte (round-1
# gate-validator MAJOR-2 / spec-auditor MAJOR-1):
#   * the Antigravity fixture IS byte-for-byte the skeleton in `…document_shape_20260802T0219Z.json`
#     — every string in that document is non-empty, so the S1 blank-string defect could not touch
#     it — EXCEPT that the real `response` was `"GEMINI_PROVIDER_OK\n"` and token substitution
#     replaces a token-BEARING string with the bare token, dropping the trailing newline. That is
#     the skeleton working as designed and it is why the assertion below is containment, not
#     equality (spec-audit MINOR-2);
#   * the Grok fixture matches the skeleton in `…grok_default_mode_20260802T0224Z.json` (the
#     post-fix rendering). The FIRST artifact, `…document_shape_20260802T0219Z.json`, was written
#     BEFORE the S1 fix and its grok skeleton therefore reads `"text": "<str:0>"` — the defect
#     itself, published. That artifact is preserved unaltered and corrected in place by
#     `docs/evidence/live/phase18e_probe_document_shape_20260802T0219Z.CORRECTION.md`; the two
#     runs' documents are structurally identical apart from that field.
# ---------------------------------------------------------------------------------------------
GEMINI_TOKEN = "GEMINI_PROVIDER_OK"

#: `agy --mode plan -p … --output-format json`, measured. A flat `response` key: the shape the
#: strict reader was built for. This probe was ACCEPTED and deserved to be.
REAL_ANTIGRAVITY_DOCUMENT = {
    "conversation_id": "<str:36>", "status": "<str:7>", "response": GEMINI_TOKEN,
    "duration_seconds": 0, "num_turns": 0,
    "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
              "cache_read_tokens": 0, "total_tokens": 0},
}

#: `grok --cwd … --permission-mode plan --output-format json -p …`, measured. The CLI exited ZERO
#: and said NOTHING: `text` is the empty string and `stopReason` is `cancelled`. The token appears
#: in exactly one place — `thought`, the reasoning trace, where the model is restating the
#: instruction back to itself ("The user wants me to reply with exactly …").
REAL_GROK_PLAN_MODE_DOCUMENT = {
    "text": "", "stopReason": "<str:9>", "sessionId": "<str:36>", "requestId": "<str:36>",
    "thought": TOKEN,
    "usage": {"input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
              "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0},
    "num_turns": 0, "total_cost_usd": 0, "total_cost_usd_ticks": 0,
    "modelUsage": {"grok-4.5": {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0,
                                "cacheCreationInputTokens": 0, "modelCalls": 0, "costUSD": 0}},
}


class TestU305AnsweredByMeasurement:
    """What the live probe of 2026-08-02 established, kept as a test so it cannot quietly stop
    being true."""

    def test_antigravity_uses_a_flat_recognised_response_field(self):
        doc = json.dumps(REAL_ANTIGRAVITY_DOCUMENT)
        shape = describe_provider_document(doc, token=GEMINI_TOKEN)
        assert shape.response_key_matched == "response"
        assert shape.token_visible_to_strict_reader is True
        # CONTAINMENT, not equality: the real field was `"GEMINI_PROVIDER_OK\n"` and the skeleton's
        # token substitution drops the trailing newline, so an equality assertion in a test titled
        # "what the live probe established" would encode a literal the real document falsifies
        # (spec-audit MINOR-2).
        assert GEMINI_TOKEN in extract_provider_response_field(doc)

    def test_grok_in_plan_mode_said_nothing_and_the_strict_reader_is_right_to_refuse(self):
        """The finding U305 was opened to prevent MISREADING, read the right way round.

        The feared shape was a genuine answer nested where the reader cannot see it. What the host
        produced instead is a document in which the model genuinely did not answer — `text` empty,
        `stopReason: cancelled` — with the token present only in the reasoning trace, because the
        model restated the instruction to itself before the turn was cancelled.

        So the strict reader's `""` is CORRECT here, and no nested-answer accommodation is owed on
        this evidence. The refusal is a fact about the run, not a defect in the reader."""
        doc = json.dumps(REAL_GROK_PLAN_MODE_DOCUMENT)
        shape = describe_provider_document(doc, token=TOKEN)
        assert shape.response_key_matched is None
        assert shape.token_paths == ("thought",)
        assert shape.token_visible_to_strict_reader is False
        assert extract_provider_response_field(doc) == ""
        # `text` IS a recognised key; it is empty, which is not a match — the CLI left it empty
        assert "text" in PROVIDER_RESPONSE_KEYS
        assert REAL_GROK_PLAN_MODE_DOCUMENT["text"] == ""

    def test_the_pre_U238_reader_would_have_ACCEPTED_the_grok_document(self, monkeypatch):
        """U238 hole 2, caught in the wild rather than in a constructed example.

        `extract_provider_text` falls back to the whole document, so the token sitting in `thought`
        reads as an answer — which is how a run where the CLI said NOTHING was accepted. §17.2
        records the operator's 2026-08-02 recon probe as having returned exact tokens for both
        providers; for `grok_build` that acceptance rested on this hole, and this test is the
        measurement that says so.

        It drives `accept_probe` itself with the strict reader swapped back for the best-effort one
        — the same substitution `docs/loop/logs/u238_before_after.py` used — because the first
        version asserted only that the token appears in `extract_provider_text`, which is a fact
        about a reader and NOT the ACCEPTED/REFUSED claim the test's name makes (round-1
        gate-validator MINOR-10)."""
        import tools.providers.frontier_provider_recon as R
        doc = json.dumps(REAL_GROK_PLAN_MODE_DOCUMENT)
        kw = dict(exit_code=0, stdout=doc, stderr="", git_status_before="x", git_status_after="x")

        assert R.accept_probe(R.GROK_PROVIDER, TOKEN, **kw).accepted is False   # today: REFUSED
        monkeypatch.setattr(R, "extract_probe_response_field", R.extract_probe_text)
        assert R.accept_probe(R.GROK_PROVIDER, TOKEN, **kw).accepted is True    # pre-U238: ACCEPTED
