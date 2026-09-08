# SW-CONDUCTOR-001 Phase 2 — the B audit (scope audit before wiring)

**UTC:** 2026-09-07T19:41:17Z entry; audit reading completed before Phase 3 edits.
**Method:** read-only. Every answer below cites file:line captured this run from the worktree at
`D:\production software 3\release-worktree`. Nothing was executed to produce these answers except
reading files.

**GATE VERDICT: Q1 CLEAN, Q3 CLEAN, Q6 CLEAN → the gate does not stop B. Phase 3 proceeds.**
Q2, Q4, Q5, Q7 are informational and answered below; Q5 carries a scope finding that is recorded,
not a stop (the loop gates only on Q1/Q3/Q6).

---

## Q1 — Does the control server accept a request from a node whose connectionState is `configured`? (GATE)

**Answer: YES. CLEAN.** The credential was issued and never used — the first request on it is
accepted, and accepting it is exactly what flips the state.

The acceptance path, in order (`control/sovereign-control-server.js`, `_handle` :284-377):

| Line | Gate | Effect on a `configured` node |
|---|---|---|
| :285-288 | POST `/v1/tools/call` only | route check, identity-blind |
| :301-304 | `Origin` header → 403 | the bridge sends no Origin (`createLoopbackRequest`, local-mcp-bridge.js:353-384) |
| :318-321 | `Host` must be in `_allowedHosts` (`127.0.0.1:<port>`, `localhost:<port>`, pinned at bind, :198-202) | the bridge's request sets host `127.0.0.1` + port (local-mcp-bridge.js:360) |
| :342-345 | `_stopping` → 503 | only during gateway stop |
| :346-350 | `identityFor(bearer(req))` → 401 if absent | **the only identity gate**: a valid unrevoked credential. `identityFor` is a Map lookup (:121); credentials come from `issueCredential` (:98-105) via `childEnv` (:176-181) |
| :354 | `this._lastSeen.set(identity.node_id, now)` | the arrival stamp |

`connectionState(nodeId)` (:140-154) is a **projection of `_lastSeen`, consulted by nobody in the
acceptance path**: `configured` is defined at :133-135 as "a credential was issued and NOTHING has
ever arrived on it". There is no state gate to fail — the first arrival is stamped (:354) and the
projection becomes `connected` (:150-152 region). Revocation is the only credential kill
(`revokeCredential` :107-112, `revokeNode` :114-119).

The `identity` operation is handled **inside the server** (:359-361): it answers `{ok:true, result:
identity}` and is deliberately NOT recorded as an operation (:371 excludes it from failure
recording too; the success path returns before :363-366). So the bridge's attach call (its one
node-behalf claim, local-mcp-bridge.js:197-214) is accepted for a `configured` node and can never
pollute `operationCount`.

## Q2 — What exactly does readiness turn 1 require?

`control/conductor-readiness.js` (:4-96), bound in `main.js:2698-2720`:

- **Gate 1** (:18-24): `waitForNodeMcp(nodeId, mcpTimeoutMs)` — main.js:2417-2424 polls
  `sovereignControl.connectionState(nodeId).state === "connected"` every 250 ms up to
  `MCP_READINESS_TIMEOUT_MS` (120000, main.js:715). Failure → `operationalState: "STALLED"`,
  reason "conductor Sovereign MCP readiness timed out".
- **Gate 2, turn 1** (:26-73): baseline `operationCount(nodeId, "get_worker_status")` (:26);
  the turn-1 prompt is literally `First call the Sovereign get_worker_status tool. Then <probe>`
  (:31-33); the loop (:53-62) requires BOTH `operationCount(...) > baseline` (:54) AND the probe
  nonce observed in `window.since(paneId, mark)` (:55-57) within `PEER_RESPONSE_DEADLINE_MS`
  (180000, main.js:718). Failure → `STALLED` (:65-72).
- **Where the count lives:** server-side `_operations` events, recorded ONLY after a handler
  returned successfully (`_recordOperation` sovereign-control-server.js:166-174, called at :366);
  `operationCount` filters `event.ok` (:162-164). `identity` is never recorded (Q1 above), so
  **attachment can satisfy gate 1 and is structurally unable to satisfy gate 2** — the bridge's
  own honesty claim (local-mcp-bridge.js:36-50) verified against the counting code.
- **Which node id:** `io.launch().nodeId` = `conductorLaunch.nodeId` = the ticket-minted
  `identity.node_id` (main.js:1013/:1023), the same id the credential is issued for
  (main.js:983-984) and the same id `_recordOperation` keys on (:169).

## Q3 — For each of the bridge's eight io dependencies, the existing main.js symbol. (GATE)

**Answer: all eight exist. CLEAN.** One correction to the bridge header's own example is recorded.

| io dep (local-mcp-bridge.js:158-168) | Existing main.js symbol | Evidence |
|---|---|---|
| `paneId` | `conductorPaneId` (module-level; accessor pattern already used) | main.js:861, :2448, :2710 |
| `token` | the `token` returned by `sovereignControl.childEnv(identity, env)` at the conductor mint — **currently discarded** (only `.env` taken) | main.js:983-989; server returns `{env, token}` sovereign-control-server.js:176-181 |
| `port` | `sovereignControl.port` | main.js:980-982 (launch already throws if absent), :2406; server :197 |
| `request` | the bridge's own `createLoopbackRequest()` | local-mcp-bridge.js:353-384 (W-40-shaped: bearer, Host=127.0.0.1:port, no Origin — matches server :301-321) |
| `sessionAlive` | `manager.processIdentity(paneId)` + registry state — see correction below | session-manager.js:232-236; main.js:2265, :2681, :2717 use it as the liveness fact |
| `window{mark,since}` | `readinessWindow` — the SAME window conductor-delegation reads through | main.js:2431; `createScreenWindow` worker-readiness.js:189, `mark` :200-203, `since` :248; delegation uses it via main.js:2505 |
| `writePrompt` | `writePanePrompt` (U328-gated, boolean-returning) | main.js:2469-2471; gate routing proven by system-pane-write-wiring.test.js:47-55 |
| `writeRefusal` | `paneWriteRefusalFor` | main.js:2639-2641; already io-bound at :2689, :2711 |

**Correction (recorded, not a stop):** the bridge header suggests `sessionAlive: () =>
manager.registry.has(paneId)` — that is NOT a liveness check: "the registry record outlives the
process, so an ended session still answers `registry.has(id)`" (session-manager.js:189-190; also
:164-168). The honest check is the one `manager.write` itself guards on (session-manager.js:
176-183): a handle of this generation exists (`processIdentity`, :232-236) AND the registry state
is `RUNNING` (:155). Phase 3 wires that composition.

The one missing piece — the token capture at :983 — is a main.js change, which Phase 3 owns.

## Q4 — What does test/local-mcp-bridge.test.js cover?

Read in full this run (292 lines). Covered, with test line numbers:

- **Parsing:** fenced block + arguments (:63); a `sovereign-result` block is never re-read as a
  call (:72); adjacent blocks are separate calls (:79); malformed JSON / non-object / missing
  `operation` are REPORTED, not dropped (:85); missing/non-object `arguments` → `{}` (:94);
  trailing whitespace on the fence (:99).
- **Attachment honesty:** identity uses the node's own bearer and port (:106); a pane with no live
  session gets no claim and NOTHING reaches the plane (:117); a refused identity leaves the bridge
  unattached with the reason (fail closed, :129); the heartbeat re-reads session liveness every
  beat and self-detaches when the session is gone (:138).
- **Relay honesty:** an emitted call is relayed and the result fence written back (:153); a SILENT
  model produces zero calls and zero writes — only the identity ever reaches the plane (:166); an
  identical still-visible block is relayed exactly once (dedupe, :181); a NEW block after the mark
  advance is relayed (:194); a refusal is passed back verbatim and never retried (:205); an
  unknown operation is answered locally with the vocabulary and never sent (:216); a malformed
  block gets an answer so the model is not left waiting (:226); a withheld write gate writes
  NOTHING and keeps the refusal reason (:237); relay before attach is a no-op (:250); the preamble
  teaches exactly the fence grammar the parser accepts — drift guard (:258); `teach()` goes
  through the governed writer and is withheld when the gate says no (:266).
- **Construction:** no node id / no pane id → throws (:281); a throwing `request` surfaces from
  `attach()` as a rejection (:287).

**NOT covered (the gaps the analysis document suspected, confirmed):**
1. `run()`'s poll loop (start/stop cadence, heartbeat interval) has no test.
2. `detach()` directly — only via heartbeat self-detach.
3. No test integrates the bridge with the REAL `SovereignControlServer` — every plane is
   `fakePlane`. The configured→connected acceptance (Q1) and the identity-never-counted fact (Q2)
   are proven here by code reading only.
4. No attach/detach against a live pane/PTY (impossible headless; U338).

Phase 3 closes gaps 1-3 with a wiring-integration test (real server + real bridge + real
`createScreenWindow` over a real `RingBuffer`, source-shape assertions for the main.js side, in
the house pattern for un-require-able main.js). Gap 4 stays open and is named in the report —
closing it would require launching the application, which this run may not do.

## Q5 — `assign_task`: does it create the task or require an existing one? Required arguments?

**Answer: there are two surfaces with the same name, and the bridge relays to the SECOND.**

1. **The Python MCP tool** (`mcp_server/sovereign_tools.py`, schema :646 — required: `objective`,
   `worker_node_ids`; handler `_assign_task` :296-317): preflights owners through the gateway
   (:300-302), **CREATES the durable task** in the collaboration store (:303-308), then calls the
   gateway operation with `{"task": task}` (:310); on delivery failure it marks the task BLOCKED
   (:312-316). This is the frontier-node path (MCP stdio server).
2. **The gateway operation** (`control/application-control.js` `assignTask` :337-355, served at
   `/v1/tools/call` via the handlers map :428-435): takes a **pre-shaped `args.task`**, requires
   `task.owner_node_ids` (array — `preflightAssignment` :318-321) and uses `task.task_id`
   (:344, :350, :354); it DELIVERS (`writePanePrompt(rec.paneId, taskPrompt(task))` :342), sets
   chrome/BUSY/deadlines. **It creates nothing durable.**

**Consequence for B (scope finding, recorded, not a gate stop):** a local conductor's
bridge-relayed `assign_task` reaches surface 2 — delivery of a task object the model must shape
itself (`{task: {task_id, owner_node_ids, objective, ...}}`), with no durable task row created.
Durable task creation remains on the Python MCP path the bridge does not relay to. Likewise
`send_message` (loop's B paragraph names it) is a Python-layer tool (:319-324), NOT in the gateway
vocabulary (application-control.js:429-435): the bridge will still SEND it (unknown operations are
sent, not filtered — local-mcp-bridge.js:99-101) and the server will refuse it
(`unsupported operation`, sovereign-control-server.js:363-364 → 400 at :375) — and the bridge
writes that refusal back to the model verbatim (local-mcp-bridge.js, relay refusal path; test
:205-210). Honest refusal, not a silent gap. The conductor vocabulary the bridge CAN serve is the
gateway's nine operations + identity (application-control.js:429-435, sovereign-control-server.js
:359-361), which includes `get_worker_status`, `spawn_worker`, `stop_worker`,
`preflight_assignment`, `assign_task` (delivery), `list_models`, `notify_message`,
`notify_debate`, `notify_debate_turn`.

Also noted for honesty: `assignTask`'s preflight requires `requireControlRole(identity,
"conductor")` (application-control.js:319) — the bridge's credential is minted with
`role: "conductor"` (main.js:984), so the role gate passes for the conductor's own calls.

## Q6 — Does the wiring require any new IPC channel or preload method? (GATE)

**Answer: NO. CLEAN.** Every bridge io dependency is a main-process symbol (Q3 table). The
attach/detach hooks live inside existing main.js lifecycle functions (`launchConductorSession`,
`onConductorSessionEnded`, `completeNormalQuit`) — all main-process. `preload.js`,
`renderer/renderer.js`, `renderer/index.html` stay read-only and untouched; no `ipcMain.handle`
is added; nothing in the bridge reads renderer state. Verified again against the Phase 3 diff at
exit (read-only hashes in REPORT.md).

## Q7 — Where is the conductor's STALLED verdict made?

`control/conductor-readiness.js`: gate-1 timeout → :19-23 (`operationalState: "STALLED"`,
"conductor Sovereign MCP readiness timed out"); typed-response timeout → :66-72 (STALLED,
"conductor typed readiness response timed out [on turn N of M]"). Adjacent verdicts: a withheld
write → the refusal's own state (:36-41); an undeliverable prompt → FAILED (:43-48); success →
READY (:78-94). The verdict rides `conductorLaunch.operationalState` via `io.setLaunch`/`io.push`
(main.js:2701-2702) to the badge; the worker-side structured STALLED failure is
`readinessFailure` (main.js:2656-2669). The 20 measured STALLED badges in the analysis document
are gate-1 timeouts: no request ever arrived from `ollama_local`, so `connectionState` stayed
`configured` forever — the exact state Q1 shows the bridge's first identity call flips.

---

## What Phase 3 will do (given the clean gate)

1. main.js (one coherent change): require the bridge module; capture the minted token at the
   conductor `childEnv` call; add `conductorSessionAlive` (the corrected liveness composition),
   `attachConductorBridge(nodeId, token)` (create per-launch instance → `attach()` → `teach()` →
   `run({pollMs:500, heartbeatMs:5000})`, fail-closed with honest logs) and
   `detachConductorBridge(why)` (idempotent); attach inside `launchConductorSession` AFTER the
   governed spawn succeeded and BEFORE `runConductorReadiness()`; detach in the launch catch, in
   `onConductorSessionEnded` (after the lifecycle ignore-check, so only the real conductor's end
   detaches), and at the top of `completeNormalQuit`.
2. New test file closing Q4 gaps 1-3: real `SovereignControlServer` + real bridge + real
   `createScreenWindow` over a real `RingBuffer` — attach flips configured→connected; a
   model-emitted block raises the REAL `operationCount`; identity never raises it; a silent model
   raises nothing (gate 2 structurally unsatisfiable); revocation produces a refusal fence; dead
   session refuses relay; run/stop lifecycle; plus source-shape assertions pinning the main.js
   wiring (attach before readiness, gated writer only, no raw writes, no new IPC, no voice
   authority touched).
3. Harness-anchor discipline (both mutation harnesses re-read this run): no new
   `manager.write(`/`manager?.write(` site, no release-sink calls, no new
   `handleOperatorResumeInput(event, input)` / `clearConductorInputResidue` occurrences, no
   4-space `event.preventDefault();`, no anchor string duplicated — every anchor stays unique.

**Residual risk named, not hidden:** the wiring cannot be exercised against a live app in this
run (no application launches permitted); its live proof is the operator's next acceptance run.
What IS proven here: the module-level integration (real server, real bridge, real window) and the
source-shape wiring, both falsification-graded in Phase 4 by the two mutation harnesses plus the
four suites.
