# CP-M1-G2-RESOLUTION — Reviewer note on the PROVIDER_SPEND_CONTRADICTION stop

| Field | Value |
|---|---|
| Trigger | CP-M1 G2, `PROVIDER_SPEND_CONTRADICTION`, 2026-08-25T08:58Z. `docs/STOP-REPORT-CP-M1.md`. |
| Builder conduct | **Correct in full.** G1 TRUE, G2 FALSE, stopped. No interpretation attempted, no product tree touched, `evidence/GATE-LEDGER.json` byte-identical (`176429fc4012ce57c1a19558e7aaed55e7f37ca268be0fdd067996fe79b8fc77`), three evidence files and the stop report written, no builder-started processes, ports clear. Nothing to correct. |
| **New finding** | **The builder's option 1 does not work, and CP-M1 G26 is unsatisfiable as written. That is a defect in my directive, not in the stop.** |
| Standing | Reviewer note. Authorizes nothing. |

---

## 1. What the stop report could not know

`modules/sow/control_plane/conductor/registry.py` holds `CONDUCTOR_MODEL_REGISTRY` with exactly three entries:

| provider_id | model_id | conductor_capable | locality |
|---|---|---|---|
| `openai_codex_cli` | `gpt-5.6-sol` | true | frontier |
| `claude_code` | `fable-5` | true | frontier |
| `claude_code` | `opus-4.8` | true | frontier |

`locality` defaults to `"frontier"` on the dataclass, and resolution refuses anything absent from the registry — *"provider/model … is not a registered conductor-capable …"*.

**There is no local conductor-capable model. Not one.**

Two consequences:

- **The builder's option 1 — set `live_operation_authorized: false` — strands the Conductor.** `LIVE_OPERATION_AUTHORIZED` is the frontier spawn gate; with it off, every conductor-capable registration becomes unspawnable. Band 4 (G25, G26 — R-04, "Conductor communication is P0") would be unreachable, and the loop would take a **second STOP** there, several hours in.
- **CP-M1 G26 says the Conductor leg "runs on a local model."** Against this registry that predicate cannot be satisfied by any configuration. I wrote a goal that assumed a local Conductor was merely unselected; it is in fact unimplemented. R-04 cannot be proven under a no-spend authorization without new feature work.

## 2. The real option set

| | Resolution | Spend | New work | R-04 provable |
|---|---|---|---|---|
| **A** | Narrow scope to one provider + bounded spend | Yes, bounded | None | **Yes, as designed** |
| **B** | Local-capable Conductor | None | A real feature | Yes, after the feature |
| **C** | Defer Band 4 | None | None | **No** |

### A · Narrow the scope, bound the spend — recommended

Keep `live_operation_authorized: true`, cut `scope.providers` to `["openai_codex_cli"]` alone, and authorize spend for **only** the Conductor leg and the acceptance chain's API-model leg. The Conductor works exactly as it is configured today; `terminals_per_subscription: 1` already caps concurrency; `grok_build`, `google_antigravity` and `claude_code` legs record `NOT_RUN(NO_SPEND_AUTHORIZATION)`.

This is the only option that proves R-04 without inventing a feature mid-package, and it makes the acceptance chain's API leg a live proof rather than a recorded absence. It is also, plainly, your normal working configuration — the Conductor is already bound to Codex.

The cost is real money on one subscription, for a handful of Conductor turns and one worker round-trip.

### B · Give the Conductor a local model

Set the gate false, add a local conductor-capable registration (`ollama_local` plus a qwen3-class tag), and rebind `config.conductor` to it. Zero spend, and it advances the local-first direction the whole modernization is pointed at.

But it is **new scope inside a running package** — precisely the drift CP-M1 §9 forbids. The launch shape differs from a vendor CLI: an Ollama conductor needs the interactive-session argv that `adapters/local/ollama_session.py` already builds, wired into the conductor pane path. The pieces exist; the assembly does not. Estimate one band's worth of work, unbudgeted, before Band 4 can start.

Defensible as a deliberate decision. Not defensible as a way to avoid a spend question.

### C · Defer Band 4

Gate false; amend G25/G26 to `NOT_RUN(NO_CONDUCTOR_MODEL_AVAILABLE)`. Truthful and free. R-04 — the requirement your original directive marked **P0** — stays unproven, and Band 5's worker round-trip loses the Conductor leg it depends on. Recorded here for completeness; I do not recommend it.

## 3. Amendment required under every option

Independent of the choice, **CP-M1 G26 must be corrected** — it asserts a local Conductor leg that no configuration can deliver. Replacement text:

> **G26 — Round-trip: human → Conductor → human.** `evidence/cpm1/8d/conductor-roundtrip.txt`: a directive typed into the surface; the Conductor's response returned into the transcript; a follow-up in the same thread demonstrably carrying prior context; and an interrupt or redirect exercised, or recorded `UNSUPPORTED(<reason>)`. **The Conductor leg runs on whichever conductor-capable model the operator's spend authorization permits, recorded by name and provider in the artifact.** Absent any permitted model, the goal is satisfied by `NOT_RUN(NO_CONDUCTOR_MODEL_AVAILABLE)` naming the registry entries examined — and Gate 8d's note states R-04 unproven. A Conductor communication failure surfaces as `CONDUCTOR_COMMUNICATION_FAILED` (G17), not as silence.

**And one envelope correction.** `modules/sow/config/**` sits in Package B's cap (150 lines), but `live_operation.json` and the conductor binding are needed in Band 0 and Band 4 — Package A. Add `config/**` to the Package A control-plane area at the same 400-line cap, or make the edits yourself outside the builder's envelope entirely. The second is cleaner: a spend authorization edited by the party that owns spend.

## 4. One incidental host fact worth keeping

The builder recorded at closeout that **:8700 is now free** — the operator-side Debate process that held it through the Gate 7b and CP-01 sessions is gone. Two goals depend on that observation: G13's cold-start proof and G14's `EXTERNAL` legibility capture both need a live `EXTERNAL` state to photograph. With :8700 free, Band 2 will have nothing external to observe unless something is started deliberately.

Not a blocker — G14 can be satisfied against a deliberately started external process — but it needs to be a decision rather than a surprise at Band 2.

---

*Registry facts read from disk 2026-08-25T09:0xZ. This note authorizes nothing; §5 of the stop report and the operator's sentence do.*
