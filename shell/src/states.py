"""
SWS module state machine — BUILD-DIRECTIVE §7.4, implemented exactly.

The transition logic lives here rather than inline in server.py so that every transition in §7.4
can be exercised by a test against a fixture process (R3-5). This is a refactor of logic that
already existed in server.py; it adds no feature, endpoint, or dependency.

States: NOT_STARTED, STOPPED, STARTING, READY, DEGRADED, FAILED(reason), EXTERNAL,
CONFIG_ERROR(reason).
"""
import os
import threading
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
    """Return the pid currently LISTENING on the loopback port, or None. G17 pre-check.

    F-022: this used to grep `netstat -ano` for the literal "LISTENING", which is LOCALIZED
    ("ABHOEREN" on German Windows, etc.), so the port-conflict pre-check silently never fired on a
    non-English host. It now queries GetExtendedTcpTable (iphlpapi) directly - the TCP state is the
    numeric MIB_TCP_STATE_LISTEN, independent of the console language.
    """
    import ctypes
    import socket
    from ctypes import wintypes

    AF_INET = 2
    TCP_TABLE_OWNER_PID_LISTENER = 3
    MIB_TCP_STATE_LISTEN = 2

    class MIB_TCPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwState", wintypes.DWORD),
            ("dwLocalAddr", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwRemoteAddr", wintypes.DWORD),
            ("dwRemotePort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    try:
        get_table = ctypes.windll.iphlpapi.GetExtendedTcpTable
    except (AttributeError, OSError):
        return None
    get_table.restype = wintypes.DWORD

    size = wintypes.DWORD(0)
    # First call sizes the buffer (returns ERROR_INSUFFICIENT_BUFFER = 122).
    get_table(None, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_LISTENER, 0)
    if size.value == 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    rc = get_table(buf, ctypes.byref(size), False, AF_INET, TCP_TABLE_OWNER_PID_LISTENER, 0)
    if rc != 0:  # NO_ERROR == 0; anything else is unobservable, which is not "free"
        return None

    num = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    rows_addr = ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD)
    rows = (MIB_TCPROW_OWNER_PID * num).from_address(rows_addr)
    for row in rows:
        if row.dwState != MIB_TCP_STATE_LISTEN:
            continue
        # dwLocalPort holds the port in network byte order in its low 16 bits.
        row_port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        if row_port == port:
            return str(row.dwOwningPid)
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
        # SWS-CORRECTIVE-01 workstream 1.3. Every start/stop/cancel/restart is an OPERATION
        # with an identity. `_op_lock` guards state transitions and admission only - it is
        # never held across a probe, a spawn or a process stop, so a 90-second SOW readiness
        # wait cannot block the shell. `_current_op` names the operation that owns this module
        # right now; anything else that finishes later is superseded and may publish nothing.
        self._op_lock = threading.RLock()
        self._op_seq = 0
        self._current_op = None
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
        with self._op_lock:
            self.state = state
            self.reason = reason
            self.last_check = _now_iso()

    # -- operation identity -------------------------------------------------
    def _begin_operation(self) -> int:
        """Claim this module for a new operation and return its id. Caller holds no lock."""
        with self._op_lock:
            self._op_seq += 1
            self._current_op = self._op_seq
            return self._op_seq

    def _supersede(self):
        """Invalidate whatever operation currently owns the module.

        A cancel or a stop is itself an operation: it takes ownership so that the start it
        interrupted can no longer publish anything, and so that a second cancel is a no-op
        rather than a second supersession.
        """
        with self._op_lock:
            self._op_seq += 1
            self._current_op = None

    def _is_current(self, op: int) -> bool:
        with self._op_lock:
            return self._current_op == op

    def _checkpoint(self, op: int, where: str) -> bool:
        """Cancellation checkpoint. True while `op` still owns the module.

        The named checkpoints are the boundaries of the slow steps - `pre_spawn`, `post_spawn`,
        `post_readiness`, `post_identity` - and they are a method rather than an inline
        comparison so a test can block at one and drive the exact interleaving it names.
        """
        return self._is_current(op)

    def _publish(self, op: int, state: str, reason: str = "") -> bool:
        """Set state ONLY if `op` still owns the module. Returns whether it was published.

        This is the whole of L3. `start()` used to end in an unconditional `_set(READY)`, so a
        start that the operator had already cancelled published READY over the cancellation the
        moment its readiness probe returned.
        """
        with self._op_lock:
            if self._current_op != op:
                return False
            self.state = state
            self.reason = reason
            self.last_check = _now_iso()
            return True

    def _observe_set(self, gen: int, ph0, state: str, reason: str = "") -> bool:
        """Publish a POLL observation only if nothing changed since it began (R02).

        A poll is an observer, never an operation, so `_probe_external` must not overwrite a start
        that took ownership while its (multi-second) HTTP/identity probe was in flight. `gen` is the
        operation counter captured before the probe and `ph0` the managed process observed then;
        either advancing means an operation ran in the meantime, and the observation is dropped.
        The process handle is read outside `_op_lock` to preserve the module→supervisor lock order.
        """
        current_ph = self.supervisor.get_process(self.id)
        with self._op_lock:
            if self._op_seq != gen or current_ph is not ph0:
                return False
            self.state = state
            self.reason = reason
            self.last_check = _now_iso()
            return True

    def begin_start(self) -> int:
        """Claim an operation and enter STARTING atomically — the SYNCHRONOUS half of a start.

        R01: the server used to admit a start (rate limit + `can_start`) and then queue an async
        worker that only reached `runner.start()` later. Between the two the module was still
        STOPPED/FAILED, so a Stop in that gap saw a stoppable-from state, took its no-op branch, and
        did NOT supersede — and the queued worker then spawned a process after the operator had been
        told the module was stopped. Claiming the operation and the STARTING transition here, under
        the same `_op_lock` the caller holds across `can_start`, closes that window: a Stop now sees
        STARTING and supersedes, and the worker's `start(op=...)` finds it is no longer current and
        spawns nothing.
        """
        with self._op_lock:
            if self.state not in (STOPPED, FAILED):
                raise ValueError(f"Cannot start from state {self.display}")
            op = self._begin_operation()
            self.state = STARTING
            self.reason = ""
            self.last_check = _now_iso()
            return op

    def _stop_owned(self, ph, grace_s: int):
        """Stop the process THIS operation spawned - never whatever now answers to the id.

        The supervisor keys processes by module id, which is reused across operations. A
        superseded start that called `supervisor.stop(self.id)` would terminate the process a
        later start owns; the identity check is what prevents that.
        """
        if ph is None:
            return
        current = self.supervisor.get_process(self.id)
        if current is not ph:
            return
        self.supervisor.stop(self.id, grace_s)

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
            return probe_mod.http_json_identity(
                cfg.get("url", ""), cfg.get("required_keys", []), require=cfg.get("require"))
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
    def start(self, env_overrides: dict | None = None, readiness_override: dict | None = None,
              op: int | None = None):
        """STOPPED -> STARTING -> READY | FAILED(EXIT|TIMEOUT|IDENTITY|JOB_ASSIGN|QUOTA_GUARD).

        Admission and the STARTING transition happen together under `_op_lock`, so two
        simultaneous requests cannot both pass the state check and both spawn. Everything slow
        - the spawn, the readiness probe, the identity probe - runs outside the lock, and every
        result is published through `_publish`, which drops it if the operation has since been
        cancelled or superseded.

        `op` is the operation id when admission already happened synchronously in the caller
        (`begin_start`, the R01 server path); the module is then already STARTING and this only
        proceeds while that operation still owns it. `op=None` keeps the self-contained path used
        by the startup test and the deterministic suite: admit here, atomically.
        """
        if op is None:
            with self._op_lock:
                if self.state not in (STOPPED, FAILED):
                    raise ValueError(f"Cannot start from state {self.display}")
                op = self._begin_operation()
                self.last_start = time.monotonic()
                self.state = STARTING
                self.reason = ""
                self.last_check = _now_iso()
        elif not self._is_current(op):
            # Admitted by the caller, then superseded (a Stop/Cancel in the admission→worker gap):
            # own nothing, spawn nothing.
            return self.display, "start superseded before spawn"

        # EPC-01 P4-4. Create this module's declared write targets before spawning it.
        #
        # While runtime state lived inside the install root those directories already existed,
        # because the installer had laid the tree down. Now that state lives under
        # %LOCALAPPDATA% they do not exist on a first run, and a module that assumes its own
        # directory would fail in a way that reads like a permissions problem.
        #
        # Only paths the adapter DECLARED are created, and compile_adapter has already refused
        # any declaration that escapes both the install root and this module's state root — so
        # this cannot create a directory somewhere a module never said it would write. A
        # failure here is reported as a configuration failure rather than swallowed: a module
        # that cannot have its state directory must not be started and then blamed for it.
        try:
            for target in self.adapter.get("runtime_writes", []):
                # F-023: compiled entries are {path, kind}. When kind is declared use it; otherwise
                # fall back to the extension heuristic (kept for legacy string declarations).
                if isinstance(target, dict):
                    path = target.get("path", "")
                    kind = target.get("kind")
                else:
                    path = target
                    kind = None
                if kind == "dir":
                    directory = path
                elif kind == "file":
                    directory = os.path.dirname(path)
                else:
                    directory = path if not os.path.splitext(path)[1] else os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            self._publish(op, FAILED, "CONFIGURATION_FAILED: state directory")
            return self.display, f"cannot create declared write target: {exc}"

        launch = self.adapter["launch"]
        env = build_env(self.adapter, env_overrides)

        # H-10 layer 2 — before CreateProcessW, not after.
        try:
            self.quota_guard = check_quota_guard(self.id, env) or None
        except QuotaGuardError as e:
            self._publish(op, FAILED, "CONFIGURATION_FAILED: quota guard")
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
                    self._publish(op, FAILED,
                                  "PORT_UNAVAILABLE (owned by pid %s)" % owner)
                    return self.display, "port %s already owned by pid %s" % (
                        m.group(1), owner)

        # Cancellation is checked immediately before CreateProcessW. A cancel that lands in the
        # window between admission and spawn must stop the start, not race it.
        if not self._checkpoint(op, "pre_spawn"):
            return self.display, "start superseded before spawn"

        since = time.time()
        try:
            ph = self.supervisor.spawn(self.id, launch["argv"], launch["cwd"], env,
                                       log_ring=self.log_ring)
        except SupervisorError as e:
            # EPC-02 dyno. The supervisor's message carries the ACTUAL cause - the Windows
            # error code from CreateProcess, a missing executable, a pipe failure. Collapsing
            # every one of them into "spawn failed" left the operator, and this builder, with
            # a FAILED badge and nothing to act on. The detail was already being returned to
            # the caller and thrown away by the async start path, so it never reached anyone.
            detail = str(e).strip()
            reason = ("PROCESS_START_FAILED: JOB_ASSIGN failed"
                      if "JOB_ASSIGN" in detail
                      else "PROCESS_START_FAILED: spawn failed")
            if detail and "JOB_ASSIGN" not in detail:
                reason = f"{reason} ({detail[:200]})"
            self._publish(op, FAILED, reason)
            return self.display, detail

        grace = self.adapter.get("stop", {}).get("grace_s", 5)

        # The spawn succeeded. If the operation was cancelled while CreateProcessW was in
        # flight, the process this operation owns is stopped here - and only that one.
        if not self._checkpoint(op, "post_spawn"):
            self._stop_owned(ph, grace)
            return self.display, "start superseded during spawn"

        cfg = readiness_override or self.adapter["readiness"]
        ready, _lat, err = self._readiness(cfg, ph, since)

        # The readiness probe is the long wait, and the window the recorded L3 reproduction
        # lands in. Nothing measured across it may be published if the operation is no longer
        # the current one.
        if not self._checkpoint(op, "post_readiness"):
            self._stop_owned(ph, grace)
            return self.display, "start superseded during readiness"

        if not ready:
            alive = ph.is_alive()
            self._stop_owned(ph, grace)
            self._publish(op, FAILED,
                          ("HEALTH_CHECK_FAILED: readiness probe not satisfied"
                           if alive else "PROCESS_START_FAILED: exited before ready"))
            return self.display, err

        ok, ierr = self._identity(self.adapter["identity"], ph)
        if not self._checkpoint(op, "post_identity"):
            self._stop_owned(ph, grace)
            return self.display, "start superseded during identity check"
        if not ok:
            self._stop_owned(ph, grace)
            self._publish(op, FAILED, "IDENTITY_MISMATCH: " + ierr)
            return self.display, ierr

        if not self._publish(op, READY):
            # Superseded between the identity check and here.
            self._stop_owned(ph, grace)
            return self.display, "start superseded before publication"
        return self.display, ""

    def stop(self):
        """READY | DEGRADED | STARTING | EXTERNAL -> STOPPED.

        Stop is the last accepted operation: it supersedes any outstanding start FIRST, so a
        start still inside its readiness probe can publish nothing afterwards, and so a stop
        issued during startup is terminal rather than a no-op the start then undoes.
        """
        with self._op_lock:
            if self.state in (STOPPED, NOT_STARTED, CONFIG_ERROR):
                return self.display
            was_external = self.state == EXTERNAL
            self._supersede()
        if was_external:
            # H-9: an externally started process is never touched. Only our view of it resets.
            self._set(STOPPED)
            return self.display
        self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 10))
        self._set(STOPPED)
        return self.display

    def cancel(self):
        """STARTING -> STOPPED (operator cancels).

        Supersession happens before the process is stopped, so the outstanding start observes
        that it no longer owns the module at its next checkpoint and publishes nothing.
        """
        with self._op_lock:
            if self.state != STARTING:
                return self.display
            self._supersede()
        self.supervisor.stop(self.id, self.adapter.get("stop", {}).get("grace_s", 5))
        self._set(STOPPED)
        return self.display

    def poll(self):
        """Periodic re-probe. Implements the READY/DEGRADED/EXTERNAL rows of §7.4.

        Polling is an observer, never an operation. It must not overwrite a transition that is
        still in flight, and it must not erase a diagnostic failure merely because the port has
        since been released - the operator needs to read WHY the last start failed.
        """
        # F-013 (+ R02). Snapshot the operation generation and the state under the lock, then treat
        # the whole poll as ONE observation. Every transition it publishes goes through
        # `_observe_set`, which drops the write if a start/stop/restart took ownership (or replaced
        # the process) since the snapshot -- so a FAILED("EXIT") can never land on a fresh STARTING,
        # and poll can never overwrite an in-flight transition it merely raced.
        with self._op_lock:
            gen = self._op_seq
            state0 = self.state
        if state0 in (NOT_STARTED, CONFIG_ERROR, STARTING):
            # STARTING belongs to an operation that is still running. A poll that touched it
            # would race the start's own publication.
            return self.display
        ph = self.supervisor.get_process(self.id)

        if state0 in (READY, DEGRADED):
            if ph is None or not ph.is_alive():
                self._observe_set(gen, ph, FAILED, "EXIT")
                return self.display
            alive_ok = self._periodic_readiness_ok(ph)
            if state0 == READY and not alive_ok:
                self._observe_set(gen, ph, DEGRADED, "readiness lost")
            elif state0 == DEGRADED and alive_ok:
                self._observe_set(gen, ph, READY)
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
        """(any, no managed process) -> EXTERNAL | FAILED(PORT_OCCUPIED_UNRECOGNIZED) | STOPPED.

        R02: the HTTP and identity probes below take seconds, and a Start can take ownership (or a
        Stop from EXTERNAL can supersede) while they are in flight. This is a poll, not an
        operation, so every transition here is published through `_observe_set` guarded by the
        operation counter and managed process captured BEFORE the probes — an observation that
        raced an operation is dropped rather than overwriting the state that operation established.
        """
        with self._op_lock:
            gen = self._op_seq
        ph0 = self.supervisor.get_process(self.id)   # None on this path; re-checked before publish

        cfg = self.adapter.get("readiness", {})
        if cfg.get("kind") != "http":
            # Only endpoint-bearing modules can be occupied by an external instance.
            if self.state == EXTERNAL:
                self._observe_set(gen, ph0, STOPPED)
            return self.display

        occupied, _, _ = probe_mod.http_probe(cfg["url"], cfg.get("expect_status", 200), 5, 500)
        if not occupied:
            # EXTERNAL and PORT_OCCUPIED_UNRECOGNIZED are observations ABOUT THE PORT: once it
            # is free they are simply no longer true, so they clear. Every other FAILED reason
            # is the diagnosis of this shell's own last start attempt - HEALTH_CHECK_FAILED,
            # IDENTITY_MISMATCH, PROCESS_START_FAILED - and a free port says nothing about it.
            # Clearing those was how a useful cause disappeared five seconds after it appeared.
            # They survive until an explicit new operation replaces them.
            if self.state == EXTERNAL or (
                    self.state == FAILED and self.reason == PORT_OCCUPIED_UNRECOGNIZED):
                self._observe_set(gen, ph0, STOPPED)
            else:
                self.last_check = _now_iso()
            return self.display

        ok, _ = self._identity(self.adapter["identity"], None)
        if ok:
            self._observe_set(gen, ph0, EXTERNAL)
        else:
            self._observe_set(gen, ph0, FAILED, PORT_OCCUPIED_UNRECOGNIZED)
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
            "maturity": self.adapter.get("maturity", "unspecified"),
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
