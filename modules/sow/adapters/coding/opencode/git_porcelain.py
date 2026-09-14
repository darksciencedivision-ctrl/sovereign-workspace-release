"""NUL-safe `git status --porcelain -z` parsing (F-136(6))."""
from __future__ import annotations


def parse_porcelain_z(raw: bytes) -> list[tuple[str, str]]:
    """Return (xy, path) pairs from `git status -z --porcelain=v1`.

    Porcelain v1 with -z is `XY SP path NUL`, and for rename/copy
    `XY SP orig NUL dest NUL`. Paths are not C-quoted.
    """
    out: list[tuple[str, str]] = []
    i = 0
    data = raw
    while i < len(data):
        if i + 3 > len(data):
            break
        xy = data[i:i + 2].decode("ascii", "replace")
        if data[i + 2:i + 3] != b" ":
            nxt = data.find(b"\0", i)
            if nxt < 0:
                break
            i = nxt + 1
            continue
        i += 3
        nxt = data.find(b"\0", i)
        if nxt < 0:
            break
        first = data[i:nxt].decode("utf-8", "surrogateescape").replace("\\", "/")
        i = nxt + 1
        if xy[:1] in "RC":
            nxt = data.find(b"\0", i)
            if nxt < 0:
                path = first
            else:
                path = data[i:nxt].decode("utf-8", "surrogateescape").replace("\\", "/")
                i = nxt + 1
        else:
            path = first
        out.append((xy, path))
    return out
