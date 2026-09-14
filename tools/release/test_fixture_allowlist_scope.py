#!/usr/bin/env python
"""F-066 - the declared-fixture allow-list exempts exact BYTES at an exact PATH, and nothing else.

542be62 added seven synthetic-credential redaction/provider fixtures to fixture_allowlist.json so the
credential-shape gate stopped flagging them. That is only safe if the exemption cannot widen:
  * a real-shaped key added to an allow-listed file must fail (its sha256 no longer matches);
  * the same synthetic bytes at an undeclared path must still be a credential hit;
  * every product key shape must still be detected in an ordinary file;
  * every shipped entry must name a tracked file whose bytes match, and must still be NEEDED (the
    file really carries a credential shape) - a stale entry is an exemption nobody reviews.

Credential shapes are assembled from fragments at runtime, so this file's own bytes match no
pattern and it needs no allow-list entry of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import package_boundary_gate as gate  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ALLOWLIST = os.path.join(HERE, "fixture_allowlist.json")

ANTHROPIC_SHAPE = "sk-" + "ant-" + "api03-" + "Q7" * 12            # not a synthetic run, key-shaped
SYNTHETIC_ANTHROPIC = "sk-" + "ant-" + "api03-" + "A" * 24
SHAPES = {
    "aws-access-key-id": "AK" + "IA" + "Q2W3E4R5T6Y7U8I9",
    "anthropic-key": ANTHROPIC_SHAPE,
    "openai-proj-key": "sk-" + "proj-" + "m3Kd9" * 3,
    "openai-style-key": "sk-" + "Zx81" * 7,
    "github-token": "gh" + "p_" + "r2D2c3PO" * 3,
    "huggingface-token": "hf" + "_" + "Qw9e" * 5,
    "google-api-key": "AI" + "za" + "Sy" + "b7Kq" * 6,
    "private-key-block": "-----BEGIN " + "RSA PRIVATE KEY-----",
}


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class FixtureAllowlistScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="f066-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, rel: str, text: str) -> str:
        full = os.path.join(self.tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return full

    def _allow(self, entries) -> dict:
        path = os.path.join(self.tmp, "allow.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f)
        return gate.load_allowlist(path)

    def _scan(self, allowlist: dict) -> dict:
        root = os.path.join(self.tmp, "tree")
        return gate.scan_tree(root, (), allowlist)

    def test_declared_synthetic_fixture_passes_only_with_its_exact_bytes(self) -> None:
        body = f'const KEY = "{SYNTHETIC_ANTHROPIC}"; // asserts the pane redacts it\n'
        full = self._write("tree/test/pane.test.js", body)
        allow = self._allow([{"path": "test/pane.test.js", "sha256": _sha(full), "reason": "synthetic"}])
        res = self._scan(allow)
        self.assertEqual([], res["credential_hits"])
        self.assertEqual([], res["violations"])
        self.assertEqual(["test/pane.test.js"], [a["path"] for a in res["allowlisted"]])

    def test_a_real_shaped_key_added_to_an_allowlisted_file_fails(self) -> None:
        body = f'const KEY = "{SYNTHETIC_ANTHROPIC}";\n'
        full = self._write("tree/test/pane.test.js", body)
        allow = self._allow([{"path": "test/pane.test.js", "sha256": _sha(full), "reason": "synthetic"}])
        self._write("tree/test/pane.test.js", body + f'const LEAK = "{ANTHROPIC_SHAPE}";\n')
        res = self._scan(allow)
        self.assertEqual([], res["allowlisted"], "changed bytes must not stay exempt")
        self.assertEqual(1, len(res["violations"]))
        self.assertIn("sha256 mismatch", res["violations"][0]["rule"])

    def test_identical_fixture_bytes_at_an_undeclared_path_are_still_flagged(self) -> None:
        body = f'const KEY = "{SYNTHETIC_ANTHROPIC}";\n'
        declared = self._write("tree/test/pane.test.js", body)
        self._write("tree/src/copied.js", body)
        allow = self._allow([{"path": "test/pane.test.js", "sha256": _sha(declared), "reason": "synthetic"}])
        res = self._scan(allow)
        self.assertEqual(["src/copied.js"], [h["path"] for h in res["credential_hits"]])

    def test_every_key_shape_is_still_detected_in_an_ordinary_file(self) -> None:
        for name, value in SHAPES.items():
            with self.subTest(shape=name):
                shutil.rmtree(os.path.join(self.tmp, "tree"), ignore_errors=True)
                self._write("tree/src/config.py", f'VALUE = "{value}"\n')
                hits = self._scan({})["credential_hits"]
                self.assertTrue(hits, f"{name} shape was not detected")

    def test_the_shipped_allowlist_entries_are_exact_tracked_and_still_needed(self) -> None:
        table = gate.load_allowlist(ALLOWLIST)
        tracked = set(subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                                     check=True).stdout.splitlines())
        for rel, entry in table.items():
            with self.subTest(path=rel):
                self.assertIn(rel, tracked, "an allow-list entry must name a tracked file")
                full = os.path.join(REPO, *rel.split("/"))
                self.assertEqual(entry["sha256"], _sha(full), "declared digest must match the candidate")
                self.assertTrue(entry["reason"].strip(), "every exemption states its reason")
                self.assertTrue(gate.scan_content(full, os.path.basename(full)) or gate.classify(
                    rel, os.path.basename(full), set(rel.split("/")[:-1])),
                    "the file no longer trips the gate, so the exemption is stale - remove it")


if __name__ == "__main__":
    unittest.main()
