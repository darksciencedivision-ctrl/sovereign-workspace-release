# utc: 2026-08-21T04:42:27.9151051Z
# producer: claude-code REM-01

# ADR-005 — SOW install and Electron binary provisioning

Status: proposed by builder (REM-01 R2-1). Supersedes nothing. Required by BUILD-DIRECTIVE §6
("native-build steps get an ADR with the captured build log") and by REVIEW-BUILD-01 B-4.

## Context

The SOW module (`modules/sow`) is an Electron desktop application. Under BUILD-DIRECTIVE §6 the
workspace owns its own runtime instance (Option A), so `node_modules` must be provisioned inside
`Production Workspace\modules\sow\apps\desktop\`.

Everything below was measured on this host at the `# utc:` above, not recalled.

### Toolchain observed

FACT[host] `node --version` → `v24.16.0`, resolved to `D:\Program Files\nodejs\node.exe`.
FACT[host] `npm --version` → `11.17.0`.
FACT[host] `npm config get ignore-scripts` → `false`. Lifecycle scripts are **not** disabled by
npm's own configuration on this host.
FACT[host] `npm config get foreground-scripts` → `false`.
FACT[host] Two `npm-cli.js` entry points exist, and **they are different npm versions**:
`D:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js` (56 bytes) reports `11.13.0`, while
`C:\Users\Sslaw\AppData\Roaming\npm\node_modules\npm\bin\npm-cli.js` (54 bytes) is the one the
bare `npm` shim on PATH resolves to and reports `11.17.0`. `shell/tools/install_sow.py` computes
the first — the one under the resolved `node.exe` directory — because R2-2 specifies
`<node dir>\node_modules\npm\bin\npm-cli.js`.

INTERPRETATION: the install is therefore performed by npm **11.13.0**, not by the 11.17.0 that a
human typing `npm` at a prompt would get. Both are npm 11 and both honour `ci --ignore-scripts`
identically, and the run captured in `evidence/phase2-sow-install.txt` succeeded, so this is
recorded as a fact rather than treated as a defect. It is worth a reviewer's attention because
"npm 11" is not a single artifact on this host.

INTERPRETATION: CLAUDE.md records "lifecycle scripts blocked by default (see ADR-005)". As
observed, npm's `ignore-scripts` is `false`, so that phrasing does not describe an npm default on
this host. What is true is the decision below: this workspace **chooses** `--ignore-scripts`. The
prior builder's account (REVIEW-BUILD-01 B-4) that npm "blocked" the scripts is not reproduced
here and is not relied on. Whatever happened in that session, the provisioning path this ADR
adopts does not depend on it, because it never asks a lifecycle script to do the work.

### What `electron`'s postinstall would otherwise do

FACT[modules/sow/apps/desktop/node_modules/electron/package.json] `"scripts": { "postinstall":
"node install.js" }`, `"version": "31.7.7"`.
FACT[modules/sow/apps/desktop/node_modules/electron/install.js] present, 3170 bytes. It is the
step that downloads and extracts the platform binary into `dist/`.

INTERPRETATION: with `--ignore-scripts`, `install.js` never runs, so `dist/` is empty and
`path.txt` is absent after `npm ci`. Any adapter whose `argv[0]` is
`node_modules/electron/dist/electron.exe` then fails at spawn. The binary must therefore be
provisioned by an explicit, logged, hash-verified step — which is the whole point of this ADR.

### Current on-disk state

FACT[modules/sow/apps/desktop/package-lock.json] Present, 32857 bytes. A valid lockfile exists,
so `npm ci` is the correct command and BUILD-DIRECTIVE §6's `npm install` carve-out ("only if no
valid lockfile exists, with ADR") does **not** apply.

FACT[modules/sow/apps/desktop/node_modules/electron/dist/version] contains `v31.7.7`.
FACT[modules/sow/apps/desktop/node_modules/electron/path.txt] contains `electron.exe`.
FACT[modules/sow/apps/desktop/node_modules/electron/dist/electron.exe]
size `180849664` bytes,
sha256 `1fa93c3471c11dc8128998c662c705104e4528b98901b61c8a25216acda424c5`.

FACT[C:\Users\Sslaw\AppData\Local\electron\Cache] Three cache entries exist. The one matching the
installed version is
`C:\Users\Sslaw\AppData\Local\electron\Cache\c94f2fc32e1fb05767f75322ea533eeb9828155f017ec184140930a3ec825e81\electron-v31.7.7-win32-x64.zip`,
size `110740332` bytes,
sha256 `e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f`.
(The other two entries are v40.10.2 and v40.10.6, unrelated to this module.)

FACT — the zip hash is corroborated by **two independent records**, neither written by this builder:

1. `C:\Users\Sslaw\AppData\Local\electron\Cache\c94f2fc32e1fb05767f75322ea533eeb9828155f017ec184140930a3ec825e81\SHASUMS256.txt`
   line: `e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f *electron-v31.7.7-win32-x64.zip`
2. `modules/sow/apps/desktop/node_modules/electron/checksums.json`, shipped inside the npm
   registry tarball, key `electron-v31.7.7-win32-x64.zip` →
   `e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f`

INTERPRETATION: this is stronger than a self-recorded first-run hash. The expected value is
readable from the package the lockfile pins, so a fresh machine can verify the download without
trusting any artifact this workspace produced.

FACT[modules/sow/apps/desktop/node_modules/node-pty] version `1.1.0`. Prebuilds ship for
`darwin-arm64`, `darwin-x64`, `win32-arm64`, `win32-x64`. `prebuilds/win32-x64/` contains
`pty.node` (303104 B), `conpty.node` (312320 B), `conpty_console_list.node` (134656 B),
`winpty.dll`, `winpty-agent.exe`, and the matching `.pdb` files.
FACT[host] `node.exe -e "require('node-pty')"` succeeds and exports
`spawn,fork,createTerminal,open,native`. The prebuild loads; no compilation is required.

FACT[host, CLAUDE.md] No Windows SDK is installed, so `node-gyp` cannot build native modules.
This is why the prebuild path matters: if lifecycle scripts ran and `node-pty` fell back to a
source build, it would fail. `--ignore-scripts` avoids that failure mode as well.

## Decision

1. **`npm ci --ignore-scripts`** is the only dependency-installation command. It is invoked as
   `[node.exe, <node dir>\node_modules\npm\bin\npm-cli.js, "ci", "--ignore-scripts"]`. Never
   `npm.cmd`, never a shell — BUILD-DIRECTIVE A-14 and the `.cmd`/`.bat` prohibition apply to
   tooling as well as to launch vectors.
2. **Electron's binary is provisioned explicitly**, not by `postinstall`. The version is read from
   `node_modules/electron/package.json`. The expected zip SHA-256 is read from
   `node_modules/electron/checksums.json` — the package's own record — with
   `docs/ADR-005-ELECTRON-ZIP-SHA256.txt` as a workspace-local fallback record if the key is
   absent. The zip is used from `%LOCALAPPDATA%\electron\Cache\**\electron-v<ver>-win32-x64.zip`
   when a cached copy matches that hash, and downloaded from the official release URL otherwise.
   A hash mismatch is fatal: the script exits non-zero and writes nothing.
3. **`dist/` is populated by extraction from the verified zip**, then `path.txt` is written with
   the literal `electron.exe` and `dist/version` with `v<version>`, matching what `install.js`
   would have produced.
4. **`node-pty` is verified, never built.** After install, `[node.exe, "-e", "require('node-pty')"]`
   must succeed and `prebuilds/win32-x64/` must contain at least one `.node`. Failure is fatal.
5. **Every step is logged** to `evidence/phase2-sow-install.txt` with the `# utc:` /
   `# producer:` headers, and the script exits non-zero on any mismatch.
6. The implementation is `shell/tools/install_sow.py`, Python stdlib only, run with `py -3.12`.
   The README calls it. PowerShell is not used, so the single "no `.cmd`/`.bat`/PowerShell launch"
   rule covers tooling and runtime alike.

## Alternatives considered

**A. Let `postinstall` run (`npm ci` without `--ignore-scripts`).** Rejected. It executes arbitrary
vendor code from every transitive package at install time, and on this host it also exposes
`node-pty` to a `node-gyp` path that cannot succeed (no Windows SDK). It additionally makes the
Electron download unverifiable from the workspace's own evidence — the hash check would live
inside vendor code, not in a logged step.

**B. `npm install --foreground-scripts` (what the prior session did).** Rejected. It is the
`npm install` path BUILD-DIRECTIVE §6 permits only when no lockfile exists; a lockfile does exist.
It can also rewrite `package-lock.json`, which changes the pinned dependency set as a side effect
of an install.

**C. Commit the extracted `dist/` into the workspace.** Rejected. ~180 MB of vendor binary inside a
directory that is manifest-hashed, for no reproducibility gain over a verified zip extraction.

**D. Manual `Expand-Archive` plus hand-written `path.txt` (the state found on disk).** Rejected as
a *procedure*, though its end state is what the disk currently holds. It is unlogged, unverified,
and absent from the README, so a reader following the README reproduces the empty `dist/` rather
than the working tree — exactly REVIEW-BUILD-01 B-4.

## Consequences

- The install is reproducible from the README on a clean extraction, with a hash gate on the one
  large binary that is not covered by `package-lock.json`.
- Lifecycle scripts never run for this module. If a future dependency genuinely requires its
  postinstall, this ADR must be revisited — it will fail loudly (missing artifact) rather than
  silently.
- The first run on a machine with no cached zip performs a ~110 MB download from
  `https://github.com/electron/electron/releases/download/v31.7.7/`. That is a network dependency
  of the *install* step only, never of the *run* or *test* steps.
- `node-pty` is used exclusively from prebuilds. An architecture without a shipped prebuild
  (nothing this host will hit — `win32-x64`) would fail the verification step rather than attempt
  a build that cannot succeed.
- The expected-hash source is the npm package itself. If a future `electron` release ships a
  `checksums.json` without the platform key, the script falls back to the recorded value in
  `docs/ADR-005-ELECTRON-ZIP-SHA256.txt` and, on a first run with neither, records the observed
  hash there and says so in the log.

## Evidence

- `evidence/phase2-sow-install.txt` — full captured log of the `shell/tools/install_sow.py` run
  described here.
- `shell/tools/install_sow.py` — the implementation.
- `modules/sow/INSTALL-PROVENANCE.json` — carries `electron_zip_sha256`
  (`e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f`) and the `electron.exe` hash.
- `modules/sow/apps/desktop/node_modules/electron/checksums.json` — vendor-shipped expected hash.
- `C:\Users\Sslaw\AppData\Local\electron\Cache\c94f2fc32e1fb05767f75322ea533eeb9828155f017ec184140930a3ec825e81\SHASUMS256.txt`
  — upstream release manifest, second corroboration.

### Result of the run this ADR documents

FACT[evidence/phase2-sow-install.txt] `py -3.12 shell\tools\install_sow.py` completed with all
eight steps verified. `npm ci --ignore-scripts` exited 0 ("added 75 packages, and audited 76
packages"), the cached zip matched `checksums.json` on the first candidate, 73 entries extracted,
and `require('node-pty')` succeeded.

FACT — the automated path reproduces the hand-made state exactly. `electron.exe` after scripted
extraction hashes to `1fa93c3471c11dc8128998c662c705104e4528b98901b61c8a25216acda424c5`, the same
value measured on the prior builder's manually extracted copy before this run. The end state
REVIEW-BUILD-01 B-4 called "probably fine" is confirmed byte-identical to the reproducible one.

FACT[evidence/phase2-sow-install.txt] `npm ci` reported "2 high severity vulnerabilities" and one
deprecation warning (`boolean@3.2.0`). No `npm audit fix` was run: it would rewrite
`package-lock.json`, changing the pinned dependency set, which is outside REM-01's scope and
outside §0.1(8). Recorded here as a finding for the operator, not acted on.

Reversible: yes — deleting `modules/sow/apps/desktop/node_modules/` and re-running
`py -3.12 shell\tools\install_sow.py` restores the same state; the cached zip and its expected
hash are both outside this decision's control.
