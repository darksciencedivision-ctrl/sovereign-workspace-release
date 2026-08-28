# Phase 1 Spike — Operator Run Instructions (Windows host)

**Why you're running this:** the build session executes in a Linux sandbox and cannot
exercise ConPTY. The Phase 1 gate (framework ratification, D-UI-01) requires real
measurements from your Windows machine. This rig collects them automatically.

## AUTORUN mode (loop directive 2026-07-16 — no human interaction needed)

```bat
cd /d "D:\multi model terminal app\sovereign-orchestration-workspace\tools\spike_compositor"
set SPIKE_AUTORUN=1
npm start
```

Runs the full guided sequence programmatically through the same code paths as the
buttons: standard-6 → 60 s streamer window → latency probe (200) → resize storm →
layout storm ×20 → panes 7–8 → 60 s resource window → **teardown + automated
containment check** (all PTY pids dead; no conhost/OpenConsole children remain) →
report → quit. Exit code 1 + an `autorun-error` event in the report means the sequence
itself failed. `SPIKE_AUTORUN_WAIT_S=<n>` shortens the two 60 s windows for smoke runs
only — evidence runs must use the default. In autorun mode the two formerly
operator-judgment kill criteria (lifecycle supervisable, ConPTY containment) are
machine-measured and can trigger.

## Prerequisites

- Windows 10 1809+ / Windows 11 (ConPTY), Node.js 20+ and npm on PATH.
- ~500 MB disk for `node_modules` (Electron). No credentials, no sign-ups, nothing leaves
  the machine — `npm install` fetches packages from the public npm registry, and that is
  the only network use.

## Run

```bat
cd /d "D:\multi model terminal app\sovereign-orchestration-workspace\tools\spike_compositor"
npm install
npm test        REM 21 logic tests should pass on your machine too
npm start
```

## Guided checklist (buttons in order, top bar)

1. **Launch standard 6** — cmd, PowerShell, full-screen TUI, 1 MB/s streamer, two idle cmd.
   Interact freely with cmd/PowerShell panes: typing must land in the focused pane only.
   Let the streamer run **≥60 s** (integrity counter appears in the HUD).
2. **Latency probe (200)** — ~45 s; writes 200 markers into the idle target pane and
   measures echo latency (main path) + paint latency (renderer). HUD shows p95s.
3. **Resize storm** — random-resizes the TUI pane ×10; the TUI reports its own size each
   redraw and the rig checks requested vs reported dims (U9 evidence).
4. **Layout storm ×20** — automated maximize/restore/detach/reattach cycle; then verifies
   every session is still alive and the streamer had **zero new gaps** (session-survival
   kill criterion).
5. **Add panes 7–8** — run **≥60 s** for the 8-pane RAM/CPU envelope (U12 evidence).
6. **Generate report** — set your RAM budget first (default 2048 MB). Writes
   `results/SPIKE_REPORT_<timestamp>.json/.md` including the kill-criteria table and a
   verdict line.

Then **quit the app** and check Task Manager for orphan `conhost.exe`/`OpenConsole.exe`
(there should be none — supervised-lifecycle criterion; note the result).

## What the results mean

- **Any kill criterion TRIGGERED** → per Plan §16 the same rig must be rerun on
  Tauri + portable-pty before any framework decision. Report it; do not ratify.
- **No kill criteria triggered** → evidence supports Electron for D-UI-01.
  **Ratification is your call, not the rig's** — the report says so explicitly.
- Either way: drop the two report files back to me (or just say "spike done") and the
  results get recorded as Phase 1 gate evidence with the D-UI-01 entry updated.

## Known limitations (recorded honestly)

- ConPTY host processes (conhost/OpenConsole) sit outside Electron's metrics API; the RAM
  figure covers Electron processes. The overhead is identical for any framework candidate,
  so the comparison stands; absolute totals are slightly understated.
- Renderer "paint latency" is measured at data-arrival in the renderer, not at pixel
  flip; treat it as an upper-level indicator, p95 main-path latency is the gate metric.
- This rig is **throwaway** (Plan §16): nothing in it is product code, and nothing from
  `tools/spike_compositor/` may be imported by later phases.
