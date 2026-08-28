"""Bytecode discipline shared by every Python mutation harness (CU-A1; U534/U539).

THE DEFECT (U529): a harness restores mutated source by a plain byte-identical write.
Identical bytes preserve SIZE; when the restore lands in the one-second mtime bucket the
mutant compile happened in, CPython passes its (mtime, size) freshness check and every later
import is served MUTANT bytecode from __pycache__ on an otherwise clean tree. The inverse
face is equally real (U534): a stale-but-fresh CORRECT pyc can mask MUTATED source.

THE REPAIR, applied identically by all twelve mutators:
  1. invalidate_for(path) immediately AFTER the mutant write and again AFTER every restore
     write (the run_one finally AND the signal-handler restore-all) - unlinking derived
     bytecode does not depend on mtime at all;
  2. child_env() on EVERY grading subprocess, so PYTHONDONTWRITEBYTECODE=1 prevents any pyc
     from being created inside a mutation window.

PYTHONPYCACHEPREFIX mandated from a runner would be an environment workaround, not an
instrument repair, and leaves developer invocations exposed; it is deliberately NOT used.
This module unlinks only bytecode cache entries adjacent to the repository files the harness
itself wrote; it deletes no cache tree and touches nothing outside the repository.
"""
from __future__ import annotations

import os
from pathlib import Path


def invalidate_for(*repo_paths):
    """Unlink any bytecode cache entry derived from the given tracked sources.

    Covers both layouts: __pycache__/<stem>.cpython-*.pyc beside a package module and the
    legacy <dir>/<stem>.pyc. Best effort: an entry that cannot be unlinked is skipped,
    never raised - grading must not crash on a hygiene no-op. Returns the removed names.
    """
    removed = []
    seen = set()
    for raw in repo_paths:
        p = Path(raw)
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file():
            continue
        for cache_dir in (p.parent / "__pycache__", p.parent):
            try:
                entries = list(cache_dir.iterdir())
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                if not name.endswith(".pyc"):
                    continue
                stem = name.split(".")[0] if cache_dir.name == "__pycache__" else name[:-4]
                if stem != p.stem:
                    continue
                try:
                    entry.unlink()
                    removed.append(str(cache_dir / name))
                except OSError:
                    pass
    return removed


def child_env(base=None):
    """An environment copy for grading subprocesses that writes NO bytecode caches."""
    env = dict(os.environ if base is None else base)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env
