# Phase 19 · Unit 19.6 — U331 + U333: provider-agnostic in the RUNTIME, not only in the selector

**Status at writing:** work committed, suites and receipt green, **both mandatory reviewers owed**
(they are the next act; nothing below is a claim that they have run).
**Work commits:** `4bc6957` (the unit), `a2cee1e` (the receipt instrument's own defect, found by
running it three times).
**Evidence commit:** this file plus the register rows.
**Tag:** none. `gate/phase-19` belongs to unit 19.10; `product/multi-frontier-v2` is never moved.

---

## 1. Reconciliation at entry

Tags said `gate/phase-18e` and `product/multi-frontier-v2` were newest; `LOOP_STATE.json` said
`next_step = phase-19.6` with 19.5 closed at iteration 132 and Phase 19's gate belonging to 19.10.
They **agreed** — no reconciliation commit owed. `HEAD` was `a43ea9b`, iteration 132's state-writing
commit, and the tree was **clean**, so nothing was inherited from a turn that died mid-unit.

## 2. What the unit was chartered to do, and what it did

Directive §18, unit 19.6, plus three items other units carried here.

| Item | Charter | Done |
|---|---|---|
| **U331** | remove the `openai_codex_cli`/`gpt-5.6-sol` pin at `main.js`, derive conductor readiness from the DESCRIPTOR | yes — `apps/desktop/control/conductor-admission.js`, bound in `runConductorReadiness` |
| **U331** (compounding) | reconcile `registry.py:154-162`: the default resolves fable-5 when the gitignored switch is absent and must not read as a config error | yes — the pin is gone (that WAS the failure), and the descriptor now carries `selection_source` so the two cases are distinguishable |
| **U333** | replace `gemini_contribution`/`grok_contribution` with contributions keyed by node id or descriptor (I-SC1) | yes — `contributions`, cross-checked against the task's candidates in both directions |
| **U423(h)** | `tests/unit/test_operational_write_path.py:395` depends on those two fields | yes — updated, and §5 of that file is new coverage for the replacement |
| **U386(c)** | `requiredTurns` keyed on the vendor name `"grok_build"` | yes — declared trait |
| **U393 MINOR-1** | three more vendor-name branches in the same call graph (`provider-readiness.js:32/:37/:41`, `pane-writer.js:237`) | yes — declared traits |
| **U425(b)** | `collaboration_service.py:317-318` states the synthesis-gate defence unqualified | yes — scoped to the tool path that provides it, with U410 named |

## 3. U331 — what the code did, and what it does

The audited line, verbatim:

```js
if (descriptor.provider_id !== "openai_codex_cli" || descriptor.model_id !== "gpt-5.6-sol") {
  ... reason: "conductor readiness requires exact OpenAI/Codex gpt-5.6-sol selection"
```

It ran **after** the selection layer had resolved a descriptor, **after** the registry had declared
it conductor-capable, and **after** the governed spawn path — live switch, provider-live, operator
terms, I-X3 lease — had admitted it and started a real session. Everything upstream was
provider-neutral. This was not, and the commit that introduced it (`3587cbd`, *"generalize
provider-agnostic conductor selection"*) says the opposite of what it did.

`control/conductor-admission.js` asks four questions, each true of a conductor of any provider: is
this a conductor descriptor, does it name a provider, does it name a model, did the registry
register it and call it conductor-capable. Each **fails closed** — an unresolved selection is a
genuine configuration error and still reports as one — and **no refusal names a vendor**, which is
asserted, because a refusal that names a vendor is the pin returning as a message.

One deliberate non-symmetry, stated because it looks like a hole: `registered`/`conductor_capable`
**absent** is not a refusal, only an explicit `false` is. Those keys come from the Python registry;
a descriptor minted by another path carries neither, and treating a missing key as `false` would
refuse on the absence of evidence rather than on evidence of a problem — re-creating this defect one
indirection away.

**A trait the conductor pane was not getting.** With the pin gone, the conductor's readiness honours
the provider's declared turn count. A backend whose first reply is its own greeting would have been
promoted on that greeting; that is `grok_build`'s declared two-turn rule, and until this unit it
applied to workers only.

**`exact_model: true` is gone.** It was a literal assignment whose only meaning was the pin above it
(the U337 class). What the readiness record carries now is what was decided and by what:
`descriptor_admitted`, `decided_by`, the provider, the model, the selection source, and the number
of turns answered.

## 4. U386(c) + U393 MINOR-1 — declared traits, and what that claim is NOT

Three runtime decisions were inline vendor comparisons. Each was **correct** for the vendor it
named; the defect is what happened to every provider it did not — behaviour nobody chose, arrived at
by falling off the end of an `if`, in a file whose reviewers had no list to check against.

`control/provider-traits.js` holds one enumerable table, and `traitsFor` answers for **every**
provider id: an undeclared one gets `GENERIC_TRAITS` (one readiness turn, one Enter, no
provider-scoped screen rules). It is **not an allowlist** — nothing here can refuse a provider;
refusal belongs to the governor and the launch ticket and stays there (invariant 7).

**The vendor strings do not disappear, and claiming otherwise would be the dishonest version of this
fix.** "press enter to continue" on a Grok onboarding overlay is a fact about Grok's TUI and has to
be written down somewhere. What I-SC1 requires, and what changed, is that the runtime consult a
descriptor rather than branch on a name.

## 5. U333 — the synthesis was structurally bound to two vendors

`_publish_synthesis` built its record with `gemini_contribution` and `grok_contribution`, both in
the `required_text` tuple and both `required` in the published tool schema. A task completed by two
Codex workers, by a Claude worker beside a local Ollama one, by **one** worker, or by three, could
not be synthesised at all — and the conductor's only way to comply was to file a node's work under a
vendor name that was not its own.

`contributions` is a list keyed by `node_id`, cross-checked against the task's own candidate set
**in both directions**, mirroring the closed-debate gate one function below it:

* a contribution naming a node that published no candidate is refused (invented work);
* a candidate node the caller left out is refused (dropped work);
* both refusals name the node, because a conductor made to guess will guess.

The two-slot form could express **neither** check: with exactly two slots a third worker's result
had nowhere to go and a missing second worker was invisible. The tool DESCRIPTION was changed too —
a schema that requires `gemini_contribution` teaches every conductor that contributions *are*
vendors, whatever the runtime then checks.

## 6. The selection's provenance (U331's other half)

`load_runtime_conductor_descriptor` now stamps `selection_source`:
`live_operation_preference` when the operator's host switch named it, `recorded_default_selection`
when the switch was absent or silent and the registry resolved the recorded fable-5 selection
(D-COND-03 — an operator choice, not a vendor default, which is the distinction invariant 3 turns
on), `unstated` for a descriptor resolved directly. It **labels**: no path refuses on it, and a
malformed or unregistered preference still fails closed exactly as before (asserted).

## 7. Falsification

| Harness | Result |
|---|---|
| `tools/mutation/pane_input_bypass_mutations.js` | ALL CAUGHT, main.js restored byte-identically |
| `tools/mutation/system_pane_write_mutations.js` | ALL 32 CAUGHT, four files restored byte-identically |
| `tools/mutation/readiness_signal_mutations.js` | ALL 26 CAUGHT |
| `tools/mutation/orchestration_mutations.js` | ALL 5 CAUGHT |

**Two of those harnesses were not runnable at HEAD, and that is a finding about unit 19.5, not about
this one.** `orchestration_mutations.js` pinned `control_plane/policy.py` at bytes that moved in
`44c2abf` and `mcp_server/collaboration_service.py` at bytes that moved in `5d56e19`, and its O4
anchor (`if round_no > debate["max_rounds"]:`) pointed at a line 19.5 replaced when it moved the
round ceiling inside the write fence. The harness therefore refused to run — fail-closed, as
designed — and had been refusing since 19.5 closed. Re-pinned, re-anchored to
`current["max_rounds"]` (same rule, same mutation), re-run: all five CAUGHT. Recorded as **U426**.

`system_pane_write_mutations.js`'s M3 anchor moved for a reason inside this unit: the conductor
readiness prompt now sits inside a per-turn loop, one indent deeper. Re-anchored; the mutation and
the property are unchanged.

## 8. Suites and the receipt

| Run | Result |
|---|---|
| `node --test test/*.test.js` (apps/desktop) | **962 passed / 0 failed / 0 skipped** |
| `py -3.12 -m pytest tests/unit -q` | **1887 passed / 1 skipped** |
| `py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q` | see §10 — reported there with its real number, not summarised here |
| D-P16-0 in-Electron receipt | `docs/evidence/receipts/PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-final_20260811T084739Z.json` — **ok: true**, commit `a2cee1e`, `tracked_product_tree_clean: true`, `live_exchanges: 0`, five legs, three real ConPTY panes, all sessions killed in-unit (D-LOOP-1) |

`ruff` is **absent from this host**: CLAUDE.md's ruff-clean bar is **not run**, not clean.

**The receipt's own defect, found by running it (`a2cee1e`).** Leg E first counted submitted lines by
the pane's prompt token. Across three runs of the same check the undeclared pane's delta read **0, 1
and 2** for ONE submitted line — a repaint redraws a prompt, a slow render hides one — so the leg
failed, passed and failed while the shell did the same thing every time. The criterion is now the
bytes handed to the session manager, recorded at the boundary and only when the manager accepted the
write: two carriage returns for the confirming provider, one for the undeclared. Each pane's body is
separately observed EXECUTING. The pane-side count stays in the receipt as an observation with its
noise stated. **The first green run of that leg was luck, and it is named as such rather than kept.**

What the receipt measured on this host: leg A admitted this shell's REAL descriptor —
`openai_codex_cli`/`gpt-5.6-sol`, `selection_source: live_operation_preference` (the operator's
switch is present on this host). **The `recorded_default_selection` path — the clone case U331 is
actually about — is therefore covered by the Python suite and not by the receipt**, because this
host cannot present it without removing the operator's file, which is outside the repo. Said here
rather than implied.

## 9. What this unit did NOT do

* **U410** (`record_synthesis` has no debate check of its own) is named, not fixed — 19.10's.
* **U412**, **U420**, **U421**, **U422**, **U423**, **U424**, **U425**(a)/(c) stay with their owners.
* The `spawn_worker` tool description still names two vendors as provider DEFAULTS. That is
  descriptive metadata for a live CLI, not a runtime branch; recorded, not changed, so the claim in
  §4 stays exactly as wide as what was done.
* `CONTROL_PROVIDER_ALIASES`, the picker's provider→binary map and the status bar's per-provider
  allowances are per-provider DATA (a subscription ceiling is a fact about a subscription). Left as
  they are.
* No live exchange, no live provider process, no credential read. `config/live_operation.json` was
  read by the shell as it always is and is not committed.

## 10. Owed at the time of writing

Both mandatory reviewers (`gate-validator`, `spec-auditor`) in the foreground, and the
integration/security/recovery/evaluation suite's reported number. §11 records what happened.

---

## 11. What happened to the two owed acts (appended; §8 and §10 pointed here)

**The integration suite finished.** `py -3.12 -m pytest tests/integration tests/security tests/recovery
tests/evaluation -q` → **487 passed in 724.51 s**. Over the 600 s ceiling again, on a host that was
also running the desktop suite, four mutation harnesses and several Electron self-checks — which is
data for **U339** (19.10's timeout diagnosis) and not a claim that the suite is slow on its own. §8's
row pointed here for this number.

**Both mandatory reviewers ran, foreground and sequential**, and their findings are recorded in full in
register row **U429**. Summary, so this file does not require the register to be read first:

| Reviewer | Tree | Verdict |
|---|---|---|
| `gate-validator` round 1 | `c3e1392` | **PASS_WITH_RESERVATIONS** — 0 BLOCKING, 2 MAJOR, 4 MEDIUM, 4 MINOR. It wrote 29 of its own mutations in a throwaway worktree; 25 CAUGHT, 4 SURVIVED. |
| `spec-auditor` round 1 | `e674eb8` | **PROHIBITED DRIFT: NONE** — 2 MAJOR, 5 MEDIUM, 4 MINOR. |

Neither found a defect in the product path. Between them they found **four claims wider than the code**
and **four guards nothing graded**, which is this phase's recurring failure mode arriving on schedule.

**The one sentence in this report that was wrong, corrected here rather than in place.** §3 and §9 rest
on a claim §5 of the register stated outright: that conductor succession onto a different backend is
now *reachable*. It is not. `control_plane/conductor/registry.py` mints three registered pairs, and
`apps/desktop/conductor/launch-source.js:136-139` refuses a launch ticket whose provider has no
verified containment profile — a fail-closed containment rule (invariant 29), deliberately **not**
removed, because deleting it to make a five-provider claim true would admit an unverified permission
boundary in exchange for a greener receipt. The claim this unit supports is narrower and is the one
that stands: **the readiness layer no longer refuses a conductor for the name it carries.** The missing
containment profiles for `grok_build`, `google_antigravity` and local conductors are real work, now
recorded with an owner.

**§9's "left standing" list was incomplete** and the two it missed are in the conductor path:
`apps/desktop/main.js:716` (a non-Claude conductor's model availability is ASSERTED where the Claude
path measures it — a fail-open on capability, against Buildout §4) and
`apps/desktop/conductor/launch-source.js:138-139`. Both are named in U429 with owners.

**The strongest open finding is the spec-auditor's MEDIUM-3**, and it is not fixed here: the new
`contributions` cross-check reads the task OUTSIDE the write fence that commits the synthesis, so a
candidate landing between the read and the commit can still produce a synthesis that omits a node —
the same class as U330, which 19.5 closed for five other writers. Moving it inside the fence is a
behaviour change to the write path, and this unit has now been validated twice; making it here would
void both rounds for a race no test yet demonstrates. Owner 19.10, with the falsification named.

**Repairs that DID land after the reviews** (commit `e674eb8` for round 1's, and the commit carrying
this section for the spec-audit's): the receipt's over-claiming leg renamed and scoped, the
host-conditional clone test made a property test, the admission module's fail-closed description
corrected twice, the two contribution guards isolated by tests that can fail, `minItems` in the
published schema, source pins that catch the validator's two surviving mutations, the
universal-before-scoped precedence pinned, and a fourth unqualified synthesis-gate sentence scoped.

**Therefore: ROUND 2 of both reviewers is OWED**, because fix-after-validation voids what preceded it.
It is the next unit's first act, and this unit is **CHECKPOINTED, not closed**.

**Final measurements on the tree this section describes:** desktop `node --test test/*.test.js` →
**963 passed / 0 failed**; `py -3.12 -m pytest tests/unit -q` → **1889 passed / 1 skipped**;
integration/security/recovery/evaluation → **487 passed**; all four JS mutation harnesses re-run with
every mutation CAUGHT and every file restored byte-identically; D-P16-0 receipt
`PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-round1-repairs_20260811T094302Z.json` — **ok: true**,
commit `e674eb8`, clean tree, `live_exchanges: 0`. A FRESH receipt is owed for the tree the round-2
reviewers will see, because the bytes moved again after that one was taken.

---

## 12. Round 2 of both reviewers, and the close (appended; §11 said this was owed)

**Both mandatory reviewers ran again, foreground, in-turn, sequential**, over `ce3d5d6` — product bytes
identical to `d3c4e6c`, the tree §11's repairs produced. Round 1's verdicts were not carried forward;
each reviewer re-derived, and each re-ran the suites itself rather than reading §8.

| Reviewer | Tree | Verdict |
|---|---|---|
| `gate-validator` round 2 | `ce3d5d6` | **PASS_WITH_RESERVATIONS** — 0 BLOCKING, 1 MAJOR, 4 MEDIUM, 4 MINOR. 27 mutations of its own: **24 CAUGHT, 3 SURVIVED**. |
| `spec-auditor` round 2 | `ce3d5d6` | **PROHIBITED DRIFT: NONE** — 4 MAJOR, 6 MEDIUM, 3 MINOR. |

**Neither found a defect in the product path.** Every MAJOR on both sides is again a claim wider than
the code, and **two of them were introduced by the round-1 repairs in §11** — which is the honest
answer to whether a repair round ends the failure mode: it did not, it reproduced it.

Full findings, corrections and owners are in register row **U430**. The four that change what this
report says:

1. **§11's "The one sentence in this report that was wrong" is itself wrong.** There were at least
   three. §3's *"Each fails closed"* is not true of the admission module: an absent `role`, an absent
   `registered` and an absent `conductor_capable` all **admit** (`conductor-admission.js:70/:79/:82`),
   which the module header and U429 state correctly and §3 does not. And §3's justification for that
   non-symmetry — "a descriptor minted by another path carries neither" — was withdrawn in the module
   and in U429 as naming a producer this product does not have, and still stands in §3. **A reader of
   §3 alone gets the wrong model of when conductor readiness refuses.** Corrected here rather than in
   place, because this file is append-only.
2. **The round-1 rename over-claims in a quieter way.** Leg B's new name,
   `readiness_admits_any_registered_descriptor`, asserts registration its five descriptors do not carry
   — they are `{role, provider_id, model_id}` objects with no `registered` key, and three name pairs
   the registry does not mint. What the leg shows is that admission does not refuse a conductor for the
   provider name it carries. Its caption comment still reads "succession onto a different backend is
   reachable", twelve lines above a `scope` string that says the opposite. Both strings are 19.10's,
   in one commit; they are not changed here, because moving self-check bytes after two completed review
   rounds would void both for a string — the spiral 19.4 and 19.5 each paid five rounds for.
3. **§9's "left standing" list is wrong about `CONTROL_PROVIDER_ALIASES`, and misses a second table.**
   It is not per-provider data: `main.js:2468-2469` refuses the conductor's `spawn_worker` on a
   name-keyed map with the message `unknown or unauthorized worker provider`, before the governor and
   the launch ticket — the I-SC1 class this unit exists to remove, and narrow enough that no
   `claude_code` or `openai_codex_cli` worker can be spawned through that path at all.
   `CONTROL_DEFAULT_MODELS` (`main.js:2044-2046`, used at `:2477`) is the second. Owner 19.10.
4. **§11's containment sentence understates the owed work.** `launch-source.js:136-139` does not look a
   containment profile up; it branches on two adapter ids, under a docstring calling itself
   provider-neutral. The refusal is still right and still must not be deleted (invariant 29 — the
   gate-validator states it would have failed the unit had it been removed). What is owed at 19.10 is a
   profile table *and* the branch's removal, not "the missing profiles".

**What is open, and the condition it places on the phase gate.** The strongest finding is unchanged
from §11 and is now independently re-derived by the gate-validator with a concrete sequence: the
`contributions` cross-check reads the task outside the fence that commits the synthesis
(`sovereign_tools.py:266` → `:294`), so a candidate landing in between yields a COMPLETED task whose
synthesis omits a node. The validator accepts the deferral **on the merits** — strictly narrower than
the two-slot form, no authority boundary touched, and visibly auditable afterwards because
`candidate_node_ids` comes from the same stale read — and **rejects the reason §11 gave for it**
("validated twice") as a process argument that expired when round 2 began. That is a fair correction,
and it is recorded as ruled: **`gate/phase-19` must not be tagged while it is open.** Owner 19.10, as a
gate precondition.

Three contribution guards (caller-order return, blank `node_id`, non-dict entry) still grade nothing —
the same class round 1 patched two instances of, not swept. Owner **19.9**, whose charter is coverage
that can fail; the three mutations are named in U430 so the fix is measured against them.

**Measurements on this tree, taken this turn (D-LOOP-2 — nothing survives a turn).** The
gate-validator's own runs: desktop `node --test test/*.test.js` **963 passed / 0 failed / 0 skipped**;
`py -3.12 -m pytest tests/unit -q` **1889 passed / 1 skipped**, the skip named under `-rs`
(`test_run_frontier_providers_ps1.py:522`, host-coupled); all four JS mutation harnesses re-run, every
mutation CAUGHT, every file restored byte-identically, `git status --porcelain` empty throughout; the
freeze manifest regenerated and confirmed byte-identical (`freeze_integrity_sha256 = 8E604CA3…`, the
operator signature preserved per U222). The builder's own run of
`py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q --durations=20`
is reported in §13 with its real number and its slowest tests — the validator declined to take §11's
`487 passed / 724.51 s` on trust and was right not to.

**D-P16-0.** The in-Electron receipt for exactly this tree exists and is committed:
`docs/evidence/receipts/PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-checkpoint_20260811T095800Z.json`
— `ok: true`, `source.commit: d3c4e6c`, `tracked_product_tree_clean: true`, `live_exchanges: 0`, five
legs, three real ConPTY panes, every session killed in-unit (D-LOOP-1). §11's "a FRESH receipt is owed"
and this file's line-3 header ("both mandatory reviewers owed") are both superseded — by that receipt
and by this section. `ruff` is still absent from this host: the ruff-clean bar is **not run, not
clean.**

**Unit 19.6 is CLOSED.** Two full review rounds, no BLOCKING finding, no prohibited drift, no
product-path defect, and every open item carrying a named owner. **No tag** — `gate/phase-19` belongs to
unit 19.10 and `product/multi-frontier-v2` is never moved. Next: **19.7** (U334/U335/U336 — the runtime
telling the truth about its own failures).

## 13. The long suite, re-run this turn — and the first real data for U339

The gate-validator declined to accept §11's `487 passed / 724.51 s` on trust and recorded it as an
unverified builder claim. It was right to: that number was measured on a host simultaneously running
the desktop suite, four mutation harnesses and several Electron self-checks. Re-run here **alone**, on
the same tree, with the diagnostic 19.10 is chartered to run:

```
py -3.12 -m pytest tests/integration tests/security tests/recovery tests/evaluation -q --durations=20
487 passed, 38 warnings in 613.71s (0:10:13)
```

**Same count, 111 seconds faster, and still over the 600 s ceiling** — so the ceiling is not straddled
by host load alone, which is what the last two units' data suggested. `--durations=20` is the first
half of U339's diagnosis and it is unambiguous: the suite does not *hang*, it *waits on this host*.

| Test | Cost | What it waits on |
|---|---|---|
| `tests/integration/test_opencode_candidate_live.py::test_live_drive_then_governed_candidate_and_merge` | **164.70 s** | a live local model driving OpenCode |
| `tests/integration/test_opencode_worktree_live.py::test_live_opencode_drives_local_model_in_isolated_worktree` | **103.56 s** | the same |
| `test_voice_input.py::test_voice_stack_detection_recorded` | 37.78 s | WSL/NeMo host probe |
| `test_conductor_voice_feed.py::test_select_engine_matches_host_detection_shape` | 36.57 s | the same |
| `test_assembled_roster.py::test_item7_ollama_smoke_runs_live` | 30.29 s | a live Ollama exchange |
| `test_wsl_parakeet.py::test_default_runner_streams_the_complete_program_into_real_wsl` | 17.61 s | real WSL |

Six host-coupled tests account for **390 s of 614 s**; the twentieth-slowest test costs 1.60 s. So the
ceiling is not a property of 487 tests — it is the cost of the six that touch this host's live
subsystems, and it will move with the host, not with the code. **That is the finding U339 needs**, and
it points at the marker set 19.10 is chartered to commit: these are exactly the tests a `live_host`
marker would name, and naming them is what would let a run summary say "the ceiling was met with the
host-coupled legs excluded, and here is what was excluded" instead of silently exceeding it. The second
half of the diagnosis (`--timeout=120 --timeout-method=thread`) is **not needed and should not be
reported as done**: it is for a suite that hangs, and this one does not — nothing here is unbounded, the
six are slow for a reason each one states.

No test was skipped: `487 passed` with no skip line. The 38 warnings are the known
`jsonschema.RefResolver` deprecation from `debate_service/service.py:36`, unchanged by this unit.
