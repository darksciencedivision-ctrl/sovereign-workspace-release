"""Exact counting for LONG map/reduce (D6): the computer counts, not the model.

For an objective that counts, totals or ranks records in a large input, the route is:
spec (a model session emits a declarative extraction spec from a sample) -> validation (the
product runs the spec on the sample, the model confirms or corrects it) -> execution (the
product applies the spec to the WHOLE input in a child process with a hard time limit, exact
integer arithmetic, ties included) -> answer (the model writes prose from the computed table
only; the product rejects prose with a number that is not in the table, and appends the table
verbatim). Anything that does not hold falls back to map/reduce with a note. See
docs/design/EXACT-COUNTING.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .exact_worker import SpecError, parse_spec

STATE_FILE = "exact.json"
WORKER = Path(__file__).with_name("exact_worker.py")
SAMPLE_CHARS = 9000
SAMPLE_ROWS_SHOWN = 8
CORRECTIONS = 2
ANSWER_TRIES = 3
SPEC_TRIES = 2
EXECUTION_SECONDS = 300.0
SAMPLE_SECONDS = 20.0

# Words that ask for a number outright: worth a spec attempt whatever else the objective says.
_COUNT_WORDS = re.compile(
    r"\b(count|counts|counted|counting|how many|number of|sum of|tally|how often|total number)\b",
    re.IGNORECASE)
# Words that rank or total ("the most warnings", "the total of"): they also turn up in prose
# requests ("summarize the most important risks"), where the spec call (a thinking model, minutes)
# would only end in "not applicable".
_RANK_WORDS = re.compile(
    r"\b(total|totals|most|least|fewest|maximum|minimum|max|min|largest|smallest|highest|lowest)\b",
    re.IGNORECASE)
_TEXT_REQUEST = re.compile(
    r"\b(list|summari[sz]e|summary|describe|explain|compare|outline|discuss|review|analy[sz]e|"
    r"draft|write|design|plan)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d[\d,]*")


def is_countable_objective(objective: str) -> bool:
    """A cheap word check: worth TRYING the exact route (the spec step still decides)."""
    if _COUNT_WORDS.search(objective):
        return True
    return bool(_RANK_WORDS.search(objective)) and not _TEXT_REQUEST.search(objective)


def objective_fit_issues(objective: str, spec: Mapping[str, Any]) -> list[str]:
    """Conservative lexical proof for requested quantities, independent of model agreement.

    Unknown field wording is refused rather than guessed. Semantic coverage still needs
    a separate model check; passing these necessary checks is not a semantic proof.
    """
    def words(text: str) -> list[str]:
        return [word.rstrip('s') for word in re.findall(r'[a-z]+', text.lower())]

    fields = {name: words(name.replace('_', ' ')) for name in spec.get('fields', {})}
    aggregates = spec.get('aggregates', [])
    issues: list[str] = []

    def field_at(text: str) -> str | None:
        tokens = words(text)
        while tokens and tokens[0] in ('the', 'of', 'number'):
            tokens.pop(0)
        for name, parts in fields.items():
            if parts and tokens[:len(parts)] == parts:
                return name
        return None

    rank_count = 0
    for match in _RANK_WORDS.finditer(objective):
        word = match.group().lower()
        op = ('sum' if word in ('total', 'totals') else
              'min' if word in ('least', 'fewest', 'minimum', 'min', 'smallest', 'lowest')
              else 'max')
        field = field_at(objective[match.end():])
        if not field or not any(a.get('op') == op and a.get('field') == field for a in aggregates):
            issues.append(f'{match.group()} {objective[match.end():].strip()}: no matching {op} field')
        else:
            rank_count += 1
    for match in re.finditer(r'\b(?:sum of)\s+(.+?)(?:[?;.]|$)', objective, re.I):
        field = field_at(match.group(1))
        if not field or not any(a.get('op') == 'sum' and a.get('field') == field for a in aggregates):
            issues.append(f'{match.group()}: no matching sum field')
    for match in re.finditer(r'\bwhich\s+(\w+)', objective, re.I):
        if not field_at(match.group(1)) or not rank_count:
            issues.append(f'{match.group()}: no captured ranked entity')
    for match in re.finditer(r'\bits\s+(\w+)\s+count\b', objective, re.I):
        if not field_at(match.group(1)) or not rank_count:
            issues.append(f'{match.group()}: no captured value for ranked record')
    count_requests = list(re.finditer(
        r'\b(?:how many|number of|count of|count the|count all)\s+(.+?)(?=\band\b|[?;.]|$)',
        objective, re.I))
    for match in count_requests:
        clause = match.group(1)
        numbers = [int(n) for n in re.findall(r'\b\d+\b', clause)]
        if numbers:
            for number in numbers:
                if not any(a.get('op') == 'count_where' and a.get('value') == number
                           and a.get('cmp') == '==' and
                           all(w in words(clause) for w in fields.get(a.get('field'), ['?']))
                           for a in aggregates):
                    issues.append(f'{match.group()}: no matching filtered count for {number}')
        elif not any(a.get('op') in ('count', 'count_where', 'group_count') for a in aggregates):
            issues.append(f'{match.group()}: no count aggregate')
        entity = words(clause)[:1]
        known = words(str(spec.get('pattern', ''))) + [w for ws in fields.values() for w in ws]
        if entity and entity[0] not in known and entity[0] not in ('record', 'row', 'line'):
            issues.append(f'{match.group()}: counted entity not captured or identified by pattern')
    if not count_requests and not rank_count and not re.search(r'\bsum of\b', objective, re.I):
        issues.append('no supported quantity could be mapped to the spec')
    return issues


class ExactCancelled(Exception):
    """The job was cancelled while the engine ran."""


class ExactEngineError(RuntimeError):
    """The engine could not apply the spec (bad spec, out of time, crashed)."""


@dataclass
class ExactOutcome:
    """``answer`` is None when the run must fall back to map/reduce (``note`` says why)."""

    answer: str | None
    note: str | None = None
    telemetry: dict[str, Any] = field(default_factory=dict)


# --- the engine, run in a child process ------------------------------------------------------------

def run_engine(spec: Mapping[str, Any], text: str, *, work_dir: Path, seconds: float,
               cancel_requested: Callable[[], bool] = lambda: False,
               command: list[str] | None = None, grace: float = 5.0,
               monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Apply ``spec`` to ``text`` in a child process that is killed at the time limit or on cancel."""
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "exact-input.tmp"
    job_path = work_dir / "exact-job.tmp"
    input_path.write_bytes(text.encode("utf-8", "surrogatepass"))
    job_path.write_bytes(json.dumps({"input_path": str(input_path), "spec": dict(spec),
                                     "seconds": seconds}).encode("utf-8"))
    argv = (command or [sys.executable, "-I", str(WORKER)]) + [str(job_path)]
    started = monotonic()
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while True:
                try:
                    out, err = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel_requested():
                    raise ExactCancelled("cancelled while counting")
                if monotonic() - started > seconds + grace:
                    raise ExactEngineError(f"counting did not finish within {seconds:.0f} s")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    finally:
        for path in (input_path, job_path):
            try:
                path.unlink()
            except OSError:
                pass
    try:
        reply = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ExactEngineError("the counting engine returned no result "
                               f"(exit {process.returncode}): {err.decode('utf-8', 'replace')[:200]}")
    if "result" not in reply:
        raise ExactEngineError(str(reply.get("error") or "the counting engine failed"))
    return reply["result"]


# --- prompts ---------------------------------------------------------------------------------------

SYSTEM = ("You produce DATA, not code. Reply with exactly one JSON object and nothing else: no "
          "prose, no code fence.")
#: The answer step is prose; the data system prompt above made the model reply with a JSON blob.
PROSE_SYSTEM = ("You answer in short, plain sentences for a person, using only the numbers you "
                "are given. Do not reply with JSON, a table or a code fence.")

SPEC_FORMAT = """\
The object is either {"applicable": false, "reason": "..."} or a spec:
{"applicable": true,
 "pattern": "<Python regular expression matching ONE record>",
 "flags": "" (or "i" and/or "m"),
 "fields": {"<group name>": "int" | "str", ...},
 "aggregates": [ ... ]}
Rules for the pattern: it must START with at least 3 literal characters that begin every record
(for example "Operations note "), then match the record through the last value you need. When
every line of the input is one record and lines start with a value that varies (a table, a CSV, a
log), start the pattern with ^ and set "flags": "m" ONLY when each record is its own line.
If several records share a line, do not start the pattern with ^: a ^ pattern matches only at
the start of a line, so it skips every later record on that line. Then each line is one record
and the pattern must match a whole line (no \\n in it). Capture
each value you need in a named group (?P<name>...); the named groups must be exactly the fields.
Use single-character repeats like \\d+ or [^,]*; do not use back-references, look-around, or a
repeat over a group with alternation inside. A record is at most 4000 characters.
Aggregates (use only what the objective needs):
  {"op": "count"}                                  the number of records
  {"op": "count_where", "field": F, "cmp": "==", "value": V}   cmp is ==, !=, <, <=, >, >=
  {"op": "sum", "field": F}     {"op": "max", "field": F}     {"op": "min", "field": F}
  {"op": "group_count", "field": F}                records per distinct value of F
"the most X" or "the highest X" is max of X; "how many records report V" is count_where field == V.
The product reports ties for max and min itself, and each max/min example row includes every
captured field. "The step with the most warnings and its record count" is max of warnings with
step and records captured. Do not reply applicable:false for that. Take literal values (V) from
the objective only.
Use {"applicable": false} when the objective asks for a list, summary, explanation, comparison or
anything that is not counting, summing or ranking records the pattern can find."""


def _missed_most_starts(result: Mapping[str, Any]) -> str | None:
    """A spec that misses more record starts than it matches is not an exact count.

    A line-record file may have a header line that does not match; that is one miss against
    many hits. A ^ anchor on records that share a line matches the first record only.
    """
    missed = int(result.get("unmatched_anchor_mentions") or 0)
    matched = int(result.get("matched") or 0)
    if missed > matched:
        return (f"the pattern matched {matched} records but {missed} places start like a record "
                "and did not match; if several records share a line, do not start the pattern with ^")
    return None


def make_sample(text: str, budget: int = SAMPLE_CHARS) -> str:
    """The head, evenly spaced windows and the tail of ``text``, within ~``budget`` characters."""
    if len(text) <= budget:
        return text
    head, window, tail = int(budget * 0.34), int(budget * 0.16), int(budget * 0.18)
    parts = [text[:head]]
    positions = [len(text) * i // 4 for i in (1, 2, 3)]
    for position in positions:
        parts.append(f"\n[... {position - len(''.join(parts))} characters omitted ...]\n")
        parts.append(text[position:position + window])
    parts.append(f"\n[... omitted ...]\n{text[-tail:]}")
    return "".join(parts)


def _spec_prompt(objective: str, sample: str, total_chars: int) -> str:
    return (f"Objective:\n{objective}\n\nThe input is {total_chars} characters. This is a sample "
            f"of it (the head, windows from the middle, the tail):\n<<<SAMPLE\n{sample}\nSAMPLE>>>"
            f"\n\nWrite the extraction spec that lets the computer answer the objective by "
            f"counting over the whole input.\n{SPEC_FORMAT}")


def _validation_prompt(objective: str, spec: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    rows = json.dumps(result["examples"][:SAMPLE_ROWS_SHOWN])
    shown = {"records_matched_in_sample": result["matched"],
             "first_parsed_rows": json.loads(rows),
             "aggregates_over_the_sample": result["aggregates"],
             "sample_mentions_of_the_record_start": result["anchor_attempts"]}
    return (f"Objective:\n{objective}\n\nYour spec:\n{json.dumps(dict(spec))}\n\nThe product ran "
            f"it over the sample:\n{json.dumps(shown)}\n\nDoes this extract the records and "
            'compute what the objective asks? If yes reply {"ok": true}. If not, reply the '
            "corrected complete spec (same format), or {\"applicable\": false, \"reason\": "
            f"\"...\"}} when counting cannot answer it.\n{SPEC_FORMAT}")


def _answer_prompt(objective: str, table: Mapping[str, Any], retry_note: str = "") -> str:
    return (f"Objective:\n{objective}\n\nExact results computed by the product over every "
            f"record of the input (not estimates):\n{json.dumps(table)}\n\nAnswer the objective "
            "in plain sentences using ONLY these results. Quote every number exactly as given. "
            "Report ties (how many records reach the maximum or minimum). Do not write any "
            f"number that is not in the results.{retry_note}")


def extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


# --- rendering -------------------------------------------------------------------------------------

def render_table(results: Mapping[str, Any]) -> str:
    """The computed numbers, verbatim, as lines the operator can read."""
    lines = [f"Computed by the product over {results['matched']} records "
             "(exact; the model did not count):"]
    for item in results["aggregates"]:
        op, name = item["op"], item.get("field")
        if op == "count":
            lines.append(f"- records: {item['result']}")
        elif op == "count_where":
            lines.append(f"- records where {name} {item['cmp']} {item['value']}: {item['result']}")
        elif op == "sum":
            lines.append(f"- sum of {name}: {item['result']}")
        elif op in ("max", "min"):
            word = "maximum" if op == "max" else "minimum"
            lines.append(f"- {word} {name}: {item['result']}, reached by {item['attained_by']} "
                         f"record(s)")
            for row in item["examples"][:3]:
                shown = ", ".join(f"{k} {v}" for k, v in row.items() if k != "offset")
                lines.append(f"    e.g. {shown}")
        else:
            top = ", ".join(f"{g['value']}: {g['count']}" for g in item["top"])
            lines.append(f"- records per {name} ({item['distinct']} distinct values; top "
                         f"{len(item['top'])}): {top}")
    if results.get("unmatched_anchor_mentions"):
        if results.get("anchor") == "start of a line":
            lines.append(f"- NOTE: {results['unmatched_anchor_mentions']} non-blank line(s) did "
                         "not match the pattern and are not counted (a header line is expected "
                         "to be one).")
        else:
            lines.append(f"- NOTE: {results['unmatched_anchor_mentions']} place(s) start like a "
                         f"record ('{results['anchor']}') but did not match the pattern and are "
                         "not counted.")
    if results.get("unparsed"):
        lines.append(f"- NOTE: {results['unparsed']} matched record(s) had a value that could "
                     "not be read and are not in the aggregates.")
    return "\n".join(lines)


def _numbers(value: Any, into: set[int]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        into.add(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            _numbers(item, into)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _numbers(item, into)
    elif isinstance(value, str):
        into.update(int(m.replace(",", "")) for m in _NUMBER.findall(value)
                    if m.replace(",", "").isdigit())


def prose_numbers_ok(prose: str, table: Mapping[str, Any], objective: str) -> bool:
    """True when every number in ``prose`` is in the computed table or the objective (or <= 10)."""
    allowed = set(range(0, 11))
    _numbers(table, allowed)
    _numbers(objective, allowed)
    for token in _NUMBER.findall(prose):
        digits = token.replace(",", "")
        if digits.isdigit() and int(digits) not in allowed:
            return False
    return True


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(json.dumps(state, indent=1).encode("utf-8"))
    os.replace(tmp, path)


# --- the route -------------------------------------------------------------------------------------

class ExactCounter:
    """Runs the exact route for one LONG job; resumes from ``exact.json``."""

    def __init__(self, port: Any, run_dir: Path, *, max_output_tokens: int,
                 cancel_requested: Callable[[], bool] = lambda: False,
                 progress: Callable[[str, str, int], None] = lambda stage, detail, pct: None,
                 engine: Callable[..., dict[str, Any]] = run_engine,
                 monotonic: Callable[[], float] = time.monotonic):
        self.port, self.run_dir = port, Path(run_dir)
        self.max_output_tokens = max_output_tokens
        self.cancel_requested, self.progress = cancel_requested, progress
        self.engine, self.monotonic = engine, monotonic
        self.state_path = self.run_dir / STATE_FILE
        self.calls = 0

    # -- state -----------------------------------------------------------------------------------
    def load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return state if isinstance(state, dict) else {}

    def _save(self, state: Mapping[str, Any]) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        _write_state(self.state_path, state)

    def _ask(self, prompt: str, system: str = SYSTEM) -> str:
        self.calls += 1
        try:
            return self.port.generate(system=system, prompt=prompt,
                                      max_tokens=self.max_output_tokens,
                                      should_stop=self.cancel_requested)
        except Exception as exc:
            if type(exc).__name__ == "ReplyTruncated":  # no usable reply: the callers retry
                return ""
            raise

    def _fallback(self, state: dict[str, Any], reason: str) -> ExactOutcome:
        state.update(status="fallback", reason=reason)
        self._save(state)
        return ExactOutcome(None, reason, {"status": "fallback", "reason": reason,
                                           "model_calls": self.calls})

    # -- the route -------------------------------------------------------------------------------
    def run(self, objective: str, material: str | None) -> ExactOutcome:
        started = self.monotonic()
        state = self.load_state()
        if state.get('spec'):
            issues = objective_fit_issues(objective, state['spec'])
            if issues:
                return self._fallback(state, 'not covered by the computed table: ' + '; '.join(issues))
        if state.get("status") == "fallback":
            return ExactOutcome(None, str(state.get("reason")),
                                {"status": "fallback", "reason": state.get("reason")})
        if state.get("status") == "answered" and state.get("answer"):
            return ExactOutcome(str(state["answer"]), None, self._telemetry(state, started))
        if "results" not in state:
            if material is None:
                return self._fallback(state, "the input is not available to count")
            spec = self._spec(objective, material, state)
            if isinstance(spec, ExactOutcome):
                return spec
            self.progress("exact_counting", "counting the whole input", 30)
            try:
                results = self.engine(spec, material, work_dir=self.run_dir,
                                      seconds=EXECUTION_SECONDS,
                                      cancel_requested=self.cancel_requested)
            except ExactEngineError as exc:
                return self._fallback(state, f"counting failed: {exc}")
            if results["matched"] == 0:
                return self._fallback(state, "the pattern matched no record in the whole input")
            missed = _missed_most_starts(results)
            if missed:
                return self._fallback(state, missed)
            state.update(spec=spec, results=results)
            self._save(state)
        results = state["results"]
        table = {"records_matched": results["matched"], "aggregates": results["aggregates"],
                 "record_start_mentions_not_matched": results["unmatched_anchor_mentions"]}
        self.progress("exact_counting", "writing the answer from the computed table", 85)
        prose = self._prose(objective, table)
        answer = (prose + "\n\n" if prose else "") + render_table(results)
        state.update(status="answered", answer=answer, prose_from_model=bool(prose))
        self._save(state)
        return ExactOutcome(answer, None, self._telemetry(state, started))

    def _spec(self, objective: str, material: str, state: dict[str, Any]) -> Any:
        """The validated spec (a dict), or an ExactOutcome that ends the exact route."""
        sample = make_sample(material)
        prompt = _spec_prompt(objective, sample, len(material))
        raw = None
        for attempt in range(SPEC_TRIES):
            self.progress("exact_counting", "writing the extraction spec", 8)
            raw = extract_json_object(self._ask(prompt))
            if raw is None:
                prompt += "\n\nYour last reply was not one JSON object. Reply with the JSON only."
                continue
            break
        if raw is None:
            return self._fallback(state, "the model did not return a spec")
        for correction in range(CORRECTIONS + 1):
            if raw.get("applicable") is False:
                reason = str(raw.get("reason") or "")[:200]
                if is_countable_objective(objective) and correction < CORRECTIONS:
                    raw = self._correct(
                        objective, sample, raw,
                        "you replied applicable false (" + reason + ") but the objective is a "
                        "counting question. Capture the fields it asks for and use max for the "
                        "most or highest. Reply a complete spec.")
                    if raw is None:
                        return self._fallback(state, "the model did not correct its spec")
                    continue
                return self._fallback(state, "the objective is not a counting question: " + reason)
            try:
                spec = parse_spec(raw)
                self.progress("exact_counting", "checking the spec on a sample", 15)
                result = self.engine(spec.as_dict(), sample, work_dir=self.run_dir,
                                     seconds=SAMPLE_SECONDS,
                                     cancel_requested=self.cancel_requested)
                if result["matched"] == 0:
                    raise SpecError("the pattern matched no record in the sample")
                missed = _missed_most_starts(result)
                if missed and str(raw.get("pattern") or "").startswith("^"):
                    stripped = dict(raw)
                    stripped["pattern"] = str(raw["pattern"])[1:]
                    try:
                        spec2 = parse_spec(stripped)
                        result2 = self.engine(spec2.as_dict(), sample, work_dir=self.run_dir,
                                              seconds=SAMPLE_SECONDS,
                                              cancel_requested=self.cancel_requested)
                    except (SpecError, ExactEngineError):
                        spec2 = None
                        result2 = None
                    if (spec2 is not None and result2 is not None and result2["matched"]
                            and not _missed_most_starts(result2)):
                        spec, result, missed = spec2, result2, None
                        raw = stripped
                if missed:
                    raise SpecError(missed)
            except (SpecError, ExactEngineError) as exc:
                problem = str(exc)
                if correction == CORRECTIONS:
                    return self._fallback(state, f"no valid spec after corrections: {problem}")
                raw = self._correct(objective, sample, raw, problem)
                if raw is None:
                    return self._fallback(state, "the model did not correct its spec")
                continue
            self.progress("exact_counting", "the model confirms the spec", 22)
            verdict = extract_json_object(self._ask(_validation_prompt(objective, spec.as_dict(),
                                                                       result)))
            if verdict is not None and verdict.get("ok") is True:
                issues = objective_fit_issues(objective, spec.as_dict())
                if issues:
                    return self._fallback(state, 'not covered by the computed table: ' + '; '.join(issues))
                coverage = extract_json_object(self._ask(
                    f'Objective:\n{objective}\nSpec:\n{json.dumps(spec.as_dict())}\n'
                    'List every part of the objective NOT covered by the captured fields and '
                    'aggregates, including qualitative judgments. Reply {"uncovered": ["part", ...]}. '
                    'Use an empty list only when every part is covered.'))
                uncovered = coverage.get('uncovered') if coverage else None
                if not isinstance(uncovered, list) or uncovered:
                    return self._fallback(state, 'not covered by the computed table: ' +
                                          (str(uncovered) if uncovered else 'coverage was not confirmed'))
                state["status"] = "counting"
                return spec.as_dict()
            if correction == CORRECTIONS or verdict is None:
                return self._fallback(state, "the model did not confirm the spec on the sample")
            raw = {k: v for k, v in verdict.items() if k != "ok"}  # a spec that may carry ok:false
        return self._fallback(state, "no confirmed spec")

    def _correct(self, objective: str, sample: str, raw: Mapping[str, Any],
                 problem: str) -> dict[str, Any] | None:
        prompt = (f"Objective:\n{objective}\n\nYour spec:\n{json.dumps(dict(raw))}\n\nIt was "
                  f"refused: {problem}\nReply the corrected complete spec.\n{SPEC_FORMAT}\n\n"
                  f"Sample:\n<<<SAMPLE\n{sample}\nSAMPLE>>>")
        return extract_json_object(self._ask(prompt))

    def _prose(self, objective: str, table: Mapping[str, Any]) -> str:
        note = ""
        for _ in range(ANSWER_TRIES):
            prose = self._ask(_answer_prompt(objective, table, note), PROSE_SYSTEM).strip()
            if prose and prose_numbers_ok(prose, table, objective):
                return prose
            note = ("\nYour last reply was empty, cut off, or used a number that is not in the "
                    "results. Answer briefly and use only the numbers given." if not prose else
                    "\nYour last reply used a number that is not in the results. Use only the "
                    "numbers given.")
        return ""

    def _telemetry(self, state: Mapping[str, Any], started: float) -> dict[str, Any]:
        results = state.get("results") or {}
        return {"status": "answered", "model_calls": self.calls,
                "records_matched": results.get("matched"),
                "unmatched_anchor_mentions": results.get("unmatched_anchor_mentions"),
                "input_sha256": results.get("input_sha256"),
                "prose_from_model": state.get("prose_from_model"),
                "seconds": round(self.monotonic() - started, 1)}
