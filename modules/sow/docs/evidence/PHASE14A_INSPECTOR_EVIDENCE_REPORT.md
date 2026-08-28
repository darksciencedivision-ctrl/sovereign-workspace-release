# PHASE 14A SUB-STEP EVIDENCE — Routing/Artifact Inspector (`phase-14a.inspector`)
Autonomous loop iteration 18 · 2026-07-18Z · sub-step `phase-14a.inspector` · **no gate tag yet**
(the high-stakes `gate/phase-14a` closes only when ALL 14A sub-steps land, with mandatory
gate-validator confirmation; this report covers the fourth sub-step and carries no tag).

## Objective
Deliver the routing/artifact inspector leg of Phase 14A (directive §9 track 14A) — **Plan §10.3**:
a per-task view of the three governed dimensions the control plane produces — **context routed**,
**artifacts published** (hash, status, provenance), and the **gate chain** — read **read-only over
the D-IPC-01 channel**. Consumes the real MCP read path built in `.ipc`; the rendered panel is an
operator-run surface like the window. `.recovery` (UI recovery after process restart) is the
remaining 14A sub-step.

## Source state
Tags through `gate/phase-13` + `build/complete` + `audit/completion-20260718`; predecessor
sub-steps `.ipc` (`7eb96e3`/`516a480`), `.shell` (`16448bb`/`ac72171`), `.tiling`
(`58dade9`/`186d1e9`) committed; `next_step: phase-14a.inspector`; **no `gate/phase-14a`**.
State/tags agree — reconciled at the start of the iteration (Loop Protocol §3.1); no gate tag was
or is claimed for a sub-step. Freeze set untouched; `docs/canonical/` not modified.

## What is actually readable — the honest read model (the crux of this sub-step)
Reconnaissance of the real subsystems established what the §10.3 dimensions can truthfully be
sourced from **over the existing read path** (the `McpControlSurface` whitelist is exactly
`{health, read_status}` — `control_plane/ipc/gateway.py:111`):

- **Artifacts published — REAL.** `read_status` returns shared-memory entries (`entry_id`, `kind`,
  `status`, `content_hash`, full `provenance`). This is the trustworthy spine; all field
  assumptions verified against `schemas/memory.schema.json` + `mcp_server/memory_service.py`.
- **Gate chain — RECONSTRUCTED, never fabricated.** `control_plane/gates/engine.py` computes a
  `gate@1.0` verdict, drives the in-memory `TaskGraph`, and **discards it** — there is no store
  table and **no read op** for `gate@1.0` (confirmed: `mcp_server/server.py` dispatch has none).
  What IS durable: the conductor publishes each gate decision as a `kind:"decision"` memory entry
  (`control_plane/orchestration/conductor_prototype.py:91`), and a stage-gate promotion stamps
  `provenance.gate_result` (`memory_service.py:114-115`). So `derive.js` reconstructs the gate
  chain from decision entries + `gate_result`, marking every row **`derived:true`** with origin
  fields; the panel paints a `derived` badge. No reconstructed row is presented as a native
  structured verdict; `verdict` is `null` when `gate_result` is absent (never invented).
- **Context routed — NOT readable at all.** `ContextCompiler` emits a `ScopedContext` dataclass
  that is never serialized/stored/exposed (`control_plane/routing/context_compiler.py`). The
  source therefore returns `routes: []` with `routingReadable: false` — an explicit, observable
  statement of the gap — rather than fabricate a bundle. Where an artifact records
  `provenance.source_artifacts`, those ids ride on the artifact row (full provenance preserved) as
  the only honest readable trace, and are NOT presented as a scoped-context bundle.

Both gaps are recorded as new uncertainties **U27** (gate@1.0 not persisted) and **U28**
(ScopedContext ephemeral). If a later phase adds real gate/route read ops, `source.js` feeds them
straight into `buildInspectorModel` and the derivation narrows to entries-only.

## What this sub-step is NOT (honest scope)
- **Not a verified panel.** Per loop directive §6, the Electron window/panel cannot be rendered or
  observed in this headless session; it is an **operator-run metric** exactly like the Phase-1
  spike (`apps/desktop/RUN_ON_WINDOWS.md`). The inspector **data model + read path** — the
  governance-bearing part — is pure and headlessly tested, including a **live read of a real seeded
  MCP server** over the real gateway. No rendered behaviour is claimed as observed.
- **Not a write path.** The inspector is strictly read-only (rides `read_status`), so it does **not**
  depend on the U25 IPC→MCP per-node credential broker (which gates writes). The onward MCP call
  still uses the surface's single pre-configured credential (pre-existing, U25) — safe because
  read-only.
- **Not a live gate@1.0 / ScopedContext feed** (U27/U28 above).

## Files (work commit)
Pure aggregation + honest derivation core (`terminal/inspector/`, headlessly tested):
- `terminal/inspector/inspector-model.js` — per-task fold of `{entries, gates, routes}`: buckets
  by `provenance.task_id`, keeps mis-provenanced entries in an explicit `unattributed` bucket
  (inv 27), records `status-divergence` + `duplicate-route` **anomalies**, deterministic output
  (status-rank + `localeCompare`), `summarize`/`taskView`, fail-closed on malformed input.
  `toGateRow` extended to carry derived-gate origin fields (`derived`, `sourceEntryId`, `author`,
  `ts`, `entryStatus`).
- `terminal/inspector/derive.js` (**NEW**) — pure map of readable memory entries →
  `{entries (non-decision), gates (derived from kind:"decision"), routes:[], routingReadable:false}`.
  Fail-closed on non-array / malformed records.

Read glue (`apps/desktop/inspector/`):
- `apps/desktop/inspector/source.js` (**NEW**) — `fetchInspectorModel(client)` sweeps `read_status`
  across all 8 lifecycle statuses via the existing `IpcClient` (mirrors `control_plane/ipc/
  client.py`), unions by **`(entry_id, status)`** so a genuine cross-status divergence survives to
  the fold's anomaly path (no silent last-write-wins on the read side), then `deriveInputs` +
  `buildInspectorModel`. Fail-closed: an `ok:false` read throws `InspectorSourceError`; transport
  faults propagate — never a half-built model.

Wiring (operator-run GUI surface; `node --check` clean, not headlessly executable — electron/xterm
are operator-host installs):
- `apps/desktop/main.js` — `inspector:fetch` handler returns `{ok, model, summary, routingReadable}`
  or a structured `{ok:false, error}` (fail-closed, observable). Gives the inspector a **separate
  read `IpcClient`** on the same loopback credential (the control channel is one-request-in-flight
  and the supervisor owns its client for the 5 s heartbeat; the 8-status sweep must not contend);
  closed in teardown.
- `apps/desktop/preload.js` — adds the read-only `inspector()` intent; no new renderer authority.
- `apps/desktop/renderer/{renderer.js,index.html}` — thin sandboxed drawer: per-task cards
  (context-routed line, gate chain with `derived` badge, artifact rows with hash/status/author),
  an unattributed card (inv 27), an anomaly list, and a "routing not readable" marker. All
  model-derived strings pass through `esc()` before `innerHTML`; CSP `script-src 'self'`.

Tests + fixture:
- `terminal/test/inspector-model.test.js` (**NEW**, 17) + `terminal/test/inspector-derive.test.js`
  (**NEW**, 7).
- `apps/desktop/test/inspector-source.test.js` (**NEW**, 7) — 5 unit (fake client: sweep-all,
  `(id,status)` union preserving divergence, fold, fail-closed ×2) + **2 LIVE** (real `IpcClient`
  → real gateway → real seeded MCP).
- `apps/desktop/test/fixtures/serve_seeded_mcp.py` (**NEW**, test fixture) — seeds a real MCP store
  (attributed finding, gate decision with `gate_result`, unattributed candidate) via authentic
  per-node publishers, bridges it with a real IPC gateway (`McpControlSurface`), prints IPC creds.

## Exit criteria for the sub-step (Plan §10.3) — met, mapped to code + test
- **Per-task view (context routed / artifacts published / gate chain):** `buildInspectorModel`
  folds all three into per-task records; tested attribution, ordering, `summarize`, `taskView`.
- **Artifacts published with hash, status, provenance:** `toArtifactRow` keeps `content_hash`,
  `status`, and FULL provenance; LIVE test asserts a real `^sha256:[0-9a-f]{64}$` hash + surfaced
  `source_artifacts`.
- **Gate chain:** derived from `kind:"decision"` entries; LIVE test asserts the seeded decision
  becomes one `derived:true` row whose `verdict` is read from real `provenance.gate_result`.
- **Consumed from MCP over the D-IPC-01 channel:** `source.js` uses the existing authenticated
  loopback `IpcClient`; the LIVE test reads a REAL seeded MCP server through the REAL gateway (not
  a mock, not skipped when `py -3.12` is present).
- **Fail-closed + observable (inv 27):** malformed input throws; `ok:false`/transport faults never
  yield a partial model; mis-provenanced entries land in `unattributed` (tested + LIVE:
  `worker-B`); `status-divergence`/`duplicate-route` anomalies recorded and surfaced.
- **No authorization logic in the read path (I-M2), read-only, deterministic:** confirmed by both
  reviewers; pure fold, no clock/randomness/model output.

## Independent review
- **gate-validator: PASS** (isolated context, real commands reproduced). Adversarially verified the
  central honesty claim against source: (a) `gate@1.0` is never persisted / no read op — TRUE
  (grepped `mcp_server/server.py` dispatch, `control_plane/gates/engine.py`); (b) `ScopedContext`
  is ephemeral — TRUE. Confirmed the derivation is faithful (decision entries are real readable
  records; `gate_result` stamped on promotion), fail-closed has no silent-empty escape hatch, the
  separate read `IpcClient` is genuinely necessary (one-request-in-flight vs the supervisor
  heartbeat), read-only ⇒ no U25 dependency, renderer sandboxed + `esc()`. Observed: 105 JS pass
  (2 LIVE ran, not skipped), 364 pytest pass, all `node --check` clean. Two non-blocking
  observations (single onward MCP credential = pre-existing U25; fixture seeds `gate_result` at
  publish rather than via `transition()` — cosmetic, derivation identical).
- **spec-auditor: CLEAN with one MINOR (fixed this iteration).** All at-risk invariants pass
  (I-7/I-M2 no authz in read path; I-8 no blanket-forward, hash not bytes; I-11/I-27 provenance +
  unattributed visibility; I-1/I-2 no self-authorization, sandboxed renderer; determinism; I-20
  loopback; fail-closed). Crucial drift check passed — gate chain marked `derived`, routing not
  invented. **MINOR:** `source.js` deduped by `entry_id` (last-writer-wins) before the fold,
  suppressing the `status-divergence` anomaly its own comment claimed was caught downstream (Inv-27
  observability / certainty-inflation smell). **FIXED:** the union is now keyed by
  `(entry_id, status)` so a real cross-status divergence reaches the fold; a new test proves the
  anomaly fires from the production source path and the most-advanced status is kept.

## Substitutions (loop directive §6)
- **GUI verification deferred, not faked.** The Electron inspector panel is an operator-run metric
  (`apps/desktop/RUN_ON_WINDOWS.md`). The inspector **data model + read path** is pure and fully
  headlessly tested, **including a live read of a real seeded MCP server** over the real IPC
  gateway (the strongest available substitution — real governed state, real transport, real
  fold). No rendered behaviour is claimed as observed.
- **Gate chain / context routed sourced honestly (U27/U28).** Because `gate@1.0` records and
  `ScopedContext` have no read path, the gate chain is reconstructed from decision entries (marked
  `derived`) and routing is reported unreadable rather than fabricated. Recorded as new
  uncertainties, not presented as real-feed results.

## Deviations / carried
- **ruff unavailable** (pip out of scope, §2.7); JS has no repo linter — code is `node --check`
  clean and exercised by `node --test`.
- **Carried (later 14A/subsequent phase):** a durable `gate@1.0` store + read op so the gate chain
  is native, not derived (U27); serialize/expose `ScopedContext` so "context routed" shows the
  real scoped bundle and `routingReadable` can go true (U28); live UI paint verification (operator
  host). `.recovery` is the remaining declared 14A sub-step.
- **U25/U26** unchanged (IPC→MCP per-node credential broker; OS pid→JobObject containment) — the
  read-only inspector does not touch them.

## Test totals
- JS: **105 passed / 0 failed** (`node --test terminal/test/*.test.js apps/desktop/test/*.test.js`)
  — terminal 83 (incl. 24 inspector model/derive), apps/desktop 22 (incl. 7 inspector-source with
  2 LIVE `py -3.12` gateway+MCP subprocess reads, not skipped).
- Python: **364 passed** (`py -3.12 -m pytest tests/ -q`) — unchanged; this sub-step adds only a
  test fixture, no product Python.

## Sub-step verdict
**PASS (sub-step)** — gate-validator PASS, spec-auditor CLEAN (sole MINOR fixed this iteration and
proven load-bearing). A pure, deterministic Plan §10.3 routing/artifact inspector: a per-task fold
of artifacts-published (real), a gate chain honestly reconstructed from decision entries (marked
`derived`), and an explicit "context routed: not readable" (ScopedContext ephemeral) — fed by a
read-only sweep of real MCP state over the D-IPC-01 channel, fail-closed, with mis-provenanced and
divergent entries surfaced not hidden (inv 27). Proven end-to-end by a LIVE read of a real seeded
MCP server. `gate/phase-14a` is **NOT** tagged — the high-stakes gate (mandatory gate-validator)
awaits `.recovery`.

## Commits
Work commit → this evidence/register commit (carries the work hash) → loop-state commit.
**No gate tag** (sub-step; `gate/phase-14a` awaits `.recovery`).

## Next
`phase-14a.recovery` — UI recovery after control-plane/process restart (directive §9 track 14A:
"UI recovery after process restart"): the shell reconstructs pane/session/supervision state and
re-establishes the governed channel after a gateway/control-plane restart, fail-closed. Then
`gate/phase-14a` closes (mandatory gate-validator, high-stakes) when all sub-steps have landed.
