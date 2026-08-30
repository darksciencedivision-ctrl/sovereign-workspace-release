"""
SWS module state machine — BUILD-DIRECTIVE §7.4, implemented exactly.

The transition logic lives here rather than inline in server.py so that every transition in §7.4
can be exercised by a test against a fixture process (R3-5). This is a refactor of logic that
already existed in server.py; it adds no feature, endpoint, or dependency.

States: NOT_STARTED, STOPPED, STARTING, READY, DEGRADED, FAILED(reason), EXTERNAL,
CONFIG_ERROR(reason).
"""
import os
import time

from shell.src import probe as probe_mod
from shell.src.supervisor import SupervisorError, query_process_image
from shell.src.adapter import _canonical

NOT_STARTED = "NOT_STARTED"
STOPPED = "STOPPED"
STARTING = "STARTING"
READY = "READY"
DEGRADED = "DEGRADED"
FAILED = "FAILED"
EXTERNAL = "EXTERNAL"
CONFIG_ERROR = "CONFIG_ERROR"

# G17 failure vocabulary - ten classes, defined once and reused (CP-M1 O-2). A FAILED
# reason is normalized onto one of these so /api/state and the card can render the class
# instead of an opaque legacy token like TIMEOUT.
FAILURE_CLASSES = [
    "PROCESS_START_FAILED", "PORT_UNAVAILABLE", "HEALTH_CHECK_FAILED",
    "IDENTITY_MISMATCH", "MODEL_UNAVAILABLE", "PROVIDER_UNAVAILABLE",
    "OPENCODE_UNAVAILABLE", "CONFIGURATION_FAILED", "WORKER_FAILED",
    "CONDUCTOR_COMMUNICATION_FAILED",
]

_LEGACY_CLASS = {
    "SPAWN": "PROCESS_START_FAILED",
    "JOB_ASSIGN": "PROCESS_START_FAILED",
    "EXIT": "PROCESS_START_FAILED",
    "TIMEOUT": "HEALTH_CHECK_FAILED",
    "IDENTITY": "IDENTITY_MISMATCH",
    "QUOTA_GUARD": "CONFIGURATION_FAILED",
}


def classify_failure(reason: str) -> str:
    """Map a raw failure reason onto exactly one FAILURE_CLASSES entry."""
    r = (reason or "").strip()
    if r in FAILURE_CLASSES:
        return r
    head = r.split(":", 1)[0].split(" ", 1)[0].strip()
    if head in FAILURE_CLASSES:
        return head
    return _LEGACY_CLASS.get(head, "CONFIGURATION_FAILED")


def port_owner_pid(port: int):
    """Return the pid currently LISTENING on the loopback port, or None. G17 pre-check."""
    import subprocess
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                         capture_output=True, text=True).stdout
    suffix = ":{}".format(port)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[1].endswith(suffix):
            return parts[4]
    return None

PORT_OCCUPIED_UNRECOGNIZED = "PORT_OCCUPIED_UNRECOGNIZED"


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_env(adapter: dict, overrides: dict | None = None) -> dict:
    """Compose the child environment: allowlist from the parent, then env_set, then overrides."""
    launch = adapter.get("launch", {})
    env = {}
    for key in launch.get("env_allowlist", []):
        val = os.environ.get(key, "")
        if val:
            env[key] = val
    for key, val in launch.get("env_set", {}).items():
        env[key] = val
    for key, val in (overrides or {}).items():
        env[key] = val
    return env


def check_quota_guard(module_id: str, env: dict) -> dict:
    """H-10 layer 2: assert the compiled env still carries the guard immediately before spawn.

    Returns the quota_guard record. Raises QuotaGuardError if the assertion fails, which must
    happen BEFORE CreateProcessW is reached.
    """
    if module_id != "sow":
        return {}
    value = env.get("SOW_CONDUCTOR_AUTOLAUNCH")
    if value != "0":
        raise QuotaGuardError(
            f"SOW_CONDUCTOR_AUTOLAUNCH is {value!r}, expected '0'")
    return {"required": True, "autolaunch_value": "0", "verified_before_spawn": True}


class QuotaGuardError(Exception):
    pass


class ModuleRunner:
    """One module's live state and the transitions between them."""

    def __init__(self, module_id: str, adapter: dict, supervisor, log_ring=None):
        self.id = module_id
        self.adapter = adapter
        self.supervisor = supervisor
        self.log_ring = log_ring
        self.reason = ""
        self.last_check = _now_iso()
        self.quota_guard = None
        self.last_start = 0.0
        if "error" in adapter:
            self.state = CONFIG_ERROR
            self.reason = adapter.get("reason", "Unknown")
        elif adapter.get("state_class") == "not_started":
            self.state = NOT_STARTED
        else:
            self.state = STOPPED

    # -- presentation -------------------------------------------------------
    @property
    def display(self) -> str:
        if self.state in (FAILED, CONFIG_ERROR) and self.reason:
            return f"{self.state}({self.reason})"
        return self.state

    def _set(self, state: str, reason: str = ""):
        self.state = state
        self.reason = reason
        self.last_check = _now_iso()

    # -- probes -------------------------------------------------------------
    def _readiness(self, cfg: dict, ph, since: float):
        """Return (ready: bool, latency: float, error: str)."""
        kind = cfg.get("kind")
        if kind == "http":
            return probe_mod.http_probe(
                cfg["url"], cfg.get("expect_status", 200), cfg["timeout_s"], cfg["poll_ms"])
        if kind == "receipt_file":
            return probe_mod.receipt_file_probe(
                cfg.get("path", ""), cfg["timeout_s"], cfg["poll_ms"],
                require=cfg.get("require") or {"ok": True}, newer_than=since)
        if kind == "process_window":
            t0 = time.time()
            deadline = t0 + cfg["timeout_s"]
            # "ready" means the process is still alive after the poll interval, not merely
            # that it was created.
            time.sleep(min(cfg["poll_ms"] / 1000.0, cfg["timeout_s"]))
            while time.time() < deadline:
                if ph is not None and ph.is_alive():
                    return True, time.time() - t0, ""
                if ph is not None and not ph.is_alive():
                    return False, time.time() - t0, "Process exited"
                time.sleep(cfg["poll_ms"] / 1000.0)
            return False, time.time() - t0, "process_window timeout"
        return False, 0.0, f"Unknown readiness kind: {kind}"

    def _identity(self, cfg: dict, ph):
        """Return (ok: bool, error: str)."""
        kind = cfg.get("kind")
        if kind == "http_json":
            return probe_mod.http_json_identity(cfg.get("url", ""), cfg.get("required_keys", []))
        if kind == "http_html_marker":
            return probe_mod.http_html_identity(cfg.get("url", ""), cfg.get("html_marker", ""))
        if kind == "process_image":
            # H-5 / ADR-004: canonical-path EQUALITY against the compiled argv[0].
            # Never a prefix comparison.
            if ph is None:
                return False, "no managed process"
            actual = query_process_image(ph.pid)
            if not actual:
                return False, "process image unavailable"
            expected = cfg.get("expected_image") or self.adapter["launch"]["argv"][0]
            if _canonical(actual) == _canonical(expected):
                return True, ""
            return False, f"image {actual} != {expected}"
        return False, f"Unknown identity kind: {kind}"

    # -- transitions --------------------------------------------------------
    def start(self, env_overrides: dict | None = None, readiness_override: dict | None = None):
        """STOPPED -> STARTING -> READY | FAILED(EXIT|TIMEOUT|IDENTITY|JOB_ASSIGN|QUOTA_GUARD)."""
        if self.state not in (STOPPED, FAILED):
            raise ValueError(f"Cannot start from state {self.display}")

        self.last_start = time.time()
        self._set(STARTING)

        launch = self.adapter["launch"]
        env = build_env(self.adapter, env_overrides)

        # H-10 layer 2 — before CreateProcessW, not after.
        try:
            self.quota_guard = check_quota_guard(self.id, env) or None
        except QuotaGuardError as e:
            self._set(FAILED, "CONFIGURATION_FAILED: quota guard")
            return self.display, str(e)

        # G17: port-conflict pre-check - its own class, naming the owning pid, before
        # any spawn attempt. Never a TIMEOUT.
        rd0 = self.adapter.get("readiness") or {}
        if rd0.get("kind") == "http":
            import re as _re
            m = _re.search(r":(\d+)", str(rd0.get("url", "")))
            if m:
                owner = port_owner_pid(int(m.group(1)))
                if owner:
                    self._set(FAILED,
                              "PORT_UNAVAILABLE (owned by pid %s)" % owner)
                    return self.display, "port %s already owned by pid %s" % (
                        m.group(1), owner)

        since = time.time()
        try:
            ph = self.supervisor.spawn(self.id, launch["argv"], launch["cwd"], env,
                                       log_ring=self.log_ring)
        except SupervisorError as e:
            reason = ("PROCESS_START_FAILED: JOB_ASSIGN failed"
                      if "JOB_ASSIGN" in str(e)
                      else "PROCESS_START_FAILED: spawn failed")
            self._set(FAILED, reason)
            return self.display, str(e)

        cfg = readiness_override or self.adapter["readiness"]
        ready, _lat, err = self._readiness(cfg, ph, since)
        if not ready:
            alive = ph.is_alive()
            self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 5))
            self._set(FAILED,
                      ("HEALTH_CHECK_FAILED: readiness probe not satisfied"
                       if alive else "PROCESS_START_FAILED: exited before ready"))
            return self.display, err

        ok, ierr = self._identity(self.adapter["identity"], ph)
        if not ok:
            self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 5))
            self._set(FAILED, "IDENTITY_MISMATCH: " + ierr)
            return self.display, ierr

        self._set(READY)
        return self.display, ""

    def stop(self):
        """READY | DEGRADED | STARTING | EXTERNAL -> STOPPED."""
        if self.state == EXTERNAL:
            # H-9: an externally started process is never touched. Only our view of it resets.
            self._set(STOPPED)
            return self.display
        if self.state in (STOPPED, NOT_STARTED, CONFIG_ERROR):
            return self.display
        self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 10))
        self._set(STOPPED)
        return self.display

    def cancel(self):
        """STARTING -> STOPPED (operator cancels)."""
        if self.state != STARTING:
            return self.display
        self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 5))
        self._set(STOPPED)
        return self.display

    def poll(self):
        """Periodic re-probe. Implements the READY/DEGRADED/EXTERNAL rows of §7.4."""
        if self.state in (NOT_STARTED, CONFIG_ERROR):
            return self.display
        ph = self.supervisor.get_process(self.id)

        if self.state in (READY, DEGRADED):
            if ph is None or not ph.is_alive():
                self._set(FAILED, "EXIT")
                return self.display
            alive_ok = self._periodic_readiness_ok(ph)
            if self.state == READY and not alive_ok:
                self._set(DEGRADED, "readiness lost")
            elif self.state == DEGRADED and alive_ok:
                self._set(READY)
            else:
                self.last_check = _now_iso()
            return self.display

        # No managed process: EXTERNAL / PORT_OCCUPIED_UNRECOGNIZED / STOPPED.
        if ph is None:
            return self._probe_external()
        return self.display

    def _periodic_readiness_ok(self, ph) -> bool:
        cfg = self.adapter.get("readiness", {})
        kind = cfg.get("kind")
        if kind == "http":
            ready, _, _ = probe_mod.http_probe(cfg["url"], cfg.get("expect_status", 200), 5, 1000)
            return ready
        if kind == "process_window":
            return ph.is_alive()
        if kind == "receipt_file":
            return ph.is_alive()
        return False

    def _probe_external(self):
        """(any, no managed process) -> EXTERNAL | FAILED(PORT_OCCUPIED_UNRECOGNIZED) | STOPPED."""
        cfg = self.adapter.get("readiness", {})
        if cfg.get("kind") != "http":
            # Only endpoint-bearing modules can be occupied by an external instance.
            if self.state == EXTERNAL:
                self._set(STOPPED)
            return self.display

        occupied, _, _ = probe_mod.http_probe(cfg["url"], cfg.get("expect_status", 200), 5, 500)
        if not occupied:
            if self.state in (EXTERNAL, FAILED):
                self._set(STOPPED)
            else:
                self.last_check = _now_iso()
            return self.display

        ok, _ = self._identity(self.adapter["identity"], None)
        if ok:
            self._set(EXTERNAL)
        else:
            self._set(FAILED, PORT_OCCUPIED_UNRECOGNIZED)
        return self.display

    def can_start(self) -> tuple:
        """(allowed, http_status, message) — Start is refused in EXTERNAL and while occupied."""
        if self.adapter.get("state_class") == "not_started":
            return False, 400, "Module has no runtime"
        if not self.runtime_present:
            return False, 400, f"Runtime not installed: {self.runtime_path}"
        if "error" in self.adapter:
            return False, 400, f"Adapter error: {self.adapter.get('reason')}"
        if self.state == EXTERNAL:
            return False, 409, "Refused: an external instance owns this endpoint"
        if self.state == FAILED and self.reason == PORT_OCCUPIED_UNRECOGNIZED:
            return False, 409, "Refused: endpoint occupied by an unrecognized process"
        if self.state not in (STOPPED, FAILED):
            return False, 400, f"Cannot start from state {self.display}"
        return True, 200, ""

    @property
    def runtime_path(self) -> str:
        """argv[0] of the launch command - the executable this module needs on disk.

        N-22/OBS-2: an optional runtime that ships in no archive (llama.cpp, R2 s3) has a real
        adapter and no binary. The operator has to be able to see WHICH path is missing, so the
        path is reported rather than merely the fact of absence.
        """
        argv = (self.adapter.get("launch") or {}).get("argv") or []
        return argv[0] if argv else ""

    @property
    def runtime_present(self) -> bool:
        """True when the launch executable exists. Unknown (no argv) counts as present, so a
        module without a launch block is never mislabelled as uninstalled."""
        path = self.runtime_path
        return True if not path else os.path.exists(path)

    def open_kind(self) -> str:
        """What this module's Open control would actually DO: browser | focus_window | none."""
        return (self.adapter.get("open") or {}).get("kind", "none")

    def can_open(self) -> bool:
        """Open is enabled in READY and EXTERNAL (§7.3 item 2) AND only where the module declares
        an open action the shell can perform.

        N-23: this used to test state alone, so `sow.json` - which declared `open.kind: none` -
        reported can_open true the moment it reached READY, and the operator got an enabled button
        wired to an empty URL. A rendered control must be a performable action (S-17), so
        enablement now follows capability as well as readiness.
        """
        if self.open_kind() == "none":
            return False
        if self.open_kind() == "browser" and not (self.adapter.get("open") or {}).get("url"):
            return False
        return self.state in (READY, EXTERNAL)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.adapter.get("display_name", self.id),
            "description": self.adapter.get("description", ""),
            "state_class": self.adapter.get("state_class", "runnable"),
            "state": self.state,
            "reason": self.reason,
            "display": self.display,
            "last_check": self.last_check,
            "port": "",
            "url": self.adapter.get("open", {}).get("url", ""),
            "can_open": self.can_open(),
            "open_kind": self.open_kind(),
            "runtime_present": self.runtime_present,
            "runtime_path": self.runtime_path,
        }
