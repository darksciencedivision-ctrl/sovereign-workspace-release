"""
SWS Adapter loader, validator, and compiler.

Path containment (H-5) is by canonical resolution via GetFinalPathNameByHandleW, never by
prefix-string comparison. See _canonical() and is_contained().
"""
import ctypes
import json
import os
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
        if not (5 <= readiness.get("timeout_s", 0) <= 120):
            raise AdapterError("readiness.timeout_s must be 5-120")
        if not (250 <= readiness.get("poll_ms", 0) <= 5000):
            raise AdapterError("readiness.poll_ms must be 250-5000")

        # Validate identity. process_path/path_prefix is gone: H-5 forbids prefix-string
        # comparison, and ADR-004 requires canonical-image equality instead (R3-11).
        identity = adapter["identity"]
        if identity["kind"] not in ("http_json", "http_html_marker", "process_image"):
            raise AdapterError(f"Invalid identity.kind: {identity['kind']}")
        if identity["kind"] == "process_image" and "path_prefix" in identity:
            raise AdapterError("identity.path_prefix is forbidden (H-5); use process_image")

        # Validate open
        open_cfg = adapter["open"]
        if open_cfg["kind"] not in ("browser", "none"):
            raise AdapterError(f"Invalid open.kind: {open_cfg['kind']}")

        # Validate stop
        stop = adapter["stop"]
        if stop["kind"] != "job_object":
            raise AdapterError(f"Invalid stop.kind: {stop['kind']}")
        if not (1 <= stop.get("grace_s", 0) <= 30):
            raise AdapterError("stop.grace_s must be 1-30")

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


def _validate_nested(adapter: dict, key: str, required: set) -> None:
    obj = adapter.get(key, {})
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


def _resolve_var(value: str, root: str) -> str:
    """Resolve ${root} in a string value. Any other ${...} raises error."""
    def replacer(m):
        var = m.group(1)
        if var == "root":
            return root
        raise AdapterError(f"Unknown variable: ${{{var}}}")
    return _VAR_PATTERN.sub(replacer, value)


def _resolve_path(path: str, root: str) -> str:
    """Resolve and canonicalize a path."""
    resolved = _resolve_var(path, root)
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

    root = adapter["root"]
    _validate_path(root)

    compiled = dict(adapter)
    compiled["root"] = _resolve_path(root, root)

    if adapter.get("runtime_writes"):
        compiled["runtime_writes"] = [_resolve_path(w, compiled["root"]) for w in adapter["runtime_writes"]]
        # H-5: every declared write target must be inside the compiled root, by canonical
        # resolution. A junction or ".." that escapes the root is a CONFIG_ERROR, not a warning.
        for w in compiled["runtime_writes"]:
            if not is_contained(compiled["root"], w):
                raise AdapterError(f"runtime_writes path escapes root (H-5): {w}")
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

        # Check no .cmd, .bat, .ps1, cmd.exe, powershell.exe
        argv0_lower = launch["argv"][0].lower()
        forbidden = [".cmd", ".bat", ".ps1", "cmd.exe", "powershell.exe"]
        for f in forbidden:
            if f in argv0_lower:
                raise AdapterError(f"argv[0] contains forbidden launcher: {f}")

        launch["env_allowlist"] = adapter["launch"].get("env_allowlist", ["SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"])
        launch["env_set"] = dict(adapter["launch"].get("env_set", {}))

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
        compiled["readiness"] = readiness

        # Compile identity. For process_image the expected value is the compiled argv[0], so
        # there is nothing separate to configure and nothing to prefix-match.
        identity = dict(adapter["identity"])
        if identity["kind"] == "process_image":
            identity["expected_image"] = launch["argv"][0]
        compiled["identity"] = identity

        # Compile the startup_test override block (ADR-004, R3-11).
        st = adapter.get("startup_test")
        if st is not None:
            st = json.loads(json.dumps(st))  # deep copy
            if "readiness" in st and "path" in st["readiness"]:
                st["readiness"]["path"] = _resolve_path(
                    st["readiness"]["path"], compiled["root"])
                if not is_contained(compiled["root"], st["readiness"]["path"]):
                    raise AdapterError(
                        "startup_test.readiness.path escapes root (H-5): "
                        + st["readiness"]["path"])
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
            adapters[compiled["id"]] = compiled
        except AdapterError as e:
            adapter_id = raw.get("id", fname)
            adapters[adapter_id] = {"error": "CONFIG_ERROR", "reason": str(e), "id": adapter_id}

    return adapters