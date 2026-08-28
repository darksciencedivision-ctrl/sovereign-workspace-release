# PHASE 18E — EVIDENCE REPORT

**Track:** OP-12.2 18E — the LIVE in-Electron acceptance leg the open-switch world demands.
**High-stakes gate** (gate-validator + spec-auditor mandatory, both foreground and in-turn, D-LOOP-2).
**Authorization:** OP-12 / OP-12.1 / **OP-12.2** (operator, 2026-08-02) — `AUTONOMOUS_BUILD_DIRECTIVE.md`
§17, §17.1, **§17.2**.

**Verdict: PASSED — with the typed live round trip SKIPPED WITH RECORD on an operator-only entry
condition (U317).** Everything §17.2(1) asks for up to the keystroke is measured, live, in the
packaged Electron shell, on this host, for **both** providers: a governed picker selection, a
supervised ConPTY pane that is a registered `node@1.1` Sovereign node on the operator's **durable**
append-only log, the exact provider and model verified off the spawned binary and the argv, a real
I-X3 terminal on that provider's own allowance-1 resource taken and handed back, the §2.2 child-env
scrub, teardown to zero, a credential-sentinel scan over the **six sinks this check can read**, and a
durable ledger that reads empty afterwards. (**Two** §17.2(1) elements are unmet, not one: the live
exchange, and the **PTY-transcript** sink §17.2(1) names — what exists is the pane's alternate-buffer
screen at teardown, which keeps no scrollback. That is **U324**, and §5 carries it.)

**The one prompt and the one live answer did not happen**, for both providers, because both CLIs sit
on their **own** first-run directory-trust modal — a protected grant the loop may not answer for the
operator (invariant 1; OP-12 operator directive §11). §17's rule for an unmet entry condition is
*skip-with-record, not failure*; §4 states precisely how far that rule stretches to cover a condition
§17 did not enumerate, and the gate closes on that reading, with the criterion recorded UNMET.

| | |
|---|---|
| Sub-steps | `.hardening` → `.live.shape` → `.live.electron.wiring` → `.live.electron` → `.close` (this) |
| `.hardening` | work `1b252ad`, remediation in-unit, evidence `020b3f0` — `docs/evidence/PHASE18E_HARDENING_CHECKPOINT.md` |
| `.live.shape` | work `3d506be`, remediation `13f0023`, evidence `ba62bfc` — `docs/evidence/PHASE18E_LIVE_SHAPE_CHECKPOINT.md` |
| `.live.electron.wiring` | work `af8daba`, remediation `bfdfe3e`, evidence `369f6bc` — `docs/evidence/PHASE18E_ELECTRON_WIRING_CHECKPOINT.md` |
| `.live.electron` | target built `697ea23`, work `8ea6555`, evidence `d2bab98` — `docs/evidence/PHASE18E_LIVE_ELECTRON_CHECKPOINT.md` |
| `.close` (this unit) | four more live in-Electron runs, **two** rounds of both mandatory reviewers with remediation after each, this report, the FINAL-report supplement, the tags |
| Receipts | `…/receipts/PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json` (`.live.electron`, `source.commit 8ea6555`, preserved byte-identical), `…_CLOSE_20260802T0726Z.json`, `…_CLOSE_20260802T0758Z.json`, and **`…_phase-18e.close_20260802T082536Z.json`** (`source.commit f5f0c3f` — **the receipt this gate rests on**, and the first written under the run-stamped naming that ends the overwrite) |
| Live model exchanges spent by 18E `.close` | **ZERO**, on all four runs — a consent-gated leg stops before a probe prompt is drawn |
| Live model exchanges spent by 18E overall | **3**, all in `.live.shape`'s headless document probes — one more than §17's cap, recorded as **U312**, operator-reserved |
| In-Electron live runs across the track | **8** — four in `.live.electron` (**not three**; corrected against the operator's durable node log, U322) and four here. The log's arithmetic: 79 rows = 15 probe rows + 8 cycles × 8 |

---

## 1. What §17.2 asked for, item by item

> **(1)** Provide the LIVE acceptance path the open-switch world demands — either a live mode of the
> existing target or a sibling target (e.g. `op12-live-acceptance`) — running §17's per-provider
> in-Electron leg: real picker selection → supervised ConPTY pane as a registered Sovereign node →
> verified exact provider+model → ONE harmless prompt → live response → teardown → lease 0 →
> credential-sentinel scan of every sink that now exists (PTY transcript + child env included) →
> durable ledger consistency. ONE live exchange per provider, no simultaneous same-provider sessions.

**Built, and run live eight times** (four in `.live.electron`, four here). The sibling target is
`apps/desktop/selfcheck/op12-live-acceptance-selfcheck.js` + `-verdict.js`, driven by
`node apps/desktop/selfcheck/run.js op12-live-acceptance`. Two of the listed elements did not exist
before this track and were built inside it: a **pane** that is a registered Sovereign node
(`.wiring`), and the **pane-output** sink in the credential scan — which is the pane's screen at
teardown and **not** the PTY transcript §17.2(1) names, a gap this gate records as **U324** rather
than counts as done. Every element **except the prompt, the response and that sink** is green for
both providers — §3 is the table. The prompt and the response are **not run and not claimed**; the
reason is U317 and it is the operator's, not the code's.

> **(2)** Close **U238** … BEFORE the live legs run, so the live verdict cannot rest on either hole.

**Done in `.hardening`, before any live leg** — both holes: the whitespace-collapsed echo fold
(twelve pure-echo shapes measured ACCEPTED → refused, three genuine-answer controls unmoved) and the
whole-document fallback (acceptance now calls a strict reader that reads only recognised response
keys). Register: **U238 CLOSED**; the narrower successors it split out (**U304** paraphrased echo,
**U305** neither provider's real document had been read) are recorded, and **U305 was then answered
by live measurement** in `.live.shape` — which is also how **U310** (`grok -p` exits zero having said
nothing) and the **U311** withdrawal of one previously-recorded live acceptance were found. The
closure is load-bearing here: the live verdict this gate rests on cannot be satisfied by an echo or
by a token buried anywhere in a document.

> **(3)** Sweep the small register debts this run exposed as in-scope-if-cheap: U234/U283/U290
> lineage is already recorded — verify, don't redo; the `gates.operator_terms_confirmed`
> parameter-default (scope_note_gate_map) gets the U283-style closure on the pane/worker emitter.

**Verified, not redone** (this unit re-checked each in the code, not in the prose):

| Item | Recorded state | Verified at `.close` |
|---|---|---|
| U234 | NARROWED and ENFORCED at 18C `.probe-path` — a headless provider call runs inside a governed, leased, supervised, job-bounded session | `node_runtime/supervisor/provider_probe_session.py::governed_probe_session` still requires `profile_loader`, `operator_terms_confirmed` **and** `registrar` as keywords with no defaults |
| U283 | NARROWED at 18C `.probe-path` (U91's shape: a manufactured `cloud` profile) | `tools/live/emit_worker_launch.py` — `profile_loader` and `operator_terms_confirmed` are required keywords; `main()` passes `profile_loader_from_host()` |
| U290 | CLOSED at 18C `.close` (verifying one provider probed the other's CLI) | `tools/live/enumerate_pane_picker.py::only_op12_probe` present and still the single entry point |

The `gates.operator_terms_confirmed` default closure on the pane/worker emitter is **U292(a)**,
**closed in `.hardening`** and proved by execution rather than by signature: the real script with the
real env var and real stdin refuses under `offline_airgapped` (`refused_by: profile_roster`) and
authorizes under `cloud`, so the air-gap leg cannot pass by refusing everything. `.hardening`'s own
spec-audit then found an **ordering** defect that only became reachable once the gate was reachable
(**U303**: the enumeration that verifies a selection left the host *before* the air-gap gate
refused) and closed it in the same unit, with a detonator in place of the enumerator so the guard
test cannot go green through a regression.

> **(4)** Mandatory gate-validator + spec-auditor; supplement the Phase-18 addendum; per §17.1 the
> existing `product/multi-frontier` tag is never moved — apply successor tag
> `product/multi-frontier-v2`.

Both reviewers ran **foreground, in-turn, concurrently** on this composition; their verdicts and
every finding's disposition are §6, which was written **after** they returned. (The draft they
reviewed asserted this paragraph in the past tense before any of it had happened — both caught it
independently, and §6 records that as the finding it was.) The Phase-18 addendum is supplemented in
`FINAL_LIVE_REPORT.md` — a new section; the 2026-08-01 addendum text is left standing, with the two
lines the operator's own actions have since overtaken named there explicitly. **The tags follow this
report's own commit**, not the other way round: `gate/phase-18e` and the **successor**
`product/multi-frontier-v2`, applied after §6's verdicts and this unit's remediation;
`product/multi-frontier` is not moved.

Also from §17.2: *"Voice-probe noise seen during the operator's failed run (`voice probe exited
null` during teardown) is expected reap noise unless the live legs reproduce it in a healthy world —
then it is a finding, not noise."* Across the eight live in-Electron runs of this track **it did not
recur**, so it stays reap noise and no finding is manufactured out of it.

## 2. The three sub-steps behind the leg, in one paragraph each

**`.hardening`** closed §17.2(2)/(3) and is summarised above. 10/10 mutation rows RED. What it did
**not** close, and this report will not compress away (spec-audit M-8): the execution transcript that
proves U292(a) proves the **profile** gate (`refused_by: profile_roster`), and
`operator_terms_confirmed` remains a hard-coded `True` moved one frame up, to a call site that cites
OP-9/OP-12. Nothing machine-readable can measure whether a subscription's terms permit a supervised
CLI call — that is the operator's determination by construction (invariant 1) — and the residual
risk that a fifth adapter inherits a confirmation no ruling covers is **U308**, still OPEN.

**`.live.shape`** answered the question the live legs would otherwise have guessed at: what a real
provider response document *looks like*. `describe_provider_document` reports **structure only** —
key names (secret-scrubbed and length-bounded), value types, dotted paths, and whether the **strict**
reader can see the token — never a string or numeric leaf, because the shape is published as
evidence. Measured on two governed live probes: `google_antigravity` is flat and its `response` key
is recognised (**the first acceptance earned under the strict reader**), while `grok_build` **exits
zero having said nothing** — `text: ""`, `stopReason: "cancelled"`, the token present only in a
`thought` trace where the model restates the instruction to itself (**U310**). No nested-answer
accommodation was added: on that evidence it would have re-opened U238 inside the unit sent to verify
its closure. A hypothesis was tested and **refuted** (`--permission-mode default` cancels
identically), so the `plan` pin did not move. Cost: one live exchange more than §17's cap, recorded
as **U312** and left to the operator rather than rationalised. **11/11** mutations RED (re-run here;
the sub-step's own report says 11/11 — the "8/8" in this track's 2026-08-01 register row predates the
three rows its reviewers added, and is corrected in the `.close` row rather than by editing an
append-only entry).

**`.live.electron.wiring`** built what §17.2(1) requires and 18D had built for the one-shot probe
session only: a supervised **pane** that is a Sovereign node. Three facts written at the three moments
each becomes true — `node@1.1` in SPAWNING at ticket time (a registrar refusal refuses the *session*
and hands the durable terminal back), READY with the supervised pid when the shell's ConPTY actually
comes up (only the shell can know that; the pid is the attestation), TERMINATED + exit at release
(deliberately not conditional on the lease half, so a lease reaped for a dead holder cannot strand a
record in SPAWNING forever). Both reviewers converged independently on the same real MAJOR (**U315**:
pane ids are reused, so the node **key** identifies nothing — the incarnation binding already existed
in the record's own uuid and was simply never compared). 22/22 mutations RED.

**`.live.electron`** ran the leg live for the first time, found **U317**, and — this is the part worth
keeping — found that its own first receipt had reported the modal as *"the keystrokes are not
reaching the live session"*: a dead-terminal finding about a session that was **alive and waiting for
a human**. That is the exact shape 17A and U310 exist to prevent, caught here by the build's own
reviewers before it was published as a defect in the product. Every outcome sentence in the receipt is
**computed from the legs** now. 28/28 mutations RED; U318–U321 recorded. **It also miscounted its own
runs** — three reported, four on the operator's durable node log — found at this gate and corrected
in `PHASE18E_LIVE_ELECTRON_CHECKPOINT.CORRECTION.md` (**U322**; the checkpoint itself is never
edited). The unit counted the runs that left receipts, and the target writes to one fixed path.

## 3. The closing live runs — four of them, and the last one is the tagged tree

| # | started (UTC) | `source.commit` | tree | what it was for | outcome |
|---|---|---|---|---|---|
| 1 | 07:26:03 | `f76e0b6` | clean | **the only honest way to learn whether the operator had cleared U317** was to ask the world, not the register | both legs consent-gated, `live_exchanges_spent: 0` |
| 2 | 07:57:37 | `b901d60` | **dirty** (`run.js` under edit) | first run of the widened credential scan | `repo_unchanged_by_the_run` **refused it** — the rule tightened one commit earlier catching its own author |
| 3 | 07:58:28 | `737f6db` | clean before **and after** | round-1 remediation, verified live | both legs consent-gated, everything else green |
| 4 | 08:25:38 | `f5f0c3f` | clean before **and after** | **the receipt this gate rests on** — round-2 remediation, and the first run under the run-stamped receipt name | both legs consent-gated, `live_exchanges_spent: 0`, 6 sinks, 5 sentinels planted / 0 skipped, node log 71 → 79, chain intact, leases 1 → 0 |

Receipts: `…_CLOSE_20260802T0726Z.json` (run 1), `…_CLOSE_20260802T0758Z.json` (run 3) and
**`…_phase-18e.close_20260802T082536Z.json`** (run 4). Run 2 published no artifact — under the old
naming the next run superseded it — which is exactly the asymmetry that produced U322, so it is
counted here in prose and in the node log rather than left to a missing file. Its credential scan was
observed green over six sinks in the emitted receipt before it was superseded; that is an
**observation, not evidence**, and it is written as one.

**On the receipt files, and the defect underneath them.** The `.live.electron` receipt at the
target's old fixed path is cited by that checkpoint *by its content* (`source.commit: 8ea6555`), so
overwriting it would make an already-published document describe a file that no longer says what it
quotes. Runs 1–3 were therefore **copied to siblings named for their real write times and the
committed receipt restored byte-identical** (verified by `git status`; the gate-validator hashed it
against `d2bab98` and matched). That was a hand practice covering a code defect, and both round-2
reviewers said so — the operator instruction in the FINAL supplement would have run the same
overwrite on the operator's behalf. **The target now writes a run-stamped name**
(`…_<unit>_<UTC>.json`) and never overwrites: run 4's receipt landed at its own path with no copying,
and the canonical name still holds exactly what `.live.electron` published. `unit` is a self-declared
label with no authority; `source.commit` and `started` are the measured facts.

| Fact §17.2(1) asks for | `grok_build` | `google_antigravity` |
|---|---|---|
| the operator's own click path (`spawnFromSelection`), governed | ✅ launched, no refusal | ✅ launched, no refusal |
| exact provider + model verified off the spawned binary and argv | ✅ `grok-4.5` (`grok.CMD --cwd … --permission-mode plan --no-memory -m grok-4.5`) | ✅ `gemini-3.6-flash-low` (`agy.EXE --mode plan --model gemini-3.6-flash-low --add-dir …`) |
| supervised ConPTY pane, `RUNNING`, in the governed workspace | ✅ pid 121520 | ✅ pid 121808 |
| a registered Sovereign node on the operator's **durable** log | ✅ `worker-pane-2`, `node@1.1`, SPAWNING → READY(pid) → TERMINATED + exit | ✅ `worker-pane-3`, `node@1.1`, same lifecycle |
| durable I-X3 terminal on its own allowance-1 resource, seen cross-process | ✅ in use 1 → 0 | ✅ in use 1 → 0 |
| §2.2 child-environment scrub | ✅ 10 names dropped, not inherited | ✅ 10 names dropped, not inherited |
| pane painted and settled (the 16A defect does not recur) | ✅ banner seen, quiescent | ✅ banner seen, quiescent |
| **ONE harmless prompt → ONE live answer** | **NOT RUN — consent gate** | **NOT RUN — consent gate** |
| teardown, lease 0, session killed | ✅ | ✅ |

Whole-run, machine-checked on run 4: `sessions_before === sessions_after === 0`; `lease_zero.ok`;
`real_ledger_leases_empty: true`; `node_log_chain.ok` over **79** rows (71 → 79, four per pane per
provider); `credential_scan.ok` over **6 sinks** — `main-process.log`, this receipt pre-write, **the
operator's durable node log**, **the operator's durable lease ledger** (both added at this gate: they
are written by `py -3.12` children that inherit the sentinel-bearing environment), and each pane's
**screen as rendered at teardown** — with 5 planted sentinels; `owed_named.ok` over 6 OWED keys;
`repo_unchanged_by_the_run.ok`, which now requires the product tree to be **clean** before and after
rather than merely to agree with itself; `live_exchanges_spent: 0`; `source.commit ==
source_after.commit == f5f0c3f` with a clean tracked product tree at both ends. Five sentinels were
**planted** and none **skipped** — a credential name the host already sets is now skipped rather than
read and overwritten, and the receipt reports both lists by name (§8).

**What the pane sink is not** (U324): both CLIs are full-screen TUIs on xterm's **alternate** buffer,
which keeps no scrollback, so that sink is the screen at teardown and **not** the session's whole
output. Material printed and repainted over is outside it, and no coverage of it is claimed here or
in the receipt. On this run the criterion is also, honestly, **untested by circumstance**: neither
CLI got past its trust modal, so neither could have written anything anywhere — the same is true of
`repo_unchanged_by_the_run`, which is a correct rule that this run did not stress.

**The gate itself, in the CLIs' own words, captured from the panes:**

* `grok`: *"Grok Build may run or modify contents in this directory, posing security risks.
  Yes, proceed y / No, quit n"*
* `agy`: *"Do you trust the contents of this project? Antigravity CLI requires permission to read,
  edit, and execute files here. > Yes, I trust this folder / No, exit"*

**One new observation, recorded because it is new and not because it changes anything.** `agy`'s
banner on these runs reads *"Welcome to the Antigravity CLI. You are currently not signed in. ⣯ Signing
in…"* before the trust modal appears, and the modal's own status line reads `plan · Gemini 3.6 Flash`.
This neither confirms nor refutes the CLI's auth state — the trust modal blocks before any model call,
so **U233** (`agy` exposes no offline auth surface) is unchanged, and nothing about sign-in is claimed
here. It is written down so that a future run which *does* get past the modal can tell a sign-in
prompt from a trust prompt rather than rediscovering the difference. It is also a host effect this
check causes and does not scan: a sign-in the check started writes session material into that CLI's
own store, outside every sink here and outside this repo — see §5.5.

## 4. Why the loop did not answer the modal — and why that is a PASS, not a stall

Answering grants a frontier CLI directory-scoped authority to **read, edit and execute** in the
operator's own workspace; `agy`'s modal says exactly that. Four independent reasons, any one of which
is sufficient:

1. **Invariant 1** — the app never self-authorizes a protected action.
2. **OP-12 operator directive §11** — tool permission is subordinate to launch tickets. Verbatim:
   *"Do not automatically enable: `--always-approve`, unrestricted shell access, unrestricted
   filesystem writes, unsandboxed execution"*, and *"a provider CLI's own 'always approve' setting is
   never operator approval."* (This report's shorthand for the first of those — "no always-approve,
   no unsandboxed defaults" — is a summary, not a quotation; the round-2 spec-audit was right that
   printing it in quotation marks beside a verbatim one made it look like one.)
3. **OP-12/OP-12.2 authorize live *sessions* under the operator's subscriptions** — a statement about
   subscription terms. Reading it as also delegating a filesystem-trust decision over the operator's
   repository is an expansion the operator never wrote.
4. **Fail closed on ambiguity** (§4 of the buildout directive) settles any residue the same way.

It is **not** a permission-mode problem: both panes already launch in the least-authority mode this
build pins (`--permission-mode plan` / `--mode plan`) and are asked anyway — directory trust is
orthogonal to tool-permission mode. No **permitted** argv flag dismisses it; the two that might
(`--always-approve`, `--dangerously-skip-permissions`, both recorded in this repo's own 18A host
reconnaissance) are precisely what §11 forbids, and neither was tried. `.live.electron` asked both
mandatory reviewers to attack this reading as over-strict; both judged it correct, the gate-validator
adding the asymmetry that settles it (*answering is an unrecorded, irreversible grant; refusing costs
the operator one keystroke and is fully recorded*) and the spec-auditor adding that answering **would
have been** the invariant-1 violation.

**Why the gate closes rather than blocks — and exactly how strong that argument is.** §17's
acceptance row states the rule for its own entry conditions: *unmet ⇒ skip-with-record, not failure.*
Both reviewers pushed back on the first draft's use of that sentence and they were right, so it is
stated precisely here (spec-audit M-3, gate-validator's disposition analysis):

* §17 **enumerates two** entry conditions — each CLI's login, and the operator's edit to
  `config/live_operation.json` — and OP-12.2's own "Standing at arming" records that **both are now
  met**. The directory-trust modal is a **third condition, discovered in flight**. Applying the
  skip-with-record clause to it is an **analogy**, not a citation. It is a good analogy — one-time,
  per-CLI, operator-only, out-of-band, and no code change can reach it — but it is the loop's
  reading, and this report will not dress it as the directive's own words.
* Directive **§8** genuinely does not yield BLOCKED. Its two categories are (a) credential, purchase
  or hardware needs with no §6 substitution — this is none of those — and (b) *"an irreconcilable
  canonical-spec contradiction"*, which an adversarial reader would test against a §17.2(1) criterion
  no code change can reach. It is not that either: nothing in the canonical set contradicts anything
  here. A provider CLI asks its owner a question, the owner has not answered yet, and invariant 1 is
  working exactly as written. §1 also forbids the loop to wait on the operator.
* Directive **§6** is satisfied in part, not in whole: §6 asks that the nearest faithful equivalent
  be **run**, and the full governance path around the missing measurement was. **Nothing stands in
  for the live answer, because nothing can** — there is no substitute for a model replying, only its
  absence, named.

So the gate closes on what the track proved, with §17.2(1)'s live-exchange criterion recorded
**UNMET**, and the tag it carries certifies the governed path rather than a model's reply. The
disposition, and this reasoning, are register row **D-P18-13**.

## 5. Substitutions and limitations (Directive §6, stated exactly)

1. **The typed live round trip did not happen, for either provider.** No Grok or Antigravity model
   has answered a prompt from this build's **pane path**. `providers_live` is `[]`,
   `live_exchanges_spent` is `0`, and every outcome sentence in the receipt is computed from the legs
   rather than asserted. **U317**, operator-owned. (The headless probe path is a different story and
   §9 tells it: `google_antigravity` has answered this build once; `grok_build` never verifiably has.)
2. **The §17.2(1) PTY-transcript sink does not exist.** What the credential scan reads is the pane's
   alternate-buffer **screen at teardown**, which keeps no scrollback — so material printed and
   repainted over is outside it, `agy`'s sign-in phase being the live example. This is the **second**
   unmet §17.2(1) element, recorded as **U324**; a real transcript sink needs the ConPTY data stream
   tee'd where the shell can scan it, which the renderer buffer structurally is not.
3. **U310 remains untested on the interactive channel.** `grok -p` exits zero saying nothing; whether
   an interactive pane shares that defect **cannot be known until the consent gate is cleared**. This
   track learned nothing about it and claims nothing.
4. **Nothing was injected in these runs** — no fixture switch, no scratch ledger, no scratch node log.
   This is the operator's real switch (`register_row: OP-12`, both OP-12 providers authorized), the
   operator's real durable lease ledger and the operator's real durable node log. That is a change of
   kind from 18D, whose four injected inputs are named in its own report.
5. **Disclosed host cost, in full.** Each of the eight runs performs the CLIs' own bounded metadata
   calls (`grok --version`/`grok models`, `agy --version`/`agy models`) — token-free, but they do
   leave this host (D-P18-7/U271/U290 disclose them; `only_op12_probe` keeps a selection from probing
   the other provider). **Two host effects beyond the network** are added here because the first
   draft did not carry them (spec-audit m-3): launching each CLI interactively causes it to create or
   update its **own first-run state outside this repository root**, and in `agy`'s case to **begin a
   sign-in** — neither is written by this build, neither is scanned by any sink, and both are the
   provider's own storage.
6. **U312 stands, operator-reserved:** 18E spent three live exchanges in `.live.shape` where §17
   allows one per provider. It is recorded as an overrun, not rationalised, and `.close` spent none.
7. **Recorded, not fixed — every open row this track owns**, because §5 is read as the complete
   limitation set:
   * **U306** an unset deployment profile resolves to the most permissive one; **U307**;
     **U308** the terms citation is per-provider while the literal carrying it is not; **U309**
     `ruff` is not installed on this host, so CLAUDE.md's ruff-clean rule is **unverified** for this
     track's Python (pyflakes stands in);
   * **U313** the OP-6 providers' panes (`claude_code`, `openai_codex_cli`) hold a durable I-X3
     terminal and are **not** node records — invariant 2 is enforced for the two OP-12 providers
     only, by deliberate scope (registering the OP-6 panes changes behaviour OP-12's own supersession
     list calls untouchable);
   * **U314** a node record can be attested for liveness, never for parentage (U25/U78(a));
     **U316** a failed node-record close is never retried;
   * **U318** the append-only chain is verified as a linked list rather than recomputed; **U319** the
     observed spawn is bound to a pane by binary path alone, and the model id is read off the
     ticket's argv rather than the observed spawn's own args — so §3's "verified off the spawned
     binary and the argv" is exactly that far and no further; **U320** the self-check module's own
     orchestration has no falsifiable coverage (narrowed here: **three** of its rules moved into the
     verdict module and are now mutation-covered — `repoUnchangedByTheRun`, `credentialSinkMap`,
     `sentinelPlan`); **U321** presentation residuals, of which **(d) is now CLOSED** — the
     environment-restore path no longer reads any real credential value (§8) — leaving (a) a gated
     leg rendering not-applicable fields as negative facts, (b) and (c);
   * **new at this gate:** **U322** (the `.live.electron` run count, closed by correction),
     **U323** (`paneConsentGate` cannot separate a modal from a model quoting one), **U324** (the
     pane sink is an alternate-screen viewport), **U325** (the lease ledger cannot see a hand-run
     provider CLI — including the one the operator step asks for; let it exit before re-running).

## 6. Both mandatory reviewers — foreground, in-turn, concurrent (D-LOOP-2), twice

### 6.1 Round 1 — on the composition as first drafted

Run on the composition at commit `4061230` (the first close run's receipt) with the draft of this
report on disk. **gate-validator: FAIL** (2 BLOCKING, 2 MAJOR, 4 MEDIUM, 4 MINOR). **spec-auditor:
PROHIBITED DRIFT: NONE**, no invariant violated in enforcement terms, with 2 MAJOR, 6 MEDIUM, 6 MINOR,
3 NIT. The validator reproduced every suite and harness number itself, ran **13 adversarial probes of
its own** against the verdict module, corroborated the live run **independently off the operator's
node log** (seq 48–55: node uuids, leases, pids, model refs, `SPAWNING → READY → TERMINATED → exit`),
verified the preserved `.live.electron` receipt is byte-identical to `d2bab98`'s
(`c89ec3aa36edc76a1aeec732ddaab8180c1316cf`), and swept the host for surviving processes.

**They converged INDEPENDENTLY on the same MAJOR for the third time in this track, and it was real:
the gate-closing report asserted, in the past tense, three things that had not happened — that both
reviewers had run, that the FINAL-report supplement was written, and that the tags were applied — and
stated its own verdict ahead of the reviews it cited as its ground.** That is iteration 115's
inversion (a field), then iteration 117's (prose inside a receipt), arriving a third time one layer
further out: in the document that closes the gate. It is fixed by writing the artifacts and then the
sentences, and this section is the record that the order was wrong first.

| # | Finding | Disposition |
|---|---|---|
| **GV BLOCKING-1 / SA M-1(b)** | §1 said the Phase-18 addendum "is supplemented in `FINAL_LIVE_REPORT.md`"; that file contained no 18E section at all | **FIXED** — the supplement is written (§7 of this report lists it); the claim now describes an artifact a reader can open |
| **GV BLOCKING-2** | the report (and the `.live.electron` checkpoint) counted **three** live in-Electron runs; the operator's durable node log carries **four**, the extra at 06:52:44Z | **FIXED + RECORDED (U322)** — counts restated with the arithmetic (15 probe rows + 8 per pane cycle; 79 rows = 8 cycles by the gate run), a `.CORRECTION.md` beside the never-edited checkpoint, the disclosed host cost restated per run, and — at round 2 — the CAUSE fixed rather than described: receipts are run-stamped and overwrite nothing |
| **GV MAJOR-1 / SA M-1(a,c)** | reviewer outcomes and the verdict asserted before the reviews returned | **FIXED** — §6 is written from the returned verdicts; §1 and §9 point at it rather than at their own expectation |
| **GV MAJOR-2 / SA m-6** | no DECISION_REGISTER row for `.live.electron`, and none for the delegated gate closure | **FIXED** — both rows appended, plus **D-P18-13** carrying the skip-with-record disposition and its reasoning |
| **SA M-2 (MAJOR)** | "a credential scan over every sink that now exists" was false: the two durable stores this run WRITES were unscanned, and the "PTY transcript" sink is an alternate-screen viewport | **FIXED + RECORDED (U324)** — node log and lease ledger are sinks now, named by path, in a `credentialSinkMap` the tests can weaken (M32); the pane sink is renamed to what it is everywhere; the alt-buffer limit is stated, not papered over |
| **GV MEDIUM-1** | `.live.shape` mutation count given as 8/8; the harness prints **11/11** | **FIXED** — §2 and §7 say 11/11 (re-run here); the stale "8/8" in the 2026-08-01 register row is corrected in the new row rather than by editing an append-only entry |
| **GV MEDIUM-2** | the U310-burial guard keyed on `echoed` alone, so a leg that **submitted** a prompt and got silence was still reportable as an honest consent skip | **FIXED** — a late gate may now explain only a leg that neither echoed nor submitted; test + mutation **M29**, and M26's test narrowed to `submitted:false` so each row measures its own guard |
| **GV MEDIUM-3** | `paneConsentGate`'s docstring claimed requiring ALL phrases ends the "a model said it" class; a paraphrase matches in full | **FIXED (comment) + RECORDED (U323)** — with a test that pins the current behaviour so the limitation is what a reader finds |
| **GV MEDIUM-4** | `repo_unchanged_by_the_run.ok` compared two readings, so two **dirty** ones agreed | **FIXED** — `repoUnchangedByTheRun` requires clean at both ends; test + mutation **M31**. It then refused this unit's own run 2, on a dirty tree — the rule catching its author |
| **SA M-3** | the skip-with-record justification was an analogy presented as a citation; §6 substitution claimed in whole | **FIXED** — §4 states both limits explicitly, and D-P18-13 records the disposition as the loop's reading |
| **SA M-4** | "no credential was created, read, stored or transmitted" contradicted by the environment-restore read (U321(d)) and by `agy`'s sign-in | **FIXED, and superseded in round 2** — §8 no longer has a read to state (the round-2 fix removed it) and §5.5 carries the host effects; the 18C verdict's stale comment saying otherwise is corrected in code |
| **SA M-5** | the receipt claimed "nothing else on this host can hold them" while instructing the operator to hand-run `grok` — which takes no lease | **FIXED (wording) + RECORDED (U325)** — the scope note says what the ledger can and cannot see, and tells the operator to let that CLI exit first |
| **SA M-6 / M-7** | §5 did not carry U313's OP-6 pane gap, nor U306–U309/U314/U316 | **FIXED** — §5.6 enumerates every open row this track owns |
| **SA M-8** | §1(3) compressed U292(a) into "closed", while the terms gate remains a hard-coded `True` one frame up | **FIXED** — §2 says so and points at U308 |
| **GV MINOR-1 / SA m-4** | the close receipt did not self-identify; the lease-ledger path was unpublished | **FIXED** — `unit`, `lease_ledger_file`, `node_log_file` in the receipt; `--unit` on the runner |
| **GV MINOR-2** | a skip could cite a gate id no signature can produce | **FIXED** — `KNOWN_CONSENT_GATE_IDS`; test + mutation **M30** |
| **GV MINOR-3** | the OWED citation rule matched inside a word (`MENU42`) | **FIXED** — word-anchored; test + mutation **M33** |
| **GV MINOR-4** | the 18C receipt was overwritten in place at `51c3340` (the operator's own run) | **ACKNOWLEDGED** — superseded content is readable at `git show 5b19ccb:…`; the dated-sibling convention this unit uses is the response |
| **SA m-1 / m-2 / n-1 / n-3** | `repo_unchanged` vacuous on this run; "verified off the spawned binary and argv" overstates U319; "at the tree this gate tags" true of product paths only; U321(a) unmentioned | **FIXED** — each qualified where it appears (§3, §5.6) |
| **SA m-3** | host effects outside the network were undisclosed | **FIXED** — §5.5 |
| **SA m-5 / SA n-2** | `PREFERRED_MODEL`'s "cheapest" claim with no cost data; the receipt sink named a sibling file | **FIXED** — a name heuristic, said as one (U321(b)); the sink names the file actually written |
| **GV "what I could not verify" (5 items)** | that the reviewers ran at all leaves no inspectable artifact; the 06:52Z run wrote no receipt; whether any argv flag dismisses the modal (untested by instruction); `conhost` provenance; anything past the modal | **ACCEPTED AS STATED** — three are structural (a subagent leaves no artifact; a superseded run leaves none; U317 is the boundary), one is U322's own cause **and is now fixed in code** (run-stamped receipts, §6.2), and the flag question is answered by §11 rather than by experiment, which §4 says |

### 6.2 Round 2 — the same two reviewers, on the remediated composition

Run foreground, in-turn and concurrently again, on commits `4061230`/`b901d60`/`737f6db` with the
rewritten report and the new receipt on disk. **gate-validator: PASS_WITH_RESERVATIONS** — "the
round-1 BLOCKINGs and MAJORs are genuinely fixed and I reproduced every number myself… **No BLOCKING
or MAJOR remains**", with 3 MEDIUM and 3 MINOR/NIT it asked to be discharged before the gate commit.
**spec-auditor: PROHIBITED DRIFT: NONE**, no invariant violated in enforcement terms, with 3 MAJOR,
5 MEDIUM and several MINOR/NIT — and it closed six of its eight round-1 findings outright.

The validator went past the receipt to check the evidence underneath it: it **recomputed the whole
79-row hash chain** with `control_plane/nodes/event_log._row_hash` (0 mismatches, 0 seq gaps —
stronger than the receipt's own linked-list check, U318), re-derived the run count from the log, and
hashed all three older receipts against their commits. Both reviewers judged the disposition
question independently and both landed on *defensible as reasoned*, the validator naming the one
thing it would not let pass unstated: **this gate closes over U312, an unruled live-budget overrun,
and that is the operator's to rule on, not a cleared item.** That sentence is repeated here because
it is right.

| # | Round-2 finding | Disposition |
|---|---|---|
| **SA MAJOR-1** | the FINAL supplement said "both providers answered live" (of the operator's own probe) while its §6 said "no live model ever has" — and U311, which **withdrew** the recorded grok acceptance, appeared nowhere in the operator-facing document | **FIXED** — §9 here and the supplement now carry the three-way split: agy answered once through the headless probe path; grok has never verifiably answered by any path (U310 + the U311 withdrawal); neither has answered through the pane path. The fourth instance of this track's inversion, caught by a reviewer rather than by a reader |
| **SA MAJOR-2** | the false absolute "a scan over every sink that now exists" survived in two summary lines, and §17.2(1)'s **PTY-transcript** sink is a *second* unmet element presented as met | **FIXED** — both lines say "the six sinks this check can read"; §5.2 and §9 record the transcript sink as UNMET with U324 |
| **SA MAJOR-3 / GV MEDIUM-3** | the supplement's own operator command would have **overwritten the committed `.live.electron` receipt** — U322's structural cause, unfixed, handed to the operator | **FIXED IN CODE** — receipts are run-stamped (`…_<unit>_<UTC>.json`) and never overwritten; run 4 landed at its own path with no copying, and the canonical file was untouched (`git status` clean for it) |
| **SA MEDIUM-1** | the round-1 fix keyed on SUBMISSION, which in this check cannot happen without an echo — so the rule could not fire, and the residual route (typed, never echoed) was **pinned green by a test** | **FIXED** — the rule keys on **TYPING**; the two tests that asserted the old semantics are rewritten with the reason; M29 re-aimed; U323's register paragraph corrected, since its "not reachable" claim rested on the same mistake |
| **SA MEDIUM-5** | the check **read** any real credential value present on the host into memory so it could restore it — §2.2 and OP-12 §13 forbid reading, not only storing | **FIXED** — `sentinelPlan`: a name the host already sets is skipped, never read, never overwritten; planted and skipped names are reported; only planted sentinels are scanned for. Test + mutation **M34** |
| **GV MEDIUM-1 / SA MEDIUM-3** | the report claimed the stale `8/8` was "corrected in the `.close` register row"; the row said nothing about it | **FIXED** — the clause is in the row now |
| **GV MEDIUM-2 / SA MEDIUM-2** | §9 rested PASSED on a returned **FAIL** with no recorded re-validation | **FIXED** — this section, and §9 now rests on it explicitly |
| **SA MEDIUM-4** | U322 marked CLOSED while its cause was untouched, and claimed "`.close` responded in code" | **FIXED** — the cause is fixed in code (above), and the register row says what was and was not done |
| **GV MINOR-1 / SA M-1 residual** | the register row and the supplement asserted tags as already applied | **FIXED** — phrased as applied by the commit that carries them |
| **GV MINOR-2** | "all runs spent 0" read as measurement while half had no surviving receipt | **FIXED** — §7 marks which runs are measured and which are inferred, with the inference stated |
| **GV MINOR-3** | run 2's "scan green over 6 sinks" is unverifiable | **FIXED** — §3 states it as an observation of a superseded artifact |
| **GV NIT-1** | the consent guards used `=== true`, so `submitted: 1` escaped | **FIXED** — the refusal keys are truthy-tested (fail closed), with a test |
| **SA MINOR-1** | the corrected run count did not propagate to two other lines | **FIXED** |
| **SA MINOR-2** | a paraphrase of OP-12 §11 sat inside quotation marks beside a verbatim one | **FIXED** — §4 quotes §11 verbatim and marks the summary as a summary |
| **SA MINOR-3** | §4 dropped §8's second BLOCKED category | **FIXED** — both categories are addressed |
| **SA MINOR-4 / NIT-1 / NIT-2** | "SCROLLBACK INCLUDED" contradicted U324 in the same file; M32's label claimed two stores while mutating one; an unguarded sink key could print `undefined (…)` | **FIXED** — all three |
| **GV NIT-2 / SA "M29 unreachable today"** | the new rule is defence-in-depth the current control flow already prevents reaching | **KEPT AND SAID SO** — the rule stands; the report no longer describes it as closing a live hole |

## 7. Verification on this host — real command output

| Check | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | **2208 passed, 1 skipped** — 390.67s before the reviews, 368.92s re-run on the tagged tree; the round-1 validator reproduced it independently (405.28s) and the round-2 validator again (385.84s) |
| `apps/desktop` → `npm test` | **820 pass, 0 fail** (813 before this unit's seven new tests, across both review rounds) |
| `terminal` → `node --test test/*.test.js` | **216 pass, 0 fail** |
| `py -3.12 tools/mutation/_op18e_live_acceptance_mutations.py` | **34/34 RED, every restore byte-identical** — M1–M28 plus **M29–M34** added from the two review rounds. M26 went **GREEN** on the first post-remediation run because the new M29 rule caught its leg; its test was narrowed rather than the row deleted, since a row that passes because a different guard fired has stopped measuring its own guard |
| `py -3.12 tools/mutation/_op18e_live_shape_mutations.py` | **11/11 RED** |
| `py -3.12 tools/manifest/compute_manifest.py --check` | **freeze check OK: no drift in FROZEN set** — the Phase-0 `freeze_integrity_sha256` and the operator signature intact |
| Live in-Electron runs across 18E | **8** — four in `.live.electron`, four here; all `ok:false`, all honest. `live_exchanges_spent: 0` is MEASURED on the four runs with surviving receipts (07:19, 07:26, 07:58, 08:25) and INFERRED for the four that were superseded before run-stamped names existed — inferred from the modal being present on every run that did leave a receipt, before and after them, and from a gated leg stopping before a prompt is drawn |
| D-LOOP-1 sweep after each close run | no `electron.exe`, `grok.exe` or `agy.exe` process on this host; durable ledger `leases: []`; `sessions_before === sessions_after === 0` |

`py -3.12` because the bare `python` on this host is 3.14 and cannot collect this suite. `ruff` is not
installed here, so CLAUDE.md's ruff-clean rule is **unverified** for this track's Python and pyflakes
stands in — recorded as U309, not glossed.

## 8. Scope and prohibitions

`docs/canonical/` untouched; no frozen schema edited (`--check` proves it); `tools/loop/run_loop.ps1`
untouched; `mcp_server/` carries no authorization logic and gained none. `config/live_operation.json`
is the operator's, gitignored, never written by this build — only read. Registers and evidence are
append-only; the `.live.electron` receipt was restored byte-identical rather than overwritten (the
validator hashed it against `d2bab98` and matched), and its miscount is corrected by a sibling file,
never by an edit.

**Credentials, stated exactly, and the statement got stronger between review rounds.** No credential
is **created, read, stored, transmitted or logged**. Round 1's version of this paragraph had to
disclose one read — the check captured whatever real value a credential name already held so it could
restore it afterwards (U321(d)) — and the round-2 spec-audit was right that §2.2 and OP-12 §13 forbid
**reading** one in the same breath as storing it. So the read is gone: a name the host already sets
is now **skipped** — never read, never overwritten with a placeholder — and the receipt reports the
planted and skipped lists **by name**, because the names are this build's own constants while the
values are the operator's. On the gate run: five planted, none skipped. Only planted sentinels are
scanned for, across the six sinks §3 lists. Both CLIs use their own host-native auth throughout, and
`agy` beginning its own sign-in writes to its own store, outside this repo and outside every sink
(§5.5). No push, no remote, no publication.

## 9. Verdict

`gate/phase-18e` — **PASSED**, on the evidence above and on §6.2's **round-2** verdicts (round 1 was
a FAIL and the gate does not rest on it), with every BLOCKING, MAJOR and MEDIUM from both rounds
fixed in-unit — each with a test and a mutation row — or recorded as a register row. **Two §17.2(1)
elements are recorded UNMET, not one:** the live exchange (U317) and the PTY-transcript sink (U324).
The tag certifies the governed path around them, not a model's reply. Closed by operator-delegation
(ruling 2026-07-16, register OP-1..OP-3), disposition **D-P18-13**. Per §17.1 no existing tag is
moved: `product/multi-frontier` stays where 18D put it and the successor tag
**`product/multi-frontier-v2`** is applied by the commit that carries this report.

**Not claimed, in the plainest words available, and the round-2 spec-audit was right that the first
version of this paragraph got it wrong in both directions:**

* **through the PANE path — the one this gate is about — no model of either provider has answered
  anything.** Both panes stop at the trust modal, every run, `providers_live: []`;
* **through the headless probe path, `google_antigravity` HAS answered this build**, once, in
  `.live.shape`: a real document with a recognised `response` key, accepted under the strict reader.
  Saying "no live Grok or Antigravity model ever has" would erase that measurement;
* **`grok_build` has never verifiably answered this build by any path.** Its headless `-p` run exits
  zero having said nothing (`text: ""`, `stopReason: "cancelled"`, U310), and the earlier recorded
  acceptance from the operator's own probe was **withdrawn** as unverifiable under the pre-U238
  reader (U311). Whether an interactive pane behaves differently cannot be known until the modal is
  cleared.

What **is** claimed, and measured eight times: both providers' panes open live, supervised, governed,
leased, badged, registered as Sovereign nodes on the operator's durable append-only log, verified
down to the binary and the model id, scrubbed of credential-bearing environment, scanned across the
six sinks this check can read, and torn down to zero — and they stop at a question only the operator
may answer.
