"""
SWS secret-bearing output sanitization — §7.6.1 (H-8), normative.

Redaction runs BEFORE process output enters the log ring, any API response, any startup-test
record, or any evidence file — never only at presentation time. The replacement value is the
literal [REDACTED].

Covered, case-insensitively:
  * api_key / api-key / apikey assignments, '=' or ':' separated
  * token, secret, password, passwd, and bare key assignments, '=' or ':' separated
  * Authorization header values
  * Bearer credential values, with or without an Authorization prefix
  * credential-bearing URL query parameters: api_key, api-key, apikey, token, key, secret,
    password, passwd, access_token
"""
import re

REDACTED = "[REDACTED]"

# Value terminators: whitespace and the usual structural punctuation. A value runs to the first
# of these, so a redaction never swallows the rest of a log line.
_VALUE = r'[^\s,;)\]}"\']+'

# Order matters: Authorization and Bearer are matched before the generic assignment forms so a
# header line is redacted whole rather than piecemeal.
_PATTERNS = [
    # Authorization: <anything to end of line>
    (re.compile(r'(?P<prefix>authorization)(?P<sep>\s*[=:]\s*)(?P<value>[^\r\n]+)',
                re.IGNORECASE), "line"),
    # Bearer <credential>
    (re.compile(r'(?P<prefix>bearer)(?P<sep>\s+)(?P<value>' + _VALUE + r')',
                re.IGNORECASE), "token"),
    # URL query parameters — checked before generic assignments so '?token=x' keeps its
    # separator character.
    (re.compile(r'(?P<lead>[?&])(?P<prefix>api[_-]?key|access[_-]?token|token|key|secret|'
                r'passw(?:or)?d)(?P<sep>=)(?P<value>[^&\s]+)', re.IGNORECASE), "query"),
    # Generic assignments: name = value or name: value
    (re.compile(r'(?P<prefix>api[_-]?key|access[_-]?token|token|secret|passw(?:or)?d|key)'
                r'(?P<sep>\s*[=:]\s*)(?P<value>' + _VALUE + r')', re.IGNORECASE), "assign"),
]


def _sub(kind):
    def repl(m):
        # Idempotence: a value already redacted by an earlier pattern is left alone. Without
        # this, '?api_key=[REDACTED]' is matched again by the generic assignment pattern, whose
        # value terminator stops at the ']', and becomes '[REDACTED]]'.
        if m.group("value").lstrip().startswith("[REDACTED"):
            return m.group(0)
        if kind == "line":
            return "{}{}{}".format(m.group("prefix"), m.group("sep"), REDACTED)
        if kind == "token":
            return "{}{}{}".format(m.group("prefix"), m.group("sep"), REDACTED)
        if kind == "query":
            return "{}{}{}{}".format(
                m.group("lead"), m.group("prefix"), m.group("sep"), REDACTED)
        return "{}{}{}".format(m.group("prefix"), m.group("sep"), REDACTED)
    return repl


def redact(text: str) -> str:
    """Replace every secret-bearing value with the literal [REDACTED]."""
    if not text:
        return text
    for pattern, kind in _PATTERNS:
        text = pattern.sub(_sub(kind), text)
    return text
