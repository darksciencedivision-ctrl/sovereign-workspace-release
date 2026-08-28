# Phase 1 Spike Plan — Terminal Compositor (written before code, per Directive §2.6)

**Scope (Plan §16, verbatim intent):** throwaway rig, Electron + xterm.js + node-pty.
Prohibited inside the spike: product UI, control-plane code, adapters. This directory is
disposable by design; nothing in it may be imported by product code later.

## What must be demonstrated

≥6 concurrent interactive ConPTY sessions — mix: `cmd`, `powershell`, one **full-screen
TUI**, one **~1 MB/s sequence-numbered streamer**, two idle CLIs; pane resize with correct
reflow; session survival across layout changes and detach/reattach; maximize / minimize /
pin / terminate; supervised process lifecycle (exit detection, respawn, no orphans);
metrics at 6 **and** 8 panes.

## Architecture (smallest thing that can prove/kill Electron)

- **Main process** owns every PTY (node-pty, ConPTY backend). Sessions live in a
  `SessionRegistry` independent of any renderer view — detach/reattach and layout changes
  must not touch the PTY (this is the survival property under test).
- **Renderer** hosts xterm.js panes in a CSS grid (near-square algorithm, Plan §10.2
  simplified). Panes bind/unbind to sessions over IPC; scrollback replay from a per-session
  ring buffer (200 KB) on reattach.
- **Scenario children** run via `ELECTRON_RUN_AS_NODE` (no external runtime dependency):
  `scenarios/tui.js` — alt-screen, cursor-addressed, animated, resize-aware; prints
  `TUI-SIZE cols x rows` on every redraw so resize correctness is machine-checkable (U9).
  `scenarios/streamer.js` — rate-controlled `SEQ:<n>:<payload>` lines; any sequence gap =
  dropped output (kill criterion), machine-checkable.
- **Probes** (all automated, results land in the report):
  1. *Input latency*: write one char to an interactive `cmd` session, timestamp until the
     echo appears in `onData` (main-side), 200 samples; p50/p95/p99/max. Renderer-paint
     timestamp recorded separately (end-to-end vs ConPTY-path latency).
  2. *Wrong-pane input*: probe chars are timing-correlated across all session streams;
     any cross-pane hit is logged (kill criterion: input crosses panes).
  3. *Output integrity*: streamer gap count at 1 MB/s sustained ≥60 s.
  4. *Resize correctness*: requested dims vs TUI-reported dims after each resize.
  5. *Layout survival*: 20 automated layout mutations (grid flips, maximize/restore,
     detach/reattach); afterward all PTY pids alive + zero new gaps.
  6. *Resource envelope*: `app.getAppMetrics()` sampled every 2 s at 6 panes, then 8
     panes (buttons add panes 7–8). Note: ConPTY host processes (conhost/OpenConsole) are
     outside Electron's metrics; identical across candidate frameworks, so excluded from
     the framework comparison and noted in the report.

## Kill criteria (from Plan §16 / Directive §5-P1 — evaluated in the generated report)

p95 input latency ≥ 50 ms sustained · any output loss (seq gaps) · RAM above operator
budget (default 2048 MB Electron-process total, operator-tunable in the rig) · input
crossing to the wrong pane · layout changes restarting/corrupting sessions · instability
at 6 terminals · unreliable ANSI/resize · process lifecycle not supervisable · ConPTY
ownership not safely containable. **Any trigger ⇒ rerun the identical rig on Tauri +
portable-pty before any framework ratification.**

## Split of execution (environment constraint E2)

- **Sandbox (Linux, this session):** pure-logic modules + `node --test` with zero deps —
  ring buffer, seq-gap detector, latency stats, layout algorithm, registry state machine.
  ConPTY cannot be exercised here; no ConPTY claims are made from sandbox runs.
- **Operator (Windows host):** `npm install && npm start`, run the guided scenario
  (buttons in order), click **Generate report** → `results/SPIKE_REPORT_<ts>.{json,md}`.
  That report is the Phase 1 gate evidence for the D-UI-01 ratification.

## Test plan for the logic modules (sandbox-runnable)

stats: percentile math incl. small-N and timeout-censored samples · seq-check: exact gap
count/duplicate/restart detection · ring buffer: byte-exact replay, overflow trimming ·
layout: near-square grid for n=1..12, double-cell for pinned/attention panes, stability
(membership-change-only recompute) · registry: legal state transitions only
(SPAWNING→RUNNING→EXITED/KILLED), detach/reattach never mutates PTY state, no-orphan
teardown ordering.
