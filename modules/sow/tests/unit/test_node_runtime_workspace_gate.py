"""Phase 3: workspace containment (API layer) + local gate determinism."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.host_prerequisites import WINDOWS, requires

from node_runtime import GateConfigError, LocalGate, WorkspaceBinding, WorkspaceEscape

# ---------- workspace binding ----------

def make_ws(tmp_path: Path, refusals: list | None = None) -> WorkspaceBinding:
    root = tmp_path / "ws"
    root.mkdir(exist_ok=True)
    logger = (lambda kind, **data: refusals.append((kind, data))) if refusals is not None else None
    return WorkspaceBinding(root, "n-test", on_refusal=logger)


def test_inside_paths_resolve_and_write(tmp_path: Path) -> None:
    ws = make_ws(tmp_path)
    p = ws.write_text("a/b/c.txt", "hello")
    assert p.read_text(encoding="utf-8") == "hello"
    assert ws.root in p.parents


@pytest.mark.parametrize("attempt", [
    pytest.param("..\\escape.txt", marks=requires(WINDOWS)),
    "../escape.txt",
    "a/../../escape.txt",
    pytest.param("a\\..\\..\\b\\escape.txt", marks=requires(WINDOWS)),
])
def test_dotdot_escapes_refused_and_logged(tmp_path: Path, attempt: str) -> None:
    refusals: list = []
    ws = make_ws(tmp_path, refusals)
    with pytest.raises(WorkspaceEscape):
        ws.write_text(attempt, "nope")
    assert refusals and refusals[0][0] == "workspace_escape_refused"
    assert not (tmp_path / "escape.txt").exists()


def test_absolute_paths_refused(tmp_path: Path) -> None:
    refusals: list = []
    ws = make_ws(tmp_path, refusals)
    outside = tmp_path / "outside.txt"
    with pytest.raises(WorkspaceEscape, match="absolute"):
        ws.write_text(str(outside), "nope")
    assert not outside.exists()
    assert refusals


def test_read_outside_refused_too(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    ws = make_ws(tmp_path)
    with pytest.raises(WorkspaceEscape):
        ws.read_text("../secret.txt")


@pytest.mark.parametrize("name", ["NUL", "CON", "COM1", "LPT1", "PRN", "AUX", "nul", "out/CON", "a/NUL.txt"])
def test_reserved_device_names_refused(tmp_path: Path, name: str) -> None:
    """Fail-open hole (spec-audit MEDIUM): device names must not reach the filesystem."""
    refusals: list = []
    ws = make_ws(tmp_path, refusals)
    with pytest.raises(WorkspaceEscape, match="reserved device"):
        ws.write_text(name, "should never persist")
    assert refusals


@pytest.mark.parametrize("name", ["report.", "data.txt ", "trailing .", "dir/thing. "])
def test_trailing_dot_or_space_refused(tmp_path: Path, name: str) -> None:
    ws = make_ws(tmp_path)
    with pytest.raises(WorkspaceEscape, match="trailing"):
        ws.write_text(name, "aliasable")


@pytest.mark.parametrize("name", ["host.txt:ads", "out/analysis.md:hidden", "C:evil"])
def test_ads_and_drive_relative_refused(tmp_path: Path, name: str) -> None:
    ws = make_ws(tmp_path)
    with pytest.raises(WorkspaceEscape):
        ws.write_text(name, "hidden stream / drive-relative")


@requires(WINDOWS)   # Windows-only semantics: POSIX treats backslash/junctions and the kernel APIs differently
def test_junction_escape_refused(tmp_path: Path) -> None:
    """The single most security-relevant behavior: a reparse point created inside the
    workspace pointing outside must be followed and refused (spec-audit MINOR: was untested).
    Junctions need no privilege (mklink /J)."""
    import subprocess

    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape_link"
    proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"could not create junction on this host: {proc.stderr.strip()}")
    refusals: list = []
    ws = WorkspaceBinding(root, "n-test", on_refusal=lambda kind, **d: refusals.append((kind, d)))
    with pytest.raises(WorkspaceEscape, match="outside the workspace"):
        ws.write_text("escape_link/pwned.txt", "escaped")
    assert not (outside / "pwned.txt").exists()
    assert refusals


# ---------- local gate ----------

def valid_output_and_content() -> tuple[dict, bytes]:
    content = b"# analysis\nreal content\n"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    output = {
        "summary": "done",
        "claims": [{"text": "c1", "evidence_refs": [digest]}],
        "artifact": {
            "artifact_id": digest, "media_type": "text/markdown", "size_bytes": len(content),
            "created_by_node": "n-test", "task_id": None,
            "ts": datetime.now(timezone.utc).isoformat(), "schema": "artifact@1.0",
        },
    }
    return output, content


def test_valid_output_passes_all_criteria(tmp_path: Path) -> None:
    output, content = valid_output_and_content()
    verdict = LocalGate().evaluate(output, content)
    assert verdict.passed, verdict.reasons()
    assert len(verdict.checks) == 5


def test_missing_evidence_fails(tmp_path: Path) -> None:
    output, content = valid_output_and_content()
    output["claims"].append({"text": "unsupported", "evidence_refs": []})
    verdict = LocalGate().evaluate(output, content)
    assert not verdict.passed
    assert any("claims_cite_evidence" in r for r in verdict.reasons())


def test_placeholder_text_fails() -> None:
    output, content = valid_output_and_content()
    content2 = content + b"\nTODO: finish\n"
    # hash mismatch would also fail; recompute so ONLY the placeholder criterion trips
    output["artifact"]["artifact_id"] = "sha256:" + hashlib.sha256(content2).hexdigest()
    output["artifact"]["size_bytes"] = len(content2)
    verdict = LocalGate().evaluate(output, content2)
    assert not verdict.passed
    reasons = " | ".join(verdict.reasons())
    assert "no_placeholders" in reasons and "artifact_metadata_valid" not in reasons


def test_tampered_content_hash_fails() -> None:
    output, content = valid_output_and_content()
    verdict = LocalGate().evaluate(output, content + b"tamper")
    assert not verdict.passed
    assert any("hash mismatch" in r for r in verdict.reasons())


def test_schema_invalid_artifact_fails() -> None:
    output, content = valid_output_and_content()
    del output["artifact"]["media_type"]
    verdict = LocalGate().evaluate(output, content)
    assert not verdict.passed
    assert any("artifact@1.0" in r for r in verdict.reasons())


def test_unknown_criterion_fails_closed() -> None:
    with pytest.raises(GateConfigError, match="unknown"):
        LocalGate(criteria=("output_parses", "definitely_not_a_check"))


def test_empty_criteria_fails_closed() -> None:
    with pytest.raises(GateConfigError, match="no criteria"):
        LocalGate(criteria=())


def test_verdict_is_deterministic() -> None:
    output, content = valid_output_and_content()
    a = LocalGate().evaluate(output, content)
    b = LocalGate().evaluate(json.loads(json.dumps(output)), content)
    assert a == b
