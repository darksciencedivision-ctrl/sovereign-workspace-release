# SOVEREIGN RESEARCH WORKSPACE
## Full System Status Report

| | |
|---|---|
| **Document** | Programme Status Report v1.0 |
| **Date** | 20 August 2026 |
| **Scope** | The entire workspace: Sovereign Distillery, Grounded Distillery, shared infrastructure, physical reality, evidence state, and blockers |
| **Author role** | Research Validator / Analyst |
| **Method** | Direct inspection of both repositories on disk, independent test execution, and reading of committed evidence. Not a synthesis of prior reports. |
| **Authority** | The operator owns objectives, scope, promotions, and acceptance. This reports and recommends. It does not decide. |

**Evidence labels used throughout:** `MEASURED` (observed on the target machine by a named tool) · `DERIVED` (computed from measured values) · `ESTIMATE` (modelled) · `INFERENCE` (reviewer's reading) · `UNVERIFIED` (asserted, no evidence located) · `ABSENT` (checked for, not found)

---

# PART A — WHERE WE ARE

## A.1 One paragraph

The workspace now contains **two model-development programmes running at very different maturities under one name.** Grounded Distillery has a merged repository, 64 tracked files, 27 passing tests, a live-partial telemetry gate, and disciplined fail-closed source admission. Sovereign Distillery — the parent research programme — has twenty-three documents, three characterization tools, one hardware profile, one teacher registry, and **zero executed engineering.** The repository named `Sovereign-Distillery` contains Grounded's work and none of Sovereign's. Both programmes have now been audited, both audits were accepted, and the next technical gate for both is blocked on the same unanswered question: **which GPU is actually going to train anything.**

## A.2 The five things that define current state

| # | Statement | Label |
|---|---|---|
| 1 | Grounded is implemented, merged, and gated. Sovereign is specified and unstarted. | `MEASURED` |
| 2 | The joint repository contains no Sovereign work product (GR-1, accepted). | `MEASURED` |
| 3 | **The two programmes are planned against two different, mutually unreconciled GPUs.** Sovereign against a measured RTX 5060 Ti (8 GiB, 5.26 free). Grounded against a 32 GiB gfx906 that appears nowhere in this workspace except a test fixture. | `MEASURED` + `ABSENT` |
| 4 | No training stack exists on the measured machine. PyTorch absent. The `sm_120` 4-bit path has never been tested. | `MEASURED` |
| 5 | Fail-closed discipline has held everywhere it was tested. No model trained, no model promoted, no source reclassified, no gate downgraded to a warning. | `MEASURED` |

## A.3 The single most important open question

**Does the 32 GiB gfx906 trainer exist on this machine?**

It gates both programmes and it is the cheapest unanswered question in the workspace. See **SR-1** and **SR-2**.

---

# PART B — SYSTEM MAP

## B.1 Four layers, as they actually exist today

```
SOVEREIGN RESEARCH WORKSPACE
│
├─ Sovereign ................. orchestration / memory / routing        [RUNNING, unversioned]
├─ Debate Table .............. adversarial evaluation                  [UNVERIFIED — never inspected]
├─ Multi-Model App ........... heterogeneous execution                 [UNVERIFIED — never inspected]
│
└─ MODEL DEVELOPMENT
   ├─ Sovereign Distillery ... capability accumulation, many teachers  [SPECIFIED, NOT STARTED]
   └─ Grounded Distillery .... workload specialization, one workload   [IMPLEMENTED, MERGED, GATED]
```

`OQ-009` remains open and unchanged since first raised: **no sibling repository has ever been inspected.** Every statement in either thesis about Debate Table or Multi-Model App integration is an `ASSUMPTION`. Paths were offered in this session and never supplied.

## B.2 Three physical locations, one name

| Path | Contents | Git | Role |
|---|---|---|---|
| `D:\Sovereign Distillery` | 23 files — Sovereign research corpus, 3 tools, hardware profile, teacher registry | **none** | Sovereign's actual work product |
| `D:\Sovereign-Grounded-Distillery` | 64 tracked files — Grounded implementation + docs | `main @ 44f69077`, clean | The "canonical joint repository" |
| *(separate)* Sovereign runtime | live product, **dirty working tree**, deliberately untouched | dirty | Source of G0 telemetry; target of the instrumentation checksum guard |

**This is GR-1 stated as geography.** The research corpus has no version control. The repository named after it holds another project's code. The runtime that produces the evidence is uncommitted.

---

# PART C — PHYSICAL REALITY

## C.1 Measured machine

Source: `runs/hardware_profile.json`, `tools/d1_characterize.py`, 19 Aug 2026.

| Property | Value | Label |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti | `MEASURED` |
| VRAM | 8151 MiB total · **5383 MiB free** · 2509 MiB in use by processes | `MEASURED` |
| Compute capability | 12.0 → `sm_120` (Blackwell) | `MEASURED` |
| Driver | 610.74 | `MEASURED` |
| PCIe link | **gen 4 × 8** (not ×16) | `MEASURED` |
| **System RAM** | **63.7 GiB** | `MEASURED` — *newly read from the profile; previously recorded as a gap* |
| Disk `D:` | 1862 GiB total · 1457 used · **404.85 GiB free** | `MEASURED` |
| Disk `C:` | 1907 GiB total · **641.85 GiB free** | `MEASURED` |
| PyTorch / bitsandbytes / psutil | **absent** | `MEASURED` |
| Second GPU (AMD / ROCm) | **not probed** — `d1_characterize.py` queries `nvidia-smi` only | `ABSENT (untested)` |

### C.1.1 What the newly-read values change

**System RAM 63.7 GiB — resolves R-14 and sharpens the teacher tiering.**

Previously R-14 read: *"System RAM insufficient for offloaded teachers — HIGH, likelihood unknown, RAM never captured."* It was captured; the WMI fallback in the tool worked and the value was in the JSON.

| Teacher class | On-disk | Fits in 63.7 GiB RAM? | Revised verdict |
|---|---:|---|---|
| ≤ 32B (`qwen3:32b`, 18.8 GiB) | 18.8 | Comfortably | Slow, not impossible |
| 70B class (`llama3.3:70b`, `deepseek-r1:70b`) | 39.6 | Yes, with headroom | T4 for **throughput**, not for capacity |
| `llama4:scout` / `gpt-oss:120b` | 60.9–62.8 | Marginal — leaves ~1–3 GiB for the OS | Thrash risk |
| **`mistral-medium-3.5`** | **74.73** | **No — exceeds total system RAM** | **Cannot be loaded at all on this machine** |

So T4 splits into two genuinely different categories: *too slow to schedule* (70B–120B) and *physically unloadable* (128B). The largest and strongest model in the library cannot be run at all. That is a cleaner finding than "168 estimated days."

**Disk 404.85 GiB free — quantifies R-10.**

The 768.4 GiB library already sits on `D:`, which is **78% full**. Everything the project still needs — corpora, checkpoints, deployment artifacts, a second student lineage, and Grounded's shard store — must fit in 405 GiB. The T3/T4 retention decision (DR-5) is no longer abstract: roughly 470 GiB of that disk is held by teachers that cannot currently be used, against 405 GiB of remaining space.

## C.2 The hardware nobody has verified

### SR-1 — NEW — `gfx906` exists in this workspace only as a test fixture

Grounded Thesis §19: *"The current training target is a 32 GB gfx906-class GPU in the Vega 20 / MI50 family… torch 2.7 / ROCm 6.3 / fp16 / PEFT / TRL / LoRA."* §20 sets the student at 4B vs 8B. §21 specifies a full trainer-card lock sequence. HG-3 is *"real 4B/8B student architecture smoke on the pinned gfx906 trainer"* and is the declared next gate.

**I searched the entire repository for any trace of that hardware.** Every occurrence of `gfx906`, `ROCm`, `MI50`, `Vega`, or `hip`:

```
tests/test_ops_and_train.py:57:  probe = lambda: {"gpu_identity": "gfx906", "free_vram_mib": 32000, ...}
tests/test_ops_and_train.py:58:  TrainerCardLock(..., expected_gpu="gfx906", minimum_free_vram_mib=30000, probe=probe, ...)
tests/test_ops_and_train.py:63:  TrainerCardLock(..., probe=bad_probe, ...)
```

**Three lines, all in one test file, all lambdas.**

`TrainerCardLock` takes `probe` as an injected callable and never implements one. There is no `rocm-smi` call, no `hipInfo` call, no GPU discovery of any kind in production code. The lock contract — exclusivity, drain, identity check, VRAM check, conflicting-process check, pre/post snapshots — is **implemented correctly and completely**, and it has **nothing to probe with**.

**Consequences:**

1. **HG-3 has an unstated software prerequisite.** §21 steps 3 and 4 ("verify GPU identity", "verify free VRAM") cannot execute. A real probe must be written before the declared next gate can run at all.
2. **The 32 GiB / 30000 MiB thresholds are fixture values**, not measured device properties.
3. **No evidence in this workspace establishes that the card exists.** It is not disproved either — `d1_characterize.py` only queries `nvidia-smi`, which cannot see an AMD GPU. This is `ABSENT (untested)`, not `REFUTED`.

`INFERENCE`, weak: the RTX 5060 Ti reports **PCIe gen 4 ×8** rather than ×16. On desktop boards a halved link commonly indicates a second populated slot. That is consistent with a second card and proves nothing.

### SR-2 — NEW — The two programmes are planned against two different, unreconciled machines

| | Sovereign Distillery | Grounded Distillery |
|---|---|---|
| Target GPU | RTX 5060 Ti, 8 GiB, `sm_120` | gfx906 / MI50, 32 GiB |
| Evidence | **`MEASURED`** | **`ABSENT (untested)`** |
| Stack | CUDA + bitsandbytes 4-bit | ROCm 6.3 + torch 2.7 fp16 |
| Student | 1B–3B, QLoRA 4-bit | 4B vs 8B, fp16 LoRA |
| Teachers | 39 local models, 768 GiB | one designated synthesis teacher |
| Trainability of its own plan | Unproven — no PyTorch | Unproven — no probe, no smoke |

**Neither programme's hardware assumption has ever been checked against the other's.** They were written independently and merged organisationally without anyone asking whether both machines exist.

The question resolves in one of three ways, and each rewrites a different programme:

| If | Then |
|---|---|
| **The gfx906 exists and is available** | Sovereign's `OQ-006` (compute envelope) is answered far more favourably than my design plan assumed. 32 GiB reopens 7B–14B students, changes the T1–T4 tiering, and partially supersedes ADR-0003. **My tiering is too pessimistic and should be recomputed.** |
| **It exists but is committed to Grounded** | Both plans stand; the workspace has two trainers and a scheduling problem rather than a capability problem. Trainer-card locking becomes a cross-programme concern, not a Grounded-internal one. |
| **It does not exist** | Grounded §19–§21, §20's 4B/8B comparison, HG-3, G3 and G4 all target absent hardware. Grounded would have to train on 5.26 GiB, which cannot host a 4B or 8B fp16 LoRA. **Grounded's entire training plan would need re-specification.** |

**Cost to answer: one command.** `rocm-smi`, or `hipInfo`, or Windows Device Manager. This is the cheapest high-value measurement remaining in the workspace and it gates the declared next gate of both programmes.

---

# PART D — PROGRAMME 1: SOVEREIGN DISTILLERY

## D.1 Status: SPECIFIED, NOT STARTED

Twenty-three files. Zero executed engineering.

| Asset | State |
|---|---|
| Validation report, design plan, canonical spec, 4 ADRs, decision ledger, 3 reviews | Complete |
| `tools/d1_characterize.py`, `d2_registry.py`, `d3_throughput.py` | Written; **d1 and d2 run once; d3 never run** |
| `runs/hardware_profile.json` | Captured — the only executed evidence the programme owns |
| `registry/teachers.json` / `.md` | Captured — 43 entries, ordering known-defective (TD-1), **v2 tool not yet re-run** |
| Evaluation suite | **Does not exist** |
| Seed (`SOV-SEED`) | **Not acquired** — no local candidate exists (EF-2) |
| Corpora, checkpoints, lineage | **None** |
| Version control | **None** |

## D.2 Phase state

| Phase | State | Blocker |
|---|---|---|
| **F.0** Environment remediation | **NOT STARTED** | PyTorch not installed. `sm_120` + bitsandbytes 4-bit path never tested. Critical path. |
| **F.1** Generation throughput | **NOT STARTED** | Tool written and shipped; needs only Ollama; **runnable today** |
| **F.2** Registry v2 + licence audit | **PARTIAL** | v2 tool shipped, not re-run. Licence audit not begun. |
| **F.3** Seed acquisition | **BLOCKED** | DR-2 undecided; nothing local qualifies |
| **F.4** Evaluation suite | **BLOCKED on F.0** | Still the highest-value unbuilt artifact in the programme |
| **F.5** Provenance / lineage skeleton | **NOT STARTED** | Cannot be retrofitted; runnable now (pure schema + code) |
| **F.6 → F.15** | NOT REACHED | — |

## D.3 Open questions

| ID | Question | State |
|---|---|---|
| OQ-001 | Seed path | Bootstrap→native resolved in principle; **exact seed still unacquired** |
| OQ-002 | Teacher inventory | **CLOSED** — 43 entries, 39 teachers, 768.4 GiB |
| OQ-003 | v1 acceptance | **CLOSED** — Route A / Route B |
| OQ-004 | M / T / D | Open — requires measured variance, requires F.4 |
| OQ-005 | Mixing ratios / non-synthetic floor | Open |
| OQ-006 | **Compute envelope** | Open — **and SR-1/SR-2 make it the live question, not a future one** |
| OQ-007 | Distribution intent | Open — gates licence-audit severity for *both* programmes |
| OQ-008 | Native architecture timing | Open |
| OQ-009 | Sibling interface contracts | **Open, unchanged, never inspected** |
| OQ-010 | Smallest-to-largest rationale | RESOLVED → HYP-1 |

## D.4 The uncomfortable observation

**Sovereign is the parent research programme and it is the less advanced of the two.** Grounded has a merged repository, an implemented shared-infrastructure core, 27 passing tests, and a live-partial telemetry gate. Sovereign has documents.

This is not a criticism of the documents — the specification work is what made the Grounded audit possible, and the shared infrastructure Grounded implemented is largely *Sovereign's design* (immutable lineage, per-example provenance, transitive exclusion, dual-gate M/T/D, human promotion). Sovereign's ideas are running in Grounded's code.

But it does mean the phrase "Grounded is one operational branch of a larger workspace" describes an intention rather than a state. Today the branch is the trunk.

---

# PART E — PROGRAMME 2: GROUNDED DISTILLERY

## E.1 Status: IMPLEMENTED, MERGED, PARTIALLY GATED

Repository `ryguy-pixel/Sovereign-Distillery`, `main @ 44f69077`, clean, 64 tracked files.

**Independently verified by me:** working tree clean (the 60 "modified" files were CRLF-vs-LF through a Linux mount); **27/27 tests pass on Linux/Python 3.11** — a platform the build never claimed; no LICENSE file; no weights or secrets; all four D-9 candidates `UNKNOWN`.

## E.2 Lineage

```
f1904399  baseline — three Grounded documents          [GR-1: no Sovereign content]
a332e688  RC3 greenfield implementation                [preserved as bundle]
c3594cfc  RC3 integrated into joint repository
b0b7f389  live G0 + pre-PR
7b3eb96a  completion record
23523bde  main advanced during PR window
864419de  reconciliation merge
39aa8890  PR #1 merged
44f69077  post-merge evidence  ← current
```

## E.3 Hard-gate state, as revised by the operator

| Gate | State | Note |
|---|---|---|
| **HG-0** Real telemetry | **PASS_PROVISIONAL / EVIDENCE_INTEGRITY_REPAIR_REQUIRED** | Correct downgrade. 4 sessions / 5 turns; event logs gitignored; one generation destroyed; label origin ambiguous |
| **HG-1** Source admission | **PASS (enforcement)** · decisions pending | Software correct; all four sources `UNKNOWN` |
| **HG-2** Transitive exclusion | **PASS_SYNTHETIC** | Closure algorithm general; acceptance harness fixture-bound (GR-8) |
| **HG-3** Student architecture smoke | **BLOCKED** | Blocked by GR-2/GR-3 by directive — **and by SR-1, which is new** |
| **HG-4** Preference-pair audit | BLOCKED | ~50 pairs, human audit |
| **HG-5** Frozen evaluation contract | NOT REACHED | **GR-2 must land or this gate is not credible when it arrives** |
| **HG-6** Controlled model effect | NOT REACHED | — |
| **HG-7** Bundle gate | NOT REACHED | — |
| **HG-8** Human promotion | NOT REACHED | **GR-3 must land or this path is not trustworthy** |

## E.4 Audit disposition — all accepted

| ID | Finding | Disposition |
|---|---|---|
| GR-1 | Repository contains no Sovereign work product | Accepted — structural; operator decision required |
| GR-2 | `declared_at` non-empty ≠ predeclared | Accepted — fix before HG-3 |
| GR-3 | Atomic ≠ durable; unguarded rollback | Accepted — fix before HG-3 |
| GR-4 | One-sided vs two-sided confidence ambiguity | Accepted |
| GR-5 | HG-0 evidence unauditable as configured | Accepted |
| GR-6 | `label_origin` unrecorded | Accepted |
| GR-7 | Checksums pinned to dirty unversioned tree | Accepted |
| GR-8/9/10 | E7 fixture-bound · store↔gate seam · no `.gitattributes` | Accepted — tracked for G2 / pre-CI |

## E.5 What is genuinely strong

The source-admission registry remains the best artifact in either programme. Weight licence separated from output-use authority, blob hashes recovered, every candidate still `UNKNOWN` because permissive weights do not answer the question being asked. `gate/historical.py` exceeds its own specification. `exclusion` is a correct closure. `ShadowPlanner` enforces non-execution structurally. **D-9 held fail-closed across four authorization directives under visible pressure to advance.**

---

# PART F — THE RECONCILIATION PROBLEM

## F.1 SR-3 — NEW — Identifier namespaces are colliding again, inside Grounded

The workspace lost traceability once to duplicate `OQ-` identifiers and built a crosswalk to fix it. The same failure is forming in a new namespace.

**`D` currently means three different things in the Grounded thesis:**

| Usage | Meaning | Where |
|---|---|---|
| `D` | Drift floor — maximum regression vs historical best | §26, §32, promotion gate |
| `D-1 … D-13` | Decision register entries (D-9 = source admission) | Reports, §41 |
| `Band D` | Advisory evaluation band | §22, §7.1 |

A sentence such as *"D-9 remains UNKNOWN and D was not breached, per Band D advisory"* is valid in the current vocabulary. In a document whose entire safety argument rests on M/T/D being unambiguous, that is a hazard worth ten minutes.

**Cross-programme collisions:** Sovereign `E-5…E-12` are evidence IDs; Grounded `E1…E10` are experiments. Sovereign `R-1…R-15` are risks; Grounded `RQ1…RQ10` are research questions.

**Recommended:** extend `docs/OQ_CROSSWALK.md` into a workspace-wide identifier register before the Sovereign canon import (which will bring `INV-`, `OQ-`, `F.`, `ADR-`, `HYP-`, `EF-`, `RD-`, `TR-`, `GR-` into the same tree).

## F.2 What "treaty verified" would actually require

The operator's target structure is right. Making it *checkable* rather than declared needs three things the workspace does not have:

1. **Sovereign's canonical set in the repository** — invariants INV-1…INV-15, OQ register, decision ledger, teacher registry summary, hardware profile summary, ADRs.
2. **A machine-checkable contract test.** Not prose. Something in the shape of: for every invariant Sovereign declares as shared, assert the shared module honours it — e.g. INV-1 (never overwrite) → assert no code path writes to a promoted checkpoint path; INV-5 (quantized artifact never a parent) → assert bundle lineage rejects a deployment artifact as parent; INV-15 (human promotion) → already enforced in `promote()`, so assert it.
3. **A named owner per shared module.** Today `validators/`, `exclusion/`, `gate/`, `ops/` are declared shared and were written entirely by one sibling.

Until (1) and (2) exist, `TREATY_VERIFIED` should read `NOT_EVALUABLE`, not `PASS`.

---

# PART G — CONSOLIDATED BLOCKER BOARD

| # | Blocker | Blocks | Cost to clear | Owner |
|---|---|---|---|---|
| **B-1** | **Does the gfx906 exist?** (SR-1/SR-2) | Grounded HG-3, G3, G4 · Sovereign OQ-006, ADR-0003, tiering | **One command** | Operator |
| **B-2** | No production GPU probe for `TrainerCardLock` (SR-1) | Grounded HG-3 | Small module | Builder |
| **B-3** | GR-2 — predeclaration not enforced | Grounded HG-3 → HG-5 | ~5 lines + test | Builder |
| **B-4** | GR-3 — durability + rollback state | Grounded HG-3 → HG-8 | ~10 lines + test | Builder |
| **B-5** | No PyTorch; `sm_120` 4-bit untested | **Sovereign F.0 and everything after** | Hours | Builder |
| **B-6** | GR-5/6/7 — HG-0 evidence integrity | HG-0 → PASS | Small | Builder |
| **B-7** | GR-1 — Sovereign canon not in repository | `TREATY_VERIFIED` | One commit + decision | **Operator** |
| **B-8** | No evaluation suite (either programme) | Sovereign F.4 · Grounded HG-5 | Weeks | Builder |
| **B-9** | Seed not acquired (DR-2) | Sovereign F.3 → F.7 | Operator + hours | Operator |
| **B-10** | Sibling repos never inspected (OQ-009) | All integration claims in both theses | Minutes | **Operator** |
| **B-11** | Licence audit not begun (OQ-007 gates severity) | Sovereign F.2 · Grounded D-9 | Manual | Operator |
| **B-12** | Disk: 405 GiB free against a 768 GiB library | Corpora, checkpoints, both programmes | Decision (DR-5) | Operator |

**B-1 and B-10 are the two cheapest, and both are operator-side.** Between them they would resolve or reshape six of the remaining ten.

---

# PART H — EVIDENCE LEDGER

| Claim | Label | Repository-verifiable? |
|---|---|---|
| RTX 5060 Ti, 8151 MiB, 5383 free, `sm_120`, driver 610.74 | `MEASURED` | Yes — `runs/hardware_profile.json` exists (uncommitted; no VCS) |
| System RAM 63.7 GiB · `D:` 404.85 GiB free | `MEASURED` | Same |
| PyTorch / bitsandbytes absent | `MEASURED` | Same |
| 43 registry entries, 39 teachers, 768.4 GiB | `MEASURED` | `registry/teachers.json` — ordering defective, v2 not re-run |
| Grounded tree clean at `44f69077` | `MEASURED` | Yes — verified by me |
| Grounded 27/27 tests | `MEASURED` | Yes — **run by me on Linux/Py3.11** |
| All four D-9 sources `UNKNOWN` | `MEASURED` | Yes |
| HG-0 live acceptance | `MEASURED-REPORTED` | **No** — events gitignored, one generation destroyed |
| Instrumentation checksum baseline | `MEASURED-REPORTED` | **No** — pinned to a dirty unversioned tree |
| gfx906 32 GiB trainer | **`ABSENT (untested)`** | **No** — three test lambdas only |
| Generation throughput / T1–T4 tiers | `ESTIMATE` | No — `d3_throughput.py` never run |
| QLoRA VRAM by model size | `ESTIMATE` | No — secondary source |
| Treaty preserved | **`NOT_EVALUABLE`** | No — Sovereign canon absent |
| Debate Table / Multi-Model interfaces | `UNVERIFIED` | No — never inspected |

**Two programmes, one hardware profile, one model registry, one merged codebase, and not a single trained parameter.** That is an accurate and unembarrassing description of a pre-implementation workspace that has been honest about its gates.

---

# PART I — CONSOLIDATED RISK REGISTER

| ID | Risk | Sev | Change since last | Status |
|---|---|---|---|---|
| **SR-2** | Two programmes, two unreconciled GPUs | **CRITICAL** | **NEW** | Open — B-1 |
| **SR-1** | No production GPU probe; HG-3 unrunnable | **HIGH** | **NEW** | Open — B-2 |
| R-8 | `sm_120` / bitsandbytes untested | **CRITICAL** | unchanged | Open — B-5 |
| GR-2 | Predeclaration unenforced | HIGH | accepted | Scheduled |
| GR-3 | Router durability / rollback state | HIGH | accepted | Scheduled |
| R-14 | System RAM insufficient for offload | **DOWNGRADED to LOW–MEDIUM** | **63.7 GiB measured** | Partially closed — only the 128B model exceeds it |
| R-10 | Storage exhaustion | **HIGH** | **quantified: 405 GiB free vs 768 GiB library** | Open — DR-5 |
| R-3 | Synthetic-data collapse | HIGH | unchanged | Controls designed, unbuilt |
| R-4 | Student capacity ceiling | HIGH | **conditional on B-1** | Open |
| R-5 | Licence contamination | HIGH | unchanged | Fail-closed holding |
| R-6 | Gate ineffective / promotion on noise | HIGH | **GR-2 makes this concrete** | Scheduled |
| R-9 | Generation wall-clock | HIGH | **estimates unreplaced — d3 never run** | Open — F.1 |
| **SR-3** | Identifier namespace collision (`D` ×3) | MEDIUM | **NEW** | Open |
| R-13 | Same-base teachers correlate | MEDIUM | unchanged | Open |
| R-11 | Scope drift | **LOW** | audits + gates holding | Controlled |

---

# PART J — DECISIONS OUTSTANDING

| ID | Decision | Recommendation |
|---|---|---|
| **NEW-1** | **Confirm or refute the gfx906 trainer** | Run `rocm-smi` / check Device Manager. Before anything else. |
| **GR-1** | Import Sovereign canon into the joint repo, **or** rename/split so the name matches the contents | Import. Renaming concedes the joint model; the shared infrastructure is real and worth keeping joint. |
| DR-2 | Acquire 1–3B seed candidates | Approve — nothing local qualifies |
| DR-3 | Corpus token budget | 2M for T1, revisit after F.1 |
| DR-5 | T3/T4 retention (~470 GiB against 405 GiB free) | Cold-store. **Now a capacity decision, not a preference.** |
| DR-6 | Non-synthetic corpus floor | Set a value before any first run |
| OQ-007 | Distribution intent | Answer early — gates licence severity for **both** programmes |
| OQ-009 | Supply sibling repository paths | Minutes of your time; unblocks every integration claim in two theses |
| **NEW-2** | Put `D:\Sovereign Distillery` under version control | It is the programme's entire memory and it has no history |

---

# PART K — CRITICAL PATH

The operator's ordering is correct. One insertion, at the front.

```
[NEW]  B-1  confirm/refute gfx906 ......................... one command, gates both programmes
          ↓
       GR-2 + GR-3 ........................................ gate-path integrity, with tests
          ↓
       GR-6 · GR-5 · GR-7 · GR-4 · GR-10 .................. evidence integrity
          ↓
       IMPORT SOVEREIGN CANON  (GR-1) ..................... + treaty-contract tests
          ↓
       THESIS v1.2 ........................................ per its own freeze rule
          ↓
[NEW]  B-2  write the real GPU probe ...................... HG-3 prerequisite
          ↓
       HG-3  real 4B/8B architecture smoke
```

**Why B-1 goes first.** If the gfx906 does not exist, then GR-2 and GR-3 are still worth fixing — they are correct regardless — but HG-3 as specified cannot be reached at all, and the remediation sequence would be aimed at a gate that has no hardware behind it. If it *does* exist, Sovereign's compute envelope reopens and my T1–T4 tiering needs recomputation before anyone plans around it. Either answer changes what happens after the remediation branch lands. It costs one command and it is the only item on this board that can be cleared in under a minute.

**Sovereign's parallel track.** F.1 (`d3_throughput.py`) needs only Ollama and is runnable today, independent of every blocker above. It would replace the last large body of `ESTIMATE` in Sovereign's plan with measurement. F.5 (provenance skeleton) is pure code with no model dependency and cannot be retrofitted later. Both can proceed while Grounded's remediation branch is in flight.

---

# PART L — HONEST SUMMARY

**What is true:** two audits were run, both found real defects, both were accepted without argument, and no gate was downgraded to a warning to make progress possible. Fail-closed source admission held across four authorization directives. No model was trained, promoted, or deployed on evidence that did not support it. The shared infrastructure — provenance, exclusion, historical-best aggregation, human promotion — is implemented to a standard above what most of this class of project achieves.

**What is also true:** the workspace has produced no trained parameter, no evaluation suite, no seed, and no throughput measurement. Its research parent is unstarted and unversioned. Its repository carries the parent's name and the child's contents. Its next declared gate targets hardware that appears nowhere in the workspace except three lambdas in a test file.

Those two paragraphs are both accurate, and the gap between them is the project. It is a well-governed pre-implementation programme that has spent its effort on the parts most projects skip — provenance, gating, falsifiability — and has not yet spent any on the part most projects start with.

That ordering is defensible. It is also the reason the single most valuable next action costs one command.

---

*This is a status report. It is not an approval. Acceptance belongs to the operator.*
