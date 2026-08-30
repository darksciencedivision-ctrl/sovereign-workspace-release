"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { WorkspaceProcessTree } = require("../selfcheck/process-tree");
const fs = require("node:fs");
const path = require("node:path");
const {
  sourceIdentity,
  committedTreeCheckName,
} = require("../selfcheck/voice-conductor-selfcheck");

test("self-check cleanup tracks descendants, terminates them, and awaits zero Node survivors", async () => {
  let rows = [
    { pid: 100, parentPid: 1, name: "electron.exe", commandLine: "electron app" },
    { pid: 101, parentPid: 100, name: "node.exe", commandLine: "node helper" },
    { pid: 102, parentPid: 101, name: "conhost.exe", commandLine: "" },
  ];
  const terminated = [];
  const guard = new WorkspaceProcessTree(100, {
    snapshot: async () => rows.map((row) => ({ ...row })),
    terminate: async (pid) => {
      terminated.push(pid);
      const killed = new Set([pid]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const row of rows) {
          if (killed.has(row.parentPid) && !killed.has(row.pid)) {
            killed.add(row.pid);
            changed = true;
          }
        }
      }
      rows = rows.filter((row) => !killed.has(row.pid));
    },
    shutdownTimeoutMs: 100,
  });
  await guard.sample();
  const result = await guard.cleanup();
  assert.deepEqual(result.tracked, [100, 101, 102]);
  assert.deepEqual(terminated, [100]);
  assert.deepEqual(result.workspaceNodeRemaining, []);
});

test("self-check cleanup reports a Node descendant that resists termination", async () => {
  const rows = [
    { pid: 200, parentPid: 1, name: "electron.exe", commandLine: "electron app" },
    { pid: 201, parentPid: 200, name: "node.exe", commandLine: "node leaked-helper.js" },
  ];
  const guard = new WorkspaceProcessTree(200, {
    snapshot: async () => rows,
    terminate: async () => {},
    shutdownTimeoutMs: 1,
  });
  await guard.sample();
  const result = await guard.cleanup();
  assert.deepEqual(result.workspaceNodeRemaining.map((row) => row.pid), [200, 201]);
});

test("bootstrap exit does not count as self-check completion while a tracked Electron descendant lives", async () => {
  let rows = [
    { pid: 300, parentPid: 1, name: "electron.exe", commandLine: "electron bootstrap" },
    { pid: 301, parentPid: 300, name: "electron.exe", commandLine: "electron app" },
  ];
  const guard = new WorkspaceProcessTree(300, {
    snapshot: async () => rows.map((row) => ({ ...row })),
    sampleIntervalMs: 1,
  });
  await guard.sample();
  rows = rows.filter((row) => row.pid !== 300);

  let settled = false;
  const waiting = guard.waitForWorkspaceExit({ timeoutMs: 100, pollIntervalMs: 1 })
    .then(() => { settled = true; });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(settled, false);

  rows = [];
  await waiting;
  assert.equal(settled, true);
});

test("waiting for self-check completion times out without killing a live descendant", async () => {
  const rows = [
    { pid: 400, parentPid: 1, name: "electron.exe", commandLine: "electron bootstrap" },
    { pid: 401, parentPid: 400, name: "node.exe", commandLine: "node live helper" },
  ];
  const guard = new WorkspaceProcessTree(400, {
    snapshot: async () => rows.map((row) => ({ ...row })),
    sampleIntervalMs: 1,
  });
  await guard.sample();

  await assert.rejects(
    guard.waitForWorkspaceExit({ timeoutMs: 5, pollIntervalMs: 1 }),
    (error) => error && error.code === "SELF_CHECK_TIMEOUT"
      && error.workspaceNodeRemaining.some((row) => row.pid === 401),
  );
});

test("the packaged launcher puts Electron behind the pre-spawn Windows job host", () => {
  const launcher = fs.readFileSync(path.join(__dirname, "../selfcheck/run.js"), "utf8");
  assert.match(launcher, /windows-job-host\.py/);
  assert.match(launcher, /process\.platform === "win32"/);

  // EPC-01 P0-2: the launcher used to carry the "-3.12" literal itself. The pin did not go
  // away — it MOVED to python-runtime.js, which is now the single place that decides which
  // interpreter this app spawns. Asserting the literal here would now pass only by accident
  // of where the string happens to live, so the guard follows the pin instead: the launcher
  // must resolve through the resolver, and the resolver must still pin 3.12.
  assert.match(launcher, /require\("\.\.\/python-runtime"\)/,
    "the launcher must take its interpreter from python-runtime.js, not hardcode one");
  const resolver = fs.readFileSync(path.join(__dirname, "../python-runtime.js"), "utf8");
  assert.match(resolver, /"-3\.12"/,
    "python-runtime.js must still pin 3.12 for the py-launcher fallback");
});

test("the Phase 17C receipt claims NO product-tree exclusion, because it no longer needs one", () => {
  const source = sourceIdentity();
  // `apps/desktop/package-lock.json` was the single carve-out and it has been TRACKED since 3d57eeb,
  // so `git ls-files --others` stopped listing it: the exclusion excluded nothing while the receipt
  // still advertised a hole (gate-validator R-5). An empty list is the honest description, and it
  // makes the check strictly stricter — any untracked product file now fails it.
  assert.deepEqual(source.disclosed_untracked_product_exclusions, []);
  assert.equal(
    committedTreeCheckName,
    "receipt_matches_committed_tracked_product_tree_with_disclosed_exclusions",
  );
  assert.equal(
    Object.prototype.hasOwnProperty.call(
      source,
      "preexisting_untracked_excluded",
    ),
    false,
  );
});

test("main-process teardown wording is limited to the resources it actually measures", () => {
  const main = fs.readFileSync(path.join(__dirname, "../main.js"), "utf8");
  assert.doesNotMatch(main, /zero tracked Electron children/);
  assert.match(main, /zero managed terminal sessions; gateway exited/);
});
