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

A whole-repository `pytest` invocation is not currently possible: a `conftest.py`
in the SOW module raises an internal error during collection. Per-module runs
work.

## What has not been done

Stated so that absence is not mistaken for success:

- No clean-room installation has been performed from this archive.
- The release producer has never been run.
- No continuous-integration lane exists. The release tooling is Windows-only by
  construction, so any future lane requires Windows runners.
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
