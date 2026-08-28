# ADR-0004 — The evaluation suite is built and frozen before the first training run

**Status:** PROPOSED (awaiting operator acceptance)
**Date:** 2026-08-19
**Relates to:** INV-3, INV-6, INV-7, F-7, R-6, R-7

## Context
The source design contains a `PASS?` promotion gate but no definition of pass. Three consequences follow:

1. Immutable lineage (ADR-0001) provides the *ability* to roll back but no *signal* for when to.
2. "Differential evaluation" — the intellectual core of the Distillery, deciding what a teacher contributes that the student lacks — requires measuring teacher and student on a common instrument. No such instrument exists.
3. LLM-as-judge (Debate Table) carries known position, verbosity, and self-preference biases. It is a useful additional signal and an unsound sole gate.

## Decision
A frozen, versioned evaluation suite is constructed **before** the first teacher is processed. It contains a deterministic machine-checkable band, a monotonically growing regression band, a private held-out set never used for corpus generation, and an advisory band (Debate Table) that is recorded but does not gate.

No training run occurs before the suite exists, because its result would be uninterpretable.

## Consequences
**Positive:** every subsequent claim about the Sovereign model becomes falsifiable; regression is detectable; differential evaluation becomes implementable rather than aspirational.
**Negative:** delays the first training run by the time it takes to build the suite. The reviewer regards this as the highest-value delay available in the project.

## Companion requirement
Establish run-to-run variance on the suite before setting the promotion margin and regression tolerance (OQ-005). Thresholds set below the noise floor produce a gate that is either always or never passed.
