# SWS-CORRECTIVE-01 — the candidate, its artifacts, and the gate record

**Run ID:** `SWS-CORRECTIVE-01-20260908T151625Z`
**Host:** Windows 11 Home 10.0.26200 · PowerShell 5.1.26100.9168 · Python 3.12.10 / 3.14.6 · Node v24.20.0
**Executor model:** Opus 5 (`claude-opus-5`)

---

## 1. Candidate identity

| Field | Value |
|---|---|
| Build commit | `0761d756dfb95d9acc7aa0218dbd828effd85a56` |
| Version | `1.0.0-rc.1` |
| Tracked tree at build | clean (`git status --porcelain --untracked-files=no` empty) |
| Reviewed baseline | `52bcc931e6ebb0db24155758cf19d1cf592731fa` |

The build refuses to run with tracked modifications, so the artifacts below correspond to exactly
this commit and nothing else.

## 2. Artifacts

Cut by `tools/release/build_release.ps1 -Commit HEAD`. Each carries a `.sha256` sidecar, and
`release-build-manifest.json` records the cut list.

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `sovereign-workspace-1.0.0-rc.1-source.zip` | 10563536 | `f15614222744758c48af3c7a13c28fc002acd05b1983a29925727d562b216dc3` |
| **`sovereign-workspace-1.0.0-rc.1-install.zip`** | **10639630** | **`4b14d525d23233880a2b3b5cb82589546b23f6703c16f1edeb500448be43177d`** |
| `debate-v1.2.1-hardening-src.zip` | 192506 | `ba10b890828e654209990dc87812ac95352db8384f6781d4be1e7b7c73062db9` |
| `distillery-1.1.0rc3-src.zip` | 2203219 | `3b97a61ae0fc68f02b0d0908d412ebc387277b20d13910962112ead60cfc21f7` |
| `shell-1.0.0-rc.1-src.zip` | 1759760 | `15daf4e3c45c6e5248fdcf34d6c26181e44e00505546aff726575ee8abff6bb3` |
| `sovereign-SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520-src.zip` | 506999 | `e112e99931d340e16515e48cc04c385306d799f44b8eeaa252175981c00bee47` |
| `sow-0.1.0-src.zip` | 5157178 | `85708d5cfbfd3a42dfe0375a93bcbec582c7fa92e4bc6e180f6f629e11cfeaaa` |
| `tokencenter-record-dated-2026-08-26-src.zip` | 389079 | `9f989228b43682fa526fca04258d132e30421606d2a76d03a289dede5067cb55` |

The install archive is the one the acceptance sequence consumes.

**Retained at** `%TEMP%\claude\D--production-software-3\<session>\scratchpad\artifacts\` — outside
Production Software 3, per the operator's instruction to keep build output out of the project
folder. They are reproducible from the commit at any time by the command above.

## 3. Reproducibility — two isolated builds (§5.8)

The build was run twice into two separate output directories from the same commit. All **eight**
artifacts were **byte-identical**, sizes and SHA-256 both:

```
build 1 -> ...\scratchpad\artifacts
build 2 -> ...\scratchpad\artifacts2
8 of 8 artifacts identical
```

`git archive` fixes entry timestamps from the commit rather than the clock, which is why whole-file
hashes reproduce rather than only content. `release-build-manifest.json` carries a UTC-free record;
it is untracked build output and excludes itself by construction.

**Stale-artifact negative control (executed).** A stranger `.zip` was planted in the output
directory and the build was re-run:

```
Output directory holds .zip file(s) this build did not cut: stale-leftover.zip.
They would otherwise be recorded as authoritative release bytes (OD-33).
EXIT=1
```

The producer refuses rather than adopting a file it did not cut.

## 4. Release gates — measured on this candidate

Every gate run against `0761d756`, exit code recorded:

| Gate | Result | Exit |
|---|---|---|
| `generate_build_manifest.py --check` | PASS | 0 |
| `sync_release_manifest.py --check` | PASS | 0 |
| `release_manifest_check.py` | PASS (0 problems) | 0 |
| `generate_model_projection.py --check` | PASS | 0 |
| `check_model_consistency.py` | PASS | 0 |
| `check_governance_bom.py` | PASS | 0 |
| `generate_sbom.py --check` | PASS (240 components match the locks) | 0 |
| `generate_notice.py --check` | PASS (NOTICE matches the SBOM) | 0 |
| `provenance_cross_hash_check.py` | PASS (5 modules) | 0 |
| `innerhtml_sink_audit.py` | PASS (39 templates, 112 interpolations) | 0 |
| `check_node_advisories.py` | PASS (2 roots, 0 advisories) | 0 |
| `package_boundary_gate.py --from-commit HEAD` | PASS (1647 files, 0 violations, 0 credential hits) | 0 |

R1 and R2 — the two gates the review recorded as FAILING — both pass on this candidate. Their
before/after is in `../01-baseline/REPRODUCTIONS.md`.

### Planted defects still fail (negative controls, executed)

Repairing a gate must not blunt it. Each of these was run and observed to fail:

| Control | Observed |
|---|---|
| a stranger `.zip` in the build output directory | build refuses, exit 1 |
| `shell/BUILD-MANIFEST.txt` enumerating an untracked file | `generate_build_manifest --check` names it and exits 1 |
| the BUILD-MANIFEST pin left stale in `RELEASE-MANIFEST.json` | `sync_release_manifest --check` reports the drift and exits 1 |
| a hand-authored file's hash changed | `sync --write` **refuses**; only `--repin <path> --reason` will move it |
| `model_hierarchy.json` with no `scope` | `check_model_consistency` fails |
| `model_hierarchy.json` claiming `configures: shipped-product` | fails |
| `scope.product_roster_source` naming the wrong file | fails |
| an empty model tag in the scoped roster | fails |
| a `sovereign_product` file resolving a role from the hierarchy | fails |
| a README bullet disagreeing with the manifest | fails |

The hierarchy controls are in `tools/release/test_check_model_consistency.py`; the single
equality control they replace was itself wrong in kind, and the replacement set is five controls
rather than one.

## 5. The tree is clean after verification (§5.3)

The defect R2 exposed was that running the tests mutated a tracked release input. After the
repair, a full `pytest shell/tests tools/release` run leaves:

```
git status --porcelain --untracked-files=no   ->   (empty)
```

`shell/BUILD-MANIFEST.txt` is no longer written by any test. The suite writes its run-stamped
copy to the gitignored `.runtime/` lane and *verifies* the tracked one instead.
