# SWS-CORRECTIVE-01 — the candidate, its artifacts, and the gate record

**Run ID:** `SWS-CORRECTIVE-01-20260908T151625Z`
**Host:** Windows 11 Home 10.0.26200 · PowerShell 5.1.26100.9168 · Python 3.12.10 / 3.14.6 · Node v24.20.0
**Executor model:** Opus 5 (`claude-opus-5`)

---

## 1. Candidate identity

| Field | Value |
|---|---|
| Build commit | `45751ac54363cf77ff8bc672eca7f375d42de9cb` |
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
| `sovereign-workspace-1.0.0-rc.1-source.zip` | 10564896 | `d611306be4979007cc037f1dcd5d05da338089a691fa16b3ad50f78fea34f6e8` |
| **`sovereign-workspace-1.0.0-rc.1-install.zip`** | **10640990** | **`5f45b35acd5791cd4bfc7122ede80bebb420e629ddb56a75d998d0b398c25953`** |
| `debate-v1.2.1-hardening-src.zip` | 192506 | `5f459f8591ccd4cbbe4e33c130d37cfe03ad59d99feddb0b0f614c88e590c18b` |
| `distillery-1.1.0rc3-src.zip` | 2203219 | `cfb52f64373dd1e227fe4f9a8b007320148a495ae11a9f36844efb420dd3cca5` |
| `shell-1.0.0-rc.1-src.zip` | 1759808 | `87574016b29eabacdda53beeaffa87273a86831ebb356f55bca9a7ae25ef3730` |
| `sovereign-SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520-src.zip` | 507753 | `938d2d412aee2702a2a6850756abb35ef80bef8f50c688b0574ffb8b40387daf` |
| `sow-0.1.0-src.zip` | 5157178 | `af58c967210719f2cdbff34882573a835ed32df9427039821aaaf3e0d1e1ab06` |
| `tokencenter-record-dated-2026-08-26-src.zip` | 389079 | `3e4e429590bb573eed270440166360a400fe033ed7ed626750b6e410df7de78b` |

The install archive is the one the acceptance sequence consumes.

**Retained at** `%TEMP%\claude\D--production-software-3\<session>\scratchpad\artifacts\` — outside
Production Software 3, per the operator's instruction to keep build output out of the project
folder. They are reproducible from the commit at any time by the command above.

## 3. Reproducibility — two isolated builds (§5.8)

The build was run twice into two separate output directories from the same commit — `0761d756`,
an earlier candidate in this run. All **eight** artifacts were **byte-identical**, sizes and
SHA-256 both:

```
build 1 -> ...\scratchpad\artifacts
build 2 -> ...\scratchpad\artifacts2
8 of 8 artifacts identical
```

The final candidate `45751ac` was then built once more, into a third directory, and those are the
hashes tabulated above. Stated precisely: the **double build was run on `0761d756`**, not
re-demonstrated on `45751ac`. Reproducibility is a property of the producer and the producer did
not change between them, but the measurement belongs to the commit it was taken on.

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

Every gate run against the candidate, exit code recorded. The twelve below were also run as part
of the whole-suite invocation recorded in §4.1, and re-run individually against `45751ac`:

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

### 4.1 The whole-product run

`tools/ci/run_ci.ps1 -SkipNode`, executed on `0761d756`, 23m19s of pytest:

```
4247 passed, 3 failed, 5 skipped, 61 warnings, 495 subtests passed in 1399.13s
19 stage(s): 12 passed, 1 failed, 6 skipped
RELEASE-QUALIFYING: NO. This run does not qualify a release.
```

The combined Python run **finished**; it was not a subset. Its three failures were all this
work's own guards catching this work's own changes, and all three are fixed in `45751ac`:

| Failure | Cause | Fixed by |
|---|---|---|
| `test_no_operator_facing_document_carries_an_undocumented_absolute_path` | the launcher table I added to `OPERATIONS.md` named an absolute build path | `7f81559` — table rewritten generically |
| `test_no_operator_facing_document_names_a_build_tree` | the same table named `release-worktree`, a directory that exists only on this machine | `7f81559` — and `Start-Sovereign.ps1` now genuinely searches rather than hard-coding the name |
| `test_build_manifest_describes_the_tracked_tree` | commits landed after the manifest was last regenerated | `45751ac` — regenerated and re-pinned through the generators |

That third failure is the R2 guard doing exactly its job: it detected the drift the old design
could not, one commit after it appeared, instead of the drift sitting undetected across two
commits and a release.

**Stages that did not run, and what that means.** `-SkipNode` was passed and `-IncludeCleanRoom`
was not, so six stages were SKIPPED with their reasons recorded. The summary consequently reports
**RELEASE-QUALIFYING: NO**, which is the correct and intended behaviour: a release-required stage
that did not run prevents qualification even though the developer run itself is useful. The
clean-room install was instead performed separately and is recorded in `../04-acceptance/`.

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
