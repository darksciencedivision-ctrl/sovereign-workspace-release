"""CU-A1 acceptance instruments (U534/U539): mutation-harness bytecode discipline.

U529's defect: a byte-identical plain-write restore preserves size, and a restore landing in
the compile's one-second mtime bucket preserves the freshness key, so a fresh interpreter is
served MUTANT bytecode from __pycache__ afterwards - or, inversely, a stale CORRECT pyc masks
mutated source. Proven RED pre-repair at this HEAD by the persisted cycle probe:
"RED - MUTANT BEHAVIOUR SERVED THROUGH A PASSING (mtime,size) FRESHNESS CHECK".

Both behavioural tests drive REAL fresh interpreters with the cache-isolation variables
explicitly absent, against REAL files under pytest tmp_path. No repository file is touched.
The first pins the MECHANISM (it stays green after the repair; if it ever goes green for the
wrong reason - e.g. CPython changes its freshness rule - the premise moved and both rows must
be re-derived). The second is the acceptance: the disciplined cycle leaves NO pyc derived
from mutated source anywhere reachable and correct behaviour for every later importer.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import time

import pytest

_TOOLS_MUTATION = (
    pathlib.Path(__file__).resolve().parents[2] / "tools" / "mutation"
)
_SPEC = importlib.util.spec_from_file_location(
    "_bytecode_discipline", _TOOLS_MUTATION / "_bytecode_discipline.py"
)
_discipline = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_discipline)

_ORIGINAL = b'GROK_DISPLAY = "Grok Build"\n'
_MUTATED = b'GROK_DISPLAY = "Gemini CLI"\n'


def _no_isolation_env():
    """A real environment with every bytecode-cache isolation variable ABSENT."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")
    }


def _fresh_label(pkg: pathlib.Path, env) -> str:
    child = (
        "import sys; sys.path.insert(0, r'%S%'); "
        "import mod_under_test as m; print(m.GROK_DISPLAY)"
    ).replace("%S%", str(pkg))
    proc = subprocess.run(
        [sys.executable, "-c", child], capture_output=True, text=True,
        env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return (proc.stdout or "").strip()


def _cycle(tmp_path: pathlib.Path, disciplined: bool):
    """The harness cycle: splice -> graded window -> byte-identical restore.

    The restore's mtime is pinned back into the compile's integer-second bucket when the
    natural write already missed it. That bucket coincidence is the race U529 turned on;
    pinning it makes the mechanism DETERMINISTIC here, and the repair under test must not
    depend on the race in either direction (its answer is unlinking, which is unconditional).
    """
    pkg = tmp_path / "u08_pkg"
    pkg.mkdir()
    mod = pkg / "mod_under_test.py"
    plain = _no_isolation_env()
    # Deterministic buckets: the original compile is keyed to second b0, the mutant compile
    # to b0+1, and the byte-identical restore lands EXACTLY inside the mutant compile's
    # bucket - the coincidence U529 turned on, held fixed instead of slept for.
    b0 = int(time.time()) - 2
    mod.write_bytes(_ORIGINAL)
    os.utime(mod, (b0 + 0.5, b0 + 0.5))
    label_before = _fresh_label(pkg, plain)  # compiles a CORRECT pyc keyed (b0, size)
    assert label_before == "Grok Build"

    mod.write_bytes(_MUTATED)  # harness mutate: plain write, equal length
    os.utime(mod, (b0 + 1.5, b0 + 1.5))  # the mutant carries its OWN distinct bucket
    if disciplined:
        _discipline.invalidate_for(mod)
        grader_env = {**plain, "PYTHONDONTWRITEBYTECODE": "1"}
    else:
        grader_env = plain
    mid = _fresh_label(pkg, grader_env)  # the graded window sees the mutant

    mod.write_bytes(_ORIGINAL)  # byte-identical plain-write restore ...
    os.utime(mod, (b0 + 1.5, b0 + 1.5))  # ... landing INSIDE the compile bucket
    assert mod.read_bytes() == _ORIGINAL
    if disciplined:
        _discipline.invalidate_for(mod)

    pycs = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*.pyc"))
    final = _fresh_label(pkg, plain)  # fresh interpreter, NO cache isolation
    return mid, final, pycs, mod


def test_undisciplined_cycle_serves_mutant_bytecode_through_a_passing_freshness_check(
    tmp_path,
):
    mid, final, pycs, mod = _cycle(tmp_path, disciplined=False)
    assert mid == "Gemini CLI"  # the graded window really executed the mutant
    assert len(pycs) == 1 and "mod_under_test" in pycs[0]
    raw = (tmp_path / "u08_pkg" / pycs[0]).read_bytes()
    flags, header_mtime, header_size = struct.unpack("<III", raw[4:16])
    assert flags == 0
    assert header_mtime == int(mod.stat().st_mtime)  # == b0+1: the mutant compile bucket
    assert header_size == len(_ORIGINAL)
    assert final == "Gemini CLI"  # mutant behaviour served on an all-correct tree


def test_disciplined_cycle_leaves_no_mutant_pyc_and_serves_correct_bytes(tmp_path):
    mid, final, pycs, _mod = _cycle(tmp_path, disciplined=True)
    assert mid == "Gemini CLI"  # the repair does not blind the harness to its own mutation
    assert pycs == []  # no bytecode derived from mutated source survives anywhere reachable
    assert final == "Grok Build"  # a fresh non-isolated interpreter imports TRUE behaviour


def test_every_python_mutator_wires_the_discipline():
    """Structural inventory guard over the twelve mutators (behaviour above is primary).

    wsl_path_hermeticity_check.py mutates nothing and is vacuously out of scope (U534);
    the shared helper itself is excluded.
    """
    expected = {
        "_op12_close_mutations.py",
        "_op13_permission_mode_mutations.py",
        "_op18c_close_mutations.py",
        "_op18c_probe_path_mutations.py",
        "_op18d_amendment_mutations.py",
        "_op18d_close_mutations.py",
        "_op18e_electron_wiring_mutations.py",
        "_op18e_hardening_mutations.py",
        "_op18e_live_acceptance_mutations.py",
        "_op18e_live_shape_mutations.py",
        "_op19_5_write_path_mutations.py",
        "_op19_policy_delegation_mutations.py",
    }
    present = {
        p.name
        for p in _TOOLS_MUTATION.glob("_*.py")
        if p.name not in ("_bytecode_discipline.py", "wsl_path_hermeticity_check.py")
    }
    assert present == expected
    for name in sorted(expected):
        text = (_TOOLS_MUTATION / name).read_text(encoding="utf-8")
        assert "import _bytecode_discipline as _discipline" in text, name
        assert text.count("_discipline.invalidate_for(") >= 2, name
        assert "_discipline.child_env()" in text, name
