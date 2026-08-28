# Phase 18B `.adapter` — sub-step record and review rounds

**Status: the sub-step is DONE. The 18B GATE IS NOT CLOSED and `gate/phase-18b` does not exist.**
Two sub-steps remain (`.picker`, `.close`). This file exists because subagent output does not
survive a print-mode turn (D-LOOP-2): the findings below were produced in-turn, in the foreground,
and would otherwise live only in a commit message.

| | |
|---|---|
| Work unit | `phase-18b.adapter` (directive §3 — a named sub-step of a large phase) |
| Authorization | OP-12 (operator, 2026-07-31), directive §17; operator directive §§2, 8, 10, 11, 12, 13, 16 |
| Work commit | `8675d97` |
| Remediation commit | (this unit's second commit — see `docs/loop/LOOP_STATE.json`) |
| Live calls | **none.** Nothing was spawned; nothing outlived the unit (D-LOOP-1). |

## What was built

Two headless reasoning workers behind the EXISTING frontier contract — the shared
`ModelWorkerAdapter` (scoped context in over MCP → node-local gate → CANDIDATE out with
provenance). The backend is the only new surface; no parallel registry, no second control path.

* `adapters/frontier/provider_cli_common.py` — one trust/emission policy for both providers:
  credential scrub, argv guard, exit-code-first classifier, model-list parsers, response
  accessors, and the backend base.
* `adapters/frontier/grok_build.py`, `adapters/frontier/antigravity.py` — the per-CLI specifics.
* `tools/providers/frontier_provider_recon.py` — rewired to IMPORT that policy and re-export it
  under the names it has published since 18A. `is`-identity is pinned by test.

## Decisions taken, with warrants (not omissions)

| Decision | Warrant | Row |
|---|---|---|
| Reasoning role only; `role="coding"` raises | a coding role needs an auto-approving mode (§11 forbids) or an undocumented sandbox profile (fabrication). §11's own "initial provider behavior" IS the reasoning role. | U260 |
| `--sandbox` not emitted on either CLI | neither help says what it restricts; an unverified containment claim is worse than none | U261 |
| `grok agent stdio` (ACP) not used | §10 permits it only if a fitting transport already exists here; none does | U262 |
| `--cwd`/`--add-dir` not banned | they bind a workspace and this build emits them | U250 |
| `--project` not banned | different warrant — a session selector nothing emits, not a workspace bind | U266 |
| four refused flags absent from the capture, kept | supersets in the fail-closed direction; now DECLARED and test-checked | U263 |

## Owed items closed

**U235** (instruction-injection flags out of the permission guard — decision preserved verbatim,
owed guard built and fenced), **U249** (dash-normalised comparison), **U250** (endpoint /
identity / auth-initiating / state-creating flags refused; the env and argv policies now agree).

## Review rounds — BOTH REVIEWERS, FOREGROUND, IN-TURN, ON `8675d97`

### gate-validator — **FAIL** (before remediation)

Proved BY MUTATION (its own words: it re-proved the tree rather than reading claims): U249
dash-normalisation red; exit-code-first not weakened by the move (red in both suites); inventory
refusal red; env scrub red; **but the two `_guard` calls SURVIVED deletion with 1803 tests green**,
and the recon report's `credential_policy()` splat was shadowed (a sentinel in the shared function
left the report unchanged). Verified by execution: full suite 1811/1 skipped, desktop 640, terminal
212, freeze OK, standalone script works, air-gap refusal holds on all three paths, `NodeRegistry`
refuses both ids, `gate/phase-18b` absent, only the five declared files touched.

1. **BLOCKING** — U259/U260/U261 cited in five places; the register ended at U258. *A residue
   recorded only in the docstring that says it is recorded is an invisible gap wearing a record's
   number.*
2. **MAJOR** — `_guard` unfenced on both adapters; "the adapters call both" was a claim, not a
   property. With the permission guard removed, a forbidden flag smuggled as a model slug or a
   workdir reached argv. The `test_frontier_claude_code.py` precedent existed and was not followed.
3. **MAJOR** — the §2 authority sentence ("every flag named below was read off the capture") is
   falsified by four entries in the list it introduces.
4. **MEDIUM** — shadowed literals below the `**credential_policy()` splat made the splat dead.
5. **MEDIUM** — subscription refs and version floors re-spelled as literals two lines after citing
   U254 against exactly that.
6. **MEDIUM** — "they live here, once" over-claims: `probe_provider_cli` duplicates the tool's
   probe orchestration and has no product consumer.
7. **MEDIUM** — `--project`'s recorded warrant misdescribes the flag.
8. **MINOR** — U249 made the 18A `--prompt` surface refuse benign prompts (`agents`, `tools`).
9. **MINOR** — "applied to EVERY CLI transcript" is false of the success path; a missing executable
   becomes an auth pause.
10. **MINOR** — grok's `streaming-json` deviation recorded asymmetrically with antigravity's.

### spec-auditor — **PROHIBITED DRIFT: NONE**; 4 MAJOR / 6 MEDIUM / 8 MINOR / 2 NIT

Stated plainly which invariants are NOT violated: I-1/I-2/I-C1 (no new path to a provider CLI
without the supervisor; the U227 fence intact and not routed around), I-3/I-4/I-5, I-10/I-11
(CANDIDATE only), I-12/I-16, I-6/I-7, I-13, I-20, I-21/I-22/I-X3 (two subscriptions, separate, at
allowance 1), §13 in substance (no leak), §11 in substance, §6, §8, I-SC1, the Decimal rule.

* **M-1** — the same missing-register-rows defect (found independently).
* **M-2** — "no endpoint override can redirect a call through the environment … the only one left"
  is a universal negative the code cannot keep: `HTTP_PROXY`/`HTTPS_PROXY`, `NODE_OPTIONS` and
  `NODE_EXTRA_CA_CERTS` survive the scrub, and `grok` is an npm-installed Node CLI.
* **M-3** — the T2 pinning claim is falsified three paragraphs earlier by the module's own
  `--leader` note: leader mode defaults from `config.toml` and `--no-leader` does not exist on the
  `grok -p` surface the adapter uses.
* **M-4** — "OS/process-layer containment is unbuilt" is contradicted by `process_tree.py` in the
  same package, and the new backend picked the weaker spawn while asserting the capability does not
  exist.
* **Md-1..Md-6** — the §2 four; the four undocumented keys lifted over a fail-closed classifier by
  an analogy that does not hold; `--project`'s warrant; the subscription literal; "reachable only
  from a governed live path" is a sentence, not a fence; `reads_credentials_by_design` re-created as
  a constant asserted against itself one layer down.

## What was fixed in-unit, and what is proved

Every BLOCKING and MAJOR finding, and every MEDIUM, is fixed. The fixes that are mechanisms rather
than sentences were **proved by mutation this turn** (`docs/loop/.mut.py`, six mutations, all
CAUGHT, restore byte-identical):

| Mutation | Result |
|---|---|
| permission guard dropped from `_guard` | CAUGHT |
| instruction guard dropped from `_guard` | CAUGHT |
| live-spawn fence disarmed (`_LIVE_SPAWN_PATH_WIRED`) | CAUGHT |
| dash normalisation removed (U249) | CAUGHT |
| preserve-allowlist widened again (U265) | CAUGHT |
| node-injection vars un-scrubbed (U264) | CAUGHT |

Also landed: the §2 claim narrowed with `CAPTURE_ABSENT_SUPERSET_ARGS` **and a test that reads the
capture** so a remembered flag goes red; the dead literals deleted so the splat is live; the probe
builders reordered to guard flags then append the prompt; `run_managed_process` gained an optional
`cwd` (additive, default `None` ⇒ every existing caller byte-identical) so the backends get the
job-object boundary **and** workspace containment instead of choosing; `ProviderNotSpawnable` so a
missing executable does not read as a login problem (§14); `--no-memory` pinned because
cross-session memory is a blanket-context vector (invariants 8/9); subscription refs taken from
`canonical_subscription_ref`; version floors and pinned modes pinned equal to the 18A tool's.

## Honest limits of this sub-step

* No picker option, no launch ticket, no ConPTY pane, no governor lease, no live call.
* **No Sovereign node can be registered for either provider** — node@1.0's adapter enum has no
  member and the amendment is operator-reserved (U227). `gate/phase-18b` must NOT close on "U227 is
  answered"; the operator owns it.
* `generate` refuses outright (U268) until the supervised launch path exists.
* Two probe orchestrations remain (U269); leader mode remains unpinnable from this surface (U267);
  a host proxy remains an environment route this build does not close (U264).

## Suites, this turn, foreground

`py -3.12 -m pytest tests/` → **1821 passed / 1 skipped** (the bare `python` on this host is 3.14
and cannot collect the suite) · `apps/desktop` node → **640** · `node --test terminal/test/*.test.js`
→ **212** · pyflakes clean on every changed file · `compute_manifest.py --check` → freeze check OK,
no drift in the FROZEN set.

---

## Correction appended at the 18B close (2026-08-01) — never rewritten above (invariant 12)

**The remediation commit row was left unresolved.** Line 13 of this checkpoint reads
`| Remediation commit | (this unit's second commit — see docs/loop/LOOP_STATE.json) |`. It is
**`909ab91`**. This is the same defect the `.picker` review round 1 graded and fixed in its own
checkpoint (MINOR-5 / Mn-4); the sibling document was not swept with it. A checkpoint that cannot
name the tree it describes is a checkpoint about nothing, which is why it is worth a line.

Raised by: 18B `.close` gate-validator MINOR-1.
