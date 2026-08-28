# ADR-0001 — Immutable checkpoint lineage

**Status:** PROPOSED (awaiting operator acceptance)
**Date:** 2026-08-19
**Relates to:** INV-1, INV-2, F-6, R-5

## Context
The Sovereign model is produced by a cumulative sequence of training stages. Each stage depends on the last. Regression from any stage may not be visible until several stages later. Licensing exposure accumulates in the same way.

## Decision
No Sovereign checkpoint is ever overwritten or modified in place. Every training run emits a new immutable candidate with a new identifier. "Promotion" mutates a pointer only. Every training example carries provenance recorded at generation time.

## Consequences
**Positive:** rollback to any prior generation is always possible; a regression can be bisected; a teacher can be excluded and the lineage rebuilt; provenance questions are answerable years later.
**Negative:** unbounded disk growth without a retention policy (R-10); provenance recording adds cost to every generation run.
**Rejected alternative:** overwrite-in-place with periodic backups — cheaper, but loses the ability to answer "which teacher introduced this behaviour," which is the question the project will most want answered.

## Cost of deferring
Provenance is free to add at generation time and impossible to reconstruct afterwards. This decision cannot be retrofitted.
