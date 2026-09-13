"""R26 — the log viewer reads the field its own API returns, and binds a response to its request.

/api/logs returns {logs: <text>, module_id}. extractLogText only checked log/content/text/output,
so it fell through to rendering the raw JSON envelope (escaped newlines + metadata). And refreshLogs
used the module-global logModuleId at write time, so a response that arrived after the operator
switched modules could paint one module's logs into another's panel.

Pinned structurally in shell/static/app.js (the renderer has no test harness; source-level
assertion is the H-4/H-13 precedent, as in test_browser_handle_map.py).
"""
import os
import re
import unittest

APP_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shell", "static", "app.js")


class TestLogViewerSchema(unittest.TestCase):
    def setUp(self):
        with open(APP_JS, "r", encoding="utf-8-sig", errors="replace") as f:
            self.src = f.read()

    def test_extract_reads_the_logs_field_first(self):
        block = re.search(r"const direct = firstString\((.*?)\);", self.src, re.S)
        self.assertIsNotNone(block, "extractLogText must build `direct` from firstString")
        fields = block.group(1)
        self.assertIn("parsed.logs", fields, "the canonical /api/logs field must be read (R26)")
        # It must be the FIRST argument so it wins over the legacy aliases (log/content/text/output).
        first_arg = fields.strip().split(",")[0].strip()
        self.assertEqual(first_arg, "parsed.logs")

    def test_refresh_binds_the_response_to_the_requested_module(self):
        self.assertRegex(self.src, r"const requested = logModuleId;")
        self.assertRegex(self.src, r"if \(requested !== logModuleId\) return;")


if __name__ == "__main__":
    unittest.main(verbosity=2)
