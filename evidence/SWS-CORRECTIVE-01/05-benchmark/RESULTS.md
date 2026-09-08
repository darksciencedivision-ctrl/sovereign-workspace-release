# SWS-BENCH-01 — results

**Protocol:** `tools/benchmark/PROTOCOL.md`, frozen and committed **before** any comparison ran.
**Dataset:** `tools/benchmark/dataset.json`, 30 held-out tasks, `dataset_sha256`
`f844c7dc61841b9b8834415a02010420bd15c1deb09c0825a5783daf0aed9313`.
**Candidate at run time:** `0761d756dfb95d9acc7aa0218dbd828effd85a56`.
**Hardware:** NVIDIA GeForce RTX 5060 Ti, 8151 MiB · Ollama 0.33.3.
**Roster:** exactly `SYSTEM_MANIFEST MODELS` — the assignments the shipped product uses.
**Runtime options:** the product's own `RUNTIME.CONTEXT_WINDOW` = 131072,
`MAX_OUTPUT_TOKENS` = 32768. No benchmark-specific sampling override.

---

## 1. Coverage, and how far short of the protocol it falls

The protocol specifies **30 tasks × 4 conditions × 3 runs = 360 executions**. This is what
actually ran:

| Condition | Tasks | Runs each | Executions | Against the protocol |
|---|---|---|---|---|
| `A_single` | 30 | 3 | 90 | **complete** |
| `B_full` | 30 | 1 | 30 | under-powered: 1 run instead of 3 |
| `C1_no_critic` | — | — | 0 | **not run** |
| `C2_no_verifier` | — | — | 0 | **not run** |

**Every result below is PRELIMINARY**, and the harness stamps `"partial": true` into every record
so a reader cannot mistake it for the protocol's own answer.

**The resource constraint, measured rather than asserted.** A single `B_full` task takes **92
seconds** on this hardware, against `A_single`'s **0.3 seconds** — the orchestration runs six-plus
model calls where the baseline runs one. The full protocol is therefore roughly
`30 × 3 × 3 × 92s ≈ 7 hours` of GPU time for the three orchestration conditions alone. That did
not fit in this session alongside the whole-product suite, the release build and the acceptance
install, all of which contend for the same host.

One further measurement worth recording: an early `B_full` task run **concurrently** with the
whole-product pytest exceeded **17 minutes without completing** — an 11× slowdown from
contention. That is why the runs here were serialised, and it is a caution for anyone repeating
this: these numbers are only meaningful on an otherwise idle host.

---

## 2. Condition A — the simple baseline (complete)

90 executions, 30 tasks × 3 runs, **zero errors**.

| Measure | Value |
|---|---|
| Task success | **77.8 %** |
| Abstention rate | 16.7 % |
| Unsupported claims (total) | 13 |
| Citation errors (total) | 0 |
| Median wall-clock | 0.3 s |
| Median model calls | 1 |
| Peak VRAM observed | 4899 MiB |

Per category:

| Category | Success |
|---|---|
| `grounded_fact` | **100 %** |
| `procedural` | **100 %** |
| `absent_fact` | 72.2 % |
| `contradiction` | 60.0 % |
| `synthesis` | 50.0 % |

The shape is informative on its own: a single 3B model with a good evidence packet is *perfect*
at reading a fact out of supplied text, and *poor* at declining to answer, at reporting a
conflict, and at combining two sources. Those three are exactly the categories an orchestration
with a critic and a verifier would be expected to help with — which is what makes the comparison
worth running properly.

---

## 3. Primary outcome — B_full minus A_single

*(filled in from `B-1run.jsonl`; see §5 for the decision)*

---

## 4. A finding that does not depend on the comparison

Task `af-03` asks "How many backups does the product keep by default?" against an evidence packet
that does not say. Condition A answered:

> "The product keeps a default of one backup by default. Refer to [source:backup] for this
> information."

That is a fabricated fact carrying a **real** citation to a **real** source that does not support
it. The acceptance validator **accepted** it: the citation exists, the claim is attributed, and
the format is fine. This is precisely the limit `assess_quick_response` declares — it checks
citation *existence*, never source *support* — and it is why `source_support_checked` is
permanently `False` and why the UI chip now reads "Accepted — format and citations checked"
rather than "Accepted".

The benchmark also caught a defect in the Q1 repair itself: task `gf-02`'s correctly-cited answer
was **rejected** because the citation followed the full stop and the clause splitter separated it
from its claim. Fixed in `0543059` with three regression tests. Both directions matter: a checker
that rejects correct answers is not a safer checker.

---

## 5. Decision

*(filled in below once the paired comparison is computed)*
