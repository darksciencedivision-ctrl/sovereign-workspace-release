# PHASE 18B `.scope` — WORK-IN-PROGRESS CHECKPOINT (the gate is NOT closed)

**Track:** 18B (OP-12, directive §17) — "registry, adapters, governor, picker, UI (mandatory
validator)". **This unit is the FIRST of four named sub-steps**, not the track.
**Status:** `gate/phase-18b` does **NOT** exist and this unit did not create it.
**Work commit:** `9343975` (initial) + this unit's remediation commit (below).
**Suites:** Python **1719 passed / 1 skipped** (`py -3.12`; the bare `python` on this host is 3.14
and cannot collect the suite), desktop node **640**, terminal node **212**, pyflakes clean on every
changed file, `compute_manifest.py --check` → *freeze check OK: no drift in FROZEN set*.
**Live calls: NONE, and none needed.** Nothing was spawned; nothing outlived the unit (D-LOOP-1).
The operator's real `config/live_operation.json` was neither read into evidence nor committed; only
the tracked `.example` changed.

---

## 1. Why 18B is split, and what the sub-steps are

Directive §3 allows a named sub-step as a work unit for a large phase. 18B is the largest track in
Phase 18 — registries, two adapters, the governor, the interactive ConPTY pane path, the picker and
the UI — and it opened blocked: **U227 said the frozen node vocabulary has no member for either
provider and called the fix operator-reserved.** The sub-steps, recorded in `LOOP_STATE.json`:

| Sub-step | Content | State |
|---|---|---|
| `phase-18b.scope` | provider identity + live-authorization scope (OP-12) + per-provider allowance + governor resources + the U227 determination | **this unit** |
| `phase-18b.adapter` | headless adapters for both providers behind the existing frontier contract; model enumeration; argv/permission guards (U235, U249, U250); credential-scrub enumeration | next |
| `phase-18b.picker` | picker options + supervised ConPTY interactive pane path + launch tickets + UI labels/badges (§9, §11, §14) + the D-P16-0 in-Electron receipt | after |
| `phase-18b.close` | full reviews, evidence report, `gate/phase-18b` | last |

## 2. What this unit did

**(a) U227 — answered, not resolved; see DECISION_REGISTER row D-P18-1.** The two providers are
integrated at the **product layer** using the operator's own OP-12 ids. `schemas/node.schema.json` is
untouched (freeze check OK; `test_the_frozen_node_schema_adapter_enum_is_untouched` pins the enum
verbatim). No false member was fabricated. The precedent — `ollama_local`, a product-layer adapter id
absent from the enum since Phase 15E — is real, and is now recorded as **U254** rather than merely
cited.

**And the claim is now a fence.** `NodeRegistry.register` refuses an `adapter` that is neither a
node@1.0 enum member nor a listed exemption, and logs the refusal. `ADAPTER_EXEMPTIONS` contains
`ollama_local` and nothing else; neither OP-12 provider is on it. This was the spec-auditor's
recommended stronger option, adopted in-unit — *"until that guard exists, 'no schema-valid node
RECORD can name this provider' is a sentence, not a fence."* **Consequence, stated so the next unit
cannot miss it: 18C cannot register a Sovereign node for either provider until the operator rules on
U227**, because the node event log is append-only (invariant 12). U227's owner moves to OPERATOR.

**(b) U237 — the code half.** The live scope is keyed to the authorizing register row: OP-6 → the
two it always did; OP-12 → those plus the new pair. Rows do not lend each other scope. Writing this
exposed a fail-open the OP-6 code had all along — a config with `"register_row": null` was read as
citing every ruling at once, because the loader delegated to an accessor whose no-argument form
returns the union. It raises now (`test_an_unknown_register_row_raises`).

**(c) Per-provider allowance (OP-12 §12), three layers, plus a ref binding.** `terminals_for` /
`register_subscription` / `TerminalLeaseLedger.acquire`. The two subscriptions carry the operator's
literal resource names, are separate buckets, and neither lends the other a terminal. The OP-6 pair
is unchanged at 2.

**(d) U230.** `_AUTHORIZED_PROVIDERS` is no longer read through a private name: `authorized_providers()`
/ `authorizing_register_rows()` / `provider_terminal_cap()` are the declared surface.

**(e) The recon engine's registration verdict was re-based.** The frozen-enum check went from GATING
to a DECLARED note (it could never pass and never will, so it reported a cause 18B is forbidden to
fix while hiding the one it can: the picker cannot offer these providers). The note is printed for
EVERY provider, including one that IS in the enum, so it cannot read as special pleading. Both
providers still read `NOT_REGISTERED`. Both reviewers independently judged this a legitimate
correction rather than a softened criterion; the weakening it does introduce is recorded as **U256**.

## 3. Reviews — BOTH RUN FOREGROUND, IN-TURN, ON THE WORK COMMIT (D-LOOP-2)

Subagent output does not survive a print-mode turn, so the findings are written down here.

**gate-validator: PASS_WITH_RESERVATIONS.** Re-ran every suite itself, mutation-tested each of the
three allowance layers (each independently RED, restored byte-identically, `git status --porcelain`
empty), proved the `register_row: null` fail-open was real by re-introducing it, appended
`"grok_build"` to the frozen enum and confirmed BOTH fences fire (`FREEZE DRIFT DETECTED` **and** the
pinned test), verified the `ollama_local` precedent citation is accurate, and forged
`registered_providers()` to show the new verdict can be made to answer REGISTERED.

**spec-auditor: 2 MAJOR / 8 MEDIUM / 5 MINOR / 4 NIT. PROHIBITED DRIFT: NONE. No invariant violated
at HEAD.** It was asked to attack the U227 judgment adversarially and did: the position is
"honest on its narrow claim and misleading on its implied fence" (§2a above is the fix), the
precedent is "smaller in kind" and was drawn from an unrecorded defect (U254), and the phrase
"product-layer provider ids" is a coinage that made proceeding *look* like a non-decision — hence
D-P18-1 exists as an explicit register row stamped as a **builder** decision, not an operator ruling.

### Must-fix findings, all FIXED IN THIS UNIT

| # | Finding | Fix |
|---|---|---|
| MF-2 / MAJOR-1 (both reviewers, independently) | The published `.example`, if the operator followed it, **crashed the status-bar feed**: `emit_subscription_status` registered every scoped provider at the GLOBAL allowance, the governor refused 2 for a 1-terminal subscription, the emitter exited nonzero, and the shell degraded the WHOLE bar to the em-dash — claude and codex included. U237's own class of defect, recurring in the commit that fixed U237. | Per-provider allowance at both sites + `allowance_by_provider` in the feed; a test now loads the **published file verbatim** and asserts a readable feed. Swept five more emitters and `apps/desktop/main.js` (U258). |
| MAJOR-2 (auditor) | This commit **removed the impossibility that kept U234 inert**. With the OP-12 row in place, an operator config was the only thing between `-Action probe` and an unsupervised frontier CLI. | `_SUPERVISED_PROBE_PATH = False`: `run_probe` refuses AFTER an allowed gate with its own `refused_by: "supervision"` outcome. Tested against the REAL flag: an OP-12 config genuinely opens the gate, and the probe still spawns nothing. |
| MAJOR-2 (validator) / MEDIUM-3 (auditor) | The cap was enforced on the provider ARGUMENT, so a second ref spelling opened a second bucket, and re-registering the operator-named ref under a higher-capped provider raised it to 2 **while the status row kept reporting the wrong provider**. | `assert_resource_binding` in both the governor and the durable ledger; re-registering a ref under a different provider is refused outright. |
| MAJOR-3 / MEDIUM-4 | Two per-provider cap tables with **opposite fail directions** (0 vs 2 for an unknown id) described as "defense in depth". | One table. The governor reads `provider_terminal_cap` and clamps to its own `MAX_ALLOWANCE`; a test asserts the two agree for every authorized provider. |
| MF-1 / MEDIUM-1 | A committed comment cited register row **U254, which did not exist**. | U254 written (§U254 in the issue register). |
| MEDIUM-2 | The `.example` told the operator the picker uses the new ids. It does not. | Corrected to say the picker does NOT offer them yet. |
| MEDIUM-5 | `statusbar-model.js` still named `_AUTHORIZED_PROVIDERS` as its authority, and called it "the frozen node.schema.json adapter enum" — never exactly true, plainly false after OP-12. | Comment names `registered_frontier_providers()` and says why. |
| MEDIUM-6 / MED-1 | `registered_providers()` and `registered_frontier_providers()` were hand-enumerated beside a third hand-enumerated group list. | One `_PROVIDER_TABLE`; all three derive from it. Residual recorded as U256. |
| MEDIUM-7 | The recon tool re-declares the provider/subscription ids as literals. | Kept (its control-plane imports are deliberately lazy so a broken control plane cannot crash the diagnostic) — but the reason is now STATED, and `test_the_recon_ids_equal_the_control_plane_exports` pins them equal. |
| MEDIUM-8 | U227's entry condition was closed with no register trace. | DECISION_REGISTER **D-P18-1**, stamped builder-by-delegation, naming what stays reserved. |
| MINOR-1/-2, MIN-2/-4, NIT | Stale docstrings asserting the pre-`terminals_for` behaviour; a refusal message hardcoding "OP-6" under an OP-12 denial; literals in the statusbar test. | Fixed. |

### Carried, each with a row: U254, U255, U256, U257, U258, and U234's narrowed status.

**One reviewer claim NOT adopted:** the validator's MED-3 (per-provider display ceiling in the status
bar) is real but belongs to the sub-step that puts these providers in `LIVE_PROVIDERS` — doing it now
would wire a UI for options that cannot be selected. Recorded as **U255**, owed *before* `.picker`
lands, with the feed already carrying `allowance_by_provider` so the data is there when it does.

## 4. Falsification harness re-pinned (honestly)

`apps/desktop/main.js` changed by one edit (the `providerAllowance` helper + the chrome field that
calls it), which invalidated `tools/mutation/pane_input_bypass_mutations.js`'s pinned baseline — by
design: *"an unfalsified guard is not a guard."* Every mutation anchor was re-read against the new
tree (the `pane:input` handler body and top, `function makeWindow() {`, `handleOperatorResumeInput`,
`conductorVoiceAuthority`, `clearConductorInputResidue` — all untouched and still unique), the pin
was updated with that reasoning recorded in the file, and the harness re-run: **ALL MUTATIONS
CAUGHT**, restore **BYTE-IDENTICAL** at `D1204A3A…B511B4`.

## 5. NOT done and NOT claimed

No adapter for either provider. No picker option. No launch ticket. No supervised pane. No governor
lease actually taken by a real session. No UI label. No live call, no probe, no model enumeration
from a running CLI. `provider_registration` reports **NOT_REGISTERED** for both, and that is the
truth. 18C's entry conditions are **not** met: the operator's `config/live_operation.json` still
cites OP-6, and U227 — now owner: OPERATOR — gates the node-registration half.
