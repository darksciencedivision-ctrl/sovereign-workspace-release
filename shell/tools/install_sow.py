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
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESKTOP = os.path.join(WORKSPACE, "modules", "sow", "apps", "desktop")
ZIP_HASH_RECORD = os.path.join(WORKSPACE, "docs", "ADR-005-ELECTRON-ZIP-SHA256.txt")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
LOG_PATH = None

PLATFORM_TAG = "win32-x64"
RELEASE_URL = "https://github.com/electron/electron/releases/download/v{ver}/electron-v{ver}-{tag}.zip"

_log_lines = []


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def log(msg):
    line = "[{}] {}".format(utc_now(), msg)
    _log_lines.append(line)
    print(line, flush=True)


def default_log_path():
    state = os.environ.get("SOVEREIGN_WORKSPACE_STATE")
    if state:
        return os.path.join(state, "sow-install.log")
    return os.path.join(tempfile.gettempdir(), "sow-install-{}.log".format(os.getpid()))


def flush_log():
    path = LOG_PATH or default_log_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(utc_now()))
        f.write("# tool: shell/tools/install_sow.py (ADR-005)\n")
        f.write("# log_path: {}\n".format(path))
        f.write("\n".join(_log_lines))
        f.write("\n")
    return path


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


def expected_zip_hash(ver, zip_name, desktop=None, hash_record=None):
    """Expected SHA-256, preferring the vendor-shipped checksums.json (ADR-005 decision 2).

    Malformed vendor or pin files fail closed. A missing pin returns (None, "none").
    This function never writes the pin file.
    """
    desktop = DESKTOP if desktop is None else desktop
    hash_record = ZIP_HASH_RECORD if hash_record is None else hash_record
    checks = os.path.join(desktop, "node_modules", "electron", "checksums.json")
    if os.path.isfile(checks):
        try:
            with open(checks, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            die("ELECTRON_ZIP_UNVERIFIABLE: checksums.json is malformed ({})".format(e))
        if not isinstance(data, dict):
            die("ELECTRON_ZIP_UNVERIFIABLE: checksums.json is not an object")
        if zip_name in data:
            h = str(data[zip_name]).strip().lower()
            if not _SHA256_RE.match(h):
                die("ELECTRON_ZIP_UNVERIFIABLE: checksums.json entry for {} is not a SHA-256".format(
                    zip_name))
            log("  expected hash source = node_modules/electron/checksums.json")
            return h, "checksums.json"
    if os.path.isfile(hash_record):
        try:
            with open(hash_record, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            die("ELECTRON_ZIP_UNVERIFIABLE: hash record unreadable ({})".format(e))
        found = None
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            parts = stripped.split()
            if len(parts) != 2 or not _SHA256_RE.match(parts[0]):
                die("ELECTRON_ZIP_UNVERIFIABLE: malformed hash record line {}".format(i))
            if parts[1] == zip_name:
                found = parts[0].lower()
        if found:
            log("  expected hash source = {}".format(hash_record))
            return found, "recorded"
    return None, "none"


def record_zip_hash(zip_name, digest):
    log("  observed Electron zip {} sha256={}".format(zip_name, digest))
    log("  (NOT written to docs/ADR-005-ELECTRON-ZIP-SHA256.txt; pin it there deliberately at "
        "build time if this is a new supported version)")


def find_cached_zip(zip_name, cache_root=None):
    base = cache_root
    if base is None:
        base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "electron", "Cache")
    hits = []
    if base and os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            cand = os.path.join(base, entry, zip_name)
            if os.path.isfile(cand):
                hits.append(cand)
    return base, hits


def _download_zip(url, target, urlopen=None):
    opener = urllib.request.urlopen if urlopen is None else urlopen
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    tmp = target + ".partial"
    try:
        with opener(url, timeout=600) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out, length=1 << 20)
        os.replace(tmp, target)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def step_4_5_zip(ver, allow_unverified=False, desktop=None, hash_record=None,
                 cache_root=None, urlopen=None):
    log("STEP 4/5: locate and verify the Electron zip")
    desktop = DESKTOP if desktop is None else desktop
    hash_record = ZIP_HASH_RECORD if hash_record is None else hash_record
    zip_name = "electron-v{}-{}.zip".format(ver, PLATFORM_TAG)
    log("  electron version = {} (from node_modules/electron/package.json)".format(ver))
    log("  zip name         = {}".format(zip_name))

    expected, source = expected_zip_hash(ver, zip_name, desktop=desktop, hash_record=hash_record)
    verified = False
    if expected:
        log("  expected sha256  = {} ({})".format(expected, source))
    elif not allow_unverified:
        die("ELECTRON_ZIP_UNVERIFIABLE: no expected SHA-256 for {} (checksums.json missing and "
            "no recorded pin). Refusing trust-on-first-use. Provision node_modules/electron so "
            "its checksums.json is present, or pass --allow-unverified-electron to bootstrap "
            "an unverified official download deliberately. That mode cannot pin a hash and "
            "cannot be reported as verified.".format(zip_name))
    else:
        log("  expected sha256  = UNKNOWN; --allow-unverified-electron -> proceeding UNVERIFIED")

    base, hits = find_cached_zip(zip_name, cache_root=cache_root)
    log("  cache root       = {}".format(base or "(unset)"))
    log("  cached copies    = {}".format(len(hits)))

    chosen = None
    for cand in hits:
        digest = sha256_file(cand)
        log("    {} sha256={}".format(cand, digest))
        if expected is None:
            log("    -> no expected hash; not trusting cached copy, will download from official URL")
            continue
        if digest == expected:
            chosen = (cand, digest)
            log("    -> matches expected hash, using this copy")
            break
        log("    -> does NOT match expected hash, skipping")

    if chosen is None:
        url = RELEASE_URL.format(ver=ver, tag=PLATFORM_TAG)
        target_dir = os.path.join(base, "rem01-{}".format(ver)) if base else os.path.join(
            desktop, ".electron-zip")
        target = os.path.join(target_dir, zip_name)
        log("  no verified cached copy; downloading {}".format(url))
        try:
            _download_zip(url, target, urlopen=urlopen)
        except Exception as e:
            die("download failed: {}".format(e))
        digest = sha256_file(target)
        log("  downloaded {} sha256={}".format(target, digest))
        if expected is not None and digest != expected:
            try:
                os.remove(target)
            except OSError:
                pass
            die("ELECTRON_ZIP_UNVERIFIABLE: downloaded {} has sha256 {} but expected {}".format(
                zip_name, digest, expected))
        chosen = (target, digest)

    zip_path, digest = chosen
    if expected is None:
        record_zip_hash(zip_name, digest)
        log("  SHA-256 UNVERIFIED (bootstrap; no trusted pin was written)")
    elif digest != expected:
        die("ELECTRON_ZIP_UNVERIFIABLE: {} has sha256 {} but expected {}".format(
            zip_path, digest, expected))
    else:
        verified = True
        log("  SHA-256 VERIFIED against {}".format(source))
    log("  zip path         = {}".format(zip_path))
    log("  zip sha256       = {}".format(digest))
    log("  zip size         = {} bytes".format(os.path.getsize(zip_path)))
    return zip_path, digest, verified


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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unverified-electron", action="store_true",
        help="download the official Electron zip with no trusted pin. Cannot be reported as "
             "verified and does not write a pin. Default is fail-closed.")
    parser.add_argument("--log", default=None,
                        help="install log path (default: state-root or temp, never tracked evidence/)")
    return parser.parse_args(argv)


def main(argv=None):
    global LOG_PATH
    args = parse_args(argv)
    LOG_PATH = args.log or default_log_path()
    log("install_sow.py starting (ADR-005, REM-01 R2-2)")
    log("workspace = {}".format(WORKSPACE))
    log("log path = {}".format(LOG_PATH))
    if args.allow_unverified_electron:
        log("UNVERIFIED bootstrap requested via --allow-unverified-electron")
    step_1_verify_cwd()
    node_exe, npm_cli = step_2_resolve_node()
    step_3_npm_ci(node_exe, npm_cli)
    ver = read_electron_version()
    zip_path, digest, verified = step_4_5_zip(
        ver, allow_unverified=args.allow_unverified_electron)
    step_6_7_extract(ver, zip_path)
    step_8_node_pty(node_exe)
    if verified:
        log("RESULT: SOW provisioning complete, Electron zip SHA-256 VERIFIED")
    else:
        log("RESULT: SOW provisioning complete, Electron zip UNVERIFIED (bootstrap; no pin written)")
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
