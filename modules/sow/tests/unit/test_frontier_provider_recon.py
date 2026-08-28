"""Phase 18A — deterministic tests for the Grok/Antigravity reconnaissance + status engine.

Covers the operator directive §16 items that belong to 18A (the runner and its brain). No network,
no provider process: every test drives `tools/providers/frontier_provider_recon.py` through an
injected fake runner, so the suite is hermetic on any host — including one where neither CLI is
installed. The items §16 lists that belong to 18B (governor lease release, picker registration,
interactive launch-ticket construction) are asserted here only as far as 18A can honestly claim
them: that the specs declare SEPARATE subscription resources at allowance 1, and that registration
is reported NOT_REGISTERED until the wiring exists.

The load-bearing test in this file is `TestExitCodeFirstClassification::test_exit_zero_transcript_
with_historical_error_words_is_success` — the Codex-period defect that must never recur.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from node_runtime.supervisor.subscription_governor import SubscriptionLimitExceeded
from tools.providers import frontier_provider_recon as R


def fake_runner(responses: dict[str, R.RunResult]) -> R.Runner:
    """Runner keyed by the joined ARGUMENT tail (argv minus the executable), so a test can script
    `--version` and `models` independently without knowing the resolved path."""

    def run(argv):
        key = " ".join(list(argv)[1:])
        if key not in responses:
            raise AssertionError(f"unscripted provider call: {key!r}")
        return responses[key]

    return run


OK = lambda out="", err="": (0, out, err, False, None)  # noqa: E731
FAIL = lambda rc, out="", err="": (rc, out, err, False, None)  # noqa: E731

GROK_MODELS_OUT = (
    "You are logged in with grok.com.\n"
    "\n"
    "Default model: grok-4.5\n"
    "\n"
    "Available models:\n"
    "  * grok-4.5 (default)\n"
)
AGY_MODELS_OUT = (
    "gemini-3.6-flash-high\n"
    "gemini-3.1-pro-high\n"
    "claude-sonnet-4-6\n"
    "gpt-oss-120b-medium\n"
)


# ---------------------------------------------------------------------------------------------
# §16 — exit-code-first classification (the binding lesson)
# ---------------------------------------------------------------------------------------------
class TestExitCodeFirstClassification:
    def test_exit_zero_is_success(self):
        out = R.classify_provider_outcome(0, "hello", "")
        assert out.outcome == R.OUTCOME_SUCCESS
        assert out.basis == "exit-code-zero"

    @pytest.mark.parametrize("transcript", [
        "warning: you were not logged in earlier; re-authentication succeeded",
        "note: a previous usage limit was reached on 2026-01-01",
        "rate limit backoff engaged, retried, HTTP 429 recovered",
        "please log in was printed by a prior release; ignore",
        "session expired token expired quota exhausted",
    ])
    def test_exit_zero_transcript_with_historical_error_words_is_success(self, transcript):
        """A successful exit is NEVER converted into a login/usage error by keyword matching
        (operator directive §6). This is the exact defect that mislabelled a working Codex CLI."""
        out = R.classify_provider_outcome(0, transcript, transcript)
        assert out.outcome == R.OUTCOME_SUCCESS, out
        assert out.basis == "exit-code-zero"

    def test_exit_zero_with_structured_error_field_is_failure(self):
        """Authority rule 2: an explicit structured error FIELD may fail a zero exit — a keyword
        never may."""
        out = R.classify_provider_outcome(0, "{}", "", structured_error={"code": "bad_request"})
        assert out.outcome == R.OUTCOME_FAILED
        assert out.basis == "structured-error-field"

    def test_nonzero_with_auth_marker_is_auth_required(self):
        out = R.classify_provider_outcome(2, "", "Error: not logged in. Run `grok login`.")
        assert out.outcome == R.OUTCOME_AUTH_REQUIRED
        assert out.basis == "nonzero-exit+auth-marker"

    def test_nonzero_with_usage_marker_is_usage_limit(self):
        out = R.classify_provider_outcome(1, "", "HTTP 429: usage limit reached")
        assert out.outcome == R.OUTCOME_USAGE_LIMIT

    def test_nonzero_without_markers_is_plain_failure(self):
        out = R.classify_provider_outcome(3, "", "panic: unexpected end of stream")
        assert out.outcome == R.OUTCOME_FAILED
        assert out.basis == "nonzero-exit"

    def test_timeout_and_spawn_error_are_distinct_states(self):
        assert R.classify_provider_outcome(None, timed_out=True).outcome == R.OUTCOME_TIMEOUT
        assert R.classify_provider_outcome(None, spawn_error="FileNotFoundError: x").outcome == \
            R.OUTCOME_NOT_SPAWNABLE


# ---------------------------------------------------------------------------------------------
# §16 — command discovery / missing executable / version parsing
# ---------------------------------------------------------------------------------------------
class TestDiscoveryAndVersion:
    def test_missing_executable_is_not_installed_and_probes_nothing(self):
        def explode(argv):
            raise AssertionError("no CLI call may be made when the executable is absent")

        st = R.probe_status(R.GROK_SPEC, explode, check_registration=False, executable=None)
        assert st.state == R.STATE_NOT_INSTALLED
        assert st.command_found is False
        assert st.models == ()
        assert st.auth_state == R.AUTH_UNVERIFIED   # absence is not an auth verdict

    def test_discovery_reports_the_resolved_path_not_a_hardcoded_one(self, monkeypatch):
        monkeypatch.setattr(R.shutil, "which",
                            lambda name: "C:/somewhere/else/grok.CMD" if name == "grok" else None)
        assert R.which_provider(R.GROK_SPEC) == "C:/somewhere/else/grok.CMD"

    def test_discovery_tries_windows_extensions(self, monkeypatch):
        monkeypatch.setattr(R.shutil, "which",
                            lambda name: "C:/x/agy.EXE" if name == "agy.exe" else None)
        assert R.which_provider(R.ANTIGRAVITY_SPEC) == "C:/x/agy.EXE"

    @pytest.mark.parametrize("text,expected", [
        ("grok 0.2.118 (1e1687c1cf)", (0, 2, 118)),
        ("1.1.9", (1, 1, 9)),
        ("v10.20.30-beta", (10, 20, 30)),
        ("no version here", None),
        ("", None),
    ])
    def test_version_parsing(self, text, expected):
        assert R.parse_version(text) == expected

    # -- W-52 (R-48): a version counts only when it is a DECLARATION ------------------------
    # The two probes read `splitlines()[0]` and handed that one line to `parse_version`, which
    # `search`es for the first semver anywhere in what it is given. That failed in both directions,
    # measured through `probe_provider_cli` before repair:
    #   '> agy@1.1.9 start' + 'grok 0.2.118'                  -> (1,1,9)   from the BANNER
    #   'npm WARN update available 1.2.3 -> 2.0.0' + 'grok..'  -> (1,2,3)   the npm OLD version
    #   'npm WARN update available 9.9.9 -> 10.0.0' alone      -> (9,9,9)   meets_minimum=True
    # Switching to "search every line" fixes only the first and makes the other two worse, because
    # the npm numbers still win. The invariant is STRUCTURAL ASSOCIATION, not "some semver wins".
    #
    # The admitted declaration shapes are the ones this tree has actually captured, and no others:
    #   BARE   '1.1.9'                                  (agy --version)
    #   NAMED  'grok 0.2.118 (1e1687c1cf)', 'codex-cli 0.144.6', 'opencode 0.99.0-mock'

    @pytest.mark.parametrize("text,expected", [
        # the captured forms -- CONTROL, these already worked
        ("grok 0.2.118 (1e1687c1cf)", (0, 2, 118)),
        ("codex-cli 0.144.6", (0, 144, 6)),
        ("opencode 0.99.0-mock", (0, 99, 0)),
        ("1.1.9", (1, 1, 9)),
        # a banner with NO version, then the real declaration
        ("> starting agy" + chr(10) + "1.1.9", (1, 1, 9)),
        # a banner that CARRIES a version of its own, then the real declaration
        ("> agy@1.1.9 start" + chr(10) + "grok 0.2.118", (0, 2, 118)),
        # npm update notice, then the real declaration
        ("npm WARN update available 1.2.3 -> 2.0.0" + chr(10) + "grok 0.2.118", (0, 2, 118)),
        ("npm notice New major version available! 9.9.9 -> 10.0.0" + chr(10) + "codex-cli 0.144.6",
         (0, 144, 6)),
        # npm notice with NO provider declaration at all -- version unavailable
        ("npm WARN update available 9.9.9 -> 10.0.0", None),
        ("npm notice 9.9.9 -> 10.0.0" + chr(10) + "npm notice Run npm i -g npm to update", None),
        # malformed / absent
        ("grok build", None),
        ("no version here", None),
        ("", None),
        # several unrelated semvers, none of them a declaration
        ("deps: foo 1.0.0, bar 2.0.0 -> 3.0.0" + chr(10) + "see https://x/1.2.3", None),
    ])
    def test_W52_a_version_counts_only_when_it_is_a_declaration(self, text, expected):
        assert R.parse_version(text) == expected

    def test_W52_a_declaration_below_a_VERSIONLESS_banner_is_found(self):
        """Grades the "first line only" direction ALONE. A banner carrying no version of its own,
        then the real declaration: a first-line-only reader sees no version and refuses, while a
        generic all-lines semver search would find the right one anyway. That asymmetry is what
        lets mutation A be caught without mutation B's grader firing too -- the two failure modes
        are pinned separately rather than as a pair."""
        assert R.parse_version("> starting agy" + chr(10) + "1.1.9") == (1, 1, 9)
        assert R.parse_version("Loading configuration..." + chr(10) + "grok 0.2.118") == (0, 2, 118)
    @pytest.mark.parametrize("line", [
        "see https://example.invalid/docs/1.2.3",
        "npm notice Run npm i -g npm@10.0.0 to update",
        "downloading dependency foo-1.2.3",
        "installed 42 packages in 1.2.3s",
    ])
    def test_W52_a_SINGLE_semver_that_is_not_a_declaration_is_ignored(self, line):
        """Grades the DECLARATION-SHAPE rule alone, and it needed its own test: the first attempt
        graded the shape rule with the npm-only transcript, and that row came back GREEN because
        `npm WARN ... 9.9.9 -> 10.0.0` carries TWO versions and the comparison rule already refuses
        it. The shape rule is what refuses a line carrying exactly ONE version that is nonetheless
        prose -- a URL, an npm install hint, a filename, a duration. Same lesson as W-51 H22: the
        guard that refuses a given input is not always the guard you assumed."""
        assert R.parse_version(line) is None
    def test_W52_THE_LOAD_BEARING_PAIR(self):
        """The centrepiece. The same npm notice, once with the provider's declaration beneath it and
        once without, must give the provider's version and then NOTHING -- which is what proves
        ASSOCIATION rather than generic semver hunting. A parser that merely preferred a later line,
        or preferred the smallest number, or skipped the first line, would pass the first half and
        fail the second."""
        notice = "npm WARN update 9.9.9 -> 10.0.0"
        assert R.parse_version(notice + chr(10) + "grok 1.2.3") == (1, 2, 3)
        assert R.parse_version(notice) is None

    def test_W52_a_comparison_line_is_never_a_declaration(self):
        """`old -> new` carries TWO versions, and a declaration carries one. Structural, not a list
        of npm phrasings -- the same reason W-46/W-47 anchored shapes instead of blacklisting words."""
        assert R.parse_version("1.2.3 -> 2.0.0") is None
        assert R.parse_version("grok 1.2.3 -> 2.0.0") is None

    def test_W52_the_probe_reports_the_DECLARATION_line_not_line_one(self):
        """Both probes displayed `splitlines()[0]` as the version string. With a banner above the
        declaration that printed the banner to the operator while the tuple came from somewhere
        else -- two facts from two different lines. They now come from the same line."""
        out = "npm WARN update available 1.2.3 -> 2.0.0" + chr(10) + "grok 0.2.118 (1e1687c1cf)"
        run = fake_runner({"--version": OK(out), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.version_tuple == (0, 2, 118)
        assert "0.2.118" in (st.version or "")
        assert "npm" not in (st.version or "")

    def test_W52_an_npm_only_transcript_fails_the_version_gate_CLOSED(self):
        """The decisive false positive, at the surface it damages: an update notice with no provider
        declaration used to satisfy `meets_minimum`."""
        run = fake_runner({"--version": OK("npm WARN update available 9.9.9 -> 10.0.0"),
                           "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.version_tuple is None
        assert st.state == R.STATE_UNSUPPORTED_VERSION

    def test_W52_BOTH_probes_agree_on_the_same_transcript(self):
        """The W-49 property, applied to the other duplicated policy this unit found: the
        `splitlines()[0]` rule was written out twice, once per probe."""
        out = "npm WARN update available 1.2.3 -> 2.0.0" + chr(10) + "grok 0.2.118"
        run = fake_runner({"--version": OK(out), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        run2 = fake_runner({"--version": OK(out), "models": OK(GROK_MODELS_OUT)})
        pr = R._P.probe_provider_cli(provider="grok_build", executable="grok", runner=run2,
                                     min_version=(0, 1, 0), parse_models=R.parse_grok_models,
                                     reports_auth=True)
        assert st.version_tuple == pr.version_tuple == (0, 2, 118)

    def test_unparseable_version_fails_closed_to_unsupported(self):
        run = fake_runner({"--version": OK("grok build"), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.state == R.STATE_UNSUPPORTED_VERSION

    def test_version_call_failure_is_probe_failed_not_available(self):
        run = fake_runner({"--version": FAIL(9, "", "boom"), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.state == R.STATE_PROBE_FAILED


# ---------------------------------------------------------------------------------------------
# §16 — model enumeration (never invented, fails closed)
# ---------------------------------------------------------------------------------------------
class TestModelEnumeration:
    def test_grok_models_parsed_from_cli_output(self):
        inv = R.parse_grok_models(GROK_MODELS_OUT)
        assert inv.models == ("grok-4.5",)
        assert inv.default_model == "grok-4.5"
        assert inv.login_reported is True
        assert inv.account_hint == "grok.com"

    def test_grok_models_multi_entry(self):
        inv = R.parse_grok_models(
            "You are logged in with grok.com.\nDefault model: grok-4.5\nAvailable models:\n"
            "  * grok-4.5 (default)\n  * grok-4.5-fast\n")
        assert inv.models == ("grok-4.5", "grok-4.5-fast")

    def test_antigravity_models_parsed_conservatively(self):
        inv = R.parse_antigravity_models(AGY_MODELS_OUT)
        assert inv.models == ("gemini-3.6-flash-high", "gemini-3.1-pro-high",
                              "claude-sonnet-4-6", "gpt-oss-120b-medium")
        assert inv.login_reported is False          # `agy models` reports no auth state

    @pytest.mark.parametrize("noise", [
        "Available models:", "  something with spaces  ", "", "   ",
        "Error: could not reach the model service",
    ])
    def test_antigravity_prose_lines_are_never_taken_as_models(self, noise):
        assert R.parse_antigravity_models(noise).models == ()

    # -- W-44 -------------------------------------------------------------------------------
    # Two defects in the same eight lines, and they pull in OPPOSITE directions — which is why
    # neither half may be fixed alone. The old filter was `not line or line.endswith(":") or
    # " " in line`, so it rejected every listing that carried any layout at all, and accepted any
    # bare one-word line the CLI happened to print. Widening it to split columns without also
    # tightening the id shape makes the second half strictly worse.

    @pytest.mark.parametrize("word", [
        "Error", "Traceback", "unauthenticated", "Warning", "FAILED", "None", "null", "true",
    ])
    def test_antigravity_bare_prose_WORDS_are_never_models(self, word):
        """The half that reaches the operator. `agy models` printing a single word — a bare
        `Traceback` before the parenthesised line, a `unauthenticated` status word — used to yield
        that word as the provider's entire inventory with `parse_note == "ok"`, and the picker then
        offered it as a model with `verified: True` and the note *"confirmed present in the CLI's
        own listing"*. A model id is not a word: it carries a digit or a separator."""
        assert R.parse_antigravity_models(word).models == ()

    def test_antigravity_reports_the_lines_it_discarded(self):
        """`parse_note` is the only place a discarded line can surface, and silence there is what
        made the empty-inventory case indistinguishable from a genuinely empty listing. Follows the
        `parse_grok_models` precedent, and goes one step further: grok says nothing about rejects
        when it found no models, which is exactly the prose-only case that most needs saying."""
        note = R.parse_antigravity_models("Traceback\nError: unreachable\n").parse_note
        assert "fail closed" in note
        assert "discarded" in note

    def test_antigravity_ok_note_still_counts_what_it_threw_away(self):
        inv = R.parse_antigravity_models("gemini-3-pro\nsomething went wrong here\n")
        assert inv.models == ("gemini-3-pro",)
        assert "discarded" in inv.parse_note

    @pytest.mark.parametrize("listing, expected", [
        # bullets — the shape `parse_grok_models` already reads for the other provider
        ("  * gemini-3-pro\n  * gemini-3-flash\n", ("gemini-3-pro", "gemini-3-flash")),
        ("- gemini-3-pro\n- gemini-3-flash\n", ("gemini-3-pro", "gemini-3-flash")),
        ("• gemini-3-pro\n", ("gemini-3-pro",)),
        # TAB-delimited columns: a tab is a structural delimiter, never English word spacing
        ("gemini-3-pro\tGemini 3 Pro\ngemini-3-flash\tGemini 3 Flash\n",
         ("gemini-3-pro", "gemini-3-flash")),
        # a run of TWO OR MORE spaces is a column separator for the same reason
        ("gemini-3-pro    Gemini 3 Pro\ngemini-3-flash  Gemini 3 Flash\n",
         ("gemini-3-pro", "gemini-3-flash")),
        # the annotation shape, which used to drop the annotated row and keep its sibling
        ("gemini-3-pro (default)\ngemini-3-flash\n", ("gemini-3-pro", "gemini-3-flash")),
        # a header does not stop the listing under it being read
        ("Available models:\n  * gemini-3-pro\n", ("gemini-3-pro",)),
    ])
    def test_antigravity_reads_a_listing_that_carries_layout(self, listing, expected):
        """The other half. Every one of these returned `()` — an EMPTY inventory, which fails the
        picker closed for a provider that is working — except the annotated case, which was worse:
        it dropped `gemini-3-pro (default)`, kept its sibling, and reported `parse_note == "ok"`.
        A silently partial inventory is the one outcome neither an operator nor a later reader can
        detect."""
        assert R.parse_antigravity_models(listing).models == expected

    def test_antigravity_refuses_a_SENTENCE_that_opens_with_a_real_model_id(self):
        """The trap a column-splitting fix walks into. `gpt-4 is not available in your region` has a
        genuinely model-shaped first token, so tightening the id shape alone does not save it — what
        saves it is that single spaces are NOT a column delimiter. The line is discarded and said."""
        inv = R.parse_antigravity_models("gpt-4 is not available in your region\n")
        assert inv.models == ()
        assert "discarded" in inv.parse_note

    def test_antigravity_refuses_a_parenthesised_traceback_tail(self):
        """`Traceback (most recent call last)` splits into a word plus something the shape of an
        annotation, so an annotation rule alone would admit it. The id shape is what refuses it."""
        assert R.parse_antigravity_models("Traceback (most recent call last)").models == ()

    def test_antigravity_prose_can_never_reach_the_picker_as_a_verified_model(self):
        """The defect stated at the surface it damages, not at the parser. Written as a test because
        `parse_antigravity_models` returning `()` and the picker offering nothing are two facts, and
        this unit is only worth anything if the second one follows."""
        from adapters.frontier import antigravity as AG
        from adapters.frontier import provider_cli_common as C
        inv = R.parse_antigravity_models("Traceback\n")
        assert inv.models == ()
        probe = C.ProviderCliProbe(
            provider="google_antigravity", present=True, executable="agy", version="1.0.0",
            version_tuple=(1, 0, 0), meets_minimum=True, auth_state=R.AUTH_UNVERIFIED,
            auth_detail="", models=inv.models, default_model=None, model_note=inv.parse_note,
            detail="")
        assert probe.selectable_models() == ()
        # The exact field the defect corrupted. Before W-44 this same call returned
        # `verified: True` with the note "confirmed present in the CLI's own listing", because the
        # word was IN the listing. W-44 emptied the listing; W-51 then made an empty listing REFUSE
        # an explicit request outright rather than carry it unverified, so the assertion here moved
        # from "published but not verified" to "not published at all" — strictly stronger, and the
        # reason this test now expects a raise.
        with pytest.raises(ValueError, match="EMPTY"):
            AG.roster_descriptor("Traceback", inv.models)

    # -- W-45 (A-7) -------------------------------------------------------------------------
    # MEASURED against W-44 parser rather than assumed covered by it, and the measurement is why
    # this unit exists: `Unauthorized`, `401 Unauthorized`, `HTTP 401` and `error: 401` were
    # already refused, and a bare `401` was NOT. W-44 evidence rule asked for "a digit or a
    # separator", which separates a model id from an English WORD but not from a bare NUMBER --
    # and an HTTP status line printed on its own is exactly a bare number. The correction is to
    # that one rule: not a second filtering layer, and not a list of auth words. A blacklist would
    # have made these rows green while leaving `429`, `500` and every future code still minted.

    @pytest.mark.parametrize("row", [
        "Unauthorized", "401", "403", "429", "500", "401 Unauthorized", "Unauthorized: 401",
        "HTTP 401", "401: Unauthorized", "error: 401", "Forbidden", "Error 401 Unauthorized",
    ])
    def test_antigravity_auth_error_output_never_becomes_a_model(self, row):
        """A-7. `agy models` failing an authorization check must yield an EMPTY inventory. The
        provider prints its error on the same stream the listing would use, so every one of these
        is a line the parser really sees -- and any one surviving is a slug the picker offers."""
        assert R.parse_antigravity_models(row).models == ()

    def test_antigravity_a_bare_status_NUMBER_is_not_a_model_id(self):
        """The one A-7 row W-44 did not cover, kept as its own test because it is the whole of
        W-45. A model id carries a LETTER. `401` carries a digit, which W-44 accepted as evidence
        that a token was an id rather than a word -- and it is evidence against being a word, not
        evidence of being an id."""
        inv = R.parse_antigravity_models("401")
        assert inv.models == ()
        assert "discarded" in inv.parse_note

    def test_antigravity_a_separator_run_of_digits_is_also_not_a_model_id(self):
        """`4-0-1` satisfies BOTH of W-44 evidence forms -- digits AND separators -- and is still
        not a model id. Pinned so the correction is understood as "an id contains a letter" rather
        than "an id is not a bare integer", which is the narrower rule that would leave this open."""
        assert R.parse_antigravity_models("4-0-1").models == ()

    def test_antigravity_digit_heavy_REAL_ids_still_survive_the_correction(self):
        """The other direction, and the reason the rule is "contains a letter" rather than "has no
        digits": real ids are digit-heavy. Without this leg the unit could be satisfied by a parser
        that refuses everything."""
        inv = R.parse_antigravity_models(chr(10).join(
            ["o3", "gpt-4", "grok-4.5", "gpt-oss-120b-medium"]))
        assert inv.models == ("o3", "gpt-4", "grok-4.5", "gpt-oss-120b-medium")
        assert inv.parse_note == "ok"

    def test_antigravity_a_status_number_cannot_reach_the_picker_as_a_verified_model(self):
        """A-7 stated at the surface it damages. Before W-45 this exact call returned
        `verified: True` with the note "confirmed present in the CLI own listing" for the string
        `401`, and `selectable_models()` offered it."""
        from adapters.frontier import antigravity as AG
        from adapters.frontier import provider_cli_common as C
        inv = R.parse_antigravity_models("401")
        assert inv.models == ()
        probe = C.ProviderCliProbe(
            provider="google_antigravity", present=True, executable="agy", version="1.0.0",
            version_tuple=(1, 0, 0), meets_minimum=True, auth_state=R.AUTH_UNVERIFIED,
            auth_detail="", models=inv.models, default_model=None, model_note=inv.parse_note,
            detail="")
        assert probe.selectable_models() == ()
        # W-51: an empty listing now REFUSES an explicit request outright rather than publishing
        # it unverified, so this assertion moved from "published but not verified" to "not
        # published at all" -- strictly stronger.
        with pytest.raises(ValueError, match="EMPTY"):
            AG.roster_descriptor("401", inv.models)

    def test_empty_enumeration_fails_closed_with_a_reason(self):
        inv = R.parse_grok_models("")
        assert inv.models == ()
        assert "fail closed" in inv.parse_note


# ---------------------------------------------------------------------------------------------
# §16 — authentication-required classification / never inferred from presence
# ---------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------
# W-49 (R-08) - the two probes are ONE implementation with two callers
# ---------------------------------------------------------------------------------------------
class TestTheTwoProbesAgree:
    """`probe_status` (recon surface) and `probe_provider_cli` (adapter surface) carried SEPARATE
    COPIES of the same auth policy, and they had already drifted in two ways at once."""

    GROK_INV = "Available models:" + chr(10) + "  * grok-4.5" + chr(10)
    LOGIN_LINE = "You are logged in with grok.com."

    def _both(self, models_result):
        run = fake_runner({"--version": OK("grok 0.2.118"), "models": models_result})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        run2 = fake_runner({"--version": OK("grok 0.2.118"), "models": models_result})
        pr = R._P.probe_provider_cli(provider="grok_build", executable="grok", runner=run2,
                                     min_version=(0, 1, 0), parse_models=R.parse_grok_models,
                                     reports_auth=True)
        return st, pr

    def test_the_login_line_on_STDERR_is_read_by_BOTH(self):
        """R-08, and the shape the REAL CLI uses: grok 0.2.118 writes its declarative auth line to
        STDERR and the inventory to stdout at exit zero. `probe_provider_cli` parsed both streams;
        `probe_status` parsed stdout ALONE -- so for the very same call one said AUTHENTICATED and
        the other UNVERIFIED. Which stream the parser sees is AUTH POLICY, not formatting."""
        st, pr = self._both(OK(self.GROK_INV, self.LOGIN_LINE))
        assert st.auth_state == R.AUTH_AUTHENTICATED
        assert pr.auth_state == R.AUTH_AUTHENTICATED
        assert st.auth_confirmed is True

    def test_an_EXPLICIT_not_authenticated_report_is_preserved_by_BOTH(self):
        """The other half of R-08. `probe_status` had NO `auth_required_reported` branch at all --
        it parsed the evidence and dropped it one line later, so a CLI explicitly saying the
        operator is signed out was recorded as merely UNVERIFIED."""
        st, pr = self._both(OK("You are not authenticated." + chr(10) + self.GROK_INV, ""))
        assert st.auth_state == R.AUTH_REQUIRED
        assert pr.auth_state == R.AUTH_REQUIRED
        assert st.state == R.STATE_AUTH_REQUIRED

    @pytest.mark.parametrize("name", ["stderr", "stdout", "not_authed", "silence"])
    def test_the_two_probes_agree_on_every_shape(self, name):
        """Agreement asserted as its own property across all four shapes, because "both were
        repaired" and "both now answer the same thing" are different claims and only the second is
        what R-08 asks for."""
        shapes = {
            "stderr": OK(self.GROK_INV, self.LOGIN_LINE),
            "stdout": OK(self.LOGIN_LINE + chr(10) + self.GROK_INV, ""),
            "not_authed": OK("You are not authenticated." + chr(10) + self.GROK_INV, ""),
            "silence": OK(self.GROK_INV, ""),
        }
        st, pr = self._both(shapes[name])
        assert st.auth_state == pr.auth_state
        assert st.models == pr.models

    def test_the_spec_NAMES_its_parser_so_no_provider_falls_through_an_else(self):
        """[[U463]], parked here by operator ruling. `probe_status` chose the parser with
        `parse_grok_models(out) if spec.provider == GROK_PROVIDER else parse_antigravity_models(out)`,
        so ANY third provider silently got the ANTIGRAVITY parser -- a provider read by a parser
        written for a different format, which is the class W-44 repaired. A required spec field
        cannot be fallen through."""
        assert R.GROK_SPEC.parse_models is R.parse_grok_models
        assert R.ANTIGRAVITY_SPEC.parse_models is R.parse_antigravity_models
        seen = {}

        def third_party_parser(text):
            seen["text"] = text
            return R.ModelInventory(("only-this-parser-produces-me",), None, None, False, False, "ok")

        import dataclasses
        spec = dataclasses.replace(R.GROK_SPEC, provider="third_party",
                                   parse_models=third_party_parser)
        run = fake_runner({"--version": OK("grok 0.2.118"), "models": OK("anything", "")})
        st = R.probe_status(spec, run, check_registration=False, executable="grok")
        assert st.models == ("only-this-parser-produces-me",)
        assert seen["text"] is not None

    def test_ONE_implementation_not_two(self):
        """The structural claim, asserted rather than described: both callers reach the same
        function object. Two names for one policy is how this drifted the first time."""
        assert R.classify_models_call is R._P.classify_models_call

class TestAuthenticationClassification:
    def test_grok_logged_in_line_yields_authenticated_and_available(self):
        run = fake_runner({"--version": OK("grok 0.2.118 (abc)"), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.auth_state == R.AUTH_AUTHENTICATED
        assert st.state == R.STATE_AVAILABLE
        assert st.models == ("grok-4.5",)

    def test_grok_silence_is_unverified_neither_authenticated_nor_required(self):
        """Silence is a third thing. An inventory with no recognised login line must not be read
        as authenticated (the original hazard) NOR as a verdict that the operator must sign in
        (which would refuse a working provider after a CLI reworded its banner)."""
        run = fake_runner({"--version": OK("grok 0.2.118"),
                           "models": OK("Available models:\n  * grok-4.5\n")})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.auth_state == R.AUTH_UNVERIFIED
        assert st.state != R.STATE_AUTH_REQUIRED
        assert st.auth_confirmed is False        # unverified is never launch-ready
        assert st.state_caveat                 # and the caveat must ride with the state

    # -- W-46 (A-8) -------------------------------------------------------------------------
    # `_GROK_LOGIN_MARKER_RE` was applied with `.search()`, so ANY line CONTAINING the phrase
    # "you are logged in" reported a logged-in session -- including sentences that say the
    # opposite, ask a question, or describe a condition. `probe_status` turns `login_reported`
    # straight into AUTH_AUTHENTICATED, so a help paragraph became a verdict about the operator.

    @pytest.mark.parametrize("prose", [
        "If you are logged in elsewhere, run `grok logout` first.",
        "Error: you are logged in on another device; sessions are limited to one.",
        "To check whether you are logged in, run `grok whoami`.",
        "Note: you are logged in only after completing the browser flow.",
        "Warning: you are logged in with an expired token.",
        "  # you are logged in",
    ])
    def test_grok_CONDITIONAL_prose_never_reports_a_login(self, prose):
        """A-8. The login line is the CLI OWN declarative report of its auth state, and it is the
        only auth evidence available without a live call -- which is exactly why a sentence that
        merely mentions the phrase must not be read as one. `login_reported` stays False, and the
        status layer then answers UNVERIFIED, which is the honest third state."""
        inv = R.parse_grok_models(prose)
        assert inv.login_reported is False
        assert inv.account_hint is None

    def test_grok_conditional_prose_does_not_reach_AUTHENTICATED_through_probe_status(self):
        """The surface the defect damages. Not inherited from the parser test above: `login_reported`
        being False and the probe refusing to say AUTHENTICATED are two facts, and only the second
        one is what an operator or a launch gate reads."""
        out = ("If you are logged in elsewhere, run `grok logout` first." + chr(10)
               + "Available models:" + chr(10) + "  * grok-4.5" + chr(10))
        run = fake_runner({"--version": OK("grok 0.2.118"), "models": OK(out)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.auth_state == R.AUTH_UNVERIFIED
        assert st.auth_confirmed is False
        assert st.models == ("grok-4.5",)      # the listing is still read; only the CLAIM is refused

    def test_grok_the_REAL_declarative_login_line_still_reports(self):
        """The other direction, and the reason this is an anchoring rule rather than a ban on the
        phrase: the observed line must keep working, with its service hint."""
        inv = R.parse_grok_models("You are logged in with grok.com.")
        assert inv.login_reported is True
        assert inv.account_hint == "grok.com"
        bare = R.parse_grok_models("You are logged in.")
        assert bare.login_reported is True and bare.account_hint is None

    def test_grok_a_login_line_with_trailing_prose_is_NOT_read_as_a_login(self):
        """DECLARED BOUND. A sentence that begins declaratively and then continues into prose is
        refused rather than parsed optimistically. Fail-closed matches the module standing answer
        that silence is UNVERIFIED -- never AUTHENTICATED on a shape nobody has observed."""
        inv = R.parse_grok_models("You are logged in with grok.com and 2 other devices.")
        assert inv.login_reported is False

    def test_antigravity_presence_alone_is_never_authenticated(self):
        """The executable exists, the version parses, models enumerate — and auth is still
        UNVERIFIED, because this CLI has no offline auth surface (§6)."""
        run = fake_runner({"--version": OK("1.1.9"), "models": OK(AGY_MODELS_OUT)})
        st = R.probe_status(R.ANTIGRAVITY_SPEC, run, check_registration=False, executable="agy")
        assert st.auth_state == R.AUTH_UNVERIFIED
        assert st.state == R.STATE_AVAILABLE
        assert "only confirmable by the live probe" in st.auth_detail

    def test_nonzero_models_call_with_auth_text_is_auth_required(self):
        run = fake_runner({"--version": OK("grok 0.2.118"),
                           "models": FAIL(1, "", "not logged in — run `grok login`")})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.state == R.STATE_AUTH_REQUIRED

    def test_exit_zero_models_output_mentioning_login_history_stays_available(self):
        """End-to-end guard for the §6 rule at the STATUS layer, not just the classifier."""
        run = fake_runner({
            "--version": OK("grok 0.2.118"),
            "models": OK("You are logged in with grok.com.\n"
                         "note: your previous session had expired and a usage limit was hit\n"
                         "Available models:\n  * grok-4.5 (default)\n")})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.state == R.STATE_AVAILABLE
        assert st.auth_state == R.AUTH_AUTHENTICATED


# ---------------------------------------------------------------------------------------------
# §16 — headless probe command construction (never auto-approving)
# ---------------------------------------------------------------------------------------------
class TestProbeCommandConstruction:
    def test_grok_probe_uses_only_flags_this_build_has(self):
        argv = R.build_grok_probe_command("grok", repo_root="D:/repo")
        assert argv[0] == "grok"
        assert argv[1:3] == ["--cwd", "D:/repo"]
        assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
        assert "-p" in argv
        assert argv[-1] == f"Reply with exactly: {R.GROK_PROBE_TOKEN}"
        # the operator directive's example flag that this build does not have
        assert "--no-auto-update" not in argv

    def test_grok_probe_takes_a_model_when_asked(self):
        argv = R.build_grok_probe_command("grok", model="grok-4.5")
        assert argv[argv.index("-m") + 1] == "grok-4.5"

    def test_antigravity_probe_uses_print_and_json(self):
        argv = R.build_antigravity_probe_command("agy", model="gemini-3.1-pro-high")
        assert argv[0] == "agy"
        assert argv[argv.index("--model") + 1] == "gemini-3.1-pro-high"
        assert argv[argv.index("--output-format") + 1] == "json"
        assert "-p" in argv
        assert "--cwd" not in argv          # this CLI has no such flag

    @pytest.mark.parametrize("builder", [R.build_grok_probe_command,
                                         R.build_antigravity_probe_command])
    def test_no_probe_ever_carries_an_auto_approval_flag(self, builder):
        argv = builder()
        for bad in R._FORBIDDEN_PROVIDER_ARGS:
            assert bad not in argv

    def test_forbidden_arguments_are_refused_structurally(self):
        with pytest.raises(ValueError):
            R._assert_no_forbidden(["grok", "--always-approve"])
        with pytest.raises(ValueError):
            R._assert_no_forbidden(["agy", "--dangerously-skip-permissions"])
        with pytest.raises(ValueError):
            R._assert_no_forbidden(["grok", "--permission-mode", "bypassPermissions"])

    def test_a_benign_permission_mode_is_not_refused(self):
        R._assert_no_forbidden(["grok", "--permission-mode", "plan"])  # must not raise

    @pytest.mark.parametrize("flag, why", [
        ("--no-plan", "undoes the pinned plan mode outright"),
        ("--plugin-dir", "its own help calls the scope 'always trusted' - hooks and MCP servers "
                         "activate without a prompt"),
        ("--agents", "inline subagent definitions widen who acts, not just what is allowed"),
    ])
    def test_the_widening_flags_the_capture_documents_are_refused(self, flag, why):
        """Round-3 spec-audit MEDIUM-4: the list claimed to hold every tool-widening flag the
        captured help documents, and these three - all present in `grok --help` - were missing.
        A claim about a captured surface is checkable against that surface, so it is checked."""
        with pytest.raises(ValueError):
            R._assert_no_forbidden(["grok", flag, "x"])
        assert flag in R._FORBIDDEN_PROVIDER_ARGS, why

    def test_instruction_injection_flags_are_deliberately_not_in_the_permission_list(self):
        """`--system-prompt-override` and `--rules` are node-controlled untrusted INPUT (T2, 18B),
        not permission widening. Conflating the two would make the guard's name a lie in the other
        direction; U235 owns them. This test pins the boundary so it is a decision, not a gap."""
        for flag in ("--system-prompt-override", "--rules"):
            assert flag not in R._FORBIDDEN_PROVIDER_ARGS
        # and neither is silently emitted by a probe either way
        for builder in (R.build_grok_probe_command, R.build_antigravity_probe_command):
            argv = builder()
            assert "--system-prompt-override" not in argv and "--rules" not in argv


# ---------------------------------------------------------------------------------------------
# §16 — probe acceptance: structured output, token, repository preservation
# ---------------------------------------------------------------------------------------------
class TestProbeAcceptance:
    STATUS = " M docs/loop/LOOP_STATE.json\n"

    def test_successful_structured_probe_is_accepted(self):
        stdout = json.dumps({"result": f"{R.GROK_PROBE_TOKEN}"})
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0, stdout=stdout,
                           git_status_before=self.STATUS, git_status_after=self.STATUS)
        assert v.accepted and v.token_seen and v.structured_output_parsed and v.repo_unchanged

    def test_nonzero_provider_failure_is_refused(self):
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=1, stdout="",
                           stderr="boom", git_status_before=self.STATUS,
                           git_status_after=self.STATUS)
        assert not v.accepted
        assert v.outcome.outcome == R.OUTCOME_FAILED

    def test_missing_token_is_refused_even_on_a_clean_exit(self):
        v = R.accept_probe(R.ANTIGRAVITY_PROVIDER, R.ANTIGRAVITY_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": "Sure! Here is a poem."}),
                           git_status_before="", git_status_after="")
        assert not v.accepted
        assert R.ANTIGRAVITY_PROBE_TOKEN in v.reason

    def test_unparseable_output_is_refused(self):
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=f"plain text {R.GROK_PROBE_TOKEN}",
                           git_status_before="", git_status_after="")
        assert not v.accepted
        assert "structured output did not parse" in v.reason

    def test_repository_modification_during_a_probe_is_refused(self):
        stdout = json.dumps({"result": R.GROK_PROBE_TOKEN})
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0, stdout=stdout,
                           git_status_before=" M a.py\n", git_status_after=" M a.py\n M b.py\n")
        assert not v.accepted
        assert "repository state snapshot" in v.reason

    def test_uncaptured_git_status_is_treated_as_unverified_not_clean(self):
        stdout = json.dumps({"result": R.GROK_PROBE_TOKEN})
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0, stdout=stdout,
                           git_status_before=None, git_status_after=None)
        assert not v.accepted

    def test_structured_error_field_on_a_zero_exit_is_refused(self):
        stdout = json.dumps({"error": {"code": "model_unavailable"},
                             "result": R.GROK_PROBE_TOKEN})
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0, stdout=stdout,
                           git_status_before="", git_status_after="")
        assert not v.accepted


# ---------------------------------------------------------------------------------------------
# §16 — credential non-disclosure (§13)
# ---------------------------------------------------------------------------------------------
class TestCredentialIsolation:
    @pytest.mark.parametrize("key", ["XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                                     "GOOGLE_APPLICATION_CREDENTIALS", "GROK_SESSION_TOKEN",
                                     "ANTIGRAVITY_AUTH", "SOME_SECRET", "MY_PASSWORD"])
    def test_credential_keys_are_scrubbed(self, key):
        assert R.is_provider_credential_env_key(key)
        env = R.scrub_provider_env({key: "value", "PATH": "/usr/bin"})
        assert key not in env
        assert env["PATH"] == "/usr/bin"

    @pytest.mark.parametrize("key", ["PATH", "USERPROFILE", "TEMP", "LANG", "HTTPS_PROXY"])
    def test_non_secret_environment_is_preserved(self, key):
        assert not R.is_provider_credential_env_key(key)
        assert key in R.scrub_provider_env({key: "x"})

    @pytest.mark.parametrize("secret", [
        "xai-abcdefghijklmnop1234",
        "AIzaSyA1234567890abcdefghij",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
        "Authorization: Bearer abcdefghijklmnop",
        'access_token": "abcdefghijklmnop"',
    ])
    def test_secret_shaped_material_is_redacted_from_diagnostics(self, secret):
        out = R.redact_diagnostics(f"provider said: {secret}")
        assert secret not in out
        assert "REDACTED" in out

    def test_diagnostics_are_bounded(self):
        assert len(R.redact_diagnostics("x" * 5000)) <= R.MAX_DIAGNOSTIC_CHARS + 20

    def test_no_module_constant_supplies_a_credential(self):
        """The engine may name credential env vars (to scrub them) but must never provide one."""
        for name in dir(R):
            val = getattr(R, name)
            if isinstance(val, str) and name.isupper():
                assert not val.startswith(("xai-", "sk-", "AIza", "eyJ")), name


# ---------------------------------------------------------------------------------------------
# §16 — provider-specific diagnostics + subscription separation + honest registration
# ---------------------------------------------------------------------------------------------
class TestProviderSeparationAndRegistration:
    def test_the_two_providers_never_share_a_subscription_resource(self):
        assert R.GROK_SPEC.subscription_resource != R.ANTIGRAVITY_SPEC.subscription_resource
        assert R.GROK_SPEC.subscription_resource == "grok_build_subscription"
        assert R.ANTIGRAVITY_SPEC.subscription_resource == "google_antigravity_subscription"

    def test_default_terminal_allowance_is_one_per_provider(self):
        assert R.GROK_SPEC.terminal_allowance == 1
        assert R.ANTIGRAVITY_SPEC.terminal_allowance == 1

    def test_display_names_are_the_operator_specified_labels(self):
        assert R.GROK_SPEC.display == "Grok Build"
        assert R.ANTIGRAVITY_SPEC.display == "Gemini · Antigravity"
        assert "Gemini CLI" not in R.ANTIGRAVITY_SPEC.display

    def test_one_providers_failure_never_appears_in_the_others_report(self):
        """§14 — never print one provider's error text for another."""
        runs = {
            "grok": fake_runner({"--version": OK("grok 0.2.118"),
                                 "models": FAIL(1, "", "Grok: not logged in")}),
            "agy": fake_runner({"--version": OK("1.1.9"), "models": OK(AGY_MODELS_OUT)}),
        }
        grok = R.probe_status(R.GROK_SPEC, runs["grok"], check_registration=False,
                              executable="grok")
        agy = R.probe_status(R.ANTIGRAVITY_SPEC, runs["agy"], check_registration=False,
                             executable="agy")
        blob = json.dumps(agy.as_dict())
        assert "Grok" not in blob and "grok" not in blob
        assert grok.state == R.STATE_AUTH_REQUIRED
        assert agy.state == R.STATE_AVAILABLE

    def test_registration_reflects_the_two_sources_and_nothing_else(self):
        """Unconditional, so it can go red. Both source facts are read here independently, and the
        verdict must equal their conjunction — a `provider_registration` mutated to always answer
        REGISTERED fails this, which the earlier `if state == ...` form did not (validator R4).

        When 18B wires the picker, these source facts change and this test follows them
        automatically: it asserts the RELATIONSHIP, not today's answer. (18B `.scope` replaced the
        second source: the frozen-enum check could not pass while U227 was unruled, so it became a
        declared note, asserted separately below. OP-12.1 has since ruled it — `node@1.1` admits
        both ids — and the note is still a note: an admissible vocabulary is not a registration.)"""
        from control_plane.nodes.pane_picker import registered_providers
        from control_plane.profiles.live_authorization import authorized_providers
        for provider in (R.GROK_PROVIDER, R.ANTIGRAVITY_PROVIDER):
            expected_scope = provider in authorized_providers()
            expected_offered = provider in registered_providers()
            state, detail = R.provider_registration(provider)
            assert state == (R.STATE_REGISTERED if (expected_scope and expected_offered)
                             else R.STATE_NOT_REGISTERED), (provider, detail)
            assert ("not offered" in detail) == (not expected_offered)

    def test_the_schema_vocabulary_fact_is_declared_on_every_answer_never_gating(self):
        """The vocabulary fact stays visible on every provider's registration detail — including
        one that IS in the frozen enum, so the note cannot read as special pleading — and it never
        decides the verdict. Since OP-12.1 the fact has three shapes, not two, and the note must
        distinguish them: frozen member, successor member, member of neither."""
        for provider in (R.GROK_PROVIDER, R.ANTIGRAVITY_PROVIDER):
            _state, detail = R.provider_registration(provider)
            assert "NOT in the frozen node@1.0 adapter enum" in detail
            assert "admitted by node@1.1" in detail and "OP-12.1" in detail
        _state, detail = R.provider_registration("claude_code")
        assert "declared: in the frozen node@1.0 adapter enum" in detail
        _state, detail = R.provider_registration("kimi_k3")
        assert "in NO node schema version's adapter enum" in detail

    def test_the_vocabulary_note_agrees_with_the_registry_fence(self):
        """A diagnostic that disagreed with the fence it describes would be worse than none, so the
        note is derived from the fence's own accessor rather than re-reading the schema files."""
        from control_plane.nodes.registry import adapter_version_map
        admitted = adapter_version_map()
        for provider, expected in (("claude_code", "node@1.0"), (R.GROK_PROVIDER, "node@1.1"),
                                   (R.ANTIGRAVITY_PROVIDER, "node@1.1")):
            assert admitted[provider] == expected
            assert expected in R._schema_vocabulary_note(provider)
        assert "kimi_k3" not in admitted

    def test_lease_state_is_not_claimed_before_the_governor_knows_the_resource(self):
        """Also unconditional: the lease wording must track the registration state exactly."""
        run = fake_runner({"--version": OK("1.1.9"), "models": OK(AGY_MODELS_OUT)})
        st = R.probe_status(R.ANTIGRAVITY_SPEC, run, executable="agy")
        expected_registered = st.registration_state == R.STATE_REGISTERED
        assert st.lease_state.startswith("not_registered") is not expected_registered


# ---------------------------------------------------------------------------------------------
# The live probe is gated by the SAME fail-closed switch as every other live path
# ---------------------------------------------------------------------------------------------
@contextmanager
def _stub_session(provider, *, probe_id, workspace, live_auth, executable, profile_loader,
                  operator_terms_confirmed, registrar):
    """A governed session STUB for the acceptance-semantics tests: same call signature as the real
    factory, no ledger, no lease, no host. It creates no node record and says so, so a test can
    never read a stronger claim out of the stub than the product makes.

    The three caller-supplied inputs are REQUIRED here for the same reason they are required on the
    real factory (18C, and `registrar` at 18D `.close`): a stub that accepted `**kwargs` would let
    the caller stop passing them without any test noticing — the stub would silently become the
    only thing that still worked. `registrar` is asserted PRESENT rather than truthy: the product
    call site must hand over a real durable registrar, and `None` here would mean this stub had
    quietly become the last place the argument existed."""
    assert profile_loader is not None and operator_terms_confirmed is True
    assert registrar is not None, "the probe engine must pass a node registrar (18D `.close`)"
    yield SimpleNamespace(
        as_dict=lambda: {"provider": provider, "node_id": f"probe-{probe_id}", "stub": True,
                         "node_registered": False, "node_record": None,
                         "teardown": {"stubbed": True}},
        workspace=str(workspace), executable=executable, spawned_pids=())


class TestLiveProbeGate:
    def test_absent_live_config_denies_the_probe(self, tmp_path):
        allowed, reason = R.live_probe_gate(R.GROK_PROVIDER,
                                            config_path=tmp_path / "nope.json")
        assert allowed is False
        assert reason

    def test_a_valid_live_config_that_does_not_name_the_provider_denies_it(self, tmp_path):
        """The config below is VALID and grants live operation — to claude_code and codex. The
        new providers must still be denied.

        An earlier version of this test used invented key names, so the loader raised on a
        malformed config and the scoped-provider path was never reached: it asserted denial while
        exercising nothing (spec-audit F-13). The shape below is the loader's real one, and the
        first assertion proves the config actually authorizes something."""
        cfg = tmp_path / "live_operation.json"
        cfg.write_text(json.dumps({
            "config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
            "scope": {"providers": ["claude_code", "openai_codex_cli"],
                      "terminals_per_subscription": 2},
        }), encoding="utf-8")
        # the gate really is open for the scoped providers on this very config...
        assert R.live_probe_gate("claude_code", config_path=cfg)[0] is True
        # ...and closed for the two new ones, which is the fact under test
        for provider in (R.GROK_PROVIDER, R.ANTIGRAVITY_PROVIDER):
            allowed, reason = R.live_probe_gate(provider, config_path=cfg)
            assert allowed is False, provider
            assert "DENIED" in reason

    def test_a_malformed_live_config_also_denies(self, tmp_path):
        cfg = tmp_path / "live_operation.json"
        cfg.write_text('{"config_version": "0.9"}', encoding="utf-8")
        assert R.live_probe_gate(R.GROK_PROVIDER, config_path=cfg)[0] is False

    @staticmethod
    def _op6_config(tmp_path: Path) -> Path:
        cfg = tmp_path / "live_operation.json"
        cfg.write_text(json.dumps({
            "config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
            "scope": {"providers": ["claude_code", "openai_codex_cli"],
                      "terminals_per_subscription": 2},
        }), encoding="utf-8")
        return cfg

    def test_the_denial_names_the_step_that_is_ACTUALLY_left(self, tmp_path):
        """18C `.close`. The denial text is the operator's ONE instruction for opening a provider,
        and it was a sentence rather than a reading of the state: it said the config edit is "NOT
        sufficient and NOT safe on its own" and named the 18B scope extension as still to come.
        That was true when U237 was written and false the moment 18B `.scope` shipped the OP-12
        row — so the surface an operator reads when 18C blocks told them a code change was owed
        that had already landed, on the very gate whose entry condition they were trying to meet
        (invariant 1 is about INFORMED final authority).

        The instruction now DERIVES from the code-pinned scope: covered by a recorded row ⇒ the
        remaining step is the operator's own file edit, named with the row; covered by none ⇒ the
        old warning, which is then true."""
        from control_plane.profiles import live_authorization as la

        assert R.GROK_PROVIDER in la.authorized_providers(), (
            "this test's premise is that 18B `.scope` code-pinned the OP-12 providers")
        allowed, reason = R.live_probe_gate(R.GROK_PROVIDER, config_path=self._op6_config(tmp_path))
        assert allowed is False
        assert "DENIED" in reason
        assert "OP-12" in reason, "the denial must name the row that already covers this provider"
        assert "config/live_operation.json" in reason
        assert "NOT sufficient" not in reason, (
            "the denial still tells the operator the config edit is insufficient, which stopped "
            "being true when the code-pinned scope extension shipped at 18B `.scope`")
        assert "18B scope extension" not in reason

    def test_an_absent_or_switched_off_config_does_not_get_the_add_to_the_list_instruction(
            self, tmp_path):
        """spec-audit MEDIUM-5. `is_provider_live` folds the MASTER FLAG in with the scoped set, and
        the loader returns a DENIED authorization — not an exception — for an absent file and for
        `live_operation_authorized: false`. The 18C `.close` instruction is an affirmative one
        ("add it to `scope.providers`"), and in those two worlds it is false: there may be no list,
        and with the flag off adding to one opens nothing. The loader's own reason is what the
        operator needs there."""
        absent = tmp_path / "nowhere" / "live_operation.json"
        off = tmp_path / "live_operation.json"
        off.write_text(json.dumps({
            "config_version": "1.1", "live_operation_authorized": False, "register_row": "OP-12",
            "scope": {"providers": ["claude_code"], "terminals_per_subscription": 1},
        }), encoding="utf-8")
        for cfg in (absent, off):
            allowed, reason = R.live_probe_gate(R.GROK_PROVIDER, config_path=cfg)
            assert allowed is False
            assert "scope.providers" not in reason, (
                f"{cfg.name}: the operator is told to add to a list that will not open anything")
            assert "live_operation.example.json" in reason
            assert "invariant 1" in reason

    def test_a_provider_covered_by_several_rows_gets_no_false_18B_provenance(self, tmp_path):
        """spec-audit MINOR-10. `claude_code` is covered by OP-6 AND OP-12, and has been scoped
        since Phase 15 — so "shipped at 18B `.scope`" is false for it, and "set register_row to that
        row" is unactionable when two are listed. Reachable whenever an operator NARROWS their own
        config."""
        cfg = tmp_path / "live_operation.json"
        cfg.write_text(json.dumps({
            "config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
            "scope": {"providers": ["openai_codex_cli"], "terminals_per_subscription": 2},
        }), encoding="utf-8")
        allowed, reason = R.live_probe_gate("claude_code", config_path=cfg)
        assert allowed is False
        assert "18B" not in reason and "U237" not in reason
        assert "one of register rows" in reason
        # …while the OP-12 pair, whose scope really did arrive at 18B, keeps the provenance
        assert "18B" in R.live_probe_gate(R.GROK_PROVIDER, config_path=cfg)[1]

    def test_a_provider_no_register_row_covers_still_gets_the_code_pinned_warning(self, tmp_path):
        """The other half of the same rule, so the fix above is not simply "delete the warning":
        an id no operator ruling covers cannot be opened by a config edit at all — the loader
        raises on it and would deny every live provider. That warning must survive, for ids it is
        true of."""
        from control_plane.profiles import live_authorization as la

        assert "acme_ai" not in la.authorized_providers()
        allowed, reason = R.live_probe_gate("acme_ai", config_path=self._op6_config(tmp_path))
        assert allowed is False
        assert "code-pinned" in reason
        assert "U237" in reason

    def test_a_denied_gate_spends_nothing(self, tmp_path, monkeypatch):
        def explode(argv):
            raise AssertionError("a denied probe must never invoke the provider CLI")

        monkeypatch.setattr(R, "which_provider", lambda spec: "grok")
        out = R.run_probe(R.GROK_SPEC, runner=explode, config_path=tmp_path / "absent.json")
        assert out["executed"] is False
        assert out["accepted"] is False
        assert out["gate"]["allowed"] is False

    def test_an_allowed_gate_runs_the_probe_and_checks_the_repository(self, monkeypatch):
        # These two tests are about ACCEPTANCE semantics only, so they stub the GOVERNED SESSION as
        # well as the gate: what the probe does with an exit code and two repo snapshots is
        # independent of who leased the terminal. The governed path itself — identity, the I-X3
        # lease taken for exactly the child's lifetime, and its measured release (U234) — is
        # asserted against the REAL session in
        # `tests/unit/test_op12_provider_scope.py::TestAnAllowedGateNowRunsThroughAGovernedSession`
        # and `tests/unit/test_op12_probe_session.py`.
        monkeypatch.setattr(R, "live_probe_gate", lambda p, config_path=None: (True, "test-scoped"))
        monkeypatch.setattr(R, "which_provider", lambda spec: "grok")
        stdout = json.dumps({"result": R.GROK_PROBE_TOKEN})
        calls: list[list[str]] = []

        def run(argv):
            calls.append(list(argv))
            return 0, stdout, "", False, None

        out = R.run_probe(R.GROK_SPEC, runner=run, git_status=lambda: " M x.py\n",
                          open_session=_stub_session)
        assert out["executed"] and out["accepted"]
        assert out["repo_unchanged"] is True
        assert len(calls) == 1 and "--always-approve" not in calls[0]
        # an injected runner never gets the job-object boundary, and the verdict says so
        assert out["supervised_execution"] is False

    def test_a_probe_that_dirties_the_repository_is_refused(self, monkeypatch):
        monkeypatch.setattr(R, "live_probe_gate", lambda p, config_path=None: (True, "test-scoped"))
        monkeypatch.setattr(R, "which_provider", lambda spec: "agy")
        snaps = iter(["", " M new_file.txt\n"])
        out = R.run_probe(R.ANTIGRAVITY_SPEC,
                          runner=lambda a: (0, json.dumps({"result": R.ANTIGRAVITY_PROBE_TOKEN}),
                                            "", False, None),
                          git_status=lambda: next(snaps), open_session=_stub_session)
        assert out["accepted"] is False
        assert "repository state snapshot" in out["reason"]

    def test_a_probe_whose_session_refuses_spends_nothing(self, monkeypatch):
        """The gate said yes; the SESSION said no (a full subscription, unconfirmed terms, an
        unresolvable binary). No child, and the refusing gate is named rather than described."""
        monkeypatch.setattr(R, "live_probe_gate", lambda p, config_path=None: (True, "test-scoped"))
        monkeypatch.setattr(R, "which_provider", lambda spec: "grok")

        @contextmanager
        def refusing(provider, **_kw):
            raise SubscriptionLimitExceeded("subscription at allowance 1")
            yield  # pragma: no cover — unreachable, present so this is a generator function

        out = R.run_probe(R.GROK_SPEC,
                          runner=lambda a: (_ for _ in ()).throw(
                              AssertionError("a refused session must never spawn a child")),
                          open_session=refusing)
        assert out["executed"] is False and out["accepted"] is False
        assert out["gate"]["allowed"] is True          # NOT a gate denial
        assert out["refused_by"] == "SubscriptionLimitExceeded"


class TestTheProbeRecordsTheDocumentItJudged:
    """U305, 18E `.live.shape`. `accepted:false` with `token_seen:false` has two causes that read
    IDENTICALLY in a verdict and opposite in a shape — the model said nothing, or it said it
    somewhere `extract_probe_response_field` does not look. Every probe now carries the structure
    of the document it judged, so a live acceptance leg can never report a reader defect as a
    provider fact."""

    def _probe(self, monkeypatch, stdout):
        monkeypatch.setattr(R, "live_probe_gate", lambda p, config_path=None: (True, "test-scoped"))
        monkeypatch.setattr(R, "which_provider", lambda spec: "grok")
        return R.run_probe(R.GROK_SPEC, runner=lambda a: (0, stdout, "", False, None),
                           git_status=lambda: "", open_session=_stub_session)

    def test_an_accepted_probe_records_the_flat_shape_that_earned_it(self, monkeypatch):
        out = self._probe(monkeypatch, json.dumps({"result": R.GROK_PROBE_TOKEN}))
        assert out["accepted"] is True
        shape = out["document_shape"]
        assert shape["response_key_matched"] == "result"
        assert shape["token_visible_to_strict_reader"] is True
        assert shape["token_paths"] == ["result"]

    def test_a_nested_answer_is_refused_AND_the_shape_says_where_it_was(self, monkeypatch):
        """The exact U305 scenario: a genuine live reply the strict reader cannot see. The refusal
        is the safe direction and stays; what changes is that the evidence names the path, so the
        next act is a reader fix and not a false report about the provider."""
        out = self._probe(monkeypatch,
                          json.dumps({"response": {"text": R.GROK_PROBE_TOKEN}, "status": "done"}))
        assert out["accepted"] is False
        assert "no recognised response field" in out["reason"]
        shape = out["document_shape"]
        assert shape["token_paths"] == ["response.text"]
        assert shape["token_visible_to_strict_reader"] is False

    def test_the_shape_carries_no_value_from_the_document(self, monkeypatch):
        """The shape is published as evidence; §2.2/§13 means it may carry names, never contents."""
        out = self._probe(monkeypatch,
                          json.dumps({"result": R.GROK_PROBE_TOKEN, "who": "sow-value-sentinel"}))
        assert "sow-value-sentinel" not in json.dumps(out["document_shape"])
        assert "who" in out["document_shape"]["top_level_keys"]


# ---------------------------------------------------------------------------------------------
# Regressions found by the Phase 18A reviewers. Each of these was a live defect in the first
# implementation; each assertion below fails if the defect returns.
# ---------------------------------------------------------------------------------------------
class TestReviewerFoundDefects:
    def test_registration_fails_closed_when_neither_source_can_be_read(self, monkeypatch):
        """spec-audit F-1: two unreadable sources used to produce REGISTERED — a fail-OPEN verdict
        claiming a lease no governor holds."""
        import builtins
        real_import = builtins.__import__

        def blow_up(name, *a, **kw):
            if "live_authorization" in name:
                raise ImportError("simulated: module unreadable")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", blow_up)
        monkeypatch.setattr(R, "REPO_ROOT", R.Path("/definitely/not/a/repo"))
        state, detail = R.provider_registration(R.GROK_PROVIDER)
        assert state == R.STATE_NOT_REGISTERED
        assert "unverifiable" in detail

    def test_available_on_unverified_auth_is_not_auth_confirmed(self):
        """spec-audit F-2: AVAILABLE was the runner's only launch gate, and it was granted to a
        provider whose authentication nothing had checked."""
        run = fake_runner({"--version": OK("1.1.9"), "models": OK(AGY_MODELS_OUT)})
        st = R.probe_status(R.ANTIGRAVITY_SPEC, run, check_registration=False, executable="agy")
        assert st.state == R.STATE_AVAILABLE
        assert st.auth_confirmed is False
        assert "UNVERIFIED" in st.state_caveat
        assert st.as_dict()["state_caveat"]      # and it survives serialisation to the runner

    def test_authenticated_provider_is_auth_confirmed_with_no_caveat(self):
        run = fake_runner({"--version": OK("grok 0.2.118"), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, check_registration=False, executable="grok")
        assert st.auth_confirmed is True
        assert st.state_caveat == ""

    @pytest.mark.parametrize("builder,flag,mode", [
        (R.build_grok_probe_command, "--permission-mode", R.GROK_PROBE_PERMISSION_MODE),
        (R.build_antigravity_probe_command, "--mode", R.ANTIGRAVITY_PROBE_MODE),
    ])
    def test_every_probe_pins_its_mode_explicitly(self, builder, flag, mode):
        """spec-audit F-3: the probe relied on the ABSENCE of --always-approve and called that
        containment. It now passes an explicit mode from each CLI's own help, so a node-controlled
        config file cannot supply a permissive default instead.

        Both values were challenged on live evidence at 18E `.live.shape` and both stayed `plan`
        (U310) — so the literal is still pinned. What the guard assertions add is the property
        behind it: whatever the pinned value is, it must be one this build is permitted to emit at
        all, which is the half that would still hold if a later measurement did move one."""
        argv = builder()
        assert flag in argv
        assert argv[argv.index(flag) + 1] == mode == "plan"
        assert mode not in R._FORBIDDEN_PERMISSION_MODES
        R._assert_no_forbidden(argv)

    @pytest.mark.parametrize("argv", [
        ["grok", "--permission-mode", "acceptEdits"],
        ["agy", "--mode", "accept-edits"],
        ["grok", "--allow", "Bash(*)"],
        ["grok", "--allowedTools", "Bash"],
        ["grok", "--tools", "bash,edit"],
    ])
    def test_tool_widening_arguments_are_refused(self, argv):
        """spec-audit F-4: acceptEdits and the allow-list flags were missing from the guard, so a
        command that auto-approves edits passed the 'structural' check."""
        with pytest.raises(ValueError):
            R._assert_no_forbidden(argv)

    @pytest.mark.parametrize("doc, expected_reason", [
        # An EMPTY response field with the prompt beside it. Under 18E this refuses for the more
        # precise of the two reasons: there is no response, so there is nothing to have echoed.
        ({"result": "", "prompt": f"Reply with exactly: {R.GROK_PROBE_TOKEN}"},
         "no recognised response field"),
        ({"result": f"Reply with exactly: {R.GROK_PROBE_TOKEN}"}, "prompt echo"),
        ({"result": "I cannot comply.",
          "request": {"prompt": f"Reply with exactly: {R.GROK_PROBE_TOKEN}"}}, "prompt echo"),
    ])
    def test_a_prompt_echo_is_not_an_answer(self, doc, expected_reason):
        """gate-validator R5: the probe prompt CONTAINS the token, so searching the transcript
        accepted a CLI that echoed the request and answered nothing.

        Still refused, all three. The assertion gained a per-case expected reason at 18E because
        the refusal now distinguishes "the CLI answered the wrong thing" from "the CLI's document
        has no response field at all" — see TestU238AcceptanceReadsAResponseFieldOrNothing. The
        REFUSAL this test was written to pin is unchanged; only its explanation got sharper."""
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps(doc),
                           git_status_before="x", git_status_after="x")
        assert not v.accepted, doc
        assert expected_reason in v.reason, v.reason

    def test_a_real_answer_is_still_accepted(self):
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": R.GROK_PROBE_TOKEN}),
                           git_status_before="x", git_status_after="x")
        assert v.accepted

    def test_the_repo_snapshot_covers_the_gitignored_live_switch(self, tmp_path, monkeypatch):
        """spec-audit F-5: `git status --short` does not report ignored files, and the live
        switch — the file that decides whether any live call may happen — is gitignored."""
        cfg = tmp_path / "config" / "live_operation.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text('{"a": 1}', encoding="utf-8")

        class FakeProc:
            returncode = 0
            stdout = " M x.py\n"

        monkeypatch.setattr(R.subprocess, "run", lambda *a, **kw: FakeProc())
        before = R._repo_state_snapshot(tmp_path)
        cfg.write_text('{"a": 2}', encoding="utf-8")
        after = R._repo_state_snapshot(tmp_path)
        assert before is not None and before != after

    @pytest.mark.parametrize("blank", [" ", "\n", "\t\n  "])
    def test_whitespace_only_version_output_does_not_raise(self, blank):
        """spec-audit F-7: `.strip().splitlines()[0]` raised IndexError out of a function whose
        contract is 'never raises'."""
        run = fake_runner({"--version": OK(blank), "models": OK(AGY_MODELS_OUT)})
        st = R.probe_status(R.ANTIGRAVITY_SPEC, run, check_registration=False, executable="agy")
        assert st.state == R.STATE_UNSUPPORTED_VERSION

    def test_an_airgapped_profile_contacts_no_frontier_cli(self, monkeypatch):
        """spec-audit F-8 / invariant 20: `<cli> models` may reach the provider's service, so an
        air-gapped profile must not run it at all."""
        monkeypatch.setenv(R._PROFILE_ENV, R._AIRGAP_PROFILE)

        def explode(argv):
            raise AssertionError("no provider CLI may be invoked under an air-gapped profile")

        st = R.probe_status(R.GROK_SPEC, explode, check_registration=False, executable="grok")
        assert st.state == R.STATE_PROBE_FAILED
        assert "air-gapped" in st.auth_detail

    @pytest.mark.parametrize("flag", ["--dangerously-skip-permissions", "--xai-api-base-url",
                                      "--sandbox", "--allowedTools"])
    def test_redaction_does_not_corrupt_the_command_surface_it_cites(self, flag):
        """gate-validator R1 / spec-audit F-10: the key-like pattern matched `sk` inside
        `--dangerously-skip-permissions`, mangling the help capture this module calls its
        authority — and mangling exactly the flag an auditor most needs to read."""
        text = f"  {flag}   Auto-approve all tool executions"
        assert flag in R.redact_diagnostics(text)

    def test_real_keys_are_still_redacted(self):
        for secret in ("xai-abcdefghijklmnopqrst", "sk-abcdefghijklmnopqrst",
                       "AIzaSyA1234567890abcdefghij"):
            assert secret not in R.redact_diagnostics(f"leaked {secret} here")

    @pytest.mark.parametrize("line,expected", [
        ("You are logged in with grok.com.", "grok.com"),
        ("You are logged in with sam@example.com.", None),      # an identity is withheld
        ("You are logged in with someone.", None),              # not service-shaped
    ])
    def test_account_hint_records_a_service_never_an_identity(self, line, expected):
        """spec-audit F-11: the field's comment promised 'never an identity' and the regex
        captured any bare token, so an email would have flowed into committed evidence."""
        inv = R.parse_grok_models(f"{line}\nAvailable models:\n  * grok-4.5\n")
        assert inv.login_reported is True
        assert inv.account_hint == expected

    @pytest.mark.parametrize("stdout", [
        "You are logged in with grok.com.\nAvailable models:\n  * none configured\n",
        "You are logged in with grok.com.\n  - Error: could not reach the model service\n",
        "  * grok-4.5 (default)\n",                    # bullets outside the section: no header
        "Available models:\n  - Note that models refresh hourly\n",
    ])
    def test_grok_prose_is_never_read_as_a_model(self, stdout):
        """gate-validator R3 / spec-audit F-14: `  * none configured` yielded the model `none`
        and `  - Error: could not reach…` yielded `Error:`, both with parse_note 'ok'."""
        inv = R.parse_grok_models(stdout)
        assert inv.models == (), inv
        assert "fail closed" in inv.parse_note

    def test_the_real_host_output_still_parses(self):
        """The guard must reject prose without rejecting the actual CLI output it was written
        for — the recorded capture from this host."""
        inv = R.parse_grok_models(GROK_MODELS_OUT)
        assert inv.models == ("grok-4.5",)


# ---------------------------------------------------------------------------------------------
# Second review round. The first remediation was itself reviewed twice; these are the defects
# that survived it.
# ---------------------------------------------------------------------------------------------
class TestSecondRoundDefects:
    def test_the_scrubber_does_not_strip_the_grok_sandbox_lever(self):
        """spec-audit N-1: `GROK_SANDBOX` is the env form of `grok --sandbox <PROFILE>` — the only
        filesystem/network containment lever this CLI exposes. The GROK_ prefix rule deleted it,
        so a scrubber written for safety silently removed the sandbox."""
        assert R.is_provider_credential_env_key("GROK_SANDBOX") is False
        env = R.scrub_provider_env({"GROK_SANDBOX": "read-only", "XAI_API_KEY": "secret"})
        assert env["GROK_SANDBOX"] == "read-only"
        assert "XAI_API_KEY" not in env

    @pytest.mark.parametrize("key", ["GROK_API_KEY", "GROK_SESSION_TOKEN", "XAI_API_KEY"])
    def test_real_provider_secrets_are_still_stripped(self, key):
        assert R.is_provider_credential_env_key(key) is True

    @pytest.mark.parametrize("echo", [
        "Reply with exactly:\n GROK_PROVIDER_OK",          # re-wrapped
        "reply with exactly: GROK_PROVIDER_OK",            # re-cased
        "Reply  with   exactly:  GROK_PROVIDER_OK",        # re-spaced
        "  Reply with exactly: GROK_PROVIDER_OK  ",        # padded
    ])
    def test_a_normalised_prompt_echo_is_still_not_an_answer(self, echo):
        """gate-validator F1 / spec-audit N-8: exact-substring removal was defeated by any
        re-wrap, re-case or re-space of the echoed prompt."""
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": echo}),
                           git_status_before="x", git_status_after="x")
        assert not v.accepted, echo

    @pytest.mark.parametrize("answer", [
        "GROK_PROVIDER_OK",
        "GROK_PROVIDER_OK.",
        "Sure — GROK_PROVIDER_OK",
    ])
    def test_a_real_answer_survives_the_stricter_check(self, answer):
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": answer}),
                           git_status_before="x", git_status_after="x")
        assert v.accepted, answer

    def test_a_degenerate_operator_prompt_still_accepts_the_token(self):
        """If the operator's own -Prompt is nothing but the token, subtracting it would erase a
        genuine answer; that case requires the token and says so."""
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": R.GROK_PROBE_TOKEN}),
                           prompt=R.GROK_PROBE_TOKEN,
                           git_status_before="x", git_status_after="x")
        assert v.accepted

    @pytest.mark.parametrize("argv", [
        ["grok", "--permission-mode=bypassPermissions"],
        ["grok", "--allowedTools=Bash"],
        ["agy", "--dangerously-skip-permissions=1"],
        ["agy", "--mode=accept-edits"],
    ])
    def test_equals_joined_arguments_do_not_bypass_the_guard(self, argv):
        """gate-validator F2 / spec-audit N-9: both CLIs accept `--flag=value`, and the guard only
        matched whole tokens — so the auto-approving form walked straight through."""
        with pytest.raises(ValueError):
            R._assert_no_forbidden(argv)

    def test_equals_joined_benign_arguments_are_still_allowed(self):
        R._assert_no_forbidden(["grok", "--permission-mode=plan", "--model=grok-4.5"])

    @pytest.mark.parametrize("entry", ["build_recon", "run_probe", "probe_status"])
    def test_no_path_contacts_a_provider_under_an_airgapped_profile(self, entry, monkeypatch):
        """spec-audit N-3: the guard lived in `probe_status` alone while the module claimed no
        frontier CLI was contacted at all — `recon` (which produced the committed evidence) and
        `probe` (which spends money) both bypassed it."""
        monkeypatch.setenv(R._PROFILE_ENV, R._AIRGAP_PROFILE)
        monkeypatch.setattr(R, "which_provider", lambda spec: "grok")
        monkeypatch.setattr(R, "live_probe_gate", lambda p, config_path=None: (True, "test"))

        def explode(argv):
            raise AssertionError(f"{entry} invoked a provider CLI under an air-gapped profile")

        if entry == "build_recon":
            R.build_recon("grok", runner=explode)
        elif entry == "run_probe":
            out = R.run_probe(R.GROK_SPEC, runner=explode, git_status=lambda: "x")
            assert out["accepted"] is False
        else:
            R.probe_status(R.GROK_SPEC, explode, check_registration=False, executable="grok")

    @pytest.mark.parametrize("profile,expected", [
        ("cloud", False), ("hybrid", False), ("offline_airgapped", True), ("banana", True),
    ])
    def test_an_unknown_profile_id_fails_closed(self, profile, expected, monkeypatch):
        monkeypatch.setenv(R._PROFILE_ENV, profile)
        assert R.airgapped() is expected

    def test_the_airgap_refusal_is_labelled_as_policy_not_a_provider_fault(self, monkeypatch):
        monkeypatch.setenv(R._PROFILE_ENV, R._AIRGAP_PROFILE)
        st = R.probe_status(R.GROK_SPEC, lambda argv: OK(), check_registration=False,
                            executable="grok")
        assert "REFUSED" in st.state_caveat        # spec-audit N-13

    def test_authorization_prose_is_not_destroyed_by_the_redactor(self):
        """spec-audit N-12 / F5: `authorization required, run \\`grok login\\`` — the exact
        AUTH_REQUIRED diagnostic an auditor needs — was replaced wholesale."""
        text = "Error: authorization required, run `grok login` to continue"
        assert "authorization required" in R.redact_diagnostics(text)

    def test_a_real_authorization_header_is_still_redacted(self):
        out = R.redact_diagnostics("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")
        assert "abcdefghijklmnopqrstuvwxyz012345" not in out

    def test_a_lone_default_line_is_not_an_inventory(self):
        """spec-audit N-15: the default was promoted into `models` even when no listing existed,
        yielding a one-entry inventory with parse_note 'ok'."""
        inv = R.parse_grok_models("You are logged in with grok.com.\nDefault model: grok-4.5\n")
        assert inv.models == ()
        assert inv.default_model == "grok-4.5"
        assert "fail closed" in inv.parse_note

    def test_auth_confirmed_is_named_for_what_it_measures(self):
        """spec-audit N-5: the field was called `launch_ready` while the same object reported
        NOT_REGISTERED, no lease, and a live gate that DENIES the provider.

        18B `.picker` registered both providers, so `registration_state` now reads REGISTERED — and
        the point of the finding survives the change intact, because that is exactly what the field
        was renamed to stop implying. A signed-in, registered provider is STILL not launch-ready:
        the live switch may deny it, no lease is held, and the assertions below say so."""
        run = fake_runner({"--version": OK("grok 0.2.118"), "models": OK(GROK_MODELS_OUT)})
        st = R.probe_status(R.GROK_SPEC, run, executable="grok")
        d = st.as_dict()
        assert "launch_ready" not in d
        assert d["auth_confirmed"] is True
        assert d["registration_state"] == R.STATE_REGISTERED
        # registered ≠ launchable: no terminal is held, and the lease line still says so IN THOSE
        # WORDS. A "registered" that a reader could hear as "a terminal is held" is the same
        # over-claim `launch_ready` was renamed to remove.
        assert "none held here" in d["lease_state"]
        assert "reads no lease ledger" in d["lease_state"]


class TestFourthRoundDefects:
    """Round-4 review. The class both reviewers kept finding: prose that cannot disagree with the
    code it describes. These are the surfaces where the round-3 sweep stopped short."""

    def test_the_cli_help_does_not_call_a_billable_tool_diagnostic_only(self, capsys):
        """Round-4 spec-audit finding 3: the module docstring records that "diagnostic only"
        stopped being true the moment the probe path landed — and the phrase was still in the
        `--help` string, which is the one surface an operator reads BEFORE running the tool
        (invariant 1: an authority decision made on a false description of the command)."""
        with pytest.raises(SystemExit):
            R.main(["--help"])
        help_text = capsys.readouterr().out
        head = help_text.split("options:")[0].lower()
        assert "diagnostic only" not in head
        assert "probe" in head and "live" in head, (
            "the help must say that --action probe spends a live call")


# ---------------------------------------------------------------------------------------------
# Report shape + selector validation
# ---------------------------------------------------------------------------------------------
class TestReport:
    def test_selector_validation(self):
        assert len(R.resolve_selection("all")) == 2
        assert R.resolve_selection("grok")[0].provider == R.GROK_PROVIDER
        assert R.resolve_selection("gemini")[0].provider == R.ANTIGRAVITY_PROVIDER
        with pytest.raises(ValueError):
            R.resolve_selection("openai")

    def test_report_carries_every_directive_6_field(self, monkeypatch):
        monkeypatch.setattr(R, "which_provider", lambda spec: None)
        report = R.build_report("all", check_registration=False)
        required = {"provider", "display", "command_found", "executable", "version", "state",
                    "auth_state", "models", "headless_supported", "interactive_supported",
                    "structured_output_supported", "lease_state", "registration_state"}
        for entry in report["providers"]:
            assert required <= set(entry)
            assert entry["state"] in R.PROVIDER_STATES

    def test_report_records_the_command_surface_deltas(self):
        deltas = {(d["provider"], d["directive"]) for d in R.RECORDED_FLAG_DELTAS}
        assert (R.GROK_PROVIDER, "§7.1/§10 `--no-auto-update`") in deltas

    def test_the_credential_claim_names_evidence_that_actually_exists(self, monkeypatch):
        """Round-4 spec-audit finding 9: the old assertion was `reads_credentials is False`
        against a literal `False` — a constant checked against itself, which is the very shape
        round 3 condemned in the auth gloss. The field now says it is a DESIGN property and
        carries the tests that enforce it, and *that* is falsifiable: rename or delete either
        test and this goes red, so the recorded claim cannot outlive its evidence."""
        import pathlib

        monkeypatch.setattr(R, "which_provider", lambda spec: None)
        policy = R.build_report("all", check_registration=False)["credential_policy"]
        assert policy["reads_credentials_by_design"] is False
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        assert policy["claim_basis"]["enforced_by"], "a claim with no named evidence is prose"
        for ref in policy["claim_basis"]["enforced_by"]:
            path, _, node = ref.partition("::")
            source = (repo_root / path).read_text(encoding="utf-8")
            for name in node.split("::"):
                assert f"class {name}" in source or f"def {name}" in source, (
                    f"{ref} names {name!r}, which does not exist in {path}")

    def test_the_recorded_credential_policy_is_the_whole_policy(self, monkeypatch):
        """Round-3 spec-audit MINOR-13: the artifact recorded the nine exact keys and neither the
        prefix/substring net nor the PRESERVE list — and the preserve list is the entire substance
        of N-1 (`GROK_SANDBOX`, the CLI's only containment lever). Evidence that omits the
        exception cannot be checked against the code, so the exception is recorded too."""
        monkeypatch.setattr(R, "which_provider", lambda spec: None)
        policy = R.build_report("all", check_registration=False)["credential_policy"]
        assert set(policy["scrubbed_key_prefixes"]) == set(R._CREDENTIAL_KEY_PREFIXES)
        assert set(policy["scrubbed_key_substrings"]) == set(R._CREDENTIAL_KEY_SUBSTRINGS)
        assert "GROK_SANDBOX" in policy["preserved_non_secret_config_keys"]
        assert (set(policy["preserved_non_secret_config_keys"])
                == set(R._PRESERVED_PROVIDER_CONFIG_KEYS))


# ---------------------------------------------------------------------------------------------
# U238 — the two probe-acceptance holes, closed at 18E BEFORE the live legs run
#
# Directive §17.2(2): "Close U238 ... BEFORE the live legs run, so the live verdict cannot rest on
# either hole". Each of the twelve shapes the two REFUSAL parametrisations below assert on was
# MEASURED as ACCEPTED on the pre-fix tree — six pure echoes and six documents in which no
# recognised response field carries the token — i.e. twelve ways a CLI that answered NOTHING could
# have certified a live provider. The before/after transcript, and the script that produced it, are
# reproduced in `docs/evidence/PHASE18E_HARDENING_CHECKPOINT.md`; the permanent guard is
# `tools/mutation/_op18e_hardening_mutations.py` (H1-H4), not that transcript.
#
# The other parametrisations here are the two controls that keep the fix from being a blunt one:
# shapes the OLD fold already refused (which must stay refused) and genuine answers (which were
# accepted before and must stay accepted). Those were measured too, and are in the same transcript.
# ---------------------------------------------------------------------------------------------
class TestU238EchoNormalisation:
    """Hole 1: the echo fold was whitespace-collapse + casefold, so a WHITESPACE-DELETING or
    punctuation-differing echo left the prompt unmatched and the token intact."""

    @staticmethod
    def _verdict(result_text: str, token: str = R.GROK_PROBE_TOKEN):
        return R.accept_probe(R.GROK_PROVIDER, token, exit_code=0,
                              stdout=json.dumps({"result": result_text}),
                              git_status_before="x", git_status_after="x")

    @pytest.mark.parametrize("echo", [
        "Reply with exactly:" + R.GROK_PROBE_TOKEN,                    # the space DELETED
        "Reply with exactly - " + R.GROK_PROBE_TOKEN,                  # colon swapped for a dash
        "Reply-with-exactly: " + R.GROK_PROBE_TOKEN,                   # spaces swapped for hyphens
        "Reply with exactly:  ->  " + R.GROK_PROBE_TOKEN,              # an arrow inserted
        "**Reply with exactly:** " + R.GROK_PROBE_TOKEN,               # markdown-emphasised
        "R e p l y  w i t h  e x a c t l y :  " + R.GROK_PROBE_TOKEN,  # letter-spaced instruction
    ])
    def test_a_punctuation_or_whitespace_deleting_echo_is_not_an_answer(self, echo):
        v = self._verdict(echo)
        assert not v.accepted, echo
        assert "prompt echo" in v.reason

    @pytest.mark.parametrize("echo", [
        "Reply with exactly:\n " + R.GROK_PROBE_TOKEN,
        "reply with exactly: " + R.GROK_PROBE_TOKEN,
        "Reply  with   exactly:  " + R.GROK_PROBE_TOKEN,
        "  Reply with exactly: " + R.GROK_PROBE_TOKEN + "  ",
        '"Reply with exactly: ' + R.GROK_PROBE_TOKEN + '"',
    ])
    def test_the_echoes_already_caught_stay_caught(self, echo):
        """The stricter fold must not be a REPLACEMENT that loses ground the old one held."""
        assert not self._verdict(echo).accepted, echo

    @pytest.mark.parametrize("answer", [
        R.GROK_PROBE_TOKEN,
        R.GROK_PROBE_TOKEN + ".",
        "Sure - " + R.GROK_PROBE_TOKEN,
        R.GROK_PROBE_TOKEN + "\n",
        "Done. " + R.GROK_PROBE_TOKEN + " (as requested)",
        # A real answer that RESTATES the instruction and then answers is still an answer: the
        # subtraction removes the restatement and the token survives it.
        ("Reply with exactly: " + R.GROK_PROBE_TOKEN + " - and here it is: " + R.GROK_PROBE_TOKEN),
    ])
    def test_a_genuine_answer_survives_the_stricter_fold(self, answer):
        assert self._verdict(answer).accepted, answer

    def test_the_token_must_still_appear_verbatim_not_only_after_punctuation_folding(self):
        """The alnum fold is for SUBTRACTING the echo, never for recognising the token: §17
        requires the exact token, and `GROK-PROVIDER-OK` is not it."""
        assert not self._verdict("GROK-PROVIDER-OK").accepted

    def test_the_presence_check_is_case_insensitive_and_that_is_pinned_not_assumed(self):
        """The honest limit of "exactly", pinned so nobody has to read the fold to learn it.

        `norm` case-folds, so a lower-case token passes. That is PRE-EXISTING and 18E deliberately
        did not change it — moving presence onto a stricter fold is what mutation H8 exists to
        forbid. It is recorded here as a fact rather than left as a gap between the word "exactly"
        in §17 and the code, so that if a future unit decides §17 means byte-exact, this test is the
        thing that goes red and tells it what it is changing."""
        assert self._verdict("grok_provider_ok").accepted
        assert self._verdict("Grok_Provider_OK").accepted
        # …but case-insensitivity is the ONLY latitude: the underscores are still structural.
        assert not self._verdict("GROKPROVIDEROK").accepted

    def test_a_paraphrased_echo_is_a_known_narrower_hole_u294(self):
        """U304, recorded rather than claimed closed (gate-validator MINOR-2).

        The subtraction removes a CONTIGUOUS occurrence of the folded prompt, so an echo that
        inserts a word into the instruction survives it. This test asserts the CURRENT behaviour so
        the register row and the code cannot drift apart: if a later unit closes U304, this test is
        where it announces itself."""
        paraphrase = "Reply with exactly the following: " + R.GROK_PROBE_TOKEN
        assert self._verdict(paraphrase).accepted, (
            "U304 appears to be closed - update the register row and this test together")

    def test_an_empty_prompt_has_nothing_to_subtract_and_does_not_erase_the_answer(self):
        """A prompt that normalises to nothing must not make `str.replace` shred the response."""
        v = R.accept_probe(R.GROK_PROVIDER, R.GROK_PROBE_TOKEN, exit_code=0,
                           stdout=json.dumps({"result": R.GROK_PROBE_TOKEN}), prompt="   ...   ",
                           git_status_before="x", git_status_after="x")
        assert v.accepted


class TestU238AcceptanceReadsAResponseFieldOrNothing:
    """Hole 2: `extract_probe_text` fell back to `json.dumps(doc)` when no recognised response key
    was present, so the token counted wherever it appeared in the document."""

    @staticmethod
    def _verdict(doc: object, token: str = R.GROK_PROBE_TOKEN):
        return R.accept_probe(R.GROK_PROVIDER, token, exit_code=0, stdout=json.dumps(doc),
                              git_status_before="x", git_status_after="x")

    @pytest.mark.parametrize("doc", [
        {"status": "done", "debug": R.GROK_PROBE_TOKEN},
        # The token as the document's ONLY string value, under a key that is not a response field.
        # Without this case a reader that scanned `doc.values()` instead of the recognised keys
        # passed every other fixture here, because each has an earlier string for it to return
        # (mutation H4 went GREEN and said so).
        {"debug": R.GROK_PROBE_TOKEN},
        {"foo": {"bar": R.GROK_PROBE_TOKEN}},
        {"trace": [R.GROK_PROBE_TOKEN]},
        {"result": None, "echoed_argv": ["grok", "-p", R.GROK_PROBE_TOKEN]},
        {"metadata": {"probe_token": R.GROK_PROBE_TOKEN}, "result": ""},
    ])
    def test_a_token_outside_a_recognised_response_field_is_not_an_answer(self, doc):
        v = self._verdict(doc)
        assert not v.accepted, doc
        assert "no recognised response field" in v.reason, v.reason

    def test_the_two_ways_to_fail_this_condition_are_reported_differently(self):
        """The refusal has to say WHICH thing went wrong. Both of these refuse for "the model did
        not answer", but one is a CLI that said the wrong thing and one is a CLI whose document has
        no field for it to have said anything in — and in the second the token IS in the transcript,
        so "a prompt echo does not count" would send a reader looking for an echo that is not there.
        """
        echo = self._verdict({"result": "Reply with exactly: " + R.GROK_PROBE_TOKEN})
        no_field = self._verdict({"status": "done", "debug": R.GROK_PROBE_TOKEN})
        assert not echo.accepted and not no_field.accepted
        assert "prompt echo" in echo.reason and "no recognised response field" not in echo.reason
        assert "no recognised response field" in no_field.reason
        assert "prompt echo" not in no_field.reason
        # and the field set is named, because "recognised" is useless without the list
        for key in ("result", "response", "text", "content", "message", "output"):
            assert key in no_field.reason

    @pytest.mark.parametrize("key", ["result", "response", "text", "content", "message", "output"])
    def test_every_recognised_response_field_still_certifies(self, key):
        assert self._verdict({key: R.GROK_PROBE_TOKEN}).accepted, key

    def test_a_bare_json_string_document_is_the_response(self):
        """`json.dumps("TOKEN")` is structured output whose whole document IS the answer."""
        assert self._verdict(R.GROK_PROBE_TOKEN).accepted

    def test_the_strict_reader_is_not_the_display_reader(self):
        """`extract_provider_text` stays best-effort — the worker adapter and the recon report's
        `response_excerpt` must keep showing an operator whatever the CLI said. Only ACCEPTANCE is
        strict, and the two readers are separate functions so neither can be tightened or loosened
        by accident."""
        doc = json.dumps({"status": "done", "debug": R.GROK_PROBE_TOKEN})
        assert R.GROK_PROBE_TOKEN in R.extract_probe_text(doc)
        assert R.extract_probe_response_field(doc) == ""

    def test_unstructured_output_yields_no_response_field(self):
        """Acceptance already requires the document to parse (condition 2); the strict reader
        agrees with that rather than quietly reading a raw transcript as a response."""
        assert R.extract_probe_response_field("plain text " + R.GROK_PROBE_TOKEN) == ""
