# PARKED — L5-5: a LIVE worker leg for a LOCAL worker

**Directive:** `release-planning/EPC-03-DIRECTIVE-20260831.md`, Layer 5, item L5-5.
**Parked under:** D-6 ("any item that cannot be completed honestly is parked with a dossier naming
the blocker and bounded options").
**Date:** 2026-08-31.
**Status:** the guard is UNCHANGED and still satisfied. No live worker leg is claimed.

---

## What L5-5 asked for

> `legs.workers` may become `live` **only** through the existing evidence derivation —
> `_assert_legs_honest` unchanged and still satisfied.

And in the directive's own words, immediately after:

> **L5-5 is the honesty line of this whole loop.** A live worker leg is derived from evidence by
> the packet builder. If it cannot be derived, the leg stays `mock` and the loop says so.

This is the loop saying so.

---

## The blocker, measured

`live_flow.derive_worker_legs` classifies each worker from an evidence row
`{node_id, leg, adapter, executed, spent, verified, model, tasks}`:

```
if not executed            -> skipped
elif leg != "live"         -> mock
elif verified              -> live
elif spent                 -> attempted
else                       -> skipped      # "reached no model at all"
```

A local Ollama pane that answered a delegated task produces:

| field | value | why |
|---|---|---|
| `executed` | `true` | it ran and answered |
| `leg` | `live` | a real model produced the text, not a mock backend |
| `spent` | `false` | invariant 19 — a local node is not subscription-governed and spends nothing |
| `verified` | `false` | a screen read cannot attest which model produced the characters |

That row falls to the final `else` and is classified **`skipped`** — with the comment *"reached no
model at all"*, which is the one thing that is definitely untrue about it.

The derivation is not wrong. It was written for subscription-backed frontier workers, where
`spent` is the proxy for *a call actually happened*, and for those workers it is exactly right.
It simply has no vocabulary for a worker that **executes without spending**, because until this
loop no such worker could execute at all.

## The two ways to force it, and why neither was taken

1. **Set `spent: true` for a local call.** It would land the row on `attempted` and read
   plausibly. It also puts a spend on the record for a call that cost nothing. Directive §6 names
   under-reporting spend as the dishonest direction; over-reporting it is the same instrument
   lying in the other direction, and a spend record that includes free calls stops being usable
   for the thing it exists for.

2. **Set `verified: true` because the daemon reported the model tag.** `OllamaConductorBackend`
   already refuses this reasoning for its own decisions: *"a CANDIDATE must never read as a
   confirmed checkpoint"*. The frontier path verifies a vendor checkpoint id datable to the call
   just made. Reading a model tag off a screen is not that, and a screen read cannot attest even
   the tag — the text could have come from anything typed into that pane.

Both are edits to `_assert_legs_honest`'s inputs designed to change its output, which is what
EPC-03 §3 names untouchable and what §5 calls a parking condition.

## What was delivered instead

The delegated answer is carried as **observation evidence**, not as a leg:

* `apps/desktop/control/conductor-delegation.js` produces a candidate marked
  `self_published: false`, `source: "observed_pane_output"`, with a note stating it is weaker
  evidence than a node's own publication.
* `control_plane/orchestration/pane_observation.py` folds observations into a record that carries
  **no `legs` key at all**, deliberately, so a reviewer can see from the shape that it cannot make
  an execution claim. A unit test asserts the absence.
* `legs.workers` stays `mock` and `live_workers_owed` stays `owed: true, issue: U58`.

So the conductor can now delegate to a local pane, inject a prompt through the gated write path,
and read the answer back — and the acceptance packet still refuses to call that a live worker leg.
Those two facts are both true and the record says both.

## Bounded options for the operator

**Option A — extend the derivation to name local execution (recommended).**
Add a fourth outcome for a row that executed on a `local` adapter with no spend: not `live`, not
`skipped`, but a distinct leg (`local`) with its own rule. This is a change to
`derive_worker_legs` and therefore needs the operator's authorization, because it changes what an
acceptance packet can say. It is additive: no existing row's classification changes, and
`_assert_legs_honest` gains a case rather than losing one.

**Option B — give local panes a way to publish for themselves.**
The real asymmetry is that a frontier coding agent holds Sovereign MCP tools and a local REPL does
not. A small supervised shim that lets a local pane call `publish_candidate` would make its
candidate the node's own claim, and then the existing derivation applies unchanged. Larger, and it
is the architecturally correct answer.

**Option C — leave it parked.**
The conductor delegates and reads back; the leg stays `mock`; U58 stays owed to gate 16F, which
already owns it. Nothing is claimed that is not true, and the capability the operator asked for
works. This is the current state and it is a legitimate resting place.

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
