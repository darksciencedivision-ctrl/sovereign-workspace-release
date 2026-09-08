"""CLI fixture for acceptance process-ownership tests."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--port", type=int, default=-1)
    parser.add_argument("--spawn-child", action="store_true")
    parser.add_argument("--child-no-root", action="store_true")
    parser.add_argument("--sleep", type=float, default=90.0)
    args, _unknown = parser.parse_known_args()
    child = None
    sock = None
    if args.spawn_child:
        cmd = [sys.executable, os.path.abspath(__file__), "--sleep", str(args.sleep)]
        if args.root and not args.child_no_root:
            cmd.extend(["--root", args.root])
        child = subprocess.Popen(cmd)
        print("child", child.pid, flush=True)
    if args.port >= 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.listen(1)
        print("port", sock.getsockname()[1], flush=True)
    print("pid", os.getpid(), flush=True)
    try:
        time.sleep(args.sleep)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
        if sock is not None:
            sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
