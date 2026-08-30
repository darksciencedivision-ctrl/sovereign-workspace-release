"""Repository-root pytest anchor.

EPC-01 P1-4 / P1-5. Before this file existed there was no way to run the product's tests
as one suite:

  * `modules/sow/conftest.py` raised `ValueError` on any item collected outside its own
    module and pytest turned that into an `INTERNALERROR` that aborted the entire run —
    including on a customer's extracted archive, where `pytest` at the root crashed rather
    than reporting. Fixed in that file.
  * Underneath the crash, five separate trees each ship a `tests/` package. Under pytest's
    default prepend import mode those collide by basename: the first `tests` package to be
    imported wins and every other module's `tests.*` submodule fails to resolve. That
    accounted for most of the 119 collection errors the crash was hiding.
  * Several modules import their own top-level packages (`distillery.*`, `piggybank`) which
    resolve only when that module's root is on `sys.path`.

The collision is solved by `--import-mode=importlib` in `pytest.ini` beside this file, which
imports test modules without touching `sys.path` at all. This file solves the third point:
each module root is placed on `sys.path` so a module's own packages import the same way they
do when that module is tested on its own.

Running a single module directly still works and still uses that module's own configuration:
pytest resolves the nearest ini file upward from the arguments, so `cd modules/sow && pytest`
continues to use `modules/sow/pytest.ini` and never sees this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#: Roots whose own packages must be importable. Order is deliberate and stable — a
#: non-deterministic sys.path is a non-deterministic test run.
MODULE_ROOTS = [
    ROOT,
    ROOT / "modules" / "sow",
    ROOT / "modules" / "distillery",
    ROOT / "modules" / "debate",
    ROOT / "modules" / "sovereign",
    ROOT / "modules" / "tokencenter",
]

for path in reversed(MODULE_ROOTS):
    if path.is_dir():
        text = str(path)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)


# Bind the ambiguous top-level name `tests` DETERMINISTICALLY, before collection starts.
#
# Two trees ship a `tests` package: modules/sow (whose helpers are imported as
# `tests.support`, `tests.fixtures`, `tests.unit`, `tests.live_call_guard`,
# `tests.host_prerequisites`, `tests.js_skip_policy`) and modules/distillery (whose
# `__init__.py` is a lone docstring that nothing imports). Collection runs alphabetically, so
# distillery is reached first, `tests` lands in sys.modules bound to ITS package, and every
# one of SOW's eleven `from tests.…` modules then fails to collect — sys.path order cannot
# help, because the name is already cached.
#
# Importing it here, first, settles the name once. This is additive: distillery's package is
# left exactly as it is, and nothing in distillery imports `tests` by name, so nothing there
# changes behaviour.
_SOW_TESTS = ROOT / "modules" / "sow" / "tests" / "__init__.py"
if _SOW_TESTS.is_file() and "tests" not in sys.modules:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "tests", _SOW_TESTS, submodule_search_locations=[str(_SOW_TESTS.parent)]
    )
    if _spec is not None and _spec.loader is not None:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["tests"] = _module
        _spec.loader.exec_module(_module)
