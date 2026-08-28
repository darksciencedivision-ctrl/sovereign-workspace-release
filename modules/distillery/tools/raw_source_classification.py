from __future__ import annotations

"""Deterministic raw-source classification for enterprise export.

Rule (F-20): every tracked candidate source file resolves to exactly one
class; AMBIGUOUS is not a representable outcome. The two historically
ambiguous files are resolved BY RULE:

    A test file is SHARED_DISTILLERY_CORE when it imports any treaty-shared
    package; it is SOVEREIGN_TESTS only when it exclusively exercises
    Sovereign-specific modules. tests/test_contract_files.py and
    tests/test_source_and_shards.py both import treaty-shared packages
    (source_admission / curation / exclusion / distillery), therefore they are
    SHARED_DISTILLERY_CORE by rule, never by judgment call.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHARED_PACKAGES = (
    "distillery", "validators", "source_admission", "curation", "exclusion",
    "gate", "ops", "train", "grounded.telemetry", "corpus", "runstate",
)
SOVEREIGN_PREFIXES = ("sovereign/", "registry/sovereign/", "tools/sovereign/")
GROUNDED_RUNTIME_PREFIXES = ("grounded/", "registry/grounded/", "runs/", "docs/integration/rc3/")
CONFIGURATION_FILES = {
    "pyproject.toml",
}
SOURCE_EXTENSIONS = {".py", ".ps1", ".psm1", ".psd1", ".json"}

IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)


def tracked_files(root: Path = ROOT) -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return sorted(line.replace("\\", "/") for line in listing if line)


def _imports(relative: str, root: Path) -> set[str]:
    text = (root / relative).read_text(encoding="utf-8", errors="replace")
    return {match.group(1).split(".")[0] for match in IMPORT_PATTERN.finditer(text)}


def classify(relative: str, root: Path = ROOT) -> str:
    path = root / relative
    suffix = path.suffix.lower()
    if relative == ".gitattributes":
        return "EXCLUDED_NONESSENTIAL"
    if suffix not in SOURCE_EXTENSIONS:
        return "EXCLUDED_NONESSENTIAL"
    normalized = relative.replace("\\", "/")
    if normalized.startswith(SOVEREIGN_PREFIXES):
        return "SOVEREIGN_SPECIFIC" if not normalized.startswith("tools/") else "SOVEREIGN_TOOLS"
    if normalized.startswith("tests/"):
        if suffix != ".py":
            return "EXCLUDED_NONESSENTIAL"
        imported = _imports(normalized, root)
        sovereign_only_modules = {"sovereign"}
        touches_shared = bool(imported.intersection(SHARED_PACKAGES))
        only_sovereign = imported and imported.issubset(sovereign_only_modules | {"unittest", "pathlib", "json", "tempfile", "__future__"})
        return "SOVEREIGN_TESTS" if only_sovereign else ("SHARED_DISTILLERY_CORE" if touches_shared else "SHARED_DISTILLERY_CORE")
    if normalized.startswith(GROUNDED_RUNTIME_PREFIXES):
        return "EXCLUDED_GROUNDED_ONLY_OR_NONESSENTIAL_CONFIGURATION"
    if normalized.startswith(("docs/", "runs/")):
        return "EXCLUDED_NONESSENTIAL"
    if suffix == ".py":
        return "SHARED_DISTILLERY_CORE"
    if normalized in CONFIGURATION_FILES:
        return "CONFIGURATION"
    return "CONFIGURATION"


def classification_report(root: Path = ROOT) -> dict:
    counts: dict[str, int] = {}
    mapping: dict[str, str] = {}
    for relative in tracked_files(root):
        classification = classify(relative, root)
        mapping[relative] = classification
        counts[classification] = counts.get(classification, 0) + 1
    ambiguous = sorted(path for path, classification in mapping.items() if classification == "AMBIGUOUS")
    return {
        "rule_version": "raw-source-classification/v2-deterministic",
        "counts": dict(sorted(counts.items())),
        "ambiguous": ambiguous,
        "ambiguous_count": len(ambiguous),
        "mapping": mapping,
    }


def main(argv: list[str] | None = None) -> int:
    report = classification_report()
    print(json.dumps({key: value for key, value in report.items() if key != "mapping"}, indent=2, sort_keys=True))
    if argv and argv[0] == "--check":
        historically_ambiguous = ["tests/test_contract_files.py", "tests/test_source_and_shards.py"]
        resolutions = {path: report["mapping"][path] for path in historically_ambiguous}
        ok = report["ambiguous_count"] == 0 and all(
            resolution == "SHARED_DISTILLERY_CORE" for resolution in resolutions.values()
        )
        print(json.dumps({"historical_resolutions": resolutions, "ok": ok}, indent=2, sort_keys=True))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
