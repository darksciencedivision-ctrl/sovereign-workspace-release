"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const { selectObjectiveRecipients } = require("../control/conductor-delegation");
test("F-36: three live worker panes and one objective produce three identical-objective recipients", () => {
  const live = [
    { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } },
    { nodeId: "n-c", paneId: "pane-4", chrome: { role: "reasoning" } },
  ];
  const { recipients } = selectObjectiveRecipients(live, live);
  assert.equal(recipients.length, 3);
  assert.deepEqual(recipients.map(r => r.pane_id).sort(), ["pane-2", "pane-3", "pane-4"]);
});
test("F-36: participation tracks panes open, not plan shape", () => {
  const a = { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } };
  const b = { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } };
  const c = { nodeId: "n-c", paneId: "pane-4", chrome: { role: "reasoning" } };
  const d = { nodeId: "n-d", paneId: "pane-5", chrome: { role: "coding" } };
  assert.equal(selectObjectiveRecipients([a, b, c, d], [a, b, c, d]).recipients.length, 4);
  assert.equal(selectObjectiveRecipients([a, b], [a, b, c]).recipients.length, 2);
});
test("F-36: panes of differing roles all receive the objective", () => {
  const live = [
    { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } },
  ];
  const { recipients } = selectObjectiveRecipients(live, live);
  assert.ok(recipients.some(r => r.role === "reasoning"));
  assert.ok(recipients.some(r => r.role === "coding"));
  assert.equal(recipients.length, 2);
});
test("F-36: a registered-but-not-live pane is reported with its reason", () => {
  const live = [{ nodeId: "n-a", paneId: "pane-2" }];
  const registered = [live[0], { nodeId: "n-idle", paneId: "pane-9", state: "exited" }];
  const { recipients, skipped } = selectObjectiveRecipients(live, registered);
  assert.equal(recipients.length, 1);
  assert.equal(skipped.length, 1);
  assert.equal(skipped[0].node_id, "n-idle");
  assert.equal(skipped[0].delivered, false);
  assert.match(skipped[0].reason, /no live pane is registered for this assignment/);
});
test("F-36: runObjective no longer selects recipients from the assignment list", () => {
  const main = fs.readFileSync(path.resolve(__dirname, "../main.js"), "utf8");
  const from = main.indexOf("async function runObjective(objective, options = {}) {");
  const to = main.indexOf("ipcMain.handle(\"conductor:run-objective\"", from);
  const body = main.slice(from, to);
  assert.match(body, /selectObjectiveRecipients\(liveWorkerRecords\(\)/);
  assert.doesNotMatch(body, /for \(const assignment of feed\.assignments/);
  assert.match(body, /task_id: objectiveId/);
  assert.match(body, /conductor_reasoning/);
  assert.match(body, /does not select recipients/);
});
test("F-36 mutation control: restoring assignment-list selection fails the differing-roles test", () => {
  const filename = require.resolve("../control/conductor-delegation");
  const source = fs.readFileSync(filename, "utf8");
  const mutant = new Module(filename, module); mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(
    "function selectObjectiveRecipients(liveRecords, registeredRecords = []) {",
    "function selectObjectiveRecipients(liveRecords, registeredRecords = [], assignments) {\n"
      + "  if (assignments) {\n"
      + "    const live = new Map((liveRecords||[]).map(r => [r.nodeId, r]));\n"
      + "    return { recipients: assignments.filter(a => live.get(a.node) && live.get(a.node).chrome && live.get(a.node).chrome.role === a.role).map(a => ({ node_id: a.node, pane_id: live.get(a.node).paneId, role: a.role })), skipped: [] };\n"
      + "  }"), filename);
  const live = [
    { nodeId: "n-a", paneId: "pane-2", chrome: { role: "reasoning" } },
    { nodeId: "n-b", paneId: "pane-3", chrome: { role: "coding" } },
  ];
  const leaked = mutant.exports.selectObjectiveRecipients(live, live,
    [{ node: "n-a", role: "reasoning" }]);
  assert.equal(leaked.recipients.length, 1);
  const good = selectObjectiveRecipients(live, live);
  assert.equal(good.recipients.length, 2);
});
