# Phase 19 · unit 19.1 — the OP-13 revert, and what reverting it exposed

**Unit:** `phase-19.1` (AUTONOMOUS_BUILD_DIRECTIVE.md §18, OP-13 / OP-13.1).
**Work commits:** `c5078bf` (the revert) + the remediation commit recorded in §5 below.
**Gate:** none. Phase 19 closes at unit 19.10 with `gate/phase-19`; this is a sub-step checkpoint,
and **no tag was created or moved by this unit** (`product/multi-frontier-v2` still points where it
did).
**Reviewers:** gate-validator and spec-auditor, both **foreground, in-turn, concurrently**
(D-LOOP-2). Round 1 verdicts and what they changed are §4.

---

## 1. What the operator ruled, and what this unit did about it

OP-13, verbatim in the directive: *"Antigravity's own `accept-edits` mode is **not** operator
approval. `D-P18-13` / `U317` stand unamended. `adapters/frontier/antigravity.py:72` returns to
`"plan"` and the `antigravity_execution` carve-out at `provider_cli_common.py:310-312` is removed so
the forbidden-mode guard is unconditional again."* Unit 19.1 adds: restore the deleted rationale
comment rather than writing a new one; settle U327 either way but **not silently**; and add a test
that refuses `accept-edits` **for every execution profile**, so the carve-out cannot reappear
untested.

| Asked | Done | Where |
|---|---|---|
| `ANTIGRAVITY_HEADLESS_MODE` → `"plan"` | yes | `adapters/frontier/antigravity.py:78` |
| carve-out removed, guard unconditional | yes — **the parameter too**, not just its effect | `adapters/frontier/provider_cli_common.py:300-321` |
| deleted rationale RESTORED, not rewritten | yes, verbatim, with a dated note appended below it | `antigravity.py:69-77`, `grok_build.py:87-108`, `frontier_provider_recon.py:200-223` |
| U327 settled in the open | **restored `"plan"`**, decision row D-P19-1, register entry U327 CLOSED | `grok_build.py:109`, `DECISION_REGISTER.md` D-P19-1 |
| a test refusing `accept-edits` for every profile | `TestTheGuardHasNoExecutionProfileCarveOut` | `tests/unit/test_op12_frontier_adapters.py` |

Two things the ruling did not name, which the revert required anyway:

* **the 18A probe path.** `ANTIGRAVITY_PROBE_MODE` was also at `accept-edits`. With the guard
  unconditional again, leaving it there would have made the operator's own diagnostic
  (`frontier_provider_recon.py`, the tool the operator ran by hand on 2026-08-02) refuse its own
  argv at build time. Reverted with it.
* **`--no-plan`.** The same range removed it from `FORBIDDEN_PROVIDER_ARGS` — where 18A had put it,
  its own comment reading *"undoes the pinned plan mode"* — and emitted it beside `default` on all
  three Grok builders. The installed capture defines it as *"--no-plan / Disable plan mode"*.
  Restoring the pin while still emitting that flag would have restored a **value** and left the
  **widening** intact under a second name. Both moved together.

## 2. Why U327 was settled by restoring `plan`, not by keeping `default`

The directive allowed either, provided the reasoning is recorded. The evidence decided it:

| Artifact on disk | What it says |
|---|---|
| `docs/evidence/live/phase18e_probe_document_shape_20260802T0219Z.json` | grok probe, `--permission-mode plan`, `"accepted": false` |
| `docs/evidence/live/phase18e_probe_grok_default_mode_20260802T0224Z.json` | grok probe, `--permission-mode default`, `"accepted": false` |
| `docs/evidence/live/phase18a_host_recon.json` (the installed `grok --help`) | `[possible values: default, acceptEdits, auto, dontAsk, bypassPermissions, plan]` — enumerated, **unranked, undescribed**; the phrase "normal execution" appears nowhere |

So: the widening buys **no measured behaviour** on this host — which is exactly what the deleted
comment said, and nothing has been measured since to overtake it — and the justification that
replaced that comment (*"the installed CLI's normal execution mode is `default`"*, *"`plan` is not
task-ready"*) is **not in the capture the build treats as authoritative**. Asserting it would be the
inference-stated-as-evidence that the round-3 spec-audit already corrected once on this same file.

What is **not** claimed: that `plan` is the most restrictive mode (the enum is unranked — the
restored comment says so), or that any permission mode is containment (invariant 29; U25 still
owed). **U310 stays OPEN and unaffected**: Grok's headless `-p` still exits zero saying nothing on
this host, and the mode is still not the cause. If a governed live run ever shows plan mode blocking
a worker, that is a measurement and the basis for an operator amendment — not an assumption this
build may make in advance.

## 3. Evidence — real command output

| Command | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q --durations=10` (on `c5078bf`) | **2262 passed, 1 skipped, 626.75s** |
| `py -3.12 -m pytest tests/ -q` (gate-validator's independent re-run) | **2262 passed, 1 skipped, 588.89s** |
| `py -3.12 tools/mutation/_op13_permission_mode_mutations.py` (round 1, 8 rows) | **8/8 RED, all restores byte-identical** |
| `py -3.12 tools/mutation/_op13_permission_mode_mutations.py` (after remediation, 12 rows) | **12/12 RED, all restores byte-identical** |
| `py -3.12 -m pytest tests/ -q` (remediated tree) | **2272 passed, 1 skipped, 556.76s** — +10 tests, all of them this unit's |

Every mutation row restores **code that was actually shipped at `b109f02`**, not an invented defect;
the gate-validator verified each row's `new` string against `git show b109f02:<file>` independently
and confirmed it (one row, M6, inlines the literal `"--no-plan"` because the constant it used no
longer exists — behaviourally identical, and recorded as such).

**Live provider calls made by this unit: zero.** Nothing here needs one: every change is to argv
construction, a guard, and prose, and all of it is deterministic. D-LOOP-1 teardown is vacuous —
no process was spawned.

## 4. What the mandatory reviewers found (round 1, on `c5078bf`)

Both ran in the foreground, in this turn, concurrently. **gate-validator: FAIL. spec-auditor:
PROHIBITED DRIFT NONE, no invariant violated, four MAJOR findings.** They independently named the
same central defect, which is the reason this section exists rather than a line in a commit message:

**The revert was incomplete.** `node_runtime/supervisor/worker_pane_spawn.py` built each pane's
launch-ticket `note` as hand-written prose, and the untagged range had edited that prose to match the
argv it widened: *"--mode accept-edits"* for Antigravity, *"plan disabled"* for Grok. Unit 19.1's
first submission reverted the argv and left the sentences. The `note` is not a comment — it is
carried in the launch ticket beside the argv, which is what receipts and the shell chrome show the
operator. **The first live pane of Path A would have written that contradiction into an acceptance
receipt**, and 2262 passing tests could not see it, because a sentence cannot disagree with a list it
was never derived from. Recorded as **U341**.

The spec-auditor additionally argued (MAJOR-2/3/4) that **U340 — the `--allow mcp__sovereign__*` rule
the same range introduced — should have been reverted by this unit rather than recorded and kept.**
The first draft kept it on a code-read argument. The argument was wrong in three specific ways: the
installed capture calls that flag *"Permission allow rule"* (provider tool permission granted by an
argv, which the guard's own docstring says never happens); D-P18-13 is a statement about the class of
provider-native auto-approval, not about one mode enum; and the rule's defence rested on
`control_plane/policy.py` role checks that **U326 says are not in place yet and unit 19.2 has not
run** — a widening resting on a fix that has not landed is the ordering OP-13.1 exists to forbid.
**Accepted, and reverted.** U340 records both calls and why the second one won.

Also fixed from round 1: the guard docstring asserted *"never granted by an argv"* four lines above
the `--allow` exemption that falsified it (MAJOR-2 — true again now); a comment claimed present-tense
that the control server role-checks *every* Sovereign operation (MAJOR-3 — deleted with the rule);
the repo's own tracked `.grok/config.toml` still pinned `permission_mode = "default"`, i.e. this
build shipped the node-controlled config its own restored comment names as the threat (MEDIUM-6 —
key removed, test added); and one test had lost the coverage its docstring claimed, asserting `plan`
twice instead of proving `default` is *permitted* — which is what makes the pin a choice rather than
an enforcement (MINOR-1 — restored).

Findings NOT actioned in this unit, recorded instead:
* **U341's remainder** — the `claude` and `codex` note branches are still prose. Not known to be
  wrong; simply not derived. Owner: unit 19.10.
* **NIT-11 (spec-auditor)** — `tools/loop/run_loop.ps1:114` invokes the build agent with
  `--permission-mode acceptEdits`. That file is in this phase's **untouchable set** by name
  (directive §18), and it governs the loop's own harness rather than a provider adapter. Out of
  scope, recorded here so the asymmetry is not mistaken for an oversight; it is the operator's call.
* **NIT-9/10** — register cross-reference and two stale receipt filenames cited in older entries.
  Append-only forbids editing them; the correct filenames are cited in this unit's own entries.

## 5. Remediation, and the re-validation it forced

Directive §18: *"fix-after-validation voids it — re-validate or split the unit."* Every reviewer
finding above was fixed in-unit, then **the whole evidence set was regenerated**: the mutation
harness grew rows M8–M11 covering exactly the newly-closed holes (each restoring the shipped code),
and both the harness and the full suite were re-run on the remediated tree.

The note fix is worth stating precisely, because it is the one that generalizes: the sentence is not
rewritten, it is **derived**. `describe_pinned_flags(argv, workspace=...)` renders the note's flag
list off the argv the note is attached to, so a note can no longer claim a pin the argv does not
carry — in either direction — and `--mode accept-edits` cannot appear in one unless the guard let it
into the other. `tests/unit/test_worker_ticket_honesty.py` holds four properties on it: every flag
named in a note is in the argv; any mode value named matches the argv's; neither note nor argv
carries a forbidden mode; and the workspace is described, not printed.

## 6. Scope, prohibitions, substitutions

* **Untouchable set intact:** `tools/loop/run_loop.ps1`, loop-state semantics, every existing gate
  tag, `docs/canonical/`, both frozen schemas, MCP authority, artifact/debate semantics, remotes,
  credentials — none touched. Verified by the gate-validator against `git show --stat`.
* **Nothing from units 19.2–19.10** was done here. `mcp_server/` and `apps/desktop/main.js` are
  untouched: U326, U328, U329, U330 and the rest remain open and owned by their units.
* **No substitutions were needed** — this unit required no prohibited or absent capability.
* `config/live_operation.json` was neither read into the repo nor committed; no credential was read,
  stored, or transmitted; no network egress; no live provider session.
* **CRLF (U274):** every file written by this unit was verified LF-only before staging.

## 7. What this unit does NOT claim

It does not claim Grok's plan mode works — U310 is open and says the opposite about headless `-p`.
It does not claim any permission mode contains anything (invariant 29; U25 owed). It does not claim
Phase 19 is closable: **U326, U328–U339 remain open**, and this checkpoint is one unit of ten. And it
does not claim the first submission was right — it was incomplete, two independent reviewers said so,
and §4 is what that correction looks like when it is recorded instead of quietly absorbed.
