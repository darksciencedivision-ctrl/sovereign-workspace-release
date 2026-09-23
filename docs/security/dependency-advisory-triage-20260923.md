# Dependency advisory triage (SW-23)

- **Date:** 2026-09-23
- **Scope:** Python dependency pins for the shipped modules. Node audits were clean and are
  not repeated here.
- **Method:** every declared/locked pin was reconciled against the version actually installed
  in each module venv; each advisory was looked up in the OSV database
  (`https://api.osv.dev/v1/vulns/<GHSA-ID>`) for its affected range and whether a fixed version
  is published; reachability was judged against how the product actually uses the package.
- **Verdict:** no advisory is reachable as the product is built and run today. One safe,
  operator-gated version bump is recommended (`anyio` in the Debate lock); everything else is
  either already at or above the fix floor, or has no published fix and is unreachable behind a
  documented compensating boundary.

This file is the dated inventory + advisory disposition the SW-23 close-condition asks for. A
machine-checkable guard for the dispositions below lives in
`modules/sow/tests/remediation/test_sw23_dependency_boundaries.py`.

---

## 1. Inventory (as of 2026-09-23)

| Package  | Module     | Declared / locked        | Installed in venv | Notes |
|----------|------------|--------------------------|-------------------|-------|
| chromadb | sovereign  | `1.5.9` (req + lock)     | `1.5.9`           | lock == installed |
| anyio    | sovereign  | `4.15.1` (lock)          | `4.14.2`          | **installed drifts below lock**; both >= fix floor 4.14.2 |
| anyio    | debate     | `4.14.1` (lock)          | `4.14.1`          | **below fix floor 4.14.2** (transitive via fastapi/uvicorn/httpx) |

`anyio` is not imported directly anywhere in the product source (`grep -rn "import anyio"` over
module source is empty); it is pulled in transitively by FastAPI / Starlette / Uvicorn / httpx.

## 2. chromadb advisories (4) - no published fix, server-mode only, not reachable

The product's ONLY use of chromadb is a local embedded client in
`modules/sovereign/praxis/praxis_commit.py`:

```python
client = chromadb.PersistentClient(path=DB_DIR)
```

There is no `chromadb.HttpClient`, no Chroma server process, no `chroma run`, no HTTP listener,
and no authorization provider or tenant layer anywhere in the source. All four advisories require
Chroma's **server / HTTP API + auth/tenant** stack, which this product never instantiates.

| GHSA | Affected | Fixed version | Requires | Reachable here? |
|------|----------|---------------|----------|-----------------|
| GHSA-f4j7-r4q5-qw2c | 1.0.0-1.5.9 | **none published** | pre-auth RCE via `trust_remote_code` on the collections HTTP endpoint | No - no server/HTTP endpoint |
| GHSA-36p7-vc44-83pf | 0.4.17-1.5.9 | **none published** | authenticated RCE via the collection-update endpoint (UPDATE_COLLECTION perm) | No - no server, no permission model |
| GHSA-2wm9-hf6c-p5cr | 0.4.17-1.5.9 | **none published** | cross-tenant read/write for authenticated users | No - single-process embedded client has no tenants |
| GHSA-xph7-9rjv-w5fr (CVE-2026-45831) | 0.5.0-1.5.9 | **none published** | `SimpleRBACAuthorizationProvider` scope-check bypass | No - the RBAC provider is only constructed by the server |

**Disposition: ACCEPT with compensating boundary.** No safe version exists to bump to (every
release through 1.5.9 is affected and no patched release is published), so the finding's rule
"do not invent a safe version where none is published" applies. The compensating boundary is
that the vulnerable surface (the Chroma server, its HTTP API, and its auth/tenant layer) is never
started: chromadb is used purely as a local, single-process, on-disk `PersistentClient` reached
by no network socket. The regression guard test asserts the source constructs no server/HTTP
client, so a future change that reintroduced server mode would fail the gate and force a
re-triage.

## 3. anyio advisories (3) - all fixed in 4.14.2

| GHSA | Affected | Fixed version | Trigger condition | Reachable here? |
|------|----------|---------------|-------------------|-----------------|
| GHSA-3w57-8xmc-8v26 | 4.14.0-4.14.1 | **4.14.2** | POSIX supplementary-group handling in `run_process`/`open_process` | No - Windows host, no direct anyio subprocess use |
| GHSA-5p39-cfhj-2xmp | <4.14.2 | **4.14.2** | process-pool worker stderr deadlock under untrusted code | No - product does not run untrusted code in an anyio process pool |
| GHSA-82r6-8w77-94w6 | <4.14.2 | **4.14.2** | TLS cert spoofing needing a non-ASCII IDN host + a hijacked connection | Very low - outbound TLS targets are ASCII API hostnames |

**Disposition: PATCH (safe bump exists).** All three are fixed in `anyio==4.14.2`, a same-line
patch release with no API change.

- **sovereign** already satisfies the floor: lock `4.15.1`, installed `4.14.2` - both >= 4.14.2.
  The installed-below-lock drift (4.14.2 vs 4.15.1) is a provisioning-integrity nit (re-provision
  to match the lock), not a security gap; both are at or above the fix.
- **debate** lock pins `4.14.1`, one patch below the fix. This is the single actionable security
  item. Recommended change (see below).

## 4. Recommended actions (operator-gated version decision)

1. **Bump the Debate `anyio` pin to `>=4.14.2`.** Edit `modules/debate/requirements.lock.txt`
   line 27 from `anyio==4.14.1` to `anyio==4.14.2` (or `4.15.1`, matching sovereign) and
   regenerate the `--hash=` lines with the module's lock tooling (do not hand-write hashes).
   Then re-provision the Debate venv. This clears all three anyio advisories for Debate.
2. **Reconcile the sovereign `anyio` drift** by re-provisioning the sovereign venv so the
   installed version matches the lock (`4.15.1`). No security change (both are >= 4.14.2); this is
   provisioning hygiene (see SW-03/04).
3. **chromadb: no change.** Keep `1.5.9` and the local-PersistentClient boundary. Re-triage only
   if (a) a patched chromadb release is published, or (b) the product ever adopts Chroma server
   mode - the regression test in this pack will force the latter to surface.

## 5. Re-scanning

To repeat this scan against the release locks:

```bash
# per GHSA id
curl -s https://api.osv.dev/v1/vulns/<GHSA-ID>
# or query by package+version
curl -s -X POST https://api.osv.dev/v1/query \
  -d '{"package":{"name":"chromadb","ecosystem":"PyPI"},"version":"1.5.9"}'
```

A repeat scan should surface exactly the seven advisories dispositioned above; any additional
finding is unexplained and must be triaged before release.
