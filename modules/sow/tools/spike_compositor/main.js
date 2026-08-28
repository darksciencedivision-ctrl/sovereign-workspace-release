"use strict";
/* Phase 1 spike rig — main process. THROWAWAY (Plan §16): no product UI, no control-plane
   code, no adapters. Owns every PTY; views detach/reattach freely (survival under test).
   All probe results are machine-collected into results/SPIKE_REPORT_<ts>.{json,md}. */
const { app, BrowserWindow, ipcMain } = require("electron");
const os = require("os");
const fs = require("fs");
const path = require("path");
const { execFile } = require("child_process");
const pty = require("node-pty");
const { SessionRegistry } = require("./lib/session-registry");
const { SeqChecker } = require("./lib/seq-check");
const { latencyStats } = require("./lib/stats");
const { lifecycleCheck } = require("./lib/lifecycle-check");
const { findOrphans, parseCimJson } = require("./lib/orphan-scan");

const IS_WIN = process.platform === "win32";
/* AUTORUN mode (loop directive phase-1-autorun): main+renderer run the full guided
   sequence programmatically and quit. SPIKE_AUTORUN_WAIT_S shortens the two 60 s
   observation windows for smoke runs only — evidence runs use the default. */
const AUTORUN = process.env.SPIKE_AUTORUN === "1";
const AUTORUN_WAIT_S = Number(process.env.SPIKE_AUTORUN_WAIT_S || 60);
const registry = new SessionRegistry();
const ptys = new Map(); // id -> IPty
const seq = new SeqChecker();
let win = null;

const state = {
  startedTs: new Date().toISOString(),
  ramBudgetMB: Number(process.env.SPIKE_RAM_BUDGET_MB || 2048),
  autorun: AUTORUN, autorunWaitS: AUTORUN ? AUTORUN_WAIT_S : null,
  lifecycleCheck: null, orphanScan: null,
  latency: null, latencyRenderer: null,
  crossPaneHits: [],
  resizeChecks: [], // {id, requested, reported, ok, ts}
  layoutStorm: null,
  metricsTimeline: [], // {ts, paneCount, procs:[{type,pid,cpu,rssMB}]}
  events: [], // supervised lifecycle log
  environment: {
    platform: process.platform, release: os.release(), arch: os.arch(),
    cpus: os.cpus().length, totalMemMB: Math.round(os.totalmem() / 1048576),
    node: process.versions.node, electron: process.versions.electron, chrome: process.versions.chrome,
  },
};
function logEvent(kind, detail) { state.events.push({ ts: new Date().toISOString(), kind, detail }); }

/* Scenario scripts must run in a CONSOLE-subsystem host: electron.exe is a GUI-subsystem
   binary, so under ConPTY its stdio never attaches to the pseudo-console (no output) and
   closing the ConPTY does not kill it (orphans). Prefer real node.exe; fall back to
   electron-as-node only when node is absent, and record which host was used. */
const NODE_EXE = (() => {
  try {
    const hit = require("child_process").execFileSync("where.exe", ["node.exe"], { encoding: "utf8" }).split(/\r?\n/)[0].trim();
    if (hit) return hit;
  } catch { /* fall through */ }
  return null;
})();
const scenarioHost = NODE_EXE ? { file: NODE_EXE, env: {} } : { file: process.execPath, env: { ELECTRON_RUN_AS_NODE: "1" } };
state.environment.scenarioHost = NODE_EXE ? NODE_EXE : "electron-as-node (GUI-subsystem: output/containment caveats)";
const SCENARIOS = {
  cmd: () => ({ file: "cmd.exe", args: [], name: "cmd (interactive)" }),
  powershell: () => ({ file: "powershell.exe", args: ["-NoLogo"], name: "powershell (interactive)" }),
  idle: () => ({ file: "cmd.exe", args: [], name: "cmd (idle probe target)" }),
  tui: () => ({ file: scenarioHost.file, args: [path.join(__dirname, "scenarios", "tui.js")], env: scenarioHost.env, name: "full-screen TUI" }),
  streamer: () => ({ file: scenarioHost.file, args: [path.join(__dirname, "scenarios", "streamer.js")], env: scenarioHost.env, name: "1 MB/s streamer" }),
  bash: () => ({ file: "bash", args: [], name: "bash (non-Windows dev only)" }),
};

function spawnSession(id, scenario, cols, rows) {
  const spec = (SCENARIOS[scenario] || (IS_WIN ? SCENARIOS.cmd : SCENARIOS.bash))();
  const p = pty.spawn(spec.file, spec.args, {
    name: "xterm-256color", cols: cols || 100, rows: rows || 30,
    cwd: os.homedir(), env: { ...process.env, ...(spec.env || {}) }, useConpty: true,
  });
  const s = registry.register(id, { scenario, pid: p.pid, name: spec.name });
  ptys.set(id, p);
  registry.transition(id, "RUNNING");
  logEvent("spawn", { id, scenario, pid: p.pid });
  p.onData((data) => {
    registry.feed(id, data);
    if (scenario === "streamer") seq.feed(data);
    scanForProbe(id, data);
    scanForTuiSize(id, data);
    if (registry.get(id).attached && win) win.webContents.send("pty-data", id, data);
  });
  p.onExit(({ exitCode }) => {
    const st = registry.get(id).state;
    if (st === "RUNNING" || st === "SPAWNING") registry.transition(id, "EXITED");
    registry.get(id).exitCode = exitCode;
    logEvent("exit", { id, exitCode });
    if (win) win.webContents.send("pty-exit", id, exitCode);
  });
  return { id, pid: p.pid, name: spec.name };
}

/* ---------- latency + wrong-pane probe ---------- */
let probe = { active: false, marker: null, t0: 0, targetId: null, samples: [], timeouts: 0, timer: null, echoSeenMain: false };
function scanForProbe(id, data) {
  if (!probe.active || !probe.marker) return;
  if (data.includes(probe.marker)) {
    if (id === probe.targetId && !probe.echoSeenMain) {
      probe.echoSeenMain = true;
      probe.samples.push(Number(process.hrtime.bigint() - probe.t0) / 1e6);
      if (win) win.webContents.send("probe-echo", probe.marker); // renderer records paint time
    } else if (id !== probe.targetId) {
      const sc = registry.get(id).meta.scenario;
      if (sc === "idle" || sc === "cmd" || sc === "powershell") {
        state.crossPaneHits.push({ ts: new Date().toISOString(), pane: id, marker: probe.marker });
        logEvent("cross-pane-hit", { pane: id, marker: probe.marker });
      }
    }
  }
}
async function runLatencyProbe(targetId, n = 200, intervalMs = 150) {
  const p = ptys.get(targetId);
  if (!p) throw new Error(`no pty ${targetId}`);
  probe = { active: true, marker: null, t0: 0n, targetId, samples: [], timeouts: 0, echoSeenMain: false };
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  for (let i = 0; i < n; i++) {
    probe.marker = "#" + chars[i % chars.length] + chars[(i * 7 + 3) % chars.length];
    probe.echoSeenMain = false;
    probe.t0 = process.hrtime.bigint();
    p.write(probe.marker);
    const deadline = Date.now() + 2000;
    while (!probe.echoSeenMain && Date.now() < deadline) await new Promise((r) => setTimeout(r, 2));
    if (!probe.echoSeenMain) probe.timeouts++;
    p.write("\x08\x08\x08"); // clear the marker from the prompt
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  probe.active = false;
  state.latency = latencyStats(probe.samples.slice(10), probe.timeouts); // discard warmup
  logEvent("latency-probe-done", state.latency);
  return state.latency;
}

/* ---------- resize correctness (TUI reports its own size) ---------- */
let lastResizeRequest = new Map(); // id -> {cols, rows, ts}
function scanForTuiSize(id, data) {
  const m = /TUI-SIZE (\d+)x(\d+)/.exec(data);
  if (!m) return;
  const req = lastResizeRequest.get(id);
  if (!req) return;
  const ok = Number(m[1]) === req.cols && Number(m[2]) === req.rows;
  state.resizeChecks.push({ id, requested: `${req.cols}x${req.rows}`, reported: `${m[1]}x${m[2]}`, ok, ts: new Date().toISOString() });
  if (ok) lastResizeRequest.delete(id); // stale intermediate redraws before final size are expected; keep checking until match
}

/* ---------- metrics sampler ---------- */
setInterval(() => {
  try {
    const procs = app.getAppMetrics().map((m) => ({
      type: m.type, pid: m.pid,
      cpuPct: Number((m.cpu?.percentCPUUsage ?? 0).toFixed(1)),
      rssMB: Math.round((m.memory?.workingSetSize ?? 0) / 1024),
    }));
    state.metricsTimeline.push({ ts: new Date().toISOString(), paneCount: registry.alive().length, procs });
    if (state.metricsTimeline.length > 3600) state.metricsTimeline.shift();
  } catch { /* sampler must never crash the rig */ }
}, 2000);

/* ---------- report ---------- */
function summarizeMetrics() {
  const byCount = {};
  for (const s of state.metricsTimeline) {
    const key = String(s.paneCount);
    const totalRss = s.procs.reduce((a, p) => a + p.rssMB, 0);
    const totalCpu = s.procs.reduce((a, p) => a + p.cpuPct, 0);
    (byCount[key] ||= { samples: 0, peakRssMB: 0, sumRss: 0, peakCpuPct: 0, sumCpu: 0 });
    const b = byCount[key];
    b.samples++; b.peakRssMB = Math.max(b.peakRssMB, totalRss); b.sumRss += totalRss;
    b.peakCpuPct = Math.max(b.peakCpuPct, totalCpu); b.sumCpu += totalCpu;
  }
  for (const k of Object.keys(byCount)) {
    const b = byCount[k];
    b.meanRssMB = Math.round(b.sumRss / b.samples); b.meanCpuPct = Number((b.sumCpu / b.samples).toFixed(1));
    delete b.sumRss; delete b.sumCpu;
  }
  return byCount;
}
function unexpectedExits() {
  return [...registry.sessions.values()]
    .filter((s) => s.state === "EXITED")
    .filter((s) => ["tui", "streamer"].includes(s.meta.scenario) || (s.exitCode !== 0 && s.exitCode !== null))
    .map((s) => ({ id: s.id, scenario: s.meta.scenario, exitCode: s.exitCode }));
}
function killCriteria() {
  const seqR = seq.report();
  const m = summarizeMetrics();
  const peak = Math.max(0, ...Object.values(m).map((b) => b.peakRssMB));
  const failedResizes = state.resizeChecks.length > 0 && state.resizeChecks.filter((r) => !r.ok).length === state.resizeChecks.length;
  return [
    { criterion: "p95 input latency >= 50 ms sustained", value: state.latency?.p95, triggered: state.latency ? state.latency.p95 >= 50 : null },
    { criterion: "output loss (streamer SEQ gaps)", value: seqR.gaps, triggered: seqR.received > 0 ? seqR.gaps > 0 : null },
    { criterion: `RAM above budget (${state.ramBudgetMB} MB, Electron processes)`, value: peak, triggered: state.metricsTimeline.length ? peak > state.ramBudgetMB : null },
    { criterion: "input crosses to the wrong pane", value: state.crossPaneHits.length, triggered: state.latency ? state.crossPaneHits.length > 0 : null },
    { criterion: "layout changes restart/corrupt sessions", value: state.layoutStorm, triggered: state.layoutStorm ? !state.layoutStorm.allAlive || state.layoutStorm.newGaps > 0 : null },
    { criterion: "instability at 6 terminals (unexpected session deaths)", value: unexpectedExits(), triggered: state.metricsTimeline.some((s) => s.paneCount >= 6) ? unexpectedExits().length > 0 : null, note: "tui/streamer exits and any nonzero-code exit count; operator-typed 'exit' in cmd/powershell does not" },
    { criterion: "resize unreliable (TUI never matches requested dims)", value: `${state.resizeChecks.filter((r) => r.ok).length}/${state.resizeChecks.length} ok`, triggered: state.resizeChecks.length ? failedResizes : null, note: "transitional pre-resize redraws are expected non-ok entries; criterion = no request ever matched" },
    state.lifecycleCheck
      ? { criterion: "process lifecycle not supervisable", value: state.lifecycleCheck, triggered: !state.lifecycleCheck.ok, note: "automated: every session has spawn + terminal event after teardown" }
      : { criterion: "process lifecycle not supervisable", value: `${state.events.filter((e) => e.kind === "exit").length} exits observed`, triggered: null, note: "operator judgment: every spawn/exit/kill appears in the event log" },
    state.orphanScan
      ? { criterion: "ConPTY ownership not safely containable", value: state.orphanScan, triggered: !state.orphanScan.ok, note: "automated: post-teardown pty pids dead + no conhost/OpenConsole children remain (pid-liveness caveat: PID reuse fails toward triggered)" }
      : { criterion: "ConPTY ownership not safely containable", value: null, triggered: null, note: "operator judgment: kill-all leaves no orphan conhost/OpenConsole (check Task Manager after quit)" },
  ];
}
function writeReport() {
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const resultsDir = path.join(__dirname, "results");
  fs.mkdirSync(resultsDir, { recursive: true });
  const crit = killCriteria();
  const anyTriggered = crit.some((c) => c.triggered === true);
  const unmeasured = crit.filter((c) => c.triggered === null).map((c) => c.criterion);
  const report = {
    rig: "spike_compositor@0.1.0", generated: new Date().toISOString(), startedTs: state.startedTs,
    autorun: state.autorun, autorunWaitS: state.autorunWaitS,
    lifecycleCheck: state.lifecycleCheck, orphanScan: state.orphanScan,
    environment: state.environment, ramBudgetMB: state.ramBudgetMB,
    sessions: [...registry.sessions.values()].map((s) => ({ id: s.id, scenario: s.meta.scenario, pid: s.pid, state: s.state, exitCode: s.exitCode })),
    latencyMainMs: state.latency, latencyRendererMs: state.latencyRenderer,
    streamer: seq.report(), crossPaneHits: state.crossPaneHits, resizeChecks: state.resizeChecks,
    layoutStorm: state.layoutStorm, metricsByPaneCount: summarizeMetrics(),
    killCriteria: crit,
    verdict: anyTriggered ? "KILL-CRITERION TRIGGERED: rerun rig on Tauri + portable-pty before D-UI-01" :
      unmeasured.length ? `INCOMPLETE: unmeasured criteria remain (${unmeasured.length}) — finish the checklist` :
      "NO KILL CRITERIA TRIGGERED: evidence supports recommending Electron for D-UI-01 (operator ratifies)",
    events: state.events,
  };
  const jsonPath = path.join(resultsDir, `SPIKE_REPORT_${ts}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2));
  const md = [
    `# Phase 1 Spike Report — ${report.generated}`,
    `Environment: ${JSON.stringify(report.environment)}`,
    `\n## Verdict\n**${report.verdict}**`,
    `\n## Kill criteria`,
    "| Criterion | Value | Triggered |", "|---|---|---|",
    ...crit.map((c) => `| ${c.criterion} | ${JSON.stringify(c.value)} | ${c.triggered === null ? "UNMEASURED" + (c.note ? " — " + c.note : "") : c.triggered} |`),
    `\n## Latency (main-process echo path)\n\`${JSON.stringify(report.latencyMainMs)}\``,
    `\n## Latency (renderer paint)\n\`${JSON.stringify(report.latencyRendererMs)}\``,
    `\n## Streamer integrity\n\`${JSON.stringify(report.streamer)}\``,
    `\n## Resource envelope by pane count\n\`${JSON.stringify(report.metricsByPaneCount)}\``,
    `\n## Layout storm\n\`${JSON.stringify(report.layoutStorm)}\``,
    `\n## Resize checks\n${report.resizeChecks.map((r) => `- ${r.id}: req ${r.requested} rep ${r.reported} ok=${r.ok}`).join("\n") || "(none run)"}`,
    `\n*Gate reminder: Phase 1 exit = OPERATOR ratifies D-UI-01. This report is evidence, not a decision.*`,
  ].join("\n");
  const mdPath = path.join(resultsDir, `SPIKE_REPORT_${ts}.md`);
  fs.writeFileSync(mdPath, md);
  logEvent("report-written", { jsonPath, mdPath });
  return { jsonPath, mdPath, verdict: report.verdict };
}

/* ---------- IPC ---------- */
ipcMain.handle("spawn", (_e, id, scenario, cols, rows) => spawnSession(id, scenario, cols, rows));
ipcMain.handle("input", (_e, id, data) => { ptys.get(id)?.write(data); });
ipcMain.handle("resize", (_e, id, cols, rows) => {
  lastResizeRequest.set(id, { cols, rows, ts: Date.now() });
  ptys.get(id)?.resize(cols, rows);
});
ipcMain.handle("detach", (_e, id) => registry.detach(id));
ipcMain.handle("reattach", (_e, id) => registry.reattach(id).toString("utf8"));
ipcMain.handle("terminate", (_e, id) => {
  const p = ptys.get(id);
  if (p) { registry.transition(id, "KILLED"); logEvent("kill", { id, pid: p.pid }); p.kill(); ptys.delete(id); }
});
ipcMain.handle("sessions", () => [...registry.sessions.values()].map((s) => ({ id: s.id, state: s.state, pid: s.pid, scenario: s.meta.scenario, name: s.meta.name, attached: s.attached })));
ipcMain.handle("latency-probe", (_e, id, n) => runLatencyProbe(id, n));
ipcMain.handle("renderer-latency", (_e, stats) => { state.latencyRenderer = stats; });
ipcMain.handle("layout-storm-result", (_e, result) => {
  const aliveIds = registry.alive().map((s) => s.id);
  const gapsBefore = result.gapsBefore ?? 0;
  state.layoutStorm = { ...result, allAlive: result.expectedAlive.every((id) => aliveIds.includes(id)), newGaps: seq.report().gaps - gapsBefore };
  logEvent("layout-storm", state.layoutStorm);
  return state.layoutStorm;
});
ipcMain.handle("seq-report", () => seq.report());
ipcMain.handle("set-ram-budget", (_e, mb) => { state.ramBudgetMB = Number(mb) || state.ramBudgetMB; });
ipcMain.handle("generate-report", () => writeReport());

/* ---------- autorun support ---------- */
ipcMain.handle("autorun-flag", () => ({ autorun: AUTORUN, waitS: AUTORUN_WAIT_S }));
ipcMain.handle("autorun-teardown-check", async () => {
  const knownPids = [...registry.sessions.values()].map((s) => s.pid).filter(Boolean);
  killAll();
  await new Promise((r) => setTimeout(r, 3000)); // let ConPTY hosts unwind
  state.lifecycleCheck = lifecycleCheck(state.events, [...registry.sessions.values()]);
  const alivePtyPids = knownPids.filter((pid) => { try { process.kill(pid, 0); return true; } catch { return false; } });
  let consoleHosts = [];
  let scanError = null;
  if (IS_WIN) {
    try {
      const raw = await new Promise((resolve, reject) => execFile(
        "powershell.exe",
        ["-NoProfile", "-NonInteractive", "-Command",
          "Get-CimInstance Win32_Process -Filter \"Name='conhost.exe' OR Name='OpenConsole.exe'\" | Select-Object Name,ProcessId,ParentProcessId | ConvertTo-Json -Compress"],
        { timeout: 15000 }, (err, stdout) => (err ? reject(err) : resolve(stdout))));
      consoleHosts = findOrphans(parseCimJson(raw), process.pid, knownPids);
    } catch (e) { scanError = String(e.message || e); }
  }
  // fail closed: a scan error means containment is NOT demonstrated
  state.orphanScan = { ok: alivePtyPids.length === 0 && consoleHosts.length === 0 && !scanError, alivePtyPids, orphanConsoleHosts: consoleHosts, scanError };
  logEvent("autorun-teardown-check", state.orphanScan);
  return { lifecycleCheck: state.lifecycleCheck, orphanScan: state.orphanScan };
});
ipcMain.handle("autorun-error", (_e, message) => {
  logEvent("autorun-error", { message });
  const r = writeReport();
  console.error("[autorun] FAILED:", message, "report:", r.jsonPath);
  killAll(); // app.exit() skips before-quit; never leave PTYs behind
  setTimeout(() => app.exit(1), 500);
});
ipcMain.handle("autorun-quit", () => { setTimeout(() => app.quit(), 300); });

/* ---------- app lifecycle (no orphans) ---------- */
function killAll() {
  for (const id of registry.teardownOrder()) {
    try { registry.transition(id, "KILLED"); ptys.get(id)?.kill(); logEvent("kill-on-quit", { id }); } catch { /* already dead */ }
  }
  ptys.clear();
}
app.whenReady().then(() => {
  win = new BrowserWindow({
    width: 1600, height: 950, title: "Phase 1 Spike — Terminal Compositor (THROWAWAY RIG)",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
});
app.on("before-quit", killAll);
app.on("window-all-closed", () => { killAll(); app.quit(); });
