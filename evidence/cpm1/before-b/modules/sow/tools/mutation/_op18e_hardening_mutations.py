"""Mutation runner for Phase 18E `.hardening` — the two U238 probe-acceptance holes and the two
gate inputs the pane/worker emitter used to answer for itself.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges.

This harness matters more than most, because most mutations below RESTORE A SHIPPED BEHAVIOUR:
the `new` string is not an invented defect, it is the code that was on the tree when the operator
armed 18E, and directive §17.2(2) requires both acceptance holes closed BEFORE the first live leg.
If any row here goes GREEN, the closure is decorative.

Three rows are NOT restorations and say so at their own entries: H6 is signature-only (see below),
H9 tests something 18E ADDED, and H10 tests an ordering that never existed before 18E.

  * H1  the echo subtraction runs on the whitespace fold again — six measured shapes of pure echo
        (`Reply with exactly:GROK_PROVIDER_OK`, a dash for the colon, markdown emphasis, a
        letter-spaced instruction …) certify a provider that answered nothing;
  * H2  acceptance reads the BEST-EFFORT extractor again, whose whole-document fallback lets a
        token in any field at all — `{"status":"done","debug":"GROK_PROVIDER_OK"}` — pass;
  * H3  the strict reader grows the same fallback, which is H2 by the other route (the shared
        accessor rather than its caller);
  * H4  the strict reader stops being strict about the KEY, so any string value certifies;
  * H5  `operator_terms_confirmed` becomes a defaulted keyword again — a parameter default
        published as a measured gate (U98's shape; U292(a));
  * H6  `profile_loader` becomes a defaulted keyword again — SIGNATURE ONLY, and that is the honest
        description (spec-audit F5): with `main()` still passing a loader, restoring the body's
        `ProfileLoader(DeploymentProfile("cloud"))` fallback would change no runtime behaviour and
        the row would prove nothing about reachability. H6 pins the SIGNATURE (U91/U283's shape,
        closed at 18C `.probe-path` on the probe surface); H7 is the row that tests the air-gap
        reachability, at the call site where it can actually be defeated;
  * H7  `main()` keeps the required keyword but hands it a manufactured `cloud` loader instead of
        the host's — the closure defeated at the ONE call site that matters, which a signature
        test alone would never see;
  * H8  the token PRESENCE check moves onto the destructive fold, so `GROK-PROVIDER-OK` reads as
        the exact token §17 requires. The strictness added for H1 must not leak into recognition;
  * H9  the two refusal reasons collapse into one, so a document with no response field is reported
        as a prompt echo. The verdict is right and the explanation is wrong, which is the kind of
        defect a green suite keeps;
  * H10 the air-gap gate goes back BEHIND the host enumeration — the ordering spec-audit F2 found.
        The refusal is unchanged and the test that only asserts `refused_by` stays green; what goes
        red is the leg that asserts the enumeration was never reached, because for an OP-12 provider
        that enumeration is an outbound `models` call made to verify a pane invariant 20 forbids
        opening (U303).

Run from the repo root:  py -3.12 tools/mutation/_op18e_hardening_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

RECON = "tools/providers/frontier_provider_recon.py"
COMMON = "adapters/frontier/provider_cli_common.py"
EMITTER = "tools/live/emit_worker_launch.py"

U238_ECHO = "tests/unit/test_frontier_provider_recon.py::TestU238EchoNormalisation"
U238_FIELD = "tests/unit/test_frontier_provider_recon.py::TestU238AcceptanceReadsAResponseFieldOrNothing"
GATE_INPUTS = "tests/unit/test_worker_emitter_gate_inputs.py"
#: W-44 grader. The antigravity listing parser is the one place a provider's PROSE could become a
#: model id the picker offers as `verified: True`, so both directions of its repair are graded here.
AGY_MODELS = "tests/unit/test_frontier_provider_recon.py::TestModelEnumeration"
#: W-46 grader. The grok login line is the ONLY offline auth evidence this build has, so a mutation
#: that widens it back to a substring search must be caught by the conditional-prose rows.
GROK_AUTH = "tests/unit/test_frontier_provider_recon.py::TestAuthenticationClassification"
#: W-47 grader. `adapters/frontier/codex.py` was anchored by NO harness before this unit -- verified
#: by grep, not assumed -- so the codex auth classifier had no falsification at all.
CODEX = "adapters/frontier/codex.py"
CODEX_AUTH = "tests/unit/test_codex_detect.py"
#: W-48 grader. The node-wide pause path lives on the backend, tested in its own module.
CODEX_BACKEND = "tests/unit/test_frontier_codex.py"
#: W-49 grader. The two probes are now ONE implementation, so a mutation to it must be caught by
#: the AGREEMENT tests -- which is the property R-08 actually asks for.
TWO_PROBES = "tests/unit/test_frontier_provider_recon.py::TestTheTwoProbesAgree"
#: W-50 grader. The live generate path and its verdict-consumption property.
BACKEND = "tests/unit/test_op12_frontier_adapters.py::TestBackendBehaviour"
#: W-52 grader. The version reader is pinned BETWEEN its two failure modes, so each row must be
#: caught by a test the other row leaves green.
VERSION = "tests/unit/test_frontier_provider_recon.py::TestDiscoveryAndVersion"
#: W-53 grader. The decoding-parity proof, kept LIVE rather than left as a one-off calibration.
DECODE_PARITY = "tests/unit/test_provider_decoding_parity.py"
#: W-54 grader. The argv guard, pinned between "refuses legitimate values" and "stops refusing
#: smuggled flags" -- two rows, two graders, neither able to pass for the other.
ARGV_GUARD = "tests/unit/test_op12_frontier_adapters.py::TestArgvGuard"
#: TIER-4 BOUNDARY grader. The cross-entry-point matrix: ONE synthetic provider observation put
#: through `probe_provider_cli`, `probe_status` and the runtime `generate` path, asserting the three
#: do not DISAGREE on an authoritative control decision. It passed 23/23 the first time it ran,
#: which is precisely when an instrument must be calibrated rather than believed -- H27/H28/H29 are
#: that calibration, kept PERMANENT rather than run once and discarded.
MATRIX = "tests/unit/test_cross_entry_point_control_state.py"
MATRIX_CONTAINMENT = (MATRIX + "::test_the_zero_exit_signed_out_shape_is_contained_at_the_LAUNCH_"
                      "gate_not_at_generate")
MATRIX_SHADOW = (MATRIX + "::test_row8_ANTI_SHADOW_the_runtime_pauses_on_the_verdict_with_no_"
                 "marker_in_its_excerpt")
#: The picker is where `selectable_models()` becomes an OFFER, which is the containment the matrix
#: leans on to call the zero-exit signed-out asymmetry compatible rather than contradictory.
PICKER = "tools/live/enumerate_pane_picker.py"

#: Anchors for the boundary rows, triple-quoted so this file carries no escape sequences the way
#: the rows above do -- one of them was mangled in transit once, and the shape is worth not
#: repeating.
_H27_OLD = """    if inv.auth_required_reported:
        return inv, AUTH_REQUIRED, "the CLI explicitly reports that the operator is not authenticated"
    if inv.login_reported:
"""
_H27_NEW = """    if inv.login_reported:
"""
_H28_OLD = """            if outcome.outcome in (OUTCOME_AUTH_REQUIRED, OUTCOME_USAGE_LIMIT):
"""
_H28_NEW = """            if is_auth_pause_text(outcome.detail):
"""
_H29_OLD = """        models=tuple(probe.selectable_models()),
"""
_H29_NEW = """        models=tuple(probe.models),
"""

MUTATIONS = [
    ("H1  the echo subtraction runs on the whitespace fold again (U238 hole 1)",
     RECON,
     "    return f_token in f_response.replace(f_prompt, \" \")",
     "    return n_token in n_response.replace(n_prompt, \" \")",
     U238_ECHO + "::test_a_punctuation_or_whitespace_deleting_echo_is_not_an_answer"),
    ("H2  acceptance reads the best-effort extractor again (U238 hole 2)",
     RECON,
     "    response = extract_probe_response_field(stdout)      # strict reader only (U238 hole 2)",
     "    response = extract_probe_text(stdout)",
     U238_FIELD + "::test_a_token_outside_a_recognised_response_field_is_not_an_answer"),
    ("H3  the STRICT reader grows the whole-document fallback",
     COMMON,
     "        for key in PROVIDER_RESPONSE_KEYS:\n"
     "            val = doc.get(key)\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                return val\n"
     "    return \"\"",
     "        for key in PROVIDER_RESPONSE_KEYS:\n"
     "            val = doc.get(key)\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                return val\n"
     "        return json.dumps(doc)\n"
     "    return \"\"",
     U238_FIELD),
    ("H4  the strict reader accepts ANY string value, not a recognised field",
     COMMON,
     "        for key in PROVIDER_RESPONSE_KEYS:\n"
     "            val = doc.get(key)\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                return val\n"
     "    return \"\"",
     "        for val in doc.values():\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                return val\n"
     "    return \"\"",
     U238_FIELD + "::test_a_token_outside_a_recognised_response_field_is_not_an_answer"),
    ("H5  `operator_terms_confirmed` becomes a defaulted keyword again (U292(a))",
     EMITTER,
     "    operator_terms_confirmed: bool,",
     "    operator_terms_confirmed: bool = True,",
     GATE_INPUTS + "::test_the_gate_input_is_a_required_keyword"),
    # Signature-only by design — see the module docstring. H7 is the behavioural half.
    ("H6  `profile_loader` becomes a defaulted keyword again (signature only; U283)",
     EMITTER,
     "    profile_loader: ProfileLoader,\n"
     "    operator_terms_confirmed: bool,",
     "    profile_loader: ProfileLoader | None = None,\n"
     "    operator_terms_confirmed: bool,",
     GATE_INPUTS + "::test_the_gate_input_is_a_required_keyword"),
    # The replacement builds the loader through a fully-qualified inline import rather than a
    # module-level name, because the closure DELETED the `DeploymentProfile` import: a mutation
    # that fell over with `NameError` would score RED without ever testing the guard.
    ("H7  main() hands the gate chain a manufactured `cloud` profile (the call site)",
     EMITTER,
     "            profile_loader=profile_loader_from_host(),",
     '            profile_loader=__import__("control_plane.profiles.loader", fromlist=["x"])'
     '.ProfileLoader(__import__("control_plane.profiles.loader", fromlist=["x"])'
     '.DeploymentProfile("cloud")),',
     GATE_INPUTS + "::test_the_production_path_refuses_a_frontier_pane_on_an_airgapped_host"),
    ("H8  token PRESENCE moves onto the destructive fold (over-strictness leaking into recognition)",
     RECON,
     "    if not n_token or n_token not in n_response:",
     "    if not n_token or fold(token) not in fold(response):",
     U238_ECHO + "::test_the_token_must_still_appear_verbatim_not_only_after_punctuation_folding"),
    # H9 is not a shipped behaviour being restored — it is the one thing 18E ADDED beyond the two
    # holes, and an addition with no guard is a comment. Collapsing the branch reports a document
    # with no response field as "a prompt echo does not count", which sends an operator hunting for
    # an echo in a transcript whose token is sitting in a `debug` field. Same refusal, wrong reason.
    ("H9  the two refusal reasons collapse into one (the no-response-field case reads as an echo)",
     RECON,
     "        if parsed and not response:",
     "        if False:",
     U238_FIELD + "::test_the_two_ways_to_fail_this_condition_are_reported_differently"),
    # H10 deletes the CALL, not the function: the guard stays defined and tested in isolation, which
    # is precisely the shape of defect that survives a green suite. The selector is the leg that
    # asserts SILENCE (no enumeration), because the leg that asserts `refused_by == profile_roster`
    # passes either way — the downstream gate still refuses, just after the egress.
    ("H10 the air-gap gate moves back BEHIND the host enumeration (the F2 ordering, U303)",
     EMITTER,
     "        _assert_profile_permits_verifying(option, loader)\n",
     "",
     GATE_INPUTS + "::test_an_airgapped_host_refuses_a_frontier_pane_without_enumerating"),
    # W-44. The antigravity listing parser failed in TWO OPPOSITE DIRECTIONS, so it needs two rows:
    # one per direction, each graded by a test the OTHER row's mutation leaves green. A single row
    # would let half the repair be deleted silently, which is the shape of the original defect.
    # W-45 re-anchored H11: the condition it mutates gained the letter predicate, so its `find`
    # was re-read against the new bytes rather than re-hashed. Its replacement now KEEPS the letter
    # rule on purpose, so H11 still fails only the WORD test and H13 still fails only the NUMBER
    # test -- two rows, two claims, neither able to pass for the other reason.
    ("H11 the model-id shape drops its digit/separator evidence, so a word is an inventory (W-44)",
     COMMON,
     "        if not (rest_ok and MODEL_SLUG_RE.match(slug) and _AGY_MODEL_ID_RE.match(slug)\n"
     "                and _AGY_ID_EVIDENCE_RE.search(slug) and _AGY_ID_LETTER_RE.search(slug)):",
     "        if not (rest_ok and MODEL_SLUG_RE.match(slug) and _AGY_ID_LETTER_RE.search(slug)):",
     AGY_MODELS + "::test_antigravity_bare_prose_WORDS_are_never_models"),
    # The other direction, and the one a "just split the columns" fix would have shipped: a SINGLE
    # space becomes a column delimiter, so every sentence whose first token is model-shaped donates
    # that token to the inventory. `gpt-4 is not available in your region` is the grader.
    ("H12 a single space becomes a column delimiter, so a sentence donates its first token (W-44)",
     COMMON,
     '_AGY_COLUMN_RE = re.compile(r"\\t| {2,}")',
     '_AGY_COLUMN_RE = re.compile(r"\\t| +")',
     AGY_MODELS + "::test_antigravity_refuses_a_SENTENCE_that_opens_with_a_real_model_id"),
    # W-45 (A-7). The letter requirement is its own row because it is its own claim: H11 grades
    # "a token is not an English WORD", this grades "a token is not a bare NUMBER". Deleting this
    # predicate leaves every H11 row green -- `Traceback` is still refused -- while `401`, `403`,
    # `429` and `500` go straight back into the inventory the picker offers.
    ("H13 the model id stops having to carry a LETTER, so an HTTP status code is a model (W-45)",
     COMMON,
     "                and _AGY_ID_EVIDENCE_RE.search(slug) and _AGY_ID_LETTER_RE.search(slug)):",
     "                and _AGY_ID_EVIDENCE_RE.search(slug)):",
     AGY_MODELS + "::test_antigravity_a_bare_status_NUMBER_is_not_a_model_id"),
    # W-46 (A-8). The regex un-anchored, which is exactly the shipped defect: `.search()` over an
    # unanchored pattern reports a logged-in session for any line that MENTIONS the phrase, and
    # `probe_status` turns that straight into AUTH_AUTHENTICATED. The grader is the CONDITIONAL
    # prose, not the real login line -- the real line stays green under this mutation, which is
    # why a row graded by the positive direction would prove nothing.
    ("H14 the grok login marker un-anchors, so prose mentioning the phrase authenticates (W-46)",
     COMMON,
     r'    r"^\s*you are logged in(?:\s+with\s+(?P<account>\S+))?\s*\.?\s*$", re.I)',
     r'    r"you are logged in(?:\s+with\s+(?P<account>\S+))?", re.I)',
     GROK_AUTH + "::test_grok_CONDITIONAL_prose_never_reports_a_login"),
    # W-47 (R-05). The codex classifier goes back to a bare substring test, which is the shipped
    # defect: every signed-out sentence that NAMES the state it denies then authenticates, unless
    # its exact phrasing happens to sit in the negative blacklist. Graded by the signed-out prose
    # rows; the declarative login rows stay GREEN under this mutation, which is the point -- the
    # positive direction cannot detect an over-permissive classifier.
    ("H15 the codex login check becomes a bare substring again (W-47/R-05)",
     CODEX,
     r'                  and bool(_LOGGED_IN_RE.search(low))',
     r'                  and "logged in" in low',
     CODEX_AUTH + "::test_a_signed_out_sentence_containing_logged_in_is_NOT_authenticated"),
    # W-48 (A-6). The zero-exit branch goes back to scanning the WHOLE answer, which is the shipped
    # defect: any successful answer discussing rate limits, quotas, 429s, logins or API keys pauses
    # the NODE. Graded by the answers, not by the error reports -- the reports stay green under this
    # mutation, so a row graded by them could not tell an over-eager classifier from a correct one.
    ("H16 the zero-exit pause scans the whole answer again, so discussing a limit is one (W-48)",
     CODEX,
     r'        if self._classify_error_report(out) and not out.startswith("{"):',
     r'        if self._classify(out) and not out.startswith("{"):',
     CODEX_BACKEND + "::test_a_successful_answer_discussing_limits_does_NOT_pause_the_node"),
    # W-49 (R-08), both halves of the drift that existed. H17 restores the stdout-only parse the
    # recon copy had; H18 removes the auth-required branch the recon copy never had. Each is graded
    # by the agreement test for its own shape, and each leaves the other shape green.
    ("H17 the shared models policy parses stdout alone, losing the STDERR login line (W-49)",
     COMMON, r'    inv = parse_models(f"{stdout}\n{stderr}" if reports_auth else stdout)', r'    inv = parse_models(stdout)',
     TWO_PROBES + "::test_the_login_line_on_STDERR_is_read_by_BOTH"),
    ("H18 the shared models policy drops the explicit not-authenticated report (W-49)",
     COMMON, r'    if inv.auth_required_reported:', r'    if False:',
     TWO_PROBES + "::test_an_EXPLICIT_not_authenticated_report_is_preserved_by_BOTH"),
    # W-50 (R-24). H19 restores the shipped defect exactly: the verdict is discarded and the pause
    # re-derived from `outcome.detail`, an excerpt of ONE stream. Graded by the decisive test --
    # the one whose excerpt carries no trigger prose -- because tests 1/2/4/5 stay GREEN under it.
    ("H19 generate() discards the verdict and re-derives the pause from the excerpt (W-50)",
     COMMON, r'            if outcome.outcome in (OUTCOME_AUTH_REQUIRED, OUTCOME_USAGE_LIMIT):', r'            if is_auth_pause_text(outcome.detail):',
     BACKEND + "::test_6_the_VERDICT_pauses_even_when_the_detail_carries_no_trigger_prose"),
    # H20 is the other direction and answers a question the first cannot: it EMPTIES the structured
    # auth verdict while LEAVING the auth prose in both streams and in the excerpt. If the
    # downstream path still paused, it would be rediscovering authority from prose and the
    # duplicated policy would still exist. It must go RED -- consuming the verdict means the
    # verdict is the only thing consulted.
    ("H20 the classifier stops MINTING the auth verdict, prose left intact (W-50)",
     COMMON, r'        return ProviderOutcome(OUTCOME_AUTH_REQUIRED, exit_code, "nonzero-exit+auth-marker",', r'        return ProviderOutcome(OUTCOME_FAILED, exit_code, "nonzero-exit+auth-marker",',
     BACKEND + "::test_1_a_stdout_only_auth_failure_pauses_the_node"),
    # W-51 (R-25). Each row RESTORES THE OLD BEHAVIOUR for one of the two absences: it returns the
    # requested slug "carried unverified" instead of refusing, which is exactly what `if available:`
    # did for both. A first attempt simply deleted the branches and H22 came back GREEN -- because
    # with the empty branch gone, `slug not in inventory` refuses `()` anyway. That is worth
    # recording: the empty branch does not carry the REFUSAL, it carries the DIAGNOSTIC that keeps
    # "established and empty" distinct from "never established". Deleting a guard whose job is a
    # diagnostic is invisible to a test that only asserts a raise, which is why the rows restore the
    # old RETURN rather than removing the check.
    ("H21 an UNESTABLISHED inventory carries the label unverified again (W-51)",
     COMMON, r'    if available is None:', r'    if available is None:\n        return slug, "carried unverified"',
     BACKEND + "::test_W51_an_UNESTABLISHED_inventory_is_refused_and_says_so_DIFFERENTLY"),
    ("H22 an EMPTY inventory carries the label unverified again (W-51)",
     COMMON, r'    if not inventory:', r'    if not inventory:\n        return slug, "carried unverified"',
     BACKEND + "::test_W51_DECISIVE_an_unknown_model_against_an_EMPTY_inventory_is_refused"),
    # W-52 (R-48). The two OPPOSITE failure modes, each graded by a test the other leaves GREEN --
    # which is the point: a reader free to drift from one into the other is not pinned. H23 is the
    # shipped "first line only" policy; H24 is the tempting "search every line for a semver" fix,
    # which repairs the false negative and makes the false positive materially worse.
    # H24's grader was CHANGED after a first attempt came back GREEN: the npm-only transcript is
    # refused by the EXACTLY-ONE-VERSION rule (`9.9.9 -> 10.0.0` is two), not by the shape rule,
    # so it could not grade the shape rule. What the shape rule uniquely refuses is a line with
    # exactly ONE version that is still prose -- a URL, an install hint, a filename, a duration.
    ("H23 the version reader looks at the FIRST LINE only again (W-52)",
     COMMON, r'    for raw in (text or "").splitlines():', r'    for raw in (text or "").splitlines()[:1]:',
     VERSION + "::test_W52_a_declaration_below_a_VERSIONLESS_banner_is_found"),
    ("H24 the version reader accepts ANY semver on a line, declaration or not (W-52)",
     COMMON, r'        m = _VERSION_BARE_RE.match(line) or _VERSION_NAMED_RE.match(line)', r'        m = _SEMVER_RE.search(line)',
     VERSION + "::test_W52_a_SINGLE_semver_that_is_not_a_declaration_is_ignored"),
    # W-53 (R-38). NO production repair was needed -- both live execution paths already pinned
    # `encoding="utf-8", errors="replace"`. What was missing was evidence, so this row keeps the
    # parity proof honest: unpin the codec on the recon runner and the behavioural test must go RED.
    # A no-repair disposition with an uncalibrated test is a celebration, not a measurement.
    ("H25 the recon runner stops replacing malformed bytes, so the codec is unpinned (W-53)",
     RECON,
     '                                  encoding="utf-8", errors="replace")',
     '                                  encoding="utf-8", errors="strict")',
     DECODE_PARITY),
    # W-54 (R-85). Restores the shipped defect exactly: every token becomes a NAME candidate, so a
    # model slug spelling a flag name is refused again. Graded by the legitimate-slug test; the
    # smuggling tests stay GREEN under it, which is why they cannot grade this row.
    ("H26 the argv guard treats VALUES as flag names again (W-54/R-85)",
     COMMON, r'        if not tok.startswith("-"):', r'        if False:',
     ARGV_GUARD + "::test_W54_a_model_slug_that_SPELLS_a_flag_name_still_builds"),
    # ---- TIER-4 BOUNDARY: the cross-entry-point matrix, calibrated in three directions --------
    # Each row restores a defect this tier ACTUALLY SHIPPED, and each is graded by the ONE matrix
    # row that uniquely carries the property -- never by the matrix FILE, which two of them would
    # redden for the wrong reason. Standing diagnostic ([[U471]] H22, [[U474]] H24): a row graded
    # by whatever happens to fail proves nothing about which guard holds.
    ("H27 `classify_models_call` parses the auth evidence and DROPS it again (W-49/R-08)",
     COMMON, _H27_OLD, _H27_NEW, MATRIX_CONTAINMENT),
    # The pre-W-50 shape verbatim: the pause re-derived from the human-readable EXCERPT instead of
    # the structured verdict. Graded by the anti-shadow row, which is the only construction where
    # the two can be told apart -- every other auth row carries the marker in the excerpt too and
    # stays GREEN under this mutation, which is exactly why H20 had to exist in the first place.
    ("H28 `generate` re-derives the pause from the 600-char excerpt again (W-50/R-24)",
     COMMON, _H28_OLD, _H28_NEW, MATRIX_SHADOW),
    # The containment itself. grok exits ZERO when signed out, so the probes' AUTH_REQUIRED verdict
    # is what fences the LAUNCH; if the picker offered `probe.models` instead, the documented
    # asymmetry between the probes and `generate` would become a real disagreement.
    ("H29 the picker offers the raw inventory instead of the selectable one (containment)",
     PICKER, _H29_OLD, _H29_NEW, MATRIX_CONTAINMENT),
]

#: Files this run may have mutated, pinned at import so the signal handler can restore ALL of them
#: even if it fires between the write and the restore. The JS sibling
#: (`pane_input_bypass_mutations.js`) documents this contract; `_op18c_probe_path_mutations.py`
#: still lacks it (U292(b)), and a harness that mutates product files must never be able to leave
#: one mutated because someone pressed Ctrl-C.
_PINNED: dict[pathlib.Path, bytes] = {}
_LOCK = ROOT / ".mutation-lock"


def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _restore_all(*_a: object) -> None:
    for path, original in _PINNED.items():
        try:
            path.write_bytes(original)
        except OSError:                                  # pragma: no cover - best effort teardown
            pass
    _LOCK.unlink(missing_ok=True)


def run_one(rel: str, old: str, new: str, target: str) -> tuple[str, str]:
    path = ROOT / rel
    before = _PINNED[path]
    before_hash = digest(path)
    text = before.decode("utf-8")
    if old not in text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    mutated = text.replace(old, new, 1)
    if mutated == text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    path.write_bytes(mutated.encode("utf-8"))
    try:
        proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True)
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
    return verdict, ("restored" if digest(path) == before_hash else "RESTORE FAILED")


def main() -> int:
    if _LOCK.exists():
        print(f"another mutation run holds {_LOCK} - refusing to mutate product files concurrently")
        return 1
    _LOCK.write_text(str(__file__), encoding="utf-8")
    for _, rel, _o, _n, _t in MUTATIONS:
        _PINNED.setdefault(ROOT / rel, (ROOT / rel).read_bytes())
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_a: (_restore_all(), sys.exit(130)))

    rows = []
    try:
        for label, rel, old, new, target in MUTATIONS:
            verdict, restore = run_one(rel, old, new, target)
            rows.append((label, verdict, restore))
    finally:
        _restore_all()

    width = max(len(r[0]) for r in rows)
    for label, verdict, restore in rows:
        print(f"{label.ljust(width)}  {verdict:<26} {restore}")
    ok = all(r[1] == "RED" and r[2] == "restored" for r in rows)
    failed = [r[0] for r in rows if r[2] == "RESTORE FAILED"]
    print(f"\n{sum(1 for r in rows if r[1] == 'RED')}/{len(rows)} RED, "
          + ("all restores byte-identical" if not failed
             else "RESTORE FAILED: " + "; ".join(failed)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
