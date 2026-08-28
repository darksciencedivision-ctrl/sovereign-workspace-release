# G2 tracked work items

These items are recorded by the post-audit remediation and are not authorization to begin
G2 or invent new architecture before the evaluation-freeze phase.

## GR-8 — General E7 acceptance

Status: **TRACKED_FOR_G2**

Generalize E7 acceptance from the named `x-*` / `y-*` synthetic fixture to arbitrary generated
lineage graphs. Property-based or deterministic seeded generation must cover variable depth,
branching, multiple roots, retained unrelated subgraphs, dangling-edge detection, and idempotent
exclusion. Later acceptance must operate on a real-client purge request without committing
private client content.

The existing descendant-closure implementation remains shared and general. This work item is
about the acceptance harness and real-client evidence boundary, not replacing the algorithm.

## GR-9 — Historical aggregate to paired-vector bridge

Status: **TRACKED_FOR_G2**

Define the versioned bridge from `HistoricalBestStore` promotion-time aggregate records to the
per-item historical reference vector consumed by `paired_gate`. The bridge must preserve suite
identity, item identity, governed promotion selection, run aggregation, and missing-item failure
semantics.

Hard invariant: **the historical-best vector must never be constructed as per-item maxima across
checkpoints or runs.** Per-item maxima would synthesize a model that never existed and silently
reintroduce lucky-run selection. The vector must come from one governed historical reference
bundle/aggregate selected under the frozen suite contract.
