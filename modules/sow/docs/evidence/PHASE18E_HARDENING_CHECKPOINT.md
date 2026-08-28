# Phase 18E `.hardening` — checkpoint evidence report

**Status:** sub-step COMPLETE and committed. **`gate/phase-18e` does NOT exist and this unit did not
create it.** 18E is a large phase and directive §3 allows a named sub-step as a work unit; this is
sub-step (1) of three.

| | |
|---|---|
| Work unit | `phase-18e.hardening` |
| Work commit | **`1b252ad`** (this report and the register rows are the second commit of the two-commit convention) |
| Authority | `AUTONOMOUS_BUILD_DIRECTIVE.md` §17.2 (OP-12.2), items **(2)** and **(3)** |
| Date | 2026-08-02 |
| Host | Windows 11, `py -3.12` (Python 3.12.10); `python` on PATH is 3.14.6 and lacks this repo's deps |
| Live calls made | **ZERO.** No provider CLI was invoked. No credential was read, stored, or transmitted. |

## 1. What §17.2 asked for, and what this unit did

> **(2)** Close **U238** (whitespace-deleting echo acceptance; `extract_probe_text` whole-document
> fallback) BEFORE the live legs run, so the live verdict cannot rest on either hole […] note the
> operator's probe already returned exact tokens, so this is hardening the acceptance, not repairing
> a result.
>
> **(3)** […] the `gates.operator_terms_confirmed` parameter-default (scope_note_gate_map) gets the
> U283-style closure on the pane/worker emitter.

Both are done. A third defect was found by this unit's own spec-audit and closed here rather than
carried (**U303**, §4). Six further limits the two reviewers found are **recorded, not fixed**
(U304–U309, §6) — each one names its owner.

**Sequencing note.** This is the sub-step that had to come first: §17.2(2) says "BEFORE the live
legs run". The live per-provider in-Electron legs are the NEXT unit (`phase-18e.live`), and the
whole-track close (`phase-18e.close`) after it.

## 2. §17.2(2) — U238, both holes

### Hole 1 — the echo fold

`_token_answered` subtracted the echoed prompt on a whitespace-COLLAPSED, case-folded fold. Collapse
is not deletion, and it says nothing about punctuation, so a model that restated the instruction with
different spacing or punctuation left the prompt unmatched and the token intact.

Fixed by asking the two questions with two folds, which is the point of the design:

* **PRESENCE** of the token stays on the whitespace fold — deliberately unchanged, because the
  stricter fold would read `GROK-PROVIDER-OK` as the token, and §17 wants the token.
* **SUBTRACTION** of the echo runs on an alphanumeric-only fold, where every space, dash, colon,
  asterisk and quote is gone from both sides, so no rewriting of the instruction's punctuation hides
  it from the removal — and the token must survive the removal anyway.

Mutation **H8** exists to stop the new strictness leaking into recognition.

### Hole 2 — the whole-document fallback

Acceptance called `extract_probe_text`, whose documented job is best-effort DISPLAY: when it finds no
recognised response key it falls back to `json.dumps(doc)`. So a token in any field at all certified
the provider. `{"status":"done","debug":"GROK_PROVIDER_OK"}` is a document in which the CLI said
nothing.

Acceptance now calls a separate strict reader, `extract_provider_response_field`: a recognised
response field, or the whole document when that document **is** a bare JSON string (the one case with
no field to look in, because the string is the payload), or `""`. Both readers iterate one shared
`PROVIDER_RESPONSE_KEYS`, so "what the model said" and "what the model said, for acceptance purposes"
cannot drift onto different key sets. The best-effort reader is behaviourally unchanged: the recon
report's `response_excerpt` and the worker adapter's result payload still show an operator whatever
the CLI emitted.

### Additional: the refusal now says WHICH thing went wrong

Two different failures reached one sentence. `{"status":"done","debug":"GROK_PROVIDER_OK"}` reported
"a prompt echo does not count", sending a reader hunting for an echo in a transcript whose token is
sitting in a `debug` field. The two are now reported separately, and the field set is named because
"recognised" is useless without the list. Guarded by mutation **H9** — the row that is not a restored
shipped behaviour, and says so.

### The measurement (this is the transcript the tests cite)

`docs/loop/logs/u238_before_after.py` (a scratch diagnostic under a gitignored path — its source is
reproduced in §7 so this report is self-contained) judges the same shapes twice: once with the two
SHIPPED behaviours restored in-process by monkeypatch, once on this unit's tree. Verbatim output:

```
=== BEFORE - the tree the operator armed 18E on ===
-- hole 1: echo normalisation (every row is PURE ECHO - the CLI answered nothing) --
    ACCEPTED 'Reply with exactly:GROK_PROVIDER_OK'
    ACCEPTED 'Reply with exactly - GROK_PROVIDER_OK'
    refused  '"Reply with exactly: GROK_PROVIDER_OK"'
    ACCEPTED 'R e p l y  w i t h  e x a c t l y :  GROK_PROVIDER_O'
    ACCEPTED 'Reply-with-exactly: GROK_PROVIDER_OK'
    ACCEPTED 'Reply with exactly:  ->  GROK_PROVIDER_OK'
    ACCEPTED '**Reply with exactly:** GROK_PROVIDER_OK'
-- hole 2: whole-document fallback (no recognised response field carries the token) --
    ACCEPTED {"status": "done", "debug": "GROK_PROVIDER_OK"}
    ACCEPTED {"debug": "GROK_PROVIDER_OK"}
    ACCEPTED {"foo": {"bar": "GROK_PROVIDER_OK"}}
    ACCEPTED {"trace": ["GROK_PROVIDER_OK"]}
    ACCEPTED {"result": null, "echoed_argv": ["grok", "-p", "GROK_PROVIDER_OK"]}
    ACCEPTED {"metadata": {"probe_token": "GROK_PROVIDER_OK"}, "result": ""}
-- control: genuine answers, which must stay ACCEPTED on both sides --
    ACCEPTED 'GROK_PROVIDER_OK'
    ACCEPTED 'Sure - GROK_PROVIDER_OK'
    ACCEPTED 'Done. GROK_PROVIDER_OK (as requested)'

=== AFTER - this unit's tree ===
-- hole 1: echo normalisation (every row is PURE ECHO - the CLI answered nothing) --
    refused  'Reply with exactly:GROK_PROVIDER_OK'
    refused  'Reply with exactly - GROK_PROVIDER_OK'
    refused  '"Reply with exactly: GROK_PROVIDER_OK"'
    refused  'R e p l y  w i t h  e x a c t l y :  GROK_PROVIDER_O'
    refused  'Reply-with-exactly: GROK_PROVIDER_OK'
    refused  'Reply with exactly:  ->  GROK_PROVIDER_OK'
    refused  '**Reply with exactly:** GROK_PROVIDER_OK'
-- hole 2: whole-document fallback (no recognised response field carries the token) --
    refused  {"status": "done", "debug": "GROK_PROVIDER_OK"}
    refused  {"debug": "GROK_PROVIDER_OK"}
    refused  {"foo": {"bar": "GROK_PROVIDER_OK"}}
    refused  {"trace": ["GROK_PROVIDER_OK"]}
    refused  {"result": null, "echoed_argv": ["grok", "-p", "GROK_PROVIDER_OK"]}
    refused  {"metadata": {"probe_token": "GROK_PROVIDER_OK"}, "result": ""}
-- control: genuine answers, which must stay ACCEPTED on both sides --
    ACCEPTED 'GROK_PROVIDER_OK'
    ACCEPTED 'Sure - GROK_PROVIDER_OK'
    ACCEPTED 'Done. GROK_PROVIDER_OK (as requested)'
```

**Twelve shapes** — six pure echoes and six documents in which no recognised response field carries
the token — went from ACCEPTED to refused. The three controls are unmoved: this is a tightening, not
a blunting. The one BEFORE row that already refused (`"Reply with exactly: …"` in quotes) is kept in
the fixture set precisely so the new fold can be shown not to have lost ground the old one held.

The gate-validator did **not** take this script's word for the BEFORE column: it extracted
`HEAD:tools/providers/frontier_provider_recon.py`, loaded it as a live module, and re-measured. Same
result, and it confirmed the monkeypatched `old_token_answered` is a faithful copy of the removed
lines.

### What "CLOSED" does not claim

* **A live verdict already rests on the pre-fix reader.** §17.2 records that the operator's own recon
  probe succeeded LIVE for both providers on 2026-08-02, under the old code. The directive's own
  words for this work are "hardening the acceptance, not repairing a result". What is guaranteed is
  that no verdict taken **from here on** rests on either hole.
* **A paraphrased echo still passes** — the subtraction removes a contiguous prompt (**U304**).
* **Neither provider's real response document has been read against the strict reader** (**U305**).
  If a CLI nests its answer, acceptance now refuses a genuine one. Safe direction, unverified fact,
  and the first thing `.live` should capture.

## 3. §17.2(3) — the pane/worker emitter's two invented gate inputs

`build_worker_launch_ticket` answered two questions that are not its to answer:

| Parameter | Was | Defect |
|---|---|---|
| `profile_loader` | `None` → `ProfileLoader(DeploymentProfile("cloud"))` | Which profile is in force is the HOST's fact. Manufacturing `cloud` made **invariant 20's air-gap half structurally unreachable on the product path** — and every test that "covered" the air-gap injected the loader the product never passed. U91's shape, closed on `provider_probe_session` at 18C `.probe-path` as U283. |
| `operator_terms_confirmed` | `True` | Published `gates.operator_terms_confirmed: true` in every ticket while no production caller supplied it — a parameter default rendered as a measurement. U98's shape; the 18C receipt had to disclose it in `scope_note_gate_map` and exclude the gate from its verdict. |

Both are now REQUIRED keyword arguments with no defaults. `main()` — the sole production caller —
supplies the profile through `profile_loader_from_host()` (the ONE implementation of that question,
imported rather than re-derived) and the terms flag with OP-9/OP-12 cited at the call site. The
`DeploymentProfile` import is deleted, so the manufactured loader cannot return unnoticed.

**Proved by execution, not by signature.** The gate-validator spawned the real script as a
subprocess with a real environment variable and real stdin:

```
=== profile=offline_airgapped  rc=0
  authorized = False  refused_by = profile_roster
  reason = ProfileViolation: adapter 'claude_code' (requires_network=True,
           offline_profile_eligible=False) is excluded from the offline/air-gapped profile
=== profile=cloud  rc=0
  authorized = True   refused_by = None
  gates.operator_terms_confirmed = True
=== profile=banana rc=1  (ProfileViolation: unknown deployment profile 'banana', no JSON)
```

The `cloud` leg is there so the air-gap leg cannot pass by refusing everything.

**What this is NOT.** `operator_terms_confirmed=True` is still a hard-coded `True`, moved one frame
up to where its authority can be cited and checked. Nothing machine-readable can measure whether the
operator's subscription terms permit a supervised CLI call — that is invariant 1, and the receipt
says so in the same words. The improvement is that the citation is now at the call site instead of
being a default inside the gate chain. `scope_note_gate_map` was rewritten to say exactly that, after
the gate-validator flagged the first draft's "an INJECTED value" as implying provenance the value
does not have.

## 4. U303 — found by this unit's own spec-audit, closed here: invariant 20 fired AFTER the egress

Closing the manufactured `cloud` loader made the air-gap gate reachable — and reachable exposed an
ordering defect. `_assert_option_offered` runs first, and for an OP-12 selection it enumerates
through `only_op12_probe(provider)`: `grok models` / `agy models`, which **leave the host**
(D-P18-7/U271). So an air-gapped host emitted provider metadata traffic and *then* refused the pane.

The verdict was right; the ordering was not. For invariant 20 that distinction is the whole point:
"excluded from the offline profile" has to mean the network was never touched, not that the answer
came back no. `_assert_profile_permits_verifying` now raises `ProfileViolation` — the same
`profile_roster` gate id, because it IS that gate — before the enumeration.

Two things worth recording about how it was verified:

* The guard test replaces `build_host_picker` with a **detonator**, so a future unit that moves the
  gate back fails with the call it should not have made, rather than with an assertion about a gate
  id. A test asserting only `refused_by == "profile_roster"` stays green through the regression —
  which is exactly why mutation **H10** targets the silence leg.
* Writing the CONTROL for that test measured the egress **one step earlier than the audit found it**:
  the cost is paid constructing `only_op12_probe`, before `build_host_picker` is ever called. The
  suite's own live-call guard caught it by refusing a real `grok models` — the guard working as
  designed, on the builder, mid-unit.

Scoping: the guard refuses frontier adapters only. A local model on an air-gapped host is the case
the offline profile EXISTS to serve (invariants 19/20) and must still reach the enumeration — pinned
by its own test, because a guard that refused everything would be no guard at all.

## 5. Verification — every command, real output

| Check | Command | Result |
|---|---|---|
| Full Python suite | `py -3.12 -m pytest tests/ -q` | **2117 passed, 1 skipped** |
| Desktop JS suite | `cd apps/desktop && npm test` | **751 pass, 0 fail** |
| Mutation harness | `py -3.12 tools/mutation/_op18e_hardening_mutations.py` | **10/10 RED, all restores byte-identical** |
| U238 measurement | `py -3.12 docs/loop/logs/u238_before_after.py` | transcript in §2 |
| JS syntax | `node --check apps/desktop/selfcheck/op12-acceptance-selfcheck.js` | OK |
| `ruff` | — | **NOT RUN: `ruff` is not installed on this host** under either interpreter. Recorded as U309 rather than left silent. |

### 5.1 Mutation results

Ten mutations, each applied alone, its selector run, the original bytes restored, and the restore
verified byte-identical by sha256. The harness pins every file it may touch at import and restores
them from a SIGINT/SIGTERM handler, so a Ctrl-C cannot leave a product file mutated.

```
H1  the echo subtraction runs on the whitespace fold again (U238 hole 1)                       RED   restored
H2  acceptance reads the best-effort extractor again (U238 hole 2)                             RED   restored
H3  the STRICT reader grows the whole-document fallback                                        RED   restored
H4  the strict reader accepts ANY string value, not a recognised field                         RED   restored
H5  `operator_terms_confirmed` becomes a defaulted keyword again (U292(a))                     RED   restored
H6  `profile_loader` becomes a defaulted keyword again (signature only; U283)                  RED   restored
H7  main() hands the gate chain a manufactured `cloud` profile (the call site)                 RED   restored
H8  token PRESENCE moves onto the destructive fold (over-strictness leaking into recognition)  RED   restored
H9  the two refusal reasons collapse into one (the no-response-field case reads as an echo)    RED   restored
H10 the air-gap gate moves back BEHIND the host enumeration (the F2 ordering, U303)            RED   restored

10/10 RED, all restores byte-identical
```

**The harness caught the builder, not just the code.** An intermediate run reported
`SKIPPED-ANCHOR-MISSING` for H6 and H10 — not RED, not GREEN. The cause was a throwaway renumbering
script that used `pathlib.write_text`, which on Windows translates `\n` to `\r\n`: six files had been
silently rewritten to CRLF, breaking the harness's multi-line anchors (and heading straight for the
U279-class phantom-diff noise this repo has fought before). The bytes were normalised back to LF and
the run above is the re-run. Recorded because it is the point of that verdict existing: a harness
whose missing anchor scored RED, or scored nothing, would have hidden a corrupted tree behind
"10/10". `git diff` shows no line-ending churn.

Most rows restore a SHIPPED behaviour — the `new` string is the code that was on the tree when the
operator armed 18E, not an invented defect. Three are not, and say so at their own entries: **H6** is
signature-only (with `main()` still passing a loader, restoring the body fallback would change no
runtime behaviour and prove nothing — H7 is the behavioural half, and that correction came from the
spec-auditor), **H9** tests something 18E added, **H10** tests an ordering that never existed before.

### 5.2 Tests modified rather than added — declared, because a changed assertion is where a weakening hides

* `TestReviewerFoundDefects::test_a_prompt_echo_is_not_an_answer` — became parametrised with a
  per-case expected reason. **All three inputs are still REFUSED**; only the explanation got sharper
  (one of them now refuses for the more precise "no recognised response field").
* `test_emit_provider_node_registration.py` — two assertions went red **without a line of product
  code changing**, both because the OPERATOR exercised their own authority:
  * `store["after"]["node_event_log"]["exists"] is False` — the operator's 2026-08-02 recon probe
    wrote the first durable `node@1.1` records, which is the outcome 18D was built for. "Absent" was
    never the claim; "untouched" is, and it is measured by digest, which holds whether the file
    exists or not. The positive half (this report's registrations go to a SCRATCH log) is now
    asserted from the other side.
  * `GROK_ADAPTER not in switch.read_text()` — the operator widened `config/live_operation.json` to
    OP-12 scope on 2026-08-01, exactly as §17 asks them to. A test that fails when the operator does
    what the directive tells them to was testing the wrong thing (the audit-R4 non-hermetic class).
    Replaced with a sha256 comparison across the call, plus a parametrised test proving that
    comparator goes red on create, delete, and a modification that preserves byte length — because a
    test whose failure branch has never been observed is a test never observed to work.

## 6. Reviewers — both run in the foreground, this turn

Per D-LOOP-2 (print-mode): both reviewers ran synchronously inside the turn that used their output.

**gate-validator: PASS_WITH_RESERVATIONS.** Claims A–D verified by execution, including an
independent re-measurement against the real pre-`HEAD` module. It re-ran every command itself, hashed
the three product files before and after the mutation run to confirm byte-clean restoration, and
tried to break the work: 24 adversarial documents against the strict reader (nested docs, lists,
JSON scalars, case-variant keys, token-as-key-name, 100 KB padding) and 24 genuine-answer shapes
against the new fold, looking for a false refusal. It found no bypass and no false refusal, and could
not turn the `not f_prompt or f_prompt == f_token` early return into an echo bypass.

**spec-auditor: no invariant violated, no prohibited drift.** Invariant 1's citation checked against
the directive text and found accurate; invariants 2/7/16/27 untouched or strengthened; every new
branch confirmed to fail in the safe direction; `PROVIDER_RESPONSE_KEYS` confirmed genuinely shared
rather than duplicated.

**Every finding was acted on in this unit — fixed or recorded, none dropped:**

| Finding | Disposition |
|---|---|
| spec-audit **F2** — invariant 20 fires after the egress | **FIXED** (§4, U303, mutation H10) |
| spec-audit **F1** / validator MINOR-1 — the tests cited a checkpoint report that did not exist | **FIXED** — this file, written and committed with the code that cites it |
| validator **MEDIUM-1** — "so no live verdict rests on either" contradicted §17.2's own record of the operator's successful pre-fix probe | **FIXED** — the docstring now carries the directive's caveat |
| spec-audit **F3** — the receipt said CLOSED while the register said OPEN | **FIXED** — register rows appended in this unit's evidence commit |
| spec-audit **F5** — H6's label claimed a behavioural test it does not perform | **FIXED** — relabelled; H7 named as the behavioural half |
| spec-audit **F7** — the receipt omitted the bare-JSON-string branch | **FIXED** |
| spec-audit **F9** — "an INJECTED value" implied provenance it lacks | **FIXED** |
| validator **MINOR-4** — `main()`'s documented exit contract missed a third shape | **FIXED** |
| validator **F12** — the builder's docstring never mentioned its two new required keywords | **FIXED** |
| validator **MINOR-2** — paraphrased echo survives | **RECORDED U304**, pinned by a current-behaviour test |
| spec-audit **F4** — real provider document shape unread | **RECORDED U305**, owner = `.live` |
| validator **MINOR-3** / F6 — "EXACT token" is case-insensitive | **FIXED** (docstring) + **pinned by a new test** |
| validator **F8** — "fails closed twice over" overstates a fail-open default | **RECORDED U306** |
| spec-audit **F10** — four implementations of "does this parse" | **RECORDED U307** |
| spec-audit **F11** — the terms literal is not provider-scoped | **RECORDED U308** |
| validator — `ruff` unavailable, so the ruff-clean rule is unchecked | **RECORDED U309** |

Neither reviewer's verdict was softened and neither was re-run after remediation to obtain a nicer
one. The suite, the JS suite and the mutation harness WERE re-run after every change above, and their
figures in §5 are post-remediation.

## 7. The measurement script, reproduced

`docs/loop/logs/` is gitignored, so the script below would not survive this session. It is reproduced
here so §2's transcript is checkable by a reader who has only the repo. The permanent guard against
both holes is `tools/mutation/_op18e_hardening_mutations.py` (H1–H4, H8–H9), not this script.

```python
"""U238 before/after: the same shapes, judged by the pre-fix and post-fix acceptance.

The BEFORE half restores the two SHIPPED behaviours in-process (monkeypatch, no file edits) so
this can be run on the fixed tree without touching a product file: `_token_answered`'s
whitespace-collapse fold, and acceptance reading the best-effort extractor.
"""
import json
import sys

sys.path.insert(0, ".")
from tools.providers import frontier_provider_recon as R  # noqa: E402

T = R.GROK_PROBE_TOKEN

H1 = ["Reply with exactly:" + T,
      "Reply with exactly - " + T,
      '"Reply with exactly: ' + T + '"',
      "R e p l y  w i t h  e x a c t l y :  " + T,
      "Reply-with-exactly: " + T,
      "Reply with exactly:  ->  " + T,
      "**Reply with exactly:** " + T]
H2 = [{"status": "done", "debug": T},
      {"debug": T},
      {"foo": {"bar": T}},
      {"trace": [T]},
      {"result": None, "echoed_argv": ["grok", "-p", T]},
      {"metadata": {"probe_token": T}, "result": ""}]
ANSWERS = [T, "Sure - " + T, "Done. " + T + " (as requested)"]


def report(tag):
    print("=== %s ===" % tag)
    print("-- hole 1: echo normalisation (every row is PURE ECHO - the CLI answered nothing) --")
    for c in H1:
        v = R.accept_probe(R.GROK_PROVIDER, T, exit_code=0, stdout=json.dumps({"result": c}),
                           git_status_before="x", git_status_after="x")
        print("   ", "ACCEPTED" if v.accepted else "refused ", repr(c[:52]))
    print("-- hole 2: whole-document fallback (no recognised response field carries the token) --")
    for d in H2:
        v = R.accept_probe(R.GROK_PROVIDER, T, exit_code=0, stdout=json.dumps(d),
                           git_status_before="x", git_status_after="x")
        print("   ", "ACCEPTED" if v.accepted else "refused ", json.dumps(d))
    print("-- control: genuine answers, which must stay ACCEPTED on both sides --")
    for a in ANSWERS:
        v = R.accept_probe(R.GROK_PROVIDER, T, exit_code=0, stdout=json.dumps({"result": a}),
                           git_status_before="x", git_status_after="x")
        print("   ", "ACCEPTED" if v.accepted else "refused ", repr(a))


def old_token_answered(response, token, echoed_prompt):
    def norm(s):
        return " ".join((s or "").split()).casefold()
    n_r, n_t, n_p = norm(response), norm(token), norm(echoed_prompt)
    if not n_t or n_t not in n_r:
        return False
    if n_p == n_t:
        return True
    return n_t in n_r.replace(n_p, " ")


_strict, _tok = R.extract_probe_response_field, R._token_answered
R.extract_probe_response_field = R.extract_probe_text
R._token_answered = old_token_answered
report("BEFORE - the tree the operator armed 18E on")
R.extract_probe_response_field, R._token_answered = _strict, _tok
print()
report("AFTER - this unit's tree")
```

## 8. Prohibitions and constraints honoured

* **§2.4 / live scope** — zero live provider calls. This unit invoked no CLI. The one time a real
  `grok models` was nearly spent (writing a control test), the suite's live-call guard refused it and
  the test was made host-free instead.
* **§2.2 credentials** — none read, stored, or transmitted. No credential name carries a value
  anywhere in this unit's diff.
* **D-LOOP-1** — no live node was spawned, so none was left running.
* **D-LOOP-2 (print-mode)** — both reviewers and all three suites ran in the FOREGROUND inside the
  turn that used their results. Nothing was left in flight.
* **`config/live_operation.json`** — never written, never committed. Verified by a digest comparison
  across the registration report, which now measures "untouched" rather than "does not contain".
* **Canonical set** — untouched. **Registers** — appended only.
* **`tools/loop/run_loop.ps1`** — not modified (OP-12 untouchable set).

## 9. What remains in 18E

| Sub-step | Content |
|---|---|
| `phase-18e.hardening` | **THIS UNIT — DONE.** U238 both holes, §17.2(3) gate inputs, U303. |
| `phase-18e.live` | §17.2(1): the LIVE per-provider in-Electron acceptance leg — picker selection → supervised ConPTY pane as a registered Sovereign node → verified exact provider+model → ONE harmless prompt → live response → teardown → lease 0 → credential-sentinel scan of every sink that now exists (PTY transcript and child env included) → durable ledger consistency. ONE live exchange per provider, no simultaneous same-provider sessions. **U305 is this unit's first order of business.** |
| `phase-18e.close` | §17.2(3)/(4): whole-track reviews, `PHASE18E_EVIDENCE_REPORT.md`, Phase-18 addendum supplement, tag `gate/phase-18e`, successor tag `product/multi-frontier-v2` (§17.1 — the existing `product/multi-frontier` is never moved). |
