import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import piggybank


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_codex_uses_last_response_total_without_double_counting_cache(self):
        path = self.home / ".codex" / "sessions" / "2026" / "08" / "22" / "session.jsonl"
        path.parent.mkdir(parents=True)
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"type": "turn_context", "timestamp": now, "payload": {"model": "gpt-test"}},
            {
                "type": "event_msg",
                "timestamp": now,
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 60,
                            "cache_write_input_tokens": 0,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 120,
                        }
                    },
                },
            },
        ]
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        events, status = piggybank.collect_codex(self.home, self.cutoff)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].total_tokens, 120)
        self.assertEqual(events[0].input_tokens, 40)
        self.assertEqual(events[0].cache_read_tokens, 60)
        self.assertEqual(status.confidence, "VERIFIED")

    def test_claude_deduplicates_stream_records_by_message_id(self):
        path = self.home / ".claude" / "projects" / "demo" / "session.jsonl"
        path.parent.mkdir(parents=True)
        now = datetime.now(timezone.utc).isoformat()
        base = {
            "type": "assistant",
            "timestamp": now,
            "message": {
                "id": "msg-1",
                "model": "claude-test",
                "usage": {"input_tokens": 5, "cache_read_input_tokens": 90, "output_tokens": 10},
            },
        }
        path.write_text(json.dumps(base) + "\n" + json.dumps(base) + "\n", encoding="utf-8")
        events, _ = piggybank.collect_claude(self.home, self.cutoff)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].total_tokens, 105)

    def test_opencode_reads_only_numeric_assistant_usage(self):
        db = self.home / ".local" / "share" / "opencode" / "opencode.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE message(id TEXT, time_created INTEGER, data TEXT)")
        stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        data = {
            "role": "assistant",
            "providerID": "ollama",
            "modelID": "qwen-local",
            "time": {"created": stamp},
            "tokens": {"total": 123, "input": 100, "output": 23, "cache": {"read": 0, "write": 0}},
        }
        con.execute("INSERT INTO message VALUES (?, ?, ?)", ("m1", stamp, json.dumps(data)))
        con.commit()
        con.close()
        events, statuses = piggybank.collect_opencode(self.home, self.cutoff)
        self.assertEqual(events[0].provider, "Ollama")
        self.assertEqual(events[0].locality, "local")
        self.assertEqual(events[0].total_tokens, 123)
        self.assertEqual(statuses[0].confidence, "VERIFIED")

    def test_unknown_is_not_rendered_as_zero_usage(self):
        status = piggybank.ProviderStatus(
            provider="Example",
            collector="discovery",
            confidence="UNKNOWN",
            coverage="NONE",
            health="HEALTHY",
            detail="No ledger",
        )
        summary = piggybank.build_summary([], [status], 1)
        self.assertEqual(summary["coverage"], "PARTIAL")
        self.assertIn("Example", summary["unmeasured_or_partial"])
        self.assertEqual(summary["today"]["total_tokens"], 0)
        self.assertIn("unknown", summary["coverage_note"].lower())

    def test_grok_parser_extracts_only_usage_object(self):
        payload = {"promptUsage": {"totalTokens": 9, "modelUsage": {"grok-test": {"totalTokens": 9}}}}
        parsed = piggybank._extract_grok_usage("Rate limited: " + json.dumps(payload))
        self.assertEqual(parsed["totalTokens"], 9)


if __name__ == "__main__":
    unittest.main()
