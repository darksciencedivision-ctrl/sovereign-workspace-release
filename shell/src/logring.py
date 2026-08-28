"""
SWS Log Ring Buffer — thread-safe, bounded, ANSI-stripped, redacted.
"""
import re
import threading

# ANSI escape sequences: CSI and OSC
_ANSI_CSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
_ANSI_OSC = re.compile(r'\x1b\][^\x07]*\x07')
# C0/C1 controls to strip (keep \t, \n, \r)
_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')


def _strip_controls(text: str) -> str:
    text = _ANSI_CSI.sub('', text)
    text = _ANSI_OSC.sub('', text)
    text = _CONTROLS.sub('', text)
    text = text.replace('\x00', '')
    return text


class LogRing:
    """Thread-safe ring buffer for process output lines."""

    def __init__(self, max_lines: int = 2000, max_line_len: int = 4096, max_read: int = 65536):
        self._max_lines = max_lines
        self._max_line_len = max_line_len
        self._max_read = max_read
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def write(self, data: bytes, runtime=None, model_id=None, artifact_id=None,
              request_id=None, load_state=None, fallback_reason=None):
        """Decode and buffer process output, applying redaction.
        Extra fields (runtime, model_id, artifact_id, request_id, load_state,
        fallback_reason) ride the same redaction path; never a parallel log."""
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            return
        text = _strip_controls(text)
        from shell.src.redact import redact
        extra = []
        if runtime: extra.append("runtime=" + str(runtime))
        if model_id: extra.append("model_id=" + str(model_id))
        if artifact_id: extra.append("artifact_id=" + str(artifact_id))
        if request_id: extra.append("request_id=" + str(request_id))
        if load_state: extra.append("load_state=" + str(load_state))
        if fallback_reason: extra.append("fallback_reason=" + str(fallback_reason))
        if extra:
            text = "[" + " ".join(extra) + "]\n" + text
        text = redact(text)
        for line in text.split('\n'):
            if len(line) > self._max_line_len:
                line = line[:self._max_line_len] + '...'
            with self._lock:
                self._lines.append(line)
                if len(self._lines) > self._max_lines:
                    self._lines = self._lines[-self._max_lines:]

    def read(self) -> str:
        """Return recent log lines as a string."""
        with self._lock:
            result = '\n'.join(self._lines)
        if len(result) > self._max_read:
            result = result[-self._max_read:]
        return result

    def read_lines(self) -> list[str]:
        """Return recent log lines as a list (for startup-test records)."""
        with self._lock:
            return list(self._lines[-200:])

    def clear(self):
        with self._lock:
            self._lines.clear()