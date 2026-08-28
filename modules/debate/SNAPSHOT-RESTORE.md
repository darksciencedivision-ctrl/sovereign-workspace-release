# Debate Table — Cold Restore Runbook

**Snapshot:** `v1.2-phase1-baseline`
**Baseline commit:** `d03a1b7` — the engine (`app.py`, `debate/`, `static/`,
`config.json`) is byte-identical between that commit and the tagged one.
**Test suite at the snapshot:** 84 passed.

This is the document to follow on a machine that has never seen this project.
Every step below was executed on the machine that produced the snapshot; see
**§9 Known limitations** for exactly what that does and does not prove.

---

## 1. Prerequisites

| | Requirement | Notes |
|---|---|---|
| OS | Windows 10/11 | Verified on Windows 11 10.0.26200, AMD64. Linux/macOS untested — see §9 |
| Python | **3.14.6** | The only version the baseline was validated on. `README.md` claims 3.10+; that floor is plausible but **untested** — see §9 |
| Ollama | **0.32.6** or compatible | Must be running and reachable |
| Disk — code | ~25 MB | 6 MB tracked files, plus ~19 MB for the virtual environment |
| Disk — models | **16.80 GiB** | Two models. See §4 — you do **not** need the third |
| Download | ~16.8 GB | One-off, for the models |
| RAM / VRAM | Enough for a 14B Q4_K_M model | Two 14.7–14.8B models at Q4_K_M, ~8.4 GiB each on disk. They load one at a time, but Ollama may keep both resident |

If your GPU cannot hold a 14B model, Ollama will fall back to system RAM and turns
will be slow but functional. See §8 for using smaller models.

---

## 2. Restore the files

Two artifacts are produced; use either. Both live in `D:\debate-table-baselines\`
on the machine that made the snapshot — copy them to the target machine first.

### Option A — from the git bundle (keeps full history)

```powershell
git clone debate-table-v1.2-phase1-baseline.bundle debate-table
cd debate-table
git checkout v1.2-phase1-baseline
```

Verify the bundle before trusting it:

```powershell
git bundle verify debate-table-v1.2-phase1-baseline.bundle
```

> **Line endings.** Clone applies *your* machine's `core.autocrlf` setting, so a
> checkout may differ from the snapshot byte-for-byte while being identical in
> content. If you intend to verify against `snapshot/MANIFEST.json` (§3), clone
> with normalisation off:
> ```powershell
> git -c core.autocrlf=input clone debate-table-v1.2-phase1-baseline.bundle debate-table
> ```

### Option B — from the zip (no git required)

```powershell
Expand-Archive debate-table-v1.2-phase1-baseline.zip -DestinationPath debate-table
cd debate-table
```

The zip was deliberately produced with `-c core.autocrlf=input`, so its contents
match the `git_blob_sha256` values in the manifest exactly.

### Check the artifacts arrived intact

```powershell
Get-FileHash debate-table-v1.2-phase1-baseline.bundle -Algorithm SHA256
Get-FileHash debate-table-v1.2-phase1-baseline.zip    -Algorithm SHA256
```

Compare against `debate-table-v1.2-phase1-baseline.sha256`.

---

## 3. Verify integrity against the manifest

`snapshot/MANIFEST.json` lists all **145** files tracked at `d03a1b7`, each with
two hashes:

- **`git_blob_sha256`** — the canonical, platform-independent content hash.
  **Use this one.** It is what the zip and a normalised clone will match.
- `sha256` — the bytes as they sat on the snapshot machine's disk, paired with
  `mtime`. Useful for forensics, **not** for verifying a restore: 25 of the 145
  files carry CRLF there and will not match a fresh checkout.

```powershell
python -c @"
import hashlib, json, pathlib, sys
entries = json.loads(pathlib.Path('snapshot/MANIFEST.json').read_text(encoding='utf-8'))
bad = []
for e in entries:
    p = pathlib.Path(e['path'])
    if not p.exists():
        bad.append((e['path'], 'missing')); continue
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() == e['git_blob_sha256']:
        continue
    # tolerate line-ending translation applied by your git checkout
    if hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest() == e['git_blob_sha256']:
        continue
    bad.append((e['path'], 'hash mismatch'))
print(f'checked {len(entries)} files, {len(bad)} problems')
for b in bad: print('  ', *b)
sys.exit(1 if bad else 0)
"@
```

### Expect exactly three mismatches — this is correct, not corruption

Run against the tagged tree, the check above reports:

```
checked 145 files, 3 problems
   .claude/launch.json hash mismatch
   .gitignore hash mismatch
   README.md hash mismatch
```

**This is the expected result.** The manifest describes `d03a1b7`. Those three
files were then deliberately changed by the snapshot's portability remediation —
they are the entire §0.4 allowlist — to remove the hardcoded
`C:\Python314\python.exe` and `D:\Debate table\` paths that would have made this
restore impossible. Anything *else* in the list is a real problem.

Verify the three against their post-remediation hashes instead:

| File | sha256 at `d03a1b7` | sha256 at the tag |
|---|---|---|
| `.claude/launch.json` | `64af3c8f…e31d` | `c2e6af33f05c1a07354d34234e3a031261d3d48765975f6b7681a6ee05032060` |
| `.gitignore` | `d10b3260…c930d` | `59d3aae2a7b6ae6ea2f983b1b2253cb1d093e2ee60d4a9bded4bdc12cad684dd` |
| `README.md` | `f79a5cea…3d52` | `b4169887572e44d52e7017c4cccc89d5eda8b4f1dc9e0348591164f170565702` |

The **engine** — `app.py`, `debate/`, `static/`, `config.json` — is byte-identical
between `d03a1b7` and the tag, and must verify clean. If any engine file appears
in the mismatch list, the restore is not faithful; stop and re-extract.

> Files added *after* `d03a1b7` — the snapshot artifacts themselves, the bootstrap
> scripts, the lockfile, and this runbook — are intentionally **not** in the
> manifest. The manifest describes the baseline, not the snapshot of it.

---

## 4. Get the models

**Do not skip the size check.** These are large downloads.

Two models are required. Run these yourself:

```powershell
ollama pull phi4:14b
ollama pull qwen2.5:14b-instruct
```

| Model | Seat | Digest (confirm you got the same weights) | Size |
|---|---|---|---|
| `phi4:14b` | Neo | `ac896e5b8b34a1f4efa7b14d7520725140d5512484457fab45d2a4ea14c69dba` | 8.43 GiB |
| `qwen2.5:14b-instruct` | Clue | `7cdf5a0187d5c58cc5d369b255592f7841d1c4696d45a8c8a9489440385b22f6` | 8.37 GiB |
| | | **Total** | **16.80 GiB** |

Confirm the digests match:

```powershell
ollama list
```

The short IDs shown (`ac896e5b8b34`, `7cdf5a0187d5`) are the first 12 characters of
the digests above. Full digests are in `snapshot/MODELS.json`.

### The third model is optional and you probably do not need it

`config.json` also names `dolphin-llama3:8b` as `extractor_model`. **It is never
contacted in the default configuration.** `config.json` sets `insight_panel: false`,
and `app.py:952-958` only constructs the insight manager when that flag is true;
every consumer is guarded on the resulting `None`.

Pull it **only** if you intend to set `insight_panel: true` — which also requires
restarting the app, since the manager is bound once at import:

```powershell
ollama pull dolphin-llama3:8b   # +4.34 GiB, optional
```

Digest: `613f068e29f863bb900e568f920401b42678efca873d7a7c87b0d6ef4945fadd`.

---

## 5. Install and check — the easy path

From the project root:

```powershell
.\scripts\bootstrap.ps1
```

On Linux or macOS:

```bash
sh scripts/bootstrap.sh
```

It checks the Python version, creates `.venv`, installs the pinned dependencies
plus pytest, then checks that Ollama responds and that each model named in
`config.json` is present.

**It never installs a model and never edits `config.json`.** If a model is missing
it prints the exact `ollama pull` command and exits 1; you run it yourself.

Expected output ends with:

```
BOOTSTRAP OK
```

### Or do it by hand

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install pytest
```

`requirements.lock.txt` pins the exact 22 distributions the baseline was validated
against. `requirements.txt` is the human-facing declaration and pins nothing — use
the lockfile for a faithful restore.

**pytest is intentionally not in either file.** It is a development-only tool
(`README.md`), so it must be installed as its own step. A venv built from the
lockfile alone cannot run the test suite.

---

## 6. Self-check

```powershell
.venv\Scripts\python.exe -m pytest tests -q -W error
```

**Expected: `84 passed`.**

The suite is offline: it starts a deterministic local Ollama-compatible mock, uses
temporary configs under `tests/`, never calls real Ollama, and verifies that your
production `config.json` is left unchanged. A green run here means the code is
intact and the environment is correct — it does **not** exercise the models.

If this fails, stop and resolve it before starting the app.

---

## 7. Start the app

```powershell
.venv\Scripts\python.exe app.py
```

Then open **http://127.0.0.1:8700**

Stop it with **Ctrl+C** in the same terminal.

- The port comes from `config.json` → `port`.
- The app binds **`127.0.0.1` only** (`app.py:1522`) and is reachable **only from
  this machine**. This is deliberate: the app exposes an unauthenticated operator
  API that rewrites `config.json` and swaps models. To reach it from another
  device, put a reverse proxy in front of it rather than changing the bind address.
- Press **`C`** to open the hidden operator drawer. Do not press it in a browser
  being captured by OBS unless you intend to expose the controls.
- The first turn is slow: Ollama has to load a ~8.4 GiB model.

---

## 8. If your model names differ

Edit `config.json`. Two seats are defined under `seats`; each needs a `model` that
`ollama list` shows on your machine:

```json
"seats": [
  { "name": "Neo",  "model": "phi4:14b",             "color": "#4fd1ff", "persona": "...", "thesis": "..." },
  { "name": "Clue", "model": "qwen2.5:14b-instruct", "color": "#7dffa0", "persona": "...", "thesis": "..." }
]
```

Change only the `model` values. You can also change models live from the operator
drawer (press `C`), which writes `config.json` atomically and survives restart.

**Two, three or four seats are supported.** Keep `persona` and `thesis` — they are
what make the seats argue distinguishably rather than agree.

Things worth knowing before you substitute models:

- **Every behavioural number in `snapshot/BEHAVIOURAL-BASELINE.md` was measured on
  this exact pair.** Change the models and none of it describes your system.
  v1.2 Spike B found seat-level effects large enough to reverse in sign between
  the two seats.
- The `0.45` repetition threshold (`debate/argument_memory.py:76`) was calibrated
  on this pair. Its own docstring says: "Re-calibrate if the seat models change."
- **Avoid reasoning-heavy models.** They can spend the whole `num_predict` budget
  on hidden reasoning and produce no public speech, which the app records as a
  skipped turn.
- If a model is unreachable, the app fails turns safely and keeps running rather
  than crashing.

---

## 9. Known limitations

Read this before claiming the restore is verified anywhere.

### What was actually verified

Restore was rehearsed **on the snapshot machine itself** (Windows 11 10.0.26200,
AMD64, CPython 3.14.6), in a **separate directory outside the repository**, with a
**fresh virtual environment**. Through `scripts/bootstrap.ps1`, end to end, with no
manual intervention, it reached:

- all 22 lockfile pins installed at exactly the locked versions
- `84 passed`
- HTTP 200 on `/`, with the served HTML byte-identical to the restored tree's own
  `static/index.html`

### What was NOT verified

- **Any other machine.** Same-host restore does not prove another host works.
- **Linux or macOS.** A Windows host cannot verify them. `scripts/bootstrap.sh`
  was **written but never executed** — no non-Windows machine was available. Treat
  it as untested.
- **Any Python other than 3.14.6.** The README's 3.10+ claim is plausible on a
  source scan (nothing newer than PEP 604 unions is used) but has no test behind
  it. There is no `requires-python` anywhere in the project.
- **Model behaviour.** The rehearsal ran with Ollama deliberately unreachable, to
  prove boot and serving without invoking a model. No debate was generated.
  Nothing in `snapshot/BEHAVIOURAL-BASELINE.md` was re-measured.

### Windows-only development harnesses

The **unit test suite is portable** — it spawns subprocesses via `sys.executable`.
The **live harnesses are not**, and were deliberately left that way:

| File | Problem |
|---|---|
| `tests/live_soak.py:75, 85` | Shells out to `powershell`, **not** guarded by an `os.name` check. Raises `FileNotFoundError` elsewhere |
| `tests/live_qualify.py:22` | Hardcodes `C:\Python314\python.exe` |
| `README.md:123-124` | Documents both with that hardcoded interpreter |

These are outside the scope of the portability work done for this snapshot; they
are reported in `snapshot/PORTABILITY.md` (findings P4, P5, P7) with proposed
minimal fixes for the operator to rule on. **They were not fixed.**

### Line endings

`.gitattributes` sets `* text=auto` and the snapshot machine has
`core.autocrlf=true`, so three different byte-forms of this tree exist (worktree,
git blob, `git archive` output). This is why §3 verifies against
`git_blob_sha256` and tolerates `\r\n` → `\n`. Full detail in
`snapshot/PORTABILITY.md`, finding P8.

### Known defects in the baseline

`snapshot/DEFECT-REGISTER.md` records five verified defects that are **present in
this snapshot by design** — it is a faithful capture, not a repaired one. Most
relevant to a new operator:

- The **consensus-breaker never fires** (0 of 53 windows in the acceptance corpus).
  `consensus_window_turns` and `consensus_challenge_weight` have no observed effect.
- **`min_turn_chars` is a dead config key** — validated, never consumed.
- Turns **exceed the 160-word ceiling ~75% of the time**.
- Turns **open by agreeing with the other seat ~29% of the time** despite an
  explicit prohibition.

None of these prevents the system running. All are measured, not estimated.

---

## 10. Where everything is

| Path | What it is |
|---|---|
| `SNAPSHOT-RESTORE.md` | this document |
| `snapshot/MANIFEST.json` | 145 files, both hashes each |
| `snapshot/VERIFICATION.json` | result of re-hashing every file |
| `snapshot/ENVIRONMENT.json` | interpreter + resolved dependency closure |
| `snapshot/MODELS.json` | model digests, sizes, parameters |
| `snapshot/BEHAVIOURAL-BASELINE.md` | what the system did, and the limits of that evidence |
| `snapshot/DEFECT-REGISTER.md` | verified defects, non-goals, untouched backlog |
| `snapshot/PORTABILITY.md` | machine-binding findings, fixed and unfixed |
| `requirements.lock.txt` | the 22 pins |
| `scripts/bootstrap.ps1` / `.sh` | prepare and check a restore |
| `scripts/capture_environment.py` | regenerate the environment capture |
| `audit/v1_2_baseline_snapshot_ledger.md` | per-stage record of how this snapshot was made |
