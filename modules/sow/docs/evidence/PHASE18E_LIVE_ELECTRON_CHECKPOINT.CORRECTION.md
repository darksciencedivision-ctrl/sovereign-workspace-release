# CORRECTION to `PHASE18E_LIVE_ELECTRON_CHECKPOINT.md` — the live-run count was three, and it was four

**Written 2026-08-02 at `phase-18e.close`.** The checkpoint it corrects is **not edited** — evidence
here is append-only, and a document that quietly acquires a different number is worse than a wrong
one with a correction beside it. This file is the repo's own convention (see
`docs/evidence/live/phase18e_probe_document_shape_20260802T0219Z.json.CORRECTION.md`).

## What is wrong

`PHASE18E_LIVE_ELECTRON_CHECKPOINT.md` says, at its header (line 10), in §2 and in its §6
verification table:

> *"across three live in-Electron runs"* … *"Live in-Electron runs | **3** (06:35Z, 06:54Z, 07:19Z)"*

The operator's own durable node log — `.sovereign_store/nodes/node_events.jsonl`, the append-only
record those runs wrote into — carries **four** two-provider pane cycles in that unit's window, each
under a different Electron main pid:

| # | pane session ids | UTC |
|---|---|---|
| 1 | `pane-2#116748.1` / `pane-3#116748.2` | 06:35:29 |
| 2 | `pane-2#78116.1` / `pane-3#78116.2` | **06:52:44 — unreported** |
| 3 | `pane-2#21920.1` / `pane-3#21920.2` | 06:54:23 |
| 4 | `pane-2#119840.1` / `pane-3#119840.2` | 07:19:48 (the receipt's own `electron_main_pid`) |

Arithmetic that settles it independently of the pids: 18D left the log at **15** rows (probe
sessions only). Each pane cycle appends 8 rows (2 panes × `spawn` + 2 `transition` + `exit`). The
`.live.electron` receipt records the log going **39 → 47**, so 39 − 15 = 24 rows = **three cycles
already present before its final run**, and its own run is the fourth.

**Found by:** the `phase-18e.close` gate-validator (BLOCKING-2), which read the node log instead of
the prose. Recorded as **U322**.

## What it changes, and what it does not

* **The count, and the disclosed host cost.** Each unreported run spawned both OP-12 CLIs live and
  made the D-P18-7/U271-disclosed metadata calls (`grok --version`/`models`, `agy --version`/
  `models`). The 18E totals are restated in `PHASE18E_EVIDENCE_REPORT.md` §3: **eight** in-Electron
  live runs across the track — four in `.live.electron`, four in `.close`.
* **Nothing else.** `live_exchanges_spent` was **0** on every one of those runs (a consent-gated leg
  stops before a probe prompt is drawn), so no live model budget was spent and the directive's
  one-per-provider allowance is still intact. The U317 finding, the per-leg measurements and the
  receipt the checkpoint publishes are unaffected: they describe the 07:19:48 run, which is real, is
  the one whose receipt is committed, and is correctly identified inside it.

## Why the unit could get this wrong

The unit counted the runs it *wrote receipts for*. The target wrote to one fixed path, so a run
superseded by the next one left no artifact at all — while the operator's append-only log keeps every
one of them. That asymmetry is the lesson: **the durable log is the record of what happened, and a
receipt is only the record of what was published.** `.close` responded by naming its own runs in the
receipt (`unit`), by counting from the node log rather than from memory, and — after its round-2
reviewers pointed out that the first two are bookkeeping around an unfixed cause — by **run-stamping
the receipt filename**, so no run supersedes another and the operator's own re-run cannot overwrite a
receipt that a published checkpoint cites by content.
