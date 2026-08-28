"""
SWS Shell — package entry point.

    py -3.12 -m shell.src [--port N] [--selftest]
    py -3.12 -I -S shell\\src\\__main__.py [--port N] [--selftest]

The second form is the H-11 isolated-interpreter proof. Under -I the interpreter does not put
the working directory on sys.path, so the workspace root is derived from __file__ here and
inserted explicitly. Every intra-package import is absolute (`from shell.src import ...`), so
the package resolves identically under both forms.
"""
import os
import sys

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)

from shell.src.server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
