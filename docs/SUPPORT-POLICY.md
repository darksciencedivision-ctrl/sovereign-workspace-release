# Support and versioning policy

**Sovereign Workspace 1.0.0-rc.1** · effective 2026-08-30 · EPC-01 P4-10

This document states what is supported, how versions work, and what is promised. Where
nothing is promised it says so, because an unstated promise is the one that gets assumed.

---

## Platform support

| | |
|---|---|
| **Operating system** | Windows 10 and Windows 11, x64 |
| **Python** | 3.12 for SOVEREIGN and SOW; 3.14 for the Debate Table |
| **Node.js** | 24.x with npm 11.x |
| **Model runtime** | Ollama, local, on loopback |

**Windows only, by construction, not by omission.** Process containment uses Windows Job
Objects, the terminal layer uses ConPTY, and the installer and release tooling are PowerShell.
There is no macOS or Linux build, none is planned for this line, and a port would be new
engineering rather than configuration.

**Two Python versions is deliberate.** SOVEREIGN and SOW are provisioned on 3.12 from pinned
locks; Debate is provisioned on 3.14 from its own. `tools/release/install.ps1` creates both.
Do not consolidate them by hand — the locks are resolved per interpreter.

---

## Version scheme

The workspace ships **six independent version numbers**, and that is intentional. Each names
a component with its own history, and flattening them to one would destroy real provenance
rather than simplify anything.

| Component | Version | Source of truth |
|---|---|---|
| Workspace (the composed product) | `1.0.0-rc.1` | `VERSION.json` |
| SOVEREIGN | `3.1.2` | `modules/sovereign/sovereign_version.py` |
| SOVEREIGN UI shell | `3.1.2` | its `package.json`, tracking its module |
| Sovereign Distillery | `1.1.0rc3` | `modules/distillery/pyproject.toml` |
| Multi-Model Terminal (SOW) | `0.1.0` | `modules/sow/apps/desktop/package.json` |
| Debate Table | `v1.2.1-hardening` | its release artifact name |

**The workspace version is the one to cite.** When reporting a problem, quote
`VERSION.json`'s version and the seal commit from `RELEASE-MANIFEST.json`; those two identify
the build exactly. Module versions describe parts, not the whole.

`tools/release/build_release.ps1` derives every artifact name from a **named file and field**
rather than from memory, so the names are reproducible from the commit.

### What the workspace version means

`MAJOR.MINOR.PATCH`, with a pre-release suffix while the release is a candidate.

- **MAJOR** — a change that requires operator action to upgrade: a migration, a changed
  authorization model, a removed module.
- **MINOR** — new capability, backwards compatible with existing state.
- **PATCH** — defect fixes only.
- **`-rc.N`** — a release candidate. **Not for production use.** The current build is
  `1.0.0-rc.1` and carries the open items in `docs/LIMITATIONS.md`.

---

## What is promised

Honestly and narrowly, for `1.0.0-rc.1`:

- The archive's contents are hash-verifiable. `RELEASE-MANIFEST.json` enumerates them and
  `tools/release/release_manifest_check.py` verifies them.
- The installer refuses to proceed on a hash mismatch, a non-empty destination, or a path
  that escapes the destination.
- Third-party components are enumerated in `NOTICE`, generated from the SBOM.
- Every automated test that ships is run before a release is cut, and its result is recorded.

## What is not promised

- **No availability, uptime or response-time commitment.** There is no SLA.
- **No support channel or ticketing system**, and no guaranteed response to any report.
- **No security-advisory notification.** The product does not phone home
  (`docs/ADR-006-no-telemetry.md`), so **checking for updates is the operator's
  responsibility**. There is no mechanism that will tell you a fix exists.
- **No backwards-compatibility guarantee across MAJOR versions**, and none at all for a
  release candidate: `rc.2` may change state formats without migration.
- **No data-loss guarantee.** See the uninstall limitation in `docs/LIMITATIONS.md`, and back
  up the state directory yourself before any upgrade.

## Deprecation

For `1.0.x` and later: anything removed is first marked deprecated in a MINOR release, with
the replacement named in the release notes, and removed no earlier than the next MAJOR.

**This does not apply to release candidates.** Anything in `1.0.0-rc.N` may change or
disappear in `rc.N+1` without notice or migration.

---

## Reporting a problem

There is no ticketing system. When reporting a problem to whoever provided this build,
include:

1. The workspace version and the seal commit from `RELEASE-MANIFEST.json`.
2. The output of `tools/release/verify_install.ps1 -Dest <your install>`.
3. The relevant logs from the state directory — see `docs/OPERATIONS.md`.
4. What you expected, what happened, and whether it reproduces.

Because the product transmits nothing, **a problem you do not report is a problem nobody
knows about.**
