"""
Root process of the H-6 job-containment fixture tree (R3-2).

    fixture_tree.py <root_pid_file> <child_pid_file> <grandchild_pid_file>

Writes its own PID, spawns fixture_leaf.py (which spawns a grandchild that attempts
CREATE_BREAKAWAY_FROM_JOB), then sleeps 120 s. All three PIDs must die when the supervisor stops
the module, and when the shell process crashes.
"""
import os
import subprocess
import sys
import time


def main():
    root_pid_file, child_pid_file, grandchild_pid_file = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(root_pid_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    here = os.path.dirname(os.path.abspath(__file__))
    leaf = os.path.join(here, "fixture_leaf.py")
    proc = subprocess.Popen([sys.executable, leaf, child_pid_file, grandchild_pid_file])
    print("child spawned: {}".format(proc.pid), flush=True)

    time.sleep(120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
