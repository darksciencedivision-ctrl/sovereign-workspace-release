"""The cross-language skip count is VISIBLE and FAILING above a threshold (2.5, W-23).

WHY THIS EXISTS. `node --test` reports a skipped test as `ok` at the TAP level and
exits 0. When `py -3.12` is absent, 28 JS<->Python legs skip and the whole run
still reads green — including the stdio MCP handshake leg that covers the surface
F2 records as broken. A suite that goes quiet exactly where it stops testing
anything is worse than one that fails, because nobody looks.

WHAT THIS IS. A parser for `node --test`'s own summary block plus a policy over
it. It deliberately does NOT trust the process exit code: exit 0 with 28 skips is
precisely the state this exists to catch.

An absent summary is a REFUSAL, not zero skips. A run that produced no summary
did not produce evidence that nothing was skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: `node --test` prints `ℹ pass 216` on a TTY and `# pass 216` under some reporters. Both are
#: accepted; the count is what matters, not the glyph in front of it.
_SUMMARY_LINE = re.compile(r"^[\sℹ#]*\s*(tests|suites|pass|fail|cancelled|skipped|todo)\s+"
                           r"(\d+)\s*$", re.MULTILINE)

#: The fields a complete summary block carries. A partial block means the run was truncated.
REQUIRED_FIELDS = ("tests", "pass", "fail", "skipped")


class SkipSummaryMissing(RuntimeError):
    """`node --test` produced no readable summary. Not the same as 'nothing was skipped'."""


@dataclass(frozen=True)
class SkipVerdict:
    ok: bool
    skipped: int
    allowed: int
    suite: str
    reason: str


def parse_node_test_summary(output: str) -> dict[str, int]:
    """The counts `node --test` reported. Raises when there is no complete summary to read."""
    found = {name: int(value) for name, value in _SUMMARY_LINE.findall(output or "")}
    missing = [f for f in REQUIRED_FIELDS if f not in found]
    if missing:
        raise SkipSummaryMissing(
            f"no complete `node --test` summary in the output (missing {', '.join(missing)}); "
            f"a run that reported nothing is not a run that skipped nothing")
    return found


def evaluate_skip_policy(output: str, *, suite: str, allowed_skips: int = 0) -> SkipVerdict:
    """Judge a `node --test` run by its SKIP count, independently of its exit code.

    `allowed_skips` is a budget a caller must state deliberately. The default is 0 because the
    cross-language legs have no legitimate reason to skip on a host that has its prerequisites —
    and on a host that does not, the skip is the finding.
    """
    counts = parse_node_test_summary(output)
    skipped = counts["skipped"]
    if skipped > allowed_skips:
        return SkipVerdict(
            ok=False, skipped=skipped, allowed=allowed_skips, suite=suite,
            reason=(f"{suite}: {skipped} test(s) SKIPPED, budget {allowed_skips}. `node --test` "
                    f"reports a skip as `ok` and exits 0, so this run reads green while those "
                    f"legs tested nothing — state which prerequisite is missing, or fix it"))
    return SkipVerdict(
        ok=True, skipped=skipped, allowed=allowed_skips, suite=suite,
        reason=f"{suite}: {skipped} skipped, within the stated budget of {allowed_skips}")
