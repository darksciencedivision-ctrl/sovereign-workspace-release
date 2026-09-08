# utc: 2026-09-06T19:25:16.331724+00:00
# producer: Codex receipt correction
FACT[regression-js.txt] The JavaScript receipt header was accidentally emitted on one line; the raw artifact is preserved with SHA-256 16184a233d0ef2dfd5597aece644ce46217b4e129e027d4b7221b159c4abe284.

FACT[regression-js-receipt.txt] This normalized receipt preserves the raw JavaScript test output after its malformed header, with a proper two-line evidence header and SHA-256 ac541fd95d5c6fb9b1a8c28063f4ab7cc7710b3bcd9487a4809c79e0697949ec.

FACT[regression-python.txt] The first Python invocation was `py -3.12 -B -m pytest tests -q` from modules/sow, broader than the prescribed unit-only command; it was interrupted and returned exit_code=1, and its incomplete output is not regression evidence. Its raw header has the same one-line formatting error.

INTERPRETATION: The builder detected the selection error while checking the directive command, then terminated the owned pytest PID 25224 and its child PID 18180 by verified process identity; no result or acceptance is inferred from that run.

RECOMMENDATION: Use only regression-python-unit.txt for the prescribed Python regression result.

INTERPRETATION: During implementation, a transient renderer IIFE-parenthesis syntax error was caught by node --check and corrected before the final focused suite and mutation runs; no failed source version is presented as the candidate. The initial F-37 red receipt is preserved separately.
