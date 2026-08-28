"""v1.2.1 hardening regression tests: structured rotating logs (P1-logs)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
PORT = 19033

_SEATS = [
    {"name": "Neo", "model": "m", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "m", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


def _load(log_dir: Path, name="debate_table_v1_2_1_logs"):
    temp_dir = Path(tempfile.mkdtemp(prefix=".r11-", dir=ROOT / "tests"))
    cfg = temp_dir / "config.json"
    cfg.write_text(
        json.dumps({"ollama_url": "http://127.0.0.1:9", "port": PORT, "seats": _SEATS, "insight_panel": False}) + "\n",
        encoding="utf-8",
    )
    old_cfg = os.environ.get("CONFIG_PATH")
    old_log = os.environ.get("DEBATE_LOG_DIR")
    os.environ["CONFIG_PATH"] = str(cfg)
    os.environ["DEBATE_LOG_DIR"] = str(log_dir)
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    for key, old in (("CONFIG_PATH", old_cfg), ("DEBATE_LOG_DIR", old_log)):
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
    return module


def test_turn_completion_logged_with_required_fields(tmp_path):
    log_dir = tmp_path / "logs"
    module = _load(log_dir)

    async def fake_chat(model, messages, on_public=None, metrics=None, **kw):
        fragment = "A complete public sentence. Another follows now."
        if on_public is not None:
            await on_public(fragment)
        return fragment

    module.ollama_chat = fake_chat
    asyncio.run(module.run_turn(module.SEATS[0], 1))

    log_file = log_dir / "debate.log"
    assert log_file.exists()
    records = [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completed = [r for r in records if r["event"] == "turn_completed"]
    assert completed, records
    record = completed[-1]
    for key in ("ts", "event", "topic_epoch", "turn", "seat", "model",
                "outcome", "completion_state", "ttft_seconds", "duration_seconds"):
        assert key in record, key
    assert record["outcome"] == "completed"


def test_skip_reason_logged(tmp_path):
    log_dir = tmp_path / "logs"
    module = _load(log_dir, "debate_table_v1_2_1_logs2")

    async def boom(model, messages, **kw):
        raise ValueError("down")

    module.ollama_chat = boom
    outcome = asyncio.run(module.run_turn(module.SEATS[0], 1))
    assert outcome is module.tc.TurnOutcome.SKIPPED_GENERATION_ERROR
    text = (log_dir / "debate.log").read_text(encoding="utf-8")
    assert '"outcome": "generation_error"' in text.replace(", ", ", ")


def test_rotation_bounds_configured(tmp_path):
    module = _load(tmp_path / "logs", "debate_table_v1_2_1_logs3")
    from logging.handlers import RotatingFileHandler

    handlers = [h for h in module._logger.handlers if isinstance(h, RotatingFileHandler)]
    assert handlers, "rotating handler missing"
    handler = handlers[0]
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 3


def test_no_interjection_payload_in_logs(tmp_path):
    log_dir = tmp_path / "logs"
    module = _load(log_dir, "debate_table_v1_2_1_logs4")
    secret = "CONFIDENTIAL-operator-note-xyz"

    async def fake_chat(model, messages, on_public=None, metrics=None, **kw):
        fragment = "A complete public sentence. Another follows now."
        if on_public is not None:
            await on_public(fragment)
        return fragment

    module.ollama_chat = fake_chat
    module.state.interject = secret
    try:
        asyncio.run(module.run_turn(module.SEATS[0], 1))
    finally:
        module.state.interject = None
    text = (log_dir / "debate.log").read_text(encoding="utf-8")
    assert secret not in text