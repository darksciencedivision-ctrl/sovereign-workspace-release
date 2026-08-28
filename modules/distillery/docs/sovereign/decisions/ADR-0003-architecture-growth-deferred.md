# ADR-0003 — Architecture growth removed from v1 scope

**Status:** PROPOSED (awaiting operator acceptance) — depends on OQ-004
**Date:** 2026-08-19
**Relates to:** F-1, C-1, C-5, ADD-1

## Context
The design conversation proposed capacity-threshold growth: `SOV-3B → SOV-7B → SOV-14B → SOV-32B`. Modelled VRAM requirements (secondary source, not measured on this machine): QLoRA 7B ≈ 8 GB at batch 1 / seq 512 / no gradient checkpointing; 14B ≈ 14 GB; 32B ≈ 28 GB. Available VRAM is 8 GB, less the Windows compositor reserve.

A further contradiction: OBJ-6 requires the final model to fit the operator's hardware. A 32B model does not fit 8 GB even for inference at Q4.

## Decision
Architecture growth beyond the measured local training ceiling is removed from v1 scope. The working envelope is a **1B–3B student under QLoRA with gradient checkpointing**. A 7B student is an experiment to attempt and measure, not a dependency.

## Consequences
**Positive:** the plan becomes executable; effort concentrates on a model size that can actually be trained, evaluated, and deployed on the target hardware.
**Negative:** the Sovereign model will not approach the capability of the larger teachers. Objectives that assume it will (notably "replace external model dependency") must be reframed as bounded per-role targets.

## Revisit condition
Resolve OQ-004. If training can burst to rented GPU compute, this ADR is superseded and the growth ladder returns with a different cost and licensing analysis. If compute is local-only, the ladder is deleted rather than deferred.

## Evidence quality caveat
The VRAM figures above are modelled estimates from a secondary source, not measurements on this GPU. This ADR should be re-examined after the first measured QLoRA run (see ADR-0004).
