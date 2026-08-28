# Grounded Distillery v1.1 — RC3 Canonical Integration

## Review anchors

- Canonical baseline: `f1904399ffc8cc357b2d413127b406fedf44b903`
- Accepted integration commit: `c3594cfc6284b7b5008bb131434436d5a3a77c9a`
- Greenfield provenance: `a332e68823ab426310c5d37f3c0bfed5c52cc1f0`
- Integrated tests at accepted integration commit: 25/25
- Original RC3 tests: 23/23

## Integration boundary

Shared validators, source admission, shard sealing, transitive exclusion, gates, evidence, promotion mechanics, and trainer-card locking have one canonical implementation. Grounded-specific curation, telemetry, CLI, and Sovereign evidence adapters remain under `grounded/`. See `docs/integration/RC3_INTEGRATION_MAP.md`.

The canonical treaty documents were amended in place. Sovereign research objectives and the D, HG, SL, G, and E namespaces remain intact. No repository-wide license was inferred; the owner license decision remains unresolved.

## Validation and operations

- No G2/G3/G4/G5/G6 execution.
- No deployment, model promotion, router promotion, or automatic merge.
- G0 status at `c3594cf`: partial. The post-integration branch evidence subsequently completes real G0-A/B/C/D, dashboards, alert paths, and checksum guards and supports HG-0 PASS.
- Every candidate source admission remains `UNKNOWN`; no permissive model-artifact license caused a classification transition.
- No prompts, outputs, corpus data, model weights, credentials, raw runtime records, or reversible source-session identifiers are tracked.

Please review; do not merge automatically.
