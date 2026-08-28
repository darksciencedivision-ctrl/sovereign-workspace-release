# Sovereign Desktop Shell — operator run (Windows host)

Product Electron shell for Phase 14A (`.shell` sub-step). Unlike the Phase-1 spike
(`tools/spike_compositor`, throwaway), this is real product code: supervised ConPTY
sessions through `terminal/`, authoritative pane state, and control-plane access ONLY over
the authenticated loopback IPC (D-IPC-01).

## Why an operator run

The **window itself cannot be verified in the headless build session** — it is an
operator-run metric, exactly like the Phase-1 spike (loop directive §6 substitution). The
governance-bearing logic beneath it is covered headlessly:

- `terminal/test/*.test.js` — ring buffer, session registry/lifecycle, session-manager
  supervision/admission (no naked sessions), pane/window state + focus routing (32 tests);
- `apps/desktop/test/*.test.js` — the envelope/integrity contract and the Node `IpcClient`
  driven against the **real Python gateway** as a separate process, including every
  fail-closed negative (11 tests).

Run them anywhere with Node ≥ 21:

```
node --test terminal/test/*.test.js apps/desktop/test/*.test.js
```

## One-command window run (Windows host)

```
cd apps/desktop
npm install       # electron + @xterm/xterm + @xterm/addon-fit + node-pty (npm registry, allowed)
npm start
```

`npm start` brings up the whole governed chain from a single command: if `IPC_PORT` /
`IPC_TOKEN` / `IPC_KEY` are not already in the environment, the shell spawns the real Python
gateway (`py -3.12 -m control_plane.ipc.run_gateway`) and reads its printed handshake, then
connects the `IpcClient` and starts the supervision heartbeat.

### The live CONDUCTOR session in pane 1 (Phase 17A `.pty`)

On launch the shell asks the governed Python path for a **launch ticket** and, if every live gate
passes (`config/live_operation.json` → provider-live → OP-9 terms → `claude` present → an I-X3
terminal free), runs the **real interactive `claude` session in pane 1's ConPTY** — supervised,
bound to this repo as its workspace, with credential-bearing env vars removed. It consumes exactly
one of the two governed terminals on that subscription, shown in the status bar as `1/2`, and hands
it back when the session ends or the shell quits.

* The **▶ live** button on pane 1's chrome starts (or restarts) that session explicitly; its tooltip
  carries the reason for the last refusal.
* To start the shell WITHOUT the automatic live session (diagnostics, or to keep both terminals
  free): `set SOW_CONDUCTOR_AUTOLAUNCH=0` before `npm start`. Deleting `config/live_operation.json`
  revokes live operation entirely — the gate chain re-reads it on every launch.

Machine check (D-P16-0): `node selfcheck/run.js conductor-pty` — starts and kills a real session and
writes `docs/evidence/receipts/PHASE17A_PTY_SELFCHECK.json`. It sends no prompt; the typed
round trip is `.roundtrip`.

### Which model that session runs (Phase 17A `.roundtrip`)

The conductor SELECTION is a label (`fable-5`); the CLI wants a slug, and it is not always the same
string — on this host `--model fable-5` is rejected outright while `claude-fable-5` is accepted. So
before the first launch the shell asks the governed probe what the CLI actually takes:

* **first launch on an unprobed host spends up to two one-word live calls** (one per candidate slug),
  behind the same live gates and holding one I-X3 terminal while it runs; the verdict is then cached
  in gitignored host state, so every later launch is offline;
* if the CLI accepts **none** of the candidates, the session launches on the **CLI default** and both
  the badge and the receipt say so (`is_fallback`) — it is never a silent substitution;
* if the probe cannot decide (rate limit, timeout, refusal), the selection is carried **verbatim**,
  exactly as before the probe existed, and the next launch asks again.

Operator levers:

* `set SOW_CONDUCTOR_MODEL_PROBE=0` — skip the live probe call. An already-recorded verdict is still
  honored (it is knowledge, not a call).
* `py -3.12 tools/live/probe_conductor_model.py --emit-model-probe --reprobe` — re-ask after a CLI
  upgrade; `--ledger-only` prints the recorded verdict without spending anything.

Machine check: `node selfcheck/run.js conductor-roundtrip` — types one prompt into the live session
and reads the answer back, writing `docs/evidence/receipts/PHASE17A_ROUNDTRIP_SELFCHECK.json`. It
spends one minimal live exchange and tears the session down.

### What to confirm visually

1. The **supervision** status card reads `READY` (green) — the shell holds a verified,
   authenticated control-plane channel. If it reads `DENIED`, no session will spawn
   (fail-closed).
2. Click **+ Terminal node** → a supervised PowerShell/ConPTY pane appears and echoes input.
   Type in it; input goes only to that pane.
3. Pane controls: **pin**, **_** (minimize → moves to the minimized tray, session survives),
   **▢** (maximize/restore), **✕** (close → session KILLED, no orphan). Click a pane to focus;
   the focused pane is outlined and shown on the `focused` card.
4. Open a full-screen console TUI in a pane (re-verifies U9 with a real TUI).
5. Quit and confirm **no orphan `conhost.exe` / `OpenConsole.exe`** remain (Task Manager) —
   `killAll()` on quit tears every PTY down.

## Automated in-runtime self-check (Phase 16A / D-P16-0)

Headless Node tests alone once shipped a runtime that failed at first launch. Every shell/UI
change is now also exercised **inside the packaged Electron runtime** by an autorun self-check
that spawns a supervised pane, asserts the banner streams into the xterm buffer, types a probe,
asserts the echo renders, and writes a machine-readable receipt:

```
cd apps/desktop
npm install
node selfcheck/run.js        # launches the shell in SHELL_SELFCHECK mode, exits 0 on PASS
```

Receipt: `docs/evidence/receipts/PHASE16A_SELFCHECK.json` (`ok:true`, `banner_seen`,
`echo_xterm_seen`/`echo_bridge_seen`, `active_element:"xterm-helper-textarea"`). The run boots
the real Python gateway, spawns a real ConPTY session, and tears everything down on exit
(no orphan processes). Its recovery state is isolated to `.recovery/selfcheck/` so it never
pollutes a real session. `echo_dom_seen` may be false under an automated/background window —
synthetic OS keystrokes are xterm/Electron internals, not shell code; `echo_xterm_seen` proves
the real `term.onData → input IPC → PTY → echo → render` wiring.

### Fail-closed check (supervision loss)

Kill the gateway process while the shell is running: within one heartbeat the supervision
card flips to `DENIED` and every session is torn down — a shell that has lost its governor
runs nothing. (Deeper OS containment — pid → Node Runtime Job Object — is a recorded
Phase-14A follow-up; see `apps/desktop/supervisor.js` and the evidence report.)
