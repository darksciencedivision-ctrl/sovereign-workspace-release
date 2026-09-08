"""F-16: startup-test receipt lane uses ${state_root}, not the historical July path."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shell.src import adapter as adapter_module  # noqa: E402


class StartupTestStateReceiptLane(unittest.TestCase):
    def test_sow_startup_test_expands_state_root(self) -> None:
        adapters = adapter_module.load_all_adapters()
        sow = adapters["sow"]
        self.assertNotIn("error", sow, sow.get("reason"))
        st = sow["startup_test"]
        receipt_dir = st["env_set"]["SHELL_SELFCHECK_RECEIPT_DIR"]
        readiness_path = st["readiness"]["path"]
        state_root = sow["state_root"].replace("\\", "/")
        self.assertTrue(receipt_dir.replace("\\", "/").startswith(state_root))
        self.assertTrue(readiness_path.replace("\\", "/").startswith(state_root))
        self.assertTrue(readiness_path.replace("\\", "/").endswith("/receipts/PHASE16A_SELFCHECK.json"))
        self.assertNotIn("/docs/evidence/receipts/PHASE16A_SELFCHECK.json", readiness_path.replace("\\", "/"))
        self.assertIn("${state_root}", json.dumps(json.loads((REPO_ROOT / "shell" / "modules" / "sow.json").read_text(encoding="utf-8"))))
