# Sovereign / Grounded Distillery

Two sibling architectures for locally training small language models, sharing one
infrastructure library under an explicit treaty (2026-08-19):

- **Grounded Distillery** — the production pipeline: deployment-gated specialization of a
  small model on one operator's real agentic workload. No candidate is promoted unless it
  clears a frozen evaluation gate against its incumbent on the measured workload and a
  general-capability floor; that guarantee is bounded by what the evaluation contract
  measures and is not a claim of universal non-regression (thesis §3.3, §45). The local
  training and serving path is provenance-tracked; admitted evidence may originate from
  separately classified external providers.
- **Sovereign Distillery** — the model-development research architecture: how a persistent
  model lineage acquires and accumulates capability from a heterogeneous ecosystem of
  teacher models within a measured compute envelope.

## Documents

| Document | Status |
|---|---|
| [`docs/THESIS.md`](docs/THESIS.md) | Frozen Grounded Distillery thesis, **v1.1 historical evidence** |
| [`docs/THESIS-v1.2.md`](docs/THESIS-v1.2.md) | **v1.2 post-audit remediation candidate** and current operational status |
| [`docs/SPEC-v1.1-draft.md`](docs/SPEC-v1.1-draft.md) | Normative design specification, **v1.1 DRAFT** — proposed amendment to the frozen v1.0 |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Integration decisions and unresolved operator authorities |
| [`docs/SHIP_CHECKLIST.md`](docs/SHIP_CHECKLIST.md) | Evidence-backed release checklist |
| [`docs/integration/RC3_INTEGRATION_MAP.md`](docs/integration/RC3_INTEGRATION_MAP.md) | RC3-to-canonical surgical integration record |
| [`docs/integration/SOVEREIGN_CANON_IMPORT_MAP.md`](docs/integration/SOVEREIGN_CANON_IMPORT_MAP.md) | Selective, hash-preserving Sovereign canon import record |

The frozen v1.0 documents remain private; the spec's §13 changelog records every
v1.0 → v1.1 delta. No raw trace content, corpora, weights, secrets, or client material
enters this repository. Privacy-minimized G0 evidence may record hashes, model/source
identity, outcomes, and measurements.

## Status

PR #1 is merged. Shared Grounded/Sovereign infrastructure exists once, with
project-specific policy kept separate, and the imported Sovereign canon is covered by a
two-sided treaty contract. New live QUICK-success and controlled DEEP-cancellation
sessions received actual operator `/success` and `/fail` marks, so G0-A/B/C/D and HG-0
are PASS. HG-3 is `BLOCKED_HARDWARE_CAPACITY`: the historical gfx906 target was not
found, the measured 8 GiB-class development node is not substituted, and the
capability-defined primary trainer remains unassigned. G2–G6 have not started, and no
model has been promoted or deployed. The current evidence and gate state lives in
[`docs/THESIS-v1.2.md`](docs/THESIS-v1.2.md) §41.

## Authors

- [ryguy-pixel](https://github.com/ryguy-pixel) — trace pipeline architecture,
  agent/gateway/observability stack, workload, hardware, Grounded synthesis
- Samuel Lawson ([@darksciencedivision-ctrl](https://github.com/darksciencedivision-ctrl)) —
  Sovereign Distillery architecture; evaluation band structure, M/T/D threshold semantics,
  variance calibration, provenance/exclusion machinery
