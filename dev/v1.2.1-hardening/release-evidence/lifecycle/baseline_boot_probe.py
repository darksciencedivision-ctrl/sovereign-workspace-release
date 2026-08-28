import json, socket, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worktree"))
WORKTREE = Path(__file__).resolve().parents[2] / "worktree"
PORT = 8700
result = {"phase": "phase0_baseline_boot", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

def port_open(p):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0

def pre_listeners():
    out = subprocess.run(["cmd", "/c", "netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if f":{PORT}" in l and "LISTENING" in l]

pre = pre_listeners()
if pre:
    print(json.dumps({"fatal": "port_busy_preexisting", "listeners": pre}))
    sys.exit(2)

proc = subprocess.Popen([sys.executable, "app.py"], cwd=str(WORKTREE),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
t0 = time.monotonic()
http_ok = False
http_status = None
body_marker = False
while time.monotonic() - t0 < 30:
    if proc.poll() is not None:
        break
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/")
        with urllib.request.urlopen(req, timeout=2) as r:
            http_status = r.status
            body = r.read().decode("utf-8", "replace")
            body_marker = "<title>Debate Table</title>" in body
        if http_status == 200:
            http_ok = True
            break
    except Exception:
        time.sleep(0.4)
boot_seconds = round(time.monotonic() - t0, 3)
result["http_200"] = http_ok
result["http_status"] = http_status
result["frontend_title_marker"] = body_marker
result["boot_seconds"] = boot_seconds

ws_ok = False
ws_first_msg_type = None
ws_error = None
try:
    import websockets
    import anyio
    async def ws_probe():
        import websockets
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            return json.loads(msg)
    import asyncio
    try:
        first = asyncio.run(asyncio.wait_for(ws_probe(), timeout=8))
        ws_ok = isinstance(first, dict)
        ws_first_msg_type = first.get("type")
    except Exception as e:
        ws_error = repr(e)
except ImportError as e:
    ws_error = "websockets lib unavailable: " + repr(e)
result["websocket_connect"] = ws_ok
result["websocket_first_msg_type"] = ws_first_msg_type
result["websocket_error"] = ws_error

proc.terminate()
try:
    proc.wait(timeout=10)
    result["exit_code"] = proc.returncode
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait(timeout=10)
    result["exit_code"] = proc.returncode
    result["force_killed"] = True
time.sleep(1.0)
post = pre_listeners()
orphans = []
out = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"], capture_output=True, text=True)
for line in out.stdout.splitlines():
    if "app.py" in line and line.strip():
        orphans.append(line.strip())
result["port_listeners_after"] = post
result["orphan_app_processes"] = orphans
result["shutdown_clean"] = (not post) and (not orphans)
result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
print("LIFECYCLE_RESULT_JSON_BEGIN")
print(json.dumps(result, indent=2))

