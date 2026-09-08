# SWS-CORRECTIVE-01 workstream 4 — the frozen acceptance workflow

**Status: FROZEN BEFORE EXECUTION.** The workflow, its expected artifacts and its success
criteria were written and committed before the acceptance sequence was run. A criterion changed
after seeing a result is not a criterion.

**Workflow ID:** `SWS-ACCEPT-01`

---

## 1. What environment this requires, and what it must not be

The acceptance gate requires a **fresh Windows VM or clean host**: documented OS build, a
standard (non-administrator) user, no development checkout, no global project packages, no
existing `%LOCALAPPDATA%\SovereignWorkspace`, and no prior Sovereign configuration.

> **A new directory on the developer machine is a fixture install, not clean-machine evidence.**
> This document uses both, and never confuses them. Every result records which environment
> produced it:
>
> - `FIXTURE` — a temporary install on the development host. Proves the mechanism.
> - `CLEAN` — a fresh VM or clean host. Proves the product installs and runs where nothing has
>   been prepared for it.
>
> A `FIXTURE` result may not be reported as satisfying gate D.

## 2. The frozen workflow

One representative, non-trivial operator task, chosen because it exercises the assembled UI, real
local model work, durable inspectable output, and restart survival — not a health page.

**The task.** Through the shell at `http://127.0.0.1:5180`, open SOVEREIGN, start a session, and
submit:

> *"Using only the supplied project evidence, state which model is configured as the primary
> reasoner and where runtime state is kept. Cite each fact."*

**Expected artifacts**, each independently checkable without asking the product whether it
succeeded:

| # | Artifact | Where | Independent check |
|---|---|---|---|
| A1 | the answer, persisted | `%LOCALAPPDATA%\SovereignWorkspace\sovereign\runtime\` (SQLite) | open the database with a separate `sqlite3`/Python process; the row exists and `PRAGMA integrity_check` returns `ok` |
| A2 | the execution's raw provenance | the session's evidence directory | the raw record files exist and their recorded SHA-256 matches their bytes |
| A3 | the acceptance verdict | in the job record | `accepted`, and the answer names `qwen2.5:3b-instruct` and `SovereignWorkspace`, each with a `[source:…]` citation naming a source that is in the packet |
| A4 | the SOW readiness receipt | `%LOCALAPPDATA%\SovereignWorkspace\sow\receipts\SHELL-LIVE-READY.json` | exists, `ok:true`, mtime later than launch — and **not** inside the installation |

**Success criteria**, independent of the product's own verdict:

1. A1–A4 all present and checkable as above.
2. The answer's factual claims match the evidence packet's contents, checked by a reader that is
   not the generating model.
3. After a full restart of the shell and modules, the persisted answer is still readable and
   identical byte-for-byte.
4. No file was written inside the installation directory during the workflow.

**Each shipped runnable module's advertised core function is exercised separately** where it is
not part of the above: Debate Table (a bounded debate round completes and persists), Token Center
(a value is recorded and read back from its SQLite store), Distillery (its file-driven status
reflects a change on disk). A health page is not a completed module workflow, and the Distillery
console being reachable is **not** training, model promotion, or demonstrated learning; it is a
status surface and is reported as one.

## 3. The required acceptance sequence

Each step records: environment (`FIXTURE`/`CLEAN`), command, start/end time, exit code, PASS /
FAIL / SKIP / BLOCKED, reason, and evidence location.

| # | Step | What must hold |
|---|---|---|
| 1 | Install the identified artifact using only declared prerequisites | full output captured; artifact SHA-256 recorded and matched to the candidate |
| 2 | Launch through the supported operator entry point | service identity confirmed via `/api/shell-info`; **source-tree independence proven** — the installed copy runs with no checkout present |
| 3 | Execute the frozen workflow through the assembled UI | screenshots or action records, sanitised logs, output artifact hashes |
| 4 | Cancel real in-progress work | bounded stop, correct final state, no further model calls after the cancel, then restart and complete another task |
| 5 | Crash an **owned test instance** at a defined checkpoint | recover; open persisted state; inspect for loss, duplication, corruption, stuck tasks |
| 6 | Back up, verify independently, restore into a **separate** state location, reopen, validate meaningful data | not a file count — the actual answer text and a database integrity check |
| 7 | Upgrade an exercised previous installation to the candidate; repeat the workflow; exercise rollback with an injected candidate failure | the declared migration/compatibility contract is followed |
| 8 | Uninstall after use, preserving state by default; verify documented reinstall/restore recovery | purge testing only against explicitly generated disposable fixture data |
| 9 | Repeat essential launch/workflow checks with a **non-writable installation** and standard-user state permissions | launch and the workflow both succeed |

### What the recovery contract permits losing

Stated explicitly, because step 5 is meaningless without it:

- **Committed and durable:** any job whose record has reached `completed`, `accepted`,
  `rejected`, `failed` or `cancelled`, and its persisted answer and raw provenance.
- **May be lost by a crash:** a job that was still `running`, its partial model output, and any
  streamed progress. It must reappear as a terminal failure or be absent — never as a task stuck
  in `running` forever with no owner.
- **Never acceptable:** a truncated or corrupt database, a duplicated committed answer, or a
  committed answer whose bytes changed.

## 4. Execution record for this run

See `evidence/SWS-CORRECTIVE-01/04-acceptance/`. Gate D's verdict is stated there, with the
environment label on every step. Where a fresh machine was unavailable, the step is marked
**BLOCKED** with the exact missing resource — never converted to a PASS.
