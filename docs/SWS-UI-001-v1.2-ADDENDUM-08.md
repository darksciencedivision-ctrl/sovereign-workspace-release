# SWS-UI-001 v1.2 — ADDENDUM 08: C-8(c) and the consolidated resume state

| Field | Value |
|---|---|
| Amends | `ADDENDUM-07` (zero-stop) and `ADDENDUM-06` (dependency graph). Both remain in force. Supersedes **C-8(b)'s launch mechanism only**. |
| ID / version | `SWS-UI-001-ADD-08 v1.0`, 2026-08-26 |
| Cause | **Four consecutive sessions have frozen on the same command shape.** Not one chose to stop; all four hung mid-command with reachable work outstanding. |

---

## 1. C-8(c) — the launch mechanism, replaced

`C-8(b)` said: start long-lived processes detached, with output to OS-owned files, holding no handle. The **rule** was right. The **mechanism** leaked a handle anyway.

**`Start-Process` with `-RedirectStandardOutput` / `-RedirectStandardError` / `-PassThru` still hands the calling shell a child handle, and OpenCode's tool wrapper blocks on it.** Confirmed four times:

| Session | Command shape | Dead air |
|---|---|---|
| fs-watch #1 | `Start-Process … -RedirectStandardOutput` | 6h 41m |
| fs-watch #2 | same | 59m |
| Electron launch | same | 30m |
| Distillery + Token Center | same, `-PassThru` added | 5h+ |

### The rule

> **Never use `Start-Process` with `-RedirectStandardOutput`, `-RedirectStandardError`, or `-PassThru`.** Launch every long-lived process through:
>
> ```
> cmd /c start "" /B "<exe>" <args> > "<outfile>" 2> "<errfile>"
> ```
>
> wrapped in `powershell.exe -NoProfile -Command`. It returns immediately and hands the calling shell **no child handle at all**.

**Liveness is verified by observation, never by waiting:** read the outfile, or `Get-NetTCPConnection -LocalPort <n> -State Listen`, or a bounded `Invoke-WebRequest -UseBasicParsing -TimeoutSec 5`. Never a process object, never a job, never a wait.

**Quote every path containing a space, twice** — once for `cmd`, once for the target. `Start-Process -ArgumentList @("D:\Product Software\...")` split on the space and produced `can't open file 'D:\\Product'`; that failure is already on the record.

## 2. Consolidated state — verified on disk 2026-08-26T20:52Z

| Fact | Value |
|---|---|
| Ledger sha256 | `7e0a55b9d67b54ee76e9f539126842ef8bb9e9bfcf82817a270064c6f9b2e2e4` |
| Gate keys | `0,1,2,3,4,5,6,4b,4c,5b,7a,7b,8a,8b,8c,8d` — `8a`–`8d`, `7a`, `7b` are `CANDIDATE` |
| Sweep (already written, adopt it) | TRUE 29 · NOT_RUN 3 · **REACHABLE 59** · PENDING_DEP 33 |
| Resolved in the 15:32–15:44 window | G26, G28, G29, G30, G31, G33, G34, G35, G36 |
| Oracle file | `goalcheck-61.txt` reads 28/124 and is **stale** — it predates the nine above |
| Provider spend, all sessions | **ZERO** |

### Product work already landed — do not redo it

- `modules/sow/control_plane/canonical_registry.py` — 53 models, 18 required fields, seeded from `CONDUCTOR_MODEL_REGISTRY` + `roster.py` + live Ollama tags, every row carrying `discovered_by`
- `modules/distillery/` — copied from the enterprise snapshot, `serve.py` health/console on **5184**, `INSTALL-PROVENANCE.json`, `INSTALL-MANIFEST.txt`
- `modules/tokencenter/` — copied from Token Piggy Bank (`data/` excluded), bind pinned to loopback, Origin/Host/CSRF guard on `POST /api/refresh`
- `shell/modules/distillery.json`, `shell/modules/tokencenter.json`
- `shell/static/app.js` + `app.css` — Token Center added and centred, Distillery's `noRuntime` gate removed
- `shell/tests/test_registry_fields_projected.py`, `test_incompatible_selection_refused.py` — both passing
- `operational-state.js` — `created_utc` and `backend` projected
- **G50 complete** — Token Center pid 30608 stopped on a pid + command-line match, 8765 free

### Two findings already banked

1. **The host's `opencode` binary is Bun 1.3.14, not a coding harness.** `--version` prints Bun, `version` errors, `--help` prints Bun's command list. G34/G35 are honestly `NOT_RUN`.
2. **No live workers exist**, so G28's live dump is `NOT_RUN` — but the projection it needed was implemented and tested.

## 3. Host state to re-verify, not assume

Distillery answered on 5184 before the freeze. Token Center on 8765 had not come up. **Both need a liveness check under C-8(c) at resume**, and relaunching under the new mechanism is the first real action of the session.

## 4. What has not changed

`ADD-07` still governs: **no halt condition**, every stop replaced by record-and-continue or quarantine-and-continue, all signatures pre-approved, the only terminal state is all 124 goals resolved, and the turn does not end while any goal is reachable.

`ADD-06` still governs: the ladder is a dependency graph, the loop always acts on the **next reachable goal**, and a skip propagates only to true dependents.

**The directive is not the constraint any more. Session survival is.** Nine goals in twelve minutes is the fastest rate any session has managed; the work stops because the turn freezes, not because the loop decides anything.
