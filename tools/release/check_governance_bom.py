#!/usr/bin/env python
"""Governance-JSON BOM guard — SWS-REM-DIR-20260828 R2, B2-5 (M-5).

Fails when any enumerated active governance JSON carries a UTF-8 BOM.
The six files were stripped of BOMs in B2-5 (strict utf-8 JSON parsers
reject a leading EF BB BF with 'Unexpected UTF-8 BOM'); this guard keeps
them clean. Enumeration is explicit — no globs. Exit 0 clean, 1 BOM found
or file missing, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

DEFAULT_GOVERNANCE_JSON = (
    "modules/sovereign/SYSTEM_MANIFEST.json",
    "modules/sovereign/constitution/constitutional_rules.json",
    "modules/sovereign/constitution/promotion_policy.json",
    "modules/sovereign/constitution/risk_policy.json",
    "modules/sovereign/library/config/clu_runtime_policy.json",
    "modules/sovereign/synthesis/synthesis_contract.json",
)

BOM = b"\xef\xbb\xbf"


def check(root: str, paths=DEFAULT_GOVERNANCE_JSON) -> list:
    problems = []
    for rel in paths:
        full = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            problems.append(f"{rel}: MISSING")
            continue
        with open(full, "rb") as f:
            head = f.read(3)
        if head == BOM:
            problems.append(f"{rel}: UTF-8 BOM present")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Governance JSON BOM guard")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"check_governance_bom: no such directory: {args.root}",
              file=sys.stderr)
        return 2
    problems = check(args.root)
    utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verdict = "FAIL" if problems else "PASS"
    print(f"check_governance_bom: {verdict} ({utc})")
    for p in problems:
        print(f"  PROBLEM {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
