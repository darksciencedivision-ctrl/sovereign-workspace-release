"""EPC-01 — a shipped PowerShell script must be pure ASCII and must parse.

Windows PowerShell 5.1 reads a `.ps1` with no byte-order mark using the system ANSI codepage,
not UTF-8. A non-ASCII character therefore arrives as mojibake — harmless in a comment, and a
**parse failure** when it lands inside a string, which is exactly what happened while writing
`upgrade.ps1`: an em dash in a `Write-Output` broke the script with a misleading
"Missing closing '}'" reported eleven lines away from the actual cause.

Adding a BOM would fix the decoding and violate P1-7, which removed BOMs from tracked files
because a BOM is content and changes every hash taken over the file. So the scripts stay pure
ASCII instead, and this guard keeps them that way.

Three of the shipped scripts carried non-ASCII when this was written, two of them from
comments added during this programme. All are now clean.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SEARCH_ROOTS = (REPO_ROOT / "tools" / "release", REPO_ROOT / "shell")

#: A character that reads acceptably under ANSI and a replacement that always does.
SUGGESTIONS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', " ": " ", "…": "...",
}


def _scripts():
    for root in SEARCH_ROOTS:
        if root.is_dir():
            for path in sorted(root.rglob("*.ps1")):
                if "node_modules" in path.parts:
                    continue
                yield path


class PowerShellScriptsAreAscii(unittest.TestCase):

    def test_some_scripts_are_actually_found(self) -> None:
        found = list(_scripts())
        self.assertGreaterEqual(
            len(found), 5, f"only {len(found)} PowerShell scripts found — the guard is blind"
        )

    def test_no_shipped_script_carries_a_byte_order_mark(self) -> None:
        """P1-7: a BOM is content and changes every hash taken over the file."""
        offenders = [
            str(p.relative_to(REPO_ROOT))
            for p in _scripts()
            if p.read_bytes().startswith(b"\xef\xbb\xbf")
        ]
        self.assertEqual(offenders, [], "PowerShell scripts carry a UTF-8 BOM:\n  "
                                        + "\n  ".join(offenders))

    def test_no_shipped_script_carries_non_ascii(self) -> None:
        offenders = []
        for path in _scripts():
            raw = path.read_bytes()
            bad = sorted({b for b in raw if b > 127})
            if not bad:
                continue
            text = raw.decode("utf-8", errors="replace")
            found = sorted({ch for ch in text if ord(ch) > 127})
            hints = ", ".join(
                f"{ch!r} -> {SUGGESTIONS[ch]!r}" for ch in found if ch in SUGGESTIONS
            )
            offenders.append(
                f"{path.relative_to(REPO_ROOT)}: {len(bad)} byte value(s) "
                + (f"({hints})" if hints else f"({found})")
            )
        self.assertEqual(
            offenders, [],
            "PowerShell 5.1 reads a BOM-less .ps1 as ANSI, so these arrive as mojibake — and a "
            "non-ASCII character inside a STRING is a parse failure, reported at a misleading "
            "line:\n  " + "\n  ".join(offenders)
        )

    def test_every_shipped_script_parses(self) -> None:
        """The property the rule above exists to protect. Checked directly as well, because a
        script can be pure ASCII and still be broken."""
        failures = []
        for path in _scripts():
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                 f"'{path}',[ref]$null,[ref]$e); if($e.Count){{ exit 1 }} else {{ exit 0 }}"],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                failures.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(
            failures, [], "these PowerShell scripts do not parse:\n  " + "\n  ".join(failures)
        )


if __name__ == "__main__":
    unittest.main()
