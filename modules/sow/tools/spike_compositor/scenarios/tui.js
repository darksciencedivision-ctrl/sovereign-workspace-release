"use strict";
/* Full-screen, resize-aware, animated TUI (U9 probe). Prints "TUI-SIZE <cols>x<rows>" on
   every redraw so resize correctness is machine-checkable. Alt-screen + cursor addressing.
   U9 finding (2026-07-16): ResizePseudoConsole reaches the console immediately (`mode con`
   proves it), but a Node child's tty layer (columns/rows AND getWindowSize()) stays stale
   under ConPTY — so this probe queries the console authoritatively via `mode con`. Real
   console apps (cmd, PowerShell, provider CLIs) see the resize natively. */
const { spawnSync } = require("child_process");
const out = process.stdout;
function consoleSize() {
  if (process.platform === "win32") {
    try {
      const r = spawnSync("cmd.exe", ["/c", "mode", "con"], { encoding: "utf8", timeout: 2000, stdio: ["ignore", "pipe", "ignore"] });
      const rows = /Lines:\s+(\d+)/.exec(r.stdout || ""), cols = /Columns:\s+(\d+)/.exec(r.stdout || "");
      if (rows && cols) return { cols: Number(cols[1]), rows: Number(rows[1]) };
    } catch { /* fall back below */ }
  }
  return { cols: out.columns || 80, rows: out.rows || 24 };
}
function draw() {
  const { cols, rows } = consoleSize();
  let s = "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l";
  const line = "#".repeat(cols);
  s += `\x1b[1;1H\x1b[36m${line}\x1b[0m`;
  s += `\x1b[${rows};1H\x1b[36m${line.slice(0, cols)}\x1b[0m`;
  for (let r = 2; r < rows; r++) s += `\x1b[${r};1H\x1b[36m#\x1b[${r};${cols}H#\x1b[0m`;
  const mid = Math.max(2, Math.floor(rows / 2));
  const t = new Date().toISOString();
  s += `\x1b[${mid};3H\x1b[33mFULL-SCREEN TUI ${t}\x1b[0m`;
  s += `\x1b[${mid + 1};3H\x1b[32mTUI-SIZE ${cols}x${rows}\x1b[0m`;
  s += `\x1b[${mid + 2};3Hspinner: ${"|/-\\"[Math.floor(Date.now() / 250) % 4]}`;
  out.write(s);
}
out.on("resize", draw); // kept for non-Windows; no-op under ConPTY (see header)
const timer = setInterval(draw, 500); // 500 ms amortizes the mode-con query
draw();
function cleanup() { clearInterval(timer); out.write("\x1b[?1049l\x1b[?25h"); process.exit(0); }
process.on("SIGTERM", cleanup);
process.on("SIGINT", cleanup);
