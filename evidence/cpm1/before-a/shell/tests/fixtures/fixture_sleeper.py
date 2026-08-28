"""Grandchild of the H-6 fixture tree: writes its PID and sleeps (R3-2)."""
import os
import sys
import time


def main():
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    time.sleep(120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
