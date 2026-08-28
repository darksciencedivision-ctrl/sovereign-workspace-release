# Electron EPIPE and process-teardown repair evidence

Date: 2026-07-28
Verified implementation commit: `c8af621d` (`c8af621`)

## Scope and changed files

The repair changes logging and process lifecycle only. It does not change phase state,
promotion state, model selection, prompts, gates, or evidence conclusions.

- `apps/desktop/main-process-logger.js`
- `apps/desktop/main.js`
- `apps/desktop/selfcheck/process-tree.js`
- `apps/desktop/selfcheck/run.js`
- `apps/desktop/test/main-process-logger.test.js`
- `apps/desktop/test/selfcheck-process-tree.test.js`
- `terminal/conpty/session-manager.js`
- `terminal/test/session-manager.test.js`
- `adapters/frontier/process_tree.py`
- `adapters/frontier/claude_code.py`
- `tests/integration/test_frontier_process_tree.py`
- `tests/unit/test_frontier_claude_code.py`
- `tools/live/run_15d_flow_live_smoke.py`

The pre-existing untracked `apps/desktop/package-lock.json` was not staged or changed.

## EPIPE behavior

`main-process-logger.js` installs explicit `error` listeners on both `process.stdout` and
`process.stderr`. Only `error.code === "EPIPE"` is treated as terminal detachment. An EPIPE
disables all later console writes; the durable file append happens before renderer or console
delivery. Non-EPIPE stream errors are persisted and re-thrown on a microtask in production.
There is no `uncaughtException` handler.

The self-check main process now awaits PTY exit confirmation, stops its authority service only
after the PTY exits, awaits the gateway, drains pending console writes, and detaches the inherited
pipe before `app.exit`. The Node launcher no longer calls `process.exit`; it exits naturally after
its tracked Electron tree has been reaped.

Focused command:

```text
node --test apps/desktop/test/main-process-logger.test.js \
  apps/desktop/test/selfcheck-process-tree.test.js
```

Result:

```text
6 tests passed, 0 failed
```

Coverage includes emitted stdout EPIPE, emitted stderr EPIPE, continued file logging, no later
console writes, observable non-EPIPE `EIO`, observable unrelated renderer failures, descendant
tracking, awaited termination, and reporting of a descendant that resists shutdown.

## 15d.flow managed process proof

The real Claude CLI backend now creates a Windows Job Object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, samples every PID assigned to it, terminates the job in
`finally`, waits for the job to become empty, and fails the call if any assigned descendant
remains. The backend accumulates PID evidence across every call made by one 15d.flow unit.

Deterministic ten-run command:

```text
py -3.12 -m pytest -q tests/integration/test_frontier_process_tree.py
```

Result:

```text
1 passed in 4.86s
```

That single regression executes ten real Windows Node roots. Each root spawns a detached Node
grandchild; after each run every recorded PID is checked with `Get-Process` and is absent.

Live 15d.flow command:

```text
py -3.12 tools/live/run_15d_flow_live_smoke.py --timeout 60
```

Result:

```text
exit=0
ran=true
published=false
skipped_with_record=true
reason="RuntimeError: claude CLI exited 1: You've hit your weekly limit · resets Jul 30, 12pm (America/Chicago)"
managed_process_pids=[31380,55020,62692,66196,69344,70180,70828,78400,81092,82492,
83508,84580,85024,86312,86560,86632,86912,87548,87824,88092,88468,88748,88844,
89084,89168,89176,89616,90032,90492,90516,90544,91068,91224,91732,92132,92252,
92288,92452,92760,93132,93316,93596]
managed_process_descendants_remaining=[]
workspace_node_electron_remaining=0
```

This proves teardown on the provider-failure path that previously leaked Node descendants.

## Real voice-conductor self-check

Command:

```text
$env:SOW_MAIN_LOG_FILE=<temporary evidence path>\main-process.log
node apps/desktop/selfcheck/run.js voice-conductor
```

Observed result:

```text
exit=1
elapsed_s=254.72
epipe_or_dialog_lines=0
workspace_node_electron_remaining=0
[selfcheck/run] tracked pids=912,2224,12728,12832,19888,24200,27664,31080,39424,
42664,45716,46508,56908,63064,65736,695
```

The exit was not an EPIPE or lifecycle failure. The receipt names the external blocker:

```text
the live conductor never replied ... You've hit your weekly limit · resets Jul 30, 12pm
(America/Chicago)
```

The same run recorded `session_killed=true`, `lease_released=true`, a clean committed source
identity, no EPIPE, no JavaScript error dialog text, and zero surviving workspace Node/Electron
processes. The persistent log contains both:

```text
[shell] conductor: LIVE session running in pane 1 ...
[shell] [selfcheck] teardown complete: zero tracked Electron children
```

Nine further live provider calls were not run after the provider disclosed the same weekly-limit
blocker. Therefore the ten-successful-live-self-check acceptance item cannot be truthfully claimed
until the subscription resets. The ten-run real detached-Node teardown regression above did pass.

## Full regression results

```text
py -3.12 -m pytest -q
1419 passed, 61 warnings in 329.07s

cd apps/desktop
npm test
483 passed, 0 failed

node --test terminal/test/*.test.js
201 passed, 0 failed

[System.Management.Automation.Language.Parser]::ParseFile("tools/loop/run_loop.ps1", ...)
run_loop.ps1 syntax: OK

git diff --check
exit=0
```

Final process-list proof:

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match '^(node|electron)(\.exe)?$' -and
    $_.CommandLine -like '*D:\multi model terminal app\sovereign-orchestration-workspace*'
  }
```

Output:

```text
workspace_node_electron_count=0
```
