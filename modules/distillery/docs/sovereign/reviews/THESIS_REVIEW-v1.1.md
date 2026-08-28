# Review — Sovereign Distillery Thesis v1.1 (GitHub-ready package)

| | |
|---|---|
| **Subject** | `sovereign-distillery-thesis-v1.1` — 9 files, 84 KB |
| **Date** | 19 August 2026 |
| **Reviewer role** | Research Validator / Analyst |
| **Authority** | Operator owns acceptance. This is a review, not an approval. |
| **Verification performed** | Full file inspection · internal Markdown link resolution · path-reference existence check · invariant numbering audit · carry-forward audit of previously-accepted defects (RD-1..RD-4) · `.gitignore` vs. stated evidence requirements · licence/platform-terms check |

---

## 0. Verdict

**The package is well built and its evidentiary posture is stricter than my own.** The `MEASURED-REPORTED` distinction is a genuine improvement and it corrects a real weakness in my design plan.

**It is not ship-ready as-is.** One defect blocks the repository's own stated path to reproducibility, two previously-accepted fixes were lost in consolidation, and five invariants were dropped while the numbering preserves the gaps where they used to be.

| Class | Count | Blocking? |
|---|---|---|
| Concessions — v1.1 corrects me | 4 | — |
| Blocking before first commit | 1 | **Yes** — TR-1 |
| Regressions against accepted decisions | 2 | **Yes** — TR-2, TR-3 |
| Should fix before push | 4 | Recommended |
| Clean | link integrity (9/9), secrets, structure, changelog discipline | — |

---

## 1. Verification results

| Check | Result |
|---|---|
| Internal Markdown links | **9 resolved, 0 broken** |
| Secrets / credentials / keys | **None found** |
| Model weights or large binaries | **None** — correctly excluded |
| Changelog ↔ document agreement | Mostly good; one claimed fix not applied (TR-6) |
| README ↔ filesystem | Accurate — every referenced file exists |
| THESIS ↔ filesystem | **2 references point outside the package** (TR-4) |
| Invariant numbering | **5 gaps** (TR-2) |
| RD-1..RD-4 carry-forward | RD-1 ✅ · RD-4 ✅ · **RD-2 ✗** · **RD-3 ✗** (TR-3) |
| `.gitignore` vs evidence requirements | **Conflict** (TR-1) |
| Licence vs GitHub platform terms | **Conflict if made public** (TR-7) |

---

## 2. Where v1.1 corrects me — conceded without qualification

### 2.1 `MEASURED-REPORTED` is the right label. Mine was wrong.

I labelled M-1 through M-5 as `MEASURED` because I read the tool output in the session transcript. From a **repository** standpoint that is not what the label means: without the raw capture committed, no reader can verify the claim from the repository. The three-tier scheme — `MEASURED` / `MEASURED-REPORTED` / `DERIVED-FROM-REPORTED` — plus the explicit promotion rule is a better instrument than mine, and the closing line of `EVIDENCE_REGISTER.md` states the reason exactly right:

> It prevents a later reader from confusing "a measurement was reported" with "this repository proves the measurement."

**The remedy is small and available now.** Both artifacts already exist on the target machine: `D:\Sovereign Distillery\runs\hardware_profile.json` and `D:\Sovereign Distillery\registry\teachers.json`. Committing them, plus the two tools, promotes M-1 through M-5 to `MEASURED` and satisfies evidence-register items 1, 2, and 3 in a single commit — **once TR-1 is fixed, because at present `.gitignore` blocks it.**

### 2.2 T1–T4 as an execution overlay, not a replacement queue — I risked scope drift

My Part C.5 said T4 was "not runnable on this hardware, full stop," and my Part J recommended adopting tiering "as the operative queue, **replacing** 'process the whole library'."

That framing risked silently amputating OBJ-3, which is an operator requirement, on the basis of an estimate. v1.1's framing is correct: **the canonical queue remains the full eligible library in ascending order; tiers schedule what executes under the present compute envelope; deferred is not removed.** `DEFERRED_COMPUTE` as a disposition that preserves queue position is the right mechanism.

This is a correction of me and it is right. A hardware measurement is a scheduling input, not a licence to redefine the objective.

### 2.3 EF-1 — I made an unsupported inference

My report stated that because every teacher is larger than the student, "the capability delta against the seed will be large and positive from the very first teacher."

v1.1 strikes this: *"This size relation does not itself prove a positive capability delta... capability delta remains an empirical result of differential evaluation."*

Correct. Parameter count does not establish capability superiority on any given axis — a well-trained 3B can exceed an 8B on specific tasks. I flagged exactly this class of inference in others and then committed it. Conceded.

### 2.4 EF-3 — "generation is the binding constraint" was premature

v1.1 restates it as *"generation is the projected scaling bottleneck; training viability is the current hard gate."* More precise. Generation cannot be called the binding constraint while training is entirely unproven. Conceded.

---

## 3. Findings

### TR-1 — BLOCKING — `.gitignore` excludes `runs/`, which is where the repository's own required evidence artifacts land

`EVIDENCE_REGISTER.md` lists the artifacts required to promote claims from `MEASURED-REPORTED` to `MEASURED`:

> 1. Raw F.0 hardware/training-stack capture with timestamps and tool versions.
> 4. F.1 generation-throughput capture with model, prompt/context size, token budget, offload state, and tokens/sec.

Both are produced into `runs/` — `runs/hardware_profile.json` and `runs/generation_throughput.json`. `.gitignore` contains:

```
runs/
```

**The repository's stated path out of `MEASURED-REPORTED` is blocked by its own ignore file.** The exclusion is otherwise correct — `runs/` will accumulate large logs and intermediate state that must never be committed. The fix is to carve out the small JSON profiles:

```gitignore
runs/
!runs/
!runs/*.json          # hardware + throughput profiles are evidence, not artifacts
runs/**/*.log
runs/**/*.jsonl
```

A drop-in corrected `.gitignore` is supplied with this review.

**Severity rationale:** this is not cosmetic. The single most valuable property of the package is its honest evidence posture, and the mechanism for discharging that debt is disabled. It would be discovered only when someone tried to commit the evidence and found it silently ignored.

### TR-2 — MAJOR REGRESSION — Five invariants dropped; numbering preserves the gaps

The invariant table defines INV-1, 2, 3, 3b, 4, 5, 6, 7, 11, 12, 14. Missing: **INV-8, INV-9, INV-10, INV-13, INV-15**.

The thesis cites invariants by number in prose ("operable standalone (INV-14)", "(INV-7)"), so the numbering is live. A reader who encounters INV-14 will reasonably assume 8 through 13 are defined somewhere. They are not.

What was lost, from the accepted integrated baseline:

| ID | Invariant | Why its absence matters |
|---|---|---|
| **INV-8** | Eligible teachers are examined smallest-to-largest | **This is OBJ-3 — the operator requirement v1.1 was specifically written to protect.** Dropping it from the invariant table while §6 argues for preserving it is self-undermining. |
| **INV-9** | A teacher with no useful capability delta may be skipped | Asserted in §4.4 step 5 but not enshrined |
| **INV-10** | Teacher ordering does not require single-teacher-only training data; replay is allowed | The ordering/mix separation is named in the **thesis statement itself** ("separate teacher ordering from training-mix composition") and is not an invariant |
| **INV-13** | Cross-family weight transfer is never assumed | Present in §4.6 as a table row; absent as an invariant |
| **INV-15** | **Human operator retains final canonical promotion authority** | **The operator's own authority invariant.** Present in the header, §4.1, and `DECISION_REGISTER.md` — absent from the one table a reader will treat as the normative list. |

All five survive as prose or as standing decisions, so nothing is *contradicted*. But the invariant table is the normative artifact — it is what an implementer will encode — and it is now incomplete in a way its own numbering advertises.

**Fix:** restore the five rows. Zero design change; it is a transcription loss.

### TR-3 — MAJOR REGRESSION — RD-2 and RD-3 were lost in consolidation

Two of the four residual defects accepted two rounds ago did not survive into v1.1. Verified by search: **zero occurrences of "criticality" anywhere in the package.**

**RD-3 — "no critical regression" is unimplementable again.** The operator's own canonical promotion rule has six conditions, of which the fourth is *"No critical regression."* RD-3's fix was a per-capability criticality tag (`CRITICAL` / `STANDARD` / `EXPERIMENTAL`) making that condition machine-checkable. v1.1's §4.5 dual-gate specifies M, T, and D only, and §4.3's Capability Ledger lists *"current score, historical best, governed floor, source, trend"* — no criticality field.

**Consequence:** condition 4 of the accepted rule has no data to evaluate against. It reverts to an undefined adjective. The distinction matters most where it is easiest to lose: a `STANDARD` capability drifting within tolerance is acceptable erosion; a `CRITICAL` one drifting the same amount is not, and only a declared tag can tell them apart.

**RD-2 — the remediation state still has no legal exit.** "Remediation" appears twice, both in §7.3's retry-budget policy. The promotion gate in §4.5 still requires a target-capability improvement. A `REMEDIATION` candidate exists to **restore** a capability toward its governed floor, not to gain a new one — so it remains unpromotable under the rule as written, which is precisely the defect accepted and marked resolved earlier.

**Fix for both:** add `criticality` to the Capability Ledger fields in §4.3 and to the gate in §4.5; add one line to §4.5 stating that a remediation candidate satisfies the improvement condition by measured restoration toward the governed floor rather than by new gain.

### TR-4 — MODERATE — Two THESIS path references point outside the package

`THESIS.md` §2.1 and §2.2 state *"Source: `tools/d1_characterize.py`"* and *"Source: `tools/d2_registry.py`"*. Neither exists in the package.

This is honest in intent — §1.3 and the evidence register both say the scripts are absent — but the "Source:" line reads as a repository path and will resolve to nothing.

`SHIP_CHECKLIST.md` catches this for README (*"Confirm README.md points to real files/directories"*) but not for THESIS.

**Fix, and it is the good one:** `.gitignore` does **not** exclude `tools/`. Commit the two scripts. That simultaneously repairs the references and discharges evidence-register item 3 (*"the exact script(s) used to produce M-1 through M-3"*). Both files are at `D:\Sovereign Distillery\tools\`.

### TR-5 — MODERATE — Phase namespace mixing, in a repository that built a crosswalk to prevent exactly this

§5.2: *"Seed acquisition is a prerequisite for **Phase D3 / F.3**."*

Two numbering schemes coexist — `D0`–`D15` from the integrated report and `F.0`–`F.11` from the design plan. §10 uses `F.*` exclusively; §5.2 uses both.

This is the OQ-collision problem recurring in a new namespace, in a package that went to the trouble of writing `OQ_CROSSWALK.md` to solve it. **Fix:** adopt `F.*` canonically, add a two-column D→F mapping to the crosswalk, and remove the dual reference in §5.2.

### TR-6 — MODERATE — A changelog-claimed fix was not applied to §3

`CHANGELOG.md` states the correction:

> T1–T4 is now explicitly a hardware-dependent execution overlay rather than a replacement queue.

§6 applies it: T3/T4 *"Remain in canonical queue; defer until compute, corpus budget, or throughput changes."*

§3's EF-3 table did not get it. Its Verdict column still reads T3 = *"Not on this hardware at this corpus size"* and T4 = *"Not on this hardware"* — the v1.0 wording, with no mention of deferral or of queue retention.

Since §3 is the findings section a reader reaches first, the uncorrected framing is the one most likely to be absorbed. **Fix:** align the §3 verdict column with §6.

### TR-7 — MODERATE — The licence conflicts with a public GitHub repository

`LICENSE` states: *"All rights reserved... No license to use, copy, modify, or distribute is granted until the operator explicitly publishes a license decision."*

This is coherent and correct for a **private** repository. It is not coherent for a public one. GitHub's documentation is explicit that publishing a repository grants other users platform-level rights irrespective of licence:

> "other users of GitHub.com have the right to view and fork your repository"

So a public repository under this licence asserts a restriction the platform's own terms already override for viewing and forking. The package is titled "github ready" and `README.md` says to revisit LICENSE before making the repository public — but the checklist does not state the consequence.

**Fix — one line in `SHIP_CHECKLIST.md`:**

> **Keep this repository PRIVATE while `LICENSE` remains all-rights-reserved.** Publishing it grants view-and-fork rights under GitHub's terms regardless of the licence text. Resolve OQ-007 (distribution intent) before changing visibility.

This is not a legal opinion and I am not a lawyer; it is a platform-terms mismatch worth surfacing before the visibility toggle rather than after.

### TR-8 — MINOR — Committing `registry/teachers.json` discloses the machine's inventory and paths

The registry artifact required by evidence item 2 contains the full local model list, blob paths, and directory structure. `.gitignore` does not exclude `registry/`, which is correct — the artifact is needed.

Under a private repository this is fine. If OQ-007 resolves toward publication, it becomes an information-disclosure decision that should be made deliberately. **Fix:** add to `SHIP_CHECKLIST.md` — *"Before making public: review `registry/teachers.json` for local paths and inventory disclosure; consider a path-redacted public variant."*

### TR-9 — MINOR — The link check is manual; make it permanent

`SHIP_CHECKLIST.md` says *"Run a Markdown link check if available."* I ran one: **9 internal links, all resolve, zero broken.** The repository is clean today.

A ~20-line GitHub Actions workflow makes that permanent and also catches the TR-4 class of defect (references to files that do not exist). A drop-in workflow is supplied with this review.

---

## 4. Ship verdict

**Do not commit as-is.** Three fixes are required first; four are recommended.

| # | Fix | Effort | Blocking |
|---|---|---|---|
| 1 | `.gitignore` — carve out `runs/*.json` | 4 lines | **Yes** (TR-1) |
| 2 | Restore INV-8, 9, 10, 13, 15 | 5 table rows | **Yes** (TR-2) |
| 3 | Restore RD-2 (remediation route) and RD-3 (criticality tag) | ~4 lines across §4.3, §4.5 | **Yes** (TR-3) |
| 4 | Commit `tools/d1_characterize.py` and `tools/d2_registry.py` | copy 2 files | Recommended (TR-4) — also discharges evidence item 3 |
| 5 | Align §3 verdict column with §6 | 2 cells | Recommended (TR-6) |
| 6 | Adopt `F.*` phase numbering; extend crosswalk | 2 lines | Recommended (TR-5) |
| 7 | Private-repo and disclosure notes in SHIP_CHECKLIST | 2 lines | Recommended (TR-7, TR-8) |
| 8 | Add link-check workflow | 1 file | Optional (TR-9) |

**After fixes 1 and 4, a second commit can promote M-1 through M-5 from `MEASURED-REPORTED` to `MEASURED`** by adding `runs/hardware_profile.json` and `registry/teachers.json`. That closes evidence items 1, 2, and 3 and is the single highest-value change available to the repository — it converts the package's honest admission of reproducibility debt into discharged debt.

---

## 5. What the package gets right, and it is most of it

The evidence-label scheme is stricter than mine and correctly so. The canonical-queue-versus-execution-overlay distinction repairs a real scope risk I introduced. The falsification conditions in §12 are unusual in a document of this kind and they are the mark of an honest one — a thesis that names the observations that would refute it is doing engineering rather than advocacy. The stop/stall/escalation policy in §7.3 is complete. The `.gitignore` correctly excludes weights, corpora, checkpoints, and secrets. The changelog distinguishes integration from correction from addition, and the audit-correction entry — removing the implication that raw captures were present when they were not — is exactly the behaviour that makes a baseline trustworthy.

The five research questions in §1.2 are the strongest single addition. They convert a design document into something testable, and RQ-2 (retention) and RQ-5 (reproducibility) are the two the project is most likely to fail at, which is the right place to point.

**One structural observation to carry forward.** The package's stated limitation — that raw artifacts are absent — is true of the *package* and not of the *project*. The measurements exist. The tools exist. Both are sitting in `D:\Sovereign Distillery\`. The gap between "reported" and "reproducible" is currently one `git add` wide, and TR-1 is the only thing standing in it.

---

*This is a review. It is not an approval. Acceptance belongs to the operator.*
