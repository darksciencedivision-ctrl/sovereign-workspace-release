"""T2 adversarial tests — harness-config injection (THREAT_MODEL.md T2/TB-4; OD-18, B3-5).

The threat: `AGENTS.md`, MCP config (`.mcp.json`) and model output are NODE-CONTROLLED
untrusted input. Sovereign authorization policy must never be read from, or influenced by,
any of them. These tests pin the three structural legs of that guarantee and the one
functional leg:

  A. `control_plane/policy.py` — THE authority — has no file/environment I/O surface at all;
     there is no channel by which a planted file could reach it.
  B. nothing under `control_plane/` names the harness-config files; the authority package
     has no knowledge of them to read from.
  C. the deployment profile in force comes from the host's ONE documented environment
     variable — a planted/unknown profile id fails closed (`ProfileViolation`), it is never
     read as permission.

Fail-before OD-18: this file did not exist (the threat model named these tests NOT
IMPLEMENTED). Fail-after: all legs green.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTROL_PLANE = REPO / "control_plane"

#: The harness-config surfaces T2 names as node-controlled untrusted input.
HARNESS_CONFIG_NAMES = ("AGENTS.md", ".mcp.json", "mcp_config.json")

#: File/environment I/O primitives. Any of these inside policy.py would be a channel a
#: planted config could reach the authority through.
_IO_PRIMITIVES = re.compile(
    r"\bopen\s*\(|\.read_text\(|\.read_bytes\(|\bos\.environ\b|\bos\.getenv\b|"
    r"\bos\.path\b|\bpathlib\b|\bPath\s*\(|\bjson\.load\(")


def test_the_authority_module_has_no_file_or_environment_io_surface() -> None:
    """Leg A (structural): policy.py decides from the Identity it is handed — nothing else.
    A file-read or env-read primitive here would be a T2 channel and must fail this test."""
    source = (CONTROL_PLANE / "policy.py").read_text(encoding="utf-8")
    hits = []
    for lineno, line in enumerate(source.splitlines(), 1):
        if _IO_PRIMITIVES.search(line):
            hits.append(f"  policy.py:{lineno}: {line.strip()}")
    assert not hits, (
        "control_plane/policy.py carries file/environment I/O — the authority must be pure "
        "decision logic over the identity it is given:\n" + "\n".join(hits))


def test_the_authority_package_never_names_the_harness_config_files() -> None:
    """Leg B (structural): no module under control_plane/ references AGENTS.md or MCP config
    by name — the package cannot consume what it does not know."""
    hits = []
    for path in sorted(CONTROL_PLANE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in HARNESS_CONFIG_NAMES:
            if name in text:
                hits.append(f"  {path.relative_to(REPO)} names {name}")
    assert not hits, (
        "control_plane/ references harness-config files — node-controlled input must not be "
        "a source the authority package even knows:\n" + "\n".join(hits))


def test_a_planted_or_unknown_deployment_profile_fails_closed() -> None:
    """Leg C (functional): the profile in force comes from SOVEREIGN_DEPLOYMENT_PROFILE alone
    (unset = documented `cloud` default); an unrecognized planted value is a ProfileViolation,
    never permission."""
    pytest.importorskip("jsonschema")
    from control_plane.profiles.loader import ProfileViolation
    from node_runtime.supervisor.provider_probe_session import profile_loader_from_host

    assert profile_loader_from_host({}).profile.profile_id == "cloud", (
        "unset means the documented default, not an error and not an invention")
    airgapped = profile_loader_from_host(
        {"SOVEREIGN_DEPLOYMENT_PROFILE": "offline_airgapped"})
    assert airgapped.profile.is_airgapped is True
    with pytest.raises(ProfileViolation):
        profile_loader_from_host({"SOVEREIGN_DEPLOYMENT_PROFILE": "planted_admin_profile"})


def test_policy_denies_by_default_for_unknown_roles_and_kinds() -> None:
    """The functional floor of T2: even a caller that MINTS an identity gets deny-by-default —
    a role outside the roster is refused, operator-only kinds refuse a worker, and a worker can
    never self-promote — so nothing a harness injects can widen authority by inventing a role."""
    from control_plane.policy import Identity, SovereignPolicy

    policy = SovereignPolicy()
    injected = Identity(node_id="n1", role="harness_invented_role", project_id="p")
    entry = {"project_id": "p", "kind": "memory", "status": "CANDIDATE",
             "provenance": {"author_node": "n1"}}
    assert policy.authorize_publish(injected, entry).allow is False, (
        "an invented role must not publish")

    worker = Identity(node_id="w1", role="worker", project_id="p")
    directive = {"project_id": "p", "kind": "directive", "status": "CANDIDATE",
                 "provenance": {"author_node": "w1"}}
    assert policy.authorize_publish(worker, directive).allow is False, (
        "a worker may never write the directive kind")

    own_candidate = {"project_id": "p", "kind": "memory", "status": "UNDER_REVIEW",
                     "provenance": {"author_node": "w1"}}
    assert policy.authorize_transition(worker, own_candidate, "ACCEPTED").allow is False, (
        "a worker may never self-promote (I-M6)")
