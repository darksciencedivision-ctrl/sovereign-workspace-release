# Retention: what grows in the state home, and what to do about it

The product keeps its state outside the install tree, in the **state home**
(`%LOCALAPPDATA%\SovereignWorkspace\sovereign` by default; see `SOVEREIGN_STATE_HOME`).
Everything below is relative to it.

## What grows

| Path | What it holds | Growth | Policy |
|---|---|---|---|
| `runtime\sovereign.db` | Sessions, messages (every answer), jobs, and the tamper-evident event log | Small: a few KB per job | **Kept.** The event log is hash-chained, so single rows are never deleted. To start clean, back up (`state_admin backup`) and use a new state home. |
| `runtime\evidence\long\<job id>\` | A LONG run's checkpoints (hash-chained) and every chunk's output | 50-400 KB per run on this machine; more for big inputs | **Prunable** with `state_admin prune` once the run is finished (below). |
| `runtime\evidence\semantic_deep\<session id>\` | DEEP evidence packets that answers link to | Per DEEP answer | **Kept**: answers link to it. `prune` reports its size. |
| `runtime\llamacpp_supervisor\llama-server.log` | The llama.cpp server's log | Rewritten at every supervisor start | Bounded by design. |
| `runtime\llamacpp_supervisor\watch.log` | One line per watcher check (every 5 s) | Was about 2 MB a day, without limit | **Rotated** at 1 MiB into `watch.log.1` (one old copy). |
| `long_inputs\` | Files you put there for LONG `@input:` | Operator-managed | Yours: never touched. |

## Pruning finished LONG runs

`prune` is a **dry run** unless you add `--apply`. It only reads the database (read-only) and the
run directories, and it prints what it would remove and why it keeps the rest.

```powershell
cd "<install root>\modules\sovereign"
.\.venv\Scripts\python.exe -m sovereign_product.state_admin --root . prune --older-than-days 30
.\.venv\Scripts\python.exe -m sovereign_product.state_admin --root . prune --older-than-days 30 --apply
```

A run directory is removed only when **all** of these hold:

- its job is final: `completed`, `failed`, `cancelled`, `rejected`, `timeout` or
  `concurrence_not_reached`;
- the job finished more than `--older-than-days` ago (default 30);
- its checkpoints verify (hash chain and stored outputs); and
- the run recorded a finished `completed` or `failed` status.

It is **kept**, with the reason listed, when:

- the job is `queued`, `running` or `interrupted` (it can still run or resume: `POST
  /v1/jobs/<id>/resume`);
- the run was cancelled or never finished (the runner can still resume it);
- its checkpoints do not verify (nothing is deleted that cannot be classified);
- no LONG job in the database has that id; or
- it is a link rather than a plain directory.

What you lose: the job's answer stays in the chat (it is in the database). Its **run view** (the
chunk list and ledger in the UI, `GET /v1/jobs/<id>/ledger`) then reports "not started", because
its checkpoints are gone.

Recommended routine: run a dry run monthly. Take a backup
(`state_admin backup --out <file.zip>`) before the first `--apply`.
