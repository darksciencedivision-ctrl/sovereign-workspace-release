# OX-ALPHA-DIRECTIVE-CP-02 — Local Inference Modernization Loop, SWS-UI-001 v1.2 + ADD-02

| Field | Value |
|---|---|
| Contract | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2, unchanged. `AGENTS.md` binds in full. |
| Envelope | `docs/SWS-UI-001-v1.2-ADDENDUM-02.md` (ADD-02 v1.0) — caps, tree status, corrections F-01…F-12, gates, STOP set. Where this file and ADD-02 appear to conflict, **ADD-02 governs** and you report the conflict. |
| Source | The operator's 81-section CP-02 directive. Its §0 SHALL/SHALL-NOT lists and its §2–§5 preservation clauses bind **verbatim** and are not restated here. Read it as delivered; this file makes it machine-checkable. |
| Authorization | The ADD-02 §9 sentence, logged verbatim with its UTC in `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation. Absent → STOP `PRECONDITION_UNSIGNED`. |
| Hard precondition | **CP-01 has exited and its `8*` band carries a reviewer verdict.** See G0.0. Not a wait loop — a STOP. |
| Loop state | `evidence/cp02/LOOP-LEDGER.jsonl`, append-only, **one JSON line per iteration, written before the next iteration begins**. A fresh session resumes by running the oracle and reading this file — never from memory. |
| Oracle | `evidence/cp02/tools/goalcheck.py` — `py -3.12`, stdlib only, read-only. Written once at G0. The loop's only judge of truth. |
| Promotion | **This package promotes nothing.** Ollama remains the production default throughout. llama.cpp exits CP-02 as a validated candidate runtime. Operator §76 governs. |

---

## 1. Operating principle

Verify, then act, then verify.

Each iteration: run the oracle against disk; take the **single smallest authorized action** that flips the **first** failing goal; run the oracle again; append one ledger line. Goals are strictly ordered — G(n) is not acted on while G(n−1) is FALSE. The bands are dependency-ordered, not thematic: you cannot connect residency actuation to a router you have not proven, and you cannot demote a context claim you have not measured.

The loop ends in exactly one of two states: every goal TRUE, or a STOP report. There is no third exit. Do not end your turn at a band boundary. If the harness ends it anyway, resume from the first failing goal without re-deriving the plan.

**Additive and reversible.** Every band leaves Ollama fully operational. If a band fails, the correct action is to disable the candidate component and restore the previous configuration — not to repair forward past a STOP. `FAILED` recorded accurately is worth more than a green gate.

**Two authorities, one pool.** The single hardest thing in this package is that llama.cpp and the residency planner both want to evict, and Ollama and llama.cpp both allocate from the same 8151 MiB. ADD-02 F-01 and F-02 settle both. Re-read them before Band D.

---

## 2. Goal state

Read `TRUE when` as a conjunction. Hashes are full lowercase 64-hex, taken after final write, `Test-Path`-verified. Every new behaviour needs a **fails-before** and a **passes-after** artifact; a test that never failed proves nothing. Every measurement artifact records command, exit status, stdout/stderr reference, and timestamp.

### Band 0 — Precondition

| # | Goal | TRUE when |
|---|---|---|
| **G0.0** | **CP-01 has exited** | `docs/CP-01-REPORT.md` exists with ledger keys `8a`–`8j` present, **or** `docs/STOP-REPORT-CP-01.md` exists; **and** a reviewer verdict covering the `8*` band exists (`docs/REVIEW-BUILD-07.md` or successor). No `8*` key is `CANDIDATE` without a verdict. No CP-01 writer is active — `evidence/cp01/` unchanged across two reads ≥ 60 s apart. Otherwise STOP `CP01_STILL_LIVE`. |
| **G0.1** | Session start | `evidence/cp02/baseline/session-start.txt` with `# utc:` / `# producer: ox-alpha CP-02` headers: true UTC; which shell your bash tool runs; sha256 of `docs/DECISIONS.md`, `AGENTS.md`, `CLAUDE.md` (latter two equal), ADD-02, this file. ADD-02 §9 sentence quoted verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. `evidence/cp02/tools/goalcheck.py` exists and runs clean. |
| **G0.2** | **Provider-spend contradiction reconciled** | `evidence/cp02/baseline/spend-reconciliation.txt` records `config/live_operation.json`'s `live_operation_authorized` and `providers` verbatim against the ADD-02 §9 authorization. If configuration permits provider-backed paths while authorization says no spend, STOP `PROVIDER_SPEND_CONTRADICTION`. **No interpretation.** Operator authority only. |
| **G0.3** | Clean baseline | `evidence/cp02/baseline/` holds: `git-head.txt`, `git-status.txt`, `host-hardware.json` (**fresh capture, not the 2026-08-19 file**), `runtime-inventory.json`, `model-registry-hash.txt`, `schema-hashes.json`, `ollama-version.txt`, `ollama-model-list.json`, `ports.txt` (**5175 · 8700 · 8765 · 5180 · 5183**), `processes.txt`. Plus `before/` — copies and hashes of every file the ADD-02 §3.2 caps permit you to touch, **as CP-01 left them**: this capture is the sole baseline for every changed-line measurement in this package (ADD-02 F-13). Protected-tree manifests captured with `evidence/tools/manifest.py` (hash asserted against `manifest_tool_sha256`). Full README suite → `test-run-before.txt` ending `OK`, count recorded. |
| **G0.4** | GGUF source reachable | `evidence/cp02/baseline/gguf-source.txt` proves the Ollama blob store is readable and identifies at least one small (7–8B) and one 12B-class GGUF blob by tag, manifest path, blob digest, and size. Unreadable → STOP `GGUF_SOURCE_UNAVAILABLE`. Ollama's store is read-only, always. |

### Band A — Gate 9a · Pinned llama.cpp beside Ollama

| # | Goal | TRUE when |
|---|---|---|
| G1 | Pinned and provenance-recorded | `runtime/llama.cpp/versions/<pinned>/` populated; `runtime/llama.cpp/current` resolves to it. `evidence/cp02/band-a/pin.txt` records release identifier, origin, SHA-256, binary inventory, CUDA backend identifier, build date. **No `latest` dependency.** Nothing modified in Ollama; global PATH unchanged; no boot autostart; not registered as a production runtime. |
| G2 | Test artifacts staged | The G0.4 blobs copied read-only into `runtime/llama.cpp/test-models/`, each with source tag, blob digest, destination sha256 — matching. Ollama's store byte-identical to G0.3. |
| G3 | A1–A4 | `--version` for cli and server, exit status recorded · **CPU-only** load/prompt/generate/clean-exit on the small model · **CUDA** run recording GPU detected, layers offloaded, VRAM before/after · **partial offload** explicitly exercised (8 GiB host) recording layer placement, RAM, VRAM, load time, TTFT, prompt rate, generation rate. Each in `evidence/cp02/band-a/a{1,2,3,4}-*.txt`. |
| G4 | A5–A8 | Single-model `llama-server`: health, model exposure, request, response, shutdown · OpenAI-compatible `POST /v1/chat/completions` non-streaming **and** streaming · cancellation of a long generation with the server still healthy and the model still usable afterwards · clean shutdown with port released, process gone, no orphan. |
| G5 | **Router mode asserted, not assumed** | `evidence/cp02/band-a/router-support.txt` positively demonstrates the pinned build enters router mode with no `-m` and answers `GET /models`, recording the flags **observed**. Absent → STOP `ROUTER_MODE_UNAVAILABLE`; Band B not attempted. (ADD-02 F-07) |
| G5.1 | **The shell owns the process** | `shell/modules/llamacpp.json` exists and declares: `launch` with an absolute `.exe` argv (never `.cmd`/`.bat`/`shell=True`), `readiness` `http` against `http://127.0.0.1:5183/models` expecting 200, `identity` `http_json` requiring the keys `/models` actually returns, `stop` `job_object`, `runtime_writes` scoped to `runtime/llama.cpp/logs`, `open` `none`. Started and stopped **only** through the shell's own routes. `evidence/cp02/band-a/module-lifecycle.txt`: Start → `READY` on an observed health response; Stop → pid gone, **5183 free**. `grep` proof that no adapter, planner, or backend spawns or kills a llama.cpp process. (ADD-02 F-14, F-15) |
| G6 | Ollama unharmed | Ollama inference works after every Band A step; version and model count equal G0.3. Port 5183 is used throughout; `llama-server`'s default 8080 is never bound. |
| G6.1 | Gate 9a | Ledger `"9a"` `CANDIDATE` with every Band A artifact hashed. Suite green. Manifests clean. |

### Band B — Gate 9b · Router mode as state and actuation source

Validation setting for this band only: `--models-max 1`, so load/unload is unambiguous. **This value does not survive into Band D** (ADD-02 F-01).

| # | Goal | TRUE when |
|---|---|---|
| G7 | B1 initial state | Router started with neither MODEL_A nor MODEL_B loaded; `GET /models` distinguishes states equivalent to `loaded` / `loading` / `unloaded`. Recorded verbatim. |
| G8 | B2 on-demand load | MODEL_A requested; transition `unloaded → loading → loaded` observed; wall-clock load time, VRAM delta, RAM delta recorded. |
| G9 | B3 explicit unload | Unload invoked; `loaded → unloaded` observed; VRAM/RAM before and after recorded. **VRAM actually returns**, not merely the state flag. |
| G10 | B4 LRU | At `models-max 1`, MODEL_A loaded then MODEL_B requested; MODEL_A evicted and MODEL_B loaded with no manual intervention. |
| G11 | B5 failure | Invalid identifier, corrupt artifact, and unsupported artifact each produce a clear failure; the router survives; an already-loaded model remains coherent. |
| G11.1 | Gate 9b | Ledger `"9b"` `CANDIDATE`. No Sovereign integration exists yet. |

### Band C — Gate 9c · Widen the existing Backend Protocol

| # | Goal | TRUE when |
|---|---|---|
| G12 | Contract widened, not replaced | The existing `Backend` Protocol (`modules/sow/adapters/base/backend.py`) exposes `list_models · load_model · unload_model · generate · cancel · health · capabilities`. **No `metrics()` yet** (ADD-02 F-08). No new parallel abstraction is introduced; `grep` proof in `evidence/cp02/band-c/no-replacement.txt`. |
| G13 | Ollama adapter conforms honestly | The Ollama backend implements the widened contract. Where a capability is not natively available it returns an **explicit unsupported result with a reason** — never a faked success, never a silent no-op. Test asserts each unsupported path returns `supported: false` with a non-empty reason. |
| G14 | `LlamaCppBackend` added | Added beside `OllamaBackend`. It translates existing internal request semantics to llama.cpp and **contains no routing policy**. Runtime identity, model identity, and artifact identity stay separate — never `model: "llama.cpp/qwen3.8-q4"`. `grep` proof. |
| G15 | Parity matrix | `evidence/cp02/band-c/parity-matrix.txt`: identical operations run against both backends where supported — health, list models, generate, stream, cancel, load, unload, capabilities, error mapping, timeout — with each cell PASS / UNSUPPORTED(reason) / FAIL. Runtime errors normalized to one vocabulary. |
| G16 | **Ollama remains the default** | `evidence/cp02/band-c/default-runtime.txt` proves the production path still resolves to Ollama. No promotion occurs in this band. |
| G16.1 | Gate 9c | Ledger `"9c"` `CANDIDATE`. Full regression per ADD-02 §7. |

### Band D — Gate 9d · Connect runtime residency to the existing planner

| # | Goal | TRUE when |
|---|---|---|
| G17 | **Budget authority chosen and recorded** | `evidence/cp02/band-d/vram-authority.txt` records which of ADD-02 F-02 (a) real VRAM reader or (b) exclusive residency was adopted, why, and how it is enforced. A load scheduled without it is `VRAM_BUDGET_UNACCOUNTED`. |
| G18 | **Router demoted to mechanism** | Router runs `--no-models-autoload` with `--models-max` strictly above the planner's concurrency bound. `evidence/cp02/band-d/single-evictor.txt` records the two numbers and the reasoning. A Band B `models-max 1` setting surviving into this band is `DUAL_EVICTOR_CONFLICT`. |
| G19 | State mapping respects existing semantics | Router states map into the **existing** planner vocabulary (`NOT_LOADED · LOADING · RESIDENT · AWAITING_EVICTION · QUEUED · EVICTED`). No new canonical state is created because llama.cpp uses a different word. Mapping table in `evidence/cp02/band-d/state-map.txt`. |
| G20 | Layered actuation | The planner requests `load_model` / `unload_model` **through the backend contract** and never spawns or kills a llama.cpp process directly. `grep` proof that no process-control call exists in the planner. |
| G21 | Round-trip proved | `evidence/cp02/band-d/roundtrip.txt`: planner sees unloaded → requests load → router loads → planner reflects `RESIDENT`; planner selects eviction → runtime unloads → planner reflects `EVICTED`/`NOT_LOADED`. VRAM observed at each step. |
| G22 | **No mid-generation eviction, from either side** | Two tests. (i) The planner never evicts a generating model. (ii) **The router performs no unrequested transition** while the planner's bound is saturated and a generation is active — the F-01 test. Both fail-before against a deliberately mis-configured router. |
| G23 | Fail closed | Router unavailable · stale response · load timeout · unload timeout · eviction requested during active generation — each produces a defined, recorded, non-corrupting outcome. |
| G23.1 | Gate 9d | Ledger `"9d"` `CANDIDATE`. |

### Band E — Gate 9e · Model identity / deployment artifact split

| # | Goal | TRUE when |
|---|---|---|
| G24 | Two records, extending not replacing | The registry distinguishes a logical **model identity** record from a runtime-specific **deployment artifact** record, extending the CP-01 registry rather than replacing it. One model owns many artifacts; artifacts retain format, quantization, runtime, path, hash. |
| G25 | **Conservative migration** | ADD-02 F-06: one tag = one artifact, always. `model_id` assigned only where the tag unambiguously denotes a known base model; otherwise `model_id = artifact_id` with `needs_operator_review: true`. **No heuristic name-matching.** `evidence/cp02/band-e/migration.txt` lists every one of the live tags with its disposition and flags. A fine-tune is never folded into its base model. |
| G26 | Legacy references resolve | `legacy_alias` / `migration_source` / `migration_version` retained; a test resolves every pre-migration identifier. Nothing is destroyed. |
| G27 | Deployment manifest schema | Canonical schema with at minimum: `artifact_id · model_id · source_identity · source_hash · artifact_hash · format · quantization · runtime_compatibility · creation_tool · creation_tool_version · creation_timestamp · validated_context · status`. Optional forward fields permitted per operator §39. |
| G28 | Ingestion, fail-closed | Manifest → validation → registry → `CANDIDATE`. **No automatic production promotion.** Rejects on missing artifact hash, hash mismatch, unknown `model_id`, invalid runtime, invalid format, invalid schema, duplicate `artifact_id` with conflicting hash, unsupported schema version. **Never partially ingests.** Each rejection has a fails-before artifact. |
| G29 | Promotion state is a third axis | `evidence/cp02/band-e/three-axes.txt` states, and a test asserts, that model promotion state is orthogonal to node/process state and to VRAM residency state. The three are never unified. (ADD-02 F-09) |
| G29.1 | Gate 9e | Ledger `"9e"` `CANDIDATE`. |

### Band F — Gate 9f · Context truthfulness

| # | Goal | TRUE when |
|---|---|---|
| G30 | Three values, distinguished | `advertised_context`, `validated_context`, `production_context`, plus `validation_evidence`, stored at the placement the existing schema architecture dictates. A label (`STANDARD`/`DEEP`/`EXTENDED`/`ULTRA`/`EXPERIMENTAL`) **never implies support**; the validation record governs eligibility. |
| G31 | Bounded measurement | ADD-02 F-04: at most three models — one 7–8B, one 12B, one 27B for the offload case — across four tiers (short baseline, medium, current declared production, next candidate). Per-run time budget declared in advance. Never a 32K→256K jump. |
| G32 | Variables recorded | Per combination: context requested, context successfully initialized, prompt tokens processed, TTFT, prompt tok/s, generation tok/s, VRAM, RAM, KV-cache footprint, retrieval correctness, instruction retention, structured-output correctness, tool-call correctness where applicable, runtime errors, OOM. `NOT_MEASURED(TIME_BUDGET)` is a valid outcome; an estimate is not. |
| G33 | **Demotion does not strand requests** | ADD-02 F-05. Before writing any value lower than the current declared one, dry-run the resolver over recorded historical capability requests under both values; `evidence/cp02/band-f/demotion-impact.txt` lists every request class that would newly fail. Applying it requires explicit operator acceptance quoted verbatim. Unaccepted → STOP `CONTEXT_DEMOTION_STRANDS_REQUESTS`. |
| G34 | Resolver consumes truth | After acceptance, `min_context` routing uses validated/production values, not advertised. A model advertising 256K but validated to 64K advertises 64K to routing. Test asserts the resolver reads the validated field. |
| G34.1 | Gate 9f | Ledger `"9f"` `CANDIDATE`, note stating exactly what was measured and what was `NOT_MEASURED`. |

### Band G — Gate 9g · Fallback visibility and resource accounting

| # | Goal | TRUE when |
|---|---|---|
| G35 | Fallback via the existing resolver | An ordered candidate list comes from the **existing descriptor-based resolver**. No separate role router is built. `grep` proof of no new routing path. |
| G36 | **Visible, never silent** | Every fallback records original candidate, failure reason, replacement candidate, runtime, artifact, timestamp, task/request id, and surfaces a fallback indication where a user-facing state exists. A silent substitution is `FAKE_STATE`. |
| G37 | **Infrastructure ≠ reasoning** | Fallback triggers only on runtime unavailable, model load failure, OOM, timeout, backend health failure, artifact unavailable. A test asserts a bad answer, a failed reasoning step, and an incorrect tool decision **do not** trigger fallback. (Operator §52 — carried verbatim.) |
| G38 | Resource accounting in existing surfaces | Runtime, model, artifact, load state, VRAM used, system RAM used, context configured, KV-cache usage where available, `node = local host` — surfaced through CP-01's accepted shell surfaces. **No parallel UI application.** |
| G39 | Logging extends, never bypasses | Existing `LogRing`, redaction surfaces, and token accounting extended with `runtime · model_id · artifact_id · request_id · load_state · fallback_reason`. A test proves the new fields pass through redaction. A parallel logging path that bypasses redaction is a STOP. |
| G40 | `metrics()` added here | Only now, and shaped by what G38 and G39 actually read. (ADD-02 F-08) |
| G40.1 | Gate 9g | Ledger `"9g"` `CANDIDATE`. |

### Band H — Gate 9h · Forward-compatibility metadata

| # | Goal | TRUE when |
|---|---|---|
| G41 | Speculative metadata only | Fields equivalent to `{supported, method, draft_model_id, draft_artifact_id, validated, evidence}` exist, default false/null, and accept `MTP` / `DFlash` / `draft model` as future methods. |
| G42 | **No speculative execution** | `grep` proof: no target+draft simultaneous residency, no MTP execution, no DFlash execution, no speculative scheduler. Operator §57 — the 8 GiB host makes it inappropriate. |
| G43 | NVFP4 describable | An artifact may declare format/quantization `NVFP4`, hardware affinity Blackwell, correctness status, validation status, upstream reference. Creates no requirement to deploy. |
| G44 | Research lane, isolated | If run: known-source artifact with verified hash/source · pinned build support verified · correctness, tool-use, repetition/looping, structured-output tests · VRAM, TTFT, prompt and generation throughput · compared against a Q4_K_M baseline. Isolated from production. Not run is a valid outcome, recorded. |
| G45 | **Correctness gate holds** | No NVFP4 artifact reaches `CANDIDATE` while the upstream GGML correctness question is unresolved or local evidence shows unexplained divergence. Permitted state: `RESEARCH` only. Violation → `NVFP4_CORRECTNESS_UNVERIFIED`. |
| G45.1 | Gate 9h | Ledger `"9h"` `CANDIDATE`. |

### Band J — Gate 9j · Regression, adversarial review, closeout

| # | Goal | TRUE when |
|---|---|---|
| G46 | Regression clean | Operator §70's list plus ADD-02 §7: capability descriptor validation · vendor-blind resolution · locality enforcement · **Ollama inference** · OpenCode harness environment filtering · residency-planner invariants · shell lifecycle · registry loading · debate participant descriptor rules · logging redaction. Suite `OK`, count ≥ baseline. Manifests clean. `app.css` `:root` unchanged. |
| G47 | Rollback proved | `evidence/cp02/final/rollback.txt` demonstrates that disabling the candidate backend and restoring the previous configuration leaves the Ollama path fully operational. Not asserted — performed. |
| G48 | **Adversarial review** | `evidence/cp02/final/adversarial-review.txt` searches for and finds **zero** of: duplicate architecture · new hardcoded model names · new vendor routing · silent fallback · fake residency state · fake context claims · new lifecycle states · remote-host leakage · provider-spend leakage · parallel logging bypass · unreviewed schema drift · Ollama regression. Any instance blocks closure. |
| G49 | Diff classification | Every changed file classified `REQUIRED` / `SUPPORTING` / `EVIDENCE` / `UNEXPECTED`. **`UNEXPECTED` must equal zero.** Per-area and absolute changed-line totals within ADD-02 §3.2. |
| G50 | Final evidence manifest | `evidence/cp02/final/FINAL-EVIDENCE-MANIFEST.json`: baseline commit, final commit, modified files, schema changes, tests executed, **tests passed, tests failed**, runtime versions, artifact hashes, known limitations, deferred items, operator decisions still open. **No test omitted because it failed.** |
| G51 | Deferred recorded | ADD-02 §8's three blocks written verbatim into the report. |
| G52 | Closeout | Every builder-started process stopped through its own path — llama.cpp through the shell's Stop route, never by `taskkill`. `Get-Process` shows nothing under `runtime\` or `modules\`; **5183 free**, and 5175 / 8700 / 8765 / 5180 as found at G0.3. Ollama running or cleanly stopped as found. No debugging left behind as finished work. |
| G53 | Report | `docs/CP-02-REPORT.md`: per band — implementation location, files changed, behaviour before, behaviour after, validation performed, result, remaining limitations. Every substantive sentence tagged `FACT[path]` / `ASSUMPTION` / `INTERPRETATION` / `RECOMMENDATION`. Ends with the §6 claim line. |
| G54 | Ledger `"9j"` | `CANDIDATE`. Gates 0–8j byte-identical. **No gate asserts llama.cpp as production default.** |

---

## 3. The loop

```
i = 0
while i < 140:
    i += 1
    state = goalcheck()                  # reads disk only; writes evidence/cp02/goalcheck-<i>.txt
    if all TRUE: break
    g = first failing goal in declared order
    act(g)                               # the ONE smallest authorized action for g
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, goal, action, changed_lines, flipped, notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS
submit: ledger keys 9a-9j + docs/CP-02-REPORT.md + claim line
```

The ledger line is written **before the next iteration begins** — not batched. Any transient failure gets exactly **one** retry; the second is logged and counts toward no-progress. Every mutation is preceded by a `before/` capture and followed by a `linecount.txt` append.

**Single writer.** Nothing else writes to this workspace while the loop runs. A file you did not write changing under you is `CONCURRENT_WRITER` — stop and name it.

---

## 4. Action envelope per band

- **G0.0–G0.4**: read-only inspection, evidence writes, the oracle. No product edits. No network.
- **G1–G6.1**: `runtime/**` and the new `shell/modules/llamacpp.json`, plus evidence. The binary is acquired once, pinned, and hashed before first execution. Ollama read-only. The other four module manifests are read-only to this package.
- **G7–G11.1**: `runtime/llama.cpp/config/**` and evidence. **No Sovereign source edits in Band B.**
- **G12–G16.1**: `modules/sow/adapters/**` within cap; adapter tests uncapped.
- **G17–G23.1**: `modules/sow/scheduler/**` and the adapter surface the planner calls. The planner never gains process control.
- **G24–G29.1**: `modules/sow/control_plane/**`, `schemas/**`, `tools/**`, `config/**` within cap.
- **G30–G34.1**: schema fields plus the resolver's read site. Measurement runs are local-only.
- **G35–G40.1**: resolver consumers, `shell/**` within cap, existing log surfaces.
- **G41–G45.1**: schema fields only, plus an isolated research directory.
- **G46–G54**: no source edits. A product defect found here is `LOOP_PRODUCT_DEFECT` — a STOP, not a repair.

All evidence files carry `# utc:` and `# producer: ox-alpha CP-02` headers, full lowercase hashes, append-only supersession.

---

## 5. STOP conditions

`AGENTS.md` §13 in full · the operator's §8 list · ADD-02 §6, plus: `LOOP_NO_PROGRESS` · `LOOP_PRODUCT_DEFECT` · `CONCURRENT_WRITER` · `FAKE_STATE` · iteration 140 reached.

A STOP writes `docs/STOP-REPORT-CP-02.md` with the loop-ledger tail, the `FACT[...]` condition, the exact conflict, why proceeding requires interpretation, **2–3 bounded operator options**, and no unauthorized implementation. Then closes out per G52 and ends with the no-gate claim line.

**A STOP condition cannot be waved away by the builder.** Only operator authority may alter scope after a STOP.

---

## 6. Exit

On every goal TRUE: write `docs/CP-02-REPORT.md`, then a final message carrying iteration count · the goal table with the artifact and hash proving each · per-area and absolute changed-line totals · the parity matrix · what was measured and what was `NOT_MEASURED` · the three deferred blocks · remaining limitations. Ending with exactly:

```
BUILDER CLAIM: Gates 9a through 9j are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder, and llama.cpp is not promoted to production default by this package.
```

On any STOP, ending with exactly:

```
BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
```

Never reworded. "Passed", "complete", "done", or "✓" beside a gate number is a violation. Say **candidate**.

---

## 7. Governing principle

```
Human operator → Sovereign governance → Capability resolver → Model identity
    → Deployment artifact → Runtime backend → Physical hardware
```

Do not invert it. A runtime does not own the model. A model does not own the router. The router does not own Sovereign. A benchmark does not own production promotion.
