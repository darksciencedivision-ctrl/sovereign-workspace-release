"""
SWS Adapter loader, validator, and compiler.

Path containment (H-5) is by canonical resolution via GetFinalPathNameByHandleW, never by
prefix-string comparison. See _canonical() and is_contained().
"""
import ctypes
import json
import os
import sys
import re
import hashlib
from ctypes import wintypes
from typing import Any


_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "modules", "schema.json")
_MODULES_DIR = os.path.join(os.path.dirname(__file__), "..", "modules")

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_PLACEHOLDER_PATTERN = re.compile(r"<PHASE-1-VERIFIED>")
_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


class AdapterError(Exception):
    pass


# --------------------------------------------------------------------------
# H-5 — canonical path resolution and containment.
#
# Prefix-string comparison is forbidden as the containment mechanism (§7.6 H-5). A path is
# canonicalized by opening a handle with FILE_FLAG_BACKUP_SEMANTICS (so directories and reparse
# points can be opened) and asking the OS for the final name, which resolves junctions, symlinks
# and 8.3 short names. Containment is then os.path.commonpath equality, case-folded.
# --------------------------------------------------------------------------

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_GENERIC_READ = 0
_FILE_SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004  # READ | WRITE | DELETE
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_VOLUME_NAME_DOS = 0x0

_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.GetFinalPathNameByHandleW.argtypes = [
    wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
]
_kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_EXTENDED_PREFIXES = ("\\\\?\\", "//?/")
_DEVICE_PREFIXES = ("\\\\.\\", "//./")


def reject_unc_and_device(path: str) -> None:
    """Reject UNC and device paths BEFORE canonicalization (H-5).

    Order matters: an extended-length or device prefix must be refused on the raw input, not
    after the OS has normalized it away.
    """
    p = str(path)
    for pref in _EXTENDED_PREFIXES + _DEVICE_PREFIXES:
        if p.startswith(pref):
            raise AdapterError(f"Device or extended-length path not allowed: {path}")
    norm = p.replace("/", "\\")
    if norm.startswith("\\\\"):
        raise AdapterError(f"UNC paths not allowed: {path}")


def _strip_extended(p: str) -> str:
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[len("\\\\?\\UNC\\"):]
    if p.startswith("\\\\?\\"):
        return p[len("\\\\?\\"):]
    return p


def _canonical(path: str) -> str:
    """Canonical, case-folded absolute path.

    Uses GetFinalPathNameByHandleW on a handle opened with FILE_FLAG_BACKUP_SEMANTICS. Falls
    back to os.path.realpath ONLY when the path does not exist yet, which is the one case the
    handle-based call cannot serve.
    """
    raw = os.path.abspath(str(path).replace("/", os.sep))
    handle = _kernel32.CreateFileW(
        raw, _GENERIC_READ, _FILE_SHARE_ALL, None,
        _OPEN_EXISTING, _FILE_FLAG_BACKUP_SEMANTICS, None,
    )
    if handle and handle != _INVALID_HANDLE_VALUE:
        try:
            size = _kernel32.GetFinalPathNameByHandleW(handle, None, 0, _VOLUME_NAME_DOS)
            if size:
                buf = ctypes.create_unicode_buffer(size + 1)
                written = _kernel32.GetFinalPathNameByHandleW(
                    handle, buf, size + 1, _VOLUME_NAME_DOS)
                if written:
                    return os.path.normpath(_strip_extended(buf.value)).casefold()
        finally:
            _kernel32.CloseHandle(handle)
    # Path does not exist (or cannot be opened): realpath is the documented fallback.
    return os.path.normpath(_strip_extended(os.path.realpath(raw))).casefold()


def is_contained(root: str, candidate: str) -> bool:
    """True when `candidate` is inside `root` after canonical resolution (H-5).

    UNC and device paths are rejected before canonicalization and return False.
    """
    try:
        reject_unc_and_device(root)
        reject_unc_and_device(candidate)
    except AdapterError:
        return False
    c_root = _canonical(root)
    c_cand = _canonical(candidate)
    try:
        return os.path.commonpath([c_root, c_cand]) == c_root
    except ValueError:
        # Different drives, or a mix of absolute and relative: not contained.
        return False


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise AdapterError(f"Cannot load {path}: {e}")


def _validate_against_schema(adapter: dict, schema: dict) -> None:
    """Basic schema validation. Full JSON Schema validation would need a lib."""
    # R18/F-028. Type BEFORE operation. A top-level JSON array/string/number reaching `.get`/`in`
    # raised AttributeError/TypeError -- which load_all_adapters (catching only AdapterError) let
    # escape and stop the whole shell. A wrongly-typed adapter is one module's CONFIG_ERROR, never
    # a shell crash, so every shape mismatch is raised as AdapterError here.
    if not isinstance(adapter, dict):
        raise AdapterError(f"adapter must be a JSON object, got {type(adapter).__name__}")
    # Check required fields
    for field in schema.get("required", []):
        if field not in adapter:
            raise AdapterError(f"Missing required field: {field}")

    # Check additionalProperties
    allowed = set(schema.get("properties", {}).keys())
    for key in adapter:
        if key not in allowed:
            raise AdapterError(f"Unknown field: {key}")

    # Check state_class
    if adapter.get("state_class") not in ("runnable", "not_started"):
        raise AdapterError(f"Invalid state_class: {adapter.get('state_class')}")

    # Check id
    if not _ID_PATTERN.match(adapter.get("id", "")):
        raise AdapterError(f"Invalid id: {adapter.get('id')}")

    if adapter.get("state_class") == "runnable":
        # Must have launch, readiness, identity, open, stop
        for field in ("launch", "readiness", "identity", "open", "stop"):
            if field not in adapter:
                raise AdapterError(f"Runnable module missing required field: {field}")

        _validate_nested(adapter, "launch", {"cwd", "argv"})
        _validate_nested(adapter, "readiness", {"kind", "timeout_s", "poll_ms"})
        _validate_nested(adapter, "identity", {"kind"})
        _validate_nested(adapter, "open", {"kind"})
        _validate_nested(adapter, "stop", {"kind", "grace_s"})

        # Validate launch
        launch = adapter["launch"]
        if not isinstance(launch["argv"], list) or len(launch["argv"]) < 1 or len(launch["argv"]) > 32:
            raise AdapterError("launch.argv must be 1-32 items")
        for i, arg in enumerate(launch["argv"]):
            if len(str(arg)) > 1024:
                raise AdapterError(f"launch.argv[{i}] exceeds 1024 chars")

        # Validate readiness
        readiness = adapter["readiness"]
        if readiness["kind"] not in ("http", "process_window", "receipt_file"):
            raise AdapterError(f"Invalid readiness.kind: {readiness['kind']}")
        # R18/F-028. Numeric fields are range-checked, so a string (or any non-number) must be
        # rejected as AdapterError rather than raising TypeError inside the comparison.
        if not _is_number(readiness.get("timeout_s")) or not (5 <= readiness["timeout_s"] <= 120):
            raise AdapterError("readiness.timeout_s must be a number 5-120")
        if not _is_number(readiness.get("poll_ms")) or not (250 <= readiness["poll_ms"] <= 5000):
            raise AdapterError("readiness.poll_ms must be a number 250-5000")

        # Validate identity. process_path/path_prefix is gone: H-5 forbids prefix-string
        # comparison, and ADR-004 requires canonical-image equality instead (R3-11).
        identity = adapter["identity"]
        if identity["kind"] not in ("http_json", "http_html_marker", "process_image"):
            raise AdapterError(f"Invalid identity.kind: {identity['kind']}")
        if identity["kind"] == "process_image" and "path_prefix" in identity:
            raise AdapterError("identity.path_prefix is forbidden (H-5); use process_image")

        # Validate open
        open_cfg = adapter["open"]
        # N-23: a third kind. `browser` opens a URL, `focus_window` raises the native window the
        # shell already launched, `none` declares that the module has no open action at all - and
        # `none` now has to mean it, because the Open control follows this value (states.can_open).
        if open_cfg["kind"] not in ("browser", "focus_window", "none"):
            raise AdapterError(f"Invalid open.kind: {open_cfg['kind']}")
        if open_cfg["kind"] == "browser" and not open_cfg.get("url"):
            raise AdapterError("open.kind browser requires open.url")
        if open_cfg["kind"] != "browser" and open_cfg.get("url"):
            raise AdapterError(f"open.url is meaningless for open.kind {open_cfg['kind']}")

        # Validate stop
        stop = adapter["stop"]
        if stop["kind"] != "job_object":
            raise AdapterError(f"Invalid stop.kind: {stop['kind']}")
        if not _is_number(stop.get("grace_s")) or not (1 <= stop["grace_s"] <= 30):
            raise AdapterError("stop.grace_s must be a number 1-30")

        # Optional startup_test override block (ADR-004, R3-11).
        st = adapter.get("startup_test")
        if st is not None:
            if not isinstance(st, dict):
                raise AdapterError("startup_test must be an object")
            for key in st:
                if key not in ("env_set", "readiness"):
                    raise AdapterError(f"Unknown startup_test field: {key}")
            if "env_set" in st:
                if not isinstance(st["env_set"], dict) or not all(
                        isinstance(v, str) for v in st["env_set"].values()):
                    raise AdapterError("startup_test.env_set must be an object of strings")
            if "readiness" in st:
                r = st["readiness"]
                if not isinstance(r, dict):
                    raise AdapterError("startup_test.readiness must be an object")
                for key in r:
                    if key not in ("kind", "path", "require", "timeout_s", "poll_ms"):
                        raise AdapterError(f"Unknown startup_test.readiness field: {key}")
                if r.get("kind") != "receipt_file":
                    raise AdapterError("startup_test.readiness.kind must be receipt_file")
                if not r.get("path"):
                    raise AdapterError("startup_test.readiness.path is required")
                if not isinstance(r.get("require", {}), dict):
                    raise AdapterError("startup_test.readiness.require must be an object")
                if not (5 <= r.get("timeout_s", 0) <= 120):
                    raise AdapterError("startup_test.readiness.timeout_s must be 5-120")
                if not (250 <= r.get("poll_ms", 0) <= 5000):
                    raise AdapterError("startup_test.readiness.poll_ms must be 250-5000")


def _is_number(value) -> bool:
    """R18/F-028. True for a real int/float, excluding bool (which is an int subclass)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_nested(adapter: dict, key: str, required: set) -> None:
    obj = adapter.get(key, {})
    # R18/F-028. A nested value that is not an object (e.g. `"readiness": "http"`) must be a
    # CONFIG_ERROR, not a TypeError from `field in obj` against a non-container.
    if not isinstance(obj, dict):
        raise AdapterError(f"{key} must be an object")
    for field in required:
        if field not in obj:
            raise AdapterError(f"{key}.{field} is required")


def _check_placeholder_literals(obj: Any, path: str = "") -> None:
    """Recursively check for <PHASE-1-VERIFIED> literals."""
    if isinstance(obj, str):
        if _PLACEHOLDER_PATTERN.search(obj):
            raise AdapterError(f"<PHASE-1-VERIFIED> literal found at {path}: {obj}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_placeholder_literals(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_placeholder_literals(v, f"{path}[{i}]")


# EPC-01 P4-4. The workspace's per-operator state root.
#
# Runtime state used to live INSIDE the install root — `${root}/runtime`, `${root}/data` and
# friends. That is the root cause of two further defects: uninstall compares the install tree
# against its manifest and refuses once the product has written anything (P0-5), and there is
# no upgrade path because a new install cannot reuse a destination that holds live state
# (P1-1). State that lives inside the thing being replaced cannot survive replacing it.
#
# %LOCALAPPDATA% is the Windows convention for per-user application state and is already in
# every adapter's `env_allowlist`, so a launched module can see it without widening what the
# shell passes through.
STATE_ROOT_ENV = "SOVEREIGN_WORKSPACE_STATE"
STATE_ROOT_DIRNAME = "SovereignWorkspace"


def workspace_state_root() -> str:
    """The root under which every module's runtime state lives, POSIX-separated."""
    override = os.environ.get(STATE_ROOT_ENV, "").strip()
    if override:
        base = override
    else:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if not local:
            # No %LOCALAPPDATA% (a service account, or a non-Windows test host): fall back to
            # the user profile rather than inventing a drive path.
            local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        base = os.path.join(local, STATE_ROOT_DIRNAME)
    return os.path.abspath(base).replace("\\", "/")


def module_state_root(module_id: str) -> str:
    """This module's own state directory. One per module, never shared."""
    return f"{workspace_state_root()}/{module_id}"


# EPC-01 P3-4 / P3-5. The install root, DERIVED rather than configured.
#
# Every adapter used to hardcode this machine's absolute path in its `root`, and two of them
# additionally hardcoded this machine's `python.exe`. `install.ps1` and `rebase_adapters.py`
# rewrote both at install time, so it was a disclosure rather than a functional break -- the
# archive shipped the build operator's username and directory layout to every recipient.
#
# Rewriting at install time also has a failure mode of its own: the value is correct only for
# as long as nobody moves the installation, and a rebase that silently does not match leaves a
# path that exists on no machine. Deriving the root from where the shell actually is removes
# both problems. `${install_root}` is computed from this file's own location, so it is right by
# construction, survives the directory being moved or renamed, and discloses nothing.
#
# The compiled value is still an absolute, canonicalised path, so H-5 containment is unchanged.
INSTALL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Override for the interpreter that Python-launched modules run under. Absent, the shell
#: launches them with the interpreter it is itself running under, which is the honest default:
#: a recorded absolute path can go stale, `sys.executable` cannot.
PYTHON_312_ENV = "SOVEREIGN_PYTHON_312"


def install_root() -> str:
    """The root of this installation, POSIX-separated. Derived, never configured."""
    return INSTALL_ROOT.replace("\\", "/")


def python_312() -> str:
    """The interpreter Python-launched modules run under."""
    override = os.environ.get(PYTHON_312_ENV, "").strip()
    if override:
        return os.path.abspath(override).replace("\\", "/")
    return os.path.abspath(sys.executable).replace("\\", "/")


def _resolve_var(value: str, root: str | None, state_root: str | None = None) -> str:
    """Resolve ${install_root}, ${python312}, ${root} and ${state_root}.

    Any other ${...} raises. `root` is None only while the adapter's own `root` field is being
    resolved -- it cannot reference itself, and saying so is better than resolving it to
    something empty and letting a containment check pass against nonsense.
    """
    def replacer(m):
        var = m.group(1)
        if var == "install_root":
            return install_root()
        if var == "python312":
            return python_312()
        if var == "root":
            if root is None:
                raise AdapterError(
                    "${root} is not available here; the adapter's own root field may only "
                    "use ${install_root}")
            return root
        if var == "state_root":
            if state_root is None:
                raise AdapterError(
                    "${state_root} is not available here; it may only be used in "
                    "runtime_writes and launch.env_set")
            return state_root
        raise AdapterError(f"Unknown variable: ${{{var}}}")
    return _VAR_PATTERN.sub(replacer, value)


def _resolve_path(path: str, root: str, state_root: str | None = None) -> str:
    """Resolve and canonicalize a path."""
    resolved = _resolve_var(path, root, state_root)
    resolved = resolved.replace("\\", "/")
    # Canonicalize
    try:
        canonical = os.path.realpath(resolved)
    except OSError:
        canonical = os.path.normpath(resolved)
    return canonical.replace("\\", "/")


def _validate_path(path: str) -> None:
    """Validate path: no UNC, no device paths, must be absolute.

    UNC and device rejection is delegated to reject_unc_and_device so that the raw-input
    ordering required by H-5 is enforced in exactly one place.
    """
    reject_unc_and_device(path)
    if not os.path.isabs(path):
        raise AdapterError(f"Path must be absolute: {path}")


def compile_adapter(adapter: dict) -> dict:
    """Compile an adapter: resolve all paths, validate, return compiled config."""
    _check_placeholder_literals(adapter, "adapter")

    # Validate id
    if not _ID_PATTERN.match(adapter.get("id", "")):
        raise AdapterError(f"Invalid id: {adapter.get('id')}")

    root = _resolve_var(adapter["root"], root=None)
    _validate_path(root)

    compiled = dict(adapter)
    compiled["root"] = _resolve_path(root, root)

    # EPC-01 P4-4. Each module's state root, resolved before runtime_writes so a declaration
    # may name it. One directory per module — never shared, so one module cannot reach
    # another's state through a path it declares.
    compiled["state_root"] = module_state_root(compiled["id"])

    if adapter.get("runtime_writes"):
        compiled["runtime_writes"] = [
            _resolve_path(w, compiled["root"], compiled["state_root"])
            for w in adapter["runtime_writes"]
        ]
        # H-5 EXTENDED, deliberately and narrowly. Every declared write target must be inside
        # the compiled root OR inside THIS module's own state root, by canonical resolution. A
        # junction or ".." that escapes both is a CONFIG_ERROR, not a warning.
        #
        # The invariant H-5 protects is "a module writes only where it declared it would, and
        # the declaration cannot be widened by a symlink". Admitting a second, named,
        # per-module root does not weaken that: it is still two exact locations resolved
        # canonically, and a path escaping both is still refused. What it removes is the
        # accidental coupling that forced runtime state to live inside the install tree — the
        # coupling that makes uninstall (P0-5) and upgrade (P1-1) impossible.
        for w in compiled["runtime_writes"]:
            if is_contained(compiled["root"], w):
                continue
            if is_contained(compiled["state_root"], w):
                continue
            raise AdapterError(
                f"runtime_writes path escapes both the install root and this module's state "
                f"root (H-5): {w}")
    else:
        compiled["runtime_writes"] = []

    if adapter.get("state_class") == "runnable":
        launch = dict(adapter["launch"])
        launch["cwd"] = _resolve_path(launch["cwd"], compiled["root"])
        _validate_path(launch["cwd"])
        if not is_contained(compiled["root"], launch["cwd"]):
            raise AdapterError(f"launch.cwd escapes root (H-5): {launch['cwd']}")

        launch["argv"] = [_resolve_var(a, compiled["root"]) for a in launch["argv"]]
        for i, arg in enumerate(launch["argv"]):
            _validate_path(arg) if i == 0 else None
        if not launch["argv"][0].lower().endswith(".exe"):
            raise AdapterError(f"argv[0] must end in .exe: {launch['argv'][0]}")

        # F-028. Compare the BASENAME exactly, not as a substring: "cmd.exe" as a substring
        # rejected an innocent "mycmd.exe", while the old set also missed other script hosts
        # (pwsh, wscript, cscript, mshta). Extension checks stay as endswith on the basename.
        argv0_lower = launch["argv"][0].lower().replace("\\", "/")
        basename = argv0_lower.rsplit("/", 1)[-1]
        if basename.endswith((".cmd", ".bat", ".ps1", ".vbs", ".wsf")):
            raise AdapterError(f"argv[0] is a script launcher, not a .exe: {basename}")
        forbidden_exe = {
            "cmd.exe", "powershell.exe", "pwsh.exe",
            "wscript.exe", "cscript.exe", "mshta.exe",
        }
        if basename in forbidden_exe:
            raise AdapterError(f"argv[0] is a forbidden launcher: {basename}")

        launch["env_allowlist"] = adapter["launch"].get("env_allowlist", ["SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"])
        launch["env_set"] = {
            key: _resolve_var(value, compiled["root"], compiled["state_root"])
            for key, value in dict(adapter["launch"].get("env_set", {})).items()
        }

        # EPC-01 P4-4. Every module is told where its state root is, whether or not its
        # adapter names it. A module that does not read the variable is unaffected; a module
        # that does no longer depends on the shell's author having remembered to declare it.
        launch["env_set"].setdefault(STATE_ROOT_ENV, compiled["state_root"])

        compiled["launch"] = launch

        # H-10: quota guard for SOW
        if adapter["id"] == "sow":
            if launch["env_set"].get("SOW_CONDUCTOR_AUTOLAUNCH") != "0":
                raise AdapterError("SOW adapter must set SOW_CONDUCTOR_AUTOLAUNCH=0 (H-10)")
            compiled["quota_guard"] = {"required": True, "autolaunch_value": "0"}

        # Compile readiness
        readiness = dict(adapter["readiness"])
        if readiness["kind"] == "http":
            if "url" not in readiness:
                raise AdapterError("http readiness requires url")
        if readiness["kind"] == "receipt_file":
            # CP-M1 G15: module-level receipt readiness.
            #
            # SWS-CORRECTIVE-01 C3. This resolved against the install root ONLY, so a module's
            # normal-launch readiness receipt was forced to live inside the installation. SOW's
            # did: `main.js` wrote `${root}/.runtime/receipts/SHELL-LIVE-READY.json` on every
            # normal launch, a path `runtime_writes` declared nowhere, and one that a
            # non-writable installation directory makes impossible.
            #
            # `${state_root}` now resolves here on exactly the terms `runtime_writes` and the
            # startup_test override already use: two exact locations, resolved canonically,
            # with anything escaping both refused. H-5's invariant is unchanged.
            if not readiness.get("path"):
                raise AdapterError("receipt_file readiness requires path")
            readiness["path"] = _resolve_path(
                readiness["path"], compiled["root"], compiled["state_root"])
            if not (is_contained(compiled["root"], readiness["path"])
                    or is_contained(compiled["state_root"], readiness["path"])):
                raise AdapterError(
                    "readiness.path escapes both the install root and this module's state "
                    "root (H-5): " + readiness["path"])
        compiled["readiness"] = readiness

        # Compile identity. For process_image the expected value is the compiled argv[0], so
        # there is nothing separate to configure and nothing to prefix-match.
        identity = dict(adapter["identity"])
        if identity["kind"] == "process_image":
            identity["expected_image"] = launch["argv"][0]
        compiled["identity"] = identity

        # Compile the startup_test override block (ADR-004, R3-11).
        # D6: ${state_root} must expand in startup_test.env_set and may name the
        # startup-test receipt lane under this module's state root.
        st = adapter.get("startup_test")
        if st is not None:
            st = json.loads(json.dumps(st))  # deep copy
            # SW-REMED-001 F-16, contract item 2. This block resolved the readiness path against
            # the install root ONLY and never resolved `env_set` at all, so a startup test could
            # not name the module's own state root in either place. The consequence was measured on
            # the operator's host: SOW's startup test launched the self-check, the self-check wrote
            # a fresh `ok:true` receipt to its default `.runtime/receipts` lane, and readiness sat
            # watching the git-tracked `docs/evidence/receipts` fossil until it timed out at 90 s
            # with "Receipt is stale (predates launch)". The probe was right every time; the
            # descriptor had no way to say where the receipt actually goes.
            #
            # Both fixes mirror `runtime_writes` above rather than inventing a second convention:
            # `${state_root}` resolves, and containment admits the install root OR this module's
            # own state root and nothing else. H-5's invariant is unchanged — still two exact
            # locations, resolved canonically, with anything escaping both refused. What it stops
            # forcing is runtime evidence back inside the install tree, which is the coupling
            # `runtime_writes` already refuses to accept.
            if "env_set" in st:
                st["env_set"] = {
                    key: _resolve_var(value, compiled["root"], compiled["state_root"])
                    # `.get(...) or {}` from the hotfix branch: a descriptor may carry
                    # `env_set: null`, and `dict(None)` would raise where an empty mapping is
                    # the honest reading of "declared nothing".
                    for key, value in dict(st.get("env_set") or {}).items()
                }
            if "readiness" in st and "path" in st["readiness"]:
                st["readiness"]["path"] = _resolve_path(
                    st["readiness"]["path"], compiled["root"], compiled["state_root"])
                path = st["readiness"]["path"]
                if not (
                    is_contained(compiled["root"], path)
                    or is_contained(compiled["state_root"], path)
                ):
                    raise AdapterError(
                        "startup_test.readiness.path escapes both the install root and "
                        "this module's state root (H-5): " + path)
            compiled["startup_test"] = st

        # Compile open
        compiled["open"] = dict(adapter["open"])

        # Compile stop
        compiled["stop"] = dict(adapter["stop"])

    # Hash the adapter for immutability tracking
    adapter_json = json.dumps(adapter, sort_keys=True)
    compiled["_adapter_hash"] = hashlib.sha256(adapter_json.encode()).hexdigest()

    return compiled


def load_all_adapters() -> dict[str, dict]:
    """Load all adapter JSONs from modules dir, validate, and compile."""
    schema = _load_json(_SCHEMA_PATH)
    adapters = {}

    for fname in sorted(os.listdir(_MODULES_DIR)):
        if fname == "schema.json" or not fname.endswith(".json"):
            continue
        path = os.path.join(_MODULES_DIR, fname)
        try:
            raw = _load_json(path)
        except AdapterError:
            adapters[fname] = {"error": "CONFIG_ERROR", "reason": f"Cannot parse {fname}"}
            continue

        try:
            _validate_against_schema(raw, schema)
            compiled = compile_adapter(raw)
            module_id = compiled["id"]
            # F-028. A duplicate id used to silently overwrite the earlier module. Keep the first
            # and record the collision as a CONFIG_ERROR rather than making a module vanish.
            if module_id in adapters and not adapters[module_id].get("error"):
                fallback = f"{module_id}#dup:{fname}"
                adapters[fallback] = {
                    "error": "CONFIG_ERROR",
                    "reason": f"duplicate adapter id {module_id!r} (already defined); {fname} ignored",
                    "id": fallback,
                }
                continue
            adapters[module_id] = compiled
        except Exception as e:  # noqa: BLE001
            # R18/F-028. ANY malformed adapter (wrong types, bad nesting, a compile fault) is ONE
            # module's CONFIG_ERROR, never a shell-wide crash: the loader previously caught only
            # AdapterError, so a TypeError/AttributeError from a wrongly-typed field escaped and
            # stopped every module's dashboard. `raw` may not be a dict, so the fallback id is
            # guarded.
            adapter_id = raw.get("id", fname) if isinstance(raw, dict) else fname
            if not isinstance(adapter_id, str) or not adapter_id:
                adapter_id = fname
            adapters.setdefault(adapter_id, {
                "error": "CONFIG_ERROR", "reason": str(e), "id": adapter_id})

    return adapters