"use strict";
/**
 * GOVERNED WORKER-PANE LAUNCH — Phase 17B `.spawn` (closes the spawn half of U70).
 *
 * `.ticket` made a picker selection *authorizable*: `tools/live/emit_worker_launch.py` turns one
 * selection into an executable `worker_launch_ticket@1.0` (interactive argv, resolved binary,
 * governed workspace, credential-scrub NAMES, Python-minted node identity, and either a held durable
 * I-X3 lease or a residency decision) — or into a fail-closed refusal. Nothing executed it. The
 * operator's finding F3 stood: "selecting a model records + badges but launches nothing".
 *
 * This module executes it, and is the ONLY place in the shell that does. It is deliberately a
 * separate, dependency-injected module rather than more of `main.js`: every rule below is then
 * exercised by the headless suite (`apps/desktop/test/worker-spawn.test.js`) as well as by the
 * in-Electron receipt, and `main.js` keeps nothing but the wiring.
 *
 * The ORDER of operations is the governance, so it is stated once here:
 *
 *   1. **Admission first.** No ticket is even requested while supervision is not READY — a session
 *      is only ever born on a verified control-plane channel (invariant 2). Asking first would take
 *      a durable terminal for a session that cannot be born.
 *   2. **The pane must be free.** A pane already holding a LIVE session is refused (its session is
 *      not silently killed to make room); a pane holding an ENDED record is forgotten first, exactly
 *      as pane 1 does, so a dead record cannot wedge the pane for the shell's lifetime.
 *   3. **The session key is chosen BEFORE the ask** (`<pane>#<pid>.<seq>`), so the terminal the
 *      emitter counts can be handed back even if the ticket never arrives (U77's lesson, and U100:
 *      an undelivered ticket used to leave a frontier terminal counted for a session that will never
 *      exist — 1 of the operator's 2, held by nothing).
 *   4. **The shell decides nothing about authorization.** `authorized !== true` ⇒ no spawn, the
 *      governed reason is recorded verbatim, and the terminal is handed back.
 *   5. **The child env is the ticket's scrub applied to the env we actually spawn from** — the same
 *      object passed to the emitter as `shellEnv`, so the names classified and the names deleted are
 *      names from one environment (U105). A name still present after the scrub is a spawn ABORT, not
 *      a warning: the whole point of the list is that it is empty afterwards.
 *   6. **A pre-birth spawn failure hands the terminal back.** A post-birth failure carries exact
 *      process identity and keeps the terminal until that process's confirmed exit.
 *   7. **D-LOOP-1**: kill and shell quit signal termination but never release on intent. The terminal
 *      is released after matching process exit; a local pane holds no terminal and that release is
 *      a no-op — called anyway, so the lifecycle has one shape.
 *
 * What this module does NOT do, stated so the receipt cannot be read as more than it is: it does not
 * make the pane's model answer anything (a live exchange is `.legs`/U58), and the containment the
 * ticket discloses as owed (`os_job_object` U25, permission-profile binding U78(a)) stays owed.
 */

const { scrubbedLaunchEnv, scrubCredentialEnv, credentialNamesIn } = require("../conductor/launch-source");
const { processSupervisionObserved } = require("../control/readiness-evidence");
const {
  sourceWorkerLaunchTicket, releaseWorkerTerminal, attestWorkerPaneSpawned,
} = require("./launch-source");

/** Observable per-pane launch states (invariant 27). `refused` is a GOVERNED refusal (a gate said no,
 * with a reason and a gate id); `unavailable` is "no ticket could be obtained at all"; `failed` is
 * this shell's own inability to spawn what it was authorized to. */
const WORKER_LAUNCH_STATES = [
  "launching", "running", "terminating", "release_pending", "release_failed",
  "exited", "refused", "unavailable", "failed",
];

/** The launch record for a pane, with every field the chrome/receipt reads present from the start
 * (an absent field and a null one read the same in a receipt, and only one of them is honest). */
function emptyRecord(paneId) {
  return {
    paneId, state: "unstarted", sessionId: null, nodeId: null, leaseId: null,
    subscriptionRef: null, subscriptionGoverned: null, residency: null, pid: null,
    sessionGeneration: null,
    argv: null, executable: null, cwd: null, envScrubNames: [], scrubbedCount: null,
    chrome: null, reason: null, refusedBy: null, modelProbe: null,
    releaseTargetState: null, releaseTargetReason: null, releaseTargetRefusedBy: null,
    startedAt: null, endedAt: null, exitCode: null, supervised: false,
    // 18E: whether this pane's Sovereign node record was moved to READY with its supervised pid,
    // and the full outcome. Present on EVERY record so a reader can tell "not attested" from
    // "nobody asked" — the same reason `node_registration` is present-and-negative on the ticket.
    nodeAttested: false, nodeAttestation: null,
    // …and the two ENDS of that record's life: what the ticket reported writing, and what the
    // release reported closing. Both are measurements the producers already make and the shell
    // used to read once and discard, so nothing could report whether a pane's node record was
    // left open (18E `.live.electron`).
    nodeRegistration: null, nodeClosure: null,
    operationalState: "STARTING", readiness: null, structuredFailure: null,
    lastSuccessfulMcpOperation: null, lastProgressAt: null,
  };
}

/**
 * Build the launcher. Every dependency is injected so the rules above are testable without Electron:
 *
 *   `sourceTicket(opts)`      → `{ok, ticket, error?}`     (default: the real Python read-source)
 *   `releaseTerminal(sid,o)`  → `{ok, released}`           (default: the real emitter release)
 *   `spawnSession({paneId, nodeId, spec})` → the shell's supervised spawn (throws ⇒ not admitted)
 *   `processIdentity(paneId)` → the shell's currently observed `{pid, generation}`
 *   `isSupervised()`          → boolean, the live admission state
 *   `hasLiveSession(paneId)` / `forgetSession(paneId)` → the pane-occupancy rules (step 2)
 *   `baseEnv`                 → the env this shell spawns children from (`process.env` in product)
 */
function createWorkerPaneLauncher(deps = {}) {
  const {
    sourceTicket = sourceWorkerLaunchTicket,
    releaseTerminal = releaseWorkerTerminal,
    // The post-spawn node attestation (18E). Injected like every other dependency so the rule can
    // be driven headlessly; it is called AFTER the session is running and its outcome is recorded,
    // never acted on — a bookkeeping fault must not kill a live governed session.
    attestSpawn = attestWorkerPaneSpawned,
    spawnSession,
    processIdentity = () => null,
    isSupervised = () => false,
    hasLiveSession = () => false,
    forgetSession = () => {},
    // G22: governed replacement tears the prior session down through THIS injected
    // primitive - the same teardown the pane-close IPC uses - never an ad-hoc kill.
    endLiveSession = () => {},
    onChange = () => {},
    // The §2.2 scrub rule itself, injectable for ONE reason: the leftover check below is a guard
    // over whatever produced the child env, and a guard nothing can drive is a guard nobody knows
    // works. A caller that injects a weaker scrub does not weaken the shell — it trips the guard.
    scrubEnv = scrubbedLaunchEnv,
    // Add the node-scoped, opaque app-control capability after credential scrubbing. The callback
    // receives the Python-issued identity; it may not replace cwd/argv or mint a different node.
    augmentSpawnEnv = (env) => env,
    revokeNodeControl = () => {},
    baseEnv = process.env,
    holderPid = process.pid,
    repoRoot,
    timeoutMs = 90000,
    // The attestation is awaited AFTER the pane is already live and visible, so it must not be
    // able to hold `launchWorkerPane` unresolved for the launch timeout (90 s) over a bookkeeping
    // call (spec-audit MINOR-11). Its own, much shorter bound; exceeding it is a recorded
    // unattested record, not a failed launch.
    attestTimeoutMs = 20000,
    log = () => {},
    scheduleRetry = (fn, delayMs) => {
      const timer = setTimeout(fn, delayMs);
      timer.unref?.();
      return timer;
    },
  } = deps;
  if (typeof spawnSession !== "function") {
    throw new Error("createWorkerPaneLauncher requires spawnSession — the shell's SUPERVISED spawn "
      + "is the only way a governed session is born (invariant 2)");
  }

  const records = new Map();   // paneId -> launch record
  let seq = 0;
  let releaseRetryScheduled = false;

  const get = (paneId) => records.get(paneId) || emptyRecord(paneId);
  const set = (paneId, patch) => {
    const next = { ...get(paneId), ...patch, paneId };
    records.set(paneId, next);
    try { onChange(paneId, next); } catch { /* observation must never break a launch */ }
    return next;
  };

  /** Is this pane's record a session THIS launcher still holds (and must still hand back)? */
  const isHeld = (paneId) => {
    const r = records.get(paneId);
    return Boolean(r && ["running", "launching", "terminating", "release_pending", "release_failed"]
      .includes(r.state) && r.sessionId);
  };

  /**
   * Record a non-launch and return it. Every refusal SAYS why — a silent no-op is the defect.
   *
   * A refusal NEVER overwrites the record of a session this launcher still holds. It used to, and
   * the consequence was the exact harm U100 names, reintroduced by the occupied-pane path: launch a
   * frontier worker into a pane (1 of the operator's 2 durable terminals), then click the picker on
   * that same pane. The refusal was correct and the running session was correctly left alone — but
   * its record was overwritten with `state:"refused"`, and every release gate keys on the state, so
   * `heldSessions()` (quit) and `onWorkerSessionEnded` (exit/kill) both went quiet. The terminal
   * became unreleasable for the life of the shell, recoverable only by dead-holder reaping that
   * cannot fire because the holder is the shell (gate-validator BLOCKING-1, 2026-07-26). The refusal
   * is still reported in full; what it must not do is forget a live session on its way out.
   */
  const refuse = (paneId, state, why, refusedBy = null, ownSessionId = null) => {
    log(`worker pane ${paneId}: launch not attempted — ${why}`);
    // "Held" means held by a DIFFERENT session than the one this attempt owns: the record of the
    // attempt in flight is ours to close (that is how a failed launch reports itself), while the
    // record of a session someone else's click is being refused for is not.
    const rec0 = records.get(paneId);
    const held = isHeld(paneId) && (!ownSessionId || rec0.sessionId !== ownSessionId);
    const rec = held
      ? get(paneId)
      : set(paneId, { state, reason: why, refusedBy, endedAt: new Date().toISOString() });
    return { launched: false, refused: state === "refused", reason: why, refusedBy, record: rec,
      // the refusal did not change what this pane holds — the caller must not repaint it as dark
      heldSessionUntouched: held };
  };

  /**
   * Launch ONE governed worker session into `paneId` for the operator's picker `selection`.
   * Never throws — the outcome is the record. `{launched, refused?, reason?, record}`.
   *
   * "Never throws" is a promise the caller relies on (`main.js` has no try/catch around it), so it
   * is enforced here rather than assumed of every dependency: an injected scrub/release/observer
   * that throws would otherwise reject out of this function and leave the record stuck at
   * `launching` (spec-audit MINOR-6). A terminal may already be counted at that point, so the
   * catch releases before it reports.
   *
   * It releases and refuses against THIS ATTEMPT'S session key only — never against whatever record
   * the pane happens to hold. Two of the injected calls (`isSupervised`, `hasLiveSession`) run
   * BEFORE this attempt has a record of its own, so a throw from either used to make the catch read
   * the record of the session already running in that pane, release ITS durable terminal and
   * overwrite its `running` state — which is BLOCKING-1's harm (an unreleasable, or wrongly
   * released, I-X3 terminal) arriving by a second route (validator MINOR-5). `minted` is set only
   * when this attempt chooses its own key, so before that point the catch has nothing to release,
   * which is exactly right: nothing was counted yet.
   */
  async function launchWorkerPane(args = {}) {
    const attempt = { sessionId: null, nodeId: null };
    try {
      return await launchWorkerPaneInner(args, attempt);
    } catch (e) {
      const pid = String((args && args.paneId) || "").trim();
      const why = `unexpected launcher fault: ${e.name || "Error"}: ${e.message}`;
      if (attempt.sessionId && !attempt.processExitPending) {
        if (attempt.nodeId) revokeNodeControl(attempt.nodeId);
        const released = await releasePrebirthRecord(pid, attempt.sessionId, "failed", why);
        if (!released.ok) {
          return { launched: false, reason: why, record: released.record };
        }
      }
      return pid ? refuse(pid, "failed", why, null, attempt.sessionId)
        : { launched: false, reason: why, record: null };
    }
  }

  async function launchWorkerPaneInner({ paneId, selection } = {}, attempt = {}) {
    const pid = String(paneId || "").trim();
    if (!pid) return { launched: false, reason: "no pane id — a governed node is minted from (pane, role)" };
    if (!selection || typeof selection !== "object" || !selection.option) {
      return refuse(pid, "refused", "selection carries no picker option (fail closed)");
    }
    // (1) admission — invariant 2, before anything is counted or reserved.
    if (!isSupervised()) {
      return refuse(pid, "unavailable",
        "supervision is not READY — a session is only ever born on a verified control-plane channel");
    }
    // (2) the pane must be free.
    if (hasLiveSession(pid)) {
      // G22: governed replacement. An unconfirmed click is still a soft refusal -
      // but it names its own class and the confirm that unlocks it, instead of the
      // old blanket "close it" wall. A CONFIRMED replacement terminates the prior
      // session through endLiveSession (the pane-close primitive), waits bounded
      // for the record to release, then falls through into a fresh launch.
      if (selection.replaceConfirmed !== true) {
        return refuse(pid, "replacement-requires-confirmation",
          `pane ${pid} already holds a live session - governed replacement terminates and `
          + "reinitializes ONLY on an explicit confirm (selection.replaceConfirmed: true); "
          + "a running session is never killed by an unconfirmed click");
      }
      try {
        endLiveSession(pid);
      } catch (e) {
        return refuse(pid, "refused",
          `governed replacement could not terminate the prior session (${e.message})`);
      }
      const clearDeadline = Date.now() + 10000;
      while (hasLiveSession(pid) && Date.now() < clearDeadline) {
        await new Promise((r) => scheduleRetry(r, 100));
      }
      if (hasLiveSession(pid)) {
        return refuse(pid, "refused",
          "prior session did not release within the governed-replacement window");
      }
    }
    try {
      forgetSession(pid);   // an ENDED record must not wedge the pane (same rule as pane 1)
    } catch (e) {
      return refuse(pid, "refused", `pane ${pid} still carries a live session record (${e.message})`);
    }

    // (3) the session key, chosen BEFORE the ask, so it is reclaimable either way.
    const sessionId = `${pid}#${holderPid}.${++seq}`;
    attempt.sessionId = sessionId;   // from here on the outer catch has a key of its OWN to release
    set(pid, {
      ...emptyRecord(pid), state: "launching", sessionId,
      startedAt: new Date().toISOString(),
    });
    log(`worker pane ${pid}: requesting a governed launch ticket for session ${sessionId}`);

    const res = await sourceTicket({
      cwd: repoRoot, holderPid, sessionId, paneId: pid, selection,
      // the env classified is the env we spawn from (U105) — one environment, one list
      shellEnv: baseEnv, timeoutMs,
    });
    const ticket = (res && res.ticket) || {};
    if (!res || res.ok !== true) {
      // U100: the emitter may have taken the durable terminal before the failure (a shape drift, a
      // timeout, a killed child). The shell never learned a lease id — but it CHOSE the session key,
      // which is the reclaim key, so it can still hand the terminal back. Without this a frontier
      // selection whose ticket never arrived left 1 of the operator's 2 terminals counted for a
      // session that will never exist, reclaimable only by the ledger's dead-holder reaping — and
      // this holder (the shell) does not die.
      const why = (res && res.error) || "worker launch ticket unavailable";
      const rel = await releasePrebirthRecord(pid, sessionId, "unavailable", why);
      log(`worker pane ${pid}: ticket undelivered — durable terminal for ${sessionId} `
        + `${rel.ok ? "reconciled" : "release FAILED; retry scheduled"} (U100)`);
      if (!rel.ok) return { launched: false, reason: why, record: rel.record };
      return refuse(pid, "unavailable", why, null, sessionId);
    }
    if (ticket.authorized !== true) {
      // A governed refusal. The emitter releases its own lease on this branch; the release below is
      // the belt to that braces — it reclaims nothing when nothing is held, and costs one call.
      const rel = await releasePrebirthRecord(
        pid, sessionId, "refused", ticket.reason || "governed refusal", ticket.refused_by || null,
      );
      if (!rel.ok) {
        return {
          launched: false, refused: true, reason: ticket.reason || "governed refusal",
          refusedBy: ticket.refused_by || null, record: rel.record,
        };
      }
      return refuse(pid, "refused", ticket.reason || "governed refusal", ticket.refused_by || null,
        sessionId);
    }

    const launch = ticket.launch || {};
    const identity = ticket.identity || {};
    attempt.nodeId = identity.node_id || null;
    const lease = ticket.lease || {};
    const names = Array.isArray(launch.env_scrub_names) ? launch.env_scrub_names.slice() : [];
    // (5) the child env: this shell's env MINUS every name the ticket lists (§2.2, names only).
    let env = scrubEnv(ticket, baseEnv);
    // W-32 moved `augmentSpawnEnv` BELOW the two scrub stages. It mints this child's capabilities,
    // and four of the five names it can add are classifier-positive (`SOVEREIGN_CONTROL_TOKEN` on
    // TOKEN; the voice authority's four on AUTH), so minting before stage 3 would have the scrub
    // delete the capability the launch just granted. Minting after both stages also means stage 4
    // examines the environment the child actually receives. The guard below is unaffected by the
    // move: it tests TICKET-declared names, and no minted name is one.
    // CASE-INSENSITIVE, deliberately: Windows env var names are case-insensitive to the OS while a
    // plain-object delete is case-sensitive, which is the very divergence U105 exists for. An
    // exact-spelling guard would have been blind to the class of leak it is guarding against
    // (spec-audit MINOR-5) — and would have rested on the correctness of the list it validates.
    const present = new Set(Object.keys(env).map((k) => k.toLowerCase()));
    const leftover = names.filter((n) => present.has(String(n).toLowerCase()));
    if (leftover.length) {
      // Unreachable through the DEFAULT scrub — which is exactly why it is checked rather than
      // assumed: the one thing this list is for is being empty afterwards, and a spawn that proceeds
      // with a credential var still in the child env is the §2.2 failure itself.
      const why = `the credential scrub left ${leftover.length} named var(s) in the child environment — `
        + "refusing to spawn (§2.2)";
      const rel = await releasePrebirthRecord(pid, sessionId, "failed", why);
      if (!rel.ok) return { launched: false, reason: why, record: rel.record };
      return refuse(pid, "failed", why, null, sessionId);
    }

    // ---- W-32 stage 3: the classifier, applied AFTER the ticket guard above has had its look ----
    // Not injectable, deliberately — it is the floor, and a caller must not be able to lower it.
    // It runs SECOND so it cannot clean up the evidence the ticket guard exists to find: if the
    // ticket declares XAI_API_KEY and an injected scrub leaves it behind, the refusal above must
    // fire first. Ordering, not tidiness (operator ruling).
    //
    // What it removes that no ticket declares: NODE_PATH, NODE_OPTIONS and NODE_EXTRA_CA_CERTS
    // redirect or inject into an npm-installed Node CLI, and the provider prefix/substring nets
    // catch a credential the ticket's author never thought to list.
    env = scrubCredentialEnv(env);
    // The shell mints this child's capabilities HERE — after both scrub stages, so the scrub cannot
    // delete what the launch just granted, and before stage 4, so the assertion sees the real env.
    env = augmentSpawnEnv(env, { ticket, paneId: pid, sessionId, identity });
    // ---- W-32 stage 4: assert on the environment ACTUALLY handed to the child -------------------
    // Stage 3 having run is not the same fact as the child being clean. This is the check the
    // review found missing elsewhere as "measured in the wrong process": it looks at `env` as it is
    // about to be spawned with, after the shell has minted this child's capabilities, so a
    // compromised or simply buggy `augmentSpawnEnv` cannot introduce a credential behind the scrub.
    const classified = credentialNamesIn(env);
    if (classified.length) {
      // NAMES only (§2.2) — never a value, not even in a refusal.
      const why = `${classified.length} credential-classified name(s) reached the child environment `
        + `(${classified.sort().join(", ")}) — refusing to spawn (§2.2)`;
      const rel = await releasePrebirthRecord(pid, sessionId, "failed", why);
      if (!rel.ok) return { launched: false, reason: why, record: rel.record };
      return refuse(pid, "failed", why, null, sessionId);
    }

    let spawnedIdentity = null;
    try {
      // THE governed spawn. `nodeId` is the identity PYTHON issued: the shell cannot mint one, and
      // the SessionManager refuses a spawn without an admitted node (invariant 2). `executable` is
      // the binary the presence gate RESOLVED; argv[0] is only its display name.
      //
      // CONTRACT the caller must honour (spec-audit MAJOR-3): a post-birth throw carries exact
      // `sessionIdentity` plus `processExitPending`; only a pre-birth throw omits them. The catch below
      // retains the durable terminal for the former until the matching process exit and immediately
      // releases only the latter. The wiring in `main.js` supplies that distinction.
      spawnedIdentity = spawnSession({
        paneId: pid,
        nodeId: identity.node_id,
        spec: {
          file: launch.executable,
          args: (launch.argv || []).slice(1),
          cwd: launch.cwd,
          env,
          title: (ticket.chrome && ticket.chrome.model_label) || "worker",
        },
      });
    } catch (e) {
      // (6) Supervision denial may occur after ConPTY birth, while a node-pty construction failure
      // may be genuinely pre-birth. Keep the terminal for an identified terminating process; hand it
      // back immediately only when there is no registered process identity.
      const why = `${e.name || "Error"}: ${e.message}`;
      const born = e && e.sessionIdentity;
      if (born && e.processExitPending === true
          && Number.isInteger(born.pid) && Number.isInteger(born.generation)) {
        attempt.processExitPending = true;
        const pending = set(pid, {
          state: "terminating",
          pid: born.pid,
          sessionGeneration: born.generation,
          nodeId: identity.node_id || null,
          leaseId: lease.lease_id || null,
          subscriptionRef: lease.subscription_ref || null,
          subscriptionGoverned: ticket.subscription_governed === true,
          residency: ticket.residency || null,
          reason: `${why}; process termination requested — lease retained until matching PTY exit`,
          supervised: false,
        });
        log(`worker pane ${pid}: spawn failed after process birth; waiting for exact pid ${born.pid} `
          + `generation ${born.generation} exit before releasing ${sessionId}`);
        return { launched: false, reason: why, awaitingProcessExit: true, record: pending };
      }
      if (identity.node_id) revokeNodeControl(identity.node_id);
      const rel = await releasePrebirthRecord(pid, sessionId, "failed", why);
      log(`worker pane ${pid}: governed spawn FAILED (`
        + `${rel.ok ? "terminal reconciled" : "terminal release failed; retry scheduled"}, `
        + `pane un-launched): ${why}`);
      if (!rel.ok) return { launched: false, reason: why, record: rel.record };
      return refuse(pid, "failed", why, null, sessionId);
    }

    // Re-observe the process through the SessionManager-facing dependency. The spawn return proves
    // what was requested; this second observation proves that the shell currently owns that exact
    // pid/generation. An unavailable or faulty observer is evidence ABSENT, never a literal true,
    // and observation itself must not strand an already-live process by throwing out of launch.
    let observedIdentity = null;
    try {
      observedIdentity = processIdentity(pid);
    } catch (e) {
      log(`worker pane ${pid}: process supervision could not be re-observed (${e.message})`);
    }
    const rec = set(pid, {
      state: "running",
      // the OS pid of the session, as reported by the shell's own spawn — the one fact about a
      // running session this launcher does not get from the ticket. Declared-but-never-assigned
      // before, so the pane chrome published `pid: null` for a RUNNING pane while its comment said
      // otherwise (validator MINOR-2 / spec-audit MINOR-4).
      pid: spawnedIdentity && Number.isInteger(spawnedIdentity.pid) ? spawnedIdentity.pid : null,
      sessionGeneration: spawnedIdentity && Number.isInteger(spawnedIdentity.generation)
        ? spawnedIdentity.generation : null,
      nodeId: identity.node_id || null,
      leaseId: lease.lease_id || null,
      subscriptionRef: lease.subscription_ref || null,
      subscriptionGoverned: ticket.subscription_governed === true,
      residency: ticket.residency || null,
      argv: (launch.argv || []).slice(),
      executable: launch.executable || null,
      cwd: launch.cwd || null,
      envScrubNames: names,           // NAMES only (§2.2) — kept so a check can verify the child env
      scrubbedCount: names.length,
      chrome: ticket.chrome || null,
      modelProbe: ticket.model_probe || null,
      // What the ticket reported WRITING (`node@1.1` record id, incarnation, log path) — kept, not
      // merely branched on below, so a receipt can bind the pane to a row on the operator's own
      // durable node log instead of recomputing an identity derivation.
      nodeRegistration: (ticket.node_registration && typeof ticket.node_registration === "object")
        ? ticket.node_registration : null,
      supervised: processSupervisionObserved({
        supervised: true,
        pid: spawnedIdentity && spawnedIdentity.pid,
        sessionGeneration: spawnedIdentity && spawnedIdentity.generation,
      }, observedIdentity),
      reason: null, refusedBy: null,
    });
    // The node record written at ticket time says SPAWNING because at that moment nothing had been
    // spawned. It has been now, with a supervised pid, so the record is moved to READY carrying it
    // (invariant 2: this terminal is a Sovereign node, and its record should say what is true of
    // it). Awaited — so the receipt below reports a MEASURED outcome rather than a scheduled
    // intention — but never fatal: the session is already live and correctly governed, and a
    // failed attestation leaves a SPAWNING record that the release still closes.
    //
    // GATED ON THE TICKET'S OWN MEASUREMENT. The first cut attested for EVERY pane, including the
    // local and OP-6 ones that have no record by design — so a pane id whose earlier grok session
    // left a record open could be attested with an ollama process's pid, on an append-only log
    // that can never be corrected (validator MAJOR-1 / MEDIUM-1, spec-audit MAJOR-2). The ticket
    // already says whether a record exists; reading it is both the fix and the reason the field
    // was measured in the first place. It also stops a `py -3.12` round trip per local pane.
    const registration = ticket.node_registration || null;
    let attestation = { ok: false, attested: false, error: "not attempted" };
    if (!registration || registration.registered !== true) {
      attestation = { ok: false, attested: false, applicable: false,
        error: `no node record was written for this pane (${(registration && registration.reason)
          || "the ticket reported none"}) — nothing to attest` };
    } else if (rec.nodeId && Number.isInteger(rec.pid)) {
      try {
        attestation = await attestSpawn(rec.nodeId, sessionId, rec.pid,
          { cwd: repoRoot, timeoutMs: attestTimeoutMs });
      } catch (e) {
        attestation = { ok: false, attested: false, error: `${e.name || "Error"}: ${e.message}` };
      }
    } else {
      attestation = { ok: false, attested: false,
        error: `no node id or pid to attest (node ${rec.nodeId}, pid ${rec.pid})` };
    }
    const attested = set(pid, { nodeAttested: attestation.attested === true,
      nodeAttestation: attestation });
    if (!attestation.attested && attestation.applicable !== false) {
      log(`worker pane ${pid}: node record NOT attested (${attestation.error}) — the session is `
        + "live and governed; its record still reads SPAWNING until release closes it");
    }
    log(`worker pane ${pid}: LIVE governed session — ${(launch.argv || []).join(" ")} `
      + `(node ${identity.node_id}, cwd ${launch.cwd}, ${names.length} credential var(s) scrubbed, `
      + `${rec.subscriptionGoverned ? `durable terminal ${lease.lease_id} ${lease.in_use}/${lease.allowance}`
        : "local — no subscription terminal, residency-governed"})`);
    return { launched: true, sessionId, record: attested };
  }

  /**
   * The pane's session ended (its own exit, an operator close, or the fail-closed killAll on
   * supervision loss) — hand the durable terminal back (D-LOOP-1) and record it honestly.
   * A no-op for a pane this launcher never launched, and for one already reaped.
   */
  function scheduleReleaseRetry() {
    if (releaseRetryScheduled) return;
    releaseRetryScheduled = true;
    scheduleRetry(async () => {
      releaseRetryScheduled = false;
      await retryPendingReleases();
    }, 30_000);
  }

  async function releasePrebirthRecord(pid, sessionId, targetState, why, refusedBy = null) {
    let rel;
    try {
      rel = await releaseTerminal(sessionId, { cwd: repoRoot, timeoutMs });
    } catch (e) {
      rel = { ok: false, released: false, error: `${e.name || "Error"}: ${e.message}` };
    }
    if (rel && rel.ok === true) {
      return {
        ok: true,
        record: set(pid, {
          state: targetState, leaseId: null, reason: why, refusedBy,
          releaseTargetState: null, releaseTargetReason: null, releaseTargetRefusedBy: null,
          endedAt: new Date().toISOString(),
        }),
      };
    }
    const rec = set(pid, {
      state: "release_failed",
      reason: `${why}; terminal release failed (${(rel && rel.error) || "unknown"})`,
      refusedBy,
      releaseTargetState: targetState,
      releaseTargetReason: why,
      releaseTargetRefusedBy: refusedBy,
      endedAt: new Date().toISOString(),
    });
    scheduleReleaseRetry();
    return { ok: false, record: rec };
  }

  async function releaseEndedRecord(pid, rec) {
    set(pid, { state: "release_pending", reason: "process exited; releasing durable terminal" });
    let rel;
    try {
      rel = await releaseTerminal(rec.sessionId, { cwd: repoRoot, timeoutMs });
    } catch (e) {
      rel = { ok: false, released: false, error: `${e.name || "Error"}: ${e.message}` };
    }
    // The release CLOSES the session's node record on the same call, and says whether it did. A
    // failed lease release and an unclosed node record are two different leaks, so the outcome is
    // recorded on BOTH branches rather than only on the happy one.
    const nodeClosure = (rel && rel.nodeRecord) || null;
    if (rel && rel.ok === true) {
      set(pid, {
        state: "exited", leaseId: null, nodeClosure,
        reason: `session exited (${rec.exitCode}); durable terminal reconciled`,
      });
    } else {
      set(pid, {
        state: "release_failed", nodeClosure,
        reason: `session exited (${rec.exitCode}); terminal release failed (${(rel && rel.error) || "unknown"})`,
      });
      scheduleReleaseRetry();
    }
    log(`worker pane ${pid}: durable terminal for ${rec.sessionId} `
      + `${rel && rel.ok ? (rel.released ? "RELEASED" : "already absent") : "release FAILED"} `
      + "(after confirmed process exit)");
    return { released: Boolean(rel && rel.ok), matched: true, processExited: true };
  }

  async function retryPendingReleases() {
    const pending = [...records.entries()]
      .filter(([, rec]) => rec.state === "release_failed" && rec.sessionId);
    for (const [pid, rec] of pending) {
      if (rec.releaseTargetState) {
        await releasePrebirthRecord(
          pid, rec.sessionId, rec.releaseTargetState, rec.releaseTargetReason,
          rec.releaseTargetRefusedBy,
        );
      } else {
        await releaseEndedRecord(pid, rec);
      }
    }
    return pending.length;
  }

  async function onWorkerSessionEnded(event = {}) {
    const pid = String(event.id || event.paneId || "");
    const rec = records.get(pid);
    if (!rec || !["running", "terminating"].includes(rec.state)) {
      return { released: false, matched: false };
    }
    const exactProcess = event
      && Number.isInteger(event.generation) && event.generation === rec.sessionGeneration
      && Number.isInteger(event.pid) && event.pid === rec.pid;
    if (!exactProcess) return { released: false, matched: false };
    if (event.kind === "kill" && event.processExited === false) {
      set(pid, { state: "terminating", reason: "session termination requested" });
      return { released: false, matched: true, awaitingProcessExit: true };
    }
    if (event.kind !== "exit" || event.processExited !== true) {
      return { released: false, matched: false };
    }
    if (rec.nodeId) revokeNodeControl(rec.nodeId);
    const ended = set(pid, {
      state: "release_pending", endedAt: new Date().toISOString(),
      exitCode: Number.isFinite(event.exitCode) ? event.exitCode : null,
      reason: `session exited (${event.exitCode}); releasing durable terminal`,
    });
    return releaseEndedRecord(pid, ended);
  }

  /** Session keys whose terminal remains held through exit or owner-death reconciliation (D-LOOP-1). */
  function heldSessions() {
    return [...records.values()]
      .filter((r) => ["running", "launching", "terminating", "release_pending", "release_failed"]
        .includes(r.state) && r.sessionId)
      .map((r) => r.sessionId);
  }

  return {
    launchWorkerPane,
    onWorkerSessionEnded,
    retryPendingReleases,
    heldSessions,
    record: (paneId) => ({ ...get(paneId) }),
    records: () => [...records.values()].map((r) => ({ ...r })),
    updateRecord: (paneId, patch) => ({ ...set(paneId, patch || {}) }),
  };
}

module.exports = { createWorkerPaneLauncher, WORKER_LAUNCH_STATES, emptyRecord };
