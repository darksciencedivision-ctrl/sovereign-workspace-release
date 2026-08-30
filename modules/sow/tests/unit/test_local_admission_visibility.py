"""What the operator is SHOWN must agree with what the admission gate will DO.

spec-audit MAJOR-2 (2026-07-26), against the 17B `.ticket` fix commit: `pane_picker._local_options`
hard-coded `available: True` for every enumerated Ollama model, with the recorded rationale "no
credential gate for a detected local model". That was correct at 16B, when residency was a display
chip. 17B promoted the residency planner into an AUTHORIZATION gate, and there are now host states —
a budget the host's own residency falsifies, a residency seeding fault — in which
`worker_pane_spawn._authorize_local` refuses EVERY local pane while the picker still renders all of
them as launchable. Fails closed at the authorization, so it was never exploitable; it is the
"what the operator is shown is not what the gate enforced" divergence (invariant 27), and it is a
state the fix commit itself created.

Also covers the containment claim the enumeration makes about itself: "a residency fault must NEVER
escape this enumeration" was delivered by `except ResidencyError`, one exception class wide — a
daemon answering `/api/tags` with a JSON array took the whole picker down, frontier options
included, which is the BLOCKING-1b failure shape via `AttributeError` (spec-audit MINOR-5).

The daemon is injected, never contacted.
"""
from __future__ import annotations

import pytest

from control_plane.profiles.live_authorization import LiveAuthorization
from tools.live import enumerate_pane_picker as epp

MB = 1024 * 1024


def _records(tags):
    """The `/api/tags` ROWS the ceiling classifier reads (LOCAL-01 F-1).

    These fixtures have always meant "an 8B-class model of this footprint" — the names say `a:8b`.
    Now that `enumerate_pane_picker` classifies the enumeration against the operator's ceiling
    before rendering it, the fixture has to carry the two fields that decision needs
    (`details.parameter_size` and `capabilities`) or every fixture model would be refused for
    having an unreadable size. Nothing about what these tests assert changes: the models stay
    inside the ceiling, so the VRAM-admission behaviour under test is what still decides them."""
    return [{"name": n, "size": mb * MB, "capabilities": ["completion"],
             "details": {"parameter_size": "8B", "family": "test", "quantization_level": "Q4_K_M"}}
            for n, mb in sorted(tags.items())]


def _daemon(tags, running=None, tags_payload=None):
    running = running or {}

    def fake(path: str, timeout: float = 3.0):
        if path == "/api/tags":
            if tags_payload is not None:
                return tags_payload
            return {"models": [{"name": n, "size": mb * MB} for n, mb in tags.items()]}
        if path == "/api/ps":
            return {"models": [{"name": n, "size_vram": mb * MB} for n, mb in running.items()]}
        return None

    return fake


@pytest.fixture(autouse=True)
def _no_operator_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOW_VRAM_BUDGET_MB", raising=False)


def _live() -> LiveAuthorization:
    return LiveAuthorization(authorized=False, providers=frozenset(), terminals_per_subscription=0,
                             register_row="(test)", source="(test)", reason="not authorized")


def _host_picker(monkeypatch: pytest.MonkeyPatch, tags, running=None, tags_payload=None,
                 runtime="C:/bin/ollama.exe"):
    monkeypatch.setattr(epp, "_daemon_json", _daemon(tags, running, tags_payload))
    monkeypatch.setattr(epp, "load_live_authorization", _live)
    monkeypatch.setattr(epp.detect, "ollama_models", lambda: sorted(tags))
    monkeypatch.setattr(epp.detect, "ollama_model_records", lambda: _records(tags))
    monkeypatch.setattr(epp.detect, "claude_code_available", lambda: False)
    # the LAUNCHABLE binary, deliberately independent of the daemon the list came from
    monkeypatch.setattr(epp.detect, "ollama_executable", lambda: runtime)
    monkeypatch.setattr(epp, "probe_codex", lambda: type("P", (), {"present": False,
                                                                   "authenticated": False})())
    return epp.build_host_picker(op12_probes=epp.no_op12_probes())


def _local(picker: dict) -> list[dict]:
    return [o for o in picker["options"] if o["locality"] == "local"]


# -- the divergence itself -------------------------------------------------------------------------

def test_local_options_are_greyed_when_no_budget_can_be_established(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """16000MB resident against a 12288MB stand-in: the budget is FALSIFIED, no planner is built,
    and the authorization gate refuses every local pane. The picker must say so."""
    picker, meta = _host_picker(monkeypatch, {"a:8b": 8000, "b:8b": 8000},
                                running={"a:8b": 8000, "b:8b": 8000})
    local = _local(picker)
    assert local, "the enumeration still OFFERS the models — greyed, never hidden"
    assert all(o["available"] is False for o in local)
    assert all("budget could not be established" in o["unavailable_reason"] for o in local)
    # the reason carries the enumeration's own diagnosis, so the operator gets the one-line fix
    assert all("SOW_VRAM_BUDGET_MB" in o["unavailable_reason"] for o in local)
    assert meta["residency_budget"]["established"] is False
    assert picker["counts"]["available"] == sum(1 for o in picker["options"] if o["available"])


def test_local_options_stay_available_when_the_budget_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fail-closed rule must not refuse the normal case: a healthy budget offers every model."""
    picker, meta = _host_picker(monkeypatch, {"a:8b": 4000, "b:8b": 4000}, running={"a:8b": 4000})
    local = _local(picker)
    assert len(local) == 2
    assert all(o["available"] is True and o["unavailable_reason"] is None for o in local)
    assert meta["residency_budget"]["established"] is True


def test_a_greyed_local_option_is_refused_by_the_shared_selection_guard() -> None:
    """The two halves agree: what the picker greys, the spawn path refuses. Without this the
    greying would be cosmetic."""
    from node_runtime.supervisor.pane_node_spawn import PaneSelection, SpawnRefused
    from node_runtime.supervisor.pane_node_spawn import assert_selection_spawnable

    option = {"provider": "ollama_local", "adapter": "ollama_local", "locality": "local",
              "label": "a:8b", "model_slug": "a:8b", "roles": ["reasoning"], "verified": True,
              "available": False, "unavailable_reason": "no local pane can be authorized: this "
              "host's VRAM admission budget could not be established"}
    with pytest.raises(SpawnRefused):
        assert_selection_spawnable(PaneSelection(
            option=option, role="reasoning", mode="attended", node_id="worker-pane-2",
            permission_profile_id="pp-worker-reasoning", subscription_ref=None))


def test_local_admission_reason_is_none_only_when_no_host_wide_condition_refuses() -> None:
    ok = {"established": True, "budget_source": "x"}
    assert epp.local_admission_reason(ok, True) is None
    for bad in ({"established": False, "budget_source": "falsified"},
                {"established": None, "budget_source": "?"},
                {"established": 1, "budget_source": "truthy is not True"},
                {}):
        reason = epp.local_admission_reason(bad, True)
        assert reason is not None and "budget could not be established" in reason
    # …and the OTHER host-wide condition, which the first fix missed entirely (validator MAJOR-A)
    runtime_gone = epp.local_admission_reason(ok, False)
    assert runtime_gone is not None and "not on this host's PATH" in runtime_gone
    # both at once: the operator gets BOTH fixes, not whichever condition was checked first
    both = epp.local_admission_reason({"established": False, "budget_source": "falsified"}, False)
    assert "budget could not be established" in both and "not on this host's PATH" in both


def test_a_reachable_daemon_with_no_launchable_cli_greys_every_local_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE validator MAJOR-A regression. `detect.ollama_models()` reads the daemon over HTTP;
    `detect.ollama_executable()` is a PATH lookup. Two independent facts — and `_authorize_local`
    refuses on the second (`runtime_absent`) while the picker offered every model as launchable.
    The first fix covered only the budget condition, so the defect survived in a second state that
    `worker_pane_spawn`'s own refusal text already documented as reachable."""
    picker, meta = _host_picker(monkeypatch, {"a:8b": 4000}, running={}, runtime=None)
    assert meta["residency_budget"]["established"] is True   # the budget is FINE; the CLI is not
    assert meta["ollama_probe"]["runtime_on_path"] is False
    local = _local(picker)
    assert local and all(o["available"] is False for o in local)
    assert all("not on this host's PATH" in o["unavailable_reason"] for o in local)
    assert all("budget could not be established" not in o["unavailable_reason"] for o in local)


def test_the_greying_condition_matches_the_gate_in_both_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Greying WIDER than the gate is a usability regression; NARROWER is the original defect.
    Drive every host-wide state through the picker AND the real authorization and require the two
    to agree — the property, not one direction of it."""
    from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
    from node_runtime.supervisor.pane_node_spawn import PaneSelection, SpawnRefused
    from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
    from node_runtime.supervisor.worker_pane_spawn import WorkerPaneRefused, authorize_worker_pane

    cases = (("C:/bin/ollama.exe", {}),                    # healthy: offered AND authorized
             (None, {}),                                    # runtime absent: greyed AND refused
             ("C:/bin/ollama.exe", {"a:8b": 99999}))        # budget falsified: greyed AND refused
    for runtime, running in cases:
        picker, _meta = _host_picker(monkeypatch, {"a:8b": 4000}, running=running, runtime=runtime)
        option = next(o for o in _local(picker) if o["model_slug"] == "a:8b")
        planner, budget = epp.host_residency_planner()
        sel = PaneSelection(option=option, role="reasoning", mode="attended",
                            node_id="worker-pane-2", permission_profile_id="pp-worker-reasoning",
                            subscription_ref=None)
        try:
            session = authorize_worker_pane(
                sel, live_auth=_live(), governor=SubscriptionGovernor(),
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True, workspace="D:/repo",
                residency_planner=planner, residency_budget=budget, executable=runtime)
            session.teardown()
            authorized = True
        except (WorkerPaneRefused, SpawnRefused):
            authorized = False
        assert option["available"] is authorized, (
            f"picker availability and gate authorization disagree for "
            f"runtime={runtime!r} running={running!r}")


# -- the containment claim the enumeration makes about itself --------------------------------------

def test_a_malformed_tags_payload_degrades_the_local_list_instead_of_killing_the_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A daemon answering `/api/tags` with a JSON ARRAY used to raise `AttributeError` out of
    `_host_residency` → `build_host_picker` → `main()`: the operator lost the WHOLE picker,
    frontier options included, over one local model. `except ResidencyError` did not cover it —
    the claim is absolute, so the catch is too (spec-audit MINOR-5)."""
    picker, meta = _host_picker(monkeypatch, {}, tags_payload=[{"name": "a:8b"}])
    assert meta["residency_snapshot"] is None
    assert meta["residency_budget"]["established"] is False
    assert "not an object" in meta["residency_budget"]["budget_source"]
    # the picker SURVIVES: frontier options are still enumerated
    assert [o for o in picker["options"] if o["locality"] == "frontier"]


def test_a_seeding_fault_degrades_the_local_list_and_names_the_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any residency fault, not only `ResidencyError`."""
    class _Boom:
        def __init__(self, total): pass
        def register_model(self, *a): raise RuntimeError("planner exploded")

    monkeypatch.setattr(epp, "ResidencyPlanner", _Boom)
    picker, meta = _host_picker(monkeypatch, {"a:8b": 4000})
    assert meta["residency_snapshot"] is None
    assert "RuntimeError: planner exploded" in meta["residency_budget"]["budget_source"]
    assert all(o["available"] is False for o in _local(picker))
    # and a missing residency view is UNKNOWN, never the fabricated `not_loaded` (FAIL-1 regression)
    assert all(o["residency"] == "unknown" for o in _local(picker))


def test_the_emit_residency_mode_reports_the_budget_and_snapshot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """The contract the in-Electron self-check computes its VRAM budgets from — without it the
    check has to guess a constant and gets whichever gate branch the daemon's state produces."""
    import json

    monkeypatch.setattr(epp, "_daemon_json", _daemon({"a:8b": 4000}, {"a:8b": 4000}))
    monkeypatch.setattr(epp, "load_live_authorization", _live)
    monkeypatch.setattr(epp.detect, "ollama_models", lambda: ["a:8b"])
    monkeypatch.setattr(epp.detect, "ollama_model_records", lambda: _records({"a:8b": 4000}))
    monkeypatch.setattr(epp.detect, "claude_code_available", lambda: False)
    monkeypatch.setattr(epp, "probe_codex", lambda: type("P", (), {"present": False,
                                                                   "authenticated": False})())
    assert epp.main(op12_probes=epp.no_op12_probes(), argv=["--emit-residency"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == epp.HOST_RESIDENCY_SCHEMA
    assert payload["budget"]["established"] is True
    assert payload["snapshot"]["used_vram_mb"] == 4000
    assert any(m["model"] == "a:8b" and m["footprint_mb"] == 4000
               for m in payload["snapshot"]["models"])
