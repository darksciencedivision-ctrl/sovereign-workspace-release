"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const V = require("../control/conductor-view");
const { spawnSync } = require("node:child_process");
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
const script = "import importlib.util,json; s=importlib.util.spec_from_file_location('j','apps/desktop/control/journal-store.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.budget({'vram_mib':8151})))";
const child = spawnSync(defaultPython(), [...defaultPythonArgs(), "-B", "-c", script],
  { cwd: path.resolve(__dirname, "../../.."), encoding: "utf8", windowsHide: true });
assert.equal(child.status, 0, child.stderr);
const large = JSON.parse(child.stdout);
function entry(id) {
  return J.prepareEntry({ node_id: "node-" + id, pane_id: "pane-" + id, model: "m", status: "answered",
    objective: "q", prompt: "p", answer: "from pane " + id, source: J.SOURCE, self_published: false },
    "session-test", () => "2026-09-06T00:00:00Z");
}
const open = [
  { pane_id: "pane-2", node_id: "node-2", live: true },
  { pane_id: "worker-pane-4", node_id: "node-4", live: true },
  { pane_id: "pane-7", node_id: "node-7", live: false },
];
test("F-33: each spelling resolves to the same pane id; unknown numbers resolve to nothing", () => {
  const spellings = ["terminal 2", "pane 2", "worker-pane-2", "#2", "2nd terminal", "second pane"];
  for (const text of spellings) {
    const r = V.resolveTerminalRefs(text, open);
    assert.ok(r.ids.includes("pane-2"), text);
    assert.equal(r.notices.length, 0, text);
  }
  const miss = V.resolveTerminalRefs("terminal 5", open);
  assert.deepEqual(miss.ids, []);
  assert.ok(miss.notices.some(n => /no terminal 5 is open/.test(n)));
});
test("F-33: unresolvable references are stated rather than silently answering another pane", () => {
  const v = V.composeView("what did terminal 5 say", [entry(2), entry(4)], large, "", open);
  assert.match(v.view, /no terminal 5 is open/);
  assert.doesNotMatch(v.view, /from pane 2|from pane 4/);
});
test("F-33: a pane that exists but is not live is distinguished from one that does not exist", () => {
  const idle = V.resolveTerminalRefs("terminal 7", open);
  assert.ok(idle.notices.some(n => /terminal 7 is not live/.test(n)));
  assert.doesNotMatch(idle.notices.join(" "), /no terminal 7 is open/);
  const missing = V.resolveTerminalRefs("terminal 9", open);
  assert.ok(missing.notices.some(n => /no terminal 9 is open/.test(n)));
});
test("F-33: view labels carry the on-screen terminal number", () => {
  const v = V.composeView("terminal 2", [entry(2)], large, "", open);
  assert.match(v.view, /terminal=#2/);
  assert.match(v.view, /pane=pane-2/);
});
test("F-33 mutation control: removing the resolver makes a reference test fail", () => {
  const filename = require.resolve("../control/conductor-view");
  const source = fs.readFileSync(filename, "utf8");
  const mutant = new Module(filename, module); mutant.filename = filename;
  mutant.paths = Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(
    "function resolveTerminalRefs(message, openPanes = []) {\n  if (!openPanes.length) return { ids: [], notices: [], attempted: false };",
    "function resolveTerminalRefs(message, openPanes = []) {\n  return { ids: [], notices: [], attempted: false };"),
    filename);
  const r = mutant.exports.resolveTerminalRefs("terminal 2", open);
  assert.deepEqual(r.ids, []);
  assert.ok(V.resolveTerminalRefs("terminal 2", open).ids.includes("pane-2"));
});
test("F-33 source pins: pane chrome shows the number", () => {
  const renderer = fs.readFileSync(path.resolve(__dirname, "../renderer/renderer.js"), "utf8");
  const html = fs.readFileSync(path.resolve(__dirname, "../renderer/index.html"), "utf8");
  assert.match(renderer, /class="pnum"/);
  assert.match(renderer, /pnum\.textContent = n \? "#" \+ n\[1\] : ""/);
  assert.match(html, /\.bar \.pnum/);
});
