# Portability Findings — v1.2-phase1-baseline (`d03a1b7`)

**Diagnosis only. No fix was applied in the stage that produced this document.**
Remediation actually applied is confined to the §0.4 allowlist and is recorded in
the Stage H ledger entry. Findings marked *outside boundary* were **not** changed;
their "minimal fix" column is a proposal for the operator to rule on.

**§0.5 boundary.** "Portable" means: **install the dependencies, start the app, and
run the unit test suite** on a machine that is not this one. Development harnesses
are outside that boundary. Making every dev tool cross-platform is a separate
decision the operator has not made.

---

## Summary

| # | Path | Blocks | In boundary? | Fixed in Stage H? |
|---|---|---|---|---|
| P1 | `.claude/launch.json:6-7` | starting the app via the launch config | **inside** | yes |
| P2 | `README.md:22-23, 105-106` | install and start instructions | **inside** | yes |
| P3 | `requirements.txt` | reproducible install | **inside** | addressed in Stage B |
| P4 | `tests/live_qualify.py:22` | live qualification harness | outside | **no — reported** |
| P5 | `tests/live_soak.py:75, 85` | live soak harness | outside | **no — reported** |
| P6 | `app.py:1522` | nothing — see finding | outside | **no — operator's call** |
| P7 | `README.md:114-115` | live-harness instructions | outside | **no — reported** |
| P8 | line-ending configuration | manifest verification after restore | **inside** | mitigated, not fixed |
| P9 | no declared Python floor | choosing an interpreter to restore onto | **inside** | documented only |
| P10 | pytest absent from every dependency file | running the test self-check | **inside** | documented only |

Nothing outside the allowlist was modified. Where a fix was wanted but out of
bounds, it is written here for the operator rather than applied.

---

## P1 — `.claude/launch.json` hardcodes interpreter and project path — **inside boundary**

**MEASUREMENT**, `.claude/launch.json:6-7`:

```json
"runtimeExecutable": "C:\\Python314\\python.exe",
"runtimeArgs": ["D:\\Debate table\\app.py"],
```

**Why it blocks portability:** two independent machine bindings in one file. The
interpreter must be at exactly `C:\Python314\`, and the project must be checked out
to exactly `D:\Debate table\`. Both fail on any other machine, and the second fails
even on *this* machine if the folder is renamed or moved. Restoring to
`C:\Users\me\debate-table\` breaks it.

**Minimal fix:** `python` on `PATH`, and a path relative to the project root.
Applied in Stage H.

---

## P2 — `README.md` install and start block hardcodes the interpreter — **inside boundary**

**MEASUREMENT**, `README.md:22-23`:

```powershell
C:\Python314\python.exe -m pip install -r requirements.txt
C:\Python314\python.exe app.py
```

and `README.md:105-106`:

```powershell
C:\Python314\python.exe -m pip install pytest
C:\Python314\python.exe -m pytest -q -W error
```

**Why it blocks portability:** this is the first thing a restorer reads and it
instructs them to run a binary that will not exist. It also installs into a global
interpreter rather than a virtual environment, so a restore following the README
literally pollutes the system Python.

**Minimal fix:** portable invocation form; add a pointer to `SNAPSHOT-RESTORE.md`.
Applied in Stage H, confined to the install/start and test blocks.

---

## P3 — `requirements.txt` pins nothing — **inside boundary**

**MEASUREMENT:** `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27`,
`pydantic>=2.0`. Four lower bounds, no upper bounds, no lockfile at `d03a1b7`.

**Why it blocks portability:** a restore resolves whatever is newest on the day. The
baseline was validated against `fastapi 0.139.0`, `starlette 1.3.1`,
`pydantic 2.13.4`, `uvicorn 0.51.0`, `httpx 0.28.1` — none of which is recorded
anywhere in the repository at `d03a1b7`. A future FastAPI or Starlette release can
change behaviour with every declared constraint still satisfied.

**Fix (Stage B, already applied):** `requirements.lock.txt` with `==` pins for all
22 resolved distributions. **`requirements.txt` was deliberately not modified** —
the human-facing declaration and the reproducible pin are different artifacts and
both are wanted.

**Residual, recorded honestly:** the lock was resolved on Windows. `uvloop` — which
`uvicorn[standard]` pulls in on Linux and macOS — is absent, because its marker
`sys_platform != 'win32'` is false here. A non-Windows restore from the lock gets a
working but slower event loop. Noted in the lockfile header and in
`snapshot/ENVIRONMENT.json` → `excluded_by_marker`.

---

## P4 — `tests/live_qualify.py:22` hardcodes the interpreter — **OUTSIDE boundary, not fixed**

**MEASUREMENT:** `PYTHON = Path(r"C:\Python314\python.exe")`, consumed at
`live_qualify.py:129` to spawn the app under test.

**Why it blocks portability:** fails on any machine without that exact path,
including a Windows machine with Python installed elsewhere.

**Proposed minimal fix (NOT APPLIED):** `PYTHON = Path(sys.executable)` — one line,
and the pattern already used by `tests/test_smoke.py:94` and `:104` in this same
repository.

**Why it was not applied:** outside the §0.5 boundary. Flagged for the operator.

---

## P5 — `tests/live_soak.py:75, 85` shell out to `powershell` — **OUTSIDE boundary, not fixed**

**MEASUREMENT — `live_soak.py:75`** (`process_memory`):

```python
command = ["powershell", "-NoProfile", "-Command",
           f"(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64"]
```

**MEASUREMENT — `live_soak.py:85-91`** (`ollama_processes`): a second `powershell`
invocation using `Get-Process -Name 'ollama*' | ConvertTo-Json`.

**Are these guarded by an `os.name` check? No.** Neither call site has one. The file
*does* check `os.name` twice, but for unrelated concerns — process-creation flags at
`:103` and `signal.CTRL_BREAK_EVENT` at `:119-121`.

**Failure mode on a non-Windows host:** `FileNotFoundError` at call time.
`process_memory` catches only `ValueError`; `ollama_processes` catches nothing.
Neither degrades gracefully.

**Proposed minimal fix (NOT APPLIED):** guard both behind `os.name == "nt"` and
return `None` / `[]` otherwise, so the harness loses memory telemetry on other
platforms instead of crashing. Cross-platform equivalents (e.g. `psutil`) would add
a runtime dependency, which §0.2 forbids.

**Why it was not applied:** outside the §0.5 boundary.

---

## P6 — `app.py:1522` binds `host="127.0.0.1"` — **OUTSIDE boundary, deliberately not changed**

**MEASUREMENT**, `app.py:1519-1525`:

```python
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(CONFIG["port"]),
                log_level="warning")
```

**Assessment: this is a deliberate local-only security property, not a portability
blocker.** The reasoning, from evidence rather than preference:

- `127.0.0.1` is the loopback address on **every** platform. It is not
  machine-specific and nothing about it fails on restore. The app binds and serves
  identically on Windows, Linux and macOS.
- `README.md:3` describes a **local** app; the intended consumer is an OBS Browser
  Source on the same machine (`README.md:75-79`).
- The app exposes an unauthenticated operator API — `/api/*` endpoints that rewrite
  `config.json`, swap models, and inject operator text. There is no auth layer
  anywhere in `app.py`. Binding `0.0.0.0` would expose all of that to the local
  network.
- `port` is configurable via `config.json`; `host` deliberately is not. That
  asymmetry reads as intentional.

**Consequence a restorer must know:** the app is reachable only from the machine it
runs on. Serving it to another device, or from a container or VM, requires either a
port-forward/reverse proxy in front of it, or a change to this line — which would
expose the unauthenticated operator API.

**Recorded, not decided. Not changed.** Per directive §0.4 and trap 8, this is the
operator's call.

---

## P7 — `README.md:114-115` documents live harnesses with a hardcoded interpreter — **OUTSIDE boundary, not fixed**

**MEASUREMENT:**

```powershell
C:\Python314\python.exe tests\live_qualify.py
C:\Python314\python.exe tests\live_soak.py --minutes 30 --models "qwen2.5:14b-instruct" "phi4:14b"
```

Same hardcoded interpreter as P2, but documenting the **live harnesses**, which are
outside the boundary and remain Windows-only regardless of how they are invoked
(P4, P5). Rewriting these two lines would make a Windows-only tool *look* portable
while P5 still crashes on `powershell`.

**Not fixed — deliberately.** Stage H's `README.md` edit is confined to the
install/start and test blocks. Making this block portable is misleading until P4
and P5 are resolved. `SNAPSHOT-RESTORE.md` records the harnesses as Windows-only
under known limitations instead.

---

## P8 — Line-ending configuration breaks manifest verification after restore — **inside boundary**

Found while committing Stage 0; it is the one finding here that a reader would not
predict from the file list.

**MEASUREMENT:** `.gitattributes` sets `* text=auto` and `*.json text eol=lf`;
`git config core.autocrlf` → `true` (global).

**MEASUREMENT — three distinct byte-forms of this tree exist:**

| Form | `app.py` | Matches git blob? |
|---|---|---|
| Worktree on this host | 53,587 B, 0 CRLF | yes (120 of 145 files match; 25 differ, all CRLF-only) |
| Git blob / canonical | 53,587 B, 0 CRLF | — |
| `git archive` output on this host | 55,112 B, 1,525 CRLF | **no** (only 64 of 145 match) |

**MEASUREMENT — what controls the archive form:** `git -c core.autocrlf=false` and
`git -c core.eol=lf` both still emit CRLF; only `git -c core.autocrlf=input archive`
reproduces blob bytes. `core.eol` is inert while `core.autocrlf` is `true`.

**Why it matters:** `git archive` applies the *exporting machine's* EOL settings. The
Stage J zip built here embeds CRLF; the same command on Linux would emit LF. A
manifest recording only worktree hashes would fail verification against either.

**Mitigation applied (not a repo change):**

1. `snapshot/MANIFEST.json` carries `git_blob_sha256` per entry alongside the
   worktree `sha256`. The blob hash is platform-independent and is what
   `SNAPSHOT-RESTORE.md` instructs a restorer to verify against.
2. The Stage J zip is produced with `-c core.autocrlf=input` so its contents match
   `git_blob_sha256` directly.

**Confirmed by execution in Stage G (MEASUREMENT).** The restored tree was exported
with plain `git archive`. Its served root page is **byte-identical to its own**
`static/index.html` (25,635 B, sha256 `e3246ce8…fbe3`) — proving the server serves
the file unmodified — while the repository worktree copy is 24,883 B, sha256
`46b078e3…a00cd`. The two differ **only** by line endings: identical after
normalising `\r\n` → `\n`. This is the predicted divergence, observed rather than
argued.

**Not fixed at source, and this is the operator's call:** setting
`* text=auto eol=lf` in `.gitattributes` would normalise all three forms
permanently. `.gitattributes` is **not** on the §0.4 allowlist, and changing it
would rewrite 25 tracked files' worktree bytes — a content change to a baseline
this run exists to preserve unmodified. **Proposed, not applied.**

---

## P9 — No declared minimum Python version — **inside boundary**

**MEASUREMENT:** `README.md:9-13` claims "Python 3.10 or newer". There is no
`pyproject.toml`, no `setup.cfg`, and no `python_requires` / `requires-python`
anywhere in the tracked tree — a search for both returned nothing.

**MEASUREMENT:** the baseline was validated on exactly one interpreter, **CPython
3.14.6** (`snapshot/ENVIRONMENT.json`).

**MEASUREMENT — source scan for version-gated constructs:** no `tomllib`,
`datetime.UTC`, `asyncio.timeout`, `except*`, `ExceptionGroup`, `typing.Self`,
`StrEnum`, `itertools.batched`, or `match` statement appears in `app.py`,
`debate/*.py`, or `tests/*.py`. PEP 604 unions (`X | None`, requiring **3.10+**) are
used 22 times across `app.py` and `debate/`.

**INFERENCE** (rests on the scan above): the 3.10 floor in the README is *plausible*
on syntax grounds — nothing newer than 3.10 syntax is used. But **it is not
measured**. Only 3.14.6 has evidence behind it, and the pinned dependency set was
resolved for 3.14. `SNAPSHOT-RESTORE.md` therefore names 3.14.6 as the verified
interpreter and 3.10 as the untested lower bound the README claims, rather than
promoting the claim to a fact.

---

## P10 — pytest is in no dependency file — **inside boundary**

**MEASUREMENT:** `pytest` appears in neither `requirements.txt` nor the 22-package
closure in `requirements.lock.txt`. `README.md:102-106` documents it as a
development-only install. Installed version on this host: `pytest 9.1.1`.

**Why it matters for restore:** the runbook's self-check step is "run the test
suite". A venv built only from `requirements.lock.txt` **cannot run it** — an
`ImportError` at the first `pytest` invocation, which reads as a broken restore
rather than a missing dev tool.

**Settled by execution (MEASUREMENT).** This was written as a prediction before
Stage G ran, so it would be measured rather than assumed. Stage G's cold restore
installed all 22 lockfile pins successfully and then failed at exactly this step:

```
D:\snapshot-restore-test\venv\Scripts\python.exe -m pytest tests -q -W error
D:\snapshot-restore-test\venv\Scripts\python.exe: No module named pytest
exit code 1
```

The prediction was correct. A restore that follows only "install from the lockfile"
cannot run its own self-check.

**Not fixed at source.** Adding pytest to `requirements.txt` would make a dev tool a
runtime dependency and contradicts a deliberate, documented decision; `requirements.txt`
is not on the allowlist in any case. Handled instead by `scripts/bootstrap.ps1`
and `scripts/bootstrap.sh` installing pytest explicitly as a named dev tool, and by
`SNAPSHOT-RESTORE.md` stating it as its own step.

---

## Cross-platform status — INFERENCE, not measurement

**Verified by execution in this run:** this host (Windows 11, 10.0.26200, AMD64),
in a separate directory, with a fresh virtual environment. That is the whole of the
verified scope.

**Not verified, and not claimed:** Linux, macOS, ARM, any other machine, and any
other Python version. The remaining evidence for those is only the source scan in
P9 and the absence of platform-specific code in `app.py` and `debate/` — which is
suggestive, not proof. A Windows host cannot verify a Linux restore.
