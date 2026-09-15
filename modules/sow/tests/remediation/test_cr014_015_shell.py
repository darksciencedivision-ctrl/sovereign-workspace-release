"""CR-014 (Distillery summary ignores snapshot failures) and
CR-015 (retained shell routes point to intentionally removed documents)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for p in (str(RELEASE_ROOT), str(SHELL_SRC)):  # server.py imports `shell.src.*` absolutely
    if p not in sys.path:
        sys.path.insert(0, p)

import distillery  # noqa: E402
import server  # noqa: E402


# -- CR-014 ----------------------------------------------------------------
def _patch(monkeypatch, handoff, questions, snapshot):
    monkeypatch.setattr(distillery, "_parse_handoff", lambda: handoff)
    monkeypatch.setattr(distillery, "_parse_open_questions", lambda: questions)
    monkeypatch.setattr(distillery, "_find_snapshot", lambda: snapshot)


NC = distillery.NOT_CONFIGURED
OK = {}  # no error key


def test_cr014_snapshot_config_error_surfaces_at_top(monkeypatch):
    _patch(monkeypatch, {"error": NC}, {"error": NC}, {"error": "CONFIG_ERROR", "reason": "boom"})
    res = distillery.get_distillery_status()
    assert res["state"] == "CONFIG_ERROR"
    assert res["snapshot"]["error"] == "CONFIG_ERROR"


def test_cr014_ambiguous_snapshot_surfaces_at_top(monkeypatch):
    _patch(monkeypatch, OK, OK, {"error": "CONFIG_ERROR(AMBIGUOUS_SNAPSHOT)", "matches": ["a", "b"]})
    assert distillery.get_distillery_status()["state"] == "CONFIG_ERROR"


def test_cr014_not_configured_snapshot_is_not_an_error(monkeypatch):
    _patch(monkeypatch, OK, OK, {"error": NC, "reason": "unset"})
    assert distillery.get_distillery_status()["state"] == "NOT_STARTED"


def test_cr014_precedence_table(monkeypatch):
    # Any component in CONFIG_ERROR => top CONFIG_ERROR; all clean/NOT_CONFIGURED => NOT_STARTED.
    err = {"error": "CONFIG_ERROR"}
    cases = [
        ((err, OK, OK), "CONFIG_ERROR"),
        ((OK, err, OK), "CONFIG_ERROR"),
        ((OK, OK, err), "CONFIG_ERROR"),
        (({"error": NC}, {"error": NC}, {"error": NC}), "NOT_STARTED"),
        ((OK, OK, OK), "NOT_STARTED"),
    ]
    for (h, q, s), expected in cases:
        _patch(monkeypatch, h, q, s)
        assert distillery.get_distillery_status()["state"] == expected, (h, q, s)


# -- CR-015 ----------------------------------------------------------------
def test_cr015_no_doc_routes_advertised():
    assert server._DOC_ROUTES == {}, "dead /doc routes must be removed in the source-only tree"


def test_cr015_frontend_advertises_no_dead_doc_link():
    static = RELEASE_ROOT / "shell" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    appjs = (static / "app.js").read_text(encoding="utf-8")
    for dead in ("/doc/discovery", "/doc/theme-baseline", "/doc/directive"):
        assert dead not in html, f"dead doc link still in index.html: {dead}"
    assert "link-discovery" not in html and "linkDiscovery" not in appjs
