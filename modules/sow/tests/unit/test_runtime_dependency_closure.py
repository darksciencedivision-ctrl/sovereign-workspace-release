"""EPC-01 P0-2 — the runtime dependency declaration must cover what runtime code imports.

The defect this file exists to prevent, stated exactly as it happened: `jsonschema` was
imported by TWELVE runtime modules and declared only in `requirements-dev.txt`, unpinned.
`tools/release/install.ps1` provisioned Python for SOVEREIGN and Debate and never for SOW,
while `apps/desktop/main.js` spawned the SYSTEM interpreter. On a clean Windows host with
Python 3.12 and no ambient `jsonschema`, the IPC gateway died on import at first launch.

Asserting "jsonschema is in requirements.txt" would close this instance and nothing else.
These tests assert the GENERAL property instead: every third-party package that runtime
code imports is declared in the runtime requirements file, pinned, or carries a recorded
exemption. A thirteenth module importing a fourteenth package fails here, at commit time,
rather than on a customer's machine.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

SOW_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = SOW_ROOT / "requirements.txt"

#: Directories that are NOT shipped runtime — their imports do not constrain the runtime
#: closure. `tools/live` is deliberately absent: the desktop app spawns fifteen scripts
#: from it, so it IS runtime.
NON_RUNTIME_PARTS = {"tests", "test", "__pycache__", "node_modules", ".venv", "docs"}

#: Test infrastructure that lives OUTSIDE those directories and therefore needs naming.
#: `conftest.py` is pytest's own hook file; `tools/mutation` holds the falsification
#: harnesses wired to `npm run test:falsify`. Neither is executed by the shipped product,
#: so neither constrains the runtime closure.
NON_RUNTIME_FILES = {"conftest.py"}
NON_RUNTIME_PREFIXES = ("tools/mutation/",)

#: Packages a runtime module may import WITHOUT declaring, each with the reason it is
#: safe. An entry here is a claim that the import cannot fail the process; the test that
#: follows verifies the claim rather than trusting it.
GUARDED_OPTIONAL = {
    "tiktoken": (
        "control_plane/routing/token_meter.py imports it inside try/except with a "
        "word-proxy fallback; the product counts tokens either way and reports which "
        "method it used."
    ),
}


def _iter_runtime_python_files():
    for path in SOW_ROOT.rglob("*.py"):
        rel = path.relative_to(SOW_ROOT)
        if NON_RUNTIME_PARTS & set(rel.parts):
            continue
        if path.name in NON_RUNTIME_FILES:
            continue
        if rel.as_posix().startswith(NON_RUNTIME_PREFIXES):
            continue
        yield path


def _top_level_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:  # pragma: no cover - a syntax error is a different test's problem
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import -> first-party
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _first_party_names() -> set[str]:
    """Anything importable from inside the module tree is first-party, not a dependency."""
    # The excluded directories are still real, importable packages in this tree — the
    # exclusion above is about whose IMPORTS constrain the closure, not about what names
    # exist. `tools/run_phase19_gate.py` imports `tests`, and `tests` is first-party.
    names: set[str] = set(NON_RUNTIME_PARTS)
    for path in SOW_ROOT.rglob("*"):
        rel = path.relative_to(SOW_ROOT)
        if NON_RUNTIME_PARTS & set(rel.parts):
            continue
        if path.is_dir():
            names.add(path.name)
        elif path.suffix == ".py":
            names.add(path.stem)
    return names


def _declared() -> dict[str, str]:
    """requirement name (normalised) -> the exact pin line."""
    out: dict[str, str] = {}
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = re.split(r"[=<>!~\[]", line, maxsplit=1)[0].strip()
        out[name.lower().replace("_", "-")] = line
    return out


def test_a_runtime_requirements_file_exists() -> None:
    """SOW had none. SOVEREIGN and Debate both did; that asymmetry was the whole defect."""
    assert REQUIREMENTS.is_file(), (
        f"{REQUIREMENTS} is missing. Runtime dependencies declared only in "
        f"requirements-dev.txt are installed by nothing on a customer's machine."
    )


def test_every_runtime_third_party_import_is_declared() -> None:
    stdlib = set(sys.stdlib_module_names)
    first_party = _first_party_names()
    declared = _declared()

    undeclared: dict[str, list[str]] = {}
    for path in _iter_runtime_python_files():
        rel = path.relative_to(SOW_ROOT).as_posix()
        for name in _top_level_imports(path):
            if not name or name in stdlib or name in first_party:
                continue
            key = name.lower().replace("_", "-")
            if key in declared or name in GUARDED_OPTIONAL:
                continue
            undeclared.setdefault(name, []).append(rel)

    assert not undeclared, (
        "runtime modules import third-party packages that requirements.txt does not "
        "declare. Either add the pin, or import it under a guard and register it in "
        "GUARDED_OPTIONAL with the reason:\n  "
        + "\n  ".join(
            f"{pkg}  <- {len(files)} file(s), e.g. {sorted(files)[0]}"
            for pkg, files in sorted(undeclared.items())
        )
    )


def test_every_declared_runtime_requirement_is_pinned_exactly() -> None:
    """A floor is a promise the index can break. Two operators a month apart get one stack."""
    loose = [line for line in _declared().values() if "==" not in line]
    assert not loose, (
        "runtime requirements must pin exactly (==), not float:\n  " + "\n  ".join(loose)
    )


def test_jsonschema_specifically_is_declared_because_twelve_modules_import_it() -> None:
    """The named instance, kept as its own assertion so a regression reads unambiguously."""
    assert "jsonschema" in _declared(), (
        "jsonschema is imported by twelve SOW runtime modules. Declaring it only in "
        "requirements-dev.txt is what made the IPC gateway die on a clean machine."
    )


@pytest.mark.parametrize("package", sorted(GUARDED_OPTIONAL))
def test_each_guarded_optional_is_actually_guarded(package: str) -> None:
    """An exemption is a claim. Verify the import really cannot kill the process."""
    importers = [
        path for path in _iter_runtime_python_files()
        if package in _top_level_imports(path)
    ]
    assert importers, (
        f"{package} is registered in GUARDED_OPTIONAL but nothing imports it. "
        f"Remove the stale exemption."
    )
    for path in importers:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        guarded = False
        for handler_parent in ast.walk(tree):
            if not isinstance(handler_parent, ast.Try):
                continue
            for node in ast.walk(handler_parent):
                if isinstance(node, ast.Import) and any(
                    a.name.split(".")[0] == package for a in node.names
                ):
                    guarded = True
                elif isinstance(node, ast.ImportFrom) and node.module and \
                        node.module.split(".")[0] == package:
                    guarded = True
        assert guarded, (
            f"{path.relative_to(SOW_ROOT).as_posix()} imports {package} OUTSIDE a "
            f"try/except, so the exemption in GUARDED_OPTIONAL is false: a missing "
            f"{package} would kill the process. Either guard the import or declare "
            f"the package in requirements.txt."
        )
