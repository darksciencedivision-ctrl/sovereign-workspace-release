from __future__ import annotations

"""Detector regression net for the enterprise secret scanner (SD-RBR-v1.1 R-2).

Every pattern in tools.export_enterprise.SECRET_PATTERNS must fire on a
representative synthetic value. The broad sk- control must fire on any
non-allowlisted sk- + 20-alphanumeric value, and suppression must happen by
exact matched VALUE against DECLARED_FIXTURE_SECRETS only - never by path.

Representative samples are assembled at RUNTIME from inert fragments so this
file carries no scannable literal: the net must never trip the very detector
it guards when the tracked tree itself is exported.
"""

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.export_enterprise import DECLARED_FIXTURE_SECRETS, SECRET_PATTERNS, _scan_tree

ALLOWED_FIXTURE_VALUE = "sk-synthetic000000000000000000"


def _representative_samples() -> list[str]:
    aws_like = base64.b64decode("QUtJQUlPU0ZPRE5OMEVYQU1QTEU=").decode("ascii")
    pem_header = "-" * 5 + "BEGIN " + "RSA PRIVATE" + " KEY" + "-" * 5
    slack_token = "xo" + "xb-" + "1234567890abcdefghijklmnop"
    google_key = "AI" + "za" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7X1"
    password_line = "pass" + "word = " + '"' + "supersecretvalue99" + '"'
    return [
        aws_like,
        pem_header,
        "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
        "github_pat_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",
        slack_token,
        "sk-" + "z" * 27,
        "glpat" + "-" + "a1B2c3D4e5F6g7H8i9J0",
        google_key,
        password_line,
    ]


def _scan_single(relative: str, text: str) -> dict:
    return _scan_tree({relative: text.encode("utf-8")})


class SecretDetectorRegressionNetTests(unittest.TestCase):
    def test_every_pattern_has_a_representative_sample(self) -> None:
        samples = _representative_samples()
        self.assertEqual(len(samples), len(SECRET_PATTERNS))
        for index, (pattern, sample) in enumerate(zip(SECRET_PATTERNS, samples)):
            with self.subTest(pattern=pattern.pattern, sample_index=index):
                result = _scan_single(f"prod/config_{index}.txt", sample)
                self.assertTrue(
                    any(f"config_{index}.txt" in finding for finding in result["hard_secret_findings"]),
                    f"pattern {pattern.pattern!r} failed to fire on its representative sample",
                )

    def test_broad_sk_control_fires_without_t3blbkfj_marker(self) -> None:
        result = _scan_single("src/leak.txt", "sk-" + "q" * 26)
        self.assertTrue(result["hard_secret_findings"], "broad sk- detector must fire on bare sk- keys")

    def test_allowlisted_fixture_value_is_suppressed_and_declared(self) -> None:
        result = _scan_single("tests/test_corpus_admission.py", ALLOWED_FIXTURE_VALUE)
        self.assertEqual(result["hard_secret_findings"], [])
        self.assertEqual(
            result["suppressed_declared_fixtures"],
            [{"value": ALLOWED_FIXTURE_VALUE, "path": "tests/test_corpus_admission.py", "pattern": SECRET_PATTERNS[5].pattern}],
        )
        self.assertTrue(result["passed"])

    def test_suppression_is_by_value_not_path(self) -> None:
        same_path_different_value = _scan_single("tests/test_corpus_admission.py", "sk-" + "w" * 26)
        self.assertTrue(same_path_different_value["hard_secret_findings"])
        self.assertEqual(same_path_different_value["suppressed_declared_fixtures"], [])
        different_path_same_value = _scan_single("production/real.env", ALLOWED_FIXTURE_VALUE)
        self.assertEqual(different_path_same_value["hard_secret_findings"], [])
        self.assertTrue(any(s["path"] == "production/real.env" for s in different_path_same_value["suppressed_declared_fixtures"]))

    def test_allowlist_contains_exactly_the_known_fixtures(self) -> None:
        self.assertEqual(DECLARED_FIXTURE_SECRETS, {ALLOWED_FIXTURE_VALUE})

    def test_net_source_carries_no_scannable_literals(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        result = _scan_tree({"tests/test_secret_detector_net.py": source.encode("utf-8")})
        self.assertEqual(
            result["hard_secret_findings"],
            [],
            "this regression net must not carry scannable secrets in its own source",
        )


if __name__ == "__main__":
    unittest.main()