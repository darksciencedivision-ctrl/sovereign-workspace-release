# PATH A — PROVIDER UNBLOCK SHEET

**Prepared:** 2026-08-06 · **Target HEAD:** `b109f02` — **superseded 2026-08-16 (W-10); current HEAD `176b0f3`** · **Repo:** `D:\multi model terminal app\sovereign-orchestration-workspace`

> ### CORRECTION — 2026-08-16 (W-10). Both audit caveats below are FALSE on this tree.
>
> Re-derived on disk, so do not act on them:
>
> - **B2 is false.** `adapters/frontier/antigravity.py:78` is `ANTIGRAVITY_HEADLESS_MODE = "plan"`, not `accept-edits` at `:72`, and the `antigravity_execution` carve-out was **removed**, not defaulted off — it occurs **zero** times in `adapters/frontier/provider_cli_common.py`. There is nothing to revert before spawning a Gemini worker. Per standing ruling **OP-13**, Antigravity's own `accept-edits` mode is not operator approval, and no carve-out, parameter or default may reintroduce one.
> - **B4 is false, in all three places it appears.** Readiness no longer classifies from the whole retained scrollback: `apps/desktop/control/worker-readiness.js:67` reads the pane's current screen through `RingBuffer.sliceFrom()` and **never** calls `snapshot()` (closed at 19.4). Early "not signed in" text, and a dismissed Grok promo/connector overlay, therefore no longer pin a pane for the life of its buffer.
>
> What the bounded window does NOT close is recorded as **U395/U400**: the window is the last 80 non-blank lines of the last 16 KB of the RAW stream, so a heavily repainting TUI buys fewer lines with that byte budget than plain text does.

This is the operator-facing sequence for getting one complete three-node run. It is written after the
cold audit, so it flags where an audit finding will interfere.

> **Standing constraint:** never run the app while the loop is running.

---

## STEP 0 — Decide two things first (see the questions at the end of the audit)

Whether Antigravity may run in `accept-edits` mode (audit B2), and whether the classifier fix (audit B4)
lands before or after this run. Both change what happens below.

---

## STEP 1 — Gemini / Antigravity, `AUTH_REQUIRED` — **only you can do this**

`agy` has no offline auth surface (U233) and raises a directory-trust modal on first run in a new
directory. The loop is forbidden to answer it, and that prohibition is correct.

```powershell
cd "D:\multi model terminal app\sovereign-orchestration-workspace"
agy
```

Answer *"Yes, I trust the contents of this project"*, complete the sign-in if prompted, confirm the CLI
reaches an authenticated idle state, then exit.

**[SUPERSEDED 2026-08-16 — see the CORRECTION above]** **Audit caveat (B2):** with `adapters/frontier/antigravity.py:72` currently set to `accept-edits`, once
this worker is live it can apply file edits in this worktree without an approval-drawer item. If you have
not ruled on B2, consider reverting that line to `"plan"` before spawning a Gemini worker.

**[SUPERSEDED 2026-08-16 — see the CORRECTION above]** **Audit caveat (B4):** `provider-readiness.js` classifies from the whole retained pane scrollback with no
recency window. Any "not signed in" text printed early in the session stays in the buffer, so a
successfully-authenticated pane can still report `AUTH_REQUIRED` on every subsequent readiness pass, with
no exit except a fresh pane. If Gemini reports `AUTH_REQUIRED` after a clean login, that is the likely
cause — not the account.

---

## STEP 2 — Grok, `USAGE_LIMIT` — **only you can do this**

Grok Build's CLI access is SuperGrok-tier. Confirm the account is on the paid plan and that the CLI is
logged into *that* account, then clear the trust modal the same way:

```powershell
cd "D:\multi model terminal app\sovereign-orchestration-workspace"
grok
```

Answer *"Yes, proceed"*, confirm it responds to one trivial prompt, then exit.

**Open question that predates this run (U310/U311):** Grok's headless `-p` mode exits zero having said
nothing on this host (`text: ""`, `stopReason: "cancelled"`), and the earlier "GROK_PROVIDER_OK"
acceptance was withdrawn as unverifiable. **Whether Grok answers at all through a pane is still
unknown.** Treat a Grok pane that comes up READY and then produces nothing as the expected failure mode,
not a surprise.

**[SUPERSEDED 2026-08-16 — see the CORRECTION above]** **Audit caveat (B4):** Grok's startup promo/connector overlay matches the classifier's
`AWAITING_PROVIDER_SETUP` regex. Once that text is in the ring buffer it stays there, so a dismissed
overlay can pin the worker at `PROVIDER_SETUP_REQUIRED` permanently.

---

## STEP 3 — Governed probe (harmless, one live call per provider)

```powershell
cd "D:\multi model terminal app\sovereign-orchestration-workspace"
py -3.12 tools\providers\frontier_provider_recon.py --action probe --provider all
```

This is the exit-code-first instrument. **If it disagrees with the in-pane state, trust this one** — that
disagreement is audit finding B4, and it has already happened once for Gemini.

---

## STEP 4 — The Python suite timeout — diagnosable without any provider

Independent of the providers, and the only part of Path A I can help execute if you want it. There is no
committed pytest configuration in the repo, so the 600 s ceiling comes from the invocation, not the
repository. To find out whether it is a hang or genuine slowness:

```powershell
cd "D:\multi model terminal app\sovereign-orchestration-workspace"

# 1. Where the time goes — 20 slowest tests, no ceiling
py -3.12 -m pytest tests/ -q --durations=20

# 2. If it hangs rather than crawls, find the test that never returns
py -3.12 -m pip install pytest-timeout
py -3.12 -m pytest tests/ -q --timeout=120 --timeout-method=thread
```

The second command installs a package — flag it if that needs a ruling. `--timeout-method=thread` prints
the stack of whatever is stuck, which turns "the suite times out" into a named test.

---

## STEP 5 — The live acceptance leg

```powershell
cd "D:\multi model terminal app\sovereign-orchestration-workspace"
node apps\desktop\selfcheck\run.js op12-live-acceptance --unit operator-run
```

**Two things to insist on this time, both from the audit:**

Run it against a **committed** HEAD. The previous receipt records
`tested_worktree: "uncommitted final-hardening changes over starting_head"`, which makes its numbers
permanently unreproducible.

Expect audit finding M2 to fire the moment the collaboration leg actually runs. Five of seven
orchestration writers do an unprotected read-modify-write on the whole task/debate record. The first
genuinely concurrent moment — two workers posting debate turns, or one publishing a candidate while the
other publishes progress — can silently discard one of them, after which `close_debate` refuses forever
because it requires a turn from every participant. **If the run reaches the debate leg and then stalls
with a debate that will not close, that is M2, not a provider problem.**

---

## WHAT I CAN DO WITHOUT YOU

Steps 1 and 2 are yours by invariant — I will not answer a trust modal or touch an account. Step 4 I can
drive if you want it run from here, though the bridge to your machine is a Linux VM without `py -3.12` or
`pytest`, so in practice the Python suite has to run on the Windows host. Steps 3 and 5 I can prepare and
read the results of, but they make live provider calls, so I will not fire them without your word.

The remediation work for audit findings B1, B3, B4 and M2 is ordinary build work and is the natural next
loop run once you have ruled on B2.
