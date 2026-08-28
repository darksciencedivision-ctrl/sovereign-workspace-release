"""v1.2.1 hardening regression tests: input boundaries (P0-16, P0-17, P0-18)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"


def _seat(name="Neo", model="mock-a:latest", color="#4fd1ff", persona="Builder", thesis="T"):
    return {"name": name, "model": model, "color": color, "persona": persona, "thesis": thesis}


def _write_and_load(tmp_path, document, module_name):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    old_config = os.environ.get("CONFIG_PATH")
    os.environ["CONFIG_PATH"] = str(config_path)
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
    return module


@pytest.fixture(scope="module")
def boundary_app():
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "port": 18811,
        "seats": [_seat(), _seat(name="Clue", color="#7dffa0")],
        "insight_panel": False,
    }
    yield _write_and_load(
        Path(_mkdtemp()), doc, "debate_table_v1_2_1_boundaries"
    )


def _mkdtemp():
    import tempfile

    return tempfile.mkdtemp(prefix=".r2-boundaries-")


_CTR = {"n": 0}


def _rejects_config(tmp_path, document, fragments):
    global _CTR
    _CTR["n"] += 1
    name = f"debate_table_v1_2_1_reject_{_CTR['n']}"
    with pytest.raises(SystemExit) as excinfo:
        _write_and_load(tmp_path, document, name)
    sys.modules.pop(name, None)
    assert excinfo.value.code == 2


def test_duplicate_seat_identities_rejected(boundary_app, tmp_path):
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "seats": [_seat(name="Neo"), _seat(name="Neo", model="mock-b:latest")],
        "insight_panel": False,
    }
    _rejects_config(tmp_path, doc, None)
    message = _capture_error(tmp_path, doc)
    assert 'duplicate seat name "Neo"' in message


def test_duplicate_seat_identity_after_normalization_rejected(tmp_path):
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "seats": [_seat(name=" Neo "), _seat(name="neo", model="mock-b:latest")],
        "insight_panel": False,
    }
    message = _capture_error(tmp_path, doc)
    assert "duplicate seat name" in message


def test_invalid_seat_cardinality_rejected(tmp_path):
    one = {
        "ollama_url": "http://127.0.0.1:9",
        "seats": [_seat()],
        "insight_panel": False,
    }
    message = _capture_error(tmp_path, one)
    assert "expected 2..4 seats" in message and "received 1" in message

    five = {
        "ollama_url": "http://127.0.0.1:9",
        "seats": [_seat(name=f"S{i}") for i in range(5)],
        "insight_panel": False,
    }
    message = _capture_error(tmp_path, five)
    assert "expected 2..4 seats" in message and "received 5" in message


@pytest.mark.parametrize(
    "seat_patch,expected_fragment",
    [
        ({"model": ""}, "config.seats[0].model"),
        ({"name": ""}, "config.seats[0].name"),
        ({"name": "x" * 101}, "exceeds 100"),
        ({"color": "blue"}, "valid color format"),
        ({"color": "#12345"}, "valid color format"),
        ({"persona": "p" * 4001}, "persona exceeds 4000"),
        ({"thesis": "t" * 8001}, "thesis exceeds 8000"),
    ],
)
def test_invalid_seat_fields_rejected(tmp_path, seat_patch, expected_fragment):
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "seats": [_seat(**seat_patch), _seat(name="Clue", color="#7dffa0")],
        "insight_panel": False,
    }
    message = _capture_error(tmp_path, doc)
    assert expected_fragment in message


def test_contradictory_numeric_bounds_rejected(boundary_app, tmp_path):
    doc = {
        "ollama_url": "http://127.0.0.1:9",
        "turn_word_min": 300,
        "turn_word_max": 50,
        "seats": [_seat(), _seat(name="Clue", color="#7dffa0")],
        "insight_panel": False,
    }
    message = _capture_error(tmp_path, doc)
    assert "turn_word_min" in message and "turn_word_max" in message
    assert "<=" in message


def test_oversized_interjection_rejected_valid_edge_cases_accepted(boundary_app):
    limits = boundary_app.INPUT_LIMITS
    too_long = "x" * (limits["interjection"] + 1)
    response = asyncio.run(
        boundary_app.api_interject(boundary_app.TextIn(text=too_long))
    )
    assert response.status_code == 400
    assert boundary_app.state.interject in ("", None)

    multiline = "Line one.\nLine two.\n\nLine three."
    response = asyncio.run(
        boundary_app.api_interject(boundary_app.TextIn(text=multiline))
    )
    assert response.status_code == 200
    single_char = "I"
    response = asyncio.run(
        boundary_app.api_interject(boundary_app.TextIn(text=single_char))
    )
    assert response.status_code == 200
    boundary_app.state.interject = ""


def test_oversized_revision_reason_and_model_rejected(boundary_app):
    reason = "r" * (boundary_app.INPUT_LIMITS["revision_reason"] + 1)
    body = boundary_app.SeatThesisIn(
        seat="Neo", thesis="Valid revised thesis.", reason=reason
    )
    response = asyncio.run(boundary_app.api_seat_thesis(body))
    assert response.status_code == 400

    model = "m" * 201
    response = asyncio.run(
        boundary_app.api_seat_model(boundary_app.SeatModelIn(seat="Neo", model=model))
    )
    assert response.status_code == 400
    empty_model_response = asyncio.run(
        boundary_app.api_seat_model(boundary_app.SeatModelIn(seat="Neo", model="   "))
    )
    assert empty_model_response.status_code == 400


def test_frontend_reflects_backend_limits(boundary_app):
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    limits = boundary_app.INPUT_LIMITS
    assert f'maxlength="{limits["public_title"]}"' in html
    assert f'maxlength="{limits["debate_brief"]}"' in html
    assert f'maxlength="{limits["interjection"]}"' in html


def _capture_error(tmp_path, document):
    """Run a throwaway interpreter so the FATAL diagnostic can be asserted."""
    config_path = tmp_path / "cfg.json"
    config_path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    import subprocess

    probe = (
        "import os,runpy,sys\n"
        f"os.environ['CONFIG_PATH'] = r'{config_path}'\n"
        "sys.argv=['app.py']\n"
        "try:\n"
        "    runpy.run_path(r'" + str(APP_PATH) + "', run_name='not_main')\n"
        "except SystemExit as e:\n"
        "    raise\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 2, result.stderr[-500:]
    assert "FATAL" in result.stderr
    return result.stderr
