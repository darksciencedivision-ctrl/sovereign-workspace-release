# CP-02-REVIEW-01 — Reviewer Findings on the Operator's CP-02 Directive

| Field | Value |
|---|---|
| Subject | "CP-02 — Sovereign Local Inference Modernization and Registry Truthfulness Directive", 81 sections, operator-supplied 2026-08-25. |
| Verdict | **Accept the scope. Correct twelve defects before execution.** Nine are technical, three are process. Two (F-01, F-02) are blocking — they would produce incorrect behaviour on this specific host, not merely inelegant behaviour. |
| Standing | Reviewer assessment. Authorizes nothing. |
| Companion artifacts | `docs/SWS-UI-001-v1.2-ADDENDUM-02.md` (envelope, corrections binding), `docs/OX-ALPHA-DIRECTIVE-CP-02.md` (executable loop). |

The directive correctly absorbs every finding from `CP-02-MODERNIZATION-ASSESSMENT.md` and adds two distinctions the source document lacked. §52 — fallback covers infrastructure failure but must never reinterpret *"bad answer / failed reasoning / incorrect tool decision"* as infrastructure failure — is a sharp line that most fallback designs get wrong. §62 — *"Inference offload and training capacity are different engineering problems"* — is the correct statement of why 63.7 GiB of system RAM does not answer D-HW-01. Both are kept verbatim in the executable version.

What follows is what it still gets wrong.

---

## Blocking

### F-01 · Two independent LRU evictors on one VRAM pool

**Severity: blocking. Violates an existing accepted invariant.**

Band B configures llama.cpp's router with `--models-max`, whose documented behaviour is *"when you hit `--models-max` (default: 4), the least-recently-used model unloads."* Band D then connects that router to the residency planner — which is itself an LRU evictor, ordering on an internal monotonic counter, bounded by an injected VRAM budget. FACT[`modules/sow/scheduler/residency_planner/residency_planner.py:16-18,33-47`]

That is two policy authorities deciding eviction over the same 8151 MiB, neither aware of the other.

The concrete failure: llama.cpp's LRU has **no knowledge of Sovereign's generation state**. It will evict a model the planner has marked `RESIDENT` and `generating`. That directly violates invariant 22, which the directive's own §33 restates: *"local concurrency is hardware-bounded (8–14B tier); VRAM residency is scheduled, visible, never mid-generation eviction."* FACT[`residency_planner.py:3-7`]

§33 asks for a test proving an active generation cannot be evicted "by normal LRU/planner behaviour". That test will pass against the planner and say nothing about the router, which is where the eviction will actually come from.

**Correction.** Make llama.cpp a *mechanism* and the planner the *sole policy authority*:

- Run the router with **`--no-models-autoload`**, so nothing loads except by an explicit `POST /models/load` the planner issued through the backend contract.
- Set **`--models-max` strictly above** the planner's own concurrency bound, so the router's LRU is unreachable by construction rather than merely unlikely.
- Add a Band D test that asserts the router never evicts autonomously: load to the planner's bound, drive generation, and prove `GET /models` shows no unrequested transition.

§15's `models-max = 1` is correct for Band B's *isolated* load/unload proof and wrong for Band D onward. The directive must say that the value changes between bands and why, or a worker will carry the validation setting into integration and reproduce this bug.

### F-02 · No cross-runtime VRAM budget authority

**Severity: blocking on an 8 GiB host. This is the default outcome, not an edge case.**

After Band C, Ollama and llama.cpp both hold models in the same 8151 MiB. Neither knows the other exists. The planner's "total budget" is an **injected input** — FACT[`residency_planner.py:10-14`]: *"It holds NO GPU handle and makes NO real VRAM measurement: the total budget and each model's footprint are injected inputs."* Band D supplies llama.cpp's view of residency. It supplies nothing about Ollama's.

So the planner will compute a budget from one runtime's footprints and schedule against a pool the other runtime is already consuming. On a 24 GB card this produces occasional pressure. On 8151 MiB, with a 12B model at ~8 GiB, it produces an out-of-memory failure on the first concurrent load.

**Correction.** One of two, chosen explicitly and recorded:

- **(a) Single budget authority.** A VRAM reader (`nvidia-smi --query-gpu=memory.used,memory.total` or NVML) becomes the planner's budget input, and per-runtime footprints are reconciled against actual free VRAM before any load is scheduled. Truthful and durable — this is also the honest reading of the assessment's "the planner has no measurement source".
- **(b) Exclusive residency during CP-02.** A hard rule that only one runtime holds resident models at a time, enforced in the backend contract, with the other's residency asserted empty before a load. Cheaper, sufficient for CP-02, and must be recorded as a limitation to be lifted later.

Either way, add STOP `VRAM_BUDGET_UNACCOUNTED` — the planner scheduling a load without a budget that accounts for both runtimes.

---

## Technical

### F-03 · Bands A and B have no input artifacts, and the likely source is not reachable

**There are zero `.gguf` files on either mounted tree.** ABSENT — `find -iname "*.gguf"` across `D:\Product Software\` and `D:\Token Piggy Bank\` returns nothing; `*.gguf` is git-ignored and the Distillery snapshot states *"No model weights are intentionally included."* Ollama keeps its weights in a content-addressed blob store outside both mounts, with no file extension.

A2 says *"use a small known-compatible GGUF model"*. There isn't one, and the directive does not say where to get it.

**Correction.** Name the acquisition path and its precondition:

- **Preferred — extract from the Ollama blob store.** Ollama's layer blobs are GGUF; the manifest under `models/manifests/…` names the blob digest, and reading that blob gives a usable file. This is offline, requires no download, and keeps provenance traceable to a tag already in the 52-tag inventory. Copy read-only into the llama.cpp `test-models\` directory; never move or rename anything in Ollama's store.
- **Precondition that must be checked first.** The store lives under `C:\Users\Sslaw\.ollama\`, outside both mounted folders — and a prior folder-access grant for `.ollama` and `.lmstudio` was **refused by the device bridge**, recorded at FACT[`…SOURCE_TREE\docs\sovereign\VALIDATION.md:169-174`]. If the path is unreadable, Band A cannot start.
- Add STOP `GGUF_SOURCE_UNAVAILABLE`. Downloading from an external host is a fallback that requires the operator to authorize network use and to record origin, size, and SHA-256 — §1.2's offline-first rule governs *operation*, not setup, but the distinction should be stated rather than assumed.

### F-04 · Band F's compute cost is uncosted and will swallow the package

§46 lists roughly fourteen measurements per combination. §47 requires at least four context tiers. Multiply by any reasonable model set and put it on a box where 27B runs through CPU offload, and prompt processing at 64K is tens of minutes **per run** before generation begins. Band F as written is days of wall-clock and will silently become the whole of CP-02.

**Correction.** Bound it explicitly: at most **three** models (one 7–8B, one 12B, one 27B for the offload case), the four tiers §47 already names, and a declared per-run time budget. Make **`NOT_MEASURED(TIME_BUDGET)`** a valid, truthful recorded outcome. A measurement not taken and honestly recorded is worth more than a measurement estimated.

### F-05 · §48 turns a truthfulness fix into a routing regression

`min_context` is a **hard filter** in the resolver: FACT[`modules/sow/scheduler/resolver/resolver.py:39-40`] `if reqs.get("min_context",0) > provided.get("min_context",0): return False`. Local nodes currently advertise `32000`. FACT[`adapters/roster.py:73,87`]

If Band F measures that a local model reliably holds only 16K at this VRAM, §48 requires writing the truthful lower value. The resolver will then **stop resolving** every capability request that asks for 32K. Tasks that ran yesterday return `NO_ELIGIBLE_NODE` today. That is a behavioural regression wearing a truthfulness fix as a disguise — and §70's regression list does not cover it.

**Correction.** Before writing any demoted value: dry-run the resolver over the recorded historical capability requests with both the old and new values, record every request class that would newly fail, and require **explicit operator acceptance** of that list. Add STOP `CONTEXT_DEMOTION_STRANDS_REQUESTS`. The demotion is still right — it just cannot be applied silently.

### F-06 · The Ollama→registry migration has a real ambiguity, and a heuristic will get it wrong

Band E migrates 43 registry entries against 52 live tags. Three of those tags illustrate the problem:

- `qwen3.8:latest` and `qwen3.8:27b` — almost certainly the same logical model, two tags.
- `orcarouter/Qwen3.8-27B-Uncensored:latest` — a **fine-tune**. Same family, **different logical model**. Name-similarity matching would fold it into the base model and destroy the distinction Band E exists to create.

§38 says "migrate conservatively" without saying what conservative means here.

**Correction.** Pin the rule: **one tag = one artifact, always.** `model_id` is assigned only where the tag unambiguously denotes a known base model; otherwise `model_id = artifact_id` and the record carries `needs_operator_review: true`. No heuristic name-matching, no fuzzy family inference. Consolidation is an operator decision made later against a visible list, not a migration-time guess.

### F-07 · The pinned build is not asserted to support router mode

Router mode is a recent llama.cpp addition. §11 captures release identifier, origin, SHA-256, binary inventory, CUDA backend, and build date — none of which establishes that *this* build has it. Band B then depends on it entirely.

**Correction.** Band A's gate asserts positively: `llama-server` started with no `-m` enters router mode, and `GET /models` answers. Absent → STOP `ROUTER_MODE_UNAVAILABLE`, and Band B is not attempted. Pin the flags observed, not the flags expected.

### F-08 · §24's `metrics()` deferral conflicts with Bands G

§24 says do not add `metrics()` *"unless Band D or Band G contains an actual consumer"* — sound discipline. But §53 requires surfacing VRAM, RAM, context, and KV-cache usage, and §54 requires extending log records with runtime and load state. Those consumers exist by Band G by construction.

**Correction.** State it rather than leaving it to inference: `metrics()` is added **at Band G, not before**, and its shape is defined by what §53 and §54 actually read. This removes a decision the worker would otherwise have to make alone, which is where speculative interface growth comes from.

### F-09 · §69 needs to be named as a third orthogonal axis

The instruction *"do not create competing status taxonomies"* is right, and three taxonomies already exist and are not competitors:

| Axis | Values | Location |
|---|---|---|
| Node/process state | `SPAWNING · READY · ASSIGNED · BUSY · PAUSED · DISCONNECTED · TERMINATED` | `schemas/node.schema@1.1.json:35` |
| VRAM residency | `NOT_LOADED · LOADING · RESIDENT · AWAITING_EVICTION · QUEUED · EVICTED` | `residency_planner.py:33-44` |
| Model promotion | `DISCOVERED · AVAILABLE · VALIDATING · RESEARCH · CANDIDATE · PRODUCTION · REJECTED · DEPRECATED` | proposed, §69 |

**Correction.** Say explicitly that promotion state is a **third orthogonal axis** — it describes a model's standing in the programme, not a process's liveness or an artifact's VRAM location. Without that sentence someone will eventually try to unify them, and the unification will be wrong in all three directions.

---

## Process

### F-10 · PRE-01 is not satisfiable as written

PRE-01 requires CP-01 **Gate 8g** to be reviewed, accepted, or abandoned. CP-01 is a single goal loop whose only exits are all-goals-TRUE or a STOP report; 8g is a mid-band gate submitted as `CANDIDATE` and cannot be reviewed in isolation while the loop continues past it.

**Correction.** PRE-01 waits for **CP-01's exit** — its §8 final message or `docs/STOP-REPORT-CP-01.md` — followed by a reviewer verdict covering the 8-band. Then CP-02 may mutate shared registry structures.

**Current state:** unmet. CP-01 is live and progressing normally at G0.1 — `evidence/cp01/tools/goalcheck.py` (28,157 B) written 06:54Z, `goalcheck-1.txt` and `goalcheck-2.txt` produced, protected-tree manifests capturing through 07:10Z. No `8*` ledger keys yet.

*Minor deviation observed, not blocking:* two goalcheck runs exist but `evidence/cp01/LOOP-LEDGER.jsonl` is still absent, where CP-01 §4 requires one appended line per iteration. Worth a note to the builder at its next report; it does not affect CP-02.

### F-11 · No loop mechanics and no changed-line envelope

CP-02 has bands, gates, and stop conditions, but no oracle, no ordered machine-checkable predicates, no append-only iteration ledger, no per-area line caps, and no no-progress detector. Those are precisely the mechanisms that are keeping CP-01 honest right now — including catching its own PowerShell `H`/`Get-History` alias bug and superseding the faulty artifact rather than overwriting it.

Handed to a worker as prose, an 81-section directive drifts. **Correction: delivered** as `docs/OX-ALPHA-DIRECTIVE-CP-02.md` and `docs/SWS-UI-001-v1.2-ADDENDUM-02.md`.

### F-12 · Stop-condition set is incomplete

§8's list is good and misses the failure modes above. **Add:** `VRAM_BUDGET_UNACCOUNTED` · `DUAL_EVICTOR_CONFLICT` · `ROUTER_MODE_UNAVAILABLE` · `GGUF_SOURCE_UNAVAILABLE` · `CONTEXT_DEMOTION_STRANDS_REQUESTS` · `TIME_BUDGET_EXCEEDED`.

---

## What carries forward unchanged

§0's split of SHALL and SHALL NOT · §2 and §3's preservation of the vendor-blind resolver and capability vocabulary · §4 and §5's refusal to redesign accepted state machines · §26–27's runtime/model/artifact identity separation · §29's "Ollama remains the production default" · §41's fail-closed ingestion · §51–52's fallback visibility and the infrastructure-versus-reasoning distinction · §57's speculative-execution prohibition with the 8 GiB reasoning stated · §60's NVFP4 correctness gate · §63–64's refusal to smuggle remote routing in under "node awareness" · §71's rollback rule · §75's `UNEXPECTED = 0` diff discipline · §76's separation of validation from promotion · §81's hierarchy.

That is most of the document, and it is right.

---

*Every finding above is tagged `FACT[path:line]` where an artifact supports it, or ABSENT where a search returned nothing. Recommendations authorize nothing; the operator issues the envelope.*
