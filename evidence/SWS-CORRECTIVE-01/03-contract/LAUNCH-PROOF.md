# Workstream 3 — the launch path, executed

**Candidate:** `3a7dfc9` (source tree; the launcher is unchanged in `45751ac`)
**Environment:** development host, FIXTURE

---

## 1. The shell launches and serves its own identity

`Start-Shell.ps1 -Port <ephemeral> -NoBrowser`, driven to readiness and then stopped:

```
port = 63124
2026-09-08T11:29:42 INFO     sws shell listening on http://127.0.0.1:63124
2026-09-08T11:29:42 INFO     sws modules loaded: debate, distillery, llamacpp, sovereign, sow, tokencenter
2026-09-08T11:29:42 INFO     sws module output is persisted under
                             C:/Users/Sslaw/AppData/Local/SovereignWorkspace/<module>/logs
ready = True
identity version = SWS-UI-001 v1.2
identity build_id = 2026-08-21
```

- **Readiness is service identity, not a listener.** The launcher waited for
  `/api/shell-info` to return a payload whose `version` starts with `SWS-UI-001`. An ephemeral
  port was used, so no default was assumed and nothing on the host was disturbed.
- **Six adapters compiled and loaded**, including SOW with its relocated receipt lane.
- **No module was started.** Launching the shell starts none, which is the documented behaviour.
- **Module output is persisted outside the install root**, as the state contract requires.

## 2. The preflight's blocking/advisory separation, live

The same run's transcript, on a host that deliberately was *not* quiet:

```
  tree                  source checkout
  version               1.0.0-rc.1
  candidate commit      3a7dfc9
  tree state            2 uncommitted change(s)
  python 3.12           Python 3.12.10
  python 3.14           present
  port 63124            free
  module ports          all free
  vram gpu 0            7375 MiB of 8151 MiB (90%)
  gpu holder            29908, ...\ollama\llama-server.exe
  windows theme         dark

  3 thing(s) to know (not blocking):
    - worktree has 2 uncommitted change(s)
    - 2 process(es) from a previous run are still alive
    - a model runtime or module process is already holding the GPU
```

Three advisories, **zero blocking**, and the launch proceeded — which is the correct behaviour and
the thing the old two-preflight arrangement could not express. Note also:

- the tree is correctly identified as a **source checkout** (an installed artifact reports as one);
- `python 3.14 present` — the prerequisite the README used to omit entirely;
- **per-GPU** VRAM reporting (`vram gpu 0`), not a single row split on commas;
- a real GPU holder was detected and reported as an advisory, not as a clean state;
- **dark theme is reported, and light mode is nowhere claimed to block startup.**

## 3. `-CheckOnly` through every entry point

| Invocation | Exit | Observed |
|---|---|---|
| `Start-Shell.ps1 -CheckOnly` | 0 | "nothing started"; no module process appeared |
| `Start-Shell.ps1 -CheckOnly -Port <occupied>` | **1** | "BLOCKED"; the occupying pid named |
| `Start-Sovereign.ps1 -CheckOnly` | 0 | delegated; identical preflight |
| `Start-Sovereign.ps1 -CheckOnly -Port <occupied>` | **1** | blocking exit code propagated |
| `Sovereign Workspace.bat -CheckOnly` | 0 | argument forwarded through two layers; exit code propagated |

The `.bat` run is the one that matters most, because it is the route most operators take and it
is the route that previously bypassed the outer preflight entirely and could accept no arguments
at all. Full transcript captured; the batch file forwarded `-CheckOnly` through
`Start-Sovereign.ps1` to `Start-Shell.ps1` and returned `BATCH EXIT=0`.

## 4. An honest observation about shutdown

Stopping the launcher's **wrapper process abruptly** (a forced kill, not Ctrl+C) leaves the shell's
Python process running: the launcher's `finally` block, which is what stops the shell, does not
run when the wrapper is killed outright.

Scope and severity, stated plainly:

- The **documented** shutdown is Ctrl+C, which does run the `finally` and does stop the shell,
  and modules stop with it because the shell holds them in a Job Object.
- A forced kill of the wrapper is not a supported shutdown, and this is not a regression — it is
  how the launcher has always behaved.
- The orphan is visible and recoverable: `Start-Shell.ps1 -CheckOnly` lists any process still
  running out of the tree, which is how it was found and cleaned up here.

It is recorded rather than fixed because putting the shell into a launcher-owned Job Object is a
behaviour change to the supported shutdown path, and this directive asks for shutdown behaviour to
be *consistent across entry points* — which it now is — rather than redesigned. It belongs in the
operator's backlog, not in a silent change.

## 5. Non-writable installation

Covered by acceptance step 9 against the installed artifact — see `../04-acceptance/`. The
source-tree launch above does not test that property, and is not offered as if it did.
