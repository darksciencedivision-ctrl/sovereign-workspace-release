# SWS-UI-001 v1.2 — ADDENDUM 06: The ladder is a graph, not a chain

| Field | Value |
|---|---|
| Amends | `ADDENDUM-05 v1.1` §2. All other addenda unchanged. |
| ID / version | `SWS-UI-001-ADD-06 v1.0`, 2026-08-26 |
| Cause | The 2026-08-26 run ended after **61 minutes** of a six-to-eight hour window, with ~60 fully reachable goals untouched. The defect was in ADD-05, not in execution. |

---

## 1. The defect, stated plainly

ADD-05 §2 said skips propagate to *dependents*, and that *"independent goals **inside a band** still run."* **Band-scoped, not ladder-scoped.** Combined with CP-M1's ordering rule — *"G(n) is not acted on while G(n-1) is FALSE"* — a single `NOT_RUN` at G28 blocked every goal behind it, including Bands 7 and 12–20, none of which depend on G28 in any way.

The builder followed the directive exactly. The directive was wrong.

## 2. The correction

**The ladder is a dependency graph. `NOT_RUN` blocks only true dependents.**

Replace CP-M1 §7's ordering rule with:

> **The loop always acts on the NEXT REACHABLE GOAL** — the lowest-numbered unresolved goal whose dependencies are all *resolved* (`TRUE`, or `NOT_RUN` in a way that does not block it). "First failing goal" is retired as a concept. A blocked goal is stepped over, not waited on.

## 3. Dependency map — authoritative, use it instead of goal order

A goal depends **only** on what its own predicate consumes. Everything not listed is independent.

| Goal(s) | Depends on | Rationale |
|---|---|---|
| G29, G30 | **G26** (Conductor channel) | Both need a Conductor that can receive a human directive |
| G31 (the "by the Conductor" clause only) | G26 | The machinery half is independent and **must still run** |
| G32 (Gate 8e) | G28–G31 resolved | A gate records outcomes; `NOT_RUN` outcomes are recordable |
| G34–G36 | G33 (opencode present) | G33's own text provides the `NOT_RUN` path |
| G94–G99 | **G38–G43** (registry created) | Band 16 populates what Band 7 creates |
| G81–G86 | G33–G37 resolved | Band 14 widens a Protocol Band 6 leaves narrow |
| G87–G93 | G75–G80 (router mode) | The planner schedules against the router |
| G116–G124 | all prior goals **resolved** | Closeout summarises; it does not require them TRUE |
| **Everything else** | **NOTHING** | Independent. Runs regardless of what came before. |

**Explicitly independent of G26, G28 and of each other:** G33–G43 · G44–G56 · G57–G63 · G64–G67 · G68–G80 · G100–G115. These are local work — registry authoring, llama.cpp pinning, Distillery, Token Center, context truthfulness, fallback accounting, metadata. **No provider. No attended window. No Conductor.**

## 4. Blocked-goal sweep — do this before anything else

Before executing any goal, walk **all 124** and resolve every goal that is *already* known to be unreachable, with its cause. This retires them permanently so they can never block again:

- Needs the operator present (live workers, an attended window) → `NOT_RUN(<cause>)`
- Needs an artifact that does not exist on disk → `NOT_RUN(<cause>)`
- Depends on a goal already resolved `NOT_RUN` per §3 → `NOT_RUN(DEPENDENCY_UNMET: G(n))`

Write `evidence/cpm1/reachability-sweep.md` with all 124 rows: `TRUE` / `NOT_RUN(cause)` / `REACHABLE`. **The `REACHABLE` set is the night's work queue.** Everything else is already finished.

## 5. The completion condition

> **The run is complete when all 124 goals are RESOLVED** — each `TRUE` or `NOT_RUN` with a named cause. **Not when a goal fails. Not when a band stalls. Not when the first blocker appears.**

**The turn does not end while any goal remains `REACHABLE`.** If the harness cuts the turn, resume at the next reachable goal without re-deriving anything. Ending a turn with reachable work outstanding is itself a defect and is reported as one.

## 6. What this changes about ending early

The old loop asked *"is the first failing goal fixable?"* and stopped when the answer was no. The new loop asks *"is anything still reachable?"* and only stops when the answer is no.

A `NOT_RUN` is a **result**, not an interruption. Sixty `NOT_RUN`s with named causes is a finished run. Two `TRUE`s and fifty-eight untouched goals is not.
