"use strict";
/**
 * U458 corrective B — a failed control-channel bootstrap must leave NOTHING behind.
 *
 * WHAT WENT WRONG, and why this file exists rather than a shorter `--test-timeout`. When W-41 broke
 * the envelope signature, five real-gateway test files stopped passing — and stopped TERMINATING.
 * Each spawned a Python gateway, hit a failing assertion, and skipped the `kill()` written as the
 * last statement of the test body. The gateway stayed alive with its stdout piped to the runner, the
 * event loop never drained, and `node --test` (which this project runs with `--test-timeout=0`)
 * never returned. `npm test` produced NO REPORT AT ALL for forty minutes.
 *
 * That is why the regression survived a whole tier: nobody had a result to read. A suite that cannot
 * report is worse than a suite that reports red. A shorter runner timeout would have made the corpse
 * easier to find; it would not have buried it, and the leaked gateway would still be holding a port.
 *
 * CLASSIFIED BEFORE REPAIRED, as the two candidates need different fixes:
 *   - the PRODUCT path is sound. `main.js` assigns `gatewayProc` immediately after `spawn()` — before
 *     the handshake can fail — and `teardown()` kills it while the quit path awaits
 *     `waitForChildExit(gatewayProc)`. A failed bootstrap in the shipped shell does not leak.
 *   - the TEST FIXTURES leaked. `supervisor.test.js` killed its private gateway inline after an
 *     assertion; `recovery-live.test.js` killed its gateway on the last line of the body. Neither
 *     was fenced, so any failure skipped both.
 * So this is a teardown repair, and the assertion below is about teardown.
 *
 * The property cannot be asserted from inside the process that would leak — "this process exits" is
 * only observable to a parent. So the failure is performed by `fixtures/gateway_bootstrap_failure.js`
 * in its own process and watched from here.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const { spawn, spawnSync, execFileSync } = require("node:child_process");

const HAVE_PY = spawnSync("py", ["-3.12", "--version"], { encoding: "utf8" }).status === 0;
const FIXTURE = path.join(__dirname, "fixtures", "gateway_bootstrap_failure.js");

//: Generous, and deliberately far below the time the leak actually cost. The bootstrap itself takes
//: about a second; anything approaching this ceiling means the process is not coming back.
const EXIT_BUDGET_MS = 60000;

function runFixture() {
  return new Promise((resolve) => {
    const started = Date.now();
    const proc = spawn(process.execPath, [FIXTURE], { cwd: path.resolve(__dirname, "..") });
    let out = "";
    let err = "";
    let timedOut = false;
    const to = setTimeout(() => { timedOut = true; try { proc.kill(); } catch { /* gone */ } },
      EXIT_BUDGET_MS);
    proc.stdout.on("data", (d) => { out += d.toString(); });
    proc.stderr.on("data", (d) => { err += d.toString(); });
    proc.on("exit", (code) => {
      clearTimeout(to);
      resolve({ code, out, err, timedOut, elapsedMs: Date.now() - started });
    });
  });
}

/**
 * Is THIS gateway — the one the fixture spawned — still alive?
 *
 * Scoped to one pid rather than counting gateways machine-wide, and that distinction is the whole
 * correctness of this check. The first version of this test counted every `run_gateway` process
 * before and after; it passed run in isolation and FAILED in the full desktop suite, which runs
 * these files concurrently and had four other gateways up at the time. A global count answers a
 * question about the machine, not about the teardown under test — the same "measured in the wrong
 * process" shape this programme has already recorded once.
 *
 * The pid is `py.exe`, which spawns a `python.exe` grandchild, so a process whose PARENT is that pid
 * counts as survival too: killing the launcher and orphaning the interpreter is not reaping.
 *
 * Windows-specific, and that is fine: this is the Windows-native host the programme targets, and it
 * is where the leak was observed. `null` means the question could not be asked, which is not the
 * same answer as "nothing survived" and is treated as such by the caller.
 */
function gatewayAlive(pid) {
  try {
    const out = execFileSync("powershell", ["-NoProfile", "-Command",
      "Get-CimInstance Win32_Process -Filter \"Name='py.exe' or Name='python.exe'\" "
      + `| Where-Object { $_.CommandLine -match 'run_gateway' -and ($_.ProcessId -eq ${pid} `
      + `-or $_.ParentProcessId -eq ${pid}) } | Measure-Object `
      + "| Select-Object -ExpandProperty Count"], { encoding: "utf8", timeout: 30000 });
    return Number(String(out).trim()) || 0;
  } catch {
    return null;
  }
}

test("U458: a failed control-channel bootstrap EXITS on its own and reaps its gateway",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    const r = await runFixture();

    assert.strictEqual(r.timedOut, false,
      `the process did not exit within ${EXIT_BUDGET_MS}ms after a failed bootstrap — a leaked child `
      + `is holding the event loop open, which is what made the whole suite unreportable\n${r.out}\n${r.err}`);
    // Not merely "it exited": it must have exited for the RIGHT reason. Exit 1 would mean the
    // supervisor came up under a wrong key, which is a worse finding than the leak.
    assert.strictEqual(r.code, 0, `fixture exited ${r.code}\n${r.out}\n${r.err}`);
    assert.match(r.out, /BOOTSTRAP_FAILED_AS_EXPECTED/,
      "the bootstrap did not actually fail, so nothing about the failure path was exercised");
    assert.match(r.out, /GATEWAY_REAPED/, "the teardown fence did not run");

    const pid = Number((r.out.match(/GATEWAY_PID (\d+)/) || [])[1]);
    assert.ok(Number.isInteger(pid) && pid > 0, `the fixture reported no gateway pid\n${r.out}`);
    const survivors = gatewayAlive(pid);
    if (survivors !== null) {
      assert.strictEqual(survivors, 0,
        `the gateway the failed bootstrap started (pid ${pid}) is still running — killing the `
        + "launcher without reaping the interpreter is not teardown");
    }
  });

test("U458: the fixture proves the failure path, not an absent one",
  { skip: !HAVE_PY ? "py -3.12 unavailable" : false }, async () => {
    // A guard against this whole file passing because the fixture silently stopped doing anything:
    // it must reach the failure, print it, and still come back well inside the budget.
    const r = await runFixture();
    assert.ok(r.elapsedMs < EXIT_BUDGET_MS / 2,
      `the failure path took ${r.elapsedMs}ms, which is close enough to the budget to be a hang`);
    assert.match(r.out, /BOOTSTRAP_FAILED_AS_EXPECTED[\s\S]*GATEWAY_REAPED/,
      "the failure must be observed BEFORE the teardown, or the ordering proves nothing");
  });
