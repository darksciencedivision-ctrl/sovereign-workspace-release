# W-18b — OS-LEVEL CONTAINMENT: DESIGN NOTE, AWAITING OPERATOR RULING

**Unit:** W-18b (R-12 / punch list 1.10, the large half) · **Status:** **STOPPED — no edit made**
**Written:** 2026-08-16 · **Requires:** an operator ruling before any code is written (§8, Invariant 1)

W-18a landed the small half (`35f44de`): process-level fault handlers that run the terminal-releasing
teardown. This note covers only the half that crosses a language boundary.

---

## The five lines

1. **Recommended mechanism: assign-at-spawn over the existing IPC surface** — the Node shell hands
   the freshly spawned PTY pid to the Python node runtime, which calls
   `JobObjectContainment.assign(pid)` (`node_runtime/supervisor/containment.py:80-92`) and **holds
   the job handle for the life of the session**.
2. **Why not a helper process:** `KILL_ON_JOB_CLOSE` fires when the *last handle closes*
   (`containment.py:60-63`). A helper invoked with the pid and then exiting would kill the tree
   immediately; keeping it alive means inventing a second long-lived supervisor lifecycle to own a
   handle the node runtime already owns.
3. **Why not Node-side FFI:** it adds a native binding (`koffi`/`ffi-napi`) — a new dependency, which
   §10 forbids and R5 makes a stop condition — and another ABI rebuild on top of the `node-pty`
   rebuild the Tier-7 Electron upgrade already needs.
4. **Cost of the recommendation, stated plainly:** it needs the IPC surface to grow a **write** op.
   `apps/desktop/supervisor.js:25-30` already records exactly this and names its blocker: *"that
   pid→job handoff needs the IPC surface to grow a write op (blocked on the U25 per-node credential
   broker)"*.
5. **Ordering dependency the directive does not state, and this is the decision-relevant part:**
   **W-18b depends on W-41.** W-41 signs the *whole* envelope rather than only `payload` and adds a
   nonce/sequence, and the directive itself marks that as *"Required before `McpControlSurface`
   carries writes"*. Adding a containment write op before W-41 would put an unauthenticated
   `from_node`/`type`/`msg_id` on a path that can kill process trees.

---

## What is true on the tree today [OBSERVED]

- `node_runtime/supervisor/containment.py:59-92` implements `CreateJobObjectW` +
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` + `AssignProcessToJobObject`, and `assign()` is already
  fail-closed: *"a node process that cannot be assigned must not keep running."*
- `grep -rn "JobObject" apps/desktop --include=*.js` returns **nothing**. The Node shell has no
  containment at all.
- Teardown is cooperative. After W-18a a *fault* also releases terminals, but neither covers
  `SIGKILL`/Task-Manager termination of the shell, which is precisely what a Job Object does cover.

## What W-18a does and does not close

| | Covered after W-18a | Still open (W-18b) |
|---|---|---|
| Unhandled rejection / uncaught exception | **yes** — terminals released, non-zero exit | — |
| Cooperative quit (`before-quit`) | yes (pre-existing) | — |
| Shell killed by the OS or Task Manager | **no** | Job Object kill-on-close |
| Provider CLI outliving the shell | **no** | Job Object kill-on-close |

## The ruling requested

1. Adopt **assign-at-spawn over IPC** (recommendation), or direct one of the alternatives?
2. Confirm the **W-41-before-W-18b** ordering, or authorize a containment write op ahead of it with
   a stated reason?
3. Is **U25** (per-node credential broker) in scope for this programme, or does W-18b stay STOPPED
   until it is closed separately?

**No file was modified for W-18b.** Read the size as **M→L**, per the directive.

*Note ends. It proposes; it authorizes nothing.*
