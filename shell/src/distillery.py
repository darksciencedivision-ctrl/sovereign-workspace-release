"""
SWS Distillery file parser — truthful status only.
"""
import hashlib
import os
import re
import json
from pathlib import Path


# EPC-01 P3-2. These three paths used to be literals naming two directories that exist on
# exactly one machine: the one that built the release. Shipping them did two things, and
# only one of them was visible.
#
# The visible half: on any other machine both reads fail and the pane reports CONFIG_ERROR.
# That is honest, but it is honest about the wrong thing -- it reports a configuration
# problem the recipient cannot fix, because the configuration was compiled in.
#
# The invisible half: the build operator's directory layout shipped to every recipient.
#
# They are configuration now, read from the environment, with NO built-in default. An
# unset variable is reported as unconfigured rather than guessed at, and there is nothing
# machine-specific left in this file. `docs/OPERATIONS.md` documents the variables.
DISTILLERY_ROOT_ENV = "SOVEREIGN_DISTILLERY_ROOT"
SNAPSHOT_ROOT_ENV = "SOVEREIGN_DISTILLERY_SNAPSHOT_ROOT"


def _distillery_root() -> str:
    """The Distillery source tree, or "" when the operator has not named one."""
    return os.environ.get(DISTILLERY_ROOT_ENV, "").strip().replace("\\", "/").rstrip("/")


def _handoff_path() -> str:
    root = _distillery_root()
    return f"{root}/CANONICAL-HANDOFF.md" if root else ""


def _open_questions_path() -> str:
    root = _distillery_root()
    return f"{root}/docs/02-OPEN-QUESTIONS.md" if root else ""


def _snapshot_root() -> str:
    """The tree searched for SOVEREIGN_DISTILLERY_ENTERPRISE_* snapshots."""
    return os.environ.get(SNAPSHOT_ROOT_ENV, "").strip().replace("\\", "/").rstrip("/")


#: Returned wherever a source tree has not been configured. Distinct from CONFIG_ERROR, which
#: means "you named a tree and it could not be read" -- a different problem with a different fix.
NOT_CONFIGURED = "NOT_CONFIGURED"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, UnicodeDecodeError):
        return ""
    return h.hexdigest()


def _parse_handoff() -> dict:
    """Parse CANONICAL-HANDOFF.md for status and supersedes."""
    path = _handoff_path()
    if not path:
        return {"error": NOT_CONFIGURED, "reason": f"{DISTILLERY_ROOT_ENV} is not set"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return {"error": "CONFIG_ERROR", "reason": "Cannot read CANONICAL-HANDOFF.md"}

    # Status is always "not started" for the Distillery
    status = "not started"
    supersedes = "All prior status reports"

    # Extract Supersedes from the table row
    m = re.search(r'\|\s*\*\*Supersedes\*\*\s*\|\s*([^|]+)\s*\|', text)
    if m:
        supersedes = m.group(1).strip()

    return {
        "status": status,
        "supersedes": supersedes,
        "handoff_text": text[:2000],  # first 2000 chars
        "sha256": _sha256_file(path),
        "file": "CANONICAL-HANDOFF.md"
    }


def _parse_open_questions() -> dict:
    """Parse 02-OPEN-QUESTIONS.md for open questions."""
    path = _open_questions_path()
    if not path:
        return {"error": NOT_CONFIGURED, "reason": f"{DISTILLERY_ROOT_ENV} is not set"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return {"error": "CONFIG_ERROR", "reason": "Cannot read 02-OPEN-QUESTIONS.md"}

    # Find "Resolved" section — everything after is resolved
    resolved_idx = text.find("## Resolved")
    active = text if resolved_idx < 0 else text[:resolved_idx]

    # Find all OQ-\d+ patterns that are not struck through
    # A struck-through line looks like ~~OQ-001~~
    oq_pattern = re.compile(r'(?<!~~)OQ-(\d+)(?!~~)')
    matches = oq_pattern.findall(active)
    oq_ids = [f"OQ-{m}" for m in matches]

    return {
        "open_count": len(oq_ids),
        "open_ids": oq_ids,
        "rule": "Rows matching OQ-\\d+ not struck-through/CLOSED",
        "sha256": _sha256_file(path),
        "file": "docs/02-OPEN-QUESTIONS.md"
    }


def _find_snapshot() -> dict:
    """Find SOVEREIGN_DISTILLERY_ENTERPRISE_* folders in the configured snapshot root."""
    root = _snapshot_root()
    if not root:
        return {"error": NOT_CONFIGURED, "reason": f"{SNAPSHOT_ROOT_ENV} is not set"}
    matches = []
    try:
        for entry in os.listdir(root):
            if entry.startswith("SOVEREIGN_DISTILLERY_ENTERPRISE_") and os.path.isdir(
                os.path.join(root, entry)
            ):
                matches.append(entry)
    except OSError:
        return {"error": "CONFIG_ERROR", "reason": "Cannot read the configured snapshot root"}

    if len(matches) == 0:
        return {"error": "CONFIG_ERROR", "reason": "No Distillery snapshot found"}
    if len(matches) > 1:
        return {"error": "CONFIG_ERROR(AMBIGUOUS_SNAPSHOT)", "matches": matches}

    return {"snapshot_id": matches[0]}


def _links() -> dict:
    """Where the source documents are, for a UI that wants to offer them.

    Empty when no tree is configured. A link to a path that exists on the build machine is
    worse than no link: it looks like a working affordance and is not one.
    """
    root = _distillery_root()
    if not root:
        return {}
    return {
        "canonical_handoff": f"{root}/CANONICAL-HANDOFF.md",
        "open_questions": f"{root}/docs/02-OPEN-QUESTIONS.md",
        "design_plan": f"{root}/SOVEREIGN-DISTILLERY-DESIGN-PLAN.md",
    }


def get_distillery_status() -> dict:
    """Return full Distillery status for the API.

    EPC-01 P3-2. An unreadable source tree used to escalate to a top-level CONFIG_ERROR,
    which was right while the paths were compiled in: unreadable then meant broken. Now that
    the tree is named by the operator, NOT_CONFIGURED is an ordinary state for a recipient
    who has no Distillery corpus, and it must not be reported as a misconfiguration.

    F-033: this endpoint reports the CORPUS and PIPELINE status, not the presence of a runtime.
    The Distillery console IS a shell-managed runnable module (shell/modules/distillery.json runs
    serve.py with an HTTP readiness probe on :5184), so an earlier verbatim claim that "no runtime,
    entry point or UI exists" contradicted the adapter and the shipped serve.py. NOT_STARTED here
    means the CORPUS/pipeline is idle (nothing loaded), which is orthogonal to whether the console
    process is running - that is the module's own lifecycle state in /api/state. A named tree that
    cannot be read is still a CONFIG_ERROR - a real problem with a real fix.
    """
    handoff = _parse_handoff()
    questions = _parse_open_questions()
    snapshot = _find_snapshot()

    for part in (handoff, questions):
        error = part.get("error")
        if error and error != NOT_CONFIGURED:
            return {"state": "CONFIG_ERROR", "reason": error, "handoff": handoff,
                    "questions": questions, "snapshot": snapshot}

    return {
        "state": "NOT_STARTED",
        "handoff": handoff,
        "questions": questions,
        "snapshot": snapshot,
        "verbatim": "Distillery corpus/pipeline is idle (nothing loaded). The console runtime is a shell-managed module; start it from the module list to bring up serve.py.",
        "links": _links(),
    }