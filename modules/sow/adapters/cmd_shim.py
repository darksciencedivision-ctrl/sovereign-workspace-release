"""N-03 / L-1 — refuse cmd.exe metacharacters on a .cmd-shim argv.

Windows npm shims are `*.cmd`. CreateProcess + cmd.exe re-parse the argument
vector; Python `list2cmdline` quoting does not stop `& | ^ < > %` from
executing (INDEPENDENT_REVIEW_WINDOWS_HOST_20260816 N-03). Validate every
argv element, including the executable path, before a .cmd shim is spawned.
"""
from __future__ import annotations

from collections.abc import Sequence

CMD_SHIM_METACHARS = frozenset("&|^<>%")


class CmdShimMetacharacter(ValueError):
    """An argv destined for a .cmd shim carried a cmd.exe metacharacter."""


def is_cmd_shim(path: str) -> bool:
    return str(path).lower().endswith(".cmd")


def assert_cmd_shim_argv_safe(argv: Sequence[str]) -> None:
    if not argv:
        return
    if not is_cmd_shim(str(argv[0])):
        return
    for index, raw in enumerate(argv):
        arg = str(raw)
        hits = "".join(ch for ch in CMD_SHIM_METACHARS if ch in arg)
        if hits:
            raise CmdShimMetacharacter(
                "refusing .cmd-shim argv[%d] carrying cmd.exe metacharacters %r: %r"
                % (index, hits, arg)
            )
