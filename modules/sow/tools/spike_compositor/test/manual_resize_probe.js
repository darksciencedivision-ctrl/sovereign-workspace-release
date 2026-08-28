"use strict";
/* Headless resize diagnostic (not part of npm test): spawns the TUI under ConPTY,
   resizes, and prints every TUI-SIZE report. Run: node test/manual_resize_probe.js */
const path = require("path");
const pty = require("node-pty");
const node = process.execPath; // plain node here
const p = pty.spawn(node, [path.join(__dirname, "..", "scenarios", "tui.js")], {
  name: "xterm-256color", cols: 100, rows: 30, cwd: __dirname, env: process.env, useConpty: true,
});
const seen = [];
p.onData((d) => { for (const m of d.matchAll(/TUI-SIZE (\d+)x(\d+)/g)) seen.push(`${m[1]}x${m[2]}`); });
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  await wait(1200);
  console.log("initial reports:", [...new Set(seen)]);
  seen.length = 0;
  p.resize(80, 20);
  await wait(1200);
  console.log("after resize 80x20:", [...new Set(seen)]);
  seen.length = 0;
  p.resize(120, 34);
  await wait(1200);
  console.log("after resize 120x34:", [...new Set(seen)]);
  p.kill();
  process.exit(0);
})();
