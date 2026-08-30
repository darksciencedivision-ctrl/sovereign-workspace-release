"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
/**
 * Phase 16A self-check launcher (D-P16-0). Runs the packaged Electron shell in SHELL_SELFCHECK mode
 * via `node` (the permitted entrypoint — same as `npm start` would spawn electron), with a hard
 * timeout so a hung GUI can never wedge the build loop. The shell writes the receipt and exits with
 * its pass/fail code; this launcher mirrors that code.
 *
 * One-command operator run:  node selfcheck/run.js                  (16A pane-I/O check)
 *                             node selfcheck/run.js picker           (16B model-picker check)
 *                             node selfcheck/run.js op12-picker      (18B Grok/Antigravity in the picker)
 *                             node selfcheck/run.js op12-acceptance  (18C OP-12 acceptance in the fail-closed world)
 *                             node selfcheck/run.js op12-live-acceptance (18E the LIVE per-provider acceptance leg)
 *                             node selfcheck/run.js op18d-registration (18D both providers register as node@1.1 Sovereign nodes)
 *                             node selfcheck/run.js conductor        (16C conductor-selection check)
 *                             node selfcheck/run.js conductor-spawn  (16C governed spawn of pane 1)
 *                             node selfcheck/run.js conductor-dispatch (16C governed worker dispatch)
 *                             node selfcheck/run.js statusbar         (16D status-bar n/2 governor feed)
 *                             node selfcheck/run.js approvals          (16D approval-drawer governed feed)
 *                             node selfcheck/run.js recovery           (16D worker-pane chrome across restart)
 *                             node selfcheck/run.js voice              (16E talk button → bridge → conductor input)
 *                             node selfcheck/run.js voice-probe        (17C non-blocking STT engine probe, U74)
 *                             node selfcheck/run.js voice-mic          (17C real PCM → WSL Parakeet → conductor, U137)
 *                             node selfcheck/run.js voice-conductor    (17C speech → the LIVE conductor session → its answer)
 *                             node selfcheck/run.js assembled          (16F operator-visible assembled run)
 *                             node selfcheck/run.js conductor-launch   (17A governed launch ticket + durable I-X3 lease)
 *                             node selfcheck/run.js conductor-pty      (17A LIVE conductor session in pane 1's ConPTY)
 *                             node selfcheck/run.js conductor-roundtrip (17A type → LIVE answer in pane 1)
 *                             node selfcheck/run.js worker-launch      (17B governed worker launch ticket, both localities)
 *                             node selfcheck/run.js worker-spawn       (17B LIVE worker session from a picker selection)
 *                             node selfcheck/run.js pane-guards        (17D sessionless-pane resize guard [U73] + the U69 attempt)
 *                             node selfcheck/run.js system-pane-write  (19.3 the system→pane modal gate [U328])
 *                             node selfcheck/run.js readiness-window   (19.4 the bounded readiness window [U329])
 *                             node selfcheck/run.js conductor-descriptor (19.6 descriptor-derived readiness + declared traits [U331])
 *                             node selfcheck/run.js runtime-honesty    (19.7 bounded stop + stale MCP + unreadable-is-not-empty [U334/U335/U336])
 *                             node selfcheck/run.js orchestration-collaboration (19.8 governed flow + evidence provenance [U337])
 *                             node selfcheck/run.js fully-live        (17E the fully-live ASSEMBLED composition)
 * (from apps/desktop, after `npm install`)
 */
const { spawn } = require("child_process");
const path = require("path");
const electron = require("electron"); // resolves to the electron.exe path string
const { WorkspaceProcessTree } = require("./process-tree");

// Which in-Electron self-check to run (D-P16-0 is per-track): `picker` → 16B; `conductor` → 16C
// selection; `conductor-spawn` → 16C governed spawn of pane 1; `conductor-dispatch` → 16C governed
// worker dispatch; default → 16A pane-I/O.
const KIND = process.argv[2] === "op12-picker" ? "op12-picker"
  : process.argv[2] === "op12-acceptance" ? "op12-acceptance"
  : process.argv[2] === "op12-live-acceptance" ? "op12-live-acceptance"
  : process.argv[2] === "op18d-registration" ? "op18d-registration"
  : process.argv[2] === "picker" ? "picker"
  : process.argv[2] === "conductor" ? "conductor"
    : process.argv[2] === "conductor-spawn" ? "conductor-spawn"
      : process.argv[2] === "conductor-dispatch" ? "conductor-dispatch"
        : process.argv[2] === "statusbar" ? "statusbar"
          : process.argv[2] === "approvals" ? "approvals"
            : process.argv[2] === "recovery" ? "recovery"
              : process.argv[2] === "voice" ? "voice"
                : process.argv[2] === "voice-probe" ? "voice-probe"
                : process.argv[2] === "voice-mic" ? "voice-mic"
                : process.argv[2] === "voice-conductor" ? "voice-conductor"
                : process.argv[2] === "assembled" ? "assembled"
                  : process.argv[2] === "conductor-launch" ? "conductor-launch"
                    : process.argv[2] === "conductor-pty" ? "conductor-pty"
                      : process.argv[2] === "conductor-roundtrip" ? "conductor-roundtrip"
                        : process.argv[2] === "worker-launch" ? "worker-launch"
                          : process.argv[2] === "worker-spawn" ? "worker-spawn"
                          : process.argv[2] === "pane-guards" ? "pane-guards"
                          : process.argv[2] === "system-pane-write" ? "system-pane-write"
                          : process.argv[2] === "readiness-window" ? "readiness-window"
                          : process.argv[2] === "conductor-descriptor" ? "conductor-descriptor"
                          : process.argv[2] === "runtime-honesty" ? "runtime-honesty"
                          : process.argv[2] === "orchestration-collaboration" ? "orchestration-collaboration"
                          : process.argv[2] === "fully-live" ? "fully-live"
                            : "1";
const appDir = path.resolve(__dirname, "..");

// An OPTIONAL label for which work unit ran this check, passed through to the shell as
// `SOW_SELFCHECK_UNIT` and recorded in the receipt (gate-validator MINOR-1: two receipts of the same
// kind were told apart by filename alone). `--unit <label>`, or the env var directly. It carries no
// authority — `source.commit` and `started` are the measured facts; this is what the runner SAID.
const unitFlag = process.argv.indexOf("--unit");
const UNIT_LABEL = unitFlag > 0 && process.argv[unitFlag + 1]
  ? process.argv[unitFlag + 1]
  : (process.env.SOW_SELFCHECK_UNIT || "");

// `conductor-roundtrip` waits on a LIVE model answer AND, on a host whose accepted `--model` slug is
// not yet cached, on the governed model probe (≤200 s). Its ceiling is the sum of the check's own
// per-step ceilings plus that budget plus headroom: the check must fail with the step it stalled on
// NAMED, rather than be killed blind by this launcher.
// `worker-launch` runs the host picker enumeration plus five bounded emitter round trips (two
// authorizations, two refusals, the cross-process status read) — each with its own 90 s ceiling, so
// the launcher's bound must sit above their sum or a slow-but-honest host is killed blind.
// `op12-picker` runs the REAL host enumeration, which now includes four bounded provider metadata
// calls (`grok --version`/`models`, `agy --version`/`models`) on top of the Ollama probe.
// `op12-acceptance` runs the host enumeration once (four bounded provider metadata calls plus the
// Ollama probe), then TWO more emitter round trips per provider — the launcher's governed ask and
// the ticket read that carries the gate map — each of which re-enumerates, scoped to that
// provider's own CLI (two metadata calls each, U290). Each has its own 120 s ceiling, and the
// durable lease-status read and the ticket-key releases follow. Their sum sits well past the 150 s
// default, and a launcher that kills a slow-but-honest run writes NO receipt (exit 124), which
// reports nothing.
// `op18d-registration` runs the host picker enumeration once (four bounded provider metadata
// calls plus the Ollama probe), then ONE bounded Python round trip that opens two real governed
// sessions against scratch state and makes no host call at all, then the durable lease-status
// read. Each leg has its own 120 s ceiling; the sum sits past the 150 s default, and a launcher
// that kills a slow-but-honest run writes NO receipt (exit 124), which reports nothing.
// `op12-live-acceptance` is the LIVE 18E leg: one picker enumeration, then PER PROVIDER a governed
// ticket (its own enumeration), a real CLI session coming up in a ConPTY, a settling TUI, one typed
// prompt, one live model answer (≤210 s), a kill, a durable release read from a separate process
// and a node-log close. Its own per-step ceilings sum past 900 s for the two providers together,
// and a launcher that kills a slow-but-honest run writes NO receipt (exit 124), which reports
// nothing about a live call that was nonetheless spent.
const HARD_TIMEOUT_MS = KIND === "op12-live-acceptance" ? 1500000
  : KIND === "op18d-registration" ? 420000
  : KIND === "op12-acceptance" ? 600000
  : KIND === "op12-picker" ? 300000
  : KIND === "conductor-roundtrip" ? 600000
  : KIND === "conductor-pty" ? 300000
    : KIND === "worker-launch" ? 420000
      // `worker-spawn` LAUNCHES two live sessions (a local model that may have to load into VRAM and
      // a frontier CLI), waits for each pane to render, exercises two refusals and waits for the
      // durable terminal to come back — every step bounded, but their sum is well past 420 s on a
      // cold host, and a launcher that kills a slow-but-honest run reports nothing useful.
      : KIND === "worker-spawn" ? 600000
        // `voice-probe` waits on FOUR real WSL NeMo probes — the launch probe, a forced re-probe, the
        // independent reference probe (its own 330 s ceiling), and the re-arm leg — plus supervision
        // and two chrome waits. Its own internal ceilings sum to ~640 s, so this must sit above THAT,
        // not above a guess: a launcher that kills at 360 s takes out a cold-but-honest host BEFORE the
        // receipt is written (exit 124, no receipt), which is precisely how U74 stayed invisible.
        : KIND === "voice-probe" ? 900000
          // `voice-mic` synthesizes a fixture (up to 120 s cold), then runs a REAL WSL Parakeet
          // transcription whose own budget is 180 s and which pays a cold `from_pretrained` model load
          // on top (measured at 41.8 s at 16E, worse on a cold page cache), then two panes and two
          // honesty negatives. Its internal ceilings sum past 600 s, and a launcher that kills a
          // slow-but-honest run writes NO receipt (exit 124) — precisely how U74 stayed invisible.
          : KIND === "voice-mic" ? 900000
            // `voice-conductor` is the sum of BOTH long paths: a governed LIVE launch (plus the model
            // probe on an uncached host), the CLI settling, the fixture, a REAL WSL Parakeet
            // transcription, then a LIVE model answer, then teardown of the session and its durable
            // terminal. Its own per-step ceilings sum past 1000 s; this must sit above THAT, because a
            // launcher that kills a slow-but-honest run writes NO receipt (exit 124) and reports nothing.
            // `.disarm` (U166) adds a SECOND live exchange to that check — the operator's typed prompt
            // after the voice turn ends — which is another ECHO_MS + ANSWER_MS (210 s) plus two bounded
            // hook dispatches. Raised from 1320 s to 1800 s so the sum still fits under it with room.
            // `.receipt` (U177) adds the runtime channel sweep: 24 renderer intents, several of which
            // are bounded Python emitter round trips (the picker enumeration, the status bar, the
            // approval route) with their own 60–90 s ceilings. Their worst case is ~300 s, so the
            // launcher's bound goes to 2100 s rather than eating the room the sum above needs.
            : KIND === "voice-conductor" ? 2100000
              // `approvals` (17D `.events`) no longer reads one canned feed: it waits for the launch
              // drawer, drives a REAL voice capture through the bridge — whose engine selection can pay
              // the WSL NeMo probe — then makes three more bounded `py -3.12` emitter round trips (the
              // re-fetch, the decide, the re-decide) while the launch-time governed dispatch is still
              // running its own MCP-backed emitter. The old 150 s default killed a run whose receipt was
              // 21/21 green, i.e. it would have reported a shell failure that had not happened.
              : KIND === "approvals" ? 420000
                // `pane-guards` (17D `.close`) starts no model and makes no emitter round trip, but it
                // does wait on supervision (25 s), a pane's xterm view (15 s), a cold PowerShell banner
                // (25 s) and two 12 s echo polls, and it types character-by-character. Their sum sits
                // just under the 150 s default — close enough that a cold host would be killed BEFORE
                // the receipt is written (exit 124, nothing to read), which is the failure mode every
                // one of these bounds above was raised to avoid.
                // `system-pane-write` (19.3, U328) starts no model and makes no emitter round trip,
                // but it waits on supervision (30 s), then TWO supervised panes each needing an
                // xterm view (20 s) and a cold PowerShell banner (30 s), three delivery
                // observations (20 s each) and one bounded absence watch. Their sum sits above the
                // 150 s default, and a launcher that kills a slow-but-honest run writes NO receipt
                // (exit 124), which reports nothing about a gate that may be perfectly fine.
                : KIND === "system-pane-write" ? 300000
                // `readiness-window` (19.4, U329) starts no model and makes no emitter round trip.
                // It waits on supervision (30 s), then FOUR supervised panes each needing an xterm
                // view (20 s) and a cold PowerShell banner (30 s), then three bounded output waits
                // (30 s each), one typed-echo wait, and three READINESS RUNS whose own deadlines are
                // 1.5 s + 12 s + 1.5 s plus the U328 gate's paste-settle inside each delivered write.
                // Their sum sits well above the 150 s default and above the 300 s this kind used
                // before the run legs existed, and a launcher that kills a slow-but-honest run
                // writes NO receipt (exit 124), which reports nothing about a state machine that
                // may be perfectly fine.
                : KIND === "readiness-window" ? 600000
                // `conductor-descriptor` (19.6, U331) starts no model and makes no emitter round
                // trip. It waits on supervision (30 s), then THREE supervised panes each needing
                // an xterm view (20 s) and a cold PowerShell banner (30 s), two typed-echo waits
                // (30 s each) and three bounded output waits, plus the U328 gate's paste-settle
                // inside each of the two gated writes. Their sum sits above the 150 s default,
                // and a launcher that kills a slow-but-honest run writes NO receipt (exit 124).
                : KIND === "conductor-descriptor" ? 420000
                // `runtime-honesty` (19.7, U334/U335/U336) starts no model, spawns no pane and makes
                // no emitter round trip that can succeed: leg A's stop budget is 0.8 s under a 5 s
                // ceiling, legs B/C are loopback HTTP, leg D is one bounded emitter read (15 s) and
                // leg E deliberately fails to launch one. Their sum is well under a minute; the bound
                // is generous only so a cold host writes its receipt rather than being killed blind
                // (exit 124 reports nothing).
                : KIND === "runtime-honesty" ? 180000
                : KIND === "orchestration-collaboration" ? 240000
                : KIND === "pane-guards" ? 300000
                  // `fully-live` (17E) is the COMPOSITION, so its bound is the sum of the long paths
                  // it composes: the governed live launch (plus the model probe on an uncached host),
                  // the CLI settling, a fixture, a REAL WSL Parakeet transcription, a live spoken
                  // answer, a live typed answer, the host picker enumeration, a local model session
                  // coming up, and a LIVE governed dispatch whose own ceiling is 900 s (17B `.legs`
                  // measured 277 s on this host) — then teardown of two sessions and their durable
                  // terminals. Its internal ceilings sum past 2400 s; a launcher that kills a
                  // slow-but-honest run writes NO receipt (exit 124) and reports nothing.
                  : KIND === "fully-live" ? 3000000
                    : 150000;
// U157: a polling process inventory cannot own a child that reparents before its first sample.
// On Windows the Python host creates a Job Object, assigns a gated member BEFORE that member may
// spawn Electron, and waits for the job to become empty. Killing the host closes the kill-on-close job.
const jobHost = path.join(__dirname, "windows-job-host.py");
const child = process.platform === "win32"
  ? spawn(defaultPython(), [...defaultPythonArgs(), jobHost, "--timeout-ms", String(HARD_TIMEOUT_MS), "--", electron, appDir,
    ], {
      cwd: appDir,
      stdio: "inherit",
      env: { ...process.env, SHELL_SELFCHECK: KIND, SOW_SELFCHECK_UNIT: UNIT_LABEL },
    })
  : spawn(electron, [appDir], {
      cwd: appDir,
      stdio: "inherit",
      detached: true,
      env: { ...process.env, SHELL_SELFCHECK: KIND, SOW_SELFCHECK_UNIT: UNIT_LABEL },
    });
function waitForShell() {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      const error = new Error("hard timeout");
      error.code = "SELF_CHECK_TIMEOUT";
      reject(error);
    }, HARD_TIMEOUT_MS);
    child.once("exit", (code, signal) => {
      clearTimeout(timeout);
      resolve({ code, signal });
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
}

async function main() {
  let exitCode = 1;
  const processTree = new WorkspaceProcessTree(child.pid);
  processTree.start();
  try {
    const result = await waitForShell();
    // On Windows the child is the pre-spawn Job Object host and cannot exit until its job is empty.
    // The inventory remains a second, fail-closed check on the host and every descendant it observes.
    await processTree.waitForWorkspaceExit({ timeoutMs: HARD_TIMEOUT_MS });
    exitCode = result.code == null ? 1 : result.code;
    console.error(`[selfcheck/run] shell exited code=${result.code} signal=${result.signal || "-"}`);
  } catch (error) {
    if (error.code === "SELF_CHECK_TIMEOUT") {
      exitCode = 124;
      console.error("[selfcheck/run] hard timeout — killing the shell");
    } else {
      console.error(`[selfcheck/run] launch error: ${error.message}`);
    }
  } finally {
    // Always reap the job host/process group and await OS confirmation before this pipe owner exits.
    try {
      const cleanup = await processTree.cleanup();
      console.error(`[selfcheck/run] tracked pids=${cleanup.tracked.join(",") || "-"}; remaining=`
        + `${cleanup.remaining.map((row) => row.pid).join(",") || "-"}`);
      if (cleanup.workspaceNodeRemaining.length) {
        exitCode = 1;
        console.error("[selfcheck/run] FAIL: workspace Node/Electron descendants remain: "
          + cleanup.workspaceNodeRemaining.map((row) => `${row.name}:${row.pid}`).join(", "));
      }
    } catch (error) {
      exitCode = 1;
      console.error(`[selfcheck/run] process-tree cleanup failed: ${error.message}`);
    }
  }
  // Natural exit lets Node flush stderr; process.exit() could close Electron's inherited output pipe
  // while late stream writes were still settling.
  process.exitCode = exitCode;
}

void main();
