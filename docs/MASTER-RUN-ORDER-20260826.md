# MASTER RUN ORDER — one loop, four phases, 2026-08-26

| Field | Value |
|---|---|
| Purpose | Carry **three** bodies of work through **one** continuous unattended session: CP-M1 (98 goals), SPA v1.3, and the Multi-Model Terminal P1 block. |
| Authority | Operator delegation in session, verbatim: *"I need that entire directive done tonight… it needs to be one loop directive that does complete tonight… Even if it has to do the SPA discovery followed by execution, that's fine as well."* Plus the SPA marks at `docs/SPA-OPERATOR-MARKS-DELEGATED.md`. |
| Governing concept | `SWS-UI-001-ADD-05 v1.1` — skip-and-continue, skips propagate, halt only on record corruption or irreversible damage. **Unchanged and applied to all four phases.** |
| Single-writer rule | **One session. One writer.** This is what makes the merge safe: two agents editing `modules/sow/**` from opposite directions corrupts it; one agent doing CP-M1's edit and then SPA's edit does not. There is no window between phases in which a second party can move the tree. |

---

## 0. Why this order, and not the obvious one

The obvious order is CP-M1 first — it is the running package. **That order is wrong tonight**, for one reason: CP-M1's 98 goals will absorb every remaining hour, and the two blocks that can actually *finish* would never start.

| Phase | Body | Size | Finishable tonight? |
|---|---|---|---|
| **1** | SPA discovery (S-1…S-5) | ~5 read-only items | **Yes**, and it unblocks the next session |
| **2** | SPA Track A (§6.1–6.5, §7) | 4 units + gate + 4 more | Partly — hard-blocked if the bundle is absent |
| **3** | MT-P1 (MT-05…MT-08) | 4 items | **Yes** |
| **4** | CP-M1 G28–G124 | 98 goals | **No.** Absorbs the remainder; stops where the night stops |

Ordering finishable work first means a short night yields two closed blocks plus partial CP-M1, instead of one partial block and two unstarted ones.

**A second reason.** SPA and MT both write a tree CP-M1 currently treats as a **protected read-only root**. Doing that work *before* CP-M1 re-enters its bands lets Phase 4 re-baseline that root once, cleanly, instead of tripping a protected-source observation on every goal for the rest of the night.

## 1. Phase 0 — tree resolution (do this first, it decides everything)

The two later phases target "the SOW tree", and **which tree that is has never been verified**. Resolve it by discovery, then apply the rule already decided here — do not deliberate at runtime.

Find the tree holding `tools/run_phase19_gate.py` and `docs/loop/LOOP_STATE.json`. Record its absolute path and git HEAD.

| Finding | Rule |
|---|---|
| It is **`D:\multi model terminal app\sovereign-orchestration-workspace`** (or another tree outside `Production Workspace`) | **Expected.** SPA and MT operate there. Phase 4's CP-M1 work is in `Production Workspace` and is disjoint. Proceed. |
| It is **inside `D:\Product Software\Production Workspace`** | SPA/MT and CP-M1 share a tree. **Still proceed** — one writer, strictly sequential, is safe. But Phase 4 re-captures `before-a/` for any file Phases 2–3 touched, so CP-M1's changed-line accounting stays honest. |
| **Both** trees hold a Phase-19 gate runner | Record it as a finding, then operate on the **multi-model-terminal** tree for SPA and MT, because MT's own constraints name `product/multi-frontier-v2` and `apps/desktop/ipc/client.js`. Note the ambiguity loudly in the final report. |

## 2. Phase boundaries — what closes each one

**Phase 1 → 2.** Discovery report written. If `sovereign-production.skill` v2.0 is **absent**, SPA P2 stops mutable work: **Phase 2 is `NOT_RUN(BUNDLE_ABSENT)` in its entirety** and the loop goes straight to Phase 3. Do not reconstruct the bundle from PDFs or v1.1 — that is a forbidden action and it is not a close call.

**Phase 2 → 3.** Track A units tagged or recorded `NOT_RUN`. `gate/phase-19` earned or its non-earning documented with a classified reason.

**Phase 3 → 4. SCOPE HANDOVER, and it must be explicit.** Phases 2–3 wrote a tree that CP-M1's Band-0 manifests recorded as protected. Before Phase 4 resumes the ladder:

1. Write `evidence/cpm1/scope-handover.md` naming every file Phases 2–3 changed in that root, with before/after hashes.
2. Re-capture the protected-root manifest for that root **only**, superseding the Band-0 artifact by name, with this document cited as authorization.
3. State plainly in Gate 8j's note that the root was writable during Phases 2–3 by operator authorization, and read-only before and after.

**Without this, CP-M1's protected-source claim becomes retroactively false, and that is the one kind of damage this whole run exists to prevent.**

**Phase 4 → end.** G124, or the night ends. Either is an acceptable outcome; the run log records precisely where.

## 3. What is *not* in this run, and why

| Excluded | Reason |
|---|---|
| **MT-01** live conductor bring-up | The punch list marks it **attended-only** in its own text. No live provider call is declared. |
| **MT-09** freeze-manifest signature | Operator-only. Cannot be delegated — it is a signature, not a decision. |
| **MT-10** Phase 19 endgame | Gated absolutely on MT-09. |
| **MT-28 / MT-29** Electron EOL, npm advisories | Require installs. Attended-only. |
| **SPA Track B / Track C** | Gated on `gate/phase-19`, B2, B3, Q2. Not reachable tonight. |
| **SPA `PRODUCT_EXTENSION`** | R-7 **STRUCK** under delegation. Product trees stay byte-identical; an integration needing one becomes `[OPEN]`. |

## 4. Standing decisions carried into all four phases

Every rule from `ADD-05 §4` and `§5` binds unchanged: skip-and-continue, propagating skips, one attempt plus one retry, a 45-minute per-item ceiling, `C-8(b)` detached launches with OS-owned output, quota exhaustion as a skip, the 25-turn spend ceiling with at most 10 on `openai_codex_cli`, `grok_build` preferred first, never `fable-5`.

**Two halts only, across all four phases:** corruption of a record (gate ledger, register, evidence already submitted), or damage that cannot be undone. *Something breaking is a halt. Something refusing is not.*

**Never write a stop report that asks a question.** The operator is asleep. Record the finding, record `NOT_RUN`, take the next item.

## 5. The honest expectation

**This will not all finish.** 98 CP-M1 goals plus SPA Track A plus four MT items is more than one night holds, and a directive that claims otherwise is lying to the operator who has to read it in the morning.

What this order guarantees instead: the two finishable blocks are attempted **first**, the expensive block absorbs the remainder, nothing stalls waiting for a human, and the run log names the exact item where the night ended so the next session starts there without re-deriving anything.

A partial run, precisely recorded, is a good outcome. A complete-looking run built on skipped dependencies is not.
