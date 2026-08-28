# Phase 19 · unit 19.2 — U326: authority returns to `control_plane/policy.py`

**Unit:** `phase-19.2` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, U326 / cold-audit finding B1).
**Work commits:** `9c59cb0` (the delegation, on `b529314`), `3e5b4dd` (round-2 remediation),
`65ae5f6` (round-3 remediation) and the round-4 remediation commit named in §7.
**Gate:** none. Phase 19 closes at unit 19.10 with `gate/phase-19`; this is a sub-step
checkpoint, and **no tag was created or moved by this unit** (`product/multi-frontier-v2` still
points at `cd08878`, verified by the round-4 gate-validator).
**Reviewers:** gate-validator and spec-auditor, **foreground, in-turn, concurrently** (D-LOOP-2),
**four rounds**. Rounds 1 and 2 are recorded in §5.1/§5.2, round 3 in §5.3, round 4 in §5.4 —
each written only after that round returned. Nothing in this document is written in the past
tense before it has happened; that was the round-1, round-2 and round-3 MAJOR, three times.
**This unit is NOT closed by this document.** The round-4 remediation post-dates round 4, and
`fix-after-validation voids it` (directive §18) means it owes a fifth round. §7 says exactly what
is owed and what the next unit must do first.

---

## 1. What was asked, and what was done

Unit 19.2, verbatim: *"Route all twelve inline role/permission checks in
`mcp_server/collaboration_service.py` (lines 53, 83, 98, 113, 132, 141, 201, 228, 259, 276, 282,
290) through the policy object it already holds, exactly as `mcp_server/memory_service.py` does
on its nine write paths. `open_debate` uses the existing `control_plane/policy.py:140`
`authorize_debate`. Extend the policy with whatever authorize_* entry points the remaining
operations need — **the new surface goes in `control_plane/`, never in `mcp_server/`.**
Falsification required: a mutation that changes a policy rule must be caught by a test that goes
through the collaboration path, proving the delegation is live and not decorative."*

The directive names twelve lines; the file carried **fifteen** decisions of that class, so three
more moved with them (115 the recipient scope, 146 the debate participant scope, 172 the debate
turn participant). Verified line by line against `git show b529314:mcp_server/collaboration_service.py`:

| Inline check (pre-unit line) | Now asks | Reason string |
|---|---|---|
| 53 create_task role | `authorize_task_create` | only the conductor/operator may create assignments |
| 83 update_task owner | `authorize_task_update` | *(was dead code — §3)* |
| 98 list_tasks worker filter | `authorize_task_read` per row | cross-task access denied |
| 113 send_message participant | `authorize_send_message` | sender is not a participant… *(shadowed — §3)* |
| 115 recipient scope | `authorize_send_message` | cross-task recipient denied |
| 132 read_messages include_all | `authorize_read_task_transcript` + `authorize_message_read` | only the conductor/operator may read a full task transcript |
| 141 open_debate caller | **`authorize_debate` (the pre-existing entry point)** | role … may not request debate |
| 146 debate participant scope | `authorize_open_debate` | debate needs at least two task participants |
| 172 post_debate_turn participant | `authorize_debate_turn` | node is not a debate participant |
| 201 close_debate role | `authorize_debate_close` | only conductor/operator may close a debate |
| 228 record_candidate | `authorize_publish_candidate` | only an assigned worker may publish a candidate |
| 259 record_synthesis role | `authorize_publish_synthesis` | only conductor/operator may publish synthesis |
| 276 list_debates filter | `authorize_debate_read` per row | node is not a debate participant |
| 282 get_debate participant | `authorize_debate_read` (via `_require_debate`) | node is not a debate participant |
| 290 `_require_task` scope | `authorize_task_read` | cross-task access denied |

The audit's own grep now answers the other way: **no role is read anywhere in
`mcp_server/collaboration_service.py`** — asserted by parsing the module (`_role_is_inspected`),
which catches `getattr(identity, "role")` and `details["role"]` as well as attribute access. It
is not unevadable (`"ro" + "le"` defeats any static check), which is why the load-bearing proof
is the injected-policy suite in §4 and not that assertion.

The file's only authority code is `_require(verdict)`, which raises a reason it did not compute.
The three list/read views are filtered BY the policy rather than by a role literal, so a scope
change reaches the views, not only the write paths.

**Two duplicate gates in the same package, not named by the finding, closed with it.**
`mcp_server/sovereign_tools.py:207,245` carried its own copies of the candidate and synthesis
role rules — a third place authority could fork to, inside the package invariant 7 names. Both
now call the policy, and `SovereignToolRuntime` takes that policy as a **required keyword** (the
U292(a) closure shape: no manufactured default), which is what makes the tool layer's delegation
falsifiable by behaviour instead of by reading its source. The candidate gate also got
**stricter**: it asked only *"is this node a worker"*, and now asks the real rule (*an
**assigned** worker*) **before** the candidate artifact is written into CAS —
`test_an_unassigned_worker_is_refused_before_anything_reaches_cas` asserts the CAS directory is
empty after a refusal, because round 2 showed that claim could otherwise be reverted invisibly.

**What is deliberately still in `mcp_server/`, and why (U344).** The bounded-debate round limit
and budget range, the "a debate may not close without a turn from every participant" quorum, the
"synthesis requires candidates from every worker" completeness rule, the `debate is not open`
state gate, the referential checks that a candidate names only messages and debates that exist,
and the CANDIDATE-status check — the last three added to this list by the round-3 reviewers, who
were right that the first enumeration was incomplete. None of them asks *who* the caller is: they
are lifecycle legality, which this package has always held — `memory_service.py` calls `mcp_server/lifecycle.validate_status_transition` and
asks `control_plane.policy` for authority, in that order, and has since Phase 3A. The claim made
here is therefore the narrow one — *no role or scope decision remains* — not "no decision
remains", which the round-2 spec-auditor correctly refuted against the first draft's docstring.

## 2. Behaviour deltas — measured, not asserted

`tools/evaluation/u326_before_after.py` (tracked, and pinned to base `b529314`, because the first
version lived in the gitignored `docs/loop/logs/` and read `HEAD:` — which the act of committing
turned into a comparison of the new module with itself, reporting `0 of 31 scenarios differ`;
both round-2 reviewers caught that, independently) imports the pre-unit module beside the current
one and runs 34 scenarios against both, on fresh stores. The pre-unit copy never called the
policy — that *is* U326 — so importing it beside the current `control_plane/policy.py`
reproduces pre-unit behaviour exactly, and the tool refuses to run against a base that already
delegates.

**Result: `19 of 34 scenarios differ`**, reducing to seven deltas plus two arithmetic
consequences. (Round 2 measured `18 of 33`; the 34th scenario is delta 7, which the round-3
gate-validator found by extending the matrix itself — the honest fix was to measure it here
rather than describe it in prose.)

| # | Delta | Direction | Why |
|---|---|---|---|
| 1 | **`voice` becomes a scoped role — reads AND writes.** `get_task`, `update_task` and `send_message` refuse `cross-task access denied`; `list_tasks`/`list_debates` return empty; `get_debate` refuses. Before, a voice identity could read **and cancel** any task in the project. | fail-closed | Everywhere else in `control_plane/policy.py` (`authorize_publish`, `authorize_transition`) `worker` and `voice` are already paired. The collaboration copy scoped `worker` alone. |
| 2 | **`gate` may now open a debate** (`caller may not open a debate` → succeeds). | widening | Directed: the unit spec ordered `open_debate` to use `authorize_debate`, whose role set is `worker/conductor/gate/operator` (I-DS1 — *any authorized node may request a debate*). `voice` is still refused by both. |
| 3 | **A malformed role is refused where it used to be served.** `get_task`/`get_debate` refuse `unknown role 'hacker'`; the list views return empty; `create_task`'s reason changes. Before, an identity with a role outside `ROLES` read and listed every task and debate in the project. | fail-closed | This unit's own rule, applied uniformly after round 1 found it gated the task rules and not the debate ones. |
| 4 | **Read authority now precedes state disclosure on debates.** A non-participant posting to a CLOSED debate gets `node is not a debate participant` where it used to get `debate is not open`. | fail-closed | `_require_debate` asks `authorize_debate_read` before returning, the ordering `_require_task` always had. Existence *within the caller's own project* is still disclosed by the lookup — the store is keyed by (project, id) — and that is stated rather than claimed closed. |
| 5 | **Reason-string change on `voice open_debate`**: `caller may not open a debate` → `role 'voice' may not request debate`. Same verdict; it is the canonical rule's sentence now. | none | Consequence of delta 2's entry point. |
| 6 | **Validation ordering in `open_debate`**: an empty participant list against a **nonexistent** task returns `a debate requires at least one participant descriptor` instead of `no such task in this project`. | none (fail-closed either way) | `authorize_debate` is asked before the task lookup — deliberately, so a caller with no debate authority learns nothing about the task, which is the order the inline check had. |

| 7 | **A scoped non-owner's `record_synthesis` meets the SCOPE refusal instead of the role refusal.** `worker-out` gets `cross-task access denied` where it used to get `only conductor/operator may publish synthesis`. | fail-closed | The round-2 remediation put `_require_task` in front of `record_synthesis` — the one write path that skipped read authority. Measured only from round 3, because the first matrix had no scoped-non-owner synthesis cell. |

The two remaining DIFF rows (`gate list_debates` 2→3, `cond include_all` 5→4) are arithmetic
consequences of deltas 2 and 1 inside the same scenario run — the gate's new debate exists, the
voice message does not — not independent changes. (Round 2 printed these as 1→2 and 3→2; both
round-3 reviewers checked the arithmetic against the script and both got the pair above. The
reasoning was right and the numbers were stale.)

**Everything else in the 34 measured scenarios is identical**, including every refusal the
fifteen checks existed to produce. One further change is outside the matrix and is stated here:
an unassigned worker's `publish_candidate` refusal now surfaces as `CollaborationError` rather
than `ToolError`, because the tool layer fetches the task through the collaboration service; the
JSON-RPC boundary prints the type name, so the wire text changed.

**`gate` is deliberately not in `_SCOPED_ROLES`**, so a gate identity has project-wide read of
every task and debate *and* debate-open authority. That combination is new in aggregate. It
follows the role's pre-existing treatment (the pre-unit code scoped `worker` only, and the gate
engine is a whole-project reviewer by design). Until round 3 this paragraph said
`test_a_gate_node_directs_nothing` pinned that it "still directs nothing", and **that was an
absolute the shipped code falsifies**: through its project-wide read a gate may `update_task`
(including `CANCELLED`), `send_message` into a task thread, and — new in this unit — open a
debate, which arms every participant's turn timer and spends budget nothing consults (U349). The
test is renamed `test_a_gate_node_is_not_one_of_the_directing_roles` and now asserts both halves:
what a gate may not do (create assignments, close debates, publish synthesis, read another node's
traffic) and what it may. No `gate` or `voice` identity reaches this path today: the only
production `CollaborationService` constructor is `mcp_server/sovereign_tools.py:90` — the second
constructor in the repo is `tools/evaluation/u326_before_after.py`, this section's own measuring
tool, which the round-4 validator was right to point out — and its identity comes from the
application-control channel, which issues `conductor` (`apps/desktop/main.js:875`) and `worker`
(`:1885`), both literal.

## 3. What the relocation exposed: checks that could never fire (U343)

`update_task` and `send_message` both call `_require_task` first, whose scoped-role clause tests
the **same condition** as the check that followed it.

* **`worker may update only an assigned task` was unconditionally dead.** Its condition was
  byte-identical to the read rule's, both route through the same `_scoped()` helper, and widening
  the read scope widens both together — so no input, and no future scope change, can make it
  live. The round-1 draft kept it with the justification *"the read scope may widen"*; the
  gate-validator proved that justification false. **It is not carried forward.**
  `authorize_task_update` is a distinct entry point that returns the read verdict, and
  `TestTheUpdateRuleIsTheReadRule` asserts the two agree for six identities — if update authority
  ever diverges from read authority, it diverges in `control_plane/` and that test is where it
  shows. The consequence, stated plainly because the round-2 auditor was right that it belongs
  next to the rule: an assigned worker may set **any** value in `TASK_STATES`, including
  `ACCEPTED` and `COMPLETED`, through `publish_progress` — that is U346, pre-existing and now
  recorded rather than inherited silently.
* **`sender is not a participant in this task` is shadowed on the service path but LIVE for a
  direct caller** — deleting it changes an observable verdict, which
  `test_the_sender_rule_is_live_for_a_direct_caller` pins. It stays, marked `SHADOWED (U343)`.
* `record_candidate`'s owner half is shadowed the same way; its role half is reachable, which is
  why that rule is not dead — `test_only_the_worker_role_publishes_a_candidate_even_when_assigned`
  pins the half that matters (a `voice` identity named as an owner is still refused; invariant 25),
  and round 3 added the `conductor`-as-owner case, which is the widening direction the voice case
  cannot see.
* **`record_synthesis`'s `_require_task` is a third instance**, found by the round-3
  gate-validator, who was right that the unit owed this call the same analysis it gave the other
  two: only directing roles reach it and neither is scoped, so that read can refuse on
  project/existence and never on authority. It is marked `SHADOWED FOR AUTHORITY (U343)` at the
  call, and it is not decorative — deleting it changes an observable verdict, which
  `test_synthesis_asks_task_read_before_it_publishes` and mutation P26 pin.

No test could previously have told a live rule from a dead one here. That is the same blindness
as B1 itself, and it is a fact about the pre-existing code — **not a defect this unit
introduced**.

## 4. Evidence — real command output

| Command | Result |
|---|---|
| `py -3.12 -m pytest tests/unit/test_collaboration_policy_delegation.py -q` (before implementation, 20 tests) | **7 failed, 13 passed** — the test-first red |
| `py -3.12 -m pytest tests/ -q --durations=10` (round 1, at `9c59cb0`) | **2299 passed, 1 skipped, 634.49s** |
| `py -3.12 tools/mutation/_op19_policy_delegation_mutations.py` (rounds 1 → 2 → 3 → 4) | **17/17 → 23/23 → 29/29 → 34/34 → 37/37 RED**, restores byte-identical every time |
| `py -3.12 -m pytest tests/ -q` (round-2 tree, gate-validator's independent re-run) | **2316 passed, 1 skipped, 609.48s** |
| `py -3.12 -m pytest tests/ -q` (round-3 tree `65ae5f6`, split; validator's independent re-run agreed) | **2329 passed, 1 skipped** |
| `py -3.12 -m pytest tests/ -q` (round-4 remediated tree) | *(§7)* |
| `npm test` in `apps/desktop` | **tests 836 · pass 836 · fail 0 · skipped 0** (verbatim; no JS changed by this unit) |
| `node --test test/*.test.js` in `terminal` | **tests 216 · pass 216 · fail 0 · skipped 0** |
| `py -3.12 tools/evaluation/u326_before_after.py` | **19 of 34 scenarios differ** — the §2 table |

The 20-test red is the file as it stood before implementation; the shipped file has more, because
the tool-layer, permissive-policy, U343 and round-2 classes were written after the first
implementation and after each review. The red is recorded for what it was — the test-first step
on the first twenty — not as a property of the file that shipped.

**The falsification, stated precisely.** The 37 rows are in three groups, and the group is part
of each row's claim:

* **Group A (P1–P16l, except P16)** — one rule changed in `control_plane/policy.py`, graded by a
  test that never mentions the policy: it calls `CollaborationService`. This is the group the unit
  spec demands. It includes the rules **this unit wrote** (`_SCOPED_ROLES`, the uniform
  unknown-role gate), the four membership/floor rules round 2 found unguarded, the four round 3
  found (`authorize_message_read`, the debate read scope, the candidate rule's role half, `ROLES`
  itself) and the three round 4 found (`_DIRECTING_ROLES` toward **voice**, the debate closer's
  identity, `authorize_open_debate`'s subset absorbing the caller). The last three are graded by
  the **verdict matrix** (§7 / U352) rather than by three more one-off tests, for the reason U352
  gives: four rounds of one-off pins produced four rounds of the same finding.
* **Group B (P16, P17–P19)** — clauses the collaboration path **cannot** reach: the cross-project
  scope clauses (`SovereignStore` scopes every operational read by project before the policy is
  asked) and the update rule (the read rule answers first — U343). Graded by direct-policy tests
  and labelled `[direct-policy]` in the row name. A row here has **not** been proven through the
  collaboration path and is not counted as if it had. P16 moved into this group at round 4, which
  was right that counting it as Group A was the same over-claim the grouping exists to prevent.
* **Group C (P20–P26)** — the delegation itself, both directions, on **both** layers and **both**
  tool-layer gates: delete a policy call (the rule survives in `control_plane/` and is simply not
  consulted), or re-inline a rule inside `mcp_server/` with the policy call left beside it so the
  wiring still looks live. All seven are graded behaviourally.

Rule tests alone could not have proved any of this: they pass whether a rule is delegated or
duplicated, which is exactly how B1 survived eighteen phases of green suites. The proof that a
**duplicate** cannot hide is `TestAPermissivePolicyReachesPastEveryRule` — one test per entry
point, each performing an operation the shipped policy refuses and requiring it to succeed under
an injected policy that allows it — plus `test_every_policy_call_the_service_makes_is_covered`,
which parses both `mcp_server/` modules for `self._policy.X` / `self.policy.X` names and asserts
none escapes that list.

**Where the falsification still stops, stated rather than papered over:** a re-inlined rule
spelled to defeat static analysis (`getattr(identity, "ro" + "le")`) is caught on every path that
has a permissive-policy test, and those cover all thirteen entry points and both tool-layer gates
— but the *structural* assertions remain evadable by construction. The `authorize_message_read`
direction this section listed as untested from round 2 **is now tested** (round 3:
`test_the_default_read_gives_the_conductor_only_its_own_traffic`, mutation P16f); the sentence
that said otherwise was carried forward one round too long, which the round-4 reviewers caught in
the safe direction. What the matrix still cannot see is a rule whose effect is invisible in a
verdict string or a list length, and the Phase-3A memory rules in the same module remain pinned in
the deny direction only (U351).

None of the 37 rows restores shipped code: the pre-unit tree made these decisions inline, so
there is no earlier version of `control_plane/policy.py` carrying a wrong collaboration rule.
Each `new` string is a deliberate defect that names what it breaks.

**Live provider calls made by this unit: zero.** Nothing here needs one — the changes are to a
pure decision function, its call sites, and tests. D-LOOP-1 teardown is vacuous: no process was
spawned.

## 5. What the mandatory reviewers found

### 5.1 Round 1 (on the first implementation)

**gate-validator: FAIL** — 2 MAJOR, 2 MEDIUM, 3 MINOR. **spec-auditor: PROHIBITED DRIFT NONE,
no invariant violated by the change** — 3 MAJOR, 6 MEDIUM, 9 MINOR. They converged independently
on the same two central defects.

1. **The tool-layer mutation row was graded by a grep of the token it inserts** — mutation O1,
   the circularity the cold audit condemned and unit 19.9 exists to remove — while three
   documents asserted *"no source grep decides those verdicts."* True of the service row, false
   of the tool-layer row. There was no behavioural grader available because
   `SovereignToolRuntime.__init__` manufactured its own `SovereignPolicy()`. **Fixed** by making
   the policy a required constructor keyword.
2. **The rules this unit itself wrote were pinned by nothing.** The gate-validator flipped
   `_SCOPED_ROLES` back to `frozenset({"worker"})` in-process and ran the suite: green, in the
   authority-widening direction. Three more were equally unpinned. **Fixed:** P14–P19 and the
   voice / malformed-role / update-rule / defence-in-depth tests.
3. **Duplication could still have hidden** for eleven of twelve rules — the single
   permissive-policy test covered one. **Fixed:** one permissive test per entry point.
4. **The documents claimed more than the artifacts supported:** a past-tense review claim over
   placeholder sections, "two behaviour deltas" that were wrong three ways, "reason strings are
   unchanged" (false), no pre-unit code quoted, and a U343 rationale that was refuted outright.
   **Fixed:** §2 became a measured table, §3 was rewritten, the dead clause was deleted.
5. Also fixed: the unknown-role gate was made uniform (gating the task rules and not the debate
   ones meant a malformed role read zero tasks and every project debate — gate-validator
   MINOR-6); the tool-layer synthesis test was given a real task id (gate-validator MINOR-5,
   spec-audit MIN-6); P2/P3 were labelled as one mutation with two selectors (MIN-5).

### 5.2 Round 2 (on the remediation, at `9c59cb0`)

**gate-validator: FAIL** — 2 MAJOR, 4 MEDIUM. **spec-auditor: PROHIBITED DRIFT NONE, no
invariant violated** — 4 MAJOR, 6 MEDIUM, 6 MINOR, 2 NIT. Both re-ran the harness and the full
suite independently (`23/23 RED`; `2316 passed, 1 skipped, 609.48s`), and both found the round-1
fix incomplete in the same place.

1. **The round-1 fix moved the grep off one tool-layer gate and left it load-bearing on the
   other.** Both `TOOLS` rows anchored on the synthesis call; the *candidate* gate had no
   behavioural row and no permissive test. The gate-validator wrote
   `if getattr(self.identity, "r" + "ole") != "worker":` into `sovereign_tools.py`, ran the full
   suite, and got **green** — reverting, invisibly, the pre-CAS gate §1 is proud of. **Fixed:**
   P24/P25, `test_an_injected_permissive_policy_reaches_past_the_candidate_gate`, and
   `test_an_unassigned_worker_is_refused_before_anything_reaches_cas`, which asserts the CAS
   directory is empty after a refusal.
2. **`_DIRECTING_ROLES` — round-1 MAJOR-2 recurring on the sibling constant.** Widening it to
   admit `gate` survived the full suite: the *deny statements* were mutated by P1/P6/P10/P13, the
   *membership set* an operator would actually edit was not. **Fixed:** P16b +
   `test_a_gate_node_directs_nothing`. Three further unpinned rules found the same way — the
   two-participant debate floor, `_task_participants` absorbing `peer_nodes`, and the candidate
   rule's role half — are P16c/P16d/P16e.
3. **The before/after script self-invalidated on commit.** It lived in the gitignored
   `docs/loop/logs/` and read `HEAD:`, so once the work was committed it compared the new module
   with itself and printed `0 of 31 scenarios differ` — the report's central quantitative claim,
   destroyed by the act of recording it. **Fixed:** the tool is tracked at
   `tools/evaluation/u326_before_after.py`, pinned to base `b529314`, and refuses a base that
   already delegates.
4. **The past-tense defect, again, one level up.** The header said the reviews had happened
   "twice" while §7 was still a placeholder, "the two work commits" named a commit that did not
   exist, and the committed evidence carried no suite result for the committed tree. **Fixed:**
   this document states each round only after it has run, and §7 carries the hashes.
5. **The module docstring asserted an absolute its own file falsified** ("decides nothing about
   who may do what") — the quorum, completeness, round-bound and CANDIDATE-status rules are
   still there, and the pending register row claimed a narrowing that had not been performed.
   **Fixed:** the docstring makes the narrow claim and names the residue; U344 now argues the
   legality-versus-authority boundary explicitly (the spec-auditor was right that "debate
   semantics are untouchable" covers the quorum and the round bound but *not* the synthesis
   completeness rule — the answer for that one is that it asks *what has happened*, not *who is
   asking*, exactly as `mcp_server/lifecycle.py` has always done).
6. Also fixed: `_require_debate` asked no authority and `post_debate_turn` disclosed a debate's
   state before authorizing (delta 4); `record_synthesis` was the one write path that skipped
   task-read authority; `_ENTRY_POINTS` had no converse completeness check; a non-`str`
   proposition raised `AttributeError` instead of `CollaborationError`; two unused imports
   (`Iterable`, `CollaborationError`) in files this unit edited; a dead constant in the harness;
   and the "evasion-proof by parsing" and "asked FIRST by every entry point" absolutes, both
   false as written.
7. **Recorded rather than fixed**, each with a register row: **U344** (legality rules remaining
   in `mcp_server/`), **U345** (`apps/desktop/main.js:requireControlRole` is a fourth copy of
   authority, and stricter than the policy — conductor-only where the policy admits the
   operator), **U346** (a worker may set `ACCEPTED`/`COMPLETED` through `publish_progress`;
   `TASK_STATES` also collides with the promotion vocabulary), **U347** (`peer_nodes` advertised
   to workers but outside the authority set), **U348** (transcript authority is not task-scoped;
   a scoped read carries no signal that it was scoped). Two more were answered rather than
   actioned: `control_plane/policy.py` importing `is_promotion` from `mcp_server/lifecycle`
   (recorded in U344 — legality is not authority) and `ruff` being absent on this host, so
   CLAUDE.md's ruff-clean rule stays unverified (U309, already open).

### 5.3 Round 3 (on the round-2 remediation, at `3e5b4dd`)

Both ran foreground, in-turn, concurrently. **gate-validator: FAIL** — 1 BLOCKING, 1 MAJOR,
3 MEDIUM, 5 MINOR. **spec-auditor: PROHIBITED DRIFT NONE, no invariant violated** — 2 MAJOR,
5 MEDIUM, 5 MINOR, 1 NIT. Both re-ran the harness (29/29) and the full suite independently.

1. **BLOCKING: the falsification requirement was not met as a property of the rule set.** The
   validator wrote its own twelve-mutation probe and **five** rule changes survived the entire
   suite: `authorize_message_read` short-circuiting for the directing roles (invariant 8 — the
   conductor would get every message on the ORDINARY path, leaving the transcript rule
   decorative); `authorize_debate_read` admitting the opener (reachable — a worker may open a
   debate it is not a participant of); `authorize_publish_candidate` admitting `conductor` (a
   conductor may genuinely be named an owner — I-M6 in the widening direction); a member added to
   `ROLES` (which this unit turned into a collaboration READ rule); and deleting the
   `record_synthesis` task-read call round 2 had just added. **Fixed:** five tests through the
   collaboration path, mutation rows P16f–P16i and P26.
2. **MAJOR: `test_a_gate_node_directs_nothing` asserted an absolute the code falsifies** — a gate
   can `update_task` to `CANCELLED` and `send_message` into any task thread through its
   project-wide read. **Fixed:** renamed, and it now asserts what a gate CAN do as well.
3. **MAJOR (spec-audit): the register rows the document said existed did not exist.** U343–U348
   were cited in prose, in `control_plane/policy.py`, in `mcp_server/collaboration_service.py`,
   in the tests and in the harness, while `UNRESOLVED_ISSUE_REGISTER.md` ended at U342 — so every
   "recorded rather than fixed" disposition was uncollateralized. This is the past-tense defect a
   third time, on the mitigations that justify what the unit chose not to fix. **Fixed at the
   evidence commit** (§7), which is where register rows belong.
4. **MEDIUM/MINOR, all fixed:** two arithmetic numbers in §2 that did not reproduce; a seventh
   behaviour delta measured outside the matrix (now scenario 34); `record_synthesis`'s task read
   not marked SHADOWED like its two siblings; module docstrings still saying "twelve" and claiming
   the reason strings were unchanged (two changed); the vestigial
   `authorize_put_artifact`/`authorize_read` escape hatch in the entry-point completeness check;
   stale harness group ranges; an incomplete U344 residue list.
5. **Recorded rather than fixed:** U349 (the `gate` debate widening is uncapped — `budget_units`
   is stored and never consulted, and `open_debate` compels every participant's pane) and U351(b)
   (`_OPERATOR_ONLY_KINDS` and the other pre-U326 rules are pinned in the deny direction only).
6. The spec-auditor also caught a **process** defect worth keeping: a concurrent reviewer's
   in-flight mutation was sitting in `control_plane/policy.py` while suites were running, from
   scratch scripts in an untracked `.gv3_scratch/` that took no `.mutation-lock` and installed no
   restore handler. The suite numbers taken in that window were discarded and re-taken on a
   verified-clean tree; the scratch directory was deleted (§6).

### 5.4 Round 4 (on the round-3 remediation, at `65ae5f6`)

Both ran foreground, in-turn, concurrently. **gate-validator: FAIL** — 3 BLOCKING, 3 MAJOR,
4 MEDIUM, 4 MINOR. **spec-auditor: PROHIBITED DRIFT NONE, no invariant violated by the change** —
1 MAJOR, 5 MEDIUM, 6 MINOR, 2 NIT. The validator re-attacked all five of round 3's survivors with
its own spellings and confirmed each now goes RED — and then found **three more of the same
class**, each surviving the full 2329-test suite:

1. **`_DIRECTING_ROLES` admitting `voice`** — one word, four authorities at once (create
   assignments, read any full transcript, close a debate, publish synthesis). Invariant 25 says
   voice cannot expand authority. Round 2 found this same constant in the `gate` direction; the
   `voice` direction was pinned by nothing.
2. **`authorize_debate_close` admitting the debate's opener** — reachable, because a worker may
   open a debate; it could then close it with its own decision.
3. **`authorize_open_debate`'s subset absorbing the caller** — a `gate` could name itself into any
   task's debate, arming turn timers on a task it was never party to.

**The fix is not three more tests.** Four consecutive rounds found this class, each pinning what
the previous round found; the answer is `TestTheWholeVerdictSurfaceIsPinned` — every admitted role
× every collaboration operation, 136 cells, through the service, as one table that no
single-constant widening can pass (U352). Mutation rows P16j–P16l are graded by it.

Also fixed from round 4: **P16 and P16i were mis-grouped** — both were counted as
collaboration-path proof while being graded structurally or directly (P16 moved to Group B;
P16i's test now iterates `ROLES` and probes each member THROUGH the service, so an added member is
observed rather than asserted about); **U349 was referenced by committed code and existed nowhere**
(written now, with U350–U352); the §2 "directs nothing" sentence and the "only constructor"
absolute; every stale number in §2 and §4; the cross-project defence-in-depth test asserting only
for a worker identity (now conductor and gate too, which is how the validator's own M15 mutation
got in); and the test module's own "twelve".

**Recorded rather than fixed, each with a register row:** U349 (invariant 17 is not honoured on
this path — this unit added one role to an already-ungoverned surface), **U350** (a directing role
may close a debate it argued in — invariant 18 is enforced in `debate_service/` and not here;
faithfully pre-unit behaviour, now pinned in the matrix as current behaviour rather than fixed),
U346 extended with the `voice`-as-owner half, U345 extended with `controlNotifyDebate`'s missing
role gate, and U351 (`mcp_server/server.py:32` still manufactures its own `SovereignPolicy()` —
the U292(a) shape this unit closed one file over).

## 6. Scope, prohibitions, substitutions

* **Untouchable set intact:** `tools/loop/run_loop.ps1`, loop-state semantics, every existing
  gate tag, `docs/canonical/`, both frozen schemas, artifact/debate semantics, remotes,
  credentials — none touched. **MCP authority:** this unit *restores* it (invariant 7) and
  relocates nothing further into `mcp_server/`.
* **Overlap with other units, disclosed:** `TestTheToolLayerAsksThePolicyToo` is coverage of
  `mcp_server/sovereign_tools.py` through real `runtime.call()` paths, which unit **19.9** also
  asks for ("a direct test of both new authorization gates, currently exercised only against a
  two-line echo fake"). It was necessary here to close round 1's MAJOR without a source grep.
  Nothing else from units 19.3–19.10 was done: `apps/desktop/main.js`, the operational store's
  write paths, the readiness state machine and the receipt work are untouched, and U328–U339
  stay open and owned by their units.
* **No substitutions were needed** — this unit required no prohibited or absent capability.
* **Deleted, and why:** `.gv3_scratch/` (two untracked mutation scripts left by the turn that
  died mid-unit; they wrote directly into `control_plane/policy.py` without taking
  `.mutation-lock` and installed no restore handler, so an interrupted run could leave an
  authority widening in the tree of a loop that commits automatically — the round-3 spec-auditor's
  MAJOR-2). Nothing tracked was deleted; the register and evidence remain append-only.
* `config/live_operation.json` neither read into the repo nor committed; no credential read,
  stored or transmitted; no network egress; no live provider session.
* **CRLF (U274):** every file written by this unit was verified LF-only before staging.

## 7. Commands, hashes, what is still owed, and what this unit does NOT claim

**Commits.** `9c59cb0` (the delegation, on base `b529314`) → `3e5b4dd` (round-2 remediation) →
`65ae5f6` (round-3 remediation) → `3fa401a` (round-4 remediation: the verdict matrix) → this
evidence/register commit, which carries them. No tag was created or moved; `gate/phase-19` does
not exist and `product/multi-frontier-v2` still points at `cd08878` (§17.1 — existing tags are
never moved).

**Measured on the tree this document describes** (`3fa401a`), all foreground, in-turn:

| Command | Result |
|---|---|
| `py -3.12 -m pytest tests/unit -q` | **1845 passed, 1 skipped, 58.79s** |
| `py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q` | **486 passed, 559.82s** |
| Python total | **2331 passed, 1 skipped** |
| `py -3.12 tools/mutation/_op19_policy_delegation_mutations.py` | **37/37 RED, all restores byte-identical** |
| `py -3.12 tools/evaluation/u326_before_after.py` | **base=b529314 · 19 of 34 scenarios differ** |
| `npm test` in `apps/desktop` | **tests 836 · pass 836 · fail 0 · skipped 0** |
| `node --test test/*.test.js` in `terminal` | **tests 216 · pass 216 · fail 0 · skipped 0** |

The suite is split because it runs ~10 minutes and the runner's per-command ceiling is 600 s;
the split is `tests/unit` + everything else, and 1845 + 486 = 2331 is the whole of `tests/`.
The JS suites were measured on `65ae5f6` and **no JavaScript changed after it** — stated rather
than re-attributed. The full-suite numbers taken while a reviewer held an in-flight mutation in
`control_plane/policy.py` were **discarded**, not reported (§5.3.6).

**Live provider calls made by this unit: zero.** Nothing here needs one — the changes are to a
pure decision function, its call sites, and tests. D-LOOP-1 teardown is vacuous: no process was
spawned, and no child process outlived any turn.

**WHAT IS STILL OWED — this document does not close the unit.** The round-4 remediation
(`3fa401a`) post-dates round 4, and directive §18's *fix-after-validation voids it* rule applies:
the verdict matrix, the P16/P16i regrouping and the register rows have **not** been reviewed by
either mandatory reviewer. **The next unit's first act is round 5** — gate-validator and
spec-auditor, foreground and concurrent, on `3fa401a` plus this evidence commit — and unit 19.2
is finished only when a round returns with nothing the fix of which changes the tree. If round 5
finds a sixth instance of the membership-set class, that is evidence about U352's coverage and
belongs in U352, not in a sixth patch.

**What this unit does NOT claim.** It does not claim `mcp_server/` is free of every kind of gate:
the debate quorum, the synthesis completeness rule, the round bound, the `debate is not open`
state gate, the candidate referential checks and the CANDIDATE-status check are still there
(U344), and `sovereign_tools.py` still validates shapes and matches a claimed provider/model
against the authenticated identity. It does not claim the rules are *right* — they are the rules
that were already being enforced, moved to where the operator can change them once; where the
relocation exposed something wrong (U346's `ACCEPTED`/`COMPLETED` reach, U349's uncapped debate
cost, U350's self-judging closer) it is recorded, not silently fixed. It does not claim
single-point-of-change across the product: `apps/desktop/main.js` holds a fourth copy for the
Electron control surface (U345), which no Phase-19 unit owns. It does not claim the structural
assertions are unevadable (§4 says where they stop) nor that the matrix sees everything (U352
says what it cannot). And it does not claim Phase 19 is closable: **U328–U339 remain open**, and
this is unit two of ten.

