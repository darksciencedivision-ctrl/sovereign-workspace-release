# Sovereign Workspace: operator guide

For the person who installs, starts and uses the workspace on their own Windows machine. The
reference machine is an RTX 5060 Ti 8 GB with 64 GB RAM, Windows 11 and PowerShell 5.1. Paths
are relative to the install root (the folder holding `Start-Shell.ps1`).

How the commands were checked (2026-09-24 to 2026-09-28):

- Run as written: `Provision-Workspace.ps1 -ReportOnly`, `Start-Shell.ps1 -CheckOnly`, the
  supervisor stop, `state_admin prune`, and the qualification `run`/`report`.
- Run by the clean-room gate: `Start-Shell.ps1 -Port ... -NoBrowser`, and the state backup and
  restore.
- Not re-run here, because they install or change your machine: the full
  `Provision-Workspace.ps1` and its `-LlamaCppExe` form. Those were checked against the
  script's own help.

## 1. Provision (once per machine, re-runnable)

```powershell
.\Provision-Workspace.ps1 -ReportOnly     # what is there and what is missing; changes nothing
.\Provision-Workspace.ps1                 # create the venvs, build the UI, record llama.cpp
.\Provision-Workspace.ps1 -LlamaCppExe "C:\tools\llama.cpp\llama-server.exe"
```

- It creates the Python virtual environments (hash-locked), builds the operator UI, finds the
  llama.cpp server and records it in `workspace.env`. It also reports whether Ollama is up.
- A missing prerequisite is reported and skipped, never fatal. Read the **Readiness** table at
  the end.
- Model weights are yours to supply: `ollama pull <tag>` for Ollama, or GGUF files for
  llama.cpp.

## 2. Start and stop

```powershell
.\Start-Shell.ps1 -CheckOnly              # preflight only: exit 0 = clear to launch, 1 = blocked
.\Start-Shell.ps1                         # start the shell on http://127.0.0.1:5180 and open it
.\Start-Shell.ps1 -Port 5181 -NoBrowser
```

- Stop with **Ctrl+C** in the shell window. Everything the shell launched stops with it (a
  Windows Job Object).
- The **llama.cpp supervisor** (port 18080) is a persistent service: it keeps running after the
  shell stops, on purpose, so models stay loaded. To stop it too, start the shell with
  `-StopInferenceOnExit` (it only stops a supervisor this launch started), or run:

  ```powershell
  cd modules\sovereign
  .\.venv\Scripts\python.exe -m sovereign_product.supervisor_service --root . stop
  ```

  This kills the llama.cpp router and its per-model servers, then releases the GPU.
- **Gaming or other GPU work:** stop the supervisor first. The llama.cpp models hold 6-7 GB of
  the 8 GB while loaded.

Every listener binds to 127.0.0.1 only. Ports are listed in `PORTS.md`.

## 3. Backends

Either backend works. The choice is `SOVEREIGN_INFERENCE_BACKEND` (`llama.cpp` or `ollama`),
else `runtime\backend_selection.json`, else llama.cpp.

- **llama.cpp** (port 18080). Required for the LONG route: it gives exact token counts and splits
  big models across the GPU and system RAM. The supervisor plans each LONG model's split from the
  VRAM that is free when it starts.
- **Ollama** (port 11434). Start it yourself. It serves QUICK/DEEP/RESEARCH/CONTINUITY but not
  LONG.

## 4. Routes

Pick a route in the composer's **Route** menu, or leave **AUTO**: the router then chooses by
fixed rules, never by a model. LONG is only ever chosen explicitly.

| Route | What it is for | Measured here |
|---|---|---|
| **STATUS** | The machine's own state: health, models, what is running. Reads the system; no model call. | 1.3 s |
| **QUICK** | Short answers and everyday questions, one model call. | Ollama, qwen3:14b: about 10 s warm, 18-43 s cold; a prompt of about 8k tokens took 22 s. llama.cpp with the GPU plan (2026-09-29): warm 10.1 s and 10.2 s, cold 40.8 s and 71.7 s, generation 6.0-6.6 tok/s. |
| **CONTINUITY** | Picks up earlier work in the same chat ("continue", "what did I ask"). | llama.cpp (2026-09-29, two starts): 20.6 s, generation 6.0-6.2 tok/s. |
| **DEEP** | Multi-step analysis, comparisons and designs, by a slate of models. | Ollama: 360 s. llama.cpp (2026-09-30, after the num_predict fix): completed in 920 s, 8 model calls, generation 5.78 tok/s. |
| **RESEARCH** | Evidence-backed answers with citations, in checkpointed iterations. | llama.cpp (2026-09-30): completed in 110.4 min, 8 iterations, 33 model calls, mean 199 s per call, generation 4.78 tok/s. |
| **LONG** | Big models on big inputs or long plans: hours, in fresh-context chunks. Explicit only. | MoE plan steps 420-512 s; 145 KB prose map/reduce 708 s; 32k map/reduce 872 s (earlier) and 1724 s on 2026-09-30 after a split (`@exact: off`, 21.3 tok/s). Exact counting on 2026-09-30: 32k 383 s and 745 s (answer 63), 65k 498 s and 611 s (answer 124), generation about 24 tok/s. Earlier map/reduce on those inputs was 872 s and 2439 s and the counts were low. |

On llama.cpp the supervisor plans a GPU/RAM split for these models when the GPU is free.
Measured 2026-09-29/30: `qwen3:14b` ran with 14 or 15 of 40 layers on the GPU and generated at
6.0-6.6 tok/s on QUICK (the old default, 8 of 40 layers, was about 3.6-4.5 tok/s). A refused
plan leaves the model on that slower default; the status bar says so.

**RESEARCH without thinking (option, off by default).** RESEARCH spends most of its time in the
model's reasoning before each phase reply (76.5% of the recorded text and reasoning characters in
the 2026-09-30 run). Setting `SOVEREIGN_RESEARCH_THINK=off` in the environment the product starts
with turns that off for the RESEARCH phases only (`on` forces it on; unset leaves the model's own
behaviour). Measured 2026-09-30 on the same objective: 12 model calls in 643 s, **53.6 s per call**
against 199 s per call with thinking (73% less), and all 12 replies were valid (they are
JSON-schema constrained). Not measured: the quality of a finished answer without thinking, so the
default is unchanged.

QUICK/DEEP rows: `docs/performance/qualification-20260924/` (Ollama, qwen3:14b). The other rows
come from the 2026-09-28 smoke run on the isolated llama.cpp stack. LONG rows:
`docs/performance/qualification-20260926-long-r2/` and the 2026-09-28 live runs. A first request
after idle includes loading the model (about 20-55 s).

## 5. Using LONG from the UI

1. Choose **LONG** in the Route menu. If it reads **LONG (unavailable)** or **LONG (degraded)**,
   hover it for the reason (section 7).
2. Pick the **model**: `qwen3.8:27b` (dense, 131k context, slower) or `qwen3:30b-a3b` (MoE,
   reasoning, 32k context). A model marked "degraded" is disabled: its plan was refused.
3. Pick what the run works through:
   - **Plan steps**: the objective only. The model plans steps, runs each in a fresh session,
     reviews, then writes the answer.
   - **Paste material**: up to the input limit (131,072 characters).
   - **Inbox file**: for large inputs. Put the file in `<state home>\long_inputs\` and give its
     plain name.
4. Write the objective and send. The run panel shows "n of N chunks done", every chunk, and the
   small ledger carried between chunks.
5. While LONG runs, it has the model to itself: a QUICK, CONTINUITY, DEEP or RESEARCH question
   you send waits in the queue ("waiting for LONG job ...") and runs after the LONG job ends;
   STATUS answers at once. An **Interrupted** LONG job does not hold the queue. Measured
   2026-09-30: a QUICK sent during a running 32k LONG job was still `queued` with that stage
   30 s later, the model server proxied only the LONG model until the LONG job ended, and the
   QUICK then completed (39 s).

6. **Counting questions are answered exactly.** If the objective counts, totals or ranks records
   in the material ("how many notes report 16 warnings", "the step with the most warnings"), the
   product does not let the model count. The model writes a small extraction *spec* (a pattern
   for one record and what to compute), the product checks it on a sample, applies it to the
   whole input itself and computes the numbers exactly, ties included, and the model only writes
   the sentences around them. The answer ends with "Computed by the product over N records" and
   the exact table. If the material has no regular record pattern, or the spec cannot be
   confirmed, the run falls back to map/reduce and the answer says: "exact counting was not
   used ... any counts in it are the model's estimate". To keep a counting question on
   map/reduce anyway, start the request with a line `@exact: off` (it may share the top with
   `@model:`). Design: `docs/design/EXACT-COUNTING.md`.

A run survives a product restart: it resumes from its checkpoints by itself. If it ends
**Interrupted** (the model server was away for more than 5 minutes, or the disk was full),
press **Resume** once the cause is fixed. It continues where it stopped.

## 6. Qualification (measuring this machine)

```powershell
cd modules\sovereign
.\.venv\Scripts\python.exe -m sovereign_product.qualification --root . run --profile ollama-production-slate --base-url http://127.0.0.1:5175 --out results.json
.\.venv\Scripts\python.exe -m sovereign_product.qualification --root . report --results results.json --out report.md
```

- It measures the product end to end through its own API, on the product you point it at.
- LONG profiles (`llamacpp-long-dense-27b`, `llamacpp-long-moe-30b-a3b`) need `--inbox
  <state home>\long_inputs` and take 1-3 hours. They are reported, never enforced: do not run
  `derive --write` or `apply` for them.
- `apply` installs a measured envelope into your state home and enforces it. Read
  `docs/performance/qualification-20260924/README.md` first.

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `llama.cpp ... refused an API key (HTTP 401); key source: ...` | The key the product sent is not the supervisor's. A stale `SOVEREIGN_LLAMA_CPP_API_KEY` user variable is the usual cause: remove it, then restart the product. The supervisor's key is `<state home>\runtime\llamacpp_supervisor\api_key`. |
| LONG shows **degraded** / "plan refused ... exceed usable VRAM" | When the supervisor started, too little VRAM was free (a game, Ollama, another model). Free the GPU, then stop and start the supervisor (section 2). `/v1/health` then shows `long_route.status: "ready"`. |
| A LONG job fails at once: "served with a N-token context, below the 32768 ..." | The same cause: the plan was refused, so the model runs with a small window. Restart the supervisor with the GPU free. |
| "reasoned although thinking is off ... thinking-only model" | `qwen3:30b-a3b` is Qwen3-30B-A3B-Thinking: it must have `"thinking": "on"` and a `reasoning_tokens` budget in `modules\sovereign\long_workload.json`. |
| A LONG counting answer ends "exact counting was not used (...)" | The model could not produce a spec the product could confirm, the objective was not a counting question, or the material has no regular records. The counts in that answer are estimates. Rephrase the objective around the records ("how many notes ..."), or use `@exact: off` to keep map/reduce on purpose. |
| A job is **Interrupted** | LONG: press **Resume** (or `POST /v1/jobs/<id>/resume`). Other routes do not resume: send the request again. |
| A job looks stuck | Open its run panel: a LONG stage of `model_unavailable` means it is waiting (up to 5 minutes) for the model server. Cancel stops any route. |
| `internal service error` | Should not happen. Report it with `product.stderr.log`. |

Where things live (`<state home>` defaults to `%LOCALAPPDATA%\SovereignWorkspace\sovereign`):

| What | Where |
|---|---|
| Chats, jobs, answers | `<state home>\runtime\sovereign.db` |
| LONG checkpoints and chunk outputs | `<state home>\runtime\evidence\long\<job id>\` |
| llama.cpp server log / supervisor watcher log | `<state home>\runtime\llamacpp_supervisor\llama-server.log`, `watch.log` |
| GPU/RAM plan per model (LONG models and the QUICK/DEEP/RESEARCH models) | `<state home>\runtime\llamacpp_supervisor\hybrid_plans.json` (present while the supervisor runs); `/v1/health` shows it as `long_route` and `role_models` |
| Backups | `python -m sovereign_product.state_admin --root . backup --out <file.zip>` |

Housekeeping: `docs/RETENTION.md` covers `state_admin prune` and `state_admin purge-deleted`.
Deleting a chat through the API is soft deletion until explicitly purged. With the workspace stopped,
run `python -m sovereign_product.state_admin --root . purge-deleted --older-than-days 30` from
`modules\sovereign` to preview; add `--apply` only after reviewing the list and taking a backup.
No purge is automatic. Existing events, evidence files and backups remain.

## 8. Known limits

- LONG counts are exact only when the material has a record pattern the product can match (a
  regular expression with at most 4,096 characters per record; records that start with a fixed
  phrase, or one record per line of a table or log). Otherwise the run falls back to
  map/reduce, where the counts are the model's estimates (on the 65k-token test input they ran
  7-19% low before exact counting: 100, 110 and 115 against a true 124), and the answer says so.
- Exact counting was confirmed live only on the 32k and 65k qualification notes (records that begin
  with a fixed phrase). Two other shapes were tried on 2026-09-30 and did **not** take the exact
  route: a 5,000-line service log (the model declined: "no three literal characters begin every
  record") and a 3,000-row CSV table (its pattern matched nothing in the sample). Both fell back to
  map/reduce, which did not finish inside the 45-minute test limit. The one-record-per-line option
  (`^` with flag `m`) is unit-tested but was not produced by the model live, so counts over such
  files are not guaranteed to be exact.
- The exact route trusts the model's reading of the objective. On an objective with no record
  structure ("how many components does the design describe, and which is the most important?" over
  a design document) it counted 25 headings and then reported "the most important component is
  phase 0", which is not an answer to the question. Read the table under "Computed by the product"
  and check that the records counted are the ones you meant; use `@exact: off` to keep map/reduce.
- Qualification r3 (the before/after re-measurement of both LONG profiles) was not run; the route
  table above holds only what the individual runs measured.
- `qwen3.5:35b-a3b` is excluded: its Ollama GGUF does not load in upstream llama.cpp.
- The inference RAM budget is 32 GB: the planner refuses bigger plans.
