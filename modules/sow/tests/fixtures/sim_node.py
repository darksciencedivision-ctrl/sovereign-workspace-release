"""Simulated node for Phase 2 supervision tests and the soak (test fixture, not product).

Prints "HB" on stdout every --hb-ms. Fault injection:
  --hang-after-s N   stop heartbeating after N seconds but stay alive (DISCONNECTED path)
  --crash-after-s N  exit(3) after N seconds (unexpected-exit / restart path)
"""
from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hb-ms", type=int, default=250)
    parser.add_argument("--hang-after-s", type=float, default=None)
    parser.add_argument("--crash-after-s", type=float, default=None)
    args = parser.parse_args()

    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if args.crash_after_s is not None and elapsed >= args.crash_after_s:
            print("SIM: crashing now", flush=True)
            return 3
        if args.hang_after_s is not None and elapsed >= args.hang_after_s:
            time.sleep(3600)  # alive but silent
        print("HB", flush=True)
        time.sleep(args.hb_ms / 1000.0)


if __name__ == "__main__":
    sys.exit(main())
