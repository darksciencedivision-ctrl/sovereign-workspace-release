# SWS-ACCEPT-01 — acceptance record

**Workflow:** `docs/ACCEPTANCE-WORKFLOW.md`, frozen and committed before this ran.
**Candidate:** `45751ac54363cf77ff8bc672eca7f375d42de9cb`
**Artifact:** `sovereign-workspace-1.0.0-rc.1-install.zip`
sha256 `5f45b35acd5791cd4bfc7122ede80bebb420e629ddb56a75d998d0b398c25953`

## ENVIRONMENT: FIXTURE — this does **not** satisfy gate D

Every step below ran on the operator's **development host**, into a disposable install and a
disposable state root under the system temp directory. The workflow document is explicit that a
new directory on a developer machine is a fixture install and not clean-machine evidence, and
this record does not present it as such.

**What gate D requires and this run did not have:** a fresh Windows VM or clean host with a
documented OS build, a standard non-administrator user, no development checkout, no global
project packages, no existing `%LOCALAPPDATA%\SovereignWorkspace`, and no prior Sovereign
configuration. This session had exactly one machine, and it is the opposite of all five.

What a FIXTURE run *does* prove: that the artifact installs, that the installed copy runs
independently of any source tree, that the lifecycle tooling works against a real 20,000-file
installation rather than a synthetic one, and that the harness itself is correct — so that
running it on a clean machine is a matter of having the machine, not of writing anything more.

---

## Step results

*(table filled in from `acceptance-record.jsonl`)*

---

## What each passing step actually demonstrated

*(filled in below)*
