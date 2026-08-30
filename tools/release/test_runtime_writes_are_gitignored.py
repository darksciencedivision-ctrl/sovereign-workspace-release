#!/usr/bin/env python
"""Every adapter-declared runtime write must land OUTSIDE the tracked tree (LOCAL-01 F-6, OD-34).

THE DEFECT THIS EXISTS TO CATCH (N-29). `shell/modules/sow.json` declared
`${root}/docs/evidence/receipts` in `runtime_writes` and pointed its `receipt_file` readiness
probe at a file inside it — and that directory is **git-tracked**. So merely USING the product
wrote into the release candidate: every builder BOOT after anyone launched SOW found a dirty
tree, which is exactly what FIXUP-01's BOOT hit and what a later run hit again.

No gate in this programme caught it. The boundary gate rejects runtime state that reaches an
*archive*, and the manifest check verifies hashes — but nothing asserted the simpler property
that the product's own declaration of "I write here at runtime" must not name a place git is
watching. The declaration and the tracked-ness were each individually fine and only wrong
together, which is the shape a cross-cutting assertion catches and a per-file one never does.

REWRITTEN AT EPC-01 P4-4, AND THE PROPERTY IS NOW STRONGER.

This test used to assert that every write was rooted at `${root}` and then check the suffix
against a known-offender list, because at the time every write necessarily lived inside the
install tree and the only question was WHERE inside it. Runtime state now lives under
`${state_root}` — `%LOCALAPPDATA%/SovereignWorkspace/<module-id>` — so the tracked tree is not
merely avoided in the right places, it is left entirely.

The assertion therefore inverts. It is no longer "a `${root}` write must land in a gitignored
suffix"; it is "a write must be under `${state_root}`, and any `${root}` write that remains is
a declared exception that must ALSO be gitignored". Strictly stronger: the old form permitted
any number of `${root}` writes so long as their suffixes were ignored, and the new one permits
exactly the ones named below.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ADAPTER_DIR = os.path.join(WORKTREE_ROOT, "shell", "modules")

ROOT_TOKEN = "${root}/"
STATE_TOKEN = "${state_root}/"

#: Declared writes still rooted at `${root}`, each with the reason it has not moved.
#:
#: An entry here is a claim that the path is NOT pure runtime state. Every one is additionally
#: required to be gitignored by the test below, so the exemption cannot be used to smuggle a
#: write into the tracked tree.
ROOT_WRITE_EXCEPTIONS: dict[str, dict[str, str]] = {
    # EMPTY, and that is the point.
    #
    # debate's config.json was the last declared write still inside the install tree, and it
    # was git-TRACKED - the N-29 defect above, still live after every other module's state had
    # moved out. It is now seeded into the state root on first start and read from there, so
    # nothing the product writes at runtime names a path git is watching.
    #
    # An entry added here must ALSO pass the gitignore assertion below. The exemption says
    # "not pure runtime state"; it does not say "may dirty the tree".
}


def _adapters() -> list[tuple[str, dict]]:
    out = []
    for name in sorted(os.listdir(ADAPTER_DIR)):
        if not name.endswith(".json") or name == "schema.json":
            continue
        with open(os.path.join(ADAPTER_DIR, name), "r", encoding="utf-8") as handle:
            out.append((name, json.load(handle)))
    return out


def _is_ignored(relative_path: str) -> bool:
    """Ask git, rather than pattern-matching .gitignore ourselves."""
    proc = subprocess.run(
        ["git", "-C", WORKTREE_ROOT, "check-ignore", "-q", relative_path],
        capture_output=True,
    )
    return proc.returncode == 0


class RuntimeWritesLeaveTheTrackedTree(unittest.TestCase):

    def test_adapters_are_actually_read(self) -> None:
        """Without this the assertions below pass vacuously on an empty directory."""
        adapters = _adapters()
        self.assertGreaterEqual(
            len(adapters), 5, f"only {len(adapters)} adapters found in {ADAPTER_DIR}"
        )
        self.assertTrue(
            any(a.get("runtime_writes") for _, a in adapters),
            "no adapter declares any runtime_writes — this guard has gone blind"
        )

    def test_every_runtime_write_is_under_the_state_root_or_a_named_exception(self) -> None:
        offenders = []
        for name, adapter in _adapters():
            allowed = ROOT_WRITE_EXCEPTIONS.get(name, {})
            for write in adapter.get("runtime_writes", []):
                if write.startswith(STATE_TOKEN):
                    continue
                if write in allowed:
                    continue
                offenders.append(
                    f"{name}: {write!r} is neither under ${{state_root}} nor a named exception"
                )
        self.assertEqual(
            offenders, [],
            "runtime state must live outside the install tree. Move the write under "
            "${state_root}, or add it to ROOT_WRITE_EXCEPTIONS with the reason it is not "
            "runtime state:\n  " + "\n  ".join(offenders)
        )

    def test_every_named_exception_is_still_declared(self) -> None:
        """An exemption for a write that no longer exists is rot: it would silently permit the
        same path being reintroduced later."""
        declared = {
            name: set(adapter.get("runtime_writes", []))
            for name, adapter in _adapters()
        }
        stale = [
            f"{name}: {write!r} is exempted but no longer declared"
            for name, writes in ROOT_WRITE_EXCEPTIONS.items()
            for write in writes
            if write not in declared.get(name, set())
        ]
        self.assertEqual(stale, [], "\n  ".join([""] + stale))

    def test_every_named_exception_is_also_gitignored(self) -> None:
        """The exemption says 'not pure runtime state'. It does NOT say 'may dirty the tree'.

        This is the original defect's actual shape: a declaration and a tracked path that were
        each fine alone and only wrong together."""
        offenders = []
        for name, adapter in _adapters():
            module_root = str(adapter.get("root", "")).replace("\\", "/").rstrip("/")
            for write in ROOT_WRITE_EXCEPTIONS.get(name, {}):
                suffix = write[len(ROOT_TOKEN):]
                if not module_root:
                    continue
                # Reconstruct the repository-relative path the write resolves to.
                marker = "/modules/"
                if marker not in module_root:
                    continue
                relative = "modules/" + module_root.split(marker, 1)[1] + "/" + suffix
                if not _is_ignored(relative):
                    offenders.append(f"{name}: {relative} is tracked by git")
        self.assertEqual(
            offenders, [],
            "a declared runtime write names a path git is watching, so merely USING the "
            "product dirties the tree:\n  " + "\n  ".join(offenders)
        )

    def test_a_rotated_log_generation_is_gitignored_too(self) -> None:
        """EPC-01. `*.log` does not match `debate.log.1`.

        Every rotating logger here writes generations as `<name>.log.1`, `.log.2` and so on.
        `.gitignore` carried `*.log` and nothing else, so the live file was ignored and its
        rotations were not - and this suite did not notice, because it only ever checked
        declared runtime_writes paths, never the shapes a logger actually produces.

        Found by running the product rather than by reading it: a test run rotated
        modules/debate/logs/debate.log and left a 1,002,682-byte debate.log.1 staged for
        commit. A rotated log is the same class of artifact as the live one.

        Asked of `git check-ignore` rather than of the pattern text, so this tests the rule
        that will actually apply at `git add` time.
        """
        candidates = [
            "modules/debate/logs/debate.log",
            "modules/debate/logs/debate.log.1",
            "modules/debate/logs/debate.log.12",
            "shell/logs/shell.log.3",
            "modules/sow/logs/anything.log.5",
        ]
        # BYTES, not text=True. On Windows, Python translates "\n" in `input` to
        # "\r\n", so git receives each path with a trailing CR, treats the CR as part of
        # the FILENAME, and quotes the result. `*.log` then fails to match `debate.log<CR>`
        # while `*.log.[0-9]*` still matches `debate.log.1<CR>` - a confidently wrong answer
        # in BOTH directions. Measured, not guessed: that is what this test did on its
        # first run, reporting three ignored paths as unignored.
        result = subprocess.run(
            ["git", "-C", WORKTREE_ROOT, "check-ignore", "--stdin"],
            input="\n".join(candidates).encode("utf-8"),
            capture_output=True, timeout=300,
        )
        ignored = {
            line.strip().replace("\\", "/")
            for line in result.stdout.decode("utf-8", "replace").splitlines()
        }
        missed = [c for c in candidates if c not in ignored]
        self.assertEqual(
            missed, [],
            "these runtime log paths are NOT gitignored and would ship if one appeared:\n  "
            + "\n  ".join(missed)
        )

    def test_no_rotated_log_is_currently_tracked(self) -> None:
        """The ignore rule protects the future; this checks the present."""
        tracked = subprocess.run(
            ["git", "-C", WORKTREE_ROOT, "ls-files"],
            capture_output=True, text=True, timeout=300,
        ).stdout.splitlines()
        offenders = [
            path for path in tracked
            if re.search(r"\.log(\.\d+)?$", path) and "/tests/" not in path
        ]
        self.assertEqual(offenders, [], f"log files are tracked in git: {offenders}")

    def test_no_adapter_declares_a_write_into_another_modules_state(self) -> None:
        """`${state_root}` is per module. A literal path naming a different module's state
        would defeat that, and is refused by the compiler — asserted here at the declaration
        level too, so it is visible in the adapter rather than only at load time."""
        offenders = []
        for name, adapter in _adapters():
            module_id = adapter.get("id", "")
            for write in adapter.get("runtime_writes", []):
                lowered = write.replace("\\", "/").lower()
                if "sovereignworkspace/" not in lowered:
                    continue
                after = lowered.split("sovereignworkspace/", 1)[1]
                named = after.split("/", 1)[0]
                if named and named != module_id.lower():
                    offenders.append(f"{name}: writes into {named!r}'s state root")
        self.assertEqual(offenders, [], "\n  ".join([""] + offenders))


if __name__ == "__main__":
    sys.exit(unittest.main())
