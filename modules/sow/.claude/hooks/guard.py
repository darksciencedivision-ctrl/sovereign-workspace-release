#!/usr/bin/env python3
"""PreToolUse guard hook - Sovereign Orchestration Workspace.

Belt-and-suspenders enforcement over .claude/settings.json permission rules
(Claude Code Buildout Directive 2026-07-16, section 2.3):
  1. Hard-block file writes/edits outside the project root.
  2. Hard-block writes to frozen canonical documents (docs/canonical/**).
  3. Hard-block git push / remote / publish / network commands in Bash.

Exit codes: 0 = allow, 2 = block (stderr is fed back to the model).
This is the code-level analogue of the product's supervisor-containment
invariant (I-29): enforcement outside the harness, never trust alone.
"""
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FROZEN = [PROJECT_ROOT / "docs" / "canonical"]

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

BASH_BLOCK = [
    (r"\bgit\s+push\b", "git push is prohibited (local-only commits; operator decision required)"),
    (r"\bgit\s+remote\b", "git remote configuration is prohibited (no remotes in staged build)"),
    (r"\bgh\s+", "GitHub CLI is prohibited (no remote publication)"),
    (r"\bnpm\s+publish\b", "npm publish is prohibited"),
    (r"\bnpm\s+login\b", "npm login is prohibited (no credentials)"),
    (r"\btwine\b", "package publication is prohibited"),
    (r"\bcurl\b", "network fetch commands are prohibited in this repo"),
    (r"\bwget\b", "network fetch commands are prohibited in this repo"),
    (r"\bssh\b", "remote shell is prohibited"),
    (r"\bscp\b", "remote copy is prohibited"),
    (r"\brsync\s+[^ ]*::|\brsync\s+-[^ ]*e\b", "remote rsync is prohibited"),
    (r"\bgit\s+config\s+--global\b", "global git config changes are prohibited (local scope only)"),
]


def deny(msg: str) -> None:
    print(f"BLOCKED by .claude/hooks/guard.py: {msg}", file=sys.stderr)
    sys.exit(2)


def check_path(raw: str) -> None:
    if not raw:
        return
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        rp = p.resolve()
    except OSError:
        deny(f"unresolvable path: {raw}")
    if PROJECT_ROOT.resolve() not in rp.parents and rp != PROJECT_ROOT.resolve():
        deny(f"write outside project root: {rp}")
    for frozen in FROZEN:
        fr = frozen.resolve()
        if rp == fr or fr in rp.parents:
            deny(f"docs/canonical/ is frozen (Phase 0 canonical set): {rp}")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # malformed input: defer to permission rules
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input", {}) or {}
    if tool in WRITE_TOOLS:
        check_path(tin.get("file_path") or tin.get("notebook_path") or "")
    elif tool == "Bash":
        cmd = tin.get("command", "") or ""
        for pattern, msg in BASH_BLOCK:
            if re.search(pattern, cmd):
                deny(f"{msg} [matched: {pattern}]")
        for m in re.finditer(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*([^\s;|&]+)", cmd):
            target = m.group(1).strip("'\"")
            if target.startswith(("/", "~", "..")) or target.startswith("../"):
                p = Path(target).expanduser()
                if p.is_absolute():
                    try:
                        rp = p.resolve()
                        root = PROJECT_ROOT.resolve()
                        if root not in rp.parents and rp != root:
                            deny(f"bash redirect outside project root: {target}")
                    except OSError:
                        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
