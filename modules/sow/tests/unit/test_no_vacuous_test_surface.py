"""A declared test directory contains tests (punch list 2.10, W-28).

MEASURED BEHAVIOUR, recorded correctly:

    py -3.12 -m pytest tests/security  ->  exit 5, "no tests ran"

Exit 5 is pytest's NO_TESTS_COLLECTED. It is not a silent green by itself — but
a runner that treats "not 1" as success reads it as one, and a command like

    pytest tests/integration tests/security tests/recovery tests/evaluation

reads as though a security suite ran when `tests/security/` held nothing but a
`.gitkeep`. Several committed evidence reports contain exactly that command.

THE PROBLEM IS SIMPLER THAN A WRAPPER BUG: the repository advertised a test
surface that contained no tests. The fix is to stop advertising it, not to teach
a runner that exit 5 is acceptable.

Where the security assertions actually live: throughout `tests/unit/` and
`tests/integration/`, next to the code they constrain — 75 files carry
injection / escalation / credential / forgery / spoofing / bypass assertions.
That is the right place for them, and moving them into a directory named after a
category would be a reorganisation, not a repair.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "tests"

#: Directories under `tests/` that legitimately hold NO test modules, each named deliberately.
#: Anything else under `tests/` is a test surface and must carry tests.
NON_TEST_DIRECTORIES: dict[str, str] = {
    "fixtures": "sample inputs consumed by tests; contains data, not assertions",
    "support": "shared helpers imported by tests; contains code, not assertions",
    "__pycache__": "interpreter artefact",
}


def _test_surfaces() -> list[Path]:
    return [p for p in sorted(TESTS.iterdir())
            if p.is_dir() and p.name not in NON_TEST_DIRECTORIES]


@pytest.mark.parametrize("surface", _test_surfaces(), ids=lambda p: p.name)
def test_every_declared_test_directory_actually_contains_tests(surface: Path) -> None:
    """The guard. A directory under `tests/` that carries no test module is a surface that reads
    as assurance and provides none — and `pytest <that dir>` exits 5, which a runner comparing
    against 1 will accept."""
    modules = sorted(p.name for p in surface.rglob("test_*.py"))
    assert modules, (
        f"tests/{surface.name}/ is presented as a test surface but contains no test module. "
        f"Populate it with assertions that genuinely belong there, or remove it — do not leave a "
        f"directory that makes a pytest invocation look broader than it is. "
        f"(If it is support code, declare it in NON_TEST_DIRECTORIES with a reason.)")


@pytest.mark.parametrize("name,reason", sorted(NON_TEST_DIRECTORIES.items()))
def test_every_non_test_directory_exemption_is_real_and_reasoned(name: str, reason: str) -> None:
    """An exemption for a directory that no longer exists is a rule nobody follows; an exemption
    for one that DOES hold tests is hiding them from this guard."""
    path = TESTS / name
    if not path.exists():
        pytest.skip(f"tests/{name}/ is not present on this tree")
    assert reason.strip(), f"tests/{name}/ is exempt with no reason"
    assert not sorted(path.rglob("test_*.py")), (
        f"tests/{name}/ is exempt from the test-surface guard but DOES contain test modules")
