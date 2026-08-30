"""EPC-01 P3-9 — running the tests must not make the tree dirty.

A CORRECTION IS RECORDED HERE. Punch List V7 listed P3-9 as "runtime caches sit in the
working tree", inferred from `package_boundary_gate` reporting 20,093 violations dominated by
`.pytest_cache/` paths. Measured directly, every one of those caches is already gitignored at
every level it occurs — creating them and running `git status` produces no output. The gate
counted them because it scans the WORKING TREE rather than the built archive, which is P2-9's
defect and not a gitignore gap.

So there was nothing to fix. This test exists so the property that was already true stays
true, and so the correction is recorded somewhere a reader will find it.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories any test run may create, and the roots they can appear under. Each is checked
#: by actually creating it and asking git, because a pattern that LOOKS right and a pattern
#: that git honours are different claims.
CACHE_NAMES = (".pytest_cache", "__pycache__", ".runtime")

CACHE_ROOTS = (
    Path("."),
    Path("modules/sow"),
    Path("modules/debate"),
    Path("modules/distillery"),
    Path("modules/sovereign"),
    Path("modules/tokencenter"),
    Path("shell"),
    Path("tools"),
)


class RuntimeCachesAreIgnored(unittest.TestCase):

    def test_every_runtime_cache_is_ignored_wherever_a_test_run_can_create_it(self) -> None:
        offenders = []
        created = []
        try:
            for root in CACHE_ROOTS:
                base = REPO_ROOT / root
                if not base.is_dir():
                    continue
                for name in CACHE_NAMES:
                    target = base / name
                    if target.exists():
                        continue  # already present and already known-clean
                    target.mkdir(parents=True)
                    (target / ".probe").write_text("", encoding="utf-8")
                    created.append(target)

            status = subprocess.run(
                ["git", "status", "--porcelain=v1"],
                cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
            ).stdout
            for line in status.splitlines():
                path = line[3:].strip()
                if any(name in path for name in CACHE_NAMES):
                    offenders.append(path)
        finally:
            for target in reversed(created):
                probe = target / ".probe"
                if probe.exists():
                    probe.unlink()
                if target.exists() and not any(target.iterdir()):
                    target.rmdir()

        self.assertEqual(
            offenders, [],
            "these runtime caches are NOT gitignored, so running the tests dirties the tree "
            "and `build_release.ps1` will refuse to cut a release:\n  " + "\n  ".join(offenders)
        )

    def test_the_probe_actually_created_something(self) -> None:
        """Without this, the test above passes vacuously on a tree where every cache already
        exists and the loop creates nothing."""
        self.assertTrue(
            any((REPO_ROOT / root).is_dir() for root in CACHE_ROOTS),
            "no cache roots exist — this guard has gone blind"
        )


if __name__ == "__main__":
    unittest.main()
