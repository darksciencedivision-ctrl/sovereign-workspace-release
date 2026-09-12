"""
SWS Log Ring Buffer - thread-safe, bounded, ANSI-stripped, redacted.

R14 (F-012): the supervisor drains the child's pipe in arbitrary byte chunks, so a line - and a
secret in it - can straddle two reads. Redacting each chunk independently let `API_KE` | `Y=sk-…`
through, and splitting a UTF-8 sequence produced U+FFFD garbage. `write` now feeds an incremental
UTF-8 decoder and holds any partial trailing line in a carry buffer, so control-stripping and
redaction run over COMPLETE lines only. The unredacted carry is never exposed by `read()`; a
partial final line surfaces only once a newline arrives or `flush()` is called at end of stream.
"""
import codecs
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

    def __init__(self, max_lines: int = 2000, max_line_len: int = 4096, max_read: int = 65536,
                 sink=None):
        """`sink` is an optional object with `write_line(str)`.

        EPC-01 P4-6. Persistence is attached HERE rather than at the supervisor's pipe, and
        the placement is the security property: by the time a line reaches the sink it has
        already been through `redact()` and the control-character strip. A second path to
        disk that tapped the raw pipe would turn an in-memory safeguard into a file full of
        whatever the module printed.
        """
        self._max_lines = max_lines
        self._max_line_len = max_line_len
        self._max_read = max_read
        self._lines: list[str] = []
        self._sink = sink
        self._lock = threading.Lock()
        # R14: streaming decode + partial-line carry, for the byte-chunk pipe path.
        self._decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self._carry = ""

    def _emit_line(self, line: str) -> None:
        """Strip controls, redact, bound, and append ONE complete line."""
        line = _strip_controls(line)
        from shell.src.redact import redact
        line = redact(line)
        if len(line) > self._max_line_len:
            line = line[:self._max_line_len] + '...'
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._max_lines:
                self._lines = self._lines[-self._max_lines:]
        # Outside the lock: the sink does file I/O, and holding the ring's lock across it
        # would let a slow disk stall the reader that serves /api/logs.
        if self._sink is not None:
            self._sink.write_line(line)

    def write(self, data, runtime=None, model_id=None, artifact_id=None,
              request_id=None, load_state=None, fallback_reason=None):
        """Buffer process output, applying redaction to complete lines.

        Two shapes, one redaction path:
          * an ANNOTATED write (any of the extra fields set) is a self-contained record - the
            annotation and its content are emitted whole, immediately, so a caller that writes
            without a trailing newline still sees it; it does not touch the streaming carry.
          * a plain byte-chunk write (the supervisor pipe pump) is STREAMED: decoded incrementally
            and split into complete lines, with any partial trailing line held in the carry for the
            next chunk (R14). Never redacts a half-line.
        """
        extra = []
        if runtime: extra.append("runtime=" + str(runtime))
        if model_id: extra.append("model_id=" + str(model_id))
        if artifact_id: extra.append("artifact_id=" + str(artifact_id))
        if request_id: extra.append("request_id=" + str(request_id))
        if load_state: extra.append("load_state=" + str(load_state))
        if fallback_reason: extra.append("fallback_reason=" + str(fallback_reason))

        if extra:
            # Record semantics: decode whole (no shared decoder state), emit the annotation and
            # every content line now. A trailing empty segment (text ended in '\n') is dropped so
            # the record does not add a blank line.
            if isinstance(data, (bytes, bytearray)):
                text = bytes(data).decode('utf-8', errors='replace')
            else:
                text = str(data or "")
            self._emit_line("[" + " ".join(extra) + "]")
            segments = text.split('\n')
            if segments and segments[-1] == "":
                segments.pop()
            for line in segments:
                self._emit_line(line)
            return

        # Stream semantics.
        if isinstance(data, (bytes, bytearray)):
            text = self._decoder.decode(bytes(data))
        else:
            text = str(data or "")
        buffer = self._carry + text
        parts = buffer.split('\n')
        self._carry = parts.pop()   # the trailing partial line, if any, waits for more input
        for line in parts:
            self._emit_line(line)

    def flush(self) -> None:
        """End of stream: decode any bytes held by the incremental decoder and emit the final
        partial line. Called by the supervisor pump when the child's pipe reaches EOF, so a last
        line with no trailing newline is not silently dropped (and is still redacted first)."""
        try:
            tail = self._decoder.decode(b"", final=True)
        except Exception:
            tail = ""
        buffer = self._carry + tail
        self._carry = ""
        if buffer:
            self._emit_line(buffer)

    def read(self) -> str:
        """Return recent log lines as a string. The unredacted carry is deliberately NOT included."""
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
            self._carry = ""
