#!/usr/bin/env python3
"""Rebase the inventoried shell adapter paths from install.json."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

OLD_ROOT = "D:/Product Software/Production Workspace"
INVENTORY = {
    "debate.json": ("/root",),
    "distillery.json": ("/root", "/launch/argv/0", "/launch/argv/1"),
    "llamacpp.json": ("/root", "/launch/argv/0", "/launch/argv/6"),
    "schema.json": (),
    "sovereign.json": ("/root",),
    "sow.json": ("/root",),
    "tokencenter.json": ("/root", "/launch/argv/0", "/launch/argv/1"),
}

# CLOSEOUT-01 X-4 (N-18). Pointers whose value IS the Python interpreter. These
# are set from install.json's python_312 UNCONDITIONALLY: the interpreter of the
# destination install is a fact of the destination, never something to be
# inherited from whatever the source machine happened to have. The previous
# logic rewrote the interpreter only when it exactly equalled a hardcoded
# source-machine constant, so neutralising the committed value would have made
# the rebase skip it in silence and produce an install pointing at an
# interpreter that does not exist.
#
# This is declared per adapter and NOT as a blanket rule on "/launch/argv/0".
# llamacpp.json also has a /launch/argv/0, but its value is
# .../llama.cpp/current/llama-server.exe -- a native server binary, not an
# interpreter. Overwriting it with python_312 would break that adapter. argv[0]
# is the interpreter only where the launch is a Python launch.
INTERPRETER_POINTERS = {
    "distillery.json": ("/launch/argv/0",),
    "tokencenter.json": ("/launch/argv/0",),
}


def _tokens(pointer: str) -> list[str]:
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def _get(document: object, pointer: str) -> object:
    current = document
    for token in _tokens(pointer):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _set(document: object, pointer: str, value: str) -> None:
    tokens = _tokens(pointer)
    current = document
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    if isinstance(current, list):
        current[int(tokens[-1])] = value
    else:
        current[tokens[-1]] = value


def _mapped(
    value: str,
    modules_root: str,
    source_modules_root: str = OLD_ROOT,
) -> str:
    normalized_value = value.replace("\\", "/")
    prefixes = (source_modules_root, OLD_ROOT)
    for prefix in prefixes:
        normalized_prefix = str(prefix).replace("\\", "/").rstrip("/")
        if normalized_value == normalized_prefix or normalized_value.startswith(normalized_prefix + "/"):
            suffix = normalized_value[len(normalized_prefix):].replace("/", "\\")
            return str(Path(modules_root)) + suffix
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--dry-run", action="store_true")
    return parser


def run(root: Path, dry_run: bool = False) -> int:
    root = root.resolve()
    install_path = root / "shell" / "config" / "install.json"
    modules_dir = root / "shell" / "modules"
    try:
        install = json.loads(install_path.read_text(encoding="utf-8"))
        modules_root = str(Path(install["modules_root"]).resolve())
        python_312 = str(Path(install["python_312"]).resolve())
        source_modules_root = str(install.get("source_modules_root") or OLD_ROOT)
        optional_adapters = install.get("optional_adapters", [])
        if not isinstance(optional_adapters, list) or not all(
            isinstance(name, str) for name in optional_adapters
        ):
            raise ValueError("optional_adapters must be a list of adapter names")
        known_adapters = {Path(name).stem for name in INVENTORY}
        unknown_adapters = sorted(set(optional_adapters) - known_adapters)
        if unknown_adapters:
            raise ValueError(
                "optional_adapters contains unknown adapter(s): "
                + ", ".join(unknown_adapters)
            )
        optional_adapters = set(optional_adapters)
        documents = {
            name: json.loads((modules_dir / name).read_text(encoding="utf-8"))
            for name in INVENTORY
        }
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    changes: list[tuple[str, str, str, str]] = []
    for name, pointers in INVENTORY.items():
        interpreter_pointers = INTERPRETER_POINTERS.get(name, ())
        for pointer in pointers:
            old = _get(documents[name], pointer)
            if not isinstance(old, str):
                print(f"ERROR: {name}{pointer} is not a string", file=sys.stderr)
                return 2
            if pointer in interpreter_pointers:
                new = python_312
            else:
                new = _mapped(old, modules_root, source_modules_root)
            if new != old:
                changes.append((name, pointer, old, new))

    missing_by_adapter: dict[str, list[str]] = {}
    for name, _, _, new in changes:
        if not Path(new).exists():
            missing_by_adapter.setdefault(Path(name).stem, []).append(new)

    fatal_missing = {
        adapter: sorted(set(paths))
        for adapter, paths in missing_by_adapter.items()
        if adapter not in optional_adapters
    }
    if fatal_missing:
        for name, pointer, old, new in changes:
            print(f"{name}{pointer}: {old!r} -> {new!r}")
        for paths in fatal_missing.values():
            for path in paths:
                print(f"ERROR: target path does not exist: {path}", file=sys.stderr)
        return 2

    skipped = sorted(set(missing_by_adapter) & optional_adapters)
    for adapter in skipped:
        paths = sorted(set(missing_by_adapter[adapter]))
        print(f"SKIPPED-WITH-RECORD {adapter}: missing target(s): {'; '.join(paths)}")

    active_changes = [
        change for change in changes if Path(change[0]).stem not in skipped
    ]
    if not active_changes:
        print("NO-OP")
        return 0

    for name, pointer, old, new in active_changes:
        print(f"{name}{pointer}: {old!r} -> {new!r}")
    if dry_run:
        return 0

    touched = {name for name, _, _, _ in active_changes}
    for name in sorted(touched):
        source = modules_dir / name
        backup = modules_dir / f"{name}.pre-rebase"
        if not backup.exists():
            shutil.copyfile(source, backup)
        for changed_name, pointer, _, new in active_changes:
            if changed_name == name:
                _set(documents[name], pointer, new)
        source.write_text(json.dumps(documents[name], indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run(args.root, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
