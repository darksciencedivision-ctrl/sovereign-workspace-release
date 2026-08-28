# CORRECTION NOTE — read this beside `PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.json`

**Filed:** 2026-07-31, Phase 17E `.close` (iteration 103), on a MAJOR finding (F1) raised by the
`spec-auditor` and a must-fix (MF-C) raised by the `gate-validator`, independently, in the same
review round. **The artifact beside this note is NOT modified** — history is append-only
(invariant 12) and an exhibit that is quietly corrected is worth nothing. This note is the
correction; the artifact stays exactly as it was written.

## What that file says that is false

Its `live_workers_owed.note` reads, in part:

> "a LIVE worker executed this dispatch: it published a CANDIDATE over MCP, **the real gate engine
> accepted it**, and its leg is derived from a VERIFIED executing checkpoint dated to a call spent
> in this run."

The same JSON object records, three keys away, what the gate actually did:

| Key in that file | Value |
|---|---|
| `gate_summary` | `{"plan": "PASS", "stage_pass": 0, "stage_total": 1, "acceptance": "FAIL"}` |
| `acceptance_verdict` | `"FAIL"` |
| `accepted_count` | `0` |
| `failed_count` | `1` |

**The gate REFUSED the artifact. The sentence saying it accepted it is false, on the exhibit's own
data.** This is the whole reason the run was published: it is this track's evidence that the gate
engine really does refuse live work that fails its criteria (the artifact carried an informal
incompleteness marker; `no_placeholders` caught it). An exhibit published to prove the gate refuses
things should not contain a sentence claiming the gate accepted them.

## Why the sentence was there, and what was fixed

`LIVE_WORKERS_MET["note"]` in `control_plane/orchestration/conductor_dispatch.py` was a **fixed
literal**, emitted by `live_workers_record()` whenever the worker aggregate was `live` and the
executing checkpoint was `verified`. It narrated the gate **without the record ever consulting the
gate** — the record's job is the U58 worker leg, and it cannot see the gate's verdict. When the gate
failed the artifact, the literal was emitted anyway and became false in place.

Fixed in commit `a64779d` (2026-07-31): the note no longer says anything about the gate. It names
the worker leg it can actually see and points the reader at the gate's own fields —
`gate_summary` / `acceptance_verdict` / `accepted_count`, computed by the gate engine. Pinned by
`test_the_u58_record_never_narrates_the_gate` in `tests/unit/test_emit_conductor_dispatch.py`.

**That fix is prospective only.** It changes what future runs emit; it cannot un-publish this one.
Hence this note.

## What in that file is still true and still evidence

Everything the record could actually see:

- a **live** `claude_code` worker node (`worker-claude-live`, `claude-opus-5[1m]`) really executed,
  on a call really spent in that run, with a VERIFIED executing checkpoint (U45);
- it really published a **CANDIDATE** over MCP (invariant 10 — workers never self-canonize);
- the **real gate engine** really evaluated it and really **refused** it: plan `PASS`, stage `0/1`,
  acceptance `FAIL`, `accepted_count: 0` (invariant 16 — a failed artifact cannot advance, and
  there is no conductor override path);
- `objective` on that run is the **bare** objective (`"Design the offline conductor roster"`), i.e.
  the configuration *before* the gate-criteria brief was added in `676362b`. It is evidence about
  the gate **function**, not about the briefed path (spec-audit M3, previous round).

## One related file, deliberately untouched

`docs/evidence/live/PHASE17B_LEGS_DISPATCH_FEED.json` carries the **same pre-fix literal**. There
its `gate_summary` is `stage_pass 1/1`, `acceptance PASS` — so on that exhibit the sentence happens
to be true. It is named here for completeness and is **not** modified either: same append-only rule,
and it needs no correction.

## The lesson this note exists to carry

A record that cannot see a fact must not narrate it — not even in a literal that is usually right.
"Usually right" is what makes the failure invisible: the sentence read correctly on every green run
and became a falsehood the first time the gate did its job. This is the same defect class as U216
(`synthesized_by` naming an adapter class as though it named a backend), and it is the defect class
this whole track exists to prevent.
