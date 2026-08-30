# Release assurance status

**Directive:** SWS-UI-001 · **Gate ledger version:** 1.2 · **Statement date:** 2026-08-30

This document states what has and has not been reviewed in this release. It is
derived from the programme's gate ledger, which is a build-control instrument and
is **not** included in the distribution — see *Why the ledger itself does not ship*
below. Nothing here is a claim of certification, and no third party has audited
this software.

## Gate posture

The programme tracks 29 gates. Their standing as of the statement date:

| Status | Count | Gates |
|---|---|---|
| PASS | 9 | 0, 1, 2, 3, 4, 4b, 4c, 5b, 6 |
| CANDIDATE — claimed, never evaluated | 19 | 7a, 7b, 8a–8j, 9c–9j |
| STOP | 1 | 5 |

Gate activity spans 2026-08-21 to 2026-08-27. Gates 9a and 9b do not exist in the
ledger.

### What "CANDIDATE" means here, stated plainly

All 19 candidate gates carry `evaluated_by: null`. **No candidate gate has been
evaluated by any reviewer at any point in the programme.** They record work the
builder claims to have completed; they do not record work anyone has checked.
The nine PASS gates are historical, covering gates 0 through 6, and are the only
gates that carry a reviewer.

Read the ratio directly: nine gates reviewed, nineteen claimed and unreviewed.
Review, not implementation, is what stands between this release and a ratified
one.

### Gate 5

Gate 5 is a STOP, and the STOP was adjudicated **correct** — it is a deliberate
halt, not a failure in the field. Non-visual evidence was accepted and carried
forward (startup records, module manifests, byte-identical git bodies, no
orphans, a clean filesystem-watch window, and a 116-case suite passing). The
visual deliverables that gate 5 covers were blocked, and gate 5b subsequently
passed.

## Testing, as measured rather than claimed

Automated test coverage is not uniform across the modules in this release. In
particular, the SOVEREIGN module carries 74 Python source files and **no Python
tests**; its only automated tests are five TypeScript/TSX tests covering the UI
shell. The orchestration engine, the model-role machinery, the system manifest
and the health endpoint are not covered by automated tests. Other modules are
substantially better covered — the SOW module ships 333 Python source files with
155 named `test_*.py`, or 167 counting every file under its test directories.

All counts in this section are taken from the distributed archive itself, not
from the working repository, so they describe what a recipient receives.

A whole-repository `pytest` invocation works and is the invocation that matters.
It previously raised an internal error during collection from a `conftest.py` in
the SOW module; with that fixed, collection from the repository root went from
392 tests and 119 errors to 3,721 tests and none.

Run both. They are not equivalent, and the difference is not incidental: twenty
defects existed **only** in the combined run, because that is the only invocation
where the modules share a process and a `PYTHONPATH`. A per-module suite that
passes is evidence about that module, not about the product.


## The verification suite

Everything that verifies this release lives in one script, `tools/ci/run_ci.ps1`, and the
CI lane invokes that script rather than repeating its steps. That arrangement is the point:
a workflow carrying its own list of checks drifts from what anyone runs locally, and the
drift is discovered when the lane goes green on a tree that is broken.

```powershell
.\tools\ci\run_ci.ps1                    # everything that does not mutate the machine
.\tools\ci\run_ci.ps1 -IncludeCleanRoom  # adds the V-1 clean-room install and verify
```

The stages, in the order they run: the seven release gates, the boundary gate against the
distribution, the whole-product `pytest` from the repository root, the two Node suites and
the UI typecheck, and the clean-room install.

Two properties are deliberate. **No stage stops the run** — a failure is recorded and the
remaining stages still execute, because the first failure is rarely the only one worth
seeing. And **a skipped stage is reported**, under a `SKIPPED-WITH-RECORD` heading naming
what did not run and why; a suite that quietly does less than it claims is worse than one
that does less loudly.

`shell/tests/test_ci_lane_runs_what_it_claims.py` holds the wiring in place: it fails if
the workflow starts calling gates directly instead of through the script, if a gate leaves
the script, if the boundary gate stops scanning the distribution, if the lane's checkout
becomes shallow, or if the script acquires a non-ASCII byte — which PowerShell 5.1 reads as
ANSI in a BOM-less file, turning one character into a parse failure at a misleading line.

## What has not been done

Stated so that absence is not mistaken for success:

- No clean-room installation has been performed from this archive.
- The release producer has never been run.
- No lane has ever RUN. The lane now exists — `.github/workflows/windows.yml`,
  invoking `tools/ci/run_ci.ps1` — and the script has been executed locally, which
  is what makes it a lane rather than a declaration. It has not yet run on a
  hosted Windows runner, so nothing here claims it has.
- No independent or third-party audit has been performed.

## Why the ledger itself does not ship

The gate ledger records 379 evidence pointers, each a path and a SHA-256 digest.
280 of those 379 point into the development-record trees, which are excluded from
the distribution. Shipping the ledger would therefore hand a recipient a document
citing 280 hashed artifacts that are not present to verify — advertising a
verifiability the archive cannot support. The ledger also carries build-host paths
in its reviewer prose. This summary exists so that the assurance posture is
disclosed without either of those defects.

The ledger remains in version control and is available to anyone with repository
access.
