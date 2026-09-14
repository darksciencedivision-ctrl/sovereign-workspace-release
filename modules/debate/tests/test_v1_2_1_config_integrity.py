"""v1.2.1 hardening regression tests: configuration integrity (P0-02, P0-03).

Contract:
- Malformed JSON config must be rejected, never replaced by defaults, and the
  original bytes must be preserved (G-05).
- Bootstrap and runtime must interpret config.json with one encoding policy
  (utf-8-sig) so a BOM produced by an editor cannot split behavior.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"

VALID_CONFIG = {
    "ollama_url": "http://127.0.0.1:9",
    "port": 18799,
    "seats": [
        {
            "name": "Neo",
            "model": "mock-a:latest",
            "color": "#4fd1ff",
            "persona": "Builder",
            "thesis": "Systems beat individual cleverness.",
        },
        {
            "name": "Clue",
            "model": "mock-b:latest",
            "color": "#7dffa0",
            "persona": "Challenger",
            "thesis": "Every claim owes a mechanism.",
        },
    ],
    "insight_panel": False,
}

MALFORMED_BYTES = (
    b'{\n  "ollama_url": "http://127.0.0.1:9",\n  "seats": [ oops\n'
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exec_app_module(config_path: Path, module_name: str):
    """Execute app.py under a temp config path, following the existing
    importlib convention used by the v1.1/v1.2 regression suites."""
    old_config = os.environ.get("CONFIG_PATH")
    old_ollama = os.environ.get("OLLAMA_URL")
    os.environ["CONFIG_PATH"] = str(config_path)
    os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        if old_config is None:
            os.environ.pop("CONFIG_PATH", None)
        else:
            os.environ["CONFIG_PATH"] = old_config
        if old_ollama is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old_ollama
    return module


@pytest.fixture(scope="module")
def config_app(tmp_path_factory):
    """One app-module instance loaded from a valid config; used to reach
    load_config / persist helpers without re-executing the world per test."""
    temp_dir = tmp_path_factory.mktemp("cfg-integrity-module")
    config_path = temp_dir / "config.json"
    config_path.write_text(json.dumps(VALID_CONFIG, indent=2) + "\n", encoding="utf-8")
    module = _exec_app_module(config_path, "debate_table_v1_2_1_cfg_integrity")
    yield module


def test_malformed_config_is_preserved_and_rejected(config_app, tmp_path):
    bad_path = tmp_path / "config.json"
    bad_path.write_bytes(MALFORMED_BYTES)
    before_digest = _digest(bad_path)

    with pytest.raises(config_app.ConfigurationError) as excinfo:
        config_app.load_config(bad_path)

    message = str(excinfo.value)
    assert str(bad_path) in message
    assert _digest(bad_path) == before_digest


def test_bom_config_parses_consistently(config_app, tmp_path):
    plain_path = tmp_path / "plain.json"
    bom_path = tmp_path / "bom.json"
    plain_path.write_text(json.dumps(VALID_CONFIG, indent=2) + "\n", encoding="utf-8")
    bom_path.write_text(json.dumps(VALID_CONFIG, indent=2) + "\n", encoding="utf-8-sig")

    assert bom_path.read_bytes().startswith(b"\xef\xbb\xbf")

    from_plain = config_app.load_config(plain_path)
    from_bom = config_app.load_config(bom_path)

    assert {k: from_bom[k] for k in ("ollama_url", "port")} == {
        k: from_plain[k] for k in ("ollama_url", "port")
    }
    assert [s["name"] for s in from_bom["seats"]] == [
        s["name"] for s in from_plain["seats"]
    ]

    # The BOM file must also survive a runtime persistence helper round trip,
    # which historically parsed with strict utf-8 and would crash on a BOM.
    # Persist helpers address the module-level CONFIG_PATH, so run them through
    # a dedicated app-module instance whose config path IS the BOM file.
    bom_module_name = "debate_table_v1_2_1_cfg_bom"
    try:
        bom_module = _exec_app_module(bom_path, bom_module_name)
        bom_module.persist_seat_thesis("Neo", "Revised via BOM config.")
    finally:
        sys.modules.pop(bom_module_name, None)
    persisted = json.loads(bom_path.read_text(encoding="utf-8-sig"))
    assert persisted["seats"][0]["thesis"] == "Revised via BOM config."


def test_invalid_config_does_not_write_defaults(config_app, tmp_path):
    bad_path = tmp_path / "config.json"
    bad_path.write_bytes(MALFORMED_BYTES)
    before_digest = _digest(bad_path)
    before_mtime_ns = bad_path.stat().st_mtime_ns

    fresh_name = "debate_table_v1_2_1_cfg_fatal"
    with pytest.raises(SystemExit) as excinfo:
        _exec_app_module(bad_path, fresh_name)

    assert excinfo.value.code == 2
    sys.modules.pop(fresh_name, None)

    assert _digest(bad_path) == before_digest
    assert bad_path.stat().st_mtime_ns == before_mtime_ns
    assert not list(tmp_path.glob("*.tmp"))
