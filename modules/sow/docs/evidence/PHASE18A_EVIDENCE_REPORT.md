# PHASE 18A — EVIDENCE REPORT (whole-track close)

**Work unit:** `phase-18a.close` (the closing act of the 18A track: round-4 reviews, remediation,
this report, the register row, the tag).
**Date:** 2026-08-01 · **Iteration:** 105 · **Status:** PASS.
**Work commit:** `82df796` (round-4 remediation). Prior 18A commits: `ea5f144` (OP-12 arming),
`1caf464` (the track's work), `eebcdf7` (round 1), `408cac2` (round 2), `6baa3e2` (round 3),
`d289114` (the iteration-104 work-in-progress checkpoint).
**Tag:** `gate/phase-18a` lands with this unit.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§17 track 18A** (register **OP-12**) and
the operator's verbatim directive `docs/operator/OP12_PROVIDER_DIRECTIVE_GROK_ANTIGRAVITY.md`
(**§3–§7, §15, §16, §18** bind this track), loop protocol §3, substitution §6, prohibitions §2,
**D-LOOP-1** (nothing spawned in a unit outlives it), **D-LOOP-2** (print-mode: every suite and
every review run foreground, in-turn).
Load-bearing invariants: **1** (operator holds final authority — no self-authorization), **2**
(every terminal a Sovereign node), **11/12** (provenance; append-only — published evidence is
corrected by a sibling, never rewritten), **16** (a failed artifact cannot advance), **19/20**
(locality, air-gap honesty), **21** (one frontier terminal per subscription — **allowance 1 each**
for the two new resources, never merged), **27** (observable), **29** (containment at the
OS/process layer, never trusted to the harness), **30** (no invented governance layers).

---

## 1. What 18A delivered

Reconnaissance first, then a runner built only on what the reconnaissance found.

| Artifact | What it is |
|---|---|
| `docs/evidence/live/phase18a_host_recon.json` | The verbatim capture of the **installed** command surface: `grok --version/--help/models/agent --help/login --help/models --help` and `agy --version/--help/models/models --help`, ten calls, all exit 0. Operator directive §2 makes this the authority for every flag decision in the phase — no flag in this track comes from memory. |
| `tools/providers/frontier_provider_recon.py` | The classification engine: discovery, version, **exit-code-first** outcome classification, auth classification, model enumeration, probe-argv construction, probe acceptance, credential scrub, registration/lease reporting, the live-authorization gate, and the report `build_report()` that every surface renders. |
| `tools/providers/run_frontier_providers.ps1` | The operator's one command surface: `status` / `install` / `login` / `probe` / `launch`, per operator directive §3–§7. A thin, testable shell over the engine so status semantics cannot drift between the two. |
| `tests/unit/test_frontier_provider_recon.py`, `tests/unit/test_run_frontier_providers_ps1.py` | 198 deterministic tests + 1 opt-in host-coupled skip, including a real PowerShell AST parse and parameter-set validation. |
| `docs/evidence/receipts/PHASE18A_RUNNER_STATUS*.txt/.md` | The runner's own output on this host, plus the two invariant-12 correction notes. |
| `docs/evidence/PHASE18A_REVIEW_ROUNDS.md` | The durable record of all four review rounds and the disposition of every finding (D-LOOP-2: subagent output dies with its turn). |

**What the host actually has** (recorded fact, not assumption): `grok` **0.2.118** at
`…\npm\grok.CMD`, logged in (`You are logged in with grok.com`), offering `grok-4.5`; `agy`
**1.1.9** at `…\agy\bin\agy.EXE`, offering 11 models, authentication **UNVERIFIABLE offline** —
that CLI has no `login`, no `auth`, and no status subcommand, so the engine reports `UNVERIFIED`
with a printed caveat and `auth_confirmed: false`, and stays there until a live probe says
otherwise (**U228**).

## 2. Exit criteria (directive §17, 18A row) — self-check with real command output

Every command below was run on this Windows host, foreground, in-turn. The **independent**
column is the round-4 `gate-validator`'s own re-verification, which it performed by mutation
testing and PATH tripwire rather than by reading the builder's claims.

| # | Criterion | Verdict | Evidence | Independent |
|---|---|---|---|---|
| 1 | Reconnaissance FIRST; the installed `--help` surface is AUTHORITATIVE; no flags from memory | **MET** | 10 captures in `phase18a_host_recon.json`, all exit 0; every flag the probe emits traces to a captured line; 7 deltas between the operator directive's assumed surface and the installed one recorded in `RECORDED_FLAG_DELTAS` (incl. `--no-auto-update` absent on this build) | validator re-captured all ten byte-identically (round 1) and re-checked every emitted flag against the capture (round 4) |
| 2 | A CLI not installed / not logged in is a **recorded fact, not a failure** | **MET** | `NOT_INSTALLED` state; `"executable not found on PATH — recorded fact, not a failure"`; `UNVERIFIED` auth with a caveat rather than a failure verdict | validator ran the fail-closed states with the CLI absent |
| 3 | Runner per §3–§7/§15/§18: status / install / login / probe / launch | **MET** | all five actions; `-Provider openai` and `-Action uninstall` rejected at parameter binding | validator parsed the script with PowerShell's own AST parser and asserted the parameter sets |
| 4 | Fail-closed status states | **MET** | closed `PROVIDER_STATES` set; unparseable version ⇒ `UNSUPPORTED_VERSION`; unreadable registration source ⇒ `NOT_REGISTERED`; empty inventory ⇒ empty list **with a reason**; unknown deployment profile ⇒ air-gapped | validator: "unverifiable ⇒ NOT_REGISTERED" re-proved after the round-1 fail-open fix |
| 5 | **Exit-code-first** classification; an exit-0 transcript containing historical error words is NEVER reclassified | **MET** | `classify_provider_outcome`; parametrised adversarial exit-0 payloads (login history, quota history, the word "error" in help text); demotion possible only through a real structured `error` field | validator ran seven adversarial exit-0 payloads plus a mutation proving the tests go red |
| 6 | Installs only under explicit `-InstallMissing` | **MET** | exit 2 with nothing installed; behavioural test with `npm` shadowed in the calling scope | validator mutated `if (-not $Authorized)` → `if ($false)`: goes red |
| 7 | **No secret read, printed, or stored, ever** | **MET** | `is_provider_credential_env_key` / `scrub_provider_env` (9 exact keys + 5 prefixes + 8 substrings incl. `XAI_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_API_KEY`); non-secret config pointers **preserved** (`GROK_SANDBOX` — the grok CLI's only containment lever); no credential store is opened anywhere | validator swept all 18A artifacts for `xai-…`/`sk-…`/`AIza…`/`ya29.…`/JWT shapes and for the operator's identity: only synthetic fixtures inside the test file; **no identity matches** |
| 8 | Repeat-safe; never starts this loop | **MET** | `-Action install` twice installs nothing the second time; `-Action status` mutates nothing; prohibition tests over comment-stripped source for `LOOP_STATE`, `run_loop.ps1`, and every git verb | validator: `tools/loop/run_loop.ps1` last touched by `f2e91f7`, pre-18A |
| 9 | Deterministic tests per §16 | **MET for 18A's half** | 198 passed / 1 opt-in skip; no network in the default suite | validator ran the **whole** suite with `grok.cmd`/`agy.cmd` tripwires on `PATH`: **1681 passed, 1 skipped, tripwire never fired**; an audit hook confirmed the real gitignored `config/live_operation.json` is opened **0 times** |
| 10 | No parallel registry, no second control plane, canonical set frozen | **MET** | `git diff --name-status ea5f144..6baa3e2` = 12 files, all inside `tools/providers/`, `tests/`, `docs/`; `provider_registration` **reads** the existing `live_authorization` scope and the frozen `node.schema.json` and reports `NOT_REGISTERED` rather than inventing a home | validator: all four canonical SHA-256 prefixes intact (`CC414372`, `8C9B7240`, `668089B5`, `6D3FD03B`); manifest regenerated, diffed (ordering + timestamp only, every per-file hash unchanged), reverted, nothing committed |
| 11 | I-X3: two NEW subscription resources, **allowance 1 each, never merged** | **MET as far as 18A can enforce it** | `grok_build_subscription` / `google_antigravity_subscription`, allowance 1, asserted unconditionally; the same line honestly prints `lease not_registered` — enforcement is 18B's, and **U233** owns it | validator concurs; recorded as an owned reservation, not a pass |

**Suites, this turn, foreground:** Python **1682 passed / 1 skipped** (`py -3.12 -m pytest tests/
-q`, 352.93 s); desktop Node **640 passed / 0 failed**; terminal Node **212 passed / 0 failed**.
`pyflakes` clean over the changed Python. (The bare `python` on this host is 3.14 and cannot
collect the suite — `jsonschema` is installed under `py -3.12`. Noted so the number is
reproducible.)

## 3. Reviews — four independent rounds, all foreground, all in-turn

Full findings and dispositions: `docs/evidence/PHASE18A_REVIEW_ROUNDS.md`.

| Round | On | gate-validator | spec-auditor | Remediation |
|---|---|---|---|---|
| 1 | `1caf464` | PASS_WITH_RESERVATIONS | 5 MAJOR / 8 MEDIUM / 7 MINOR · **PROHIBITED DRIFT: NONE** | `eebcdf7` |
| 2 | `eebcdf7` | PASS_WITH_RESERVATIONS | 1 MAJOR / 7 MEDIUM / 7 MINOR · **NONE** | `408cac2` |
| 3 | `408cac2` | PASS_WITH_RESERVATIONS | findings `MAJOR-1..3`, `MEDIUM-4..9`(+), `MINOR-11..18`, `NIT-20..21` · **NONE** — per-severity totals **not recoverable**: the round-3 text was never transcribed, which is itself round-4 finding 1; every ID is accounted for in the register (U230, U234–U245) | `6baa3e2` |
| 4 | `6baa3e2` | PASS_WITH_RESERVATIONS — "the §17 18A exit criteria are MET for everything that is a property of the tree" | 3 MAJOR / 7 MEDIUM / 5 MINOR · **NONE** | `82df796` (this unit) |

**Why four rounds and not one.** Each round's PASS was conditioned on fixes the reviewers had not
yet seen, and each round found that the *remediation* had introduced or left defects of its own —
including, twice, a fix that reached the code and stopped short of the committed artifact the
finding was about. The gate did not close until a round's must-fix list was discharged and its
verdict rested on the tree as it stands. Every fix in every round has a test that goes red when
the guard is removed; the round-4 validator re-verified this class by mutation (four install-guard
mutations, three widening-flag mutations, four `=`-bypass mutations, two air-gap choke-point
mutations), restoring each file byte-identically and proving it with `git status`.

**Round-4 must-fix items, all discharged in `82df796` and this report's companion documents:**
the durable review record now carries rounds 3 and 4 (it had claimed two); the committed
reconnaissance capture's two stale/false statements are corrected by a **sibling** note
(`phase18a_host_recon_CORRECTION.md`) and not by editing the capture; `--help` no longer calls a
billable tool "diagnostic only"; the runner's header states the supervision gap instead of selling
it as compliance; and the runner-status correction note's "unchanged in substance" over-claim is
corrected by an appended section that also restores the round-2 install caveat the R3 receipt had
dropped.

## 4. Substitutions and limitations (directive §6 — none silently skipped)

| Item | Why | What was done instead |
|---|---|---|
| **No live provider call was made.** | Prohibition §2.4 as amended by OP-12: live legs belong to **18C**, whose entry conditions (operator CLI logins + the operator's own edit to the never-committed live switch + the code-pinned scope extension owed in 18B) are not met. | The probe path is **exercised** and **refused**: `-Action probe` returns exit 3 with a named reason and spends nothing, with `claude_code`/`openai_codex_cli` used as a positive control to prove the gate is a real gate and not a stub. This is the fail-closed switch working as designed, not a skipped criterion. |
| **`agy` authentication is UNVERIFIED, not confirmed.** | That CLI has no offline auth surface at all — verified against its own captured `--help`. | Reported as `UNVERIFIED` with a printed caveat and `auth_confirmed: false`; **never** inferred from the executable existing. **U228** owns it until the 18C probe. |
| **`-Action install -InstallMissing` and `-Action login` were not run.** | Both CLIs are already installed (so install short-circuits, repeat-safe), and `login` opens a browser/vendor TUI — an interactive flow the loop must not start on the operator's behalf. | The four install branches (refusal, failure, unverifiable, PATH-refresh) are covered deterministically with `npm` and `Invoke-RestMethod` **shadowed in the calling scope**, so the vendor commands are named and never run; the round-4 validator re-observed four of the six exit codes by hand. The receipt says exactly which branch it demonstrates (**restored caveat**, see the correction note), and **U252** records that exit 4 still has no positive test. |
| **The Antigravity installer has no published checksum.** | Quoted from operator directive §4.2; §10.2 requires integrity verification "where published", and none is. | Gated behind `-InstallMissing`, and announced as **unverified integrity** before it runs. Accepted-with-record (round-1 F-19). |
| **`-Action login -Provider gemini` starts the vendor TUI unsupervised.** | Operator directive §5.2 mandates exactly this; `agy` has no login subcommand. | Invariant-2 tension, disclosed in the console, in the script header, and fenced by **U241**: it must not become the pattern for 18B panes, which go through the existing supervised ConPTY + launch-ticket path. |
| **The probe child holds no node identity and no I-X3 lease.** | 18A's engine is a bootstrap surface, not the node runtime. | Recorded as the gap it is (**U234**), owed **before the first live probe**. The round-4 validator states that if 18C opens the switch before this is routed through the supervised launch-ticket path, **that is a gate failure at 18C**. |
| **`ruff` is not installed on this host.** | Pre-existing, repo-wide. | CLAUDE.md's ruff-clean bar is **unverified, not met and not failed**, for these files; `pyflakes` is clean. **U253**. |
| **The reconnaissance capture was not regenerated.** | A regeneration would re-run authenticated vendor calls (`grok models`, `agy models` — U236) to fix two sentences already fixed in the code that produces them. | Corrected by sibling note; the capture's provider facts were verified byte-identically by the round-1 and round-4 validators. Stated explicitly in the note. |

## 5. Delegated decisions closed by this gate

Per directive §1 (operator ruling 2026-07-16), formerly interactive closures are decided by
delegation on recorded evidence. 18A closes none that were open — OP-12 itself is the operator's
own ruling, recorded at `ea5f144`. What 18A **records** for the operator rather than deciding:
the **U237** correction (the printed 18C entry condition was impossible as written, because
`_AUTHORIZED_PROVIDERS` is code-pinned and raises on an unknown id — so naming a new provider in
`config/live_operation.json` would deny *every* live provider, `claude_code` included). The
direction of failure is safe and invariant 1 is upheld: **a config file cannot widen a code-pinned
scope.** The real 18C entry condition is the operator's OP-12 authorization (recorded) **plus** the
scope extension owed in 18B **plus** the operator's own edit to the never-committed switch. The
original ruling text is not rewritten; the clarification is appended to directive §17.

## 6. Open items carried out of 18A

Owned by **18B**: U227 (the frozen `node.schema.json` adapter enum has no member for either
provider — operator-reserved, and it **blocks 18B's design**), U230, U232, U233, U234, U235, U236,
U238, U239, U240, U241, U243, U244, U245, U246, U247, U248, U249, U250, U251, U252.
Owned by **post-18**: U231 + U242 (identity in resolved paths, required by operator directive §6),
U253 (ruff).

**Not done, and not claimed:** no adapter, no registry entry, no picker option, no governor lease,
no UI label, no live call. Those are 18B and 18C. `gate/phase-18a` certifies reconnaissance, the
runner, and their tests — nothing further.

## 7. Verdict

**PASS.** The §17 18A exit criteria are met on the committed tree; the round-4 gate-validator
confirms them independently and its reservations are either fixed in `82df796` or carried with a
register row; the spec-auditor reports **PROHIBITED DRIFT: NONE** across all four rounds; the full
suites are green; no live call was made and none was needed.

`gate/phase-18a` is tagged on the evidence commit that carries this report.
