"""F-121 / F-127 - legacy root resolution and publication formatting, regression-pinned.

Both repairs landed in 430d61e without a test naming them.

F-121: `_search_for_marker_root` iterated a SET of anchors (cwd, argv[0], __file__). str hashing is
randomised per process, so when the anchors lead to different marked roots the chosen root varied
between runs. The anchors are an ordered tuple now; this proves it from the outside by resolving the
same situation under several hash seeds.

F-127: `_provenance_header` built an f-string and then called `.format(version=...)` on it, so any
brace in a topic, tag or model name raised or was silently rewritten; `_LATEX_CMD_RE` removed every
backslash-word, turning "C:\\Users" into "C:".
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import format_alignmentforum as faf  # noqa: E402
from tools import sovereign_paths  # noqa: E402


class MarkerRootResolutionIsDeterministic(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="f121-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _marked_root(self, name: str) -> Path:
        root = self.tmp / name
        (root / "sandbox_agi").mkdir(parents=True)
        (root / sovereign_paths.ROOT_MARKER_NAME).write_text(sovereign_paths.ROOT_MARKER_CONTENT,
                                                             encoding="utf-8")
        return root

    def test_the_cwd_anchor_wins_under_every_hash_seed(self) -> None:
        cwd_root = self._marked_root("checkout")
        # __file__ lives under the real module root, which carries its own marker - a DIFFERENT
        # marked root. With a set, which one won depended on the process's string hash seed.
        probe = ("import sys; sys.path.insert(0, " + repr(str(MODULE_ROOT)) + "); "
                 "from tools import sovereign_paths as sp; print(sp._search_for_marker_root())")
        seen = set()
        for seed in ("0", "1", "2", "3", "17", "4242"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            env.pop("SOVEREIGN_ROOT", None)
            out = subprocess.run([sys.executable, "-c", probe], cwd=str(cwd_root), env=env,
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(0, out.returncode, out.stderr)
            seen.add(out.stdout.strip())
        self.assertEqual({str(cwd_root.resolve())}, seen)


class ProvenanceHeaderIsBraceSafe(unittest.TestCase):
    def test_braces_in_every_interpolated_field_are_kept_verbatim(self) -> None:
        manifest = {"gate_timestamp": "{gate}", "synthesis_tag": "{0}", "seeded_by": ["{x}"],
                    "gate_passed": True}
        header = faf._provenance_header("sess-{1}", "set {x} and {version} and {", manifest,
                                        ["tag {y}"], "{ts}")
        for literal in ("sess-{1}", "set {x} and {version} and {", "{gate}", "`{0}`", "{x}", "tag {y}", "{ts}"):
            self.assertIn(literal, header)
        self.assertIn(f"SOVEREIGN v{faf.SOVEREIGN_VERSION}", header)


class NormalisationKeepsWindowsPaths(unittest.TestCase):
    def test_backslash_words_without_braces_survive(self) -> None:
        text = faf._normalize_for_af(r"Stored at C:\Users\operator\notes and \textbf{bold}.")
        self.assertIn(r"C:\Users\operator\notes", text)
        self.assertIn("and bold.", text)
        self.assertNotIn(r"\textbf", text)


if __name__ == "__main__":
    unittest.main()
