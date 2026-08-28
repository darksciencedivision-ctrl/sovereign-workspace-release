"""Retired adapter compatibility entry point.

The product no longer has a second HTTP implementation.  Existing operator
commands that invoke ``ui/adapter_service/adapter.py`` are forwarded to the
same unified Flask service used by ``Start-Sovereign.ps1`` and
``python -m sovereign_product.server``.

``adapter_config.json`` and ``adapter_settings.json`` are intentionally not
read.  Runtime configuration and durable settings belong to the unified
service so this compatibility path cannot create competing state.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence


ADAPTER_VERSION = "compat-unified-1"
COMPATIBILITY_TARGET = "sovereign_product.server"
ROOT_MARKER = ".sovereign-root"
ROOT_MARKER_CONTENT = "SOVEREIGN_ROOT_MARKER=1"


def find_product_root(start: str | Path | None = None) -> Path:
    """Find the marker-validated product root without machine-specific paths."""

    origin = Path(start or __file__).expanduser().resolve(strict=False)
    if origin.is_file() or origin.suffix:
        origin = origin.parent
    for candidate in (origin, *origin.parents):
        marker = candidate / ROOT_MARKER
        try:
            valid = (
                marker.is_file()
                and marker.read_text(encoding="utf-8").strip()
                == ROOT_MARKER_CONTENT
            )
        except OSError:
            valid = False
        if valid:
            return candidate
    raise RuntimeError(
        f"unable to locate a valid {ROOT_MARKER} above {origin}"
    )


def _has_root_argument(arguments: Sequence[str]) -> bool:
    return any(
        argument == "--root" or argument.startswith("--root=")
        for argument in arguments
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Forward legacy invocation to the canonical unified service."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    root = find_product_root()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    from sovereign_product.server import main as unified_main

    forwarded = list(arguments)
    if not _has_root_argument(forwarded):
        forwarded[0:0] = ["--root", root_text]
    print(
        "[adapter compatibility] forwarding to "
        f"{COMPATIBILITY_TARGET}; no legacy adapter state is used."
    )
    return int(unified_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
