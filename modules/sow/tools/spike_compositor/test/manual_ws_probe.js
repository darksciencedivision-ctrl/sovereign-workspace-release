"use strict";
/* Headless U9 diagnostic 3 (manual; not part of npm test): shows that a Node child's
   process.stdout.getWindowSize() AND .columns stay stale after ResizePseudoConsole —
   the Node-child tty limitation behind the tui.js mode-con workaround.
   Run: node test/manual_ws_probe.js  (expected output: "after 80x20: WS 100x30 cols=100") */
const pty = require("node-pty");
const p = pty.spawn(process.execPath, ["-e", "setInterval(()=>{try{const ws=process.stdout.getWindowSize();console.log(`WS ${ws[0]}x${ws[1]} cols=${process.stdout.columns}`)}catch(e){console.log('WS-ERR '+e.message)}},400)"], { name: "xterm-256color", cols: 100, rows: 30, cwd: __dirname, env: process.env, useConpty: true });
let buf=""; p.onData(d=>buf+=d);
(async()=>{ const w=(ms)=>new Promise(r=>setTimeout(r,ms));
  await w(1000); buf="";
  p.resize(80,20); await w(1000); console.log("after 80x20:", [...new Set([...buf.matchAll(/WS [^ ]+ cols=\d+/g)].map(m=>m[0]))].join(" | "));
  p.kill(); process.exit(0); })();
