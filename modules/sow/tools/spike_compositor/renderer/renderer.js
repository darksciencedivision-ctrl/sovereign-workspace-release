"use strict";
/* Renderer: xterm panes on a CSS grid. Views are disposable; sessions live in main.
   Detach/reattach destroys and rebuilds the xterm instance — the PTY must not notice. */
const grid = document.getElementById("grid");
const hud = document.getElementById("hud");
const panes = new Map(); // id -> {term, fit, el, pinned, maximized, scenario}
let paneSeq = 0;

/* ---------- pane management ---------- */
function makePane(id, scenario, title) {
  const el = document.createElement("div");
  el.className = "pane";
  el.id = `pane-${id}`;
  el.innerHTML = `
    <div class="bar">
      <span>${id}</span> <span>${title}</span> <span class="state">RUNNING</span>
      <span style="margin-left:auto"></span>
      <button data-a="pin">pin</button>
      <button data-a="min">min</button>
      <button data-a="max">max</button>
      <button data-a="detach">detach</button>
      <button data-a="reattach">reattach</button>
      <button data-a="terminate">kill</button>
    </div>
    <div class="term"></div>`;
  grid.appendChild(el);
  const term = new Terminal({ scrollback: 10000, fontSize: 12, theme: { background: "#000000" } });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(el.querySelector(".term"));
  term.onData((d) => window.spike.invoke("input", id, d));
  const p = { id, term, fit, el, pinned: false, maximized: false, scenario, attached: true };
  panes.set(id, p);
  el.querySelector(".bar").addEventListener("click", async (ev) => {
    const a = ev.target.dataset?.a;
    if (!a) return;
    if (a === "pin") { p.pinned = !p.pinned; el.classList.toggle("pinned", p.pinned); relayout(); }
    if (a === "max") { p.maximized = !p.maximized; el.classList.toggle("maximized", p.maximized); fitPane(p); }
    if (a === "min") { p.minimized = !p.minimized; el.querySelector(".term").style.display = p.minimized ? "none" : ""; el.style.minHeight = p.minimized ? "0" : ""; if (!p.minimized) fitPane(p); }
    if (a === "detach") { await window.spike.invoke("detach", id); p.attached = false; p.term.dispose(); }
    if (a === "reattach") {
      if (p.attached) return;
      const scrollback = await window.spike.invoke("reattach", id);
      const t2 = new Terminal({ scrollback: 10000, fontSize: 12, theme: { background: "#000000" } });
      const f2 = new FitAddon.FitAddon();
      t2.loadAddon(f2);
      el.querySelector(".term").innerHTML = "";
      t2.open(el.querySelector(".term"));
      t2.onData((d) => window.spike.invoke("input", id, d));
      t2.write(scrollback);
      p.term = t2; p.fit = f2; p.attached = true;
      fitPane(p);
    }
    if (a === "terminate") { await window.spike.invoke("terminate", id); setState(id, "KILLED"); }
  });
  return p;
}
function setState(id, s) {
  const el = document.querySelector(`#pane-${id} .state`);
  if (el) { el.textContent = s; el.className = `state ${s}`; }
}
function fitPane(p) {
  if (!p.attached) return;
  try {
    p.fit.fit();
    window.spike.invoke("resize", p.id, p.term.cols, p.term.rows);
  } catch { /* pane may be zero-sized mid-layout */ }
}
function relayout() {
  const n = panes.size;
  if (!n) return;
  const cols = Math.ceil(Math.sqrt(n));
  grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  requestAnimationFrame(() => panes.forEach(fitPane));
}
async function spawn(scenario, title) {
  const id = `s${++paneSeq}`;
  const info = await window.spike.invoke("spawn", id, scenario, 100, 30);
  makePane(id, scenario, title || info.name);
  relayout();
  return id;
}

/* ---------- main-process event streams ---------- */
window.spike.on("pty-data", (id, data) => {
  const p = panes.get(id);
  if (p && p.attached) {
    p.term.write(data);
    if (probeWatch.marker && data.includes(probeWatch.marker) && id === probeWatch.targetId && !probeWatch.seen) {
      probeWatch.seen = true;
      probeWatch.samples.push(performance.now() - probeWatch.t0);
    }
  }
});
window.spike.on("pty-exit", (id, code) => setState(id, `EXITED(${code})`));

/* renderer-side paint latency capture, correlated with main's probe */
const probeWatch = { marker: null, targetId: null, t0: 0, seen: true, samples: [] };
window.spike.on("probe-echo", () => { /* main saw echo; renderer timing handled in pty-data */ });

/* ---------- guided scenarios (named functions; buttons AND autorun call these) ---------- */
let latencyTargetId = null;
async function launchStandard6() {
  await spawn("cmd");
  await spawn("powershell");
  await spawn("tui");
  await spawn("streamer");
  latencyTargetId = await spawn("idle", "cmd (latency target)");
  await spawn("idle", "cmd (idle)");
}
async function runLatencyProbeScenario() {
  if (!latencyTargetId) throw new Error("launch standard 6 first");
  probeWatch.samples = [];
  hud.textContent = "latency probe running (~45 s)…";
  // renderer-side correlation: watch for markers on the target pane
  const stop = window.spike.on("probe-echo", () => {});
  probeWatch.targetId = latencyTargetId;
  const mainStats = await window.spike.invoke("latency-probe", latencyTargetId, 200);
  stop();
  // paint-latency stats (coarse: renderer sample set collected during same window)
  const paint = probeWatch.samples.slice(10).sort((a, b) => a - b);
  const pct = (arr, p) => (arr.length ? arr[Math.min(arr.length - 1, Math.ceil((p / 100) * arr.length) - 1)] : null);
  const rendererStats = { n: paint.length, p50: pct(paint, 50), p95: pct(paint, 95), p99: pct(paint, 99) };
  await window.spike.invoke("renderer-latency", rendererStats);
  hud.textContent = `latency main p95=${mainStats.p95?.toFixed(1)}ms renderer p95=${rendererStats.p95?.toFixed(1) ?? "?"}ms timeouts=${mainStats.timeouts}`;
}
document.getElementById("btn-standard").addEventListener("click", launchStandard6);
document.getElementById("btn-latency").addEventListener("click", () => runLatencyProbeScenario().catch((e) => alert(e.message)));
async function runResizeStorm() {
  hud.textContent = "resize storm…";
  for (let i = 0; i < 10; i++) {
    for (const p of panes.values()) {
      if (p.scenario === "tui") {
        const cols = 60 + Math.floor(Math.random() * 60);
        const rows = 15 + Math.floor(Math.random() * 20);
        p.term.resize(cols, rows);
        await window.spike.invoke("resize", p.id, cols, rows);
        await new Promise((r) => setTimeout(r, 1200)); // TUI reports every ~500 ms (mode-con probe); give each request 2+ report cycles
      }
    }
  }
  panes.forEach(fitPane); // restore to fitted size
  hud.textContent = "resize storm done (see report resizeChecks)";
}
document.getElementById("btn-resize").addEventListener("click", runResizeStorm);
async function runLayoutStorm() {
  hud.textContent = "layout storm…";
  const before = await window.spike.invoke("seq-report");
  const expectedAlive = [...panes.values()].filter((p) => !["EXITED", "KILLED"].some((s) => p.el.querySelector(".state").textContent.startsWith(s))).map((p) => p.id);
  for (let i = 0; i < 20; i++) {
    const list = [...panes.values()];
    const pick = list[i % list.length];
    if (i % 4 === 0) { pick.maximized = true; pick.el.classList.add("maximized"); fitPane(pick); }
    else if (i % 4 === 1) { pick.maximized = false; pick.el.classList.remove("maximized"); relayout(); }
    else if (i % 4 === 2 && pick.attached && pick.scenario !== "streamer") { await window.spike.invoke("detach", pick.id); pick.attached = false; pick.term.dispose(); }
    else if (!pick.attached) {
      const sb = await window.spike.invoke("reattach", pick.id);
      const t2 = new Terminal({ scrollback: 10000, fontSize: 12 });
      const f2 = new FitAddon.FitAddon();
      t2.loadAddon(f2);
      pick.el.querySelector(".term").innerHTML = "";
      t2.open(pick.el.querySelector(".term"));
      t2.onData((d) => window.spike.invoke("input", pick.id, d));
      t2.write(sb);
      pick.term = t2; pick.fit = f2; pick.attached = true; fitPane(pick);
    } else { relayout(); }
    await new Promise((r) => setTimeout(r, 300));
  }
  // reattach anything left detached
  for (const p of panes.values()) if (!p.attached) p.el.querySelector('[data-a="reattach"]').click();
  const result = await window.spike.invoke("layout-storm-result", { mutations: 20, expectedAlive, gapsBefore: before.gaps });
  hud.textContent = `layout storm: allAlive=${result.allAlive} newGaps=${result.newGaps}`;
}
document.getElementById("btn-layout").addEventListener("click", runLayoutStorm);
async function addPanes78() {
  await spawn("cmd", "cmd (pane 7)");
  await spawn("powershell", "powershell (pane 8)");
}
document.getElementById("btn-eight").addEventListener("click", addPanes78);
async function generateReport() {
  await window.spike.invoke("set-ram-budget", document.getElementById("ram-budget").value);
  const r = await window.spike.invoke("generate-report");
  hud.textContent = `report written → ${r.mdPath.split(/[\\/]/).pop()} · ${r.verdict}`;
  return r;
}
document.getElementById("btn-report").addEventListener("click", generateReport);
window.addEventListener("resize", () => panes.forEach(fitPane));

/* ---------- AUTORUN (loop directive phase-1-autorun): same code paths as the buttons,
   driven programmatically: standard-6 → wait → latency → resize storm → layout storm →
   panes 7–8 → wait → teardown+containment check → report → quit. ---------- */
(async () => {
  const flag = await window.spike.invoke("autorun-flag");
  if (!flag.autorun) return;
  const waitMs = flag.waitS * 1000;
  const wait = (ms, label) => { hud.textContent = `AUTORUN: ${label} (${ms / 1000}s)…`; return new Promise((r) => setTimeout(r, ms)); };
  try {
    hud.textContent = "AUTORUN: standard 6…";
    await launchStandard6();
    await wait(waitMs, "streamer integrity window @6 panes");
    await runLatencyProbeScenario();
    await runResizeStorm();
    await runLayoutStorm();
    await addPanes78();
    await wait(waitMs, "resource window @8 panes");
    hud.textContent = "AUTORUN: teardown + containment check…";
    await window.spike.invoke("autorun-teardown-check");
    const r = await window.spike.invoke("generate-report");
    hud.textContent = `AUTORUN done: ${r.verdict}`;
    await new Promise((res) => setTimeout(res, 800));
    await window.spike.invoke("autorun-quit");
  } catch (e) {
    await window.spike.invoke("autorun-error", String((e && e.stack) || e));
  }
})();
setInterval(async () => {
  const seq = await window.spike.invoke("seq-report");
  if (seq.received) hud.dataset.seq = `SEQ ok=${seq.received} gaps=${seq.gaps}`;
}, 5000);
