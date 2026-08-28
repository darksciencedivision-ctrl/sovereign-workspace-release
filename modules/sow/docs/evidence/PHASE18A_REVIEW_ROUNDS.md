# Phase 18A — review rounds, findings, and dispositions

**Status line, amended 2026-08-01 (round-4 spec-audit finding 1).** This paragraph originally read
"the durable record of **two** independent review rounds" and said the third round was the next
unit's first act. Four rounds have now run. The original sentence is corrected here rather than
left to mislead, and the rounds-1-and-2 sections below are untouched. The finding was that round
3's reviewer output survived only in a commit message and in summarised register rows — which is
exactly what this file exists to prevent (U226: reviewer findings are preserved, never reduced to
a number), and which would have made the §6 evidence report unwritable from the honest record.

This is the durable record of **four** independent review rounds run in-turn (D-LOOP-2: subagent
output dies with the turn that spawned it, so it is written down here or it is lost), plus the
disposition of every finding.

| Commit | What it is |
|---|---|
| `ea5f144` | OP-12 arming: directive §17, the operator's verbatim directive, the register row |
| `1caf464` | 18A work: reconnaissance engine + PowerShell runner + deterministic tests |
| `eebcdf7` | Round-1 remediation |
| `408cac2` | Round-2 remediation |
| `6baa3e2` | Round-3 remediation |
| (this unit) | Round-4 remediation + evidence report + gate |

## Round 1 — on `1caf464`

**gate-validator: PASS_WITH_RESERVATIONS.** Verified independently: recon-first with all ten
`--help` transcripts re-captured byte-identically; the PowerShell AST parse and parameter set;
exit-code-first classification (seven adversarial exit-0 payloads, plus a mutation proving the
tests go red); fail-closed states with the CLI absent; credential isolation against six injected
secrets; hermeticity re-proven under a plugin that raises on any provider spawn or socket
connect; the probe refusal (exit 3, nothing spent) with `claude_code`/`openai_codex_cli` as a
positive control; scope discipline and the 11/11 canonical freeze.

**spec-auditor: FINDINGS — 5 MAJOR, 8 MEDIUM, 7 MINOR. PROHIBITED DRIFT: NONE.**

The defects both rounds turned on, all fixed in `eebcdf7`:

| ID | Defect | Fix |
|---|---|---|
| F-1 | `provider_registration` accumulated prose reasons and derived the verdict by prefix-matching them, so two unreadable sources produced **REGISTERED** — a fail-open verdict claiming a lease no governor holds | booleans conjoined; unverifiable ⇒ NOT_REGISTERED |
| F-2 | `AVAILABLE` granted on unverified auth, and the runner's only launch gate | `state_caveat` + a derived boolean, both printed |
| F-3 | the probe relied on the ABSENCE of `--always-approve` and called that containment | `--permission-mode plan` / `--mode plan` pinned explicitly |
| F-4 | the guard omitted `acceptEdits`, `--allow`, `--allowedTools`, `--tools` | all added |
| F-5 | "no repository modification" via `git status --short`, which does not report the gitignored live switch | snapshot digests `config/live_operation.json`, and states what it does not cover |
| R5 | probe acceptance passed on a **prompt echo** (the prompt contains the token) | token sought only in the model's response, prompt subtracted |
| F-6 | exit codes documented but undeliverable: `Write-Error` terminates under `Stop`, and native stdout joins a function's return stream | `$script:ActionExit` + `Write-Failure` |
| F-7/F-10/F-11/F-13/F-14 | `probe_status` raised on whitespace-only output; the redactor mangled `--dangerously-skip-permissions` and `--xai-api-base-url` in its own evidence; `account_hint` would have recorded an email; the live-gate test used invented config keys and exercised nothing; grok prose parsed as model ids | each fixed, each with a test |

## Round 2 — on `eebcdf7`

Both reviewers confirmed the round-1 fixes were real (mutation-tested), and both found that the
remediation had introduced or left defects of its own. All of the following are fixed in
`408cac2`:

| ID | Defect | Fix |
|---|---|---|
| **N-1** (MAJOR) | the credential scrubber deleted `GROK_SANDBOX` — the env form of `grok --sandbox <PROFILE>`, the CLI's only filesystem/network containment lever — on the same path whose docstrings claimed containment | non-secret config pointers enumerated and preserved (`_PRESERVED_PROVIDER_CONFIG_KEYS`), as `codex.py` preserves `CODEX_HOME` |
| **N-7b** (blocking) | a FAILED install fell through to the PATH branch and told the operator it had installed and needed a new terminal, with exit 4 | `$installExit` checked; a failed install says so and exits 5 |
| **F1 / N-8** | the echo defence used exact-substring removal, so any re-wrap, re-case or re-space of an echoed prompt still ACCEPTED | both sides normalised before subtraction; degenerate prompts handled explicitly |
| **F2 / N-9** | `--flag=value` bypassed the forbidden-argument guard entirely | argv normalised to (name, value) pairs |
| **F3 / N-3** | the air-gap guard existed only in `probe_status`; `recon` (which produced the committed evidence) and `probe` (which spends money) bypassed it while the module claimed no CLI was contacted at all | one choke point (`_guarded_run`) every invocation passes through |
| **N-4** | the profile env var was described as an existing operator convention; it is not, and an unknown id read as "not air-gapped" | described as this tool's own switch; validated through the canonical `DeploymentProfile`; unknown ⇒ fails closed |
| **N-5** | `launch_ready: true` for a provider that is NOT_REGISTERED, holds no lease, and whose live legs are DENIED | renamed `auth_confirmed`, which is what it measures |
| **N-12 / F5** | the redactor destroyed `authorization required, run \`grok login\`` — the exact AUTH_REQUIRED diagnostic an auditor needs | header pattern now requires a separator and a long unbroken value |
| **N-13 / N-15** | the air-gap refusal rendered as a broken provider; a lone `Default model:` line became a one-entry inventory | caveat added; the default joins the inventory only when one was listed |
| **N-14** | interactive sign-in piped through `Out-Host`, which typically breaks TUI rendering | unpiped (safe now that the exit code no longer travels the pipeline) |
| **F4** | three regressions the `eebcdf7` message claimed were tested were not — deleting the caveat print, the auth print, or collapsing the engine-crash branch all left the suite green | tests added, the last behavioural via a stub engine |
| **F6** | the "hermetic" probe test read the operator's real gitignored live switch — it would have become a live subscription spend the day the operator extends it at 18C, which is a documented entry condition | pinned to a fixture config |

### Accepted with record (not defects to fix in 18A)

* **F-12 / F7 — `-Action login -Provider gemini` starts the vendor TUI unsupervised.** Operator
  directive §5.2 mandates exactly this (`agy` has no login subcommand). It is invariant-2 tension:
  for the duration of onboarding it is the vendor agent, not a Sovereign node. Disclosed in the
  console output and in-line. **It must not become the pattern for 18B panes** — those go through
  the existing supervised ConPTY + launch-ticket path (directive §9).
* **F-19 — the Antigravity installer is fetched and executed with no published checksum.** Quoted
  from operator directive §4.2, gated behind `-InstallMissing`, and now announced as
  unverified-integrity before it runs.
* **F-20** — `-Action login -Provider all` starts both flows in sequence; warned, not blocked
  (adding a confirmation would itself be an invented approval layer, I-30).
* **N-10** — the committed evidence contains the operator's OS account name inside the resolved
  executable path (`C:\Users\Sslaw\...`). Operator directive §6 *requires* reporting the resolved
  path, so the field stays; the inconsistency with `account_hint`'s identity-withholding is
  recorded rather than silently resolved either way. → **U231**
* **N-11** — receipt §3 shows the repeat-safe install short-circuit, not the `-InstallMissing`
  refusal branch (both CLIs are already installed on this host). The receipt now says so.
* **F-17** — `live_authorization._AUTHORIZED_PROVIDERS` is read via a private name; the
  `frozenset()` default fails closed on a rename. → **U230**
* **F-18 / N-7a** — provider facts are declared in the Python descriptor and re-keyed by literal
  id in the PowerShell `switch` blocks; the install path prints the descriptor's command and
  executes a hardcoded one. → **U232**
* **N-2 / question 1** — pinning `--permission-mode plan` is **not** containment in the
  invariant-29 sense; it is an argument the harness honours. The docstrings now say that, name
  what IS enforced (no widening flag can be emitted; changes are DETECTED afterwards), and record
  grok's `--sandbox <PROFILE>` as unused-because-unenumerated. OS-layer containment for provider
  children remains owed (U25).
* **F10 — `ruff` is not installed on this host**, so CLAUDE.md's "ruff-clean" bar is unverified
  (not failed) for these files; `pyflakes` is clean. Pre-existing, repo-wide.

## Round 3 — on `408cac2`

Both reviewers ran foreground, in-turn. **gate-validator: PASS_WITH_RESERVATIONS.** **spec-auditor:
FINDINGS; PROHIBITED DRIFT: NONE.** Remediation is `6baa3e2`.

**A gap in this record, stated rather than papered over.** Round 3's reviewer text was not
transcribed here when it ran — that is round-4 finding 1, and this section is written from what
survived: the `6baa3e2` commit message and the register rows U230, U234–U245, each of which names
its raiser. The **per-severity totals for round 3 are therefore not recoverable** and are not
invented here. What is recoverable is the reviewers' own numbering, which ran `MAJOR-1..3`,
`MEDIUM-4..9`(+), `MINOR-11..18`, `NIT-20..21` for the spec-auditor and `A-1..A-9` / `M-1..M-2`
for the gate-validator; every one of those IDs is accounted for below or in the register. Rounds 1,
2 and 4 were transcribed while their output was still in the turn, and are complete.

| ID | Defect | Disposition |
|---|---|---|
| **MAJOR-1 / A-1** | the auth parenthetical was printed unconditionally, so `auth confirmed : False` went out annotated *"the CLI itself reported a signed-in session"* — on the one provider whose auth is unverifiable offline, and it was already inside a committed receipt | gloss derived from `$Entry.auth_confirmed`, both branches behaviourally tested; the published receipt corrected by a sibling note, never rewritten (inv 12) |
| **MAJOR-2 / A-3** | the 18C entry condition printed to the operator was impossible: naming a new provider in `config/live_operation.json` **raises** and would deny every live provider, `claude_code` included | the real mechanism (register row + code-pinned scope extension in 18B + the operator's own switch edit) stated where the operator reads it; **U237**; directive §17 amended by appended clarification |
| **MAJOR-3 / A-9** | `Invoke-Expression` of a PowerShell installer sets no `$LASTEXITCODE`, so the round-2 failed-install guard read a stale 0 and announced an install that never happened, with exit 4 — on the one path that runs unchecksummed remote code | failures exit 5; a throwing fetch exits 5 instead of an undocumented 1; an install nothing can verify says so under its own code 7 |
| **MEDIUM-4** | three widening flags the capture documents (`--no-plan`, `--plugin-dir`, `--agents`) were missing from the guard whose comment claimed all of them | added; comment re-checked against the capture |
| **MEDIUM-5 / M-1** | both install assertions were greps — the guard could be deleted with the literals left behind and the suite stayed green | behavioural: `npm` and `Invoke-RestMethod` shadowed in the calling scope, so the vendor commands are named and never run; all four mutations that used to pass go red |
| **MEDIUM-6** | the probe child is a bare `subprocess.run` holding no node identity and no I-X3 lease, and the docstring framed that as a virtue | reframed as the gap it is; **U234**, owed *before* the first live probe |
| **MEDIUM-8 / MEDIUM-9** | `-Action status` makes authenticated vendor calls outside the live gate; the two accepted invariant-2 tensions had no durable fence beyond a document | **U236**, **U241** |
| **MINOR-11 / A-2** | `grok login` recorded as "hidden from the Commands list" — the same file's capture lists it | `RECORDED_FLAG_DELTAS` corrected in code at `6baa3e2`; the *committed capture* was missed and is corrected at round 4 (finding 2) |
| **MINOR-12 / NIT-20** | U231 undercounted the operator's OS account name in tracked evidence (four occurrences; it is at least ten) | **U242** — a correction row, U231's disposition unchanged |
| **MINOR-13** | the recorded credential policy was the named half only: no prefixes, no substrings, and no PRESERVE list — and the preserve list is the whole substance of N-1 | `build_report` emits all four, pinned by `test_the_recorded_credential_policy_is_the_whole_policy`; the *committed capture* corrected at round 4 (finding 5) |
| **MINOR-14** | `Get-Content.*token` sat in a substring list where it could never match — an unfalsifiable prohibition test | real regex, own test |
| **MINOR-15 / MINOR-17** | launch exports two env vars nothing reads; the runner accepts any Python 3 while the engine needs ≥3.10 | **U243** |
| **MINOR-16 / M-2** | false-as-written claims: `grok login` "hidden"; `plan` presented as a documented ranking; `--mode plan` called containment; the module called diagnostic-only after the probe path landed; the recorded credential policy silent on its own exception | each retired in code; the module docstring now records *why* "diagnostic only" stopped being true (the `--help` string was missed — round-4 finding 3) |
| **MINOR-18** | `SOVEREIGN_DEPLOYMENT_PROFILE` is a tool-local switch wearing a workspace-wide name, defaulting open | **U244** (watch-item; value validated through the canonical `DeploymentProfile`, unknown ⇒ fails closed) |
| **NIT-21** | `_assert_no_forbidden` raises a `ValueError` (traceback, exit 6) on an operator-supplied value where a governed refusal is right | **U245** |
| **A-4..A-8** | probe-acceptance holes (whitespace-deletion echoes; `extract_probe_text` falling back to the whole JSON document); the generic substring net over-scrubbing non-secrets; an air-gapped refusal rendering as a broken provider; `_AUTHORIZED_PROVIDERS` read through a private name | **U238**, **U239**, **U240**, **U230** — all owed before or at 18C, which is where they would first decide a live verdict |

## Round 4 — on `6baa3e2`

Both reviewers ran foreground, in-turn, on the tagged-candidate tree. **gate-validator:
PASS_WITH_RESERVATIONS** — "the §17 18A exit criteria are MET for everything that is a property of
the tree", 9 findings (2 MEDIUM, 7 MINOR), none blocking. **spec-auditor: FINDINGS — 3 MAJOR,
7 MEDIUM, 5 MINOR; PROHIBITED DRIFT: NONE**, with findings 1–6 named must-fix-before-tag.

What the validator re-proved independently, by mutation and by tripwire (its own runs, not the
builder's claims): the auth gloss goes red both ways; `Invoke-Expression` really does leave
`$LASTEXITCODE` stale (`42` survived a vendor-installer body); all six documented install exit
codes are *deliverable*, four of them re-observed by hand; four install-guard mutations go red and
restore byte-identically; the widening-flag and `=`-bypass guards go red when broken (3 and 4
tests respectively); `_guarded_run` is on every provider-invocation path; six injected secrets and
an identity sweep over the 18A artifacts come back clean; and the **whole default suite runs with
`grok.cmd`/`agy.cmd` tripwires on `PATH` without either firing** — 1681 passed, 1 skipped, tripwire
`False`, with an audit hook confirming the real gitignored `config/live_operation.json` is opened
**0 times**. Scope: `git diff --name-status ea5f144..6baa3e2` is twelve files, `run_loop.ps1`
untouched, no schema edit, all four canonical SHA-256 prefixes intact, `git tag --contains
ea5f144` empty.

**Fixed in this unit (spec-audit findings 1–6, the must-fix set):**

| ID | Defect | Fix |
|---|---|---|
| **1 (MAJOR)** | this document claimed two rounds, stopped its commit table at `408cac2`, and listed round 3 as future work — so round 3's reviewer output survived only as a commit message and summarised rows, the exact loss this file exists to prevent (U226) | the round-3 and round-4 sections above and below, the amended status line, the extended commit table |
| **2 (MAJOR)** | `phase18a_host_recon.json:139` still says `grok login` is "hidden from the Commands list" while `:209` of the *same file* lists `login  Sign in to Grok`; round 3 fixed the code and never the artifact, and the capture is what operator directive §2 makes authoritative | sibling `docs/evidence/live/phase18a_host_recon_CORRECTION.md` quoting both lines; the capture is **not** edited (inv 12) |
| **3 (MAJOR)** | `--help` still described the tool as "(Phase 18A, diagnostic only)" while `--action probe` executes a live, billable, unsupervised call — on the one surface an operator reads *before* running it (inv 1) | description rewritten to name the probe's live call and U234; `test_the_cli_help_does_not_call_a_billable_tool_diagnostic_only` goes red on the old string |
| **4 (MEDIUM)** | the runner's header presented "supervises nothing, holds no lease" as compliance, on the operator's primary surface — false for `-Action probe` and `-Action login`, and U234's own honesty fix had reached the Python and not the PowerShell | header states the gap, names U234/U241, and states that neither may become the 18B pane pattern |
| **5 (MEDIUM)** | the committed capture records the pre-round-3 credential policy (nine keys, no prefixes/substrings/preserve-list) — the fix landed in the producer and never in the product it was about | covered by the same sibling correction note, including the round-4 rename below |
| **6 (MEDIUM)** | the invariant-12 correction note said every other line of the superseded receipt was "unchanged in substance"; two enumerated items had changed — the probe refusal (a **reversal** of a wrong instruction, U237) and the install caveat (round-2's N-11 disclosure **dropped** by the R3 receipt) | "APPENDED 2026-08-01" section on the correction note; the N-11 caveat restored there rather than by editing the published R3 receipt |

**Also fixed, though the reviewers rated them carry-able** — each is one line of policy in the
fail-closed direction, each with a test that goes red without it:

* **gate-validator finding 1 (MEDIUM)** — `tests/live_call_guard.py::LIVE_PROVIDER_CLIS` knew only
  `claude` and `codex`. 18A added a real spawn seam for `grok`/`agy`; the validator proved by
  tripwire that nothing reaches it *today*, which makes this the right moment to add the defence
  rather than the wrong one. Both names added.
* **spec-audit finding 9 (MEDIUM)** — `reads_credentials: false` was a constant asserted against
  itself, and the runner printed "No credential was read, printed, or stored **by this run**" from
  a code path that produces no such observation: the round-3 auth-gloss shape, one surface over.
  The field is now `reads_credentials_by_design` plus a `claim_basis` naming the tests that
  enforce it, and the test asserts **those tests exist** — rename or delete either and it goes red.
  The runner's line now says the isolation is structural and names what enforces it.
* **gate-validator finding 3 (MINOR)** — exit 5 was documented as "provider not available" only,
  while the round-3 fix also emits it for a failed install. The `.NOTES` table says both now.
* **spec-audit finding 14 (MINOR)** — the header's "two decisions are genuinely this script's own"
  was a closed enumeration that did not check out; it now lists five and says why it grew.

**Recorded and carried, with a register row each (not fixed in 18A):** cross-vendor model
inventory under the Antigravity subscription → **U246**; unguarded `& npm` yielding an
undocumented exit 1 on a Node-less host → **U247**; `Invoke-LoginAction`'s missing `default`
(unreachable behind the `ValidateSet`) → **U248**; single-dash flag spellings passing
`_assert_no_forbidden` on a Go-`flag` CLI → **U249**; the widening-denylist residue and the
endpoint-override asymmetry between argv and env policy (also gate-validator finding 2) →
**U250**; `probe_status` calling `models` after judging the version unsupported → **U251**; the
three install-path fences no test can falsify — exit 4 untested, the `$LASTEXITCODE` reset
unfalsifiable, two unreachable `_guarded_run` sites (gate-validator findings 4/5/6) → **U252**;
`ruff` absent on this host so the ruff-clean bar is unverified rather than met → **U253**.

**The reviewers' own reservations, carried verbatim in substance:** the validator accepts finding 1
as non-blocking *only* because the tripwire proved nothing reaches those CLIs today, and requires
it closed before 18B lands an adapter spawn seam (done here); it holds that if 18C opens the live
switch before the probe child is routed through the supervised launch-ticket path, **that is a gate
failure at 18C** (U234); and it holds that U238's two probe-acceptance holes may be deferred to the
track that spends the call but **not carried past 18C's gate**. The auditor's audit-scope caveat —
that it read the working tree and the gate must name a committed, clean hash — is discharged by the
work commit this report cites.

## What remains before `gate/phase-18a` can be tagged

Nothing that is a property of the tree. The closing acts, in order: this document (done), the
§6 evidence report, the DECISION_REGISTER gate row, and the tag.
