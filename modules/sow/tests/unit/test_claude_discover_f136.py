"""F-136(11) — Claude executable discovery prefers a real PATH hit including .cmd."""
from __future__ import annotations

from adapters.frontier.claude_code import ClaudeCliBackend


def test_resolve_falls_back_to_configured_name(monkeypatch, tmp_path):
    backend = ClaudeCliBackend(executable="claude")
    monkeypatch.setattr("adapters.frontier.claude_code.shutil.which", lambda name: None)
    monkeypatch.setattr("adapters.frontier.claude_code.os.path.isfile", lambda p: False)
    assert backend._resolve_executable() == "claude"


def test_resolve_prefers_cmd_shim(monkeypatch):
    backend = ClaudeCliBackend(executable="claude")
    monkeypatch.setattr("adapters.frontier.claude_code.os.path.isfile", lambda p: False)

    def which(name):
        if name == "claude.cmd":
            return r"C:\npm\claude.cmd"
        return None

    monkeypatch.setattr("adapters.frontier.claude_code.shutil.which", which)
    assert backend._resolve_executable().endswith("claude.cmd")
