# Release checklist

For the operator cutting a release of the workspace from `remediation/p1` after the
`feature/sharded-inference` and `product/completion` PRs are merged. Work top to bottom. Every
check here is read-only unless it says otherwise.

## 1. The tree is the one you mean to ship

- [ ] `git status` is clean, and `git log -1` is the merge commit you are releasing.
- [ ] `git ls-files --eol | Select-String 'i/crlf|i/mixed'` prints nothing (LF in the index,
      F-074). A few working copies may be CRLF (`w/crlf`); the index bytes are what ships.
- [ ] No `__pycache__` or `.pyc` files are tracked (`git ls-files | Select-String __pycache__`).

## 2. Gates, on that exact commit

```powershell
cd "<repo>\modules\sow"
$env:PYTHONDONTWRITEBYTECODE = "1"
..\sovereign\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider
cd "<repo>\modules\sovereign\ui\ui_shell"
npm run typecheck
npx vitest run tests/remediation
npm run build
powershell -NoProfile -ExecutionPolicy Bypass -File "<repo>\tools\cleanroom\Test-CleanRoomBoot.ps1" -Live
```

- [ ] Suite: all passed. UI: typecheck, vitest and build are clean.
- [ ] Clean-room gate prints `RESULT: PASS` and exits 0.

## 3. Release identity files (stale: regenerate, or record them as manual)

A check on 2026-09-28 found these out of date against the tree:

| File | State on 2026-09-28 | How it is produced |
|---|---|---|
| `shell/BUILD-MANIFEST.txt` | 107 of 119 hashes differ (last generated 2026-09-14) | `generate_build_manifest --write`, from the release tooling used for CLOSE-04 (`21f8d47`). **Not in this repository.** |
| `modules/debate/MANIFEST-SHA256.json` | 28 of 51 files differ | The debate packaging step (see `modules/debate/PRODUCTION-README.md`). **No generator in this repository.** |
| `modules/debate/snapshot/ENVIRONMENT.json` | Captured 2026-08-08 | `modules/debate/scripts/capture_environment.py`. It is in the repo, but it also REWRITES `requirements.lock.txt`: run it only with debate's own 3.14 venv, then review the lock diff. |
| `VERSION.json`, `modules/*/INSTALL-PROVENANCE.json`, `RELEASE-MANIFEST.json` | Pinned to earlier commits | `generate_module_provenance`, `sync_release_manifest` (release tooling). **Not in this repository.** |

Rules:
- Never hand-edit a hash or a pin.
- If you have the release tooling, regenerate in dependency order (sources, then locks, then
  provenance, then the build manifest, then the release manifest), and review each diff.
- If you do not, ship with these files recorded as **stale** in the release notes. Do not "fix"
  them by hand.

Read-only check of the two manifests (prints mismatch counts):

```powershell
cd "<repo>"
python -c "import hashlib,pathlib; r=pathlib.Path('shell'); rows=[l.split('  ',1) for l in (r/'BUILD-MANIFEST.txt').read_text(encoding='utf-8').splitlines() if l and not l.startswith('#')]; bad=[p for d,p in rows if not (r/p).is_file() or hashlib.sha256((r/p).read_bytes()).hexdigest()!=d]; print(len(rows),'entries',len(bad),'mismatches')"
cd modules\debate
python -c "import hashlib,json,pathlib; r=pathlib.Path('.'); m=json.loads((r/'MANIFEST-SHA256.json').read_text(encoding='utf-8')); bad=[e['path'] for e in m['files'] if not (r/e['path']).is_file() or hashlib.sha256((r/e['path']).read_bytes()).hexdigest()!=e['sha256']]; print(len(m['files']),'files',len(bad),'mismatches')"
```

## 4. Version bump plan (3.1.2 -> 3.2.0)

This release adds the LONG route (sharded inference), restart resume, the resume endpoint and the
state prune. That is a feature release: **3.2.0** is proposed; the operator decides.

The version is set in these places. Change them together, in one commit:

| File | Field |
|---|---|
| `modules/sovereign/sovereign_version.py` | `PRODUCT_VERSION`, `PEP440_VERSION` (the authority: `/v1/health` reports it, and the UI reads it from there) |
| `modules/sovereign/ui/ui_shell/package.json` | `version` (and its `package-lock.json` entry, through `npm version 3.2.0 --no-git-tag-version`) |
| `modules/sovereign/SYSTEM_MANIFEST.json` | `ARCHIVE_VERSION` |
| `modules/sovereign/runtime_profile.json` | `schema_version`, `product_version` |
| `modules/sovereign/PACKAGE_MANIFEST.txt` | the version line |
| `VERSION.json` | `modules.sovereign` (a description string) |

Then (the bump itself was not run here; this is the plan):
- [ ] `git grep -n "3\.1\.2"` shows only history (STATUS.md, README_RUN.md, docs/performance).
- [ ] Run the gates again (section 2). `test_sw25d_state_version_backup.py` reads the version.

## 5. Live checks on the isolated stack (not the operator's real state)

- [ ] One job per route through the UI (STATUS, QUICK, CONTINUITY, DEEP, RESEARCH, LONG) completes.
- [ ] `/v1/health` reports `routes.LONG: true` and `long_route.status: "ready"`.
- [ ] After stopping: no `llama-server.exe` under the install tree, and nothing listening on
      :18080 or the product port.

## 6. Cut

- [ ] Tag the merge commit (`git tag -a v3.2.0 -m ...`) and push the tag.
- [ ] Release notes: what changed (the PR bodies), the known limits (docs/OPERATOR-GUIDE.md,
      "Known limits"), and the stale identity files from section 3, if they were not regenerated.
