"""Gate 5 shell lifecycle driver (work order A-2/C-1).

Starts the product shell exactly as the README says (py -3.12 -m shell.src) with stdout+stderr
redirected to evidence/gate5/shell-stdout.txt, in a new process group. Stops it ONLY via its own
shutdown path: CTRL_BREAK_EVENT -> KeyboardInterrupt -> main()'s finally -> supervisor.close()
(server.py:451-459), which is the H-9 cleanup under test. Triggered by the sentinel file
shell.stop next to this script.
"""
import os
import signal
import subprocess
import sys
import time

WS = r"D:\Product Software\Production Workspace"
OUT = os.path.join(WS, "evidence", "gate5", "shell-stdout.txt")
ERR = os.path.join(WS, "evidence", "gate5", "shell-stderr.txt")
STOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shell.stop")
PIDFILE = os.path.join(WS, "evidence", "gate5", "shell.pid")


def main():
    argv = ["py", "-3.12", "-B", "-m", "shell.src"]
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
