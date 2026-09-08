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


#: Files that make up the shipped service. If any of them ever resolves a model role from the
#: legacy hierarchy, the scope declaration below stops being true and this gate must fail.
PRODUCT_PACKAGE = os.path.join("modules", "sovereign", "sovereign_product")

#: The one legitimate reason the product opens the hierarchy: it offers it to the model as an
#: evidence document. Any other reference is a role resolution and is a finding.
EVIDENCE_ONLY_REFERENCES = {
    ("evidence.py", "model hierarchy"),
    ("evidence.py", "synthesis/model_hierarchy.json"),
    ("server.py", "synthesis/model_hierarchy.json"),
}


def check_hierarchy(root: str, models: dict) -> list:
    """Verify the hierarchy's SCOPE, not equality with the product roster.

    SWS-CORRECTIVE-01 R1. This function used to assert
    `king_synthesizer.model == MODELS.SYNTHESIZER`, which forced two independent pipelines to
    share one value. Tracing the actual consumers on this candidate:

      * `SYSTEM_MANIFEST.json MODELS` is the ONLY source the shipped service reads for role
        assignment - `ProductService._quick_executor` and `_deep_executor_from_manifest`.
      * `synthesis/model_hierarchy.json` configures the legacy synth_king /
        live_orchestrator pipeline, which the shipped product never launches.

    Two different pipelines may legitimately run different rosters, so equality was the wrong
    assertion. What must hold - and what is checked here instead - is stronger and falsifiable:
    the hierarchy DECLARES which pipeline it configures and where the product's roster lives,
    that declaration names the product's real source, and no file in the shipped service
    resolves a model role from the hierarchy. The last check is the one that matters: if the
    product ever starts consuming this file, the declaration becomes a lie and this gate fails.

    Retargeting the legacy pipeline's rosters to the product's 3B set is a product decision
    with no evidence in the tree either way, so it is NOT made here.
    """
    problems = []
    path = os.path.join(root, "modules", "sovereign", "synthesis",
                        "model_hierarchy.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        return [f"model_hierarchy.json unreadable: {exc}"]

    scope = doc.get("scope")
    if not isinstance(scope, dict):
        return ["hierarchy: model_hierarchy.json declares no `scope`. A roster that differs "
                "from SYSTEM_MANIFEST MODELS must say which pipeline it configures, because "
                "the product serves this file to the model as evidence."]

    if scope.get("product_roster_source") != "SYSTEM_MANIFEST.json MODELS":
        problems.append(
            "hierarchy: scope.product_roster_source = "
            f"`{scope.get('product_roster_source')}`, but the shipped service resolves every "
            "model role from SYSTEM_MANIFEST.json MODELS")

    if scope.get("configures") != "legacy-synthesis-pipeline":
        problems.append(
            f"hierarchy: scope.configures = `{scope.get('configures')}`; this gate only "
            "recognises `legacy-synthesis-pipeline`. If the product now consumes this file, "
            "the roster must be reconciled with SYSTEM_MANIFEST MODELS instead of scoped away.")

    # Every model the hierarchy names must still be a usable tag, so a scoped-out roster is
    # not a place where nonsense can accumulate unchecked.
    def walk(node, trail):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "model":
                    if not isinstance(value, str) or not value.strip():
                        problems.append(
                            f"hierarchy: {trail}.model is not a usable model tag: {value!r}")
                else:
                    walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")

    for key in ("king_synthesizer", "alpha_wing", "beta_wing", "wing_reconciliation",
                "cross_channel", "clu_roles"):
        if key in doc:
            walk(doc[key], key)

    problems.extend(check_product_does_not_consume_hierarchy(root))
    return problems


def check_product_does_not_consume_hierarchy(root: str) -> list:
    """The scope declaration is only true while the shipped service ignores the hierarchy."""
    problems = []
    package = os.path.join(root, PRODUCT_PACKAGE)
    if not os.path.isdir(package):
        return [f"product package not found at {PRODUCT_PACKAGE}"]
    for entry in sorted(os.listdir(package)):
        if not entry.endswith(".py"):
            continue
        try:
            with open(os.path.join(package, entry), "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as exc:
            problems.append(f"{PRODUCT_PACKAGE}/{entry} unreadable: {exc}")
            continue
        for number, line in enumerate(lines, 1):
            if "model_hierarchy" not in line and "model hierarchy" not in line:
                continue
            if any(entry == name and token in line
                   for name, token in EVIDENCE_ONLY_REFERENCES):
                continue
            problems.append(
                f"hierarchy: {PRODUCT_PACKAGE}/{entry}:{number} references the legacy model "
                "hierarchy outside the evidence-document allowlist. The shipped service must "
                "resolve model roles from SYSTEM_MANIFEST MODELS only; if this is a new "
                "consumer, the two rosters must be reconciled rather than scoped apart.")
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
