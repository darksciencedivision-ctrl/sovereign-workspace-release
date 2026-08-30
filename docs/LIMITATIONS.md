# Known limitations

**Sovereign Workspace 1.0.0-rc.1** · stated as of 2026-08-30

This document exists so that what the product does **not** do is as easy to find as what it
does. Every item below is a deliberate scope decision, not an oversight and not a defect.
Where something is genuinely unfinished it says so in those words.

`shell/tests/test_limitations_are_disclosed.py` asserts that each heading below is present.
That guard exists because a disclosure marker in `modules/sow/docs/THREAT_MODEL.md` was once
removed by an edit that closed the underlying gap — the right outcome, reached without anyone
noticing the disclosure had gone. A statement nothing enforces is a statement that will
eventually disappear quietly.

---

## The product is single-operator by design

Sovereign Workspace runs on one workstation, for one operator, bound to the loopback
interface. That is the shape of the product, and the four limitations below follow from it
rather than from anything being incomplete.

### No authentication

The shell and every module serve unauthenticated. There is no login, no session, no API key.
Anything able to reach the loopback interface on the machine can drive the product with the
operator's full authority.

### No authorization or role separation

There is no user model and therefore no roles, no permissions and no privilege boundaries
between operators. The operator holds final authority over every governed action by design;
the product does not model a second person who holds less.

### No security audit log

The gate ledger and the evidence tree record **build and governance** events — what was
claimed, evaluated and sealed. Neither is a security audit log: they do not record who did
what at runtime, because there is no "who".

### Single operator, loopback only

The product binds `127.0.0.1` and refuses anything else. `modules/sovereign/sovereign_product/
server.py` enforces this in code, not merely in configuration — a non-loopback bind is
rejected rather than warned about. There is no multi-user, shared-deployment or
server-hosted mode, and reaching one would be an architectural change, not a setting.

**What this means in practice.** Treat the machine as the security boundary. Anyone with an
account on it, or any process running as the operator, has full access to the product and its
data. If that is not acceptable for your use, this release is not the right fit — and no
configuration of it will make it so.

---

## No telemetry, no crash reporting, no phone-home

The product transmits nothing about its own use. There is no analytics, no error reporting,
no update check, no usage beacon, and no opt-in framework to enable one later. See
`docs/ADR-006-no-telemetry.md` for why this is a decision rather than an omission.

The consequence, stated plainly: when something breaks, nobody learns about it unless the
operator says so. Diagnosis relies on local logs.

---

## Windows only

The release tooling, the process containment (Windows Job Objects), the terminal layer
(ConPTY) and the installer are Windows-specific by construction. There is no macOS or Linux
build and no compatibility layer.

---

## Nineteen of twenty-nine gates have never been reviewed

The programme's own assurance record is incomplete, and the product does not pretend
otherwise. Of 29 gates, 9 are PASS (all historical, gates 0–6), 1 is an adjudicated STOP, and
**19 are CANDIDATE with no evaluator recorded** — claimed by the builder, checked by nobody.

`docs/RELEASE-ASSURANCE.md` carries the detail. This is the largest open item in the release
and it is a review backlog, not an engineering one.

---

## Verification not performed

Named so their absence is not mistaken for success:

- **No clean-room install on a bare machine.** The install path is exercised against a fresh
  destination on a developer host; it has not been run on a virgin operating system.
- **No end-to-end run driven through the UI.** The services start and report healthy; no work
  has been driven through them as an acceptance test.
- **The Electron desktop application has not been launched** as part of release verification.
  Its 1,109 unit tests pass; the assembled app was not started.
- **No third-party security audit or penetration test.**

---

## The licence is not final

`LICENSE` is complete and operative but has not been reviewed by legal counsel, and its
governing-law clause is unfixed pending that review. It is marked `PENDING COUNSEL SIGN-OFF`.
See `docs/THIRD-PARTY-LICENCE-POSITION.md` for the third-party position.

---

## The archive names the machine that built it, in places

The distribution carries the build operator's account name and directory layout in a small,
enumerated set of files. This is disclosure, not a functional defect: nothing in the product
reads these paths at runtime, and an installation does not depend on them.

**What was fixed rather than disclosed.** The identifiers that mattered are gone:

| Was | Now |
|---|---|
| `shell/config/install.json` held the build tree and the build operator's `python.exe` | a template carrying `<set-by-installer>` |
| all five module adapters held an absolute `root` into the build tree | `${install_root}`, resolved from where the shell actually is |
| distillery and tokencenter pinned that interpreter as `argv[0]` | `${python312}`, the interpreter the shell is running under |
| `shell/src/distillery.py` hardcoded two of the operator's directories in product code | environment variables with no default |
| `SBOM.json` recorded absolute build-host paths as licence provenance | repository-relative |
| the agent envelopes and three `Start-*.ps1` launchers shipped | excluded from the archive |

**What remains, and why each cannot simply be deleted.**

- **Provenance records** — `INSTALL-PROVENANCE.json` for each module, `DISCOVERY.md`, the
  SWS-UI-001 addenda. These record where each vendored module *came from*. The path is the
  content; scrubbing it would not remove information, it would make the record false.
- **Module evidence trees** — `modules/*/docs/evidence`, `modules/*/runs`. Twenty-five of the
  twenty-eight files carrying an identifier are cited by something you may run:
  `test_evidence_receipts.py`, `run_phase19_gate.py`, the desktop selfcheck scripts, the
  decision registers. Cutting them would trade a disclosure for a broken verification path.
  The three cited by nothing were cut.
- **`BUILD-DIRECTIVE-SWS-UI-001.md`** — the shell serves it as a documentation route and the
  README links it, so removing it would replace a disclosure with a broken link. The builder
  envelope forbids the builder editing it, so the change is the operator's to make.
- **`docs/DECISIONS.md`** — read-and-hash-only for the builder, for the same reason.

**This set is pinned, not merely observed.**
`shell/tests/test_developer_identifiers_are_bounded.py` fails if any file outside the
disclosed list acquires an identifier, if the repaired files regress, if the build harness
starts shipping again, or if a disclosed entry stops needing disclosure. It was proven by
reintroducing all three defect classes in an isolated clone and confirming each was caught.
The number can go down without editing that file. It cannot go up.

## Lifecycle: resolved in this release

Four limitations previously listed here are closed. They are recorded rather than deleted, so
a reader holding an older copy can tell what changed and why.

- **Runtime state no longer lives inside the install root.** Each module writes under
  `%LOCALAPPDATA%/SovereignWorkspace/<module-id>` — one directory per module, never shared.
  That relocation is what made the three below possible; state inside the thing being replaced
  cannot survive replacing it.
- **Uninstall works on an installation that has been used.** It removes exactly the paths its
  manifest records, then names the operator's state and *keeps it by default*. `-PurgeData`
  removes it as well, after listing what goes.
- **An upgrade path exists.** `tools/release/upgrade.ps1` verifies the incoming artifact
  against its sidecar before touching anything, backs up the state root, moves the outgoing
  installation aside rather than deleting it, installs, verifies, and leaves both the previous
  installation and the state backup in place. Rollback is moving the previous installation
  back.
- **Backup and restore exist.** `backup_state.ps1` and `restore_state.ps1` produce and consume
  one archive with a SHA-256 sidecar. Restore verifies before writing anything, refuses an
  archive whose sidecar does not match, and never deletes the state it replaces.

What has *not* changed: an existing installation created before this release still has its
state beside the code. Nothing migrates it automatically. Copy it into the new state root, or
start fresh.
