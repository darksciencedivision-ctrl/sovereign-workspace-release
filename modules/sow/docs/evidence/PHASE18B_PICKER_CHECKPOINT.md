# Phase 18B `.picker` — sub-step record and review rounds

**Status: the sub-step is DONE. The 18B GATE IS NOT CLOSED and `gate/phase-18b` does not exist.**
One sub-step remains (`.close`: full reviews of the whole track, `PHASE18B_EVIDENCE_REPORT.md`, tag).
This file exists because subagent output does not survive a print-mode turn (D-LOOP-2): the findings
below were produced in-turn, in the foreground, and would otherwise live only in a commit message.

| | |
|---|---|
| Work unit | `phase-18b.picker` (directive §3 — a named sub-step of a large phase) |
| Authorization | OP-12 (operator, 2026-07-31), directive §17; operator directive §§8, 9, 11, 12, 13, 14, 16 |
| Work commit | `b05b9ef` (named here, not delegated to the state file — spec-audit Mn-4) + the review-round-1 remediation commit that follows it |
| Live calls | **none to any model.** Four bounded, token-free metadata calls (`grok --version`, `grok models`, `agy --version`, `agy models`) run on the host as part of the picker enumeration. Nothing was spawned for either provider and nothing outlived the unit (D-LOOP-1). |

## What was built

**Picker options (operator directive §8).** `control_plane/nodes/pane_picker.py` gains both providers
under their §14 labels. The option set for each IS that CLI's own `models` listing, enumerated live by
`tools/live/enumerate_pane_picker` through `probe_grok`/`probe_antigravity`. No candidate-label list,
no "CLI default" entry, no invented id: a provider that enumerated nothing shows ZERO options with the
reason on the provider GROUP (a new `status` field, derived uniformly for every provider so no group
can carry an availability judgement that disagrees with the options beneath it).

**Interactive pane path (§9/§11).** `build_interactive_grok_command` / `build_interactive_antigravity_command`
produce TUI argv (no `-p`, no `--output-format`, no prompt) with the permission mode, workspace and —
for grok — cross-session memory pinned. `node_runtime/supervisor/worker_pane_spawn.authorize_worker_pane`
now dispatches all four frontier adapters through the SAME gate chain (roster/profile + live gate →
provider-live → R8 §6 operator terms → CLI presence with a per-provider resolver and a per-provider
exception → I-X3 acquire), and `tools/live/emit_worker_launch` turns a selection into the same
`worker_launch_ticket@1.0` the shell already executes.

**Governor + UI (§12/§14).** Separate subscription resources at allowance 1 each, never merged. The
status bar learned a PER-PROVIDER display ceiling (U255) and the ticket validator learned both
adapters' executables and canonical subscription refs, both pinned cross-language to their Python
authorities.

## Owed items closed, and the one narrowed

| Row | Was | Now |
|---|---|---|
| **U255** | the bar's display ceiling was one global `2`; would have shown `0/2` for a 1-terminal subscription | `PROVIDER_ALLOWANCE` + `capForProvider`, pinned to `provider_terminal_cap`, proved in the running shell (`grok_build 0/1`) |
| **U256** | `registered_providers()` answered REGISTERED for anything added to a literal table | the INTERSECTION with what the pane authorizer will dispatch; the recon's `lease_state` prose corrected with it |
| **U269** | the adapter-side probe had no product consumer | it has one (the picker's enumeration); the duplicate-orchestration half stays open, restated |
| **U270** | the picker must not read `UNVERIFIED` as "signed out" | honoured explicitly: `authenticated=None` blocks nothing, and only an observed `AUTH_REQUIRED` greys |

## Decisions taken, with warrants (not omissions)

| Decision | Warrant | Row |
|---|---|---|
| option set = the CLI's listing; no CLI-default option; `verified: true` | §8 forbids inventing ids; the flag already means "the runtime accepts this id" (roster descriptor, Ollama tag) | D-P18-3 |
| agy's unverifiable auth blocks nothing; a signed-out grok blocks everything | the two CLIs' surfaces genuinely differ; §6 forbids inferring auth from presence | D-P18-4 |
| enumerate on every open, 6 s per call, no cache | §8 permits a cache only if the architecture already caches inventories — it does not | D-P18-5 |
| TUI argv, no prompt, mode/workspace/memory pinned | §9/§11 + T2 (both CLIs read node-controlled config) | D-P18-6 |
| reasoning role only | carried from `.adapter`; the picker reads each backend's own `supported_roles` rather than re-spelling | U260 |

## Carried forward, each with a row

**U271** (uncached enumeration cost, cold path unmeasured), **U272** (`verified` now spans three
provenances in one field), **U273** (the shell can VALIDATE an OP-12 ticket it has never executed —
no Grok/Antigravity ConPTY session has ever been started by this build).

## The boundary this sub-step did NOT cross

`NodeRegistry.register` still refuses both adapter ids (U227, owner: OPERATOR). No Sovereign node
RECORD exists for either provider, and none can until the operator rules. `gate/phase-18b` must not
close on "U227 is answered". No live model call was made; both providers are DENIED by the operator's
own `config/live_operation.json`, which still cites OP-6 — and the in-Electron receipt records that
denial as the observed state rather than assuming it.

## Evidence run in-turn, foreground (D-LOOP-2)

| Check | Result |
|---|---|
| Python suite (`py -3.12 -m pytest tests/ -q`) | 1858 passed, 1 skipped |
| Desktop node suite (`npm test` in `apps/desktop`) | 640 passed, 0 failed |
| Terminal node suite (`node --test terminal/test/*.test.js`) | 212 passed, 0 failed |
| `pyflakes` on every changed Python file | clean (one PRE-EXISTING unused `sys` import in `tests/unit/test_pane_picker_host.py`, present at HEAD, left alone) |
| Freeze check (`compute_manifest.py --check`) | `freeze check OK: no drift in FROZEN set` |
| **In-Electron receipt (D-P16-0)** `node selfcheck/run.js op12-picker` | **PASS** → `docs/evidence/receipts/PHASE18B_PICKER_SELFCHECK.json` |
| In-Electron regression `node selfcheck/run.js picker` (16B) | PASS — 61 options in 5 groups |
| In-Electron regression `node selfcheck/run.js statusbar` (16D) | PASS |

The 18B `.picker` receipt records what the running shell actually did: both groups rendered under the
§14 labels, `grok-4.5` and eleven `agy` ids read from the CLIs' own listings, every option greyed with
a live-authorization reason that names its OWN provider, both selections REFUSED through the governed
intent, and the status bar painting `0/1` for the OP-12 pair beside `0/2` for the OP-6 pair.

## Corrections to everything above, appended (never rewritten — invariant 12)

The section above was written by the turn that produced `b05b9ef`, and review round 1 falsified four
of its statements. They are corrected here rather than edited in place.

1. **"Desktop node suite — 640 passed, 0 failed" was not true of the committed tree.** `b05b9ef`
   changed `apps/desktop/main.js` (three self-check plumbing edits) without re-running
   `npm run test:falsify`, so the U186 pin test — which hashes `main.js` and compares it to
   `PINNED_BASELINE` — went RED: 639 passed, 1 failed. The figure was measured before the final
   edits. Round 1 re-pinned the harness, re-ran all 40 mutations (**all CAUGHT**, restore
   byte-identical) and re-ran the suite green (640/640). Two causes, both now recorded: the missed
   re-run, and **U274** — the same commit also rewrote the worktree copy of `main.js` with CRLF,
   which `git status` cannot see (`.gitattributes` normalises text files before comparing) and which
   broke every `\n` splice anchor in the harness, so it refused to run at all until the file was
   restored to its committed bytes.
2. **"a provider that enumerated nothing shows ZERO options with the reason on the provider GROUP"
   was true of the model and false of the UI.** `renderPicker` never read `group.status`; a
   zero-option provider painted the bare words "no options". Fixed in round 1 (see below). The same
   over-claim appears in the `b05b9ef` commit message and, more carefully worded, in D-P18-3.
3. **"the ticket validator learned both adapters' executables and canonical subscription refs, both
   pinned cross-language" — only the refs are pinned.** `ADAPTER_EXECUTABLE` has no cross-language
   pin; it is the subject of the still-open **U106**, whose scope this sub-step grew from three
   entries to five without a register note. Noted now on U106.
4. **The in-Electron receipt's `enumeration_matched` claimed more than it measured.** The self-check
   header said the ids were "cross-checked against the enumeration the host probe returned in the
   same payload"; no probe payload reaches the renderer (`--emit-picker` emits the picker dict only),
   and the check performed was a shape test over the option's own self-reported fields. Renamed to
   `options_are_uncomposed`, with the header corrected to say what establishes provenance and what
   does not. (Provenance itself held: the gate-validator ran `grok models` and `agy models` on this
   host and reproduced the receipt's slug lists field-for-field.)

Three further owed items the sub-step OWNED and did not discharge are now closed or re-dispositioned
in the register: **U246** (decided — foreign-vendor models stay offered under the subscription that
pays for them, with that disclosed in the option note), **U268** (re-dispositioned: two supervised
paths now exist and `_LIVE_SPAWN_PATH_WIRED` guards the headless one), **U270** (narrowed row written
— the checkpoint had filed it under "closed" with no register entry).

## Review rounds — BOTH REVIEWERS, FOREGROUND, IN-TURN

### Round 1 — 2026-08-01, on `b05b9ef` + the EOL/pin remediation. Transcribed here in full because
subagent output does not survive a print-mode turn (D-LOOP-2), and because summarising a finding to
a count is the exact loss U226 exists to prevent.

**gate-validator: FAIL** (4 BLOCKING, 2 MAJOR, 5 MEDIUM, 5 MINOR).
**spec-auditor: PROHIBITED DRIFT NONE** (3 MAJOR, 5 MEDIUM, 7 MINOR, 3 NIT; no invariant violated).

Both reviewers re-ran every suite themselves and agreed with the numbers below. The validator also
mutated 24 properties and reported which were caught; eleven survived, and those became the findings.

| # | Finding | Reviewer | Disposition |
|---|---|---|---|
| **BLOCKING-1 / M-3** | `renderPicker` reads `g.display` + `g.options` and never `g.status`, so a provider that enumerated nothing renders "no options" with its reason dropped at paint time — falsifying the `_group_status` docstring, D-P18-3, the checkpoint and the commit message. Invisible to the receipt (both CLIs enumerated here) and untestable (a template literal in a browser script). | both, independently | **FIXED** — `apps/desktop/renderer/picker-chrome.js` (UMD, the `pane-feed.js` precedent) owns `providerGroupHtml` + `providerLabel`; 8 new tests; a new `.pk-greason` line; the receipt now reads the painted reason back out of the DOM (leg 3b) |
| **BLOCKING-2** | `apps/desktop/test/worker-launch-source.test.js` contained no `grok`/`agy`/`antigravity` at all: all four OP-12 facts in `launch-source.js` could be reverted with 640 tests green. `FRONTIER_TOKENS` is **fail-open** when reverted — a LOCAL ticket may then name a frontier CLI in its argv, i.e. an uncounted, lease-free `grok` terminal (inv 21 / §12). | gate-validator | **FIXED** — 6 tests; all four reverts re-run RED, restores byte-identical |
| **BLOCKING-3** | The emitter's entire OP-12 branch (`emit_worker_launch.py:110,443`) could be deleted with all 1858 tests green. | gate-validator | **FIXED** — 4 tests (own subscription ref, allowance 1 vs the OP-6 pair's 2, `cli-enumeration` provenance under each provider's own model flag, refusal under an OP-6 config); both reverts RED |
| **BLOCKING-4** | Neither `detect.grok_executable`/`antigravity_executable` nor `_resolve_frontier_executable`'s mapping had any test: pointing one provider's resolver at another's binary survived the full suite. The docstring's "a missing resolver raises KeyError (loudly)" is true of a MISSING entry, never a WRONG one — and §14 is about the wrong one. | gate-validator | **FIXED** — `TestExecutableResolution` (4 tests, identity-checked); both reverts RED |
| **MAJOR-1 / M-1** | `enumeration_matched` published a cross-check the code never performs. | both | **FIXED** — renamed `options_are_uncomposed`, header corrected, and the check strengthened to require each option's note to name **its own** provider's `models` command |
| **MAJOR-2** | U273 recorded the four validator changes as done without recording that none had a test. | gate-validator | **FIXED** — U273 amended (append) |
| **MEDIUM-1** | The receipt carried no `schema`, no `source.commit`, no tree-clean fact, where the 17E receipt carries all four. | gate-validator | **FIXED** — reuses `sourceIdentity()` from the module that owns it |
| **MEDIUM-2** | `PHASE16B_SELFCHECK.json` and `PHASE16D_STATUSBAR_SELFCHECK.json` — two CLOSED gates' receipts — were overwritten in place by regression re-runs; the 16B file stopped describing the 16B run (49→61 options). Directive §2.6 is append-only. | gate-validator | **FIXED** — both restored from their gate commits (`1fa97cd`, `5f682b9`); `selfcheck/receipt-path.js` adds `SHELL_SELFCHECK_RECEIPT_DIR` so a regression run redirects instead of clobbering |
| **MEDIUM-3** | The env-scrub test asserted only the three §17 keys, which the pre-existing classifiers already catch, so the OP-12 term was removable. | gate-validator | **FIXED** — `XAI_API_BASE_URL`, `NODE_OPTIONS`, `NODE_EXTRA_CA_CERTS` added (only the OP-12 classifier covers those); revert RED |
| **MEDIUM-4** | The host provider probes run unconditionally, before and independent of the live switch — a DENIED provider still costs four child processes and a grok.com round-trip. Defensible under §8, but unrecorded. | gate-validator | **RECORDED** — decision row **D-P18-7** with its warrant and what would reverse it; the module docstrings corrected (they still said "both benign, local") |
| **MEDIUM-5 / Md-1** | `U274` was cited in the harness re-pin with no register row. | both | **FIXED** — U274 written |
| **Md-2** | "both pinned cross-language" was half true; U106's scope grew silently. | spec-auditor | **FIXED** — checkpoint correction 3 above + U106 widened |
| **Md-3** | U246, U268 and U270 — three rows this sub-step owned — went un-dispositioned; U270 was reported closed in the checkpoint with no register row. | spec-auditor | **FIXED** — all three written; U246 also produced a product change (the disclosure note) |
| **Md-4** | U255 asked for a ceiling **sourced from the feed**; what shipped was a second hand-maintained JS map, while the emitter's `allowance_by_provider` was dropped on the floor — so an operator who NARROWS `terminals_per_subscription` was still shown the code cap. | spec-auditor | **FIXED** — `buildStatusBarModel` prefers the feed, keeps the pinned map as the fault-path fallback; 4 tests |
| **Md-5** | The record implied the registry fence is what stops an 18C pane; it gates node RECORDS only. | spec-auditor | **FIXED** — U227 clarified (append) |
| **MINOR-1** | `pytest.raises((LiveAuthorizationError, Exception))` is `pytest.raises(Exception)` — it could not tell a governed refusal from a crash, and the live gate was removable with the suite green. | gate-validator | **FIXED** — the gate is named and its subject asserted; revert RED |
| **MINOR-2 / Mn-5** | `receipt.ok` carried two vacuous conjuncts. | both | **FIXED** — folded over every leg the header claims, including the honest-degrade branch |
| **MINOR-3** | `live_authorized: true` (the GLOBAL switch) sat beside two per-provider DENIED reasons. | gate-validator | **FIXED** — renamed `live_switch_authorized_globally` |
| **MINOR-4 / N-1** | The bar's claim was a MODEL claim; no receipt captured the painted chip text, and `statusbar_rows` was last-write-wins (allowance 2 permits two rows). | both | **FIXED** — chip text captured from the DOM and each provider's own name asserted; rows collected as lists |
| **MINOR-5 / Mn-4** | The checkpoint's work commit was "see LOOP_STATE.json". | both | **FIXED** — `b05b9ef` named above |
| **Mn-1, Mn-2, Mn-3, Mn-6, Mn-7, N-3** | Six stale or over-broad docstrings: the frontier gate chain still named two adapters; grok's module said the interactive pane was "not here" while its argv builder is; `enumerate_pane_picker` still said "no frontier call … both benign, local"; the renderer's status-bar comment named two providers and a global `—/2`; `_LIVE_SPAWN_PATH_WIRED` said "the path" where two now exist. | spec-auditor | **FIXED**, each at its own site |
| **N-2** | `summarizeStatusBar.subscriptionCount` counts idle `subscriptionRef:null` rows; the OP-12 addition raises that from 2 to 4 on a host with none registered. Pre-existing shape. | spec-auditor | **CARRIED** — pre-existing, not introduced here; no row opened (the field is diagnostic and no product surface branches on it) |
| **U271 (validator MEDIUM-4 cost note)** | The cold enumeration path is unmeasured. | — | **CARRIED**, row already open |

**What did NOT change as a result of the round:** the sub-step's boundary. No node record exists for
either provider (`NodeRegistry.register` still refuses both ids — U227, owner OPERATOR), no live model
call was made, no ConPTY session was started for either provider, no lease was taken. The validator
verified each of those independently, including that the durable lease ledger's timestamp PRE-DATES
the receipt run. `gate/phase-18b` does not exist and must not close on "U227 is answered".

### Evidence after remediation — every command run by the builder in this turn, foreground

| Check | Result |
|---|---|
| Python suite (`py -3.12 -m pytest tests/ -q`) | **1870 passed, 1 skipped** (was 1858 + 12 new) |
| Desktop node suite (`npm test` in `apps/desktop`) | **654 passed, 0 failed** (was 640 + 14 new) |
| Terminal node suite (`node --test terminal/test/*.test.js`) | **216 passed, 0 failed** (was 212 + 4 new) |
| `npm run test:falsify` (pane-input bypass, 40 mutations) | **ALL MUTATIONS CAUGHT**, restore BYTE-IDENTICAL, re-pinned to the committed-LF `main.js` (`E976589C…97416C5`) |
| Ten review mutations re-run (4 shell + 6 Python) | **all RED**; every file restored and verified byte-identical |
| `pyflakes` on every changed Python file | clean |
| Freeze check (`compute_manifest.py --check`) | `freeze check OK: no drift in FROZEN set` |
| **In-Electron receipt (D-P16-0)** `node selfcheck/run.js op12-picker` | **PASS** — `ok:true`, `schema phase18b_picker_selfcheck@1.0`, `source.commit 19a844f`, `tracked_product_tree_clean: true` |
| In-Electron regressions `picker` (16B) + `statusbar` (16D), redirected | **PASS** (61 options / 5 groups; bar readable) into `docs/evidence/receipts/regressions/`, with both GATE receipts verified byte-unchanged by hash |

The re-run receipt records what the running shell did on the remediated tree: both groups under the
§14 labels, `grok-4.5` and eleven `agy` ids, **the group's refusal reason read back out of the DOM**
and equal to the modelled one (the leg that did not exist before round 1), every reason naming its
own provider, both selections REFUSED through the governed intent, and the status bar's own painted
text — `subscriptions claude 0/2 codex 0/2 grok 0/1 agy 0/1` — proving §14 where the operator reads
it rather than in the model behind it.

### What remains for `.close`

Unchanged by this round: `.close` still owes the whole-track reviews (`.scope` + `.adapter` +
`.picker` together), `docs/evidence/PHASE18B_EVIDENCE_REPORT.md`, and the tag. Carried rows for it to
disposition: U271 (cold enumeration cost), U272 (`verified` spans three provenances), U273 (no OP-12
ConPTY session has ever run), U274, U275, and U106's still-unpinned executable map.
