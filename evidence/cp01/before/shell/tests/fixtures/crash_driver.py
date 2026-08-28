"""
Shell-crash driver for the H-6 crash test (R3-4).

    crash_driver.py <root_pid_file> <child_pid_file> <grandchild_pid_file>

Spawns the fixture tree through a real JobSupervisor, waits until all three PIDs exist, then
calls os._exit(1) — no cleanup, no atexit, no finally. JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE on the
shell job must kill the whole tree anyway.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, WORKSPACE)

from shell.src.supervisor import JobSupervisor  # noqa: E402


def main():
    root_pid_file, child_pid_file, grandchild_pid_file = sys.argv[1:4]
    sup = JobSupervisor()
    env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
           "PATH": os.environ.get("PATH", ""),
           "PYTHONDONTWRITEBYTECODE": "1"}
    sup.spawn(
        "crashtest",
        [os.path.realpath(sys.executable), "-B", os.path.join(HERE, "fixture_tree.py"),
         root_pid_file, child_pid_file, grandchild_pid_file],
        HERE, env)

    deadline = time.time() + 20
    while time.time() < deadline:
        if all(os.path.isfile(p) and os.path.getsize(p) > 0
               for p in (root_pid_file, child_pid_file, grandchild_pid_file)):
            break
        time.sleep(0.1)

    print("crash_driver: tree up, exiting hard", flush=True)
    # Hard exit: no supervisor cleanup runs. Only KILL_ON_JOB_CLOSE can save us.
    os._exit(1)


if __name__ == "__main__":
    main()
