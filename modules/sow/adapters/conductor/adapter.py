"""Conductor adapter (Plan §2.14, §9.11; Phase 4).

The conductor is an INTERFACE; the current runtime selection (today: fable-5) backs it but
the architecture knows only this contract (I-CN1). This adapter:
  - loads the 12 operator-authored conductor files FROM MCP, in declared order, BEFORE it
    produces or assigns any work (Plan §2.10.4; the conductor-file draft mandates this);
  - runs the conductor loop against a backend (Phase 4: the deterministic mock reasoner);
  - holds NO provider/subscription credential (Phase 4 exit criterion) — it carries only an
    MCP identity reference; the model backend credential, if any, stays host-side;
  - is subscription-governed (I-X3): one terminal per subscription, acquired at start and
    released on close / before succession.
Phase 4 records conductor DECISIONS as CANDIDATE proposals (the conductor may propose, not
promote — invariant 16/§4.5); launching and assigning workers is Phase 5.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from adapters.base.contract import AdapterCapability, AdapterContext, BaseAdapter
from adapters.base.mock_backend import MockReasoningBackend

# Declared load order (Canonical Handoff §2.10.4): IDENTITY -> ROLE -> policies -> state.
CONDUCTOR_FILE_ORDER: tuple[str, ...] = (
    "IDENTITY.md", "ROLE.md", "CONDUCTOR_DIRECTIVE.md", "ORCHESTRATION_RULES.md",
    "TASK_DECOMPOSITION_RULES.md", "CONTEXT_ROUTING_POLICY.md", "DEBATE_POLICY.md",
    "GATE_POLICY.md", "MODEL_SELECTION_POLICY.md", "OPERATOR_RESERVED_AUTHORITY.md",
    "STOP_CONDITIONS.md", "CURRENT_PROJECT_STATE.md",
)


class ConductorNotReady(Exception):
    """The conductor was asked to act before loading its conductor files (fail closed)."""


class ConductorAdapter(BaseAdapter):
    def __init__(self, context: AdapterContext, mcp_client: Any, backend: MockReasoningBackend | None = None,
                 governor: Any = None, conductor_file_refs: dict[str, str] | None = None) -> None:
        super().__init__(context)
        self._mcp = mcp_client
        self._backend = backend or MockReasoningBackend()
        self._governor = governor
        self._file_refs = dict(conductor_file_refs or {})
        self._loaded: dict[str, str] = {}
        self._cycle = 0
        self._started = False

    def capability(self) -> AdapterCapability:
        # F-136(2): a local Ollama conductor must not advertise frontier/subscription fable-5.
        if type(self._backend).__name__ == "OllamaConductorBackend":
            return AdapterCapability(
                adapter="conductor_ollama_local", node_class="conductor", locality="local",
                offline_profile_eligible=True, requires_network=False, local_runtime=True,
                capabilities=("reasoning", "synthesis"), subscription_backed=False,
            )
        return AdapterCapability(
            adapter="conductor_fable5", node_class="conductor", locality="frontier",
            offline_profile_eligible=False, requires_network=True, local_runtime=False,
            capabilities=("reasoning", "synthesis"), subscription_backed=True,
        )

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        """Acquire the subscription terminal (I-X3), then load conductor files from MCP. If the
        load fails, release the terminal so a retry/successor isn't wedged (spec-audit F2)."""
        if self._governor is not None and self._context.subscription_ref:
            self._governor.acquire(self._context.subscription_ref, self._context.node_id)
        try:
            self._load_conductor_files()
        except Exception:
            self.close()  # release the just-acquired terminal; fail closed AND recover
            raise
        self._started = True

    def _load_conductor_files(self) -> None:
        missing = [f for f in CONDUCTOR_FILE_ORDER if f not in self._file_refs]
        if missing:
            raise ConductorNotReady(f"conductor-file resource refs missing from MCP: {missing}")
        for filename in CONDUCTOR_FILE_ORDER:  # declared order, one MCP read each
            res = self._mcp.call("get_content", entry_id=self._file_refs[filename])
            self._loaded[filename] = base64.b64decode(res["content_b64"]).decode("utf-8")
            self._log("loaded_conductor_file", filename=filename, entry_id=self._file_refs[filename])
        self._log("conductor_files_loaded", order=list(CONDUCTOR_FILE_ORDER))

    @property
    def loaded_files(self) -> tuple[str, ...]:
        return tuple(self._loaded)

    @property
    def is_active(self) -> bool:
        """Whether this conductor is live: started and not yet closed.

        Distinct from `get_context_status()["ready"]`, which reports whether all 12 conductor files
        were LOADED — a closed conductor still has them in memory, so `ready` stays True after
        `close()` and is not a liveness signal. Phase 15D `.succession` needs the real one to
        evidence that a killed predecessor is actually gone, and probing by calling `run_cycle`
        would risk spending a live model call if the refusal ever regressed.
        """
        return self._started

    @property
    def backend(self) -> Any:
        """The bound backend, read-only.

        Exposed so a governed caller (Phase 15D `.succession`) can classify the conductor's leg
        from the backend it ACTUALLY holds — exact type, counted calls, reported checkpoint —
        instead of reaching into `_backend` from another module or trusting configuration. It
        grants no new authority: the backend only produces text, and every spawn gate has already
        run by the time a caller holds the adapter. Mirrors `ModelWorkerAdapter.backend`.
        """
        return self._backend

    @property
    def reported_model(self) -> str | None:
        """The EXECUTING checkpoint the backend's provider actually reported, or None when the
        backend reported nothing (mock path, or a CLI that returned no model field). Read-only and
        fail-closed: a selection label is never promoted into this slot (Phase 15D `.selection`)."""
        reported = getattr(self._backend, "reported_model", None)
        return reported if isinstance(reported, str) and reported.strip() else None

    # -- conductor loop --------------------------------------------------------
    def run_cycle(self, objective: str) -> dict[str, Any]:
        """One conductor tick: propose a decomposition and record it as a CANDIDATE decision
        in MCP. Refuses to act until conductor files are loaded (fail closed)."""
        if not self._started or len(self._loaded) != len(CONDUCTOR_FILE_ORDER):
            raise ConductorNotReady("conductor must load all conductor files before acting")
        self._cycle += 1
        decision = self._backend.propose_plan(objective, self._loaded, self._cycle)
        content = _json_bytes(decision)
        prov = {"author_node": self._context.node_id, "task_id": None,
                "ts": datetime.now(timezone.utc).isoformat(), "directive_version": "v2.4",
                "confidence": "medium", "model": self._backend.model_name}
        pub = self._mcp.call("publish", kind="decision", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"), provenance=prov,
                             status="CANDIDATE")
        self._log("conductor_decision", cycle=self._cycle, entry_id=pub["entry_id"])
        return {"cycle": self._cycle, "decision_entry": pub["entry_id"], "decision": decision}

    def read_accepted(self) -> list[dict[str, Any]]:
        """Read ACCEPTED shared-memory entries via MCP (provenance-bearing). Public so the
        orchestration layer never reaches into the adapter's MCP client.

        Refuses once closed (U53, discharged at `phase-15d.gate`): a succession's central claim is
        that the predecessor is GONE, and a closed conductor that can still act makes that claim
        rest on the caller's discipline rather than on construction."""
        if not self._started:
            raise ConductorNotReady("a closed conductor cannot read project state (fail closed)")
        return self._mcp.call("read_status", status="ACCEPTED")

    def publish_acceptance_packet(self, packet: dict[str, Any]) -> str:
        """Publish the operator acceptance packet as a CANDIDATE decision — the conductor
        proposes; only the operator accepts (invariant 1).

        Refuses once closed (U53): a corpse must not be able to publish. `run_cycle` already
        enforced this; the two MCP-touching methods beside it did not."""
        if not self._started:
            raise ConductorNotReady("a closed conductor cannot publish (fail closed)")
        import base64
        content = _json_bytes(packet)
        prov = {"author_node": self._context.node_id, "task_id": None,
                "ts": datetime.now(timezone.utc).isoformat(), "directive_version": "v2.4",
                "confidence": "high", "model": self._backend.model_name}
        pub = self._mcp.call("publish", kind="decision", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"),
                             provenance=prov, status="CANDIDATE")
        return pub["entry_id"]

    # -- succession surface ----------------------------------------------------
    def export_session_state(self) -> dict[str, Any]:
        # project truth lives in MCP; this is only enough to resume the loop position
        return {"node_id": self._context.node_id, "cycle": self._cycle,
                "loaded_files": list(self._loaded), "backend_calls": self._backend.calls,
                "conductor_file_refs": dict(self._file_refs)}

    def get_context_status(self) -> dict[str, Any]:
        return {"loaded": len(self._loaded), "expected": len(CONDUCTOR_FILE_ORDER),
                "cycles_run": self._cycle, "ready": len(self._loaded) == len(CONDUCTOR_FILE_ORDER)}

    def close(self) -> None:
        if self._governor is not None and self._context.subscription_ref:
            self._governor.release(self._context.subscription_ref, self._context.node_id)
        self._started = False


def _json_bytes(obj: dict[str, Any]) -> bytes:
    import json
    return json.dumps(obj, sort_keys=True).encode("utf-8")
