"""LOOP-01 shell lifecycle driver (adapted from evidence/gate5/tools/shell_driver.py).

Starts the product shell exactly as the README says (py -3.12 -B -m shell.src) with stdout and
stderr redirected under evidence/loop5/, in a new process group. Stops it ONLY via its own
shutdown path: CTRL_BREAK_EVENT -> KeyboardInterrupt -> main()'s finally -> supervisor.close(),
the H-9 cleanup. Triggered by sentinel shell.stop next to this script.
"""
import os
import signal
import subprocess
import sys
import time

WS = r"D:\Product Software\Production Workspace"
PY = r"C:\Windows\py.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WS, "evidence", "loop5", "shell-stdout.txt")
ERR = os.path.join(WS, "evidence", "loop5", "shell-stderr.txt")
STOP = os.path.join(HERE, "shell.stop")
PIDFILE = os.path.join(WS, "evidence", "loop5", "shell.pid")


def main():
    argv = [PY, "-3.12", "-B", "-m", "shell.src"]
    with open(OUT, "ab", buffering=0) as fo, open(ERR, "ab", buffering=0) as fe:
        proc = subprocess.Popen(
            argv, cwd=WS, stdout=fo, stderr=fe,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        with open(PIDFILE, "w") as f:
            f.write(str(proc.pid))
        print("SHELL-DRIVER started pid={} argv={}".format(proc.pid, argv), flush=True)
        stopped_by = None
        try:
            while not os.path.exists(STOP):
                rc = proc.poll()
                if rc is not None:
                    stopped_by = "exited rc={}".format(rc)
                    break
                time.sleep(0.4)
        finally:
            if stopped_by is None:
                stopped_by = "stopfile"
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception as e:
                    print("SHELL-DRIVER signal error: {!r}".format(e), flush=True)
            try:
                rc = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print("SHELL-DRIVER did not exit within 30 s of CTRL_BREAK", flush=True)
                rc = None
            print("SHELL-DRIVER stop={} exit_code={}".format(stopped_by, rc), flush=True)
            if os.path.exists(STOP):
                os.remove(STOP)
            try:
                os.remove(PIDFILE)
            except OSError:
                pass


if __name__ == "__main__":
    main()