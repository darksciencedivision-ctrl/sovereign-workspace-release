# D-HW-01 — Grounded Primary Trainer Reality Rebaseline

| Field | Value |
|---|---|
| `decision_id` | `D-HW-01` |
| Date | 2026-08-21 |
| Status | ACCEPTED — OPERATOR |
| Scope | Grounded hardware implementation plan before HG-3 |
| Operator authority | SOVEREIGN / GROUNDED DISTILLERY HARDWARE REALITY REBASELINE PRE-HG-3 OPERATOR DIRECTIVE |

## Decision

The assumed 32 GiB gfx906 trainer is retired as an unverified planning target. Bounded authorized discovery found no physical machine or configured access route. Historical expected properties remain evidence, but they are not measurements and no longer define the universal Grounded trainer stack.

Grounded now uses a capability-defined primary trainer requirement. `GND-TRAINER-PRIMARY` remains `UNASSIGNED` until a physical machine is designated and measured.

## Old assumption and discovery evidence

The v1.1/v1.2 plan assumed a gfx906-class Vega 20 / MI50-family card with 32 GiB VRAM, torch 2.7, ROCm 6.3, FP16 LoRA, and two gfx906 compatibility variables. That assumption did not name a host or access route.

The authorized discovery record at [trainer-discovery evidence](../../runs/HG-3/trainer-discovery/evidence.json) searched canonical and imported documents, histories, SSH and terminal configuration, remote-development targets, launchers, inventory files, and existing network caches. It found no target. `GND-TRAINER-GFX906` therefore preserves `status=TARGET_NOT_FOUND` and `disposition=RETIRED_AS_UNVERIFIED_PLANNING_TARGET`.

## Measured workstation

`GND-DEV-EXEC-01` is the locally accessible development execution node:

| Property | Measured value |
|---|---|
| Host | `DESKTOP-03PTABH` |
| OS | Windows 11 Home build 26200 |
| GPU | NVIDIA GeForce RTX 5060 Ti |
| VRAM | 8151 MiB |
| Driver | 610.74 |
| Status | `ACCESS_VERIFIED_LOCAL` |

It is not the primary Grounded FP16 trainer.

## Memory analysis

Nominal FP16 static-weight memory is approximately:

| Candidate class | Calculation | Static weights only |
|---|---:|---:|
| 4B | 4,000,000,000 × 2 bytes / 2³⁰ | 7.45 GiB |
| 8B | 8,000,000,000 × 2 bytes / 2³⁰ | 14.90 GiB |

These estimates exclude activations, allocator overhead, LoRA adapters, gradients, optimizer state, temporary buffers, attention workspace, and sequence-length growth. The 8151 MiB workstation must not be represented as satisfying the canonical 4B/8B FP16 HG-3 contract without contrary measured evidence.

## New capability requirement

Hardware requirement v1 for `GND-TRAINER-PRIMARY` is:

- provisional minimum usable VRAM: 24 GiB;
- preferred VRAM: at least 32 GiB;
- no vendor or GPU architecture selected before physical designation;
- backend stack selected and pinned after hardware is measured;
- FP16 LoRA remains the canonical HG-3 lane;
- QLoRA remains an experimental alternate path and cannot prove the FP16 lane.

The 24 GiB value qualifies bounded architecture smokes; it does not guarantee every sequence length. At least 32 GiB is preferred for sequence headroom, batch flexibility, stable 8B FP16 operation, retraining cadence, and reduced OOM pressure.

## Software consequence

The former torch 2.7 / ROCm 6.3 / gfx906 / `HSA_OVERRIDE_GFX_VERSION=9.0.6` plan is classified `HISTORICAL_GFX906_PLANNED_STACK`. Future NVIDIA hardware receives a CUDA-qualified stack; future AMD hardware receives a ROCm-qualified stack. Grounded remains backend-portable where practical.

## Effect on HG-3

HG-3 becomes `BLOCKED_HARDWARE_CAPACITY`.

Exact blocker:

> NO DESIGNATED MACHINE CURRENTLY SATISFIES THE GND-TRAINER-PRIMARY CAPABILITY CONTRACT.

Candidate identity is resolved and trainer discovery is closed. HG-3 resumes only after a real machine is registered, VRAM is measured, the backend stack is selected and pinned, a read-only environment probe passes, and separate compute authorization is granted.

## Effect on project objective

This decision does not change the Grounded objective, pinned Qwen3 4B/8B candidates, from-base doctrine, workload specialization, source-admission policy, evaluation architecture, M/T/D controls, Sovereign/Grounded treaty, or future ability to use AMD hardware. It changes only the hardware implementation plan.
