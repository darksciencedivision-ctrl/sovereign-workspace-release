"""
SWS secret-bearing output sanitization - §7.6.1 (H-8), normative.

Redaction runs BEFORE process output enters the log ring, any API response, any startup-test
record, or any evidence file - never only at presentation time. The replacement value is the
literal [REDACTED].

Covered, case-insensitively:
  * api_key / api-key / apikey / access_token / client_secret / secret / password / passwd / token
    and a STANDALONE `key`, assigned with '=' or ':', whether the value (and/or the key) is
    quoted or bare - so `API_KEY=x`, `API_KEY="x"`, `password = 'x'`, `OPENAI_API_KEY: "x"`, and
    the JSON form `{"api_key": "x"}` are all redacted (R13/F-010);
  * Authorization header values and Bearer credentials;
  * credential-bearing URL query parameters;
  * BARE provider credentials by shape - `sk-`, `sk-ant-`, `sk-proj-`, `ghp_`/`gho_`,
    `github_pat_`, `glpat-`, `xox[baprs]-`, `AKIA…`, `AIza…`, `hf_`, `gsk_`, and JWTs - so a token
    that appears with no `key=` introducer is still removed (R13/F-010).

Not over-redacted: a bare `key` only matches as a standalone token, so `monkey`, `hotkey` and
`primary_key` are left alone (R13/F-010).
"""
import re

REDACTED = "[REDACTED]"

# Unquoted value: runs to the first whitespace or structural terminator, so a redaction never
# swallows the rest of a log line. Deliberately excludes quotes (a quoted value is handled below).
_UNQUOTED = r'[^\s,;)\]}"\']+'

# The key name that introduces a secret assignment. The strong names (api_key, secret, password,
# token, …) match even as the SUFFIX of a larger identifier, because OPENAI_API_KEY, DB_PASSWORD and
# ANTHROPIC_AUTH_TOKEN are all real; a bare `key` is anchored with a left non-word lookbehind so
# `monkey`/`primary_key`/`hotkey` are NOT matched (the value's `[=:]` separator already blocks most
# suffix false-positives, but `monkey:` needs the anchor).
_KEYNAME = (r'(?:api[_-]?key|access[_-]?token|client[_-]?secret|auth[_-]?token|secret|'
            r'passw(?:or)?d|token|(?<![A-Za-z0-9_])key)')

# The key, with an optional matching pair of surrounding quotes (JSON keys: `"api_key"`), then the
# separator. `kq` is back-referenced so an opening quote is balanced by the same closing quote.
_KEY = (r'(?P<kq>["\']?)(?P<prefix>' + _KEYNAME + r')(?P=kq)'
        r'(?P<sep>\s*[=:]\s*)')

# Bare provider/token shapes, redacted whole wherever they appear (no `key=` introducer needed).
_SHAPES = re.compile(
    r'(?<![A-Za-z0-9_-])('
    r'sk-ant-[A-Za-z0-9_-]{8,}'
    r'|sk-proj-[A-Za-z0-9_-]{8,}'
    r'|sk-[A-Za-z0-9]{20,}'
    r'|gh[pousr]_[A-Za-z0-9]{20,}'
    r'|github_pat_[A-Za-z0-9_]{20,}'
    r'|glpat-[A-Za-z0-9_-]{16,}'
    r'|xox[baprs]-[A-Za-z0-9-]{10,}'
    r'|AKIA[0-9A-Z]{16}'
    r'|AIza[0-9A-Za-z_\-]{30,}'
    r'|hf_[A-Za-z0-9]{20,}'
    r'|gsk_[A-Za-z0-9]{20,}'
    r'|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}'
    r')')

_PATTERNS = [
    # Authorization: <to end of line> - matched before Bearer so a header line is redacted whole.
    (re.compile(r'(?P<prefix>authorization)(?P<sep>\s*[=:]\s*)(?P<value>[^\r\n]+)',
                re.IGNORECASE), "line"),
    # Bearer <credential>
    (re.compile(r'(?P<prefix>bearer)(?P<sep>\s+)(?P<value>' + _UNQUOTED + r')',
                re.IGNORECASE), "token"),
    # URL query parameters - before the generic assignment so '?token=x' keeps its separator.
    (re.compile(r'(?P<lead>[?&])(?P<prefix>api[_-]?key|access[_-]?token|token|key|secret|'
                r'passw(?:or)?d)(?P<sep>=)(?P<value>[^&\s]+)', re.IGNORECASE), "query"),
    # Assignment with a QUOTED value: name [=:] "value" | 'value' (key may itself be quoted).
    (re.compile(_KEY + r'(?P<vq>["\'])(?P<value>(?:\\.|(?!\4).)*)(?P=vq)', re.IGNORECASE), "qassign"),
    # Assignment with a BARE value.
    (re.compile(_KEY + r'(?P<value>' + _UNQUOTED + r')', re.IGNORECASE), "assign"),
]


def _already_redacted(value: str) -> bool:
    return value.lstrip().startswith("[REDACTED")


def _sub(kind):
    def repl(m):
        if _already_redacted(m.group("value")):
            return m.group(0)
        if kind == "line" or kind == "token":
            return "{}{}{}".format(m.group("prefix"), m.group("sep"), REDACTED)
        if kind == "query":
            return "{}{}{}{}".format(
                m.group("lead"), m.group("prefix"), m.group("sep"), REDACTED)
        if kind == "qassign":
            # Preserve the key's quotes and the value's quotes, blanking only the value, so a JSON
            # document stays shaped like one: {"api_key": "[REDACTED]"}.
            kq, vq = m.group("kq"), m.group("vq")
            return "{}{}{}{}{}{}{}".format(
                kq, m.group("prefix"), kq, m.group("sep"), vq, REDACTED, vq)
        # bare assignment
        return "{}{}{}{}{}".format(
            m.group("kq"), m.group("prefix"), m.group("kq"), m.group("sep"), REDACTED)
    return repl


def redact(text: str) -> str:
    """Replace every secret-bearing value with the literal [REDACTED]."""
    if not text:
        return text
    for pattern, kind in _PATTERNS:
        text = pattern.sub(_sub(kind), text)
    # Bare token shapes last: a token already blanked as a value above is now [REDACTED] and will
    # not match; a truly bare token in prose is caught here.
    text = _SHAPES.sub(REDACTED, text)
    return text
