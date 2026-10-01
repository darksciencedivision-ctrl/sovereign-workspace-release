# Exact counting for LONG map/reduce (D6)

Status: implemented in `sovereign_product/exact_counting.py`; wired into
`LongWorkloadExecutor.run` for inputs given as material (`---` or `@input:`).

## The problem

LONG answers a counting question over a big input by mapping chunks with a model and reducing
the parts. A model does not count reliably: on the 65k qualification input (2109 notes, 124 of
them with 16 warnings) the answers were 100, 115 and 110. The operator's decision (D6): if the
computer can do it, the computer does it, not the AI. Counts, totals, maxima and minima of a
LONG answer are computed by the product, deterministically.

## The route

An objective with a countable or aggregate intent, over material, takes the exact route. It
has four steps; the model only ever writes *data* (a spec) and *prose*, never a number that
ends up in the answer.

1. **Spec.** One model session sees the objective and a sample of the input (the head, evenly
   spaced windows and the tail, with their offsets) and replies with one JSON object:
   `{"applicable": false}` (a list, summary or explanation objective) or
   `{"applicable": true, "pattern": ..., "flags": ..., "fields": {...}, "aggregates": [...]}`.
   The regex has named groups only; each is a field typed `int` or `str`. Aggregates
   come from a closed list: `count`, `count_where` (`==`, `!=`, `<`, `<=`, `>`, `>=` against a
   literal), `sum`, `max`, `min` (with ties), and `group_count`. Nothing in the spec is code.
2. **Validation.** The product checks the spec against the allow-list, compiles the pattern
   under a static safety check, runs it over the sample, and shows the model the parsed rows
   and the aggregates over the sample. The model replies `{"ok": true}` or a corrected spec.
   At most two corrections. A spec that is invalid, matches nothing in the sample, or is not
   confirmed ends the exact route: the run falls back to map/reduce and the answer says so.
3. **Execution.** The product finds every start of a record (the pattern's literal anchor, or
   every non-blank line for a `^` pattern with flag `m`), matches the pattern from there up to
   the next start (so a greedy tail cannot swallow the following record: live, a `[^,]*` tail
   halved a count of 63 to 31) and computes every aggregate exactly with integer arithmetic: ties included, with the matched
   record count, the input's SHA-256 and byte size, first and last match offsets, examples,
   and how many times the pattern's literal anchor occurs against how many records matched
   (a gap means some mentions did not match the pattern; the answer states it).
4. **Answer.** One model session (its own system prompt: plain sentences, not the JSON of the
   spec calls) writes the answer from the computed table only. The product
   rejects prose containing a number that is not in the table or the objective (two retries,
   then a plain deterministic answer), and appends the table verbatim under
   "Computed by the product over N records".

## Safety limits

* No code execution. The spec is data validated against the allow-list: at most 2,000
  characters of pattern, 12 fields, 8 aggregates, only flags `i` and `m`.
* The pattern is checked statically before it runs: no back-references, look-around or atomic
  groups; no alternation or unbounded repeat inside another repeat; bounded repeats (`{m,n}`)
  top out at 1,000 and nested repeats may multiply to at most 2,000 combinations (a nested
  1,000 x 1,000 repeat ran for over a minute on a 60-character record); an unbounded repeat
  applies to a single character or class; it must start with at least 3 literal characters
  (the record anchor), or with `^` under flag `m` when every line is a record (a table, a CSV,
  a log whose lines start with a varying value). Each match attempt starts at an
  anchor and sees at most 4,096 characters, so a record longer than that is not matched (it is
  reported as an unmatched mention).
* The engine runs in a child process (`exact_worker.py`, stdlib only, `python -I`) that the
  product kills at 300 s (20 s on the sample) or on cancel: a runaway pattern costs a timeout,
  never a stuck worker.
* Input is already capped at 64 MiB (`MAX_INPUT_BYTES`); execution keeps running aggregates,
  not the rows, and refuses a group-by with more than 10,000 distinct values.
* Cancellation is checked between steps and while the engine runs.

## When it is used

`is_countable_objective` is a cheap word check. Words that ask for a number outright (count, how
many, number of, sum of, tally, how often, total number) always try the exact route. Words that
rank or total (total, most, least, fewest, maximum, minimum, largest, smallest, highest, lowest)
try it only when the objective is not also a text request (list, summarize, describe, explain,
compare, outline, discuss, review, analyze, draft, write, design, plan): "summarize the most
important risks" is not a counting question, and the spec call is a thinking-model session that
takes minutes. The check only decides whether to *try* the exact route; the spec step still says
`applicable: false` for a list or summary objective, and the run then maps and reduces as before
(A1 rules unchanged).

## Resume

The exact route writes `exact.json` in the run's folder (atomically): the status, the spec, the
computed results and the final answer as each is known. A resumed job re-uses it; results
already computed never need the input file again. A run whose `exact.json` says `fallback`
resumes as map/reduce.

## Evidence (live, on the 32k and 65k qualification inputs)

See the progress log and `docs/performance/` for the measured runs: the answer must give 63
(32k) and 124 (65k) notes with 16 warnings, the maximum 16 and its ties, on every run.
