# Retention: what grows in the state home, and what to do about it

The product keeps its state outside the install tree, in the **state home**
(`%LOCALAPPDATA%\SovereignWorkspace\sovereign` by default; see `SOVEREIGN_STATE_HOME`).
Everything below is relative to it.

## What grows

| Path | What it holds | Growth | Policy |
|---|---|---|---|
| `runtime\sovereign.db` | Sessions, messages (every answer), jobs, and the tamper-evident event log | Small: a few KB per job | Chats are soft-deleted until explicitly purged with `purge-deleted`. The hash-chained event log remains. |
| `runtime\evidence\long\<job id>\` | A LONG run's checkpoints (hash-chained) and every chunk's output | 50-400 KB per run on this machine; more for big inputs | **Prunable** with `state_admin prune` once the run is finished (below). |
| `runtime\evidence\long\<job id>\exact.json` | An exact-counting run's spec, computed table and answer (small; a crash can leave `exact-input.tmp` / `exact-job.tmp`, up to the input's size) | A few KB per run | **Prunable** like the run folder it sits in; `prune` also clears stray temp files of a job that is not running. |
| `runtime\llamacpp_supervisor\hybrid_plans.json` | The GPU/RAM plan of every LONG and role model (`applied`, layers, context, or the reason it was refused) | One small file, rewritten at every supervisor start | Bounded by design; `/v1/health` reads it (`role_models`). |
| `runtime\evidence\semantic_deep\<session id>\` | DEEP evidence packets that answers link to | Per DEEP answer | **Kept**: answers link to it. `prune` reports its size. |
| `runtime\llamacpp_supervisor\llama-server.log` | The llama.cpp server's log | Rewritten at every supervisor start | Bounded by design. |
| `runtime\llamacpp_supervisor\watch.log` | One line per watcher check (every 5 s) | Was about 2 MB a day, without limit | **Rotated** at 1 MiB into `watch.log.1` (one old copy). |
| `long_inputs\` | Files you put there for LONG `@input:` | Operator-managed | Yours: never touched. |

## Purging deleted chats

Deleting a chat through the API is a soft delete: its rows remain until you run this command.
No purge runs automatically. Stop the workspace and take a backup before applying a purge.

```powershell
cd "<install root>\modules\sovereign"
.\.venv\Scripts\python.exe -m sovereign_product.state_admin --root . purge-deleted --older-than-days 30
.\.venv\Scripts\python.exe -m sovereign_product.state_admin --root . purge-deleted --older-than-days 30 --apply
```

The first command opens the database read-only and lists eligible session ids. The second removes
chats soft-deleted at least 30 days ago and their dependent database rows, appending a purge event
for each. Live chats and recently deleted chats remain. Existing events (including session titles),
separate evidence artifacts and backups remain; this is not a secure disk erase. LONG evidence has
its separate `prune` command below. Unrelated detached jobs are not purged by `purge-deleted`.

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
- the run recorded a finished `completed` or `failed` status (a run answered by the exact-counting
  route records it in `exact.json`, which counts the same way).

It is **kept**, with the reason listed, when:

- the job is `queued`, `running` or `interrupted` (it can still run or resume: `POST
  /v1/jobs/<id>/resume`);
- the run was cancelled or never finished (the runner can still resume it);
- its checkpoints do not verify (nothing is deleted that cannot be classified);
- no LONG job in the database has that id; or
- it is a link rather than a plain directory.

Whatever the job's state, a job that is **not queued or running** has its leftover
`exact-input.tmp`, `exact-job.tmp` and `exact.json.tmp` removed by `--apply` (they exist only when
the product stopped in the middle of counting); the dry run lists them under `stray_temp`.

What you lose: the job's answer stays in the chat (it is in the database). Its **run view** (the
chunk list and ledger in the UI, `GET /v1/jobs/<id>/ledger`) then reports "not started", because
its checkpoints are gone.

Recommended routine: run a dry run monthly. Take a backup
(`state_admin backup --out <file.zip>`) before the first `--apply`.
