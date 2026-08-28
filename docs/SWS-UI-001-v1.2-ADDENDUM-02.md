# SWS-UI-001 v1.2 — ADDENDUM 02: Local Inference Modernization Envelope (CP-02)

| Field | Value |
|---|---|
| Amends | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2. Contract text unchanged. Independent of, and additive to, `ADDENDUM-01` (CP-01). |
| Addendum ID / version | `SWS-UI-001-ADD-02 v1.0`, 2026-08-25. |
| Basis | Operator-supplied "CP-02 — Sovereign Local Inference Modernization and Registry Truthfulness Directive" (81 sections), as corrected by `docs/CP-02-REVIEW-01.md` findings F-01 … F-12. |
| Issuer / final authority | Human operator (sam). No authority until the §9 sentence is logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. |
| Work order | `docs/OX-ALPHA-DIRECTIVE-CP-02.md`. |
| Precedence | `AGENTS.md` §1 item 2, beside `ADDENDUM-01`. **The two envelopes never apply simultaneously**, because the two packages never run simultaneously (§5). CP-02's caps are measured against the **post-CP-01 baseline** captured at G0.3 — they do not compound with, subtract from, or inherit CP-01's. See `docs/CP-02-CONFLICT-AUDIT.md`. |
| Hard precondition | CP-01 must have **exited** — §8 final message or `docs/STOP-REPORT-CP-01.md` — and its `8*` band must carry a reviewer verdict. See §5. |

---

## 1. Scope

CP-02 is an **inference and control-plane** change package. It is not a training package, not a UI package, and not an architecture package. It implements the eight bands `CP-02-MODERNIZATION-ASSESSMENT.md` identified as real gaps, and nothing else.

The operator's CP-02 §0 SHALL / SHALL NOT lists bind verbatim and are not restated here. The operator's §2–§5 preservation clauses — vendor-blind resolver, capability vocabulary, residency state machine, shell lifecycle contract — bind absolutely and are STOP conditions if violated.

---

## 2. Corrections binding on the work order

The supplied directive is accepted with twelve corrections. Each is binding; none is waivable by the builder. Full reasoning in `docs/CP-02-REVIEW-01.md`.

| # | Correction |
|---|---|
| **F-01** | **llama.cpp is a mechanism; the residency planner is the sole eviction authority.** The router runs with `--no-models-autoload`, and `--models-max` is set strictly above the planner's concurrency bound so the router's own LRU is unreachable by construction. `--models-max 1` is a Band B validation setting only and MUST be changed before Band D. A Band D test asserts the router performs no unrequested transition while the planner's bound is saturated and a generation is active. |
| **F-02** | **One VRAM budget authority, accounting both runtimes.** Before Band D schedules any load, the builder adopts and records exactly one of: **(a)** a real VRAM reader (`nvidia-smi --query-gpu=memory.used,memory.total,memory.free` or NVML) as the planner's budget input, with both runtimes' footprints reconciled against actual free VRAM; or **(b)** exclusive residency — only one runtime holds resident models at a time, enforced in the backend contract, the other asserted empty before a load, recorded as a standing limitation. Scheduling a load without such an authority is `VRAM_BUDGET_UNACCOUNTED`. |
| **F-03** | **GGUF acquisition is offline-first from the Ollama blob store**, read-only, copied into the runtime's `test-models\`, provenance recorded back to the originating tag. Ollama's store is never moved, renamed, or written. If the store path is unreadable — a prior grant for `.ollama` was refused by the device bridge, FACT[`…SOURCE_TREE\docs\sovereign\VALIDATION.md:169-174`] — that is `GGUF_SOURCE_UNAVAILABLE`, a STOP. An external download is a fallback requiring separate operator authorization and a recorded origin, size, and SHA-256. |
| **F-04** | **Band F is time-bounded.** At most three models (one 7–8B, one 12B, one 27B for the offload case) across the four tiers the operator's §47 names, with a declared per-run time budget. `NOT_MEASURED(TIME_BUDGET)` is a valid recorded outcome; an estimated measurement is not. |
| **F-05** | **A context demotion may not strand existing capability requests silently.** Before writing any validated value lower than the current declared value, dry-run the resolver over recorded historical capability requests under both values and record every request class that would newly fail. Applying the demotion requires explicit operator acceptance of that list. Unaccepted → `CONTEXT_DEMOTION_STRANDS_REQUESTS`. |
| **F-06** | **Migration rule: one tag = one artifact, always.** `model_id` is assigned only where the tag unambiguously denotes a known base model; otherwise `model_id = artifact_id` with `needs_operator_review: true`. No heuristic name-matching, no family inference. A fine-tune is a different logical model. Consolidation is a later operator decision against a visible list. |
| **F-07** | **Router-mode support is asserted, not assumed.** Band A's gate positively demonstrates that the pinned build enters router mode with no `-m` and answers `GET /models`. Absent → `ROUTER_MODE_UNAVAILABLE`; Band B is not attempted. |
| **F-08** | **`metrics()` is added at Band G, not before**, and its shape is defined by what the operator's §53 and §54 actually read. |
| **F-09** | **Model promotion state is a third orthogonal axis** — distinct from node/process state and from VRAM residency state. It describes a model's standing in the programme, not a process's liveness or an artifact's VRAM location. The three are never unified. |
| **F-10** | **PRE-01 means CP-01's exit**, not Gate 8g in isolation. See §5. |
| **F-11** | Loop mechanics and changed-line caps are supplied by this addendum (§3) and the work order. |
| **F-12** | STOP set extended per §6. |
| **F-13** | **Caps do not compound.** CP-02's changed-line caps are measured by `difflib` against the `evidence/cp02/baseline/before/` capture taken at G0.3 — that is, against the workspace **as CP-01 left it**. Lines CP-01 changed are part of CP-02's baseline, not part of CP-02's budget. A builder that measures against a pre-CP-01 state is measuring the wrong thing and will STOP `ENVELOPE_EXCEEDED` incorrectly. |
| **F-14** | **llama.cpp's server process is owned by the shell, as a module.** It is not spawned by the planner (the work order's G20 forbids that), not spawned by an adapter, and not left as an operator-run orphan. It gets `shell/modules/llamacpp.json` with a real `http` readiness probe against its own `GET /models`, `http_json` identity, `job_object` stop, and `runtime_writes` scoped to `runtime/llama.cpp/logs`. This is the same adapter pattern the Distillery and Token Center take under CP-01 — the third consumer of it, which is evidence the pattern is right rather than a reason to invent a fourth. |
| **F-15** | **The llama.cpp port is pinned to `5183`** — adjacent to the shell's 5180, and unreferenced anywhere in the workspace today (ABSENT: searched `8080` and `5183` across `shell/`, ADD-01, and the CP-01 work order). It joins 5175 / 8700 / 8765 / 5180 in every quiescence check, baseline capture, and closeout verification. `llama-server`'s default 8080 is never used. |

### 2.1 One deviation from the supplied directive

The operator's §10 suggests `D:\Product Software\Runtime\llama.cpp\`. That path is **outside** `Production Workspace\`, where `AGENTS.md` §6 forbids all writes. Rather than widen a protected-source rule for a convenience, the runtime installs at:

```
D:\Product Software\Production Workspace\runtime\llama.cpp\
```

with the operator's own subtree layout (`versions\<pinned>\`, `current\`, `config\`, `logs\`, `test-models\`). This satisfies §10's actual requirement — deterministic, version-controlled where appropriate, not a random user directory — without touching §6. The operator's "or the repository's existing canonical runtime directory" clause anticipates this.

---

## 3. Mutation envelope

### 3.1 Tree status

| Tree | Status |
|---|---|
| `Production Workspace\runtime\**` | **Creatable.** New. Binaries and models here are artifacts, not changed lines. |
| `Production Workspace\modules\sow\adapters\**`, `scheduler\**`, `control_plane\**`, `schemas\**`, `config\**`, `tools\**` | **Writable**, per §3.2. |
| `Production Workspace\shell\**` | **Writable**, per §3.2 — resource-accounting surface and log fields only. Overlaps `ADDENDUM-01`; stricter cap governs. |
| `modules\sovereign\**`, `modules\debate\**`, `modules\distillery\**`, `modules\tokencenter\**` | **Read-only.** Not in scope. |
| Ollama's store (`%USERPROFILE%\.ollama\`) | **Read-only, always.** Copy out; never move, rename, write, or delete. Never `ollama pull`, `rm`, or `cp`. |
| `D:\Sovereign Distillery\`, `D:\Sov 1\`, `D:\multi model terminal app\`, `D:\Token Piggy Bank\`, `D:\Product Software\` outside `Production Workspace\` | **Protected, read-only.** Unchanged. |

### 3.2 Changed-line caps

Added + removed via `difflib` against the Band-0 `before/` capture, summed per area. Test files excluded.

| Area | Cap |
|---|---:|
| `modules/sow/adapters/**` — protocol widening, `LlamaCppBackend`, Ollama adapter conformance | 450 |
| `modules/sow/scheduler/**` — residency actuation and budget authority | 200 |
| `modules/sow/control_plane/**` + `schemas/**` — identity/artifact split, manifest, ingestion | 500 |
| `modules/sow/tools/**` + `config/**` | 150 |
| `shell/**` — resource accounting and log fields | 220 |
| `shell/modules/llamacpp.json` — new module manifest (F-14) | 45 |
| `runtime/**` — configuration files only | 60 |
| **Absolute total** | **1,625** |

Measured against the G0.3 `before/` capture — the workspace as CP-01 left it (F-13). `shell/modules/llamacpp.json` is a **new** file and does not touch CP-01's `shell/modules/*.json` bucket; the other four manifests are read-only to CP-02.

Exceeding any cap is `ENVELOPE_EXCEEDED`, a STOP. Splitting one logical change across sub-cap edits to evade a cap is a violation, not a technique.

### 3.3 Installs, network, and spend

- **No `pip`, no `npm`, no `ollama pull`.** The llama.cpp binary is a pinned download, which is an **artifact acquisition**, not a package install: origin, release identifier, SHA-256, binary inventory, CUDA backend identifier, and build date are recorded before first execution. A step that requires any other download is `INSTALL_REQUIRED`, a STOP.
- **Offline-first governs operation, not setup.** Once the binary and test artifacts are present, every band must run with no network.
- **Provider spend remains a mandatory STOP.** CP-02 exercises local runtimes only. `config/live_operation.json` carries `"live_operation_authorized": true` across four paid providers; the operator's PRE-02 requires that contradiction reconciled before any provider-backed path is invoked. Unreconciled → `PROVIDER_SPEND_CONTRADICTION`.

### 3.4 Untouchable

`AGENTS.md`, `CLAUDE.md`, the contract, `ADDENDUM-01`, this file, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, `docs/DECISIONS.md`. Never `"status": "PASS"`. Gates 0–8j byte-identical before and after every ledger write.

---

## 4. Gates added

| Gate | Name | Operator §§ |
|---|---|---|
| `9a` | llama.cpp pinned install and single-model validation | 9–13 |
| `9b` | Router mode as state and actuation source | 14–22 |
| `9c` | Backend Protocol widened; `LlamaCppBackend` added | 23–29 |
| `9d` | Runtime residency connected to the existing planner | 30–34 |
| `9e` | Model identity / deployment artifact split, manifest, ingestion | 35–42 |
| `9f` | Context truthfulness | 43–48 |
| `9g` | Fallback visibility and resource accounting | 49–54 |
| `9h` | Forward-compatibility metadata and the NVFP4 research lane | 55–60 |
| `9j` | Regression, adversarial review, closeout | 70–75 |

Bands are strictly ordered. `9j` requires `9a`–`9h` at `CANDIDATE` or better. **No gate in this band promotes llama.cpp to production default** — the operator's §76 governs, and promotion is a separate operator act after reviewing CP-02 evidence.

---

## 5. Precondition — CP-01 must have exited

CP-02 does not begin while CP-01 is live. Concurrent writers on the registry, the schemas, or `shell/static` produce exactly the corruption both loops' `CONCURRENT_WRITER` conditions exist to prevent.

CP-02's G0 asserts, from disk: CP-01 has written either its §8 final message artifacts (`docs/CP-01-REPORT.md` plus ledger keys `8a`–`8j`) or `docs/STOP-REPORT-CP-01.md`; and a reviewer verdict covering the `8*` band exists as `docs/REVIEW-BUILD-07.md` or successor. Any `8*` key still `CANDIDATE` with no reviewer verdict, or any evidence of an active CP-01 writer, is `CP01_STILL_LIVE` — a STOP, not a wait loop.

**Status at issuance:** unmet. CP-01 is live at G0.1 (`evidence/cp01/tools/goalcheck.py` written 06:54Z; two goalcheck runs; protected-tree manifests capturing through 07:10Z; no `8*` keys).

---

## 6. Stop conditions this addendum adds

`AGENTS.md` §13 in full, plus the operator's §8 list, plus:

`VRAM_BUDGET_UNACCOUNTED` · `DUAL_EVICTOR_CONFLICT` · `ROUTER_MODE_UNAVAILABLE` · `GGUF_SOURCE_UNAVAILABLE` · `CONTEXT_DEMOTION_STRANDS_REQUESTS` · `TIME_BUDGET_EXCEEDED` · `CP01_STILL_LIVE` · `ENVELOPE_EXCEEDED` · `INSTALL_REQUIRED` · `PROVIDER_SPEND_CONTRADICTION`

Every STOP writes `docs/STOP-REPORT-CP-02.md` with the `FACT[...]` condition, the exact conflict, why proceeding requires interpretation, and 2–3 bounded operator options. Then stops.

---

## 7. Regression obligation

Standing at every gate, not once at the end. The operator's §70 list binds verbatim, plus: the full README suite ends `OK` with count ≥ the CP-01 exit baseline; `shell/BUILD-MANIFEST.txt` regenerated and equal to live hashes; all protected manifests `fc /b` clean; `app.css` `:root` unchanged from `THEME-BASELINE-v3.md`; **Ollama inference works at every gate** and no configuration change makes llama.cpp mandatory.

---

## 8. Deferred — recorded at closure, per the operator's §79

```
DEFERRED_HARDWARE:        ExLlamaV3 · EXL3 · Unsloth training · GRPO ·
                          speculative execution · broad quantization generation ·
                          large-student Distillery training
DEFERRED_OPERATOR_DECISION: remote-machine routing · loopback sovereignty invariant repeal ·
                            >=24 GiB trainer designation · named-role display aliases ·
                            Token Center ownership and location
RESEARCH_ONLY:            NVFP4
```

Deferred is not failed. Deferred is not complete. Deferred means deliberately outside CP-02 authority.

---

## 9. Issuance

No authority until the operator sends this sentence in session and the builder logs it verbatim with the UTC of receipt into `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation:

```
OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-02 v1.0 is issued as written; the CP-02 envelope, the runtime install, and gates 9a-9j are authorized; corrections F-01 through F-12 bind; stage pauses waived; no provider spend authorized; llama.cpp is not promoted to production default by this package.
```

Absent → STOP `PRECONDITION_UNSIGNED`. The §2 corrections and the §5 precondition bind from issuance and are not waivable by anything short of a versioned successor to this file.
