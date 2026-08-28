# SOVEREIGN WORKSPACE — CANONICAL HANDOFF

**Document ID:** SOVEREIGN-HANDOFF-20260827
**Prepared:** 2026-08-27 (UTC)
**Prepared by:** Reviewer role (validation/audit), on operator instruction
**Operator / final authority:** Samuel Lawson (`Darksciencedivision@gmail.com`)
**Audited root:** `D:\Product Software`
**Primary work tree:** `D:\Product Software\Production Workspace`
**Intended recipients:** Any model or engineer resuming this work in a new session
**Disposition:** CONTROLLED DEVELOPMENT AND REMEDIATION ONLY — **not** a ratified production baseline

---

## 0. How to use this document

This is a **state handoff, not a directive.** It tells you what is on disk, what is proven, what is claimed but unproven, and what must not be changed. It deliberately does not tell you what to build next; the operator sets objectives.

Three rules govern how you read it:

1. **Every claim below carries an evidence label.** Preserve those labels if you quote this document. Repetition does not promote a label.
2. **Do not treat any number in this document as ratified** unless it is marked `[OBSERVED]` with the command that produced it.
3. **If you disagree with a finding, re-derive it from disk.** Do not adopt or reject it on the strength of this document alone. Two independent audits already converged on the disposition above; a third should test it, not echo it.

### Evidence labels

| Label | Meaning |
|---|---|
| `[OBSERVED]` | Directly read from disk or produced by a command run against the live tree, and recorded here with its source |
| `[REPORTED]` | Asserted by an audit, a run record, or a tool's own output; not independently re-derived here |
| `[DERIVED]` | Computed from other stated facts in this document |
| `[UNVERIFIED]` | Stated somewhere in the record but not confirmed, or confirmed only in part |
| `[WITHDRAWN]` | Previously asserted by this reviewer and since retracted, with reason |

---

## 1. Project identity and terminology

The **Sovereign Workspace** is a multi-module local-first application workspace on a Windows host. Terminology below is **frozen** — do not rename, abbreviate, or "clean up" any of it.

**Modules** (`Production Workspace\modules\`) `[OBSERVED — ls]`:

| Module | Role | Port |
|---|---|---|
| `sow` | Sovereign Orchestration Workspace — control plane, adapters, scheduler, Electron desktop app | shell on 5180 |
| `debate` | Debate Table multi-model deliberation | 8700 |
| `sovereign` | Sovereign reasoning pipeline (Ollama-backed) | 5175 |
| `distillery` | Sovereign Distillery — training/serving layer | 5184 |
| `tokencenter` | Token Center (a.k.a. Token Piggy Bank) — usage ledger and dashboard | 8765 |

**Governing contract:** `BUILD-DIRECTIVE-SWS-UI-001.md`, version **1.2**, plus addenda ADD-01 … ADD-08 in `docs/`.

**Gate ledger:** `evidence\GATE-LEDGER.json` — the record of gate decisions. `directive: SWS-UI-001`, `version: 1.2`. `[OBSERVED]`

**Goal oracle:** `goalcheck.py`, whose numbered output lands in `evidence\cpm1\goalcheck-N.txt`. The oracle is the **sole judge** of goal truth under this contract — a goal is TRUE only if the oracle says so, and no prose report overrides it. `[REPORTED — contract]`

**Work program in flight:** **CP-M1**, a 124-goal ladder. Latest oracle run is `goalcheck-66.txt`. `[OBSERVED]`

---

## 2. Ground truth on disk

### 2.1 Scale

`[REPORTED — independent audit 2026-08-26]`

- ~20,444 files, 7,915,922,685 bytes under `D:\Product Software`
- `Production Workspace` ≈ 7.90 GB / 20,217 files
- Includes one 5.225 GB GGUF model, which is most of the footprint
- 12 ZIPs recursively, 5 PDFs, 60 EXE, 37 DLL

### 2.2 Version control — the single most important fact in this document

**`Production Workspace` is NOT a git repository.** `[OBSERVED]`

```
$ git -C "D:\Product Software\Production Workspace" status
fatal: not a git repository (or any parent up to mount point)
```

The CP-M1 closeout manifest states this in its own hand `[OBSERVED — evidence\cpm1\9j\FINAL-EVIDENCE-MANIFEST.json]`:

```json
"final_commit": "no git commit (envelope forbids)"
```

**Consequence:** there is no commit to diff against, so every "changed lines" and "changed files" figure in the run records is a self-produced artifact with no independent anchor. This is the root cause of several findings in §5. **Establishing version control is the highest-value single action available and should precede any new feature work.**

`D:\Token Piggy Bank` *is* a git repository. It has exactly one commit. `[OBSERVED]`

### 2.3 What physically exists and runs

`[OBSERVED]` — present on disk:

- `modules/distillery/` with `serve.py`
- `modules/tokencenter/` with a hardened `piggybank.py` (adds POST Host/Origin/CSRF controls and loopback-pinned binding relative to the older copy)
- `shell/modules/*.json` manifests including `distillery.json`, `tokencenter.json`, `llamacpp.json`
- `shell/static/app.js`, `app.css` (patched)
- `shell/tests/` including `test_registry_fields_projected.py`, `test_incompatible_selection_refused.py`, `test_tokencenter_loopback_and_csrf.py`
- `runtime/` containing `current`, `logs`, `test-models`, `versions` (llama.cpp runtime is present)

`[REPORTED — audit runtime observation, read-only, 2026-08-26]` — listening at audit time:

| Port | Service | State |
|---|---|---|
| 5184 | Distillery | health OK, status **idle**, compute **false** |
| 8765 | Token Center — **served from the older `D:\Token Piggy Bank\piggybank.py`, not the hardened workspace copy** | health OK |
| 11434 | Ollama 0.33.0 | up |
| 5175 / 5180 / 8700 | Sovereign / shell / Debate | **not listening** |

### 2.4 Static validation results

`[REPORTED — independent audit]`

- 512 first-party Python files parsed — **0 syntax errors**
- 232 first-party JSON files parsed — **0 parse errors**
- 240 first-party JavaScript files checked — **0 syntax errors**
- Shell build manifest: **62/62 live paths match**
- Debate Python env: **22/22 locked packages match**
- Sovereign Python env: **85/85 locked packages match**
- Node: **75 lockfile entries, no version mismatch detected**

The codebase is syntactically and dependency-wise coherent. The problems are governance and evidence problems, not broken code.

---

## 3. The completion question: 107 vs 32

This is the number most likely to be misused by a resuming session. Read this section before quoting any completion figure.

### 3.1 What the oracle says

`[OBSERVED — evidence\cpm1\goalcheck-66.txt]`

```
summary: 107/124 TRUE
```

17 goals are FALSE. The named limitations, from the closeout manifest `[OBSERVED]`:

```
G26   NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH)
G28   NOT_RUN(LIVE_WORKERS_UNAVAILABLE)
G34/G35, G53, G91   NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
G70–G80             llama.cpp live legs NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
G117  fs-watch window operator-owned
G118  live rollback generate not demonstrated
```

Note the cause on G70–G80: **operator-owned service launch**, *not* a missing runtime. The llama.cpp runtime is present on disk. `[OBSERVED]`

### 3.2 Why 107 overstates completion

An audit pass classified each goal's oracle predicate into four kinds `[REPORTED — audit A predicate classification]`:

| Class | What the predicate actually tests |
|---|---|
| SUBSTANTIVE | An observable behavior of the system |
| STRUCTURAL | A file exists, or a manifest lists something |
| SELF-REFERENTIAL | A record the same run wrote, e.g. "the ledger says gate X is CANDIDATE" |
| TRIVIAL | Tautological or unconditionally satisfiable |

Only SUBSTANTIVE predicates are evidence that work was done. On that classification, **the count of goals resting on a substantive predicate is approximately 32** `[DERIVED — ceiling, not a verified pass count]`.

Two concrete illustrations, both from the oracle's own output `[OBSERVED — goalcheck-66.txt]`:

- `G115: TRUE  CANDIDATE, 3 evidence entries verified` — reads `GATE-LEDGER.json` and three files the same run produced. Self-referential.
- `G120: TRUE  every changed file classified; UNEXPECTED=0` — reads `evidence\cpm1\9j\diff-classification.txt`. The zero is circular: ten hash-confirmed changed product files are absent from the classification the predicate reads, so "UNEXPECTED=0" reports the completeness of the list to itself. `[REPORTED — audit; classification file confirmed present]`

### 3.3 Adversarial sample

A 15-goal adversarial re-test of goals the oracle marked TRUE returned **3 pass / 3 partial / 9 fail** `[REPORTED — audit G]`.

### 3.4 The number to carry forward

> **Use 32 as the substantive ceiling and 107 as the oracle count, and always state which one you mean.**

A session that starts from "107 done" will build on top of roughly nine failures it believes are finished. This is the single most consequential misreading available in this handoff.

---

## 4. Attribution record — Token Piggy Bank launchers (CLOSED)

Recorded because it was an open protected-tree question and is now settled. Future sessions should not re-open it.

**Baseline.** `D:\Token Piggy Bank` HEAD is one commit `[OBSERVED]`:

```
6972194 | 2026-08-23 15:30:37 -0500 | Samuel Lawson <Darksciencedivision@gmail.com>
        | "Launch Sovereign Token Center"

git show HEAD:Start-TokenPiggyBank.ps1        → 729 bytes  sha256 0d806419…ad6c
git show HEAD:Start-SovereignTokenCenter.ps1  → 729 bytes  sha256 0d806419…ad6c
```

This matches the CP-M1 Band-0 manifest exactly, so Band-0 recorded the committed state correctly.

**Event 1 — content change, 2026-08-26 21:48. Author unattributed; change benign.** `[OBSERVED diff; [UNVERIFIED] author]`

Both launchers were rewritten to 2078 bytes, sha256 `50e56fe6…46f97`, as an **uncommitted working-tree edit** — which is why git records no author. `git status` shows ` M Start-TokenPiggyBank.ps1`. The diff is +46/−9 and is a coherent hardening upgrade: it validates that the process holding port 8765 is actually a `piggybank.py` python process before proceeding, resolves the 3.12 interpreter explicitly with a real error path, pins the bind to `--host 127.0.0.1 --port 8765`, adds a 30-second health-poll readiness loop, and terminates the child on failure.

The CP-M1 closeout lists *"Token Center ownership after Band 9"* as an **open operator decision** `[OBSERVED]`, which is consistent with Band 9 having produced this edit. That is circumstantial and is **not** offered as proof of authorship.

**Event 2 — relocation, 2026-08-27 ~02:39. Authorized and accounted for.** `[OBSERVED]`

The independent audit moved `Start-SovereignTokenCenter.ps1` from `D:\Token Piggy Bank\` to `D:\Product Software\`, hash-preserving, at the operator's express request. `git status` now shows ` D Start-SovereignTokenCenter.ps1`. The audit report states it did not alter `Start-TokenPiggyBank.ps1`.

**Disposition:** this was **not** an unauthorized protected-tree write. It is an uncommitted local edit that needs committing, plus one authorized move. Two actions remain: commit the working-tree change in `D:\Token Piggy Bank` so it stops reading as drift, and resolve the relocated launcher (see B-05).

---

## 5. Consolidated blocker register

Merged from two independent audits. `A#` = CP-M1 evidence audit; `F#` = independent `D:\Product Software` audit, 2026-08-26. Both audits reached the same disposition; the second states it re-derived facts rather than adopting the first's conclusion.

| ID | Severity | Finding | Source | Label |
|---|---|---|---|---|
| **B-01** | **Critical** | **No version control on `Production Workspace`.** No commit exists; the closeout records `"final_commit": "no git commit (envelope forbids)"`. Every change record is unanchorable. | A, F-01 | `[OBSERVED]` |
| **B-02** | **Critical** | **Sovereign install provenance names the wrong product's archive.** `modules/sovereign/INSTALL-PROVENANCE.json` records `source: SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520.zip` with `source_sha256: 620e8459…be96`. That hash belongs to the **Distillery** enterprise zip. The Sovereign zip hashes `150e518e…ec51`. The module cannot be traced to its own claimed package. | F-02 | `[OBSERVED]` |
| **B-03** | **Critical** | **Workspace is ahead of its ratified baseline.** Gate ledger: 29 entries — **9 PASS, 1 STOP, 19 CANDIDATE**. The operator promotion on Gate 6 applies to an earlier SWS v1.2 baseline; all CP-M1 work is candidate-only. | F-01 | `[OBSERVED]` |
| **B-04** | **High** | **Change records are wrong.** `linecount-a.txt` records `TOTAL-A 371 / 1850` plus a `+59` addendum (430 total); independent recomputation gives **814**. `linecount-b.txt` records `TOTAL-B 156 / 1625`; recomputation gives **279**. `G121: TRUE "both envelopes honoured separately"` reads these same records, so the oracle validated the run's own arithmetic. | A, F-01 | `[OBSERVED]` records; `[REPORTED]` recomputation |
| **B-05** | **High** | **Relocated launcher cannot cold-start.** `D:\Product Software\Start-SovereignTokenCenter.ps1` derives `$root` from its own directory and expects a sibling `piggybank.py`. That file is not there — it is in `D:\Token Piggy Bank\`. The launcher appears to work only because the old service is already listening. | F-03 | `[OBSERVED]` |
| **B-06** | **High** | **Active Token Center is the older, less-hardened copy.** Port 8765 is served from `D:\Token Piggy Bank\piggybank.py`. The workspace copy adds POST Host/Origin/CSRF protections the running one lacks. It was launched on `127.0.0.1`, which bounds exposure. | F-07 | `[REPORTED]` |
| **B-07** | **High** | **Debate production ZIP broke its signed boundary.** On disk: 44 entries / 232,589 bytes, sha256 `29b364b0…2f93`. Sidecar and report expect 35 entries / 133,553 bytes, `be6cfe8c…a383`. Nine `SOW_REVIEW_ROUND2_RAW` files were added inside the archive. The 34 application-manifest files still hash correctly. | F-04 | `[REPORTED]`; hashes `[OBSERVED]` in package manifest |
| **B-08** | **High** | **Documented clean install does not reproduce the layout.** The README expands the Debate and Sovereign ZIPs directly into module directories, but both archives contain their own top-level directory, so a clean run produces nested paths and fails validation. | F-05 | `[REPORTED]` |
| **B-09** | **High** | **Electron 31.7.7 is end-of-life.** Outside the supported stable-major window. Sandboxing, context isolation, and navigation/window restrictions are in place and are real mitigations, but do not substitute for upstream security fixes. | F-06 | `[REPORTED]` |
| **B-10** | **High** | **Full-auto tooling grants broad mutation authority by default.** `Start-OpenCode.ps1` launches `opencode --auto` with `edit`, `bash`, and `webfetch` all set to `allow`. **Provenance note: this permission profile was authored by this reviewer at the operator's request to unblock an automated run. The finding is accepted.** | F-08 | `[OBSERVED]` |
| **B-11** | **Medium** | **Weak and self-referential oracle predicates.** See §3.2. Roughly 92 of 124 goals rest on structural, self-referential, or trivial predicates. | A | `[REPORTED]` |
| **B-12** | **Medium** | **Gate evidence stored at mutable paths.** Of 379 evidence references rehashed from the ledger, **322 match and 57 differ; none missing.** Mismatches concentrate in older gates citing live paths. Contract addendum E-7c requires frozen copies under `evidence/cpm1/<gate>/frozen/`; this is not uniformly honored. | A, F-10 | `[REPORTED]` |
| **B-13** | **Medium** | **`G120 UNEXPECTED=0` is circular.** Ten hash-confirmed changed product files are absent from `evidence\cpm1\9j\diff-classification.txt`, which the predicate reads. | A | `[REPORTED]` |
| **B-14** | **Medium** | **Sovereign runtime config drift with no provenance decision.** Installed `SYSTEM_MANIFEST.json` changes two model assignments vs the signed package: adversarial challenger `qwen3:32b → ornith:9b`, synthesizer `qwen2.5:14b-instruct → qwen3.8:27b`. No adjacent operator decision record explains it. | F-09 | `[OBSERVED]` |
| **B-15** | **Medium** | **Full-suite evidence is stale.** The 129-passing shell run predates later build-manifest changes and carries a lingering-subprocess ResourceWarning, an unclosed-file ResourceWarning, and a PowerShell RemoteException line. Only six targeted tests were run afterward. | F-11 | `[REPORTED]` |
| **B-16** | **Medium** | **`canonical_registry.py` is dead code.** `modules/sow/control_plane/canonical_registry.py` (53 models, 18 fields) has **zero consumers** — grep across all `.py`/`.js` under `modules/sow` finds no reference to `canonical_registry` or `list_for_selectors` outside the module itself. | A | `[OBSERVED]` |
| **B-17** | **Low** | **Hygiene.** A stray file literally named `$null` in the workspace root contains captured PowerShell error output. Many PE files are unsigned. Secret-pattern scanning found only test fixtures and detector examples — which does not prove absence of secrets. | F-12 | `[OBSERVED]` for `$null`; rest `[REPORTED]` |

### 5.1 Corrections issued by this reviewer

Recorded so a resuming session does not inherit them:

- `[WITHDRAWN]` "The G70–G80 NOT_RUN band is contradicted because the llama.cpp runtime is present." The closeout states the cause as `SERVICE_LAUNCH_IS_OPERATOR_OWNED`, not a missing runtime. No contradiction exists.
- `[WITHDRAWN]` "`shell/modules/llamacpp.json` is 52 lines against a 45-line cap." This misread the record format. In `linecount-b.txt`, `llamacpp.json | 0 | 45` means *zero changed lines against a 45-changed-line budget* — it is a change budget, not a file-size cap. The file is 52 lines total `[OBSERVED]` and is absent from `evidence/cpm1/before-b/` `[OBSERVED]`, which is consistent with "not touched in Package B." Whether it was created earlier in the program is **`[UNVERIFIED]`** and settling it requires the `before-a` tree.
- `[WITHDRAWN]` "Two files were modified in a protected tree without authorization." Superseded by §4.

---

## 6. Constraints that remain in force

These are operator-set or contract-frozen. **A resuming session must preserve every one of them.** They are not suggestions and they are not this reviewer's preferences.

**Publication and accounts**
- No `git push`, no remotes, no PRs, no publication of any kind
- No purchases, sign-ups, or account changes
- No credentials created, read, stored, or transmitted; **credentials must never reach an artifact**

**Frozen surfaces**
- `docs/canonical/` and `schemas/*.schema.json` — **frozen**
- Registers and evidence — **append-only**; history is never rewritten
- `config/live_operation.json` — **operator-only**
- Terminology — frozen. **Removal of `ws` is FORBIDDEN** (`apps/desktop/ipc/client.js:26` requires it)
- **Never populate** `mcp_server/auth/` or `mcp_server/access_control/`

**Protected trees — read-only**
- `D:\Product Software\` outside `Production Workspace\`
- `D:\multi model terminal app\`
- `D:\Sovereign Distillery\`
- `D:\Sov 1\`
- `D:\Token Piggy Bank\` (its `data/**` excluded)
- Product trees must remain **byte-identical**
- **Ollama's model store is read-only at all times** — never pull, rm, move, rename, or write

**Test integrity**
- **Never delete a test, add a skip or xfail, widen an assertion, or raise a timeout to turn a red green.** This has no exceptions.

**Execution**
- Application code never launches via `cmd.exe`, PowerShell, `.cmd`, `.bat`, or `shell=True`
- No live provider call without a declared, authorized live probe
- llama.cpp is **never** promoted to production default; **Ollama remains the production default**
- No TTS path; no Antigravity execution carve-out

**Builder-role limits** (apply to any model doing the work, as distinct from the reviewer)
- **Never write PASS to a gate.** The builder writes only `CANDIDATE`, `NOT_RUN`, or `STOP`
- **Never sign as the operator**
- Never write to protected sources
- Never claim availability that was not demonstrated
- Never promote to production
- One causal chain, one commit; a repair sweeps what it moved
- The live-leg set is **derived, never enumerated**

---

## 7. What is NOT proven

State these as open whenever the system is described to anyone:

- No end-to-end live generation path has been demonstrated for the current candidate
- Rollback has never been demonstrated (`G118 FALSE — rollback.txt absent/incomplete` `[OBSERVED]`)
- Live workers were unavailable throughout (`G28`)
- The filesystem-watch window is operator-owned and was not exercised (`G117 FALSE` `[OBSERVED]`)
- The Conductor in-app spawn path dies on launch; cause isolated by elimination to the in-app supervised-spawn path, **not** conclusively identified (`G26`)
- Distillery reports `status: idle, compute: false`; its hardware gate remains blocked. **It must not be described as a production training system**
- No clean-room install has succeeded from an empty destination
- No full test suite has been run against the current final tree

### 7.1 Two architectural findings worth carrying forward

Both are genuine results from the G26 investigation and should not be re-derived from scratch:

1. **Governed Conductor communication is Claude-hook-specific by design.** It requires the `voice_turn_boundary@1.0` hook protocol, which only the `claude_code` provider implements. `modules/sow/tools/live/emit_conductor_launch.py` states the rule directly: *"Do not fabricate Claude hooks for a provider that does not implement that hook protocol."* A non-Claude conductor cannot satisfy the boundary by imitation.
2. **A quoting defect made a `claude_code` conductor impossible on any host with spaces in its paths.** The producer rendered PowerShell single-quoted with `'` doubling; the verifier re-derived double quotes, so `commands_equal: false` always. **Found, fixed, and pinned** by `apps/desktop/test/conductor-hook-command-roundtrip.test.js`.

---

## 8. Recommended remediation sequence

Ordered by dependency, not by severity. Steps 1–2 unblock everything else.

1. **Establish version control.** `git init` `Production Workspace`, add a `.gitignore` that excludes the 5.225 GB model and `runtime/` build output, and commit the current tree as the frozen candidate. Nothing downstream is verifiable without this. *(B-01)*
2. **Commit the working-tree change in `D:\Token Piggy Bank`** so the launcher edit stops reading as unattributed drift. *(§4)*
3. **Repair Sovereign provenance** from verified installation evidence, and add an automated cross-package identity check that rejects a hash belonging to another product. *(B-02)*
4. **Recompute and correct the linecount records** against the new commit, and re-run the oracle so `G121` validates real arithmetic. *(B-04)*
5. **Freeze gate evidence** into content-addressed per-gate bundles under `evidence/cpm1/<gate>/frozen/` and repoint the ledger at the frozen artifacts. *(B-12)*
6. **Choose one canonical Token Center location**, migrate its data deliberately, repair the relocated launcher, and cold-start the hardened copy after regression and state-compatibility checks. *(B-05, B-06)*
7. **Quarantine the altered Debate ZIP.** Do not reuse its stale sidecar; rebuild, manifest, report, and sign under a new immutable identity. Keep review evidence outside product archives. *(B-07)*
8. **Fix the install procedure and clean-room test it** from an empty destination. *(B-08)*
9. **Replace weak oracle predicates** with behaviorally discriminating assertions, then re-run the full ladder. Expect the TRUE count to fall — that is the point. *(B-11, B-13)*
10. **Run the full suite at the frozen commit**, eliminate the resource warnings, and bind the output to the commit and build-manifest hashes. *(B-15)*
11. **Execute the live paths**: worker failure, model generation, PNG, planner, filesystem watch, and rollback. *(§7)*
12. **Upgrade Electron** through supported majors with staged compatibility testing, then add an automated supported-major policy check. *(B-09)*
13. **Constrain full-auto tooling**: make restricted permissions the default, require an explicit operator action for full-auto, scope filesystem access, and log the selected privilege profile at startup. *(B-10)*
14. **Remove `canonical_registry.py` or give it a consumer.** Dead code in a control plane is a maintenance and audit liability. *(B-16)*
15. **Delete the stray `$null` file** after preserving anything forensically needed. *(B-17)*

---

## 9. Instructions to the receiving session

**Do:**
- Re-derive any finding you intend to act on
- Preserve evidence labels when you quote this document
- State plainly which completion number you are using and why (§3.4)
- Treat `goalcheck.py` as the sole judge of goal truth
- Ask the operator when scope, promotion, or acceptance is in question — those are his, not yours

**Do not:**
- Do not treat this document as a directive, a scope definition, or an authorization
- Do not write PASS to any gate, or sign as the operator
- Do not promote anything to production
- Do not describe the workspace as a verified or production-ready release
- Do not weaken a test to make a red go green
- Do not write to any protected tree listed in §6
- Do not silently redefine an objective, and do not quietly drop a constraint you find inconvenient

**If you find this document wrong, say so explicitly and show the disk state that contradicts it.** That is a better outcome than agreement.

---

## 10. Provenance of this document

| Field | Value |
|---|---|
| Assembled from | CP-M1 evidence audit (audits A–G); independent `D:\Product Software` audit dated 2026-08-26; direct read-only inspection of the live tree on 2026-08-27 |
| Independent audit package | `SOVEREIGN_PRODUCT_SOFTWARE_INDEPENDENT_AUDIT_PACKAGE_20260826.zip`, manifest schema `sovereign-independent-audit-package-v1`, created `2026-08-27T03:12:03Z`, 30 files |
| Live-tree commands run | `git status`, `git log`, `git show`, `git diff`, `sha256sum`, `ls`, `wc`, `cat`, `find` — read-only |
| Files modified by this reviewer while preparing this document | **None** |
| Convergence | Two independent audits reached the same disposition. The second states it re-derived key ledger and evidence facts rather than adopting the first's conclusion. |

**Builder claim:** No gate is submitted for reviewer evaluation. No PASS status is asserted.

**Operator authority:** Objectives, scope, promotions, strategic direction, and final acceptance belong to the operator. This document records state; it does not grant authority.

*End of canonical handoff.*
