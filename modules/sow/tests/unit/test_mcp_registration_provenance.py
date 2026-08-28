"""W-57 — MCP registration provenance: the conductor actually in use must be wired from the repo.

The OP-12 conductor is `openai_codex_cli`. Measured on this host with the real CLI (codex-cli
0.146.0, offline `codex mcp list` — no provider call):

  * run from the repo root, the CLI lists `sovereign` with command `py`, args
    `-3.12 -m mcp_server.sovereign_tools` and the three SOVEREIGN_* env vars — the registration
    it reads is THIS repo's tracked `.codex/config.toml`, not a hand-edit anywhere else;
  * run from any other cwd, `sovereign` VANISHES from the list — project-config pickup is
    cwd-dependent, so a conductor session not bound to the repo root sees no sovereign server at
    all. That is the N-02 mechanism, observed one level worse than ModuleNotFoundError.

The governed desktop path already binds the conductor session's cwd to the repo root (the launch
ticket's `cwd`, the shell's ConPTY binding, `conductor-pty-selfcheck`). What was NOT pinned was the
MCP server's own working directory inside the registration, and nothing GRADED that the
registration exists in the repo at all. These tests pin both. The `cwd` value is absolute and
host-specific on purpose: a relative value would resolve against whatever directory codex itself
started in — the very thing being pinned away. Single-host build; if the repo moves, the pin fails
LOUDLY (server fails to start; W-55 diagnoses it), never silently.

DECLARED BOUND: `.mcp.json` (Claude Code) still carries no cwd/env of its own. It is not the
conductor in use, and its pane path is covered by the governed ConPTY cwd binding; its gaps are
recorded, not repaired here. `~/.codex/config.toml` (home) is deliberately not touched — wiring
from the repo means the home file must stay OUT of the registration (measured: from a foreign cwd
only `node_repl` from the home file remains).
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CODEX_CONFIG = ROOT / ".codex" / "config.toml"


def _live_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _same_path(a: str, b: pathlib.Path) -> bool:
    try:
        return pathlib.Path(a).resolve() == b.resolve()
    except OSError:
        return False


# ---- negative: the defect -----------------------------------------------------------------------

def test_the_codex_registration_pins_the_mcp_server_working_directory() -> None:
    """NEGATIVE. Pre-repair `.codex/config.toml` declares no `cwd`, so the server's working
    directory is whatever codex happens to give it, and `-m mcp_server.sovereign_tools` resolves
    only by luck of the launch directory. Repaired, the registration pins it to the repo root."""
    cfg = CODEX_CONFIG.read_text(encoding="utf-8")
    live = "\n".join(_live_lines(cfg))
    section = live.split("[mcp_servers.sovereign]", 1)
    assert len(section) == 2, "the repo must declare [mcp_servers.sovereign] for the conductor"
    body = section[1].split("[mcp_servers.", 1)[0]  # the sovereign block only
    match = re.search(r"^cwd\s*=\s*[\"'](.+?)[\"']\s*$", body, re.MULTILINE)
    assert match, (
        "the sovereign MCP registration carries no cwd pin — the server's module resolution "
        "depends on wherever codex was launched from (N-02, measured: registration pickup is "
        "itself cwd-dependent)")
    assert _same_path(match.group(1), ROOT), (
        f"the cwd pin must be THIS repo's root so `-m mcp_server.sovereign_tools` resolves "
        f"deterministically; found {match.group(1)!r}")


# ---- positive: the provenance that must hold ------------------------------------------------------

def test_the_registration_is_wired_from_the_repo_not_handwritten() -> None:
    """POSITIVE (pre-repair truth, preserved). The conductor's registration lives in the TRACKED
    repo file, names the module path (repo-relative wiring, not a hand-installed script), and the
    file is committed — provenance a reviewer can read off the tree, mirroring the `.grok` pin
    (`test_the_repo_config_does_not_supply_the_value_the_argv_pins`)."""
    assert CODEX_CONFIG.is_file(), "the repo must track the conductor's MCP registration"
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", ".codex/config.toml"],
        capture_output=True, text=True)
    assert listed.returncode == 0, (
        f".codex/config.toml is not tracked by git — the registration would live outside the "
        f"repo (hand-wired): {listed.stderr.strip()}")
    cfg = CODEX_CONFIG.read_text(encoding="utf-8")
    live = _live_lines(cfg)
    assert "[mcp_servers.sovereign]" in live
    assert 'command = "py"' in live
    assert 'args = ["-3.12", "-m", "mcp_server.sovereign_tools"]' in live, (
        "the registration must invoke the repo's module, not a hand-installed entry point")
    assert ('env_vars = ["SOVEREIGN_CONTROL_PORT", "SOVEREIGN_CONTROL_TOKEN", '
            '"SOVEREIGN_STORE_ROOT"]') in live, (
        "the env whitelist must be exactly the three governance vars — nothing credential-bearing, "
        "nothing that hand-wires resolution (e.g. PYTHONPATH)")


def test_the_registration_stays_enabled_and_nonfatal_to_the_conductor() -> None:
    """POSITIVE (pre-repair truth, preserved). `enabled = true` (the conductor gets the server)
    and `required = false` (a sovereign fault must not take down the conductor process — the
    degraded-state discipline W-55 established on the server side)."""
    cfg = CODEX_CONFIG.read_text(encoding="utf-8")
    live = "\n".join(_live_lines(cfg))
    body = live.split("[mcp_servers.sovereign]", 1)[1].split("[mcp_servers.", 1)[0]
    assert re.search(r"^enabled\s*=\s*true\s*$", body, re.MULTILINE)
    assert re.search(r"^required\s*=\s*false\s*$", body, re.MULTILINE)
