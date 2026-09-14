#!/usr/bin/env python
"""Project the canonical model roster from SYSTEM_MANIFEST.json onto the surfaces that quote it.

SWS-CORRECTIVE-01 workstream 2 (R1). `check_model_consistency.py` reported six mismatches:
four README bullets and two `model_hierarchy.json` entries. The instruction was to find the
authoritative assignments and their ACTUAL consumers rather than pick whichever set cleared
the gate. Traced on this candidate:

  SYSTEM_MANIFEST.json MODELS  -- 3B roster -- is the ONLY source the shipped product reads
    for role assignment. `ProductService._quick_executor` and `_deep_executor_from_manifest`
    both resolve PRIMARY_REASONER / CRITIC / SYNTHESIZER / ADVERSARIAL_CHALLENGER from it, and
    `SemanticDeepExecutor` is the default DEEP executor. Nothing in `sovereign_product/`
    resolves a model role from anywhere else.

  README_PRODUCTION.md -- 8B roster -- documents the assignments and is read by operators. It
    had simply not been updated when the roster moved to 3B. It has no runtime consumer, so
    correcting it changes no behaviour; it stops the document contradicting the product.

  synthesis/model_hierarchy.json -- 8B roster -- configures the LEGACY synth_king /
    live_orchestrator pipeline (`synthesis/live_orchestrator.py` imports `synth_king`, which
    reads this file). The shipped product never launches it: `shell/modules/sovereign.json`
    starts `sovereign_product.server`, and `cycle_runner_v3.py` appears there only as a
    presence flag. `sovereign_product` opens this file for ONE purpose - as an evidence
    document offered to the model (`evidence.py:179`, `server.py:705`).

That last fact is why the divergence still mattered. An operator asking "what model is
configured?" could be handed a hierarchy that says `deepseek-r1:8b` as EVIDENCE, while the
product was running `llama3.2:3b` - a cited answer that is wrong, which is precisely the
failure mode Q1 is about.

WHAT THIS TOOL CHANGES, AND WHAT IT DELIBERATELY DOES NOT. It projects the manifest roster
onto README_PRODUCTION.md, which has no runtime consumer. It does NOT retarget the legacy
hierarchy's rosters: which models that pipeline should run is a product decision with no
evidence in the tree either way, and rewriting it to clear a gate is exactly what the
directive forbids. Instead the hierarchy now DECLARES its scope, so the evidence document says
which pipeline it configures and where the product's roster actually lives, and
`check_model_consistency.py` enforces that declaration.

Exit 0 consistent, 1 drift (or drift corrected with --write), 2 usage error. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

README_LABEL_TO_KEY = (
    ("Primary reasoner", "PRIMARY_REASONER"),
    ("Adversarial challenger", "ADVERSARIAL_CHALLENGER"),
    ("Critic", "CRITIC"),
    ("Synthesizer", "SYNTHESIZER"),
    ("Embedding model", "EMBEDDING_MODEL"),
)

BULLET_RE = re.compile(r"^- ([A-Za-z ]+):\s*`([^`]+)`\s*$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_models(root: Path) -> dict:
    path = root / "modules" / "sovereign" / "SYSTEM_MANIFEST.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    models = doc.get("MODELS")
    if not isinstance(models, dict) or not models:
        raise SystemExit("SYSTEM_MANIFEST.json has no MODELS map")
    return models


def project_readme(root: Path, models: dict, write: bool) -> list[str]:
    path = root / "modules" / "sovereign" / "README_PRODUCTION.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    wanted = {label: models.get(key) for label, key in README_LABEL_TO_KEY}

    drift = []
    changed = False
    for index, line in enumerate(lines):
        match = BULLET_RE.match(line.strip())
        if not match or match.group(1) not in wanted:
            continue
        label, current = match.group(1), match.group(2)
        expected = wanted[label]
        if current == expected:
            continue
        drift.append(
            "README_PRODUCTION.md: {} says `{}`, canonical roster says `{}`".format(
                label, current, expected))
        if write:
            lines[index] = "- {}: `{}`".format(label, expected)
            changed = True

    if write and changed:
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return drift


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    root = repo_root()
    models = load_models(root)
    drift = project_readme(root, models, write=args.write)

    if not drift:
        print("generate_model_projection: PASS - every projected surface matches "
              "SYSTEM_MANIFEST MODELS")
        return 0

    verb = "corrected" if args.write else "found"
    print("generate_model_projection: {} {} projection drift(s)".format(verb, len(drift)))
    for item in drift:
        print("  {}".format(item))
    if args.write:
        print("  Review the diff and commit it with the manifest change that caused it.")
        return 1
    print("  Re-project with: py -3.12 tools/release/generate_model_projection.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
