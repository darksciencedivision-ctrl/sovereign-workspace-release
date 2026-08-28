"""Audit R4 falsification — the wsl-probe tests must not be green because the host happens to have WSL.

`wsl_parakeet.probe_nemo` short-circuits on `shutil.which("wsl") is None`. Before the fix, the probe
tests inherited the host PATH, so on a machine WITHOUT WSL every one of them took that short-circuit:
the ones expecting an unavailable engine passed for the wrong reason, and the ones asserting what a
real probe does (`test_probe_true_on_rc0`, the TTL and re-probe tests) FAILED — on a file whose
docstring promises determinism on any host. Either way the result said nothing about the code under
test. The `wsl_present` fixture now pins the lookup with `monkeypatch.setattr`.

This runs the same two test files in a child process whose PATH contains no `wsl.exe` at all, and
fails if they do not still pass. It changes nothing on disk, and the STRIPPED leg starts no WSL
process; the baseline leg is an ordinary run of those files, so on a host that has WSL it runs the
two host-gated proofs that deliberately spawn `wsl.exe` and `node`.

A run that merely goes green is not enough, because a file whose every test SKIPPED would do that
too — the vacuity R4 is about, wearing a different hat. So the stripped run is compared with the
normal-PATH run: the same tests must be collected, and the only tests allowed to skip are the ones
that declare a host requirement in a `skipif` reason (the induced-hang proof needs `node`, the
managed-stdin proof needs a real WSL). Anything else skipping is a failure.

Run from the repo root:  py -3.12 tools/mutation/wsl_path_hermeticity_check.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.host_prerequisites import NODE, WSL  # noqa: E402

FILES = ["tests/integration/test_wsl_parakeet.py", "tests/integration/test_voice_mic.py"]

# Skips permitted on a host without WSL: each names a proof that genuinely needs a host binary.
#
# DERIVED from the prerequisite declarations rather than duplicated as literals. The first version
# hard-coded the two reason strings, so when W-22 replaced those `skipif` reasons — with ones that
# NAME the missing prerequisite, which is stricter than what they replaced — this check failed with
# "tests skipped for reasons that are not a declared host requirement" while the property it exists
# to defend was actually being met better than before. Two copies of a string are one copy too many
# when the whole point is that the reason must be a DECLARED host requirement: `requires()` refuses
# an undeclared prerequisite, so deriving from it is what makes "declared" mean something.
ALLOWED_SKIP_REASONS = (NODE.skip_reason, WSL.skip_reason)


def _counts(stdout: str) -> dict[str, int]:
    """The `N passed, M skipped` tail line, as numbers."""
    out = {"passed": 0, "skipped": 0, "failed": 0, "error": 0}
    for n, word in re.findall(r"(\d+) (passed|skipped|failed|error)", stdout):
        out[word] = int(n)
    return out


def _run(env: dict[str, str]) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *FILES, "-q", "-rs"],
        env=env, capture_output=True, text=True,
        # W-22 corrective: the child writes UTF-8 (PYTHONIOENCODING above); without this the
        # PARENT decoded it with the host ANSI codepage, so any non-ASCII skip reason came
        # back mojibaked and could never match. Latent until a reason contained an em-dash.
        encoding="utf-8", errors="replace", cwd=REPO,
    )
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    base_env = dict(os.environ)
    base_env["PYTHONIOENCODING"] = "utf-8"
    stripped = dict(base_env)
    # A PATH with no System32 on it: `shutil.which("wsl")` can find nothing.
    stripped["PATH"] = str(Path(sys.executable).parent)

    seen = subprocess.run(
        [sys.executable, "-c", "import shutil;print(shutil.which('wsl'))"],
        env=stripped, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO,
    ).stdout.strip()
    print(f"child PATH resolves wsl to: {seen}")
    if seen != "None":
        print("REFUSING: the stripped PATH still finds wsl — this check would prove nothing.")
        return 3

    base_code, base_out, _ = _run(base_env)
    base = _counts(base_out)
    print(f"normal PATH:   {base}")
    if base_code != 0:
        print(base_out[-2000:])
        print("REFUSING: the baseline run is not green — fix that before reading this check.")
        return 3

    code, out, err = _run(stripped)
    got = _counts(out)
    print(f"stripped PATH: {got}")
    print(out[-1200:])
    if code != 0:
        print(err[-2000:])
        print("FAIL: the probe tests depend on the host having WSL on PATH (audit R4 not discharged).")
        return 1

    collected_base = base["passed"] + base["skipped"]
    collected = got["passed"] + got["skipped"]
    if collected != collected_base:
        print(f"FAIL: {collected} tests ran without WSL vs {collected_base} with it — "
              "the comparison is not like-for-like.")
        return 1

    # `SKIPPED [n] path\to\file.py:LINENO: reason` — the first pattern written here used `[^:]+` for
    # the path, which cannot cross the `:` before the line number, so it matched NOTHING on real
    # pytest output and the guard below could never fire (spec-audit F2). It is asserted, not
    # assumed: a run that reports skips this cannot read is a run whose skip check did not happen.
    skip_lines = re.findall(r"^SKIPPED \[(\d+)\] .+?:\d+: (.+)$", out, flags=re.MULTILINE)
    counted = sum(int(n) for n, _ in skip_lines)
    if counted != got["skipped"]:
        print(f"FAIL: {got['skipped']} tests skipped but only {counted} skip reasons could be read — "
              "the skip check cannot be performed on this output.")
        return 1
    unexpected = [r.strip() for _, r in skip_lines if r.strip() not in ALLOWED_SKIP_REASONS]
    if unexpected:
        print(f"FAIL: tests skipped for reasons that are not a declared host requirement: {unexpected}")
        return 1
    # Every test that ran with WSL must still run without it, minus exactly the host-gated skips
    # accounted for above. No slack: an extra silent skip is the vacuity this check exists to catch.
    if got["passed"] != base["passed"] - counted:
        print(f"FAIL: {got['passed']} passed without WSL vs {base['passed']} with it, and only "
              f"{counted} accounted-for skips — something else went quiet.")
        return 1

    print(f"PASS: {got['passed']} of {collected_base} probe tests are hermetic — they pin the PATH "
          f"lookup instead of inheriting it; the {got['skipped']} skipped ones declare a host "
          "requirement in their own skipif reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
