# Independent Audit — Grounded RC3 Integration and PR #1 Merge

| | |
|---|---|
| **Subject** | `ryguy-pixel/Sovereign-Distillery` @ `44f69077` · RC3 build → integration → PR #1 → merge · Grounded Thesis v1.1 |
| **Date** | 20 August 2026 |
| **Auditor role** | Research Validator / Analyst |
| **Method** | **Independent inspection of the repository on disk**, not review of the build transcript. Git history, working-tree state, test execution, source reading, evidence files, and licence research were checked directly. |
| **Authority** | Operator owns acceptance. This is an audit, not an approval. |

---

## 0. Summary

The merge is real, the tree is clean, and the tests pass — **I verified all three independently rather than accepting the reports.** The engineering quality of the shared infrastructure is high in the places that matter most, and the source-admission discipline is better than the field norm.

Three findings are structural rather than cosmetic. One of them concerns what is in the repository at all.

| Class | Count |
|---|---|
| Verified-correct claims (checked, not assumed) | 9 |
| Structural findings | 1 (**GR-1**) |
| Gate-integrity findings | 2 (**GR-2**, **GR-3**) |
| Evidence-integrity findings | 3 (GR-4 … GR-7) |
| Minor / hygiene | 3 (GR-8 … GR-10) |
| Stale-document issue | 1 |

---

## 1. What I verified directly

| Claim | Method | Result |
|---|---|---|
| Working tree clean at `44f69077` | `git status`, then CRLF analysis | **CONFIRMED.** My first look showed 60 modified files — that was a false positive from reading a CRLF Windows checkout through a Linux mount. `git diff --ignore-cr-at-eol` is empty. The report was right. |
| 27/27 tests | **Staged the code into this container and ran pytest** on Linux / Python 3.11 | **CONFIRMED — 27 passed, 6 subtests.** Reports only claimed Windows 3.12/3.13/3.14; cross-platform portability is now verified too. |
| No repository-wide licence inferred | `git ls-files \| grep -i licen` | **CONFIRMED** — no LICENSE file |
| No weights / secrets / caches staged | `.gitignore` review + `git check-ignore` | **CONFIRMED** — `dist/`, `*.egg-info/`, `*.gguf`, `*.safetensors`, `*.pt`, `checkpoints/`, `corpora/`, `private/`, `*.key`, `*.pem` all excluded |
| All four D-9 candidates remain UNKNOWN | `registry/source_admission_candidates.json` | **CONFIRMED**, and see §3 — the policy text is exemplary |
| Gemma 4 is Apache-2.0 | Web research | **CONFIRMED.** Gemma 4 did move to Apache-2.0, unlike the earlier custom Gemma Terms. The report's research was accurate, and its caution that this does *not* establish output-training authority is correct. |
| Historical best is an aggregate, not a lucky run | Read `gate/historical.py` | **CONFIRMED, and better than specified** — requires ≥2 promotion runs per bundle, computes an *n*-weighted mean, and records `max_single_run_ignored` explicitly. Faithful to thesis §27. |
| Source-admission transitions match thesis §7 | Read `source_admission/__init__.py` | **CONFIRMED**, including `REJECTED: set()` — terminal, no exit path |
| Shadow surface cannot execute | Read `ops/promotion.py` | **CONFIRMED** — `ShadowPlanner` exposes no execution method and returns `mutating_execution_available: False`. Thesis §31 honoured in code, not just prose. |

I also confirmed `exclusion/__init__.py` performs a correct BFS descendant closure with dangling-edge detection and deterministic ordering.

**On method:** I initially suspected three defects — CRLF-corrupted hashing, a per-item "lucky run" historical best, and a Gemma licence error. All three were **refuted** by inspection. They are recorded here because a validator who only reports confirmed suspicions is not measuring anything.

---

## 2. Findings

### GR-1 — STRUCTURAL — The "canonical joint Sovereign Distillery repository" contains no Sovereign work product

**Evidence.** The declared canonical baseline `f1904399` is titled *"Add Grounded Distillery thesis v1.1 and design spec (draft)"* and contains exactly three files: `README.md`, `docs/SPEC-v1.1-draft.md`, `docs/THESIS.md` — **all three are Grounded documents.**

Of 64 tracked files at `44f69077`, the only path containing "sovereign" is `grounded/harness_adapters/sovereign_product.py` — a *Grounded* adapter that reads Sovereign's runtime records. `docs/THESIS.md` is the **Grounded** thesis. There is no Sovereign thesis, spec, decision register, invariant list, evidence register, teacher registry, hardware profile, or tool in the repository.

Meanwhile the Sovereign work product — validation report, design plan, integration review, `DECISIONS-v1.md`, `runs/hardware_profile.json`, `registry/teachers.json`, and three characterization tools — sits in **`D:\Sovereign Distillery`**, a separate directory that no phase of this work inspected or integrated.

**Why this matters, beyond bookkeeping.** Report §E stated: *"The canonical three-file baseline contained zero automated tests or workflows. Therefore there were no pre-existing canonical Sovereign tests to run."* That is literally true and structurally misleading. It frames *absence of Sovereign* as *absence of tests*. Sovereign was never in the repository, so "no Sovereign tests to run" was guaranteed before the work began.

The consequence is concrete: every report asserts *"Grounded/Sovereign treaty preserved: PASS."* **That assertion cannot be verified from this repository**, because the treaty is documented only in Grounded's own files, describing Grounded's own obligations. Sovereign's invariants (INV-1…INV-15), its dual-gate governed-floor design, its tiered teacher queue, and its OQ register are not present to be checked against.

**This is not an argument against the merge.** The Grounded implementation is sound and the merge is clean. It is an argument that the repository is currently *Grounded's*, named Sovereign's, and that the treaty is a one-sided declaration until Sovereign's canonical documents are committed alongside it.

**Recommended:** import the Sovereign canonical set into `docs/sovereign/` (or a sibling path) as a distinct commit, then re-assert treaty compliance as a checkable property rather than a stated one. That is also what would let a future `tests/test_treaty_contracts.py` mean something.

### GR-2 — MAJOR — HG-5's anti-p-hacking control is a non-empty-string check

Thesis §26: *"M/T/D must be declared before comparative results are inspected."* This is the single control preventing margins from being fitted to results after the fact.

`GateMargins.__post_init__` enforces only that `declared_at` and `authority` are non-empty and margins non-negative. **`paired_gate()` never compares `declared_at` against the evaluation run's timestamp.** A margin set after inspecting comparative results validates identically to one predeclared.

The invariant is documented, named as governing a hard gate, and enforced as "a string exists."

**Fix, and it is small:** thread the evaluation run's `started_at` (or the frozen suite-run id and its timestamp) into `paired_gate`, assert `declared_at < started_at`, and record both in the evidence package so the ordering is auditable after the fact rather than asserted at the time.

### GR-3 — MAJOR — The router write is atomic but not durable, and the rollback write can fail unhandled

Two defects in `ops/promotion.py`, both on the HG-8 path.

**(a) No durability.** `_atomic_write` writes a temp file then calls `os.replace`. Verified by source probe: no `flush()`, no `os.fsync()` on the file, no directory fsync. `os.replace` makes the *directory-entry swap* atomic; it does **not** guarantee the temp file's contents reached disk. A crash or power loss in that window can leave the router pointing at a truncated or empty file. `current()` then raises `ContractError` — which means **the rollback path itself becomes unavailable.** For a promotion router that is the worst available failure mode: the mechanism designed to recover from a bad promotion is disabled by the same event.

**(b) The rollback write is unguarded.** In `promote()`, when `readiness_check` fails the code calls `_atomic_write(prior)` with no `try/except`. Verified: `"rollback write wrapped in try/except: False"`. If that second write fails, the exception propagates and the router is left on the **unhealthy candidate**, in a state that is neither `PROMOTED` nor `ROLLED_BACK`. Thesis §32 admits only those two outcomes.

**On the citation.** The first build report justified this with *"os.replace … has atomic semantics according to the official Python documentation."* Python attributes that guarantee to POSIX. This project runs on **Windows** (`D:\` paths, PowerShell, a Windows-specific SQLite handle defect in the same report). The write pattern is still the right one — but the citation does not transfer, and directory fsync is unavailable on Windows, so durability there needs a different treatment rather than an assumption.

**Fix:** `flush()` + `os.fsync()` before `os.replace`; wrap the rollback write and, on failure, emit a terminal `ROLLBACK_FAILED` state rather than an exception; document the Windows durability posture explicitly.

### GR-4 — MODERATE — The confidence level is ambiguous between thesis and implementation

`paired_mean_ci` builds a **two-sided** percentile interval: at `confidence=0.95` the lcb is the 2.5th percentile. All three decision rules in `paired_gate` use **only** the lcb — they are one-sided tests. A 2.5th-percentile bound used one-sided is a **97.5% one-sided** test, not 95%.

`power_report` uses `1.96 * stdev / sqrt(n)`, which is the two-sided-95% / one-sided-97.5% z-value — so the implementation is *self-consistent*. But thesis §26 states *"Default confidence level: 95%"* next to three LCB-only rules, which reads as one-sided 95% (z = 1.645).

The gate is therefore **stricter than the stated policy**, which is the safe direction — it cannot cause a false promotion. The cost is real anyway: an item budget computed from a one-sided-95% understanding will be roughly **42% short** of what the implemented gate requires to resolve the same margin. That is a G2 planning consequence, not a bug.

**Fix:** state in §26 which it is, and make `paired_mean_ci` take the tail explicitly rather than leaving it implicit in an index calculation.

### GR-5 — MODERATE — HG-0 PASS rests on 4 sessions / 5 turns, and its evidence is unauditable by construction

`runs/G0-live/hg0-status.json`: `session_count: 4`, `turn_count: 5`, `gold_accrual_candidates: 2`, implicit signals 2 positive / 2 negative. All twelve assertions `true`.

Every assertion may be honest. But **HG-0 is named "Real telemetry acceptance"** and it is being satisfied by five turns.

Compounding it: `runs/G0-live/events.jsonl` and `hg0-events.jsonl` are **gitignored**, and the 12:27 report records that the first generation of the event log *"was never committed and is not recoverable through Git."* So the committed evidence is a summary JSON asserting its own conclusions, with the underlying events untracked and one generation destroyed. **Under the current `.gitignore`, HG-0 can never become repository-verifiable.**

Excluding raw content is *correct* — thesis §43 forbids prompts and outputs in Git. But the choice is not binary. A **content-free hashed event manifest** — session-id hash, turn ids, timestamps, outcome, signal type, validator result, source-admission class, no prompts or outputs — would give full auditability without content, and the thesis's own §3.4 lineage schema already enumerates those exact fields.

**Also:** `active_alerts` contains a live `NO_TRACE` alert *at the moment HG-0 was declared PASS*. It is the deliberate monitor fixture (`sessions.no_trace_monitor`), so the gate is not lying. But a synthetic alert left permanently firing makes a real `NO_TRACE` indistinguishable from the fixture and is the standard route to alert fatigue. Mark fixture-generated alerts as such, or clear it.

### GR-6 — MODERATE — Whether G0-A and G0-B were live or retro-labelled imports is not recorded

Thesis §39 requires *"G0-A: real success session with stable joins and `/success`"* and *"G0-B: real failure session with `/fail`."* Those are live operator marks.

The earlier `status.json` records `mode: "active-runtime-immutable-evidence-import"` with the limitation *"Imported real pre-existing runtime turn evidence; no newly generated session was initiated."* The later `hg0-status.json` asserts `G0-A: true`, `G0-B: true`, and `explicit_label_compliance: {finished: 3, labeled: 3, rate: 1.0}` — **but does not distinguish a live `/success` mark from a label attached during import.**

G0-C is clearly live and is good evidence (the same-session DEEP cancellation → QUICK recovery). G0-A and G0-B are not distinguishable from retro-labelled historical records, and imported Sovereign runtime records almost certainly predate Grounded's `/success` and `/fail` commands.

**Fix:** add a `label_origin` field per session — `live_operator_mark` vs `import_time_classification` — and re-state HG-0 accordingly. If A and B are retro-labelled, that is defensible; it just is not what §39 says.

### GR-7 — MODERATE — The instrumentation checksum guard is anchored to an unversioned dirty tree

`registry/instrumentation_checksums.json` pins SHA-256 values for `sovereign_product.model_client` and `sovereign_product.semantic_deep` — files in the **separate Sovereign runtime**, which every report describes as *"dirty and deliberately left untouched."*

So the expected hashes were captured from an uncommitted working state of another repository. Three consequences:

1. The baseline is **not reproducible** — no commit reconstructs that file state.
2. If the operator ever commits or tidies that runtime, the guard fires.
3. The guard **cannot distinguish tampering from housekeeping**, which is the one distinction it exists to make.

The registry note (*"a mismatch blocks HG-0 evidence finalization until reviewed; it does not authorize resetting the runtime tree"*) is thoughtful and does not solve the provenance problem.

**Fix:** record the runtime repository's commit SHA plus its dirty-file list alongside the hashes, or require that tree be committed before pinning.

### GR-8 — MINOR — E7 acceptance is fixture-bound

`e7_acceptance` hardcodes `x-child`, `x-grandchild`, `sx1`–`sx3`, `y-root`, `y-child`. It validates exactly the graph in thesis §17 and nothing else. The reports' qualification — *"HG-2: PASS on synthetic transitive E7 acceptance"* — is accurate and appropriately hedged.

The gap is forward-looking: there is no general acceptance harness for a **real client purge**, which is what HG-2 must eventually cover and what RQ7 asks. The closure algorithm in `exclude()` *is* general; only the acceptance wrapper is not.

### GR-9 — MINOR — The historical-best store and the paired gate are not connected

`HistoricalBestStore.reference()` returns a **scalar** aggregate. `paired_gate()` consumes a **per-item vector** `historical_best`. Nothing in the codebase produces that vector.

This is a G2 work item rather than a defect — but it is the precise seam where the "no lucky single run" discipline could be silently lost. The store forbids it correctly; the vector-builder does not exist yet and would be the natural place to reintroduce a per-item maximum across checkpoints, which is exactly the artifact §27 rules out.

**Flag it now so whoever writes the builder knows it is load-bearing.**

### GR-10 — MINOR — No `.gitattributes`; `core.autocrlf` unset

Verified: `docs/THESIS.md` holds 1577 CR and 1577 LF bytes; no `.gitattributes`; `core.autocrlf` unset. Line endings are therefore environment-dependent.

Currently harmless — all hashing in the codebase is byte-mode on files outside the repo, and the router writes with `newline="\n"` explicitly (a good catch by whoever wrote it). But this is a repository whose entire evidentiary model is hash-based, and CI on Linux will check out different bytes than a Windows workstation. **Pin it before CI exists, not after.**

---

## 3. Where the work is genuinely strong

Worth stating plainly, because the findings above are the exceptions rather than the pattern.

**The source-admission registry is the best artifact in the repository.** Its policy line:

> *"No model moves from UNKNOWN because a similarly named or exact artifact has a permissive model-weight license; UNKNOWN and REJECTED remain barred from training and synthetic seeding."*

with per-candidate `output_use_restrictions: "NOT_ESTABLISHED_BY_MODEL_WEIGHT_LICENSE"` and `commercial_or_internal_restrictions: "PENDING_EXPLICIT_OUTPUT_USE_REVIEW"`. That separates **weight licence** from **output-use authority** — a distinction most of the field collapses, and the one I flagged as unresolved in the original Sovereign validation report (F-6). It is resolved here properly: blob hashes recovered, upstream model cards cited, and every candidate still `UNKNOWN` because the licence research does not answer the question actually being asked.

`gate/historical.py` exceeds its specification. `source_admission` transitions are exact. `exclusion` is a correct closure with dangling-edge detection. `ShadowPlanner` enforces §31 structurally rather than by convention. The `.gitignore` correctly excludes raw telemetry. D-9 held fail-closed across four separate authorization directives under evident pressure to advance — that is the discipline actually being tested, and it held.

---

## 4. Document-state issue

**The uploaded `GROUNDED_DISTILLERY_THESIS_v1.1_GITHUB.md` is not the repository's `docs/THESIS.md`.**

| | Uploaded file | Repository `docs/THESIS.md` |
|---|---|---|
| Authors row | absent | present (Samuel Lawson · ryguy-pixel) |
| Status | *"architecture frozen pending final treaty-owner sign-off and canonical PR merge"* | *"canonical branch integration complete, with PR #1 open pending treaty-owner review"* |

**Both are now stale.** PR #1 merged at `39aa889`; main is `44f69077`. In-repo §41 still reports the integrated suite as **25/25** (now 27) and HG-0 as **BLOCKED / PARTIAL LIVE** (now claimed PASS).

Per the thesis Release Note — *"Future substantive thesis changes after freeze require a version bump and run evidence"* — the correct remedy is a **v1.2 bump or an appended evidence-state section**, not a silent edit to a frozen document. Editing §41 in place would violate the document's own freeze rule.

---

## 5. Exact next actions

Ordered by cost-to-value.

| # | Action | Finding | Effort |
|---|---|---|---|
| 1 | Add `label_origin` to G0 session evidence and re-state HG-0 | GR-6 | one field |
| 2 | Assert `declared_at < eval_run.started_at` in `paired_gate` | **GR-2** | ~5 lines |
| 3 | `flush()` + `fsync()` before `os.replace`; guard the rollback write; add a terminal `ROLLBACK_FAILED` state | **GR-3** | ~10 lines |
| 4 | Commit a content-free hashed event manifest for G0 | GR-5 | one writer |
| 5 | Pin the runtime commit SHA + dirty-file list beside the instrumentation checksums | GR-7 | one field |
| 6 | Declare one-sided vs two-sided in §26; make the tail explicit in `paired_mean_ci` | GR-4 | one line + doc |
| 7 | Add `.gitattributes` pinning `* text=auto eol=lf` before CI | GR-10 | one file |
| 8 | Mark or clear the fixture `NO_TRACE` alert | GR-5 | one field |
| 9 | Import the Sovereign canonical document set, then re-assert treaty compliance as checkable | **GR-1** | one commit |
| 10 | v1.2 thesis bump reflecting merged state, 27/27, and current gate status | §4 | doc |

**Items 2 and 3 should land before HG-3.** Both sit on gate paths that HG-5 and HG-8 depend on, and both are cheaper to fix now than after a candidate exists to be gated.

**Item 9 is the one that changes what the project is.** Until Sovereign's canonical documents live in the repository named after Sovereign, "treaty preserved" is a claim the repository cannot evaluate.

---

*This is an audit. It is not an approval. Acceptance belongs to the operator.*
