#!/usr/bin/env python
"""Model-assignment consistency gate — SWS-REM-DIR-20260828 R2, B2-6 (M-6).

SYSTEM_MANIFEST.json is the single source of truth for package-level role →
model assignments (format_alignmentforum.py docstring: "read from
SYSTEM_MANIFEST.json (single source…)"). This gate mechanically verifies:

* README_PRODUCTION.md — the five "Current default model assignments" bullets
  equal the manifest's MODELS values (label → key map is explicit);
* synthesis/model_hierarchy.json — king_synthesizer.model equals MODELS.
  SYNTHESIZER (the king is the runtime synthesizer; synth_king.py:1325 uses
  the hierarchy value first, manifest SYNTHESIZER as fallback) and
  cross_channel.critique.model equals MODELS.CRITIC.

Exit 0 consistent, 1 mismatches/parse problems, 2 usage error. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

README_LABEL_TO_KEY = {
    "Primary reasoner": "PRIMARY_REASONER",
    "Adversarial challenger": "ADVERSARIAL_CHALLENGER",
    "Critic": "CRITIC",
    "Synthesizer": "SYNTHESIZER",
    "Embedding model": "EMBEDDING_MODEL",
}

BULLET_RE = re.compile(r"^- ([A-Za-z ]+):\s*`([^`]+)`\s*$")


def load_manifest(root: str) -> dict:
    path = os.path.join(root, "modules", "sovereign", "SYSTEM_MANIFEST.json")
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    models = doc.get("MODELS")
    if not isinstance(models, dict) or not models:
        raise ValueError("SYSTEM_MANIFEST.json has no MODELS map")
    return models


def check_readme(root: str, models: dict) -> list:
    problems = []
    path = os.path.join(root, "modules", "sovereign", "README_PRODUCTION.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        return [f"README_PRODUCTION.md unreadable: {exc}"]
    found = {}
    for line in lines:
        m = BULLET_RE.match(line.strip())
        if m and m.group(1) in README_LABEL_TO_KEY:
            found[m.group(1)] = m.group(2)
    for label, key in README_LABEL_TO_KEY.items():
        if label not in found:
            problems.append(f"README: assignment bullet missing for {label}")
            continue
        want = models.get(key)
        if found[label] != want:
            problems.append(
                f"README: {label} says `{found[label]}` but SYSTEM_MANIFEST "
                f"MODELS.{key} = `{want}`")
    return problems


def check_hierarchy(root: str, models: dict) -> list:
    problems = []
    path = os.path.join(root, "modules", "sovereign", "synthesis",
                        "model_hierarchy.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        return [f"model_hierarchy.json unreadable: {exc}"]
    king = (doc.get("king") or doc.get("king_synthesizer") or {})
    king_model = king.get("model")
    want_synth = models.get("SYNTHESIZER")
    if king_model != want_synth:
        problems.append(
            f"hierarchy: king_synthesizer.model = `{king_model}` but "
            f"SYSTEM_MANIFEST MODELS.SYNTHESIZER = `{want_synth}`")
    critique = (doc.get("cross_channel") or {}).get("critique") or {}
    critique_model = critique.get("model")
    want_critic = models.get("CRITIC")
    if critique_model != want_critic:
        problems.append(
            f"hierarchy: cross_channel.critique.model = `{critique_model}` "
            f"but SYSTEM_MANIFEST MODELS.CRITIC = `{want_critic}`")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="model assignment consistency gate")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"check_model_consistency: no such directory: {args.root}",
              file=sys.stderr)
        return 2
    try:
        models = load_manifest(args.root)
    except (OSError, ValueError) as exc:
        print(f"check_model_consistency: CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    problems = check_readme(args.root, models) + check_hierarchy(args.root, models)
    utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"check_model_consistency: {'FAIL' if problems else 'PASS'} ({utc})")
    for p in problems:
        print(f"  PROBLEM {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
