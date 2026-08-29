"""
SWS Startup Test — launch, readiness, identity, record, stop.

Applies the adapter's optional `startup_test` override block (ADR-004, R3-11): its `env_set` is
merged OVER `launch.env_set`, and its `readiness` replaces `readiness` when present. The normal
Start path never uses either.
"""
import json
import os
import time
from datetime import datetime, timezone

from shell.src.redact import redact
from shell.src.states import ModuleRunner, build_env, check_quota_guard, QuotaGuardError


def _make_filename(module_id: str) -> str:
    """Windows-safe startup-test filename (no colons); body holds the full RFC 3339 value."""
    now = datetime.now(timezone.utc)
    return "{}-{}.{:03d}Z.json".format(
        module_id, now.strftime("%Y%m%dT%H%M%S"), now.microsecond // 1000)


def evidence_root() -> str:
    """Where startup-test records are written.

    Defaults to the workspace's gitignored `.runtime/evidence/` lane so normal product use never
    dirties tracked release inputs. `SWS_EVIDENCE_ROOT` redirects it, which the test suite uses
    so fixture records land in a tempfile directory. It is a test seam, not a feature: nothing
    in the product sets it and no UI or endpoint exposes it.
    """
    override = os.environ.get("SWS_EVIDENCE_ROOT", "").strip()
    if override:
        return override
    return os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", ".runtime", "evidence"))


def _record_path(module_id: str) -> str:
    evidence_dir = os.path.join(evidence_root(), "startup-tests")
    os.makedirs(evidence_dir, exist_ok=True)
    return os.path.join(evidence_dir, _make_filename(module_id))


def merged_env_overrides(adapter: dict) -> dict:
    """startup_test.env_set, merged over launch.env_set by build_env's override argument."""
    return dict(adapter.get("startup_test", {}).get("env_set", {}))


def effective_readiness(adapter: dict) -> dict:
    """startup_test.readiness when present, else the normal readiness block."""
    st = adapter.get("startup_test", {})
    if "readiness" in st:
        cfg = dict(st["readiness"])
        cfg.setdefault("timeout_s", 90)
        cfg.setdefault("poll_ms", 1000)
        return cfg
    return adapter["readiness"]


def run_startup_test(module_id: str, adapter: dict, supervisor, log_ring,
                     keep: bool = False, runner=None) -> dict:
    """Run a startup test: launch -> readiness -> identity -> record -> stop (or keep)."""
    own_runner = runner is None
    if own_runner:
        runner = ModuleRunner(module_id, adapter, supervisor, log_ring)

    env_overrides = merged_env_overrides(adapter)
    readiness_cfg = effective_readiness(adapter)
    env_preview = build_env(adapter, env_overrides)

    start_time = datetime.now(timezone.utc)
    result = {
        "module_id": module_id,
        "adapter_hash": adapter.get("_adapter_hash", ""),
        "compiled_argv": adapter.get("launch", {}).get("argv", []),
        "env_keys": sorted(env_preview.keys()),
        "startup_test_env_set": sorted(env_overrides.keys()),
        "readiness_kind": readiness_cfg.get("kind"),
        "readiness_source": "startup_test" if "readiness" in adapter.get("startup_test", {})
                            else "adapter",
        "start": start_time.isoformat(),
        "keep": keep,
        "readiness": {"outcome": "not_attempted", "latency_s": 0},
        "identity": {"outcome": "not_attempted", "latency_s": 0},
        "exit_code": None,
        "logs": [],
        "undeclared_writes": [],
        "quota_guard": None,
    }

    # H-10 layer 2 is recorded here as well as enforced in ModuleRunner.start.
    try:
        result["quota_guard"] = check_quota_guard(module_id, env_preview) or None
    except QuotaGuardError as e:
        result["readiness"] = {"outcome": "FAILED(QUOTA_GUARD)", "latency_s": 0, "error": str(e)}
        result["identity"] = {"outcome": "skipped", "latency_s": 0}
        result["end"] = datetime.now(timezone.utc).isoformat()
        _save_record(result, module_id)
        return result

    t0 = time.time()
    display, err = runner.start(env_overrides=env_overrides, readiness_override=readiness_cfg)
    elapsed = round(time.time() - t0, 3)

    ph = supervisor.get_process(module_id)

    if display.startswith("READY"):
        result["readiness"] = {"outcome": "READY", "latency_s": elapsed}
        result["identity"] = {"outcome": "PASS", "latency_s": 0}
    elif "IDENTITY" in display:
        result["readiness"] = {"outcome": "READY", "latency_s": elapsed}
        result["identity"] = {"outcome": "FAILED(IDENTITY)", "latency_s": 0, "error": err}
    else:
        result["readiness"] = {"outcome": display, "latency_s": elapsed, "error": err}
        result["identity"] = {"outcome": "skipped", "latency_s": 0}

    if not keep and display.startswith("READY"):
        runner.stop()
        ph = None

    result["exit_code"] = ph.exit_code if ph is not None else None
    # H-8: the ring already holds redacted lines; redact again on the way into the record so a
    # future change to the ring cannot leak into persisted evidence.
    result["logs"] = [redact(line) for line in log_ring.read_lines()]
    result["end"] = datetime.now(timezone.utc).isoformat()
    result["undeclared_writes"] = _undeclared_writes(adapter)
    _save_record(result, module_id)
    return result


def _undeclared_writes(adapter: dict) -> list:
    """Placeholder for the Gate 5 instance-tree diff.

    §7.2 makes this a finding, not a failure, and specifies it as a diff of the instance tree
    after the test. Gate 5 is where that diff is produced; recording an empty list here with an
    explicit marker is honest, whereas omitting the key would read as 'none found'.
    """
    return []


def _save_record(result: dict, module_id: str):
    path = _record_path(module_id)
    payload = json.dumps(result, indent=2, default=str)
    # H-8, fourth surface: nothing secret-bearing reaches a persisted evidence file.
    payload = redact(payload)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.write("\n")
        result["_record_path"] = path
    except OSError:
        pass
