# Correction to `PHASE19_UNIT1_OP13_REVERT_CHECKPOINT.md` — round 2 of the reviews

Evidence reports are append-only (directive §2.6), so this file corrects the checkpoint rather than
editing it. It records what the **second** foreground pass of the two mandatory reviewers found, on
the remediated tree (`0f81a6e`), and what was done about each finding.

**Round-2 verdicts: gate-validator PASS** (four enumerated reservations, none blocking).
**spec-auditor: PROHIBITED DRIFT NONE, no MAJOR** (3 MEDIUM, 5 MINOR, 4 NIT), with the standing
pre-existing I-7 violation correctly attributed to **U326**, which is unit 19.2's work and not this
unit's. Both reviewers independently reproduced the suite (2272 passed) and the mutation harness
(12/12 RED), and both independently confirmed the restored comments are verbatim, the registers are
append-only additions, the untouchable set is intact, and no tag was created or moved.

## 1. Corrections to statements in the checkpoint

| Checkpoint said | Correction |
|---|---|
| §3: *"Every mutation row restores code that was actually shipped at `b109f02`… one row, M6, inlines the literal"* | **Overstated.** Four rows depart from byte-exact restoration, not one: **M2** is signature-only and produces a state never shipped; **M7/M8** are single-factor mutations of the *current* line (isolating one flag each) rather than the shipped line that moved two; **M9/M10** inline literals or re-flow prose because the constants and line structure they used are gone. Each still reproduces the defect it names — the substance held, the sentence did not. The harness docstring now says this at the top and at each row (gate-validator MEDIUM-2, spec-audit MINOR-4). |
| §4 / `worker_pane_spawn.py`: the note derivation cannot be wrong *"in either direction"* | **False as first written, true now.** The first deriver rendered an ENUMERATED set of flags, so it could not over-claim but could silently omit — and the flags it would have omitted include `--allow` and `--no-plan`, i.e. exactly the half of the widening this unit reverted. The gate-validator proved it: dropping the mode flags from the set left the entire 2272-test suite green. Fixed in round 2 by inverting the list (`_NOTE_SILENT_FLAGS` — everything else is disclosed by default) and adding `test_the_note_omits_no_flag_the_argv_carries`, which walks argv → note. Mutation row **M12** now goes RED on exactly the gate-validator's mutation. |
| §4/§5: the note *"is what the receipts and the shell chrome show the operator"* | **The chrome half is unsupported.** The note is written into the launch ticket (`tools/live/emit_worker_launch.py`), and the spec-auditor found no renderer path that consumes `launch.note` and no receipt on disk carrying one. The accurate statement is: the note travels in the ticket, which is the record the receipts are built from and the surface an operator-facing reader would use. The *finding* is unchanged — a ticket that describes itself falsely is a defect whether or not a pixel currently shows it — but the checkpoint enlarged it (spec-audit MINOR-7). |
| §4's disposition list | **Incomplete.** It enumerated MAJOR-1..4, MEDIUM-6, MINOR-1 and the deferred NITs, and omitted round 1's MEDIUM-1 (registers uncommitted at `c5078bf`) and MEDIUM-2 / MINOR-7 / MINOR-8. All four were in fact discharged in `0f81a6e` — the registers and the checkpoint are committed there, the T2 residue section and the harness numbering note are in the tree — but a reader could not establish that from §4, which is the property §4 exists to provide (gate-validator MINOR-3, spec-audit MINOR-5). |
| §preamble: *"the remediation commit recorded in §5 below"* | §5 records no commit id. It is **`0f81a6e`**; this round's is recorded in the register row that cites this file (spec-audit MINOR-6). |

## 2. A finding that rests on a mistaken premise, corrected in the other direction

The spec-auditor's **MEDIUM-3** reads U340 as having been *rewritten in place* in violation of
append-only, inferring it from the entry's own account of a first call that was overturned.

**That did not happen.** The first U340 text — the open-and-kept draft — was written into the
working tree and **never committed**: the reviewers ran on `c5078bf`, which contains no register
change at all (that is round 1's own MEDIUM-1). `git log -S "U340" -- docs/registers/UNRESOLVED_ISSUE_REGISTER.md`
returns exactly one commit, `0f81a6e`. So the committed register has one U340 section, appended once,
which narrates a reversal that happened before anything shipped. Nothing was edited away, and the
alternative the auditor proposed (append the reversal as a successor section) would have appended a
correction to text no reader could ever have seen.

The auditor could not run git in that session and said so; the inference was reasonable from the body
text alone, and the body text is what made it reasonable. This correction is recorded so a later
reader does not re-derive the same wrong conclusion from the same sentence.

## 3. What round 2 changed in the code

* `describe_pinned_flags` now works from an **exclusion** list (`_NOTE_SILENT_FLAGS` = the model
  slug and the prompt/output plumbing). A flag nobody enumerated — the next provider's `--allow`
  equivalent — is disclosed by default instead of silently dropped. Disclosure that fails open is
  not disclosure.
* The workspace comparison strips both sides, so a padded path is still redacted rather than printed
  into operator-facing text (spec-audit MINOR-8).
* `test_worker_ticket_honesty.py`: the reverse-direction property added; the workspace-redaction
  test parametrized over both providers (it was Grok-only); one vacuous assertion — a hyphen-stripped
  haystack can never contain `accept-edits` — replaced with the two checks it was pretending to be
  (gate-validator MINOR-1/2, spec-audit MINOR-8).
* Mutation rows **M12** (the note deriver reverts to an omitting inclusion list) and **M13** (the
  *Grok* note reverts to hand-written prose — M10's missing twin) added. Neither restores shipped
  code, because the deriver never shipped; both name the exact defect a reviewer demonstrated.

## 4. Evidence for this round

| Command | Result |
|---|---|
| `py -3.12 tools/mutation/_op13_permission_mode_mutations.py` | **14/14 RED, all restores byte-identical** |
| `py -3.12 -m pytest tests/ -q` (round-2 tree) | **2275 passed, 1 skipped, 625.05s** |
| gate-validator round 2, independent | **PASS**; own suite run 2272 passed / 1 skipped / 635.81s on `0f81a6e`; own harness run 12/12 RED; four self-authored mutations, two RED and two GREEN — both GREENs are the omission direction, now closed by M12 |
| spec-auditor round 2, independent | **PROHIBITED DRIFT NONE; no MAJOR**; no invariant violated by this unit |

## 5. Carried forward, not closed here

* **U341 stays OPEN.** The `claude` and `codex` launch notes are still prose. They are not known to
  be wrong; they are simply not derived, which is the property that failed. Owner: unit 19.10.
* **The MCP-attachment claim is an owed measurement (spec-audit MEDIUM-2).** The code and U340 say a
  Grok pane still reaches Sovereign MCP because `.grok/config.toml` declares the server. Nothing has
  observed that: no Grok pane has completed a session, and the installed capture documents
  `~/.grok/config.toml` for `[ui]` keys without stating that a project-local file's `mcp_servers`
  block is honoured. The auditor is right that this is the same species of unverified present-tense
  claim the unit removed elsewhere. **It is not an argument to restore `--allow`** — the revert
  stands on invariant 1 and 7 — it is an argument that OP-12 pane attachment is unmeasured. Recorded
  as **U342**, owner: the first live Grok pane leg.
* **A live Grok pane will now likely raise a permission prompt on its first Sovereign MCP call**, and
  **U328** (panes written to blind while a modal is up) is open and owned by unit 19.3. That is the
  fail-closed direction and the operator's ruled preference, and the sequencing is OP-13.1's: the
  blocking findings are fixed before the live run.
* **NIT-11** — `tools/loop/run_loop.ps1` invokes the build agent with `--permission-mode acceptEdits`.
  That file is in Phase 19's untouchable set by name. Out of scope, the operator's call, recorded
  twice now so it is not mistaken for an oversight.
* **D-P19-1 says "8/8 RED"** against a harness that is now 14 rows. Append-only forbids editing it;
  the correction is here and in the successor decision row, per this register's own precedent.
