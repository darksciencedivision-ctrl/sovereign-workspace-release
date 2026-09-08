"use strict";
/* Headless resize diagnostic 2: does ResizePseudoConsole reach the console itself?
   Uses cmd + `mode con` (authoritative console query). Run: node test/manual_resize_probe2.js */
const pty = require("node-pty");
const p = pty.spawn("cmd.exe", [], { name: "xterm-256color", cols: 100, rows: 30, cwd: __dirname, env: process.env, useConpty: true });
let buf = "";
p.onData((d) => { buf += d; });
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const modeCon = async () => {
    buf = "";
    p.write("mode con\r");
    await wait(900);
    const lines = [...buf.matchAll(/(Lines|Columns):\s+(\d+)/g)].map((m) => `${m[1]}=${m[2]}`);
    return lines.join(" ");
  };
  await wait(1500);
  console.log("initial:", await modeCon());
  p.resize(80, 20);
  await wait(500);
  console.log("after resize 80x20:", await modeCon());
  p.resize(120, 34);
  await wait(500);
  console.log("after resize 120x34:", await modeCon());
  p.kill();
  process.exit(0);
})();
