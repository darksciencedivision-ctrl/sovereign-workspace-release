# Sovereign Distillery invariant register

This register consolidates the accepted Sovereign invariants that were distributed across
the provisional [`SPEC.md`](SPEC.md), accepted [`DECISIONS-v1.md`](DECISIONS-v1.md),
evidence-grounded [`DESIGN.md`](DESIGN.md), and the accepted corrections recorded by
[`reviews/THESIS_REVIEW-v1.1.md`](reviews/THESIS_REVIEW-v1.1.md). It does not convert
proposals or open questions into operator decisions.

| ID | Invariant |
|---|---|
| INV-1 | A Sovereign checkpoint is never overwritten. Every candidate has a new immutable identity; promotion changes a pointer. |
| INV-2 | Every training example carries teacher, generation, prompt-source, time, and license provenance at creation; provenance is never reconstructed later. |
| INV-3 | No checkpoint is promoted without the frozen, versioned evaluation and regression suite. |
| INV-3b | No critical capability regression is promotable; capability criticality is explicit and machine-checkable. |
| INV-4 | Distillation is offline and black-box by default; teacher generation and student training are separate processes. |
| INV-5 | The canonical master and quantized deployment artifacts are separate; a lossy deployment artifact is never a lineage parent. |
| INV-6 | Evaluation suites are frozen and versioned separately; a content change requires a suite-version bump. |
| INV-7 | Held-out evaluation material never enters corpus generation or training. |
| INV-8 | Eligible teachers are examined smallest-to-largest as the declared operational ordering. |
| INV-9 | A teacher with no useful capability delta may terminate as `SKIPPED_NO_DELTA`; forced distillation is forbidden. |
| INV-10 | Teacher ordering is distinct from training-mix composition; cumulative replay remains permitted. |
| INV-11 | Model scale does not increase automatically. |
| INV-12 | Model scale may increase only when capacity evidence and approved compute permit it. |
| INV-13 | Cross-family weight transfer is never assumed; only a compatible, evidenced mechanism may authorize it. |
| INV-14 | Sovereign Distillery remains operable standalone. Its Knowledge Lineage is Distillery-owned and may be synchronized outward. |
| INV-15 | The human operator retains final canonical promotion authority. |

## Governed gate doctrine

Sovereign's promotion gate uses predeclared **M/T/D** policy margins plus criticality:

- **M**: required useful target-capability gain;
- **T**: maximum regression against the immediate parent;
- **D**: maximum regression against the human-governed floor;
- historical best remains an immutable reported fact even when an authorized override
  moves the governed floor;
- a remediation route proves restoration toward the governed floor rather than inventing
  a new target gain;
- final promotion remains human-only.

This governed-floor doctrine is Sovereign-specific policy layered on shared statistical,
evidence, provenance, and promotion infrastructure.
