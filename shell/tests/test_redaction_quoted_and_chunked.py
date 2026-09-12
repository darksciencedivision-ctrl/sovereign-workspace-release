"""R13 (F-010) and R14 (F-012): quoted/JSON/bare-shape credentials are redacted, a bare `key` is
not over-redacted, and a secret split across pipe-chunk boundaries is still caught.
"""
import os
import sys
import unittest

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src.logring import LogRing  # noqa: E402
from shell.src.redact import redact  # noqa: E402

SENTINEL = "sk-ant-api03-DEADBEEFdeadbeef012345"


class TestQuotedAndJsonRedaction(unittest.TestCase):
    def _redacted(self, text):
        out = redact(text)
        self.assertNotIn(SENTINEL, out, f"leaked in: {out!r}")
        self.assertIn("[REDACTED]", out, f"nothing redacted in: {out!r}")
        return out

    def test_double_quoted_value(self):
        self._redacted(f'API_KEY="{SENTINEL}"')

    def test_single_quoted_value_with_spaces(self):
        self._redacted(f"password = '{SENTINEL}'")

    def test_json_object_with_quoted_keys(self):
        out = self._redacted(f'{{"api_key": "{SENTINEL}", "token": "{SENTINEL}"}}')
        self.assertEqual(out.count("[REDACTED]"), 2, out)

    def test_prefixed_env_key_with_quoted_value(self):
        self._redacted(f'OPENAI_API_KEY: "{SENTINEL}"')

    def test_bare_provider_token_shape(self):
        # No key= introducer at all - caught by shape.
        self._redacted(f"using credential {SENTINEL} for the call")

    def test_various_bare_shapes(self):
        for tok in ("ghp_" + "A" * 36, "AKIA" + "A" * 16, "AIza" + "B" * 35,
                    "xoxb-" + "1" * 12 + "-abcdef", "glpat-" + "x" * 20):
            out = redact(f"leaked {tok} here")
            self.assertNotIn(tok, out, f"shape not redacted: {tok}")
            self.assertIn("[REDACTED]", out)


class TestNoOverRedaction(unittest.TestCase):
    def test_words_ending_in_key_are_left_alone(self):
        for benign in ("monkey: banana", "primary_key: id", "hotkey=F5", "donkey: grey"):
            self.assertNotIn("[REDACTED]", redact(benign), f"over-redacted: {benign}")

    def test_unquoted_assignment_still_redacts(self):
        # The pre-existing contract must not regress.
        self.assertIn("[REDACTED]", redact("API_KEY=plainsecretvalue"))
        self.assertIn("[REDACTED]", redact("token=plainsecretvalue"))
        self.assertNotIn("plainsecretvalue", redact("token=plainsecretvalue"))


class TestChunkBoundaryRedaction(unittest.TestCase):
    def test_secret_split_across_two_writes_is_redacted(self):
        ring = LogRing()
        # The key and its value straddle a chunk boundary; redaction must see the whole line.
        ring.write(b"API_KE")
        ring.write(b"Y=" + SENTINEL.encode() + b"\n")
        out = ring.read()
        self.assertNotIn(SENTINEL, out, f"a boundary-split secret leaked: {out!r}")
        self.assertIn("[REDACTED]", out)

    def test_partial_final_line_is_flushed_and_redacted(self):
        ring = LogRing()
        ring.write(b"trailing token=" + SENTINEL.encode())   # no newline
        self.assertNotIn(SENTINEL, ring.read(),
                         "an un-terminated partial line must not appear un-redacted")
        ring.flush()
        out = ring.read()
        self.assertNotIn(SENTINEL, out)
        self.assertIn("[REDACTED]", out)

    def test_multibyte_split_across_writes_is_not_mojibake(self):
        snowman = "☃"  # 3 UTF-8 bytes: e2 98 83
        raw = snowman.encode("utf-8")
        ring = LogRing()
        ring.write(raw[:2])         # first two bytes
        ring.write(raw[2:] + b"\n")  # the third byte completes the character
        self.assertIn(snowman, ring.read(), "a multibyte char split across writes was corrupted")

    def test_no_spurious_blank_line_after_a_newline_terminated_chunk(self):
        ring = LogRing()
        ring.write(b"one line\n")
        self.assertEqual(ring.read(), "one line")


if __name__ == "__main__":
    unittest.main(verbosity=2)
