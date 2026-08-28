"""
SWS Distillery file parser — truthful status only.
"""
import hashlib
import os
import re
import json
from pathlib import Path


HANDOFF_PATH = "D:/Sovereign Distillery/CANONICAL-HANDOFF.md"
OPEN_QUESTIONS_PATH = "D:/Sovereign Distillery/docs/02-OPEN-QUESTIONS.md"
PRODUCT_SOFTWARE = "D:/Product Software"


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
    try:
        with open(HANDOFF_PATH, "r", encoding="utf-8") as f:
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
        "sha256": _sha256_file(HANDOFF_PATH),
        "file": "CANONICAL-HANDOFF.md"
    }


def _parse_open_questions() -> dict:
    """Parse 02-OPEN-QUESTIONS.md for open questions."""
    try:
        with open(OPEN_QUESTIONS_PATH, "r", encoding="utf-8") as f:
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
        "sha256": _sha256_file(OPEN_QUESTIONS_PATH),
        "file": "docs/02-OPEN-QUESTIONS.md"
    }


def _find_snapshot() -> dict:
    """Find SOVEREIGN_DISTILLERY_ENTERPRISE_* folders in Product Software."""
    matches = []
    try:
        for entry in os.listdir(PRODUCT_SOFTWARE):
            if entry.startswith("SOVEREIGN_DISTILLERY_ENTERPRISE_") and os.path.isdir(
                os.path.join(PRODUCT_SOFTWARE, entry)
            ):
                matches.append(entry)
    except OSError:
        return {"error": "CONFIG_ERROR", "reason": "Cannot read Product Software directory"}

    if len(matches) == 0:
        return {"error": "CONFIG_ERROR", "reason": "No Distillery snapshot found"}
    if len(matches) > 1:
        return {"error": "CONFIG_ERROR(AMBIGUOUS_SNAPSHOT)", "matches": matches}

    return {"snapshot_id": matches[0]}


def get_distillery_status() -> dict:
    """Return full Distillery status for the API."""
    handoff = _parse_handoff()
    questions = _parse_open_questions()
    snapshot = _find_snapshot()

    if "error" in handoff:
        return {"state": "CONFIG_ERROR", "reason": handoff["error"], "handoff": handoff, "questions": questions, "snapshot": snapshot}

    if "error" in questions:
        return {"state": "CONFIG_ERROR", "reason": questions["error"], "handoff": handoff, "questions": questions, "snapshot": snapshot}

    return {
        "state": "NOT_STARTED",
        "handoff": handoff,
        "questions": questions,
        "snapshot": snapshot,
        "verbatim": "No runtime, entry point, or UI exists for Sovereign Distillery. Startup test not applicable.",
        "links": {
            "canonical_handoff": "D:/Sovereign Distillery/CANONICAL-HANDOFF.md",
            "open_questions": "D:/Sovereign Distillery/docs/02-OPEN-QUESTIONS.md",
            "design_plan": "D:/Sovereign Distillery/SOVEREIGN-DISTILLERY-DESIGN-PLAN.md"
        }
    }