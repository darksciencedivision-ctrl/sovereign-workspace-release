"""
SOW module provisioning — REM-01 R2-2, implements ADR-005.

Python standard library only. Run with:

    py -3.12 shell\\tools\\install_sow.py

Performs, in order:
  1. verify the SOW desktop directory exists and is the working directory
  2. resolve node.exe and npm-cli.js absolutely (never npm.cmd, never a shell)
  3. npm ci --ignore-scripts
  4. locate or download the Electron zip matching node_modules/electron/package.json
  5. verify its SHA-256 against the expected value (ADR-005)
  6. extract it to node_modules/electron/dist/
  7. write node_modules/electron/path.txt and dist/version
  8. verify node-pty loads from its win32-x64 prebuild
Every step is logged to evidence/phase2-sow-install.txt. Any mismatch exits non-zero.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESKTOP = os.path.join(WORKSPACE, "modules", "sow", "apps", "desktop")
LOG_PATH = os.path.join(WORKSPACE, "evidence", "phase2-sow-install.txt")
ZIP_HASH_RECORD = os.path.join(WORKSPACE, "docs", "ADR-005-ELECTRON-ZIP-SHA256.txt")

PLATFORM_TAG = "win32-x64"
RELEASE_URL = "https://github.com/electron/electron/releases/download/v{ver}/electron-v{ver}-{tag}.zip"

_log_lines = []


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def log(msg):
    line = "[{}] {}".format(utc_now(), msg)
    _log_lines.append(line)
    print(line, flush=True)


def flush_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(utc_now()))
        f.write("# producer: claude-code REM-01\n")
        f.write("# tool: shell/tools/install_sow.py (ADR-005)\n")
        f.write("\n".join(_log_lines))
        f.write("\n")


def die(msg, code=1):
    log("FATAL: " + msg)
    flush_log()
    sys.exit(code)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def step_1_verify_cwd():
    log("STEP 1: verify SOW desktop directory")
    if not os.path.isdir(DESKTOP):
        die("SOW desktop directory not found: {}".format(DESKTOP))
    os.chdir(DESKTOP)
    actual = os.path.normcase(os.path.realpath(os.getcwd()))
    expected = os.path.normcase(os.path.realpath(DESKTOP))
    if actual != expected:
        die("cwd is {}, expected {}".format(actual, expected))
    if not os.path.isfile(os.path.join(DESKTOP, "package.json")):
        die("package.json not found in {}".format(DESKTOP))
    log("  cwd = {}".format(DESKTOP))
    lock = os.path.join(DESKTOP, "package-lock.json")
    if not os.path.isfile(lock):
        die("package-lock.json absent; ADR-005 requires 'npm ci', which needs a lockfile")
    log("  package-lock.json present, sha256={}".format(sha256_file(lock)))


def step_2_resolve_node():
    log("STEP 2: resolve node.exe and npm-cli.js")
    node_exe = shutil.which("node")
    if not node_exe:
        die("node.exe not found on PATH")
    node_exe = os.path.realpath(node_exe)
    if not node_exe.lower().endswith(".exe"):
        die("resolved node is not an .exe: {}".format(node_exe))
    for bad in (".cmd", ".bat", ".ps1"):
        if node_exe.lower().endswith(bad):
            die("forbidden launcher extension in {}".format(node_exe))
    npm_cli = os.path.join(os.path.dirname(node_exe), "node_modules", "npm", "bin", "npm-cli.js")
    if not os.path.isfile(npm_cli):
        die("npm-cli.js not found at {}".format(npm_cli))
    v = subprocess.run([node_exe, "--version"], capture_output=True, text=True, timeout=60)
    log("  node.exe   = {}".format(node_exe))
    log("  node       = {}".format(v.stdout.strip()))
    log("  npm-cli.js = {}".format(npm_cli))
    nv = subprocess.run([node_exe, npm_cli, "--version"], capture_output=True, text=True,
                        timeout=180, cwd=DESKTOP)
    log("  npm        = {}".format(nv.stdout.strip()))
    return node_exe, npm_cli


def step_3_npm_ci(node_exe, npm_cli):
    log("STEP 3: npm ci --ignore-scripts (ADR-005 decision 1)")
    argv = [node_exe, npm_cli, "ci", "--ignore-scripts"]
    log("  argv = {!r}".format(argv))
    r = subprocess.run(argv, cwd=DESKTOP, capture_output=True, text=True, timeout=3600)
    for line in (r.stdout or "").splitlines():
        log("  npm> " + line)
    for line in (r.stderr or "").splitlines():
        log("  npm! " + line)
    log("  exit code = {}".format(r.returncode))
    if r.returncode != 0:
        die("npm ci --ignore-scripts failed with exit code {}".format(r.returncode))


def read_electron_version():
    pkg = os.path.join(DESKTOP, "node_modules", "electron", "package.json")
    if not os.path.isfile(pkg):
        die("node_modules/electron/package.json missing after npm ci")
    with open(pkg, "r", encoding="utf-8") as f:
        return json.load(f)["version"]


def expected_zip_hash(ver, zip_name):
    """Expected SHA-256, preferring the vendor-shipped checksums.json (ADR-005 decision 2)."""
    checks = os.path.join(DESKTOP, "node_modules", "electron", "checksums.json")
    if os.path.isfile(checks):
        try:
            with open(checks, "r", encoding="utf-8") as f:
                data = json.load(f)
            if zip_name in data:
                h = data[zip_name].strip().lower()
                if len(h) == 64:
                    log("  expected hash source = node_modules/electron/checksums.json")
                    return h, "checksums.json"
        except (OSError, ValueError, KeyError) as e:
            log("  checksums.json unreadable ({}), falling back".format(e))
    if os.path.isfile(ZIP_HASH_RECORD):
        for line in open(ZIP_HASH_RECORD, "r", encoding="utf-8"):
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == zip_name and len(parts[0]) == 64:
                log("  expected hash source = docs/ADR-005-ELECTRON-ZIP-SHA256.txt")
                return parts[0].lower(), "recorded"
    return None, "none"


def record_zip_hash(zip_name, digest):
    header = ("# utc: {}\n# producer: claude-code REM-01\n"
              "# ADR-005 first-run record of Electron zip SHA-256. Subsequent runs must match.\n"
              ).format(utc_now())
    existing = ""
    if os.path.isfile(ZIP_HASH_RECORD):
        existing = open(ZIP_HASH_RECORD, "r", encoding="utf-8").read()
        if not existing.endswith("\n"):
            existing += "\n"
    else:
        existing = header
    with open(ZIP_HASH_RECORD, "w", encoding="utf-8", newline="\n") as f:
        f.write(existing)
        f.write("{}  {}\n".format(digest, zip_name))
    log("  recorded {} {} in docs/ADR-005-ELECTRON-ZIP-SHA256.txt".format(digest, zip_name))


def find_cached_zip(zip_name):
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "electron", "Cache")
    hits = []
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            cand = os.path.join(base, entry, zip_name)
            if os.path.isfile(cand):
                hits.append(cand)
    return base, hits


def step_4_5_zip(ver):
    log("STEP 4/5: locate and verify the Electron zip")
    zip_name = "electron-v{}-{}.zip".format(ver, PLATFORM_TAG)
    log("  electron version = {} (from node_modules/electron/package.json)".format(ver))
    log("  zip name         = {}".format(zip_name))

    expected, source = expected_zip_hash(ver, zip_name)
    if expected:
        log("  expected sha256  = {} ({})".format(expected, source))
    else:
        log("  expected sha256  = UNKNOWN — first run may record it (ADR-005 decision 2)")

    base, hits = find_cached_zip(zip_name)
    log("  cache root       = {}".format(base or "(LOCALAPPDATA unset)"))
    log("  cached copies    = {}".format(len(hits)))

    chosen = None
    for cand in hits:
        digest = sha256_file(cand)
        log("    {} sha256={}".format(cand, digest))
        if expected is None:
            chosen = (cand, digest)
            break
        if digest == expected:
            chosen = (cand, digest)
            log("    -> matches expected hash, using this copy")
            break
        log("    -> does NOT match expected hash, skipping")

    if chosen is None:
        url = RELEASE_URL.format(ver=ver, tag=PLATFORM_TAG)
        target_dir = os.path.join(base, "rem01-{}".format(ver)) if base else os.path.join(DESKTOP, ".electron-zip")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, zip_name)
        log("  no verified cached copy; downloading {}".format(url))
        try:
            with urllib.request.urlopen(url, timeout=600) as resp, open(target, "wb") as out:
                shutil.copyfileobj(resp, out, length=1 << 20)
        except Exception as e:
            die("download failed: {}".format(e))
        digest = sha256_file(target)
        log("  downloaded {} sha256={}".format(target, digest))
        chosen = (target, digest)

    zip_path, digest = chosen
    if expected is None:
        record_zip_hash(zip_name, digest)
    elif digest != expected:
        die("ELECTRON_ZIP_UNVERIFIABLE: {} has sha256 {} but expected {}".format(
            zip_path, digest, expected))
    else:
        log("  SHA-256 VERIFIED against {}".format(source))
    log("  zip path         = {}".format(zip_path))
    log("  zip sha256       = {}".format(digest))
    log("  zip size         = {} bytes".format(os.path.getsize(zip_path)))
    return zip_path, digest


def step_6_7_extract(ver, zip_path):
    log("STEP 6/7: extract to dist/ and write path.txt + dist/version")
    electron_dir = os.path.join(DESKTOP, "node_modules", "electron")
    dist = os.path.join(electron_dir, "dist")
    if os.path.isdir(dist):
        shutil.rmtree(dist)
        log("  removed pre-existing dist/")
    os.makedirs(dist, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        zf.extractall(dist)
    log("  extracted {} entries".format(len(members)))
    exe = os.path.join(dist, "electron.exe")
    if not os.path.isfile(exe):
        die("electron.exe not present after extraction")
    log("  electron.exe size   = {} bytes".format(os.path.getsize(exe)))
    log("  electron.exe sha256 = {}".format(sha256_file(exe)))
    with open(os.path.join(electron_dir, "path.txt"), "w", encoding="utf-8", newline="") as f:
        f.write("electron.exe")
    log("  wrote path.txt = electron.exe")
    with open(os.path.join(dist, "version"), "w", encoding="utf-8", newline="") as f:
        f.write("v{}".format(ver))
    log("  wrote dist/version = v{}".format(ver))


def step_8_node_pty(node_exe):
    log("STEP 8: verify node-pty prebuild")
    prebuild_dir = os.path.join(DESKTOP, "node_modules", "node-pty", "prebuilds", "win32-x64")
    if not os.path.isdir(prebuild_dir):
        die("node-pty prebuilds/win32-x64 not found at {}".format(prebuild_dir))
    nodes = sorted(n for n in os.listdir(prebuild_dir) if n.endswith(".node"))
    if not nodes:
        die("no .node prebuild in {}".format(prebuild_dir))
    for n in nodes:
        p = os.path.join(prebuild_dir, n)
        log("  {} {} bytes sha256={}".format(n, os.path.getsize(p), sha256_file(p)))
    r = subprocess.run([node_exe, "-e", "require('node-pty')"], cwd=DESKTOP,
                       capture_output=True, text=True, timeout=120)
    for line in (r.stdout or "").splitlines():
        log("  pty> " + line)
    for line in (r.stderr or "").splitlines():
        log("  pty! " + line)
    if r.returncode != 0:
        die("require('node-pty') failed with exit code {}".format(r.returncode))
    log("  require('node-pty') OK")


def main():
    log("install_sow.py starting (ADR-005, REM-01 R2-2)")
    log("workspace = {}".format(WORKSPACE))
    step_1_verify_cwd()
    node_exe, npm_cli = step_2_resolve_node()
    step_3_npm_ci(node_exe, npm_cli)
    ver = read_electron_version()
    zip_path, digest = step_4_5_zip(ver)
    step_6_7_extract(ver, zip_path)
    step_8_node_pty(node_exe)
    log("RESULT: SOW provisioning complete, all steps verified")
    flush_log()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - log then fail loudly
        log("UNHANDLED: {}: {}".format(type(exc).__name__, exc))
        flush_log()
        sys.exit(1)
