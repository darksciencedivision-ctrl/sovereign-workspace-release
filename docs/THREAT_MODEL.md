# Threat model — Sovereign Workspace

**Version 1.0.0-rc.1** · workspace level · EPC-01 P4-9

`modules/sow/docs/THREAT_MODEL.md` covers the orchestration workspace's internal trust
boundaries in detail. This document covers the **composed product** a recipient installs, and
deliberately states unimplemented controls as unimplemented — a threat model that lists only
what was built is a marketing document.

Status vocabulary, used strictly below:
**ENFORCED** (a control exists and is verified in code) · **PARTIAL** (some legs real, the
absent ones named) · **NOT IMPLEMENTED** (asserted nowhere, built nowhere) ·
**OUT OF SCOPE** (a deliberate ruling, recorded in `docs/LIMITATIONS.md`).

---

## The trust model

**One operator, one machine, one trust level.** Everything the product does, it does with the
operator's authority. There is no second principal, so there is nothing to separate.

That makes the host the security boundary. The controls below defend the operator against
*the outside* and against *the product's own mistakes*. None of them defends the operator
against anyone who already has the machine.

---

## Boundaries

| # | Boundary | Trusted side | Untrusted side |
|---|---|---|---|
| B1 | Loopback network | the shell and modules | anything else on the host that can open a socket |
| B2 | The archive | the verified install | the archive as received, until its hash is checked |
| B3 | Dependency supply | pinned, hash-verified artifacts | the package registries and GitHub |
| B4 | Model output | the operator's judgement | anything a local or frontier model emits |
| B5 | Frontier provider | the operator's explicit authorization | any code path that would spend quota |
| B6 | The filesystem | paths inside the install root | any path an adapter or archive names |

---

## Threats

### T1 — Another local process drives the product
**B1.** Any process on the host can reach loopback and act as the operator.
**Status: OUT OF SCOPE.** The single-operator ruling accepts this; the machine is the
boundary (`docs/LIMITATIONS.md`). No authentication exists and none is planned for this line.
Mitigation is the operator's: do not run this on a shared or untrusted machine.

### T2 — A remote origin drives the product through a browser
**B1.** A page the operator visits attempts requests against the shell.
**Status: ENFORCED.** Loopback-only binding refuses non-loopback addresses in code; `Host`
and `Origin` are exact-matched on every state-changing request; no CORS headers are emitted;
a per-instance CSRF nonce is served only in the shell's own HTML.

### T3 — A tampered archive installs
**B2.** The install archive is modified in transit or at rest.
**Status: ENFORCED.** The installer verifies the archive against its `.sha256` sidecar before
reading its contents, and refuses to proceed on mismatch. `RELEASE-MANIFEST.json` enumerates
the contents with per-file hashes and `release_manifest_check.py` verifies them.

### T4 — An archive entry escapes the destination
**B2/B6.** A crafted entry uses `..` or an absolute path to write outside the install root.
**Status: ENFORCED.** Every entry's resolved destination is checked against the destination
prefix and rejected if it escapes. The installer additionally refuses a filesystem-root
destination and a non-empty one.

### T5 — An adapter path escapes containment
**B6.** A module adapter names a path outside the workspace, or reaches one through a
junction or symlink.
**Status: ENFORCED.** Containment is decided by canonical resolution through
`GetFinalPathNameByHandleW`, which resolves junctions, symlinks and 8.3 short names. Prefix
string comparison is explicitly forbidden as the mechanism. UNC and device paths are rejected
on the raw input, before normalisation could hide them.

### T6 — A dependency arrives unverified
**B3.** A ~100 MB binary is fetched from the internet by an install script.
**Status: ENFORCED, and this was a real defect during this programme.** Electron is
provisioned from a hash-verified zip checked against the `checksums.json` inside the npm
package the lockfile pins (`docs/ADR-005-...`). The installer previously ran a plain `npm ci`
and let Electron's postinstall download it unchecked; that is fixed and
`shell/tests/test_installer_honours_adr005.py` holds it shut.

### T7 — A known-vulnerable dependency ships
**B3.** A component with a published advisory reaches a recipient.
**Status: PARTIAL.** The **Node** side is ENFORCED: `check_node_advisories.py` is a release
gate running `npm audit` against both trees with a threshold of zero. The **Python** side is
**NOT IMPLEMENTED** — the SBOM is generated from the build machine's virtual environments and
its own metadata marks Python coverage `partial-parked` and `missing-parked`, so it cannot be
used for scanning. Tracked as P2-1/P2-2.

### T8 — A test or code path spends provider quota
**B5.** A run makes a billable frontier call without the operator authorizing it.
**Status: ENFORCED.** Live operation is denied by absence: the authorizing configuration is
gitignored, untracked, absent from disk and absent from the archive, so a fresh install
cannot make a billable call. The test suite installs a guard that raises if any test spawns a
live provider CLI, and that guard has its own positive controls — which were themselves found
silently broken during this programme and repaired.

### T9 — A credential ships in the distribution
**B2.** A key, token or private key reaches a recipient.
**Status: ENFORCED, and measured.** `package_boundary_gate --from-commit` scans the archive
for key material, env files, databases, runtime state and credential patterns; it exits
non-zero on a planted violation and zero on the current archive. An independent sweep of the
extracted archive found every credential-shaped hit to be a declared detector fixture.

### T10 — Model output is acted on as fact
**B4.** A local or frontier model emits something wrong and the product acts on it.
**Status: PARTIAL.** Deterministic code owns pricing, eligibility, permission and gate logic —
never model output — and gates are explicit, so a failed artifact cannot advance. What is
**NOT IMPLEMENTED** is any content-level validation of model output itself: the operator
reviews it. `LICENSE` §5 states this to the recipient.

### T11 — Runtime state is destroyed by ordinary lifecycle operations
**B6.** An upgrade or uninstall deletes the operator's data.
**Status: ENFORCED.** This was the largest open risk in the previous revision of this document
and it is now closed at the root: state lives **outside** the install tree, under
`%LOCALAPPDATA%\SovereignWorkspace\<module-id>`, so replacing the installation cannot reach
it. Four controls follow from that and each is proven by test:

- A module may write only inside the install root **or inside its own state root**, decided by
  canonical resolution. A declaration naming anywhere else — including another module's state
  root — is refused as a configuration error. H-5 is extended to a second named root, not
  relaxed.
- Uninstall keeps state by default and names it; `-PurgeData` lists what it removes first.
- Upgrade backs up state, then **moves** the outgoing installation aside rather than deleting
  it. Nothing in the upgrade path deletes anything.
- Restore verifies the archive against its sidecar before writing, and moves any existing
  state aside rather than overwriting it.

Residual: an installation created **before** this release still has state beside its code, and
nothing migrates it automatically. Stated in `docs/LIMITATIONS.md`.

### T12 — A runtime action cannot be attributed after the fact
**B1.** Something happened and there is no record of what or when.
**Status: NOT IMPLEMENTED.** There is no security audit log, and observability is thin: four
files use `logging`, most diagnostic output is `print()` to a console, with no levels, no
rotation and no configured destination (P4-6). Once a service's stdout is gone, so is the
record.

---

## Registered absences

Collected so they are countable rather than scattered:

- **T1** authentication — OUT OF SCOPE by operator ruling
- **T7** Python dependency scanning — **NOT IMPLEMENTED** (P2-1/P2-2)
- **T10** model-output validation — **NOT IMPLEMENTED**, operator review is the control
- **T12** audit logging and observability — **NOT IMPLEMENTED** (P4-3, P4-6)

No third-party security audit or penetration test has been performed on this release.
