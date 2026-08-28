# PHASE 18E `.live.shape` — CHECKPOINT EVIDENCE (no gate)

**Unit:** `phase-18e.live.shape` — the first order of business of the `.live` sub-step, per the
iteration-114 loop note and directive §17.2(1).
**Status:** COMPLETE as a checkpoint. **`gate/phase-18e` does not exist and this unit did not
create it.** The in-Electron per-provider acceptance leg — the rest of `.live` — is NOT done.
**Authorization:** OP-12 / OP-12.2 (directive §17, §17.2). Live probes are §17's own acceptance
element — and §17's wording is "**exactly one** harmless live probe per provider", which **this
unit exceeded for `grok_build`**: it spent two. That is disclosed here, in §7, and in **U312**, and
it is flagged as **operator-reserved** rather than resolved by builder rationale. Both reviewers
raised it independently (validator MEDIUM-6, auditor MEDIUM-4) and both were right to: an app that
writes itself a spend allowance over an operator-costed resource has invented a governance layer
(invariants 1 and 30). The second exchange bought a refutation that PREVENTED a widening, which is
an argument for the operator to weigh — not a permission this unit had.

---

## 1. Why this unit exists, and why it is only this

The iteration-114 note handed the `.live` unit one instruction before anything else:

> **U305 IS THAT UNIT'S FIRST ORDER OF BUSINESS:** neither provider's real `-p --output-format
> json` document has ever been read against the new strict reader, so if a CLI nests its answer,
> acceptance will REFUSE a genuine live reply — safe direction, but capture the document shape
> BEFORE concluding anything about a provider.

That instruction earned its place. Acting on it produced a finding that changes what the rest of
`.live` can claim, and it would have been invisible to an in-Electron leg that only reported
pass/fail. `.live` is therefore split: this checkpoint answers U305; the in-Electron acceptance leg
is the next unit. Splitting a large sub-step is directive §3's allowance, and the split is recorded
here rather than assumed.

## 2. The instrument: `describe_provider_document`

`adapters/frontier/provider_cli_common.py`. It answers the question a verdict cannot:
`accepted:false, token_seen:false` reads identically whether the model said nothing or said it
somewhere the reader does not look, and those two facts point in opposite directions.

It reports **structure and never a string or numeric LEAF VALUE** — top-level type, key names,
per-key types, dotted paths to every string and number leaf, which of `PROVIDER_RESPONSE_KEYS` the
strict reader matched, every path at which the probe token appears, and whether the strict reader
can see it. That is a credential-isolation property (§2.2/§13), not a convenience: a shape record is
published to `docs/evidence/live/`, and a describer that copied string values would publish whatever
the CLI put in them.

**"Never a value" was the first draft's wording and it was too wide.** Key names ARE reported, and a
key name is provider-controlled data rather than schema — this unit's own evidence proves it, since
`modelUsage.grok-4.5.costUSD` puts a model identifier in a key position, and a CLI is equally free
to key a map by account or session. Both reviewers found it (validator MEDIUM-5, auditor MEDIUM-1).
Key names now go through `redact_diagnostics` — the same `SECRET_PATTERNS` every other evidence
surface in the module uses — and are length-bounded; what survives is a provider-controlled string
in a published artifact and the docstring now says so. Measuring that also exposed a real gap in the
shared redactor: `sk-[A-Za-z0-9_]{16,}` excluded hyphens, so `sk-proj-…`-shaped keys matched four
characters and passed through. Widened to admit `-` — strictly more redaction, never less.

One deliberate exception makes the instrument useful: the `skeleton` field is the same document with
every string leaf replaced by a `<str:LEN>` placeholder **except** strings containing the probe
token, which become the token. The skeleton is a **replayable fixture** carrying no model prose —
and the replay property is narrower than that sentence, in two ways that are now tested rather than
assumed:

- it holds for `extract_provider_response_field` **only**, never for `accept_probe`: substituting
  the bare token deletes the prose echo subtraction exists to remove, so a pure echo (REFUSED)
  skeletonises into an ACCEPTED document. A skeleton is not a fixture for an echo test — that is
  U238/U304 territory (validator MEDIUM-7);
- under truncation it does not hold at all, and it now fails **closed**: a truncated value becomes
  `null`, which no reader matches, so a truncated skeleton can lose a response the original had and
  never invent one. It previously became `"<truncated>"` — a non-empty string, i.e. the blankness
  inversion below by another route (validator MEDIUM-3).

Bounded by construction (`max_nodes`, `max_depth`), with `truncated` saying so: a CLI's document is
untrusted input (T2), and a partial description must not be published as a whole one. The bound now
covers the key inventory and the skeleton's own key count too — `top_level_keys`/`key_types` were
built outside the walk and could enumerate 50,000 provider-chosen keys beside `truncated: true`
(validator MEDIUM-4).

Wired into `run_probe`'s verdict as `document_shape` on every probe that **reached a child**,
including accepted ones — where it is the positive record that the document really is the flat shape
the reader was built for. Gate-denied and session-refused probes return before the field exists,
which is correct: nothing was read (validator NIT-14).

## 3. What the live probes measured

Two governed live probes, 2026-08-02T02:19:24Z, through the supervised I-X3-leased path. Emitted to
`docs/evidence/live/phase18e_probe_document_shape_20260802T0219Z.json`.

> **Read that artifact with its correction.** Its Grok `skeleton` carries `"text": "<str:0>"` — the
> pre-fix rendering of an empty string, published because the S1 fix landed BETWEEN the two live
> runs and the artifact was never regenerated. Replayed, it inverts this section's finding. The
> artifact is preserved unedited and corrected in place by
> `phase18e_probe_document_shape_20260802T0219Z.CORRECTION.md`, which also lists the fields that
> are unaffected — including every field this section's conclusions actually rest on. Found by both
> round-1 reviewers (validator MAJOR-1/2, auditor MAJOR-1); an earlier draft of §3.2 below printed
> the intended output while citing the emitted one.

### 3.1 `google_antigravity` — flat, recognised, ACCEPTED

```json
{"conversation_id": "<str:36>", "status": "<str:7>", "response": "GEMINI_PROVIDER_OK",
 "duration_seconds": 0, "num_turns": 0,
 "usage": {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
           "cache_read_tokens": 0, "total_tokens": 0}}
```

`response_key_matched: "response"`, `token_paths: ["response"]`,
`token_visible_to_strict_reader: true`. **The feared nesting does not exist here.** The acceptance
is real and is now the first one earned under the strict reader.

### 3.2 `grok_build` — exit ZERO, and the CLI said NOTHING

```json
// the skeleton AS PUBLISHED in …0219Z.json — `"<str:0>"` is the S1 defect; see the CORRECTION
{"text": "<str:0>", "stopReason": "<str:9>", "sessionId": "<str:36>", "requestId": "<str:36>",
 "thought": "GROK_PROVIDER_OK",
 "usage": {…}, "num_turns": 0, "total_cost_usd": 0, "total_cost_usd_ticks": 0,
 "modelUsage": {"grok-4.5": {…}}}

// the same document rendered by the FIXED describer, as published in …0224Z.json
{"text": "", "stopReason": "<str:9>", …}
```

`stopReason` is `"cancelled"`. `text` — a **recognised** response key — is EMPTY in the real
document; the artifact's own `response_excerpt` and `outcome.detail` show `"text": ""` verbatim, and
`response_key_matched: null` / `strict_response_found: false` / `token_paths: ["thought"]` are all
computed from the real document rather than the skeleton, so this section's conclusion rests on
fields the defect never touched. The token appears
at exactly one path: `thought`, the reasoning trace, whose real content is *"The user wants me to
reply with exactly \"GROK_PROVIDER_OK\". This is a simple request with no tools needed."* — the
model restating the instruction to itself.

**So U305's fear is not what happened, and the difference matters.** This is not a genuine answer
the strict reader cannot see; it is a document in which the model did not answer. The reader's `""`
is CORRECT. **No nested-answer accommodation was added**, because adding one on this evidence would
have widened acceptance to admit a document that says nothing — the U238 hole, re-opened by the very
unit sent to verify its closure.

## 4. The hypothesis that was tested and refuted

The obvious reading of `stopReason: cancelled` was that `--permission-mode plan` has no approval
channel in a single-turn run, so the turn is cancelled when the agent tries to leave plan mode. That
reading has a cost attached — it would move a pin that exists to stop a node-controlled config
supplying a permissive mode (§11) — so it was tested rather than assumed.

**One further live probe with `--permission-mode default` cancelled IDENTICALLY**
(`docs/evidence/live/phase18e_probe_grok_default_mode_20260802T0224Z.json`: `text: ""`,
`stopReason: cancelled`, token only at `thought`). `default` is the only other value
`FORBIDDEN_PERMISSION_MODES` permits this build to emit, so the experiment exhausted the emittable
space. **That second exchange is the one that exceeded §17's stated cap** — see the Authorization
note above and U312.

**The mode is not the cause, so the pin did not move.** The change was made and then undone **in the
working tree, before any commit** — there is no reverted commit in the history and this document
previously implied one (validator MINOR-11). `git diff 6a8f038..HEAD` over
`adapters/frontier/grok_build.py` and `tools/providers/frontier_provider_recon.py` shows no pinned
value moved: only comments, one docstring, the alias and the `document_shape` wiring. The tree
carries a test (`TestThePinnedModeSurvivedALiveTest`) recording the refutation beside the pin, so
the next reader finds the answer instead of re-spending the call. A widening bought with a refuted
hypothesis is still a widening.

**What was measured, exactly, and what was not.** The live argv was the RECON PROBE's
(`--cwd … --permission-mode … --output-format json -p …`). `GrokCliBackend.build_command` emits a
different argv — it adds `--no-memory` and `-m <slug>` — and has never executed at all
(`_LIVE_SPAWN_PATH_WIRED = False`). The two mode constants are pinned equal by test, so the VALUE
claim transfers; the MEASUREMENT claim is attached one argv over, and `--no-memory` is consequently
absent from U310's suspect list (spec-audit MINOR-4).

The leading untested suspect is named in U310 rather than guessed at here:
`supervised_probe_runner` passes `stdin=subprocess.DEVNULL` (deliberately, U281) and `grok` is
TUI-derived, so immediate EOF is a plausible cancel signal. The counter-evidence that keeps it a
suspect: `agy` ran through the same runner with the same stdin disposition and answered.

## 5. The result this unit withdraws

Directive §17.2 records the world at 18E's arming as the operator's own probe having "succeeded LIVE
for BOTH providers … exact tokens (`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`)". That run predates
the U238 fix, so acceptance called `extract_provider_text`, whose fallback is the whole JSON
document — and the token it found was the one in `thought`.

`test_the_pre_U238_reader_would_have_ACCEPTED_the_grok_document` measures it, and measures the
ACCEPTANCE rather than the reader: it drives `accept_probe` itself with the strict reader swapped
back for the best-effort one and gets `accepted: True`, against `accepted: False` today. Its first
version only asserted that the token appears in `extract_provider_text`, which is a fact about a
reader and not the claim the test's name makes (validator MINOR-10).

**`grok_build`'s live acceptance therefore cannot be relied on.** The honest limit, which both
reviewers pressed and which the register now carries: the operator's own probe document was **never
captured**, so the inference that its token was the one in `thought` comes entirely from two later
same-day runs. Had that run produced a non-empty `text`, the pre-U238 reader would have accepted it
validly. What is measured is that Grok did not answer in either run this unit made, and that the
reader which accepted it would accept a document in which nothing was said.
`google_antigravity`'s acceptance stands and has been re-earned. Recorded as **U311**,
because §17.2's account of the world is what armed this phase and a later reader comparing directive
to evidence must find the discrepancy explained rather than silently superseded. It also converts
U238 from a constructed-example fix into one with a live instance: the hole had already certified a
provider that said nothing.

**Consequence for the next unit:** the Grok leg of the in-Electron acceptance cannot pass until U310
is isolated. An interactive ConPTY pane is a genuinely different channel and may not share the
defect, so that leg is worth attempting on its own evidence rather than presumed dead — but it must
not be reported as a provider success if it is really the same cancellation wearing different
clothes.

## 6. Verification

All figures below are the POST-REMEDIATION run — taken after every round-1 reviewer finding was
fixed or recorded, not before.

| Check | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | **2161 passed, 1 skipped** (was 2117/1 at `.hardening`; +44) |
| `apps/desktop` `npm test` | **751 pass, 0 fail** |
| `node --test terminal/test/*.test.js` | **216 pass, 0 fail** |
| `tools/mutation/_op18e_live_shape_mutations.py` | **11/11 RED, all restores byte-identical** |
| `pyflakes` on every touched file | clean |
| `tools/manifest/compute_manifest.py --check` | freeze check OK, no drift in the FROZEN set |

The mutation harness is the guard that matters here, because **nothing refuses on account of this
instrument** — it informs, so it can lie silently. Three of its eleven rows are worth naming:

- **S1** is a defect this unit caused and caught **while building** — the skeleton mapped `""` to
  `<str:0>`, so the real Grok document became a skeleton whose `text` field READ AS AN ANSWER. The
  fix landed between the two live runs, which is precisely why the first artifact was published
  carrying it (§3 note, and the CORRECTION file).
- **S3** went GREEN on the first run: nothing pinned `token_paths` to the *exact* token, so a
  case-folded match would have named paths the token is not at. A test was added and it is RED.
- **S10/S11/S12** were added at the round-1 review and guard remediations, not the original design.

One row was written and then **removed rather than kept green**: a mutation restoring the old
`"<truncated>"` marker changes no outcome, because S12's dict-branch break drops the key before the
marker can be produced. `return None` is a backstop behind that break, not the primary guard, and a
green row asserting otherwise would have overstated which line does the work.

## 6.1 Round-1 review, and what it changed

Both mandatory reviewers ran **foreground, in-turn, concurrently** (D-LOOP-2) on commit `3d506be`.
Neither verdict was softened and neither reviewer was re-run to obtain a nicer one.

- **gate-validator: FAIL** — on the artifact/prose mismatch (MAJOR-1/2), with every claimed figure
  independently re-measured and confirmed, and the pin claim independently verified as unmoved.
- **spec-auditor: PROHIBITED DRIFT NONE, no invariant violated** — 1 MAJOR, 5 MEDIUM, 5 MINOR,
  4 NIT, concentrated in the honesty surface.

They converged independently on the same MAJOR, and it was real. Dispositions:

| Finding | Disposition |
|---|---|
| MAJOR — published artifact carries the pre-fix skeleton; three documents quote it wrongly | **FIXED**: artifact preserved unedited + `.CORRECTION.md`; §3.2, the test provenance note and the fixture claim corrected |
| MEDIUM — skeleton replay inverts blankness under truncation | **FIXED**: truncated values become `null`; test + mutation S6/S12 |
| MEDIUM — `top_level_keys`/`key_types` (and the skeleton's key count) unbounded | **FIXED**: bounded by the same budget; test + mutations S10/S12 |
| MEDIUM — key names are provider data and were published unredacted | **FIXED**: scrubbed + length-bounded; the docstring's wide claim narrowed; test + mutation S11. Also widened `SECRET_PATTERNS` — `sk-…`/`xai-…` excluded hyphens, so `sk-proj-…` passed through |
| MEDIUM — skeleton launders an echo into an acceptance | **FIXED as a documented limit**: pinned by `test_a_skeleton_is_NOT_a_fixture_for_echo_or_acceptance_tests` |
| MEDIUM — live-exchange overrun, self-authorized | **RECORDED, not resolved**: U312, operator-reserved; the self-authored allowance in U310 removed; the Authorization line corrected |
| MEDIUM — U305 closed by narrowing for Grok | **RECORDED**: the U305 row now separates what is closed outright from what is closed only in the sense that the document was read |
| MEDIUM — U311 overstated | **NARROWED**: the operator's probe document was never captured, so the `thought` attribution is an inference; the claim is now "cannot be relied on", not "disproven" |
| MINOR — pre-U238 test asserted less than its name | **FIXED**: it now drives `accept_probe` with the reader swapped |
| MINOR — "reverted in full" implied a commit that never existed | **FIXED** |
| MINOR — filenames misdated the runs | **FIXED**: both renamed to their real write times |
| MINOR — DECISION_REGISTER row malformed (2 cells in a 4-column table, no evidence column) | **FIXED** |
| MINOR — `RecursionError` escapes the describer | **FIXED** + test |
| MINOR — agy fixture asserted equality the real `"…OK\n"` falsifies | **FIXED**: containment |
| MINOR — measurement recorded on a constant whose argv never ran | **FIXED**: both the comment and U310 now say which argv was measured, and that `--no-memory` is untested |
| MINOR — `document_shape` on a no-child branch reads as "empty document" | **FIXED**: the note now says no provider was contacted |
| NIT — `as_dict` shared the skeleton reference; `token=""` published a true visibility claim | **FIXED** |
| NIT — `<str:LEN>` discloses exact lengths; path aliasing (`{"a.b"}` vs `{"a":{"b"}}`) | **ACCEPTED**: disclosed limits of a structural description, not defects |

## 7. Live spend, and what it bought

Three live exchanges, each answering a question with no offline answer:

| Exchange | Question | Answer | Within §17's stated cap? |
|---|---|---|---|
| `agy` probe | does Antigravity nest its answer? | no — flat `response`, ACCEPTED | yes (1 of 1) |
| `grok` probe (`plan`) | does Grok nest its answer? | no — Grok says nothing at all | yes (1 of 1) |
| `grok` probe (`default`) | is the permission-mode pin the cause? | **no** — pin kept | **NO — see U312** |

The third row is an overrun, not a rounding. §17 says "exactly one harmless live probe per
provider" and OP-12.2 says "ONE live exchange per provider"; this unit spent two on one
subscription. It is recorded as **U312**, operator-reserved, and the register's first draft of U310
carried a self-authored allowance ("one live exchange per hypothesis") which has been **removed** —
an app writing itself a spend rule over an operator-costed resource is an invented governance layer
(invariants 1 and 30), whatever the spend bought.

Teardown measured on every one: `lease_released: true`, `governor_released: true`,
`in_use_after: 0`, `process_tree_clean: true`, `node_exit_recorded: true` (D-LOOP-1). Repository
unchanged before/after on all three (`repo_unchanged: true`). No credential read, stored or
transmitted; the CLIs use their own host-native auth (§2.2).

## 8. What this checkpoint does NOT establish

- **No in-Electron receipt exists for either provider.** No picker selection, no supervised pane, no
  pane teardown, no PTY-transcript credential scan. That is the rest of `.live` and it is owed.
- **No gate is closed.** `gate/phase-18e` is not applied and `product/multi-frontier-v2` is not
  applied; both belong to `.close`.
- **The cause of Grok's cancellation is unknown** (U310). One hypothesis is refuted; the rest are
  untested.
- **The `agy` acceptance is one exchange, one prompt.** It says the document shape is flat and the
  provider answered once — not that it answers reliably, and not anything about an interactive pane.

---

*Checkpoint written at the close of `phase-18e.live.shape`. Next unit: `phase-18e.live.electron` —
the §17.2(1) per-provider in-Electron acceptance leg, with U310 as its first obstacle on the Grok
side.*
