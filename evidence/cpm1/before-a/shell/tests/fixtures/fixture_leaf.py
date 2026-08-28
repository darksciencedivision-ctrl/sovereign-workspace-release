"""
Middle process of the H-6 job-containment fixture tree (R3-2).

    fixture_leaf.py <own_pid_file> <grandchild_pid_file>

Writes its own PID, spawns a grandchild with CREATE_BREAKAWAY_FROM_JOB (0x01000000) — which must
FAIL to escape the Job Object — then sleeps.
"""
import os
import subprocess
import sys
import time

CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def main():
    own_pid_file, grandchild_pid_file = sys.argv[1], sys.argv[2]
    with open(own_pid_file, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    here = os.path.dirname(os.path.abspath(__file__))
    sleeper = os.path.join(here, "fixture_sleeper.py")

    # The breakaway attempt is the point of the test. If the Job forbids breakaway (it does,
    # because JOB_OBJECT_LIMIT_BREAKAWAY_OK is never set), CreateProcess fails with
    # ERROR_ACCESS_DENIED; fall back to a normal spawn so the grandchild still exists and can be
    # asserted to be inside the job.
    try:
        proc = subprocess.Popen(
            [sys.executable, sleeper, grandchild_pid_file],
            creationflags=CREATE_BREAKAWAY_FROM_JOB)
        print("grandchild spawned WITH breakaway flag: {}".format(proc.pid), flush=True)
    except OSError as e:
        proc = subprocess.Popen([sys.executable, sleeper, grandchild_pid_file])
        print("breakaway refused ({}), grandchild spawned normally: {}".format(
            e, proc.pid), flush=True)

    time.sleep(120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
