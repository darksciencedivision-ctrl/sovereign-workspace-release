#!/usr/bin/env python
"""Every adapter-declared runtime write must land OUTSIDE the tracked tree (LOCAL-01 F-6, OD-34).

THE DEFECT THIS EXISTS TO CATCH (N-29). `shell/modules/sow.json` declared
`${root}/docs/evidence/receipts` in `runtime_writes` and pointed its `receipt_file` readiness probe
at a file inside it — and that directory is **git-tracked**. So merely USING the product wrote into
the release candidate: every builder BOOT after anyone launched SOW found a dirty tree, which is
exactly what FIXUP-01's BOOT hit and what this run's BOOT hit again.

No gate in this program caught it. The boundary gate rejects runtime state that reaches an
*archive*, and the manifest check verifies hashes — but nothing asserted the simpler property that
the product's own declaration of "I write here at runtime" must not name a place git is watching.
The declaration and the tracked-ness were each individually fine and only wrong together, which is
the shape a cross-cutting assertion catches and a per-file one never does.

This is the N-16 rule, generalised: runtime evidence lives in a gitignored lane. It is asserted for
EVERY adapter, not just SOW, so the next module to declare a runtime write cannot reintroduce it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ADAPTER_DIR = os.path.join(WORKTREE_ROOT, "shell", "modules")

#: `${root}` in an adapter path is the module's own directory. Which module a given adapter names is
#: not this test's business — what matters is the SUFFIX below `${root}`, because that is the part
#: that decides whether git is watching it.
ROOT_TOKEN = "${root}/"


def _adapters() -> list[tuple[str, dict]]:
    out = []
    for name in sorted(os.listdir(ADAPTER_DIR)):
        if not name.endswith(".json") or name == "schema.json":
            continue
        with open(os.path.join(ADAPTER_DIR, name), "r", encoding="utf-8") as handle:
            out.append((name, json.load(handle)))
    return out


def _module_root(adapter: dict, adapter_name: str) -> str:
    """The real directory `${root}` stands for, from the adapter's own id."""
    return os.path.join(WORKTREE_ROOT, "modules", str(adapter.get("id") or adapter_name[:-5]))


def _declared_runtime_paths(adapter: dict) -> list[str]:
    """Every path the adapter says the product writes to at runtime.

    Both surfaces count. `runtime_writes` is the declaration; a `receipt_file` readiness path is a
    runtime write whether or not it is also listed there — the probe exists because the product
    creates that file on launch.
    """
    paths = [p for p in (adapter.get("runtime_writes") or []) if isinstance(p, str)]
    readiness = adapter.get("readiness") or {}
    if readiness.get("kind") == "receipt_file" and isinstance(readiness.get("path"), str):
        paths.append(readiness["path"])
    return paths


def _is_ignored(path: str) -> bool:
    """Does git ignore this path? Asked of GIT, not of a copy of the ignore rules.

    `check-ignore` answers for a path that does not exist yet, which is the case that matters: the
    assertion must hold on a clean clone where no runtime file has been written.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=WORKTREE_ROOT, capture_output=True, check=False,
    )
    return result.returncode == 0


#: KNOWN OFFENDERS, recorded as LOCAL-01 **N-38** — every one found by this test on its first run.
#:
#: OD-34 rules on SOW's receipt path, and F-6 fixes that one. Writing the assertion generally
#: immediately showed the same defect in FOUR other adapters: N-29 is not one instance, it is the
#: **fifth through eleventh** instance of the N-16 class, and nothing in this program had noticed.
#: `debate.json` is the sharpest of them — Debate PERSISTS a seat-model change back into its own
#: tracked `config.json`, so using the product's own model dropdown edits the release candidate.
#:
#: They are pinned rather than fixed because each is another module's runtime contract and outside
#: this run's authorized item set (S-9: park, do not improvise). The set may only ever SHRINK: a new
#: offender fails this test, so the class cannot grow while the operator decides on these seven.
KNOWN_TRACKED_RUNTIME_WRITES = frozenset({
    ("debate.json", "${root}/config.json"),
    ("distillery.json", "${root}/logs"),
    ("llamacpp.json", "${root}/logs"),
    ("sovereign.json", "${root}/runtime"),
    ("sovereign.json", "${root}/published"),
    ("sovereign.json", "${root}/library/queues"),
    ("sovereign.json", "${root}/logs"),
})


class RuntimeWritesLeaveTheTrackedTree(unittest.TestCase):
    def test_no_adapter_declares_a_NEW_tracked_runtime_write(self) -> None:
        """The ratchet. Every offender must already be in the recorded N-38 set."""
        offenders = []
        checked = 0
        for name, adapter in _adapters():
            root = _module_root(adapter, name)
            for declared in _declared_runtime_paths(adapter):
                if not declared.startswith(ROOT_TOKEN):
                    # An absolute or otherwise unrooted declaration is out of this test's reach;
                    # record it rather than passing it silently.
                    offenders.append(f"{name}: {declared!r} is not rooted at ${{root}}")
                    continue
                resolved = os.path.join(root, declared[len(ROOT_TOKEN):].replace("/", os.sep))
                checked += 1
                if not _is_ignored(resolved) and (name, declared) not in KNOWN_TRACKED_RUNTIME_WRITES:
                    offenders.append(
                        f"{name}: declares a runtime write at {declared!r}, which git TRACKS "
                        f"({os.path.relpath(resolved, WORKTREE_ROOT)}) — using the product would "
                        f"dirty the release candidate (OD-34/N-29). Move it to a gitignored lane, "
                        f"as N-16 did for the shell."
                    )
        self.assertTrue(checked, "no adapter runtime writes were checked — the test found nothing")
        self.assertFalse(offenders, "\n  ".join([""] + offenders))

    def test_the_known_offender_list_does_not_rot(self) -> None:
        """A pinned defect that has been fixed must leave the list, or the list stops meaning
        anything. Every recorded offender must still BE one."""
        stale = []
        for name, adapter in _adapters():
            root = _module_root(adapter, name)
            declared = set(_declared_runtime_paths(adapter))
            for known_name, known_path in KNOWN_TRACKED_RUNTIME_WRITES:
                if known_name != name:
                    continue
                if known_path not in declared:
                    stale.append(f"{known_name}: no longer declares {known_path!r}")
                elif _is_ignored(os.path.join(root, known_path[len(ROOT_TOKEN):].replace("/", os.sep))):
                    stale.append(f"{known_name}: {known_path!r} is gitignored now — remove it "
                                 f"from KNOWN_TRACKED_RUNTIME_WRITES (N-38 shrinks)")
        self.assertFalse(stale, "\n  ".join([""] + stale))

    def test_sow_is_not_among_the_known_offenders(self) -> None:
        """F-6's own row: SOW is FIXED, not pinned. It must never be added to the list."""
        self.assertFalse([p for n, p in KNOWN_TRACKED_RUNTIME_WRITES if n == "sow.json"])

    def test_the_sow_receipt_lane_is_the_gitignored_runtime_lane(self) -> None:
        """The specific row OD-34 rules on, pinned by name so a silent revert is loud."""
        path = os.path.join(ADAPTER_DIR, "sow.json")
        with open(path, "r", encoding="utf-8") as handle:
            sow = json.load(handle)
        declared = _declared_runtime_paths(sow)
        self.assertIn("${root}/.runtime/receipts", declared)
        self.assertIn("${root}/.runtime/receipts/SHELL-LIVE-READY.json", declared)
        for entry in declared:
            self.assertNotIn(
                "docs/evidence/receipts", entry,
                "SOW must not declare a runtime write inside the tracked evidence tree (OD-34)")

    def test_the_historical_receipts_are_left_where_they_are(self) -> None:
        """OD-34: "Existing tracked receipts are history: leave them, stop writing new ones there."

        Relocating the WRITE must not become a deletion of the record. The gate receipts committed
        by the phases that produced them stay tracked and untouched.
        """
        historical = os.path.join(
            WORKTREE_ROOT, "modules", "sow", "docs", "evidence", "receipts")
        self.assertTrue(os.path.isdir(historical),
                        "the historical receipt directory must still exist")
        tracked = subprocess.run(
            ["git", "ls-files", "modules/sow/docs/evidence/receipts"],
            cwd=WORKTREE_ROOT, capture_output=True, text=True, check=False).stdout.split()
        self.assertGreater(len(tracked), 0,
                           "the historical gate receipts must remain tracked as history")


if __name__ == "__main__":
    unittest.main()
