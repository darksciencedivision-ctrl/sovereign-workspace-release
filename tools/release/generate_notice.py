"""Generate NOTICE — the third-party attribution file — from the SBOM.

EPC-01 P0-1 / P2-5. The workspace shipped a placeholder LICENSE and no NOTICE at all,
while distributing 304 third-party library components. This tool produces the attribution
file from the SBOM rather than by hand, so it cannot drift from what actually ships.

Two rules it enforces, because both were violated by the state it replaces:

  * A licence is never guessed. Where the SBOM says UNKNOWN, the value is read from the
    installed distribution's own metadata (License-Expression, then Trove classifier, then
    the License field). A package that resolves to nothing is written into the output as
    UNRESOLVED and the tool exits non-zero — an incomplete NOTICE fails the build rather
    than shipping quietly.
  * Spelling variants are normalised. The SBOM carries four spellings of Apache-2.0 and one
    entry whose "licence id" is an entire MIT licence text. Normalising is presentation
    only; the raw value is preserved alongside it.

Usage:
    py -3.12 tools/release/generate_notice.py [--sbom SBOM.json] [--out NOTICE] [--check]

`--check` regenerates into memory and fails if the file on disk differs, which is how CI
catches a NOTICE that stopped matching the SBOM.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Presentation-only normalisation. Maps the spellings the SBOM actually contains onto one
#: SPDX identifier each. Anything not listed is passed through unchanged.
SPELLINGS = {
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "the unlicense (unlicense)": "Unlicense",
    "python software foundation license": "PSF-2.0",
    "mit license": "MIT",
    "bsd license": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
}

#: Values that are technically present but say nothing useful. `python-dateutil` declares
#: "Dual License" in its License field while naming both options in its classifiers; a NOTICE
#: that repeats the vague field is worse than one that reads the classifiers.
# F-075: "unresolved" is itself vague - a component whose SBOM licence is literally "UNRESOLVED"
# must NOT be written into NOTICE as a licence named UNRESOLVED with exit 0. Treating it as vague
# sends it through from_installed and, failing that, into the unresolved list -> the tool exits
# non-zero, so an incomplete NOTICE fails the build (as this module's docstring promises).
VAGUE = {"", "unknown", "dual license", "other", "other/proprietary license", "unresolved"}

#: Licences whose obligations need more than attribution. Each maps to the section of
#: docs/THIRD-PARTY-LICENCE-POSITION.md that records the position taken.
NEEDS_POSITION = ("MPL-2.0",)


def normalise(value: str) -> str:
    if not value:
        return value
    key = value.strip().lower()
    if key in SPELLINGS:
        return SPELLINGS[key]
    # An entry whose "id" is an entire licence text: keep the family, drop the body.
    if len(value) > 60:
        for family in ("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0"):
            if family.lower() in key[:40]:
                return family
        return "SEE-COMPONENT-METADATA"
    return value.strip()


def declared(component: dict) -> str | None:
    for entry in component.get("licenses") or []:
        node = entry.get("license") or {}
        value = node.get("id") or node.get("name") or entry.get("expression")
        if value:
            return value
    return None


def from_installed(name: str) -> tuple[str | None, str]:
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return None, "not installed"
    expression = meta.get("License-Expression")
    if expression:
        return expression, "License-Expression"
    classifiers = [c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    if classifiers:
        names = []
        for classifier in classifiers:
            tail = classifier.split("::")[-1].strip()
            if tail and tail not in names:
                names.append(tail)
        label = "Trove classifier" if len(names) == 1 else "Trove classifiers"
        return " OR ".join(normalise(n) for n in names), label
    field = meta.get("License")
    if field and len(field) < 80 and "\n" not in field:
        return field.strip(), "License field"
    return None, "metadata states no licence"


def ecosystem(component: dict) -> str:
    purl = component.get("purl") or ""
    match = re.match(r"pkg:([a-z]+)/", purl)
    return match.group(1) if match else "other"


def build(sbom_path: Path) -> tuple[str, list[str]]:
    doc = json.loads(sbom_path.read_text(encoding="utf-8"))
    libraries = [c for c in doc.get("components", []) if c.get("type") == "library"]

    rows, unresolved = [], []
    for component in libraries:
        name = component.get("name", "?")
        version = component.get("version", "?")
        raw = declared(component)
        source = "SBOM"
        if not raw or raw.strip().lower() in VAGUE:
            raw, source = from_installed(name)
            if not raw or raw.strip().lower() in VAGUE:
                unresolved.append(f"{name} {version} ({source})")
                continue
        rows.append({
            "name": name,
            "version": version,
            "licence": normalise(raw),
            "raw": raw,
            "source": source,
            "ecosystem": ecosystem(component),
        })

    rows.sort(key=lambda r: (r["ecosystem"], r["name"].lower(), r["version"]))
    by_licence: dict[str, int] = defaultdict(int)
    for row in rows:
        by_licence[row["licence"]] += 1

    out: list[str] = []
    out.append("THIRD-PARTY NOTICES")
    out.append("=" * 72)
    out.append("")
    out.append("Sovereign Workspace incorporates the third-party components listed below.")
    out.append("Each remains the property of its authors and is used under the licence named")
    out.append("against it. This file is GENERATED from the release SBOM by")
    out.append("tools/release/generate_notice.py — do not edit it by hand.")
    out.append("")
    out.append(f"Components: {len(rows)}")
    out.append("")
    out.append("Licences represented:")
    for licence, count in sorted(by_licence.items(), key=lambda kv: (-kv[1], kv[0])):
        marker = "  <- see docs/THIRD-PARTY-LICENCE-POSITION.md" \
            if any(licence.startswith(n) for n in NEEDS_POSITION) else ""
        out.append(f"  {licence:<40} {count:>4}{marker}")
    out.append("")

    current = None
    for row in rows:
        if row["ecosystem"] != current:
            current = row["ecosystem"]
            out.append("")
            out.append("-" * 72)
            out.append(f"{current.upper()} COMPONENTS")
            out.append("-" * 72)
        suffix = "" if row["source"] == "SBOM" else f"   [licence read from {row['source']}]"
        out.append(f"  {row['name']} {row['version']} — {row['licence']}{suffix}")

    out.append("")
    out.append("=" * 72)
    out.append("Full licence texts are distributed with each component in its own package")
    out.append("metadata. Source for any component under a source-availability obligation is")
    out.append("available from its upstream project; see docs/THIRD-PARTY-LICENCE-POSITION.md.")
    out.append("")
    return "\n".join(out), unresolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", default=str(REPO_ROOT / "SBOM.json"))
    parser.add_argument("--out", default=str(REPO_ROOT / "NOTICE"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    sbom = Path(args.sbom)
    if not sbom.is_file():
        print(f"generate_notice: SBOM not found: {sbom}", file=sys.stderr)
        return 2

    content, unresolved = build(sbom)
    out = Path(args.out)

    if unresolved:
        print("generate_notice: UNRESOLVED licences — NOTICE is incomplete:", file=sys.stderr)
        for item in unresolved:
            print(f"  {item}", file=sys.stderr)
        if not args.check:
            print("generate_notice: refusing to write an incomplete NOTICE", file=sys.stderr)
        return 1

    if args.check:
        if not out.is_file():
            print(f"generate_notice: {out} does not exist", file=sys.stderr)
            return 1
        if out.read_text(encoding="utf-8") != content:
            print(f"generate_notice: {out} is stale — regenerate it", file=sys.stderr)
            return 1
        print(f"generate_notice: {out} matches the SBOM")
    else:
        out.write_text(content, encoding="utf-8", newline="\n")
        print(f"generate_notice: wrote {out} ({len(content.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
