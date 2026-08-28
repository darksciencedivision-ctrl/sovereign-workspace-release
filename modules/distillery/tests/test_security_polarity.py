from __future__ import annotations

"""SD-RBR-v1.1 R-3: manifest presence-flag polarity, both directions.

weights_present / private_runtime_payloads_present must be True when the
condition exists and False when it does not. Assertions target the single real
construction path (tools.export_enterprise.manifest_presence_flags) used by
both the in-archive MANIFEST.json and the export report gate_state - not a
reimplementation of the expression.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.export_enterprise import manifest_presence_flags


def _security(*, weights: bool, private: bool) -> dict:
    return {
        "hard_secret_findings": [],
        "known_private_runtime_payloads": ["runs/private/blob"] if private else [],
        "model_weight_files": ["model.safetensors"] if weights else [],
        "oversized_files": [],
        "unexpected_binary_files": [],
        "suppressed_declared_fixtures": [],
        "scope_note": "test",
    }


class ManifestPresencePolarityTests(unittest.TestCase):
    def test_weights_present_true_when_weights_exist(self) -> None:
        flags = manifest_presence_flags(_security(weights=True, private=False))
        self.assertIs(flags["weights_present"], True)

    def test_weights_present_false_when_no_weights(self) -> None:
        flags = manifest_presence_flags(_security(weights=False, private=False))
        self.assertIs(flags["weights_present"], False)

    def test_private_payload_present_true_when_payload_exists(self) -> None:
        flags = manifest_presence_flags(_security(weights=False, private=True))
        self.assertIs(flags["private_runtime_payloads_present"], True)

    def test_private_payload_present_false_when_absent(self) -> None:
        flags = manifest_presence_flags(_security(weights=False, private=False))
        self.assertIs(flags["private_runtime_payloads_present"], False)

    def test_both_conditions_simultaneously(self) -> None:
        flags = manifest_presence_flags(_security(weights=True, private=True))
        self.assertIs(flags["weights_present"], True)
        self.assertIs(flags["private_runtime_payloads_present"], True)


if __name__ == "__main__":
    unittest.main()