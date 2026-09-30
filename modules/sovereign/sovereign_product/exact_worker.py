"""The exact-counting engine: a validated extraction spec applied to text (stdlib only, D6).

A spec is DATA, not code: a regular expression with named groups that matches one record, a type
for each group, and aggregates from a closed list. ``parse_spec`` validates it against the
allow-list; ``execute`` applies it to text with integer arithmetic and returns every aggregate
exactly, ties included, with the evidence a reader needs to trust the number.

This file is also run as a script (``exact_worker.py <job.json>``) so the product can apply a spec
to a large input in a child process it can kill: a pattern that runs away costs a timeout, never a
stuck worker. It imports nothing from the product.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

try:  # Python 3.11+ moved the parser; the old name is a deprecated alias
    import re._parser as _sre_parse
    import re._constants as _sre_const
except ImportError:  # pragma: no cover
    import sre_parse as _sre_parse  # type: ignore[no-redef]
    import sre_constants as _sre_const  # type: ignore[no-redef]

MAX_PATTERN_CHARS = 2000
MAX_FIELDS = 12
MAX_AGGREGATES = 8
MAX_BOUNDED_REPEAT = 1000
#: Nested repeats multiply their bounds; above this product the backtracking is not bounded in practice.
MAX_NESTED_REPEAT_PRODUCT = 2000
MIN_ANCHOR_CHARS = 3
#: A record must fit this window from its first character; bounds the work of every attempt.
RECORD_WINDOW_CHARS = 4096
MAX_DISTINCT_GROUPS = 10_000
TOP_GROUPS = 10
EXAMPLES = 5
OPS = ("count", "count_where", "sum", "max", "min", "group_count")
COMPARISONS = ("==", "!=", "<", "<=", ">", ">=")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
_SIMPLE = {_sre_const.LITERAL, _sre_const.NOT_LITERAL, _sre_const.ANY, _sre_const.IN,
           _sre_const.CATEGORY}
_ALLOWED_KEYS = {"applicable", "reason", "pattern", "flags", "fields", "aggregates"}


class SpecError(ValueError):
    """The spec is not acceptable; the message says what to change."""


class ExecutionError(RuntimeError):
    """The spec cannot be applied to this input (too many groups, out of time)."""


@dataclass(frozen=True)
class Aggregate:
    op: str
    field: str | None = None
    cmp: str | None = None
    value: Any = None


@dataclass(frozen=True)
class Spec:
    pattern: str
    flags: str
    fields: dict[str, str]
    aggregates: tuple[Aggregate, ...]
    anchor: str

    def as_dict(self) -> dict[str, Any]:
        return {"applicable": True, "pattern": self.pattern, "flags": self.flags,
                "fields": dict(self.fields),
                "aggregates": [{k: v for k, v in (("op", a.op), ("field", a.field),
                                                  ("cmp", a.cmp), ("value", a.value))
                                if v is not None} for a in self.aggregates]}


def _re_flags(flags: str) -> int:
    return (re.IGNORECASE if "i" in flags else 0) | (re.MULTILINE if "m" in flags else 0)


def _walk(items: Any, in_repeat: bool, weight: int = 1) -> None:
    for op, av in items:
        if op in _SIMPLE or op is _sre_const.AT:
            continue
        if op is _sre_const.SUBPATTERN:
            _walk(av[3], in_repeat, weight)
        elif op is _sre_const.BRANCH:
            if in_repeat:
                raise SpecError("the pattern has an alternation (a|b) inside a repeat; "
                                "restructure it so repeats apply to single characters")
            for alternative in av[1]:
                _walk(alternative, in_repeat, weight)
        elif op in (_sre_const.MAX_REPEAT, _sre_const.MIN_REPEAT):
            minimum, maximum, body = av
            unbounded = maximum == _sre_const.MAXREPEAT
            if not unbounded and maximum > MAX_BOUNDED_REPEAT:
                raise SpecError(f"a repeat allows more than {MAX_BOUNDED_REPEAT} repetitions")
            if unbounded and not (len(body) == 1 and body[0][0] in _SIMPLE):
                raise SpecError("an unbounded repeat (* or +) must apply to a single character "
                                "or character class, e.g. \\d+ or [^,]*; use {m,n} for groups")
            if in_repeat and unbounded:
                raise SpecError("the pattern nests an unbounded repeat inside another repeat")
            inner = weight * (1 if unbounded else max(1, maximum))
            if in_repeat and inner > MAX_NESTED_REPEAT_PRODUCT:
                raise SpecError("repeats nested inside repeats allow too many combinations "
                                f"(bounds multiply to more than {MAX_NESTED_REPEAT_PRODUCT}); "
                                "use smaller {m,n} bounds")
            _walk(body, True, inner)
        else:
            raise SpecError("the pattern uses a regex feature that is not allowed (back-"
                            "references, look-around and atomic groups are refused)")


def _anchor(parsed: Any) -> str:
    chars: list[str] = []
    for op, av in parsed:
        if op is _sre_const.AT and not chars:
            continue
        if op is _sre_const.LITERAL:
            chars.append(chr(av))
        else:
            break
    return "".join(chars)


def parse_spec(value: Any) -> Spec:
    """Validate ``value`` (a decoded JSON object) into a Spec, or raise SpecError."""
    if not isinstance(value, Mapping):
        raise SpecError("the spec must be one JSON object")
    unknown = sorted(set(value) - _ALLOWED_KEYS)
    if unknown:
        raise SpecError(f"unknown spec keys: {', '.join(map(str, unknown))}")
    if value.get("applicable") is not True:
        raise SpecError('"applicable" must be true for a spec that extracts records')
    pattern = value.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise SpecError('"pattern" must be a non-empty regular expression string')
    if len(pattern) > MAX_PATTERN_CHARS:
        raise SpecError(f'"pattern" is longer than {MAX_PATTERN_CHARS} characters')
    flags = value.get("flags", "")
    if not isinstance(flags, str) or set(flags) - {"i", "m"} or len(set(flags)) != len(flags):
        raise SpecError('"flags" may only contain i and m, each once')
    try:
        compiled = re.compile(pattern, _re_flags(flags))
        parsed = _sre_parse.parse(pattern, _re_flags(flags))
    except (re.error, RecursionError, OverflowError) as exc:
        raise SpecError(f'"pattern" is not a valid regular expression: {exc}') from exc
    _walk(parsed, False)
    anchor = _anchor(parsed)
    if len(anchor) < MIN_ANCHOR_CHARS:
        raise SpecError(f"the pattern must start with at least {MIN_ANCHOR_CHARS} literal "
                        "characters that begin every record (e.g. 'Operations note ')")
    raw_fields = value.get("fields")
    if not isinstance(raw_fields, Mapping) or not raw_fields or len(raw_fields) > MAX_FIELDS:
        raise SpecError(f'"fields" must map 1 to {MAX_FIELDS} group names to "int" or "str"')
    fields: dict[str, str] = {}
    for name, kind in raw_fields.items():
        if not isinstance(name, str) or not _NAME.match(name):
            raise SpecError(f"field name {name!r} is not a simple identifier")
        if kind not in ("int", "str"):
            raise SpecError(f'field {name!r} must be typed "int" or "str"')
        fields[name] = kind
    if set(compiled.groupindex) != set(fields):
        raise SpecError("the named groups in the pattern must be exactly the fields: "
                        f"groups {sorted(compiled.groupindex)}, fields {sorted(fields)}")
    raw_aggregates = value.get("aggregates")
    if (not isinstance(raw_aggregates, list) or not raw_aggregates
            or len(raw_aggregates) > MAX_AGGREGATES):
        raise SpecError(f'"aggregates" must list 1 to {MAX_AGGREGATES} operations')
    aggregates = tuple(_parse_aggregate(item, fields) for item in raw_aggregates)
    return Spec(pattern=pattern, flags=flags, fields=fields, aggregates=aggregates,
                anchor=anchor)


def _parse_aggregate(item: Any, fields: Mapping[str, str]) -> Aggregate:
    if not isinstance(item, Mapping):
        raise SpecError("each aggregate must be a JSON object")
    op = item.get("op")
    if op not in OPS:
        raise SpecError(f"aggregate op {op!r} is not one of {', '.join(OPS)}")
    allowed = {"op"} | ({"field"} if op != "count" else set()) \
        | ({"cmp", "value"} if op == "count_where" else set())
    extra = sorted(set(item) - allowed)
    if extra:
        raise SpecError(f"aggregate {op} does not take: {', '.join(map(str, extra))}")
    if op == "count":
        return Aggregate("count")
    field = item.get("field")
    if field not in fields:
        raise SpecError(f"aggregate {op} names field {field!r}, which is not declared")
    if op in ("sum", "max", "min") and fields[field] != "int":
        raise SpecError(f"aggregate {op} needs an int field; {field!r} is {fields[field]}")
    if op != "count_where":
        return Aggregate(op, field)
    cmp = item.get("cmp")
    if cmp not in COMPARISONS:
        raise SpecError(f"count_where cmp must be one of {', '.join(COMPARISONS)}")
    value = item.get("value")
    if fields[field] == "int":
        if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 10 ** 18:
            raise SpecError(f"count_where on int field {field!r} needs an integer value")
    else:
        if not isinstance(value, str):
            raise SpecError(f"count_where on str field {field!r} needs a string value")
        if cmp not in ("==", "!="):
            raise SpecError("a str field can only be compared with == or !=")
    return Aggregate(op, field, cmp, value)


_COMPARE: dict[str, Callable[[Any, Any], bool]] = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b, "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def execute(text: str, spec: Spec, *, deadline: float | None = None,
            monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Apply ``spec`` to ``text``; every aggregate exactly, with the evidence."""
    flags = _re_flags(spec.flags)
    compiled = re.compile(spec.pattern, flags)
    anchor = re.compile(re.escape(spec.anchor), flags & re.IGNORECASE)
    total = len(text)
    states: list[dict[str, Any]] = []
    for aggregate in spec.aggregates:
        states.append({"n": 0, "best": None, "examples": [], "groups": {}})
    attempts = matched = parsed_rows = 0
    first = last = None
    unmatched: list[int] = []
    examples: list[dict[str, Any]] = []
    position = 0
    while True:
        found = anchor.search(text, position)
        if found is None:
            break
        start = found.start()
        attempts += 1
        if deadline is not None and attempts % 1024 == 0 and monotonic() > deadline:
            raise ExecutionError("the time limit for counting was reached")
        record = compiled.match(text, start, min(total, start + RECORD_WINDOW_CHARS))
        if record is None:
            if len(unmatched) < EXAMPLES:
                unmatched.append(start)
            position = start + 1
            continue
        position = max(record.end(), start + 1)
        matched += 1
        if first is None:
            first = start
        last = start
        row = _row(record, spec.fields)
        if row is None:
            continue
        parsed_rows += 1
        if len(examples) < EXAMPLES:
            examples.append({**row, "offset": start})
        for aggregate, state in zip(spec.aggregates, states):
            _accumulate(aggregate, state, row, start)
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    return {
        "matched": matched, "parsed": parsed_rows, "unparsed": matched - parsed_rows,
        "anchor": spec.anchor, "anchor_attempts": attempts,
        "unmatched_anchor_mentions": attempts - matched, "unmatched_offsets": unmatched,
        "first_offset": first, "last_offset": last, "input_chars": total,
        "input_sha256": digest, "examples": examples,
        "aggregates": [_summary(a, s) for a, s in zip(spec.aggregates, states)],
    }


def _row(record: "re.Match[str]", fields: Mapping[str, str]) -> dict[str, Any] | None:
    row: dict[str, Any] = {}
    for name, kind in fields.items():
        raw = record.group(name)
        if raw is None:
            return None
        if kind == "int":
            try:
                row[name] = int(raw.strip())
            except ValueError:
                return None
        else:
            row[name] = raw.strip()
    return row


def _accumulate(aggregate: Aggregate, state: dict[str, Any], row: Mapping[str, Any],
                offset: int) -> None:
    op = aggregate.op
    if op == "count":
        state["n"] += 1
    elif op == "count_where":
        if _COMPARE[aggregate.cmp](row[aggregate.field], aggregate.value):
            state["n"] += 1
    elif op == "sum":
        state["n"] += row[aggregate.field]
    elif op in ("max", "min"):
        value = row[aggregate.field]
        best = state["best"]
        better = best is None or (value > best if op == "max" else value < best)
        if better:
            state["best"], state["n"], state["examples"] = value, 1, [{**row, "offset": offset}]
        elif value == best:
            state["n"] += 1
            if len(state["examples"]) < EXAMPLES:
                state["examples"].append({**row, "offset": offset})
    else:  # group_count
        groups = state["groups"]
        key = row[aggregate.field]
        if key not in groups and len(groups) >= MAX_DISTINCT_GROUPS:
            raise ExecutionError(f"more than {MAX_DISTINCT_GROUPS} distinct values of "
                                 f"{aggregate.field!r}; group on a field with fewer values")
        groups[key] = groups.get(key, 0) + 1


def _summary(aggregate: Aggregate, state: Mapping[str, Any]) -> dict[str, Any]:
    op = aggregate.op
    out: dict[str, Any] = {"op": op}
    if aggregate.field is not None:
        out["field"] = aggregate.field
    if op == "count":
        out["result"] = state["n"]
    elif op == "count_where":
        out.update(cmp=aggregate.cmp, value=aggregate.value, result=state["n"])
    elif op == "sum":
        out["result"] = state["n"]
    elif op in ("max", "min"):
        out.update(result=state["best"], attained_by=state["n"], examples=state["examples"])
    else:
        ordered = sorted(state["groups"].items(), key=lambda kv: (-kv[1], str(kv[0])))
        out.update(distinct=len(ordered),
                   top=[{"value": k, "count": v} for k, v in ordered[:TOP_GROUPS]])
    return out


def _main(argv: list[str]) -> int:
    """``exact_worker.py <job.json>``: {"input_path", "spec", "seconds"} -> one JSON line."""
    try:
        with open(argv[1], encoding="utf-8") as handle:
            job = json.load(handle)
        with open(job["input_path"], encoding="utf-8", newline="") as handle:
            text = handle.read()
        spec = parse_spec(job["spec"])
        deadline = time.monotonic() + float(job.get("seconds", 300))
        result = execute(text, spec, deadline=deadline)
    except (SpecError, ExecutionError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 3
    print(json.dumps({"result": result}))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
