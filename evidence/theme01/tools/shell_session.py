"""THEME-01 builder tooling: run one live-shell capture session.

Starts the shell on 127.0.0.1:5180 (absolute interpreter, argv array, no shell),
waits for readiness, executes the Edge headless capture plan, then stops the
shell through its own CTRL_BREAK path and waits. Writes a session log.

Usage: py -3.12 -B shell_session.py <session-log-path> <plan-file>
plan-file: JSON list of [outfile_relative_to_after_or_before_dir, args...] where
args are msedge switches; "{out}" placeholder receives the absolute output path.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import winreg

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXE = r"C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe"


def edge_path():
    with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
        val, _ = winreg.QueryValueEx(k, "")
    assert val and os.path.isfile(val), "msedge.exe not resolvable"
    return val


def main():
    log_path, plan_path = sys.argv[1], sys.argv[2]
    plan = json.loads(open(plan_path, "r", encoding="utf-8").read())
    logs = []
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [EXE, "-B", "-m", "shell.src", "--port", "5180"],
        cwd=WS, env=env, creationflags=flags,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logs.append("# utc: {} # producer: ox-alpha THEME01 shell_session".format(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    logs.append("shell pid={} argv=[...]-m shell.src --port 5180".format(proc.pid))
    base = "http://127.0.0.1:5180"
    ready = False
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/shell-info", timeout=1) as r:
                if r.status == 200:
                    ready = True
                    break
        except OSError:
            time.sleep(0.2)
    logs.append("ready={}".format(ready))
    if not ready:
        proc.kill()
        raise SystemExit("shell never became ready")
    edge = edge_path()
    for out_rel, args in plan:
        out_abs = os.path.join(WS, out_rel)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        cmd = [edge] + [a.replace("{out}", out_abs) for a in args] + [base + "/"]
        logs.append("CMD: " + " ".join(cmd))
        r = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        if "--dump-dom" in args:
            with open(out_abs, "w", encoding="utf-8", newline="\n") as f:
                f.write(r.stdout)
        time.sleep(0.4)
    proc.send_signal(signal.CTRL_BREAK_EVENT)
    try:
        rc = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = "killed"
    logs.append("shell stop via CTRL_BREAK_EVENT; exit={}".format(rc))
    out = proc.stdout.read() if proc.stdout else ""
    logs.append("--- shell stdout tail ---")
    logs.extend(out.splitlines()[-40:])
    open(log_path, "w", encoding="utf-8", newline="\n").write("\n".join(logs) + "\n")
    print("session complete; log:", log_path)


if __name__ == "__main__":
    main()