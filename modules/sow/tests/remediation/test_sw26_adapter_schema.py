"""SW-26 - Adapter validation must enforce the supported schema subset with explicit type
checks and stable, field-scoped AdapterErrors.

The finding: the validator accepted malformed `launch.argv` numeric entries and
`runtime_writes` numeric values (they slipped through and only broke deeper, or were silently
coerced to strings), and raised a raw `TypeError` - not a structured AdapterError with a field
path - for a malformed `id` or startup-timeout type. The loader catches only AdapterError, so a
raw TypeError from one malformed module could escape and stop the whole shell.

The shell is stdlib-only (a self-test asserts zero site-packages), so this extends the existing
hand-rolled checks rather than adding a JSON-schema library.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for _p in (str(RELEASE_ROOT), str(SHELL_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import adapter as adapter_mod  # noqa: E402

AdapterError = adapter_mod.AdapterError


def _schema():
    return adapter_mod._load_json(adapter_mod._SCHEMA_PATH)


def _valid_adapter():
    return {
        "id": "demo",
        "display_name": "Demo",
        "description": "test module",
        "state_class": "runnable",
        "root": "${install_root}/modules/demo",
        "runtime_writes": ["${state_root}/logs"],
        "launch": {"cwd": "${root}", "argv": ["${root}/app.exe", "--serve"],
                   "env_allowlist": [], "env_set": {}},
        "readiness": {"kind": "http", "url": "http://127.0.0.1:9/health",
                      "expect_status": 200, "timeout_s": 5, "poll_ms": 250},
        "identity": {"kind": "http_json", "url": "http://127.0.0.1:9/health",
                     "required_keys": ["status"]},
        "open": {"kind": "browser", "url": "http://127.0.0.1:9/"},
        "stop": {"kind": "job_object", "grace_s": 5},
    }


def _validate(a):
    adapter_mod._validate_against_schema(a, _schema())


# -- baseline: the valid adapter still passes ---------------------------------------------
def test_valid_adapter_passes_validation_and_compiles():
    a = _valid_adapter()
    _validate(a)  # must not raise
    adapter_mod.compile_adapter(a)  # must not raise


# -- id: a non-string must be an AdapterError, never a raw TypeError ----------------------
@pytest.mark.parametrize("bad_id", [123, ["demo"], {"x": 1}, None])
def test_non_string_id_is_adapter_error_not_typeerror(bad_id):
    a = _valid_adapter()
    a["id"] = bad_id
    with pytest.raises(AdapterError):  # NOT a bare TypeError escaping to the loader
        _validate(a)


def test_non_string_id_is_adapter_error_in_compile():
    # compile_adapter is reachable directly (startup test / deterministic suite) without going
    # through _validate_against_schema; it must fail closed the same way.
    a = _valid_adapter()
    a["id"] = 123
    with pytest.raises(AdapterError):
        adapter_mod.compile_adapter(a)


# -- launch.argv: numeric entries must be rejected with the exact index -------------------
def test_numeric_argv_entry_rejected_with_index():
    a = _valid_adapter()
    a["launch"]["argv"] = ["${root}/app.exe", 8080]
    with pytest.raises(AdapterError, match=r"launch\.argv\[1\] must be a string"):
        _validate(a)


def test_non_string_cwd_rejected():
    a = _valid_adapter()
    a["launch"]["cwd"] = 5
    with pytest.raises(AdapterError, match=r"launch\.cwd must be a non-empty string"):
        _validate(a)


# -- runtime_writes: numeric / malformed values must be rejected with a field path --------
def test_numeric_runtime_writes_entry_rejected():
    a = _valid_adapter()
    a["runtime_writes"] = ["${state_root}/logs", 123]
    with pytest.raises(AdapterError, match=r"runtime_writes\[1\] must be a string or object"):
        _validate(a)


def test_runtime_writes_object_numeric_path_rejected():
    a = _valid_adapter()
    a["runtime_writes"] = [{"path": 5, "kind": "dir"}]
    with pytest.raises(AdapterError, match=r"runtime_writes\[0\]\.path must be a non-empty string"):
        _validate(a)


def test_runtime_writes_object_bad_kind_rejected():
    a = _valid_adapter()
    a["runtime_writes"] = [{"path": "${root}/x", "kind": "socket"}]
    with pytest.raises(AdapterError, match=r"runtime_writes\[0\]\.kind must be"):
        _validate(a)


def test_runtime_writes_object_unknown_field_rejected():
    a = _valid_adapter()
    a["runtime_writes"] = [{"path": "${root}/x", "kind": "dir", "mode": 777}]
    with pytest.raises(AdapterError, match=r"runtime_writes\[0\] has unknown field"):
        _validate(a)


def test_runtime_writes_not_a_list_rejected():
    a = _valid_adapter()
    a["runtime_writes"] = "not-a-list"
    with pytest.raises(AdapterError, match=r"runtime_writes must be an array"):
        _validate(a)


def test_valid_object_runtime_write_still_accepted():
    a = _valid_adapter()
    a["runtime_writes"] = [{"path": "${root}/data", "kind": "dir"}]
    _validate(a)  # must not raise


# -- startup_test timeouts: a wrong type must be an AdapterError, never a raw TypeError ----
def _with_startup_test(timeout_s, poll_ms=1000):
    a = _valid_adapter()
    a["startup_test"] = {
        "readiness": {"kind": "receipt_file", "path": "${state_root}/r.json",
                      "timeout_s": timeout_s, "poll_ms": poll_ms},
    }
    return a


def test_string_startup_timeout_is_adapter_error_not_typeerror():
    a = _with_startup_test(timeout_s="45")  # string, not a number
    with pytest.raises(AdapterError, match=r"startup_test\.readiness\.timeout_s must be a number"):
        _validate(a)


def test_string_startup_poll_ms_is_adapter_error_not_typeerror():
    a = _with_startup_test(timeout_s=30, poll_ms="500")
    with pytest.raises(AdapterError, match=r"startup_test\.readiness\.poll_ms must be a number"):
        _validate(a)


def test_valid_startup_test_still_accepted():
    a = _with_startup_test(timeout_s=30, poll_ms=500)
    _validate(a)  # must not raise


# -- the shipped adapters all still validate + compile (no regression) --------------------
def test_all_shipped_adapters_validate_and_compile():
    modules_dir = RELEASE_ROOT / "shell" / "modules"
    schema = _schema()
    seen = 0
    for path in sorted(modules_dir.glob("*.json")):
        if path.name == "schema.json":
            continue
        raw = adapter_mod._load_json(str(path))
        adapter_mod._validate_against_schema(raw, schema)
        adapter_mod.compile_adapter(raw)
        seen += 1
    assert seen >= 5, f"expected the shipped module adapters, found {seen}"
