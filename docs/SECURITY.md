# Security

**Version 1.0.0-rc.1** · EPC-01 P4-9

What this release protects, what it does not, and what was measured rather than assumed.

Read `docs/LIMITATIONS.md` alongside this. The four largest facts about this product's
security posture are limitations, not features, and they are stated there.

---

## The security model in one paragraph

**The machine is the boundary.** Sovereign Workspace is a single-operator local product. It
binds loopback only, authenticates nobody, and grants whoever can reach it the operator's full
authority. Anyone with an account on the host, or any process running as the operator, has
complete access to the product and its data. If that is not acceptable for your use, no
configuration of this release will make it so.

---

## What is enforced, in code

These are properties the product actively maintains, not settings you can get wrong.

**Loopback-only binding.** `modules/sovereign/sovereign_product/server.py` refuses to bind a
non-loopback address — it raises rather than warning, and the check resolves the address
rather than matching a string.

**Path containment by canonical resolution.** `shell/src/adapter.py` resolves paths through
`GetFinalPathNameByHandleW`, so junctions, symlinks and 8.3 short names are resolved before
containment is decided. Prefix-string comparison is explicitly forbidden as the mechanism.
UNC and device paths are rejected on the raw input, before normalisation can hide them.

**Archive extraction refuses to escape.** The installer rejects any archive entry whose
resolved destination falls outside the install root, and refuses a filesystem-root or
non-empty destination.

**Artifact hash verification before use.** The installer verifies the install archive against
its sidecar before reading its contents, and Electron is provisioned from a **hash-verified**
zip rather than by an unverified postinstall download (`docs/ADR-005-...`).

**Process containment.** Modules launch inside Windows Job Objects with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, including grandchildren that attempt breakaway.

**Origin and CSRF checks on the shell.** `Host` and `Origin` are exact-matched on every
state-changing request, with no CORS headers, and a per-instance CSRF nonce is served only in
the shell's own HTML.

**Secret redaction before buffering.** Process output is redacted before it reaches any
buffer, response or file.

**Live provider operation is denied by absence.** The configuration that authorizes spending
against a frontier provider subscription is gitignored, untracked, and absent from the
distribution. A fresh install cannot make a billable call until an operator deliberately
creates it. The test suite additionally installs a guard that raises if any test tries to
spawn a live provider CLI.

---

## What is not protected

Restating the essentials from `docs/LIMITATIONS.md`, because a security document that omits
them is misleading:

- **No authentication.** No login, no session, no API key.
- **No authorization or roles.** No user model, so no privilege boundaries.
- **No security audit log.** The gate ledger records build events, not runtime actions by a
  person — there is no "who" to record.
- **No multi-user isolation.** Single operator by construction.
- **No telemetry**, which also means no security-advisory notification: checking for updates
  is your responsibility (`docs/ADR-006-no-telemetry.md`).

---

## What was measured for this release

Stated as measurements, with their result, so the claims are checkable:

**No live credential ships.** The distributed archive was extracted and swept for private key
blocks, provider API keys, GitHub and Slack tokens, AWS access-key ids, and secret-shaped
assignments. Every hit is a declared detector fixture — the recurring one is a synthetic
placeholder registered in `modules/distillery/tools/export_enterprise.py` as
`DECLARED_FIXTURE_SECRETS`, and the others are self-evidently non-secrets used to test the
detectors. **No live credential is present.**

*(This paragraph deliberately does not quote the fixture value. It is credential-shaped by
design, and reproducing it here would make this document itself a finding in the packaging
gate — which is exactly what happened when it was first written.)*

**No known advisory ships in a Node dependency.** `npm audit` runs against both Node trees
with a threshold of zero, as release gate `tools/release/check_node_advisories.py`. Both are
clean. One HIGH advisory (`nanoid`, GHSA-2v37-7h3g-55p8) was found and closed during this
programme; it had sat in the lockfile through an entire release cycle because the audit was
not a gate.

**The packaging boundary holds on the distribution.** `package_boundary_gate --from-commit`
scans the archive for user state, databases, env files, key material, logs, runtime session
state and credential patterns. Zero violations, zero credential hits.

**Third-party components are enumerated.** `NOTICE` covers all 304 library components with
zero unresolved licences, generated from the SBOM rather than maintained by hand.

---

## What was NOT tested

Named so absence is not read as assurance:

- **No third-party security audit or penetration test.**
- **No clean-room install on a bare machine** — the install path is exercised against a fresh
  destination on a developer host only.
- **The SBOM cannot be used for Python vulnerability scanning.** It is generated from the
  build machine's virtual environments and its own metadata marks Python coverage
  `partial-parked` and `missing-parked`. Tracked as P2-1/P2-2. `npm audit` covers the Node
  side properly; the Python side has no equivalent in this release.
- **Nineteen of twenty-nine assurance gates have never been reviewed by anyone**
  (`docs/RELEASE-ASSURANCE.md`).

---

## Reporting a security issue

There is no security contact process, no advisory feed and no coordinated disclosure policy
for this release. Report to whoever provided the build, and include the seal commit from
`RELEASE-MANIFEST.json`. See `docs/SUPPORT-POLICY.md` for what is promised in return, which
is deliberately little.
