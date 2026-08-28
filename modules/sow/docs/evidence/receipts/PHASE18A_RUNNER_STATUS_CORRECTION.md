# CORRECTION — `PHASE18A_RUNNER_STATUS.txt` states something false about authentication

**Recorded 2026-07-31, third review round, Phase 18A (OP-12).**
The receipt it names is **not rewritten**. Evidence is append-only and an artifact that was
published is part of the record whether or not it was right (invariant 12). This note sits beside
it, carries the false sentence, the data that falsifies it, and what remains true.

## The false statement

`docs/evidence/receipts/PHASE18A_RUNNER_STATUS.txt`, lines 32 and 104:

```
  auth confirmed     : False  (the CLI itself reported a signed-in session - NOT launch readiness)
```

Read literally, that line tells the operator the CLI **did** report a signed-in session — on the
line that reports `False`, for the provider (`google_antigravity`, U228) whose authentication is
*not confirmable offline at all*. The parenthetical was printed unconditionally, so it could not
disagree with its own value.

Found independently by both round-3 reviewers (spec-auditor **MAJOR-1**, gate-validator **A-1**).

## The falsifying data, from the same receipt

Two lines above the false one, the same entry reads:

```
    ^ caveat          : AVAILABLE on an UNVERIFIED session: ... nothing here can confirm the
                        operator is signed in — only a live probe can
  authentication     : UNVERIFIED  no offline auth-state surface on this CLI
```

So the receipt contradicts itself in the space of three lines. Nothing reported a signed-in
session for Antigravity; nothing could.

## What is true

* `auth_confirmed` is derived, not asserted: it is `True` only when the CLI's own auth-reporting
  command said so. For `grok_build` on this host it was `True` on real output
  (`You are logged in with grok.com`); for `google_antigravity` it was `False` because that CLI
  has no offline auth surface. **The values in the old receipt are correct. Only the gloss is
  wrong.**
* `auth_confirmed` is not launch readiness, and never was — that part of the sentence stands.
* Every other line of the superseded receipt (states, models, subscription resources,
  registration, the probe refusal, the install no-op, the launch carriage) was re-produced by the
  corrected run and is unchanged in substance.

## Where the corrected receipt is

`docs/evidence/receipts/PHASE18A_RUNNER_STATUS_R3.txt` — generated after the fix, on the same
host, same day. It now prints, for a `False` value:

```
  auth confirmed     : False  (NOTHING reported a signed-in session here - which is not a claim
                               that the operator is signed out)
```

## The fix, and the test that would have caught it

`tools/providers/run_frontier_providers.ps1` builds the gloss from `$Entry.auth_confirmed` before
printing it. `tests/unit/test_run_frontier_providers_ps1.py::TestStatusHonesty::
test_the_auth_gloss_follows_the_value` drives the real runner against a stub engine in both states
and asserts each gloss appears **and** that the other one does not.

## The lesson

The field was *renamed* in round 2 for honesty (`launch_ready` → `auth_confirmed`, finding N-5) and
the rename shipped with a sentence that undid it. A static annotation attached to a dynamic value
is a claim in disguise; if it cannot go false when the value does, it is not a disclosure.

---

## APPENDED 2026-08-01 (round-4 spec-audit finding 6) — "unchanged in substance" was too strong

The sentence at the end of *What is true* above says every other line of the superseded receipt
"was re-produced by the corrected run and is unchanged in substance". It is left standing (this
document is append-only too), and it is **wrong about two of the items it enumerates**. A sibling
correction note is the one artifact whose whole job is to be exactly accurate about what changed;
this paragraph is what that costs when it is written from a diff read too quickly.

**1. The probe refusal changed materially, not cosmetically.**
`PHASE18A_RUNNER_STATUS.txt:67` told the operator the switch is extended at Phase 18C:

```
  live gate  : False - ... DENIED (fail closed; the operator extends the switch at Phase 18C)
```

`PHASE18A_RUNNER_STATUS_R3.txt:70-80` says the opposite of the operative half — that editing
`config/live_operation.json` is **not sufficient and not safe on its own**, because
`_AUTHORIZED_PROVIDERS` is code-pinned and raises on an unknown id, which would deny *every* live
provider including `claude_code`. That is the U237 correction, and it is a **reversal of an
instruction the old receipt got wrong**, not a re-wording.

**2. The install caveat was dropped, not re-produced.**
`PHASE18A_RUNNER_STATUS.txt:69-71` carried the round-2 N-11 disclosure verbatim — *this run
demonstrates only the repeat-safe short-circuit; the `-InstallMissing` refusal branch is NOT
exercised here*. `PHASE18A_RUNNER_STATUS_R3.txt:95` reduced it to "(no `-InstallMissing`; both CLIs
already present)". **The caveat stands and is restored here rather than by editing the published
R3 receipt:** section 3 of `PHASE18A_RUNNER_STATUS_R3.txt` demonstrates ONLY the repeat-safe
short-circuit on a host where both CLIs are already installed. It does **not** exercise the
`-InstallMissing` refusal, the failed-install path (exit 5), the unverifiable-install path
(exit 7), or the PATH-refresh path (exit 4). Those four are covered by the deterministic suite
against stubbed `npm` / `Invoke-RestMethod` (`tests/unit/test_run_frontier_providers_ps1.py`),
mutation-verified at the round-4 gate — never on this host's real vendor installers, which is
also why the round-4 gate-validator's finding 5 (no positive test for exit 4) is recorded rather
than waved off.

Nothing in the *values* either receipt reports changed. The two items above are about what the
receipts **say about themselves**, which is exactly the class of defect this whole document exists
to record.
