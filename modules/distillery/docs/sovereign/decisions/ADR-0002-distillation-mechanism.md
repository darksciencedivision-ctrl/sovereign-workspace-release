# ADR-0002 — Offline black-box distillation as the primary mechanism

**Status:** PROPOSED (awaiting operator acceptance)
**Date:** 2026-08-19
**Relates to:** INV-4, F-1, F-2

## Context
The operator's terms "distill," "clone," and "cannibalize" map to three distinct mechanisms with different feasibility on the stated hardware (RTX 5060 Ti, 8 GB).

| Mechanism | Requirement | Feasible on 8 GB? |
|---|---|---|
| (a) White-box / logit-level KD | Shared tokenizer, or a cross-tokenizer method; teacher + student co-resident | No — co-residency roughly doubles peak memory |
| (b) Black-box / sequence-level KD | Nothing beyond the ability to run each model separately | Yes |
| (c) Weight-level transfer (merge, task vectors, layer transplant) | Same architecture **and** same tokenizer, usually same base | Cross-family: no established method exists |

Cross-tokenizer KD is real active research (ULD, DSKD, MultiLevelOT, ALM, X-Token), but the ALM authors limit their published claims to 2.4B–3.3B models and report persistent transfer degradation and inconsistent variant selection (arXiv 2503.20083v2).

## Decision
Offline, black-box, sequence-level distillation is the primary and default mechanism. Teacher generates → corpus persisted → student trains in a separate process.

- White-box KD is a **research track**, attempted only if a same-tokenizer teacher/student pair exists and memory permits.
- Cross-family weight transfer is **out of scope**. Same-family merging may be revisited if OQ-002 reveals same-family teachers.

## Consequences
**Positive:** tokenizer- and architecture-agnostic; fits the hardware; decouples generation from training; corpora are inspectable, auditable, and reusable across student generations.
**Negative:** discards the richer signal in teacher logits; student capability is bounded by teacher *outputs* rather than teacher *distributions*; requires substantially more generated tokens for equivalent transfer.

## Note on the operator's framing
"Cannibalize" maps cleanly onto (b) and only onto (b). This is not a reduction of the concept — (b) is the mechanism behind most well-known distilled small models. Recording it explicitly prevents repeated failed attempts at (c).
