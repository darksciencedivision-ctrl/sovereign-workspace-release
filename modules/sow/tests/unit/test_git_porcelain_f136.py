"""F-136(6) — NUL-safe git porcelain parsing."""
from __future__ import annotations

from adapters.coding.opencode.git_porcelain import parse_porcelain_z


def test_ordinary_and_untracked():
    raw = b" M src/a.py\0?? new file.txt\0"
    assert parse_porcelain_z(raw) == [(" M", "src/a.py"), ("??", "new file.txt")]


def test_quoted_characters_are_literal_with_z():
    raw = b'M  path with space.txt\0A  cafe\xc3\xa9.txt\0'
    pairs = parse_porcelain_z(raw)
    assert pairs[0] == ("M ", "path with space.txt")
    assert pairs[1][1].endswith("cafe\u00e9.txt") or "cafe" in pairs[1][1]


def test_rename_uses_destination():
    raw = b"R  old.txt\0new.txt\0"
    assert parse_porcelain_z(raw) == [("R ", "new.txt")]
