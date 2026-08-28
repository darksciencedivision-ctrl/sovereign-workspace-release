"""Phase 15B `.conductor`: the LIVE `claude_code` backend is CONDUCTOR-CAPABLE — the Phase-4
ConductorAdapter can bind it behind the same governed contract (no naked session, no credential,
subscription-governed), and the governed live-conductor spawn enforces every live gate.

Proven here:
  1. `ClaudeCodeConductorBackend` structurally satisfies the `ConductorBackend` contract and so does
     Phase 4's `MockReasoningBackend` — "conductor-capable" is a checkable claim.
  2. `propose_plan` is honest: a JSON decomposition parses to tasks; garbage / malformed ⇒ NO
     fabricated tasks (fail closed), with the raw excerpt preserved.
  3. MOCK-FIRST end-to-end through the REAL entrypoint + REAL MCP: an authorized live_auth +
     confirmed terms + an injected mock backend spawns a governed conductor that loads conductor
     files from MCP and publishes a CANDIDATE decision — zero live call.
  4. Governance: DENIED-by-absence auth and unconfirmed operator terms both skip-with-record; the
     I-X3 allowance comes from live_auth (OP-6: 2), a third conductor on the subscription refused.
  5. The conductor holds NO provider credential; the executing model is recorded honestly.
  6. A `BackendAuthPause` mid-cycle is a fail-closed pause that releases the terminal.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.base.backend import ConductorBackend
from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor import publish_conductor_files
from adapters.conductor.adapter import CONDUCTOR_FILE_ORDER
from adapters.frontier.claude_code import (
    ClaudeCliBackend,
    ClaudeCodeAuthError,
    ClaudeCodeConductorBackend,
    MockClaudeCliBackend,
    _parse_decomposition,
    claude_code_conductor_descriptor,
    extract_reported_model,
)
from control_plane.profiles.live_authorization import LiveAuthorization, load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.conductor_spawn import (
    ConductorSmokeOutcome,
    attempt_live_conductor_smoke,
    spawn_claude_code_conductor,
)
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
)

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"

# OP-6 two-provider live scope (matches the worker adapter tests).
_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-19T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


def _authorized(tmp_path: Path) -> LiveAuthorization:
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")  # a TEST config, never the repo one
    return load_live_authorization(path=cfg)


class _JsonConductorBackend:
    """A worker `Backend` whose `generate` returns a JSON decomposition — lets the mock-first proof
    exercise the STRUCTURED parse path deterministically (the plain MockClaudeCliBackend returns
    prose, which is the honest fail-closed 'unstructured' path)."""

    name = "claude_code:mock:json"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        return json.dumps({
            "proposed_tasks": [
                {"desc": "research compare-and-swap", "capability": "reasoning"},
                {"desc": "write the CAS test", "capability": "coding"},
            ],
            "rationale": "two subtasks",
        })


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _mcp(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj")); c.connect()
    return c


def _manifest(server: MCPServer) -> dict[str, str]:
    op = _mcp(server, "operator", "operator")
    try:
        return publish_conductor_files(op, "operator", CONDUCTOR_DIR)
    finally:
        op.close()


# ---- (1) the wrapper is conductor-capable; so is the Phase-4 mock -----------------------------

def test_conductor_backend_protocol_satisfied() -> None:
    assert isinstance(ClaudeCodeConductorBackend(MockClaudeCliBackend()), ConductorBackend)
    assert isinstance(MockReasoningBackend(), ConductorBackend)  # Phase-4 backend fits the same shape


def test_model_name_records_executing_backend_not_a_selection_label() -> None:
    # default: adopt the wrapped backend's name (honest about what actually ran)
    assert ClaudeCodeConductorBackend(MockClaudeCliBackend(model="fable-5")).model_name.endswith("fable-5")
    # explicit override wins (the supervisor sets a conductor-scoped label)
    b = ClaudeCodeConductorBackend(MockClaudeCliBackend(), model_name="claude_code:conductor:default")
    assert b.model_name == "claude_code:conductor:default" and b.calls == 0


# ---- (2) propose_plan honesty: parse structured, fail-closed on anything else -----------------

def test_propose_plan_parses_structured_json() -> None:
    b = ClaudeCodeConductorBackend(_JsonConductorBackend())
    decision = b.propose_plan("Explain CAS", {"ROLE.md": "be the conductor"}, cycle=1)
    assert b.calls == 1 and decision["parse_mode"] == "structured"
    assert [t["capability"] for t in decision["proposed_tasks"]] == ["reasoning", "coding"]
    assert decision["files_considered"] == ["ROLE.md"] and decision["cycle"] == 1
    # the recorded model is the SELECTION label, marked unverified inside the decision body so a
    # CANDIDATE artifact is never read as a confirmed checkpoint (spec-audit NIT; §11 15B honesty)
    assert decision["model_verified"] is False


def test_propose_plan_fails_closed_on_prose() -> None:
    # MockClaudeCliBackend returns prose, not JSON — NO fabricated tasks, raw preserved
    b = ClaudeCodeConductorBackend(MockClaudeCliBackend())
    decision = b.propose_plan("do the thing", {"ROLE.md": "x"}, cycle=1)
    assert decision["parse_mode"] == "unstructured" and decision["proposed_tasks"] == []
    assert decision["raw_excerpt"]  # the operator sees what the model actually said


@pytest.mark.parametrize("raw", [
    "not json at all",
    '{"proposed_tasks": []}',                                   # empty list ⇒ unstructured
    '{"proposed_tasks": [{"desc": "x"}]}',                      # missing capability ⇒ fail closed
    '{"proposed_tasks": [{"desc": "", "capability": "reasoning"}]}',  # blank desc ⇒ fail closed
    '{"proposed_tasks": ["a string not an object"]}',          # malformed element ⇒ fail closed
])
def test_parse_decomposition_fails_closed(raw: str) -> None:
    tasks, mode = _parse_decomposition(raw)
    assert tasks == [] and mode == "unstructured"


def test_parse_decomposition_handles_fenced_json() -> None:
    raw = "Here is the plan:\n```json\n{\"proposed_tasks\": [{\"desc\": \"a\", \"capability\": \"review\"}]}\n```\n"
    tasks, mode = _parse_decomposition(raw)
    # a task that declares no dependencies gets an EMPTY dep list — never a guessed one
    assert mode == "structured" and tasks == [{"desc": "a", "capability": "review", "deps": []}]


def test_parse_decomposition_carries_declared_deps() -> None:
    """Phase 15D `.flow`: a decomposition's ORDERING is part of what the conductor proposed — the
    task graph consumes it and the plan gate's `plan_acyclic` criterion evaluates it."""
    raw = json.dumps({"proposed_tasks": [{"desc": "a", "capability": "reasoning"},
                                         {"desc": "b", "capability": "coding", "deps": [1]}]})
    tasks, mode = _parse_decomposition(raw)
    assert mode == "structured"
    assert tasks == [{"desc": "a", "capability": "reasoning", "deps": []},
                     {"desc": "b", "capability": "coding", "deps": [1]}]


@pytest.mark.parametrize("deps", ["1", {"1": 2}, [1.5], ["1"], [True]])
def test_parse_decomposition_fails_closed_on_malformed_deps(deps) -> None:
    """A malformed `deps` is a refusal of the WHOLE decomposition, not a silently dropped field.
    `[True]` is covered explicitly: bool is an int subclass and must not pass as a task index."""
    raw = json.dumps({"proposed_tasks": [{"desc": "a", "capability": "reasoning", "deps": deps}]})
    tasks, mode = _parse_decomposition(raw)
    assert tasks == [] and mode == "unstructured"


@pytest.mark.parametrize("deps", [[0], [-1], [3], [99], [1, 7]])
def test_parse_decomposition_fails_closed_on_out_of_range_deps(deps) -> None:
    """A well-TYPED index naming no proposed task is still malformed. The indices are 1-based over
    the proposed list, so `0`, negatives and anything past the last task are refused — the whole
    decomposition, never a silently dropped edge.

    A validator mutation proved this range check was unpinned — deleting it from BOTH this parser
    and `live_flow._resolve_deps` left the entire suite green."""
    raw = json.dumps({"proposed_tasks": [{"desc": "a", "capability": "reasoning"},
                                         {"desc": "b", "capability": "coding", "deps": deps}]})
    tasks, mode = _parse_decomposition(raw)
    assert tasks == [] and mode == "unstructured"


# ---- (2b) executing-model reconciliation from the CLI JSON (Phase 15B `.gate`) ----------------

@pytest.mark.parametrize("payload,expected", [
    ({"result": "ok", "model": "claude-fable-5-20260101"}, "claude-fable-5-20260101"),
    ({"result": "ok", "model": "  claude-opus-4-8  "}, "claude-opus-4-8"),      # trimmed
    ({"result": "ok", "modelUsage": {"claude-fable-5": {"in": 3}}}, "claude-fable-5"),  # single key
    ({"result": "ok"}, None),                                                    # absent ⇒ unverified
    ({"result": "ok", "model": ""}, None),                                       # blank ⇒ unverified
    ({"result": "ok", "model": 42}, None),                                       # wrong type ⇒ None
    ({"modelUsage": {"a": {}, "b": {}}}, None),                                  # no cost signal ⇒ None
    ("not a dict", None),                                                        # non-dict ⇒ None
    # REAL multi-model shape (Phase 15D `.flow` live smoke): a primary + a fast-model helper.
    # Reconciled to the cost-DOMINANT model, deterministically.
    ({"modelUsage": {"claude-haiku-4-5-20251001": {"costUSD": 0.00058},
                     "claude-opus-4-8[1m]": {"costUSD": 0.068}}}, "claude-opus-4-8[1m]"),
    # cost tie between two real checkpoints ⇒ ambiguous ⇒ unverified (never a coin flip)
    ({"modelUsage": {"a": {"costUSD": 0.01}, "b": {"costUSD": 0.01}}}, None),
    # a helper with no numeric cost ⇒ cannot disambiguate ⇒ fail closed
    ({"modelUsage": {"a": {"costUSD": 0.05}, "b": {"costUSD": None}}}, None),
    # bool is not a numeric cost (bool is an int subclass) ⇒ fail closed
    ({"modelUsage": {"a": {"costUSD": True}, "b": {"costUSD": 0.05}}}, None),
    # a non-string key poisons the whole map ⇒ fail closed
    ({"modelUsage": {"claude-opus": {"costUSD": 0.9}, 7: {"costUSD": 0.1}}}, None),
])
def test_extract_reported_model_fail_closed(payload, expected) -> None:
    assert extract_reported_model(payload) == expected


def test_extract_reported_model_matches_the_captured_real_cli_shape() -> None:
    """Ground truth: the sanitized envelope actually captured from the host `claude` CLI during the
    Phase 15D `.flow` live smoke resolves to its cost-dominant primary — not None, not the helper."""
    from pathlib import Path

    from adapters.frontier.claude_code import reported_models

    captured = ROOT / "tools" / "live" / "claude_json_shape.captured.json"
    if not captured.exists():                       # the fixture is written by the operator-run smoke
        pytest.skip("no captured live CLI envelope on this host")
    payload = json.loads(captured.read_text(encoding="utf-8"))
    primary = extract_reported_model(payload)
    assert primary is not None and primary.strip() == primary
    # the primary is the most expensive modelUsage entry
    usage = payload["modelUsage"]
    assert primary == max(usage, key=lambda k: usage[k]["costUSD"])
    # the full set is surfaced (transparency), and the primary is one of them
    all_ids = reported_models(payload)
    assert primary in all_ids and len(all_ids) == len(usage)


_DECOMPOSITION_REPLY = json.dumps({"proposed_tasks": [{"desc": "a", "capability": "reasoning"}],
                                   "rationale": "one"})


class _ReportingBackend:
    """A DUCK TYPE wearing every mark of a live CLI backend — the vendor-shaped `name`, a `calls`
    counter, a `reported_model`, a matching stamp — while spawning nothing.

    Until `phase-15d.gate` this fixture drove the module's positive verification test and its
    checkpoint was recorded as VERIFIED. That was U45 site 3: a mock published as a real-provider
    result (§6/§10.4). It is retained deliberately, now as the REFUSAL fixture."""

    name = "claude_code:cli:fable-5"

    def __init__(self, reported: str | None) -> None:
        self.reported_model = reported
        self.reported_model_at_call: int | None = None
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        if self.reported_model:
            self.reported_model_at_call = self.calls   # perfectly fresh — and still not the class
        return _DECOMPOSITION_REPLY


def _genuine_reporting_backend(reported: str | None) -> ClaudeCliBackend:
    """A REAL `ClaudeCliBackend` whose `generate` is replaced so nothing spawns, stamping exactly
    as the live one does. Exact-type checking constrains the CLASS, not the behaviour (U43), which
    is what makes this the only way to exercise the verified path in a mock-first suite."""
    backend = ClaudeCliBackend(model="fable-5")

    def _generate(prompt: str, *, max_tokens: int = 256) -> str:
        backend.calls += 1
        backend.reported_model = reported
        backend.reported_model_at_call = backend.calls if reported else None
        return _DECOMPOSITION_REPLY

    backend.generate = _generate  # type: ignore[method-assign]
    return backend


def test_propose_plan_reconciles_executing_model_when_cli_reports_it() -> None:
    # LIVE path: the wrapped backend is the REAL CLI class and stamped a checkpoint on the call
    # propose_plan just made ⇒ decision records IT, verified, while the selection label is preserved
    # separately (spec-audit `.gate` owed item discharged).
    b = ClaudeCodeConductorBackend(_genuine_reporting_backend("claude-fable-5-20260101"),
                                   model_name="claude_code:conductor:fable-5")
    decision = b.propose_plan("o", {"ROLE.md": "x"}, cycle=1)
    assert decision["model"] == "claude-fable-5-20260101"      # the CLI-reported checkpoint
    assert decision["model_verified"] is True
    assert decision["model_selection"] == "claude_code:conductor:fable-5"  # selection preserved


def test_propose_plan_refuses_a_vendor_shaped_duck_type() -> None:
    """U45 site 3. A backend that is not the CLI class cannot verify a checkpoint however
    convincingly it is dressed — this fixture's stamp is perfectly fresh and still refused."""
    b = ClaudeCodeConductorBackend(_ReportingBackend("claude-fable-5-20260101"),
                                   model_name="claude_code:conductor:fable-5")
    decision = b.propose_plan("o", {"ROLE.md": "x"}, cycle=1)
    assert decision["model_verified"] is False
    assert decision["model"] == "claude_code:conductor:fable-5"   # the label, never the checkpoint


def test_propose_plan_refuses_a_checkpoint_left_over_from_an_earlier_call() -> None:
    """U45 site 3, the staleness half. The genuine backend reported a checkpoint on an earlier
    call; on THIS call it reports nothing, so the decision must not inherit the old one."""
    backend = _genuine_reporting_backend("claude-fable-5-20260101")
    b = ClaudeCodeConductorBackend(backend, model_name="claude_code:conductor:fable-5")
    assert b.propose_plan("o", {"ROLE.md": "x"}, cycle=1)["model_verified"] is True

    def _silent(prompt: str, *, max_tokens: int = 256) -> str:
        backend.calls += 1          # a call IS spent — it just reports no checkpoint
        return _DECOMPOSITION_REPLY

    backend.generate = _silent  # type: ignore[method-assign]
    stale = b.propose_plan("o", {"ROLE.md": "x"}, cycle=2)
    assert backend.reported_model == "claude-fable-5-20260101", "the stale value is still sitting there"
    assert stale["model_verified"] is False
    assert stale["model"] == "claude_code:conductor:fable-5"


def test_propose_plan_stays_unverified_when_cli_reports_no_model() -> None:
    # No reported checkpoint (mock, or a CLI that reported none) ⇒ stays the selection label + False,
    # never fabricated.
    b = ClaudeCodeConductorBackend(_genuine_reporting_backend(None),
                                   model_name="claude_code:conductor:fable-5")
    decision = b.propose_plan("o", {"ROLE.md": "x"}, cycle=1)
    assert decision["model"] == "claude_code:conductor:fable-5"
    assert decision["model_verified"] is False
    assert decision["model_selection"] == "claude_code:conductor:fable-5"


# ---- (3) MOCK-FIRST governed conductor spawn end-to-end through the real entrypoint -----------

def test_mock_first_conductor_publishes_candidate_decision(server: MCPServer, tmp_path: Path) -> None:
    manifest = _manifest(server)
    cond = _mcp(server, "conductor-fable5", "conductor")
    gov = SubscriptionGovernor()
    adapter = spawn_claude_code_conductor(
        mcp_client=cond, governor=gov, subscription_ref="claude-sub", node_id="conductor-fable5",
        permission_profile_id="pp-conductor", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        conductor_file_refs=manifest, model="fable-5", backend=_JsonConductorBackend())
    assert adapter.holds_provider_credential() is False  # conductor holds NO credential (§2.2)
    adapter.start()
    assert adapter.loaded_files == CONDUCTOR_FILE_ORDER  # files loaded from MCP in order
    assert gov.active_count("claude-sub") == 1           # I-X3: one terminal acquired
    result = adapter.run_cycle("Build the CAS test harness")
    # the decision is a CANDIDATE proposal in MCP (conductor proposes, never self-promotes)
    decisions = cond.call("read_status", status="CANDIDATE")
    row = next(d for d in decisions if d["entry_id"] == result["decision_entry"])
    assert row["kind"] == "decision"
    body = json.loads(base64.b64decode(cond.call("get_content", entry_id=row["entry_id"])["content_b64"]))
    assert body["parse_mode"] == "structured" and body["model"] == "claude_code:conductor:fable-5"
    assert len(body["proposed_tasks"]) == 2
    adapter.close()
    assert gov.active_count("claude-sub") == 0  # released on close (no wedge)
    cond.close()


def test_conductor_smoke_publishes_and_records_model(server: MCPServer, tmp_path: Path) -> None:
    manifest = _manifest(server)
    cond = _mcp(server, "conductor-fable5", "conductor")
    gov = SubscriptionGovernor()
    outcome = attempt_live_conductor_smoke(
        objective="decompose the objective", mcp_client=cond, governor=gov,
        subscription_ref="claude-sub", node_id="conductor-fable5",
        permission_profile_id="pp", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        conductor_file_refs=manifest, model="fable-5", backend=_JsonConductorBackend())
    assert outcome.ran and outcome.published and not outcome.skipped_with_record
    assert outcome.decision_entry is not None
    assert outcome.model_resolution["model_ref"]["resolved_slug"] == "fable-5"
    assert gov.active_count("claude-sub") == 0  # smoke released the terminal
    cond.close()


# ---- (4) governance: skip-with-record paths + I-X3 allowance ---------------------------------

def test_denied_authorization_skips_with_record(server: MCPServer, tmp_path: Path) -> None:
    cond = _mcp(server, "conductor-fable5", "conductor")
    gov = SubscriptionGovernor()
    outcome = attempt_live_conductor_smoke(
        objective="o", mcp_client=cond, governor=gov, subscription_ref="claude-sub",
        node_id="conductor-fable5", permission_profile_id="pp",
        live_auth=load_live_authorization(path=tmp_path / "no_config.json"),  # DENIED-by-absence
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        conductor_file_refs=_manifest(server), backend=_JsonConductorBackend())
    assert not outcome.ran and outcome.skipped_with_record and outcome.decision_entry is None
    assert outcome.model_resolution is not None  # model resolution surfaced even on skip (§11 15B)
    assert gov.active_count("claude-sub") == 0
    cond.close()


def test_unconfirmed_terms_skip_with_record(server: MCPServer, tmp_path: Path) -> None:
    cond = _mcp(server, "conductor-fable5", "conductor")
    gov = SubscriptionGovernor()
    outcome = attempt_live_conductor_smoke(
        objective="o", mcp_client=cond, governor=gov, subscription_ref="claude-sub",
        node_id="conductor-fable5", permission_profile_id="pp", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=False,
        conductor_file_refs=_manifest(server), backend=_JsonConductorBackend())
    assert not outcome.ran and outcome.skipped_with_record
    assert "LiveTermsNotConfirmed" in outcome.reason and gov.active_count("claude-sub") == 0
    cond.close()


def test_ix3_allowance_two_third_conductor_refused(server: MCPServer, tmp_path: Path) -> None:
    """The I-X3 allowance comes from live_auth (OP-6: 2). Two conductors on the SAME subscription
    start; a third is refused by the governor — never a hardcoded 1."""
    manifest = _manifest(server)
    auth = _authorized(tmp_path)
    assert auth.terminals_per_subscription == 2
    loader = ProfileLoader(DeploymentProfile("cloud"))
    gov = SubscriptionGovernor()
    clients = []

    def _spawn_start(node_id):
        c = _mcp(server, node_id, "conductor"); clients.append(c)
        a = spawn_claude_code_conductor(
            mcp_client=c, governor=gov, subscription_ref="claude-sub", node_id=node_id,
            permission_profile_id="pp", live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=True, conductor_file_refs=manifest, backend=_JsonConductorBackend())
        a.start()
        return a

    a1, a2 = _spawn_start("cond-a"), _spawn_start("cond-b")
    assert gov.active_count("claude-sub") == 2
    with pytest.raises(SubscriptionLimitExceeded):
        _spawn_start("cond-c")
    assert gov.active_count("claude-sub") == 2
    a1.close(); a2.close()
    for c in clients:
        c.close()


# ---- (5)/(6) credential invariant + fail-closed auth pause -----------------------------------

def test_real_backend_scrubs_credentials_conductor_path(tmp_path: Path) -> None:
    """The conductor wraps the SAME ClaudeCliBackend as the worker path, so the §2.2 env scrub is
    inherited: no credential/endpoint var reaches the child. (Pure build_env — no subprocess.)"""
    real = ClaudeCliBackend(model="fable-5")
    wrapped = ClaudeCodeConductorBackend(real)
    env = real.build_env({"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sekret",
                          "CLAUDE_CODE_OAUTH_TOKEN": "tok", "LANG": "C.UTF-8"})
    assert "PATH" in env and "LANG" in env
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert wrapped.model_name.endswith("fable-5")


def test_auth_pause_mid_cycle_releases_terminal(server: MCPServer, tmp_path: Path) -> None:
    class _AuthExpiredBackend:
        name = "claude_code:cli"

        def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
            raise ClaudeCodeAuthError("session expired — pause (Plan §18.4)")

    cond = _mcp(server, "conductor-fable5", "conductor")
    gov = SubscriptionGovernor()
    outcome = attempt_live_conductor_smoke(
        objective="o", mcp_client=cond, governor=gov, subscription_ref="claude-sub",
        node_id="conductor-fable5", permission_profile_id="pp", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        conductor_file_refs=_manifest(server), backend=_AuthExpiredBackend())
    assert outcome.ran is True and outcome.published is False
    assert outcome.skipped_with_record is True and "auth pause" in outcome.reason
    assert gov.active_count("claude-sub") == 0  # released on the pause path (no wedge)
    cond.close()


# ---- roster/Inspector honesty ----------------------------------------------------------------

def test_conductor_descriptor_labels_conductor_and_surfaces_model() -> None:
    d = claude_code_conductor_descriptor("fable-5")
    assert d["node_class"] == "conductor" and d["conductor_capable"] is True
    assert d["model_ref"]["resolved_slug"] == "fable-5" and d["model_ref"]["verified"] is False
    fallback = claude_code_conductor_descriptor(None)
    assert fallback["model_ref"]["is_fallback"] is True  # CLI-default fallback recorded, never silent
