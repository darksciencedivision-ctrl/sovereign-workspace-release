# PHASE 18D — `.amendment` sub-step checkpoint

**Status:** the sub-step is DONE and both mandatory reviewers have now run on it.
`gate/phase-18d` does **not** exist and this unit did not create it.
**Work commit:** `c40c1e3` (prior turn) · **remediation + reviews:** this unit.
**Authority:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §17.1 — operator ruling **OP-12.1** (2026-08-01),
U227 resolved by successor schema.

This file exists because subagent output does not survive a print-mode turn (U226, D-LOOP-2) and
because `docs/registers/DECISION_REGISTER.md`'s OP-12.1 row cites it. The 18D gate-validator
(MEDIUM-1) and spec-auditor (M-2) both flagged that citation as dangling at `c40c1e3`: the register
row landed in the work commit naming an evidence artifact no commit had produced. It is produced
here.

---

## 1. What this sub-step was, and what it deliberately was not

`phase-18d` as the directive §17.1 defines it is four things: the amendment, the registration of
both providers as Sovereign nodes, the 18C legs previously skipped on the registration fence, and
the gate. Following §3's allowance for a named sub-step as a work unit, it is split:

| Sub-step | Content | State |
|---|---|---|
| `phase-18d.amendment` | `node@1.1` beside the frozen `@1.0`; the freeze manifest extended additively; `NodeRegistry.register`'s vocabulary derived as the union over schema versions | **DONE** — `c40c1e3`, reviewed and remediated in this unit |
| `phase-18d.close` | register both providers as Sovereign nodes; re-run the 18C legs skipped on the old fence (entry conditions unchanged); whole-track reviews; evidence report; D-P16-0 in-Electron receipt; the gate and its tag | **NEXT** |

**Not claimed by `.amendment`, and still true after this unit:** no node record for either provider
has been created; no live call has been made; the 18C legs skipped on the old fence are still
skipped. The vocabulary is open. Nothing is wired to write into it.

---

## 2. Reviews — foreground, in-turn, concurrent, on `c40c1e3`

Both mandatory reviewers were run synchronously inside one turn (D-LOOP-2: a background review does
not survive a print-mode turn, and a "review in flight" recorded in loop state is dead).

**gate-validator: PASS_WITH_RESERVATIONS.** All six §17.1 exit criteria satisfied on evidence the
validator produced itself. 27 mutations run, 23 RED. It independently reproduced the U293 defect on
this Windows host — reverting `sorted_files()` at the `SETS` site and running the tool for real
produced `A97DD85C…` and reset `operator_signature.status` to `PENDING` — and confirmed the fix
reproduces `8E604CA3…` byte-for-byte with the signature intact. Every suite number the work commit
reported reproduced exactly. Reservations: 1 MAJOR, 3 MEDIUM, 6 MINOR, 4 NIT.

**spec-auditor: PROHIBITED DRIFT — NONE. No invariant violated.** 3 MEDIUM, 6 MINOR, 5 NIT. It
recorded its own verification limit honestly (read-only, no shell: it could not run `git show`,
the suites, or the manifest tool, and said so before its findings). Invariants it checked and found
CLEAN: 1, 2/I-C1, 3, 4, 7, 10, 11, 12, 13, 16, 19/20, 21, I-SC1, 27, 29, 30, the Decimal rule, and
the Phase-0 freeze contract.

Both independently found the same central class: **the boundary moved and some of the prose that
described it did not.**

---

## 3. Findings and dispositions — every BLOCKING/MAJOR/MEDIUM fixed in this unit

| # | Finding | Source | Disposition |
|---|---|---|---|
| **MAJOR-1** | The work commit claimed the stale "U227 is operator-reserved / no record can exist" prose was "corrected in all nine places it lived". **Seven more remained**, three flatly false — including `tools/providers/frontier_provider_recon.py:648` ("could never pass … **and never will**") fifty lines above the text the same commit corrected, and the operator-facing `run_frontier_providers.ps1` help. | validator | **FIXED** in all eight live sites (the seven + `config/live_operation.example.json`), and **mechanised**: `tests/unit/test_u227_prose_is_not_stale.py` |
| **M-1** | `config/live_operation.example.json` — the file an operator reads while deciding to authorize live operation, whose own comment invokes invariant 1 ("final authority has to be INFORMED authority") — still said "OPEN, operator-reserved", "no schema-valid node RECORD can name them", "the canonical node-record vocabulary is unchanged". All three false. | spec-audit | **FIXED** — the comment now quotes what it is correcting and states what the ruling did and did not do |
| **MEDIUM-1 / M-2** | The `DECISION_REGISTER` OP-12.1 row cited `docs/evidence/PHASE18D_AMENDMENT_CHECKPOINT.md`, which no commit had produced. Registers are append-only, so a dangling citation is permanent unless answered. | both | **FIXED** — this file |
| **MEDIUM-2** | The U293 register entry claimed a regeneration would also have "printed `FREEZE DRIFT DETECTED` for eleven canonical documents". Measurably false: `--check` compares a DICT keyed by path and is order-independent. The signature-reset half is true and was reproduced. | validator | **FIXED** by APPENDED correction (append-only register: the row stands, the retraction is appended) |
| **MEDIUM-3** | The shipped `OWED` constants had **no** red-able test. Replacing `OWED.provider_node_record` with "a Sovereign node record EXISTS for both providers and the 18C legs are unblocked" left all three suites green — the rules ran only at in-Electron emit time and every test used a synthetic fixture. | validator | **FIXED** — `apps/desktop/test/op12-acceptance-owed-shipped.test.js` points the existing rules at the shipped object and adds an over-claim rule (mutation M9 → RED). Residual class recorded as **U296** |
| **M-3** | Amendment attribution was **asserted, never authenticated**: `AMENDMENT_AUTHORIZATIONS` is free text and nothing checked the cited ruling exists. A future change could add a successor schema, invent "OP-13.2", add a `NODE_SCHEMA_VERSIONS` row and regenerate — every check green, the vocabulary widened with no operator act behind it. | spec-audit | **FIXED** — `attribution_for()` requires the ruling id to be findable in `AUTONOMOUS_BUILD_DIRECTIVE.md` or the `DECISION_REGISTER`; otherwise `UNATTRIBUTED (ruling X is recorded in none of …)` and `--check` fails closed |
| MINOR-1 | The U293 fix landed at three call sites and was pinned at one. | validator | **FIXED** — `test_every_glob_collection_site_uses_the_platform_independent_key` checks the parsed source, so it goes red on either platform |
| MINOR-2 | `_schema_adapter_enum()` had no product caller; every test asserted on it while the fence read `adapter_version_map()`, so widening the wrapper left the fence untouched. | validator | **FIXED** — wrapper deleted, tests re-pointed at the function `register()` calls |
| MINOR-4 | The re-declaration grep covered 4 of 11 enum members. | validator | **FIXED** — an AST check over all members; robust to the docstring that legitimately discusses `ollama_local`/`ollama_direct` by name |
| MINOR-5 | Untracked builder scratch (`.gvtmp/`, `docs/loop/.commitmsg-18d-work.txt`) left in the tree; neither ignored, both swept up by a later `git add -A`. | validator | **FIXED** — removed; the mutation battery promoted to `tools/mutation/_op18d_amendment_mutations.py` |
| m-4 / m-5 / NIT-1 | `--check` published `amendment_integrity_sha256` and `freeze_integrity_sha256` without verifying either, and never compared the recorded `authorized_by`. | both | **FIXED** — all three verified; mutations M5/M6 → RED |
| m-7 | `ADAPTER_EXEMPTIONS == frozenset()` was asserted only incidentally, inside a test about `ollama_local`. | spec-audit | **FIXED** — its own named test, stating why an empty set is the assertion |
| m-8 | `node@1.1`'s new description sentence claimed enforcement `NodeRegistry.register` does not perform. | spec-audit | **FIXED** — the description now names WHERE each refusal lives and says registration is not, and must never become, the only gate |
| m-9 | `test_an_unattributed_amendment_file_is_itself_drift` never planted a file and never ran `--check`, while its neighbour did exactly that. | spec-audit | **FIXED** — it plants one and runs `--check` end to end |
| n-11 | The `NODE_SCHEMA_VERSIONS` comment omitted the third and only behaviour-changing act (adding the tuple row). | spec-audit | **FIXED** |
| MINOR-6 | The sole record of OP-12.1 — `AUTONOMOUS_BUILD_DIRECTIVE.md` — is covered by no hash, while `CLAUDE.md` and the hooks are. | validator | **RECORDED, not fixed — U294.** Adding it to `EXTRA` would move `freeze_integrity_sha256` and reset the operator's signature: the exact U222 failure the amendment block was built to avoid. The correct fix is an operator-facing decision about what the operator signs. Partial mitigation: the citation is now authenticated against that file |
| MINOR-3, n-10, n-12, n-13, n-14, NIT-2/3/4 | Consistency notes, an awkward `schema_amendments.schema_amendments` nesting, per-call schema re-reads, a test name that reads like a product fact. | both | **ACKNOWLEDGED, not changed.** None is a false claim or an unguarded decision; each is noted here rather than acted on, so the next unit inherits them explicitly |

Two GREEN mutation results are worth as much as the RED ones:

- The validator's **D1b** (over-claim in the shipped OWED block) was GREEN across all three suites —
  that GREEN is what MEDIUM-3 is, and it is now RED.
- The prose detector **caught its own harness.** Promoting the mutation battery from scratch into
  `tools/mutation/` put its M8 payload — a deliberately stale sentence — onto a scanned live
  surface, and the suite went red naming the file and line. The payload stays; the entry now states
  the ruling within sight of the claim, exactly as the rule requires of every other surface.
- This unit's own **M8**, first placed in `control_plane/nodes/pane_picker.py`, was GREEN: that file
  already names OP-12.1 eleven lines away, and the ±12-line window cannot distinguish "the
  correction is right here" from "a correction happens to be nearby". Re-placed in a neutral file it
  goes RED. The limitation is recorded as **U295** rather than smoothed over, because widening the
  window makes it worse and requiring the ruling on the same line would reject the multi-line
  docstring corrections that are the honest form.

---

## 4. Verification — commands run in this unit, foreground

| Check | Command | Result |
|---|---|---|
| Python suite | `py -3.12 -m pytest tests/ -q` | **1993 passed, 1 skipped** (was 1978/1; +15 new) |
| Desktop suite | `npm test` in `apps/desktop` | **695 pass, 0 fail** (was 692; +3) |
| Terminal suite | `node --test terminal/test/*.test.js` | **216 pass, 0 fail** |
| Pane-input falsification | `npm run test:falsify` | **ALL MUTATIONS CAUGHT**, `main.js` restored byte-identical |
| Authority falsification | `npm run test:falsify:authority` | **ALL 11 MUTATIONS CAUGHT**, all files restored byte-identical |
| This unit's mutations | `py -3.12 tools/mutation/_op18d_amendment_mutations.py` | **9 RED / 9, every restore byte-identical** |
| Lint | `py -3.12 -m pyflakes` on every touched Python file | clean |
| Freeze | `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK`; the only INFO is the expected append-only register change |
| Freeze regeneration | `py -3.12 tools/manifest/compute_manifest.py` | `freeze_integrity_sha256 = 8E604CA3…` (byte-identical to Phase 0), `operator_signature.status = SATISFIED_BY_OPERATOR_RULING` |

**One defect this unit caused and caught before committing:** editing files through Python's
`write_text` on Windows rewrote four of them — including `schemas/node.schema@1.1.json` — entirely
in CRLF, in a repo whose every tracked file is LF. `--check` passed anyway, because the manifest had
just been regenerated from those same CRLF bytes: the recorded hash and the file agreed with each
other and would have disagreed with every fresh clone. This is the U274 class, and the tell was
git's `CRLF will be replaced by LF` warning at `git add`, not any test. All four normalised to LF
and the manifest regenerated from the corrected bytes.

The manifest was regenerated in this unit because `node@1.1`'s `description` changed (m-8). The
amendment block's hash moved; **the freeze hash and the operator signature did not** — which is the
separation the amendment block exists to provide, now demonstrated by a second, independent edit
rather than argued from the first.

**No live call was made and none was needed.** The operator's live switch cites OP-6, so both OP-12
providers remain DENIED. Nothing was spawned; nothing outlived the unit (D-LOOP-1).

---

## 5. What `phase-18d.close` inherits

1. **Register both providers as Sovereign nodes** — the vocabulary admits them; no caller creates a
   record. `GovernedProbeSession.node_registered` is still `False`, now a fact about that module.
2. **The 18C legs skipped on the old fence**, re-run under the amended vocabulary. Entry conditions
   are unchanged and still the operator's: each CLI's own login, and their own edit to the
   never-committed `config/live_operation.json` (which, per U237, only takes effect alongside the
   code-pinned scope shipped at 18B). Unmet ⇒ skip-with-record, not failure.
3. **Whole-track reviews** (mandatory gate-validator + spec-auditor — 18D is high-stakes), the
   evidence report in Directive §6 format, the D-P16-0 in-Electron receipt, the gate register row,
   and the tag. Per §17.1, `product/multi-frontier` is never moved: a successor tag only.
4. **Open rows this unit added:** U294 (the authorization document is unhashed — OPERATOR), U295
   (the prose detector's limits), U296 (shipped honesty constants guarded only where a test points
   at them). U293's retraction is appended above its original row.
