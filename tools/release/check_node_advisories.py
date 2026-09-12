#!/usr/bin/env python3
"""Release gate: no known advisory may ship in a Node dependency tree.

EPC-01 P2-6. `npm audit` was never part of the release gates, so a HIGH-severity advisory
(nanoid < 3.3.18, GHSA-2v37-7h3g-55p8) sat in the SOVEREIGN UI lockfile through an entire
release programme and was found only by running the audit by hand during a systems review.
An enterprise buyer runs a scanner on day one; this gate runs it first.

Both Node roots are checked. `--audit-level` is deliberately NOT raised to hide low findings:
the threshold is zero, because a dependency tree with a known-and-ignored advisory is a
conversation nobody wants to have during procurement.

Usage:
    py -3.12 tools/release/check_node_advisories.py [--offline]

`--offline` reports SKIPPED-WITH-RECORD rather than failing, for a build host with no registry
access. A skip is recorded in the output so it cannot be mistaken for a pass.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NODE_ROOTS = (
    Path("modules/sovereign/ui/ui_shell"),
    Path("modules/sow/apps/desktop"),
)


def _audit(root: Path) -> tuple[str, dict | None, str]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        return "no-npm", None, "npm is not on PATH"
    proc = subprocess.run(
        [npm, "audit", "--json", "--audit-level=low"],
        cwd=str(root), capture_output=True, text=True, check=False, timeout=300,
    )
    # F-065. `npm audit` exits 0 (clean) or 1 (advisories found); ANY other code means the audit
    # did not run (network/registry failure), and on such a failure npm prints a JSON ERROR object
    # to stdout with no metadata.vulnerabilities. Accepting any parseable JSON and reading a
    # missing metadata as "0 advisories" was fail-open: a registry outage printed "0 advisories"
    # and PASSED. Require a real audit exit code AND a real vulnerabilities block.
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or proc.stdout or "").strip()[:200]
        return "audit-error", None, f"npm exit {proc.returncode}: {detail}"
    if not proc.stdout.strip():
        return "no-output", None, (proc.stderr or "").strip()[:200]
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "bad-json", None, proc.stdout[:200]
    if not isinstance(report, dict) or not isinstance(
            report.get("metadata", {}).get("vulnerabilities"), dict):
        return "no-metadata", None, "audit JSON has no metadata.vulnerabilities block"
    return "ok", report, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    failures, skips = [], []
    for relative in NODE_ROOTS:
        root = REPO_ROOT / relative
        if not (root / "package-lock.json").is_file():
            skips.append(f"{relative.as_posix()}: no package-lock.json")
            continue

        state, report, detail = _audit(root)
        if state != "ok":
            message = f"{relative.as_posix()}: audit unavailable ({state}: {detail})"
            (skips if args.offline else failures).append(message)
            continue

        counts = report.get("metadata", {}).get("vulnerabilities", {})
        total = sum(v for k, v in counts.items() if k != "total")
        if total:
            named = ", ".join(f"{k}={v}" for k, v in counts.items() if v and k != "total")
            advisories = sorted(report.get("vulnerabilities", {}))
            failures.append(
                f"{relative.as_posix()}: {total} advisory/advisories ({named}) "
                f"-> {', '.join(advisories[:8])}"
            )
        else:
            print(f"  {relative.as_posix()}: 0 advisories")

    for line in skips:
        print(f"  SKIPPED-WITH-RECORD {line}")
    for line in failures:
        print(f"  VIOLATION {line}", file=sys.stderr)

    if failures:
        print(f"check_node_advisories: FAIL ({len(failures)} root(s) with advisories)",
              file=sys.stderr)
        return 1
    print(f"check_node_advisories: PASS ({len(NODE_ROOTS) - len(skips)} root(s) clean, "
          f"{len(skips)} skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
