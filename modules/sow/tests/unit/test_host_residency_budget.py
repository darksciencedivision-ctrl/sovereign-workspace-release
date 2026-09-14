"""The HOST VRAM budget rule — `tools/live/enumerate_pane_picker._host_residency`.

17B promoted this function from a 16B display chip into an AUTHORIZATION gate (a local worker pane is
admitted or refused on the free VRAM it computes) and it shipped with no regression coverage at all.
Three gate-validator passes were spent on the arithmetic; this suite is what stops the fourth.

The defect class under test (gate-validator B1 → BLOCKING-1, 2026-07-26): the budget was DERIVED from
the resident set — first `total = sum(running)`, then `total = max(running, floor)`. Either way the
same models define the budget and then consume it, so free VRAM collapses to 0 whenever the running
total reaches the budget, and every local pane is refused for a reason that is an artifact of the
heuristic rather than a fact about the host. The rule now fixes the budget BEFORE reading residency,
and when the host's own residency contradicts it, says so instead of manufacturing capacity.

The daemon is injected (`_daemon_json`), never contacted: these are arithmetic facts, and a test that
depended on what the operator's Ollama happens to be serving would be the same non-determinism the
validator caught in the receipt.
"""
from __future__ import annotations

import pytest

from scheduler.residency_planner.residency_planner import ResidencyError
from tools.live import enumerate_pane_picker as epp

FLOOR = epp.STAND_IN_VRAM_BUDGET_MB
MB = 1024 * 1024


def _daemon(tags: dict[str, int], running: dict[str, int] | None = None):
    """A fake Ollama daemon: `tags` = model → on-disk MB, `running` = model → VRAM MB."""
    running = running or {}

    def fake(path: str, timeout: float = 3.0):
        if path == "/api/tags":
            return {"models": [{"name": n, "size": mb * MB} for n, mb in tags.items()]}
        if path == "/api/ps":
            return {"models": [{"name": n, "size_vram": mb * MB} for n, mb in running.items()]}
        return None

    return fake


@pytest.fixture(autouse=True)
def _no_operator_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator's real env must never leak into these assertions."""
    monkeypatch.delenv("SOW_VRAM_BUDGET_MB", raising=False)


def _residency(monkeypatch: pytest.MonkeyPatch, tags, running=None):
    monkeypatch.setattr(epp, "_daemon_json", _daemon(tags, running))
    return epp._host_residency()


def _fake_host(monkeypatch: pytest.MonkeyPatch, tags: dict[str, int], running=None) -> None:
    """Inject the daemon for the END-TO-END picker as well. `build_host_picker` reads residency
    through `_daemon_json` but enumerates the model list through `detect.ollama_model_records`, a
    separate HTTP read. Faking only the first left the list coming from whatever the operator's
    Ollama was serving, so the assertion held on his host and failed wherever no daemon ran."""
    monkeypatch.setattr(epp, "_daemon_json", _daemon(tags, running))
    monkeypatch.setattr(epp.detect, "ollama_model_records", lambda timeout=3.0: [
        {"name": n, "size": mb * MB, "details": {"parameter_size": n.rsplit(":", 1)[-1].upper()}}
        for n, mb in tags.items()])


def _budget(prov: list[dict]) -> dict:
    return next(row for row in prov if "vram_budget_mb" in row)


# -- the inversion itself -------------------------------------------------------------------------

def test_the_budget_is_never_derived_from_what_is_resident(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE regression, and it has to bite ABOVE the old floor: with a resident total below 12288 the
    old `max(running, floor)` and the constant are indistinguishable, so a fixture there proves
    nothing about the defect (validator R2). 13000MB resident is where `max()` took over."""
    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "20000")
    idle_planner, _r, idle_prov = _residency(monkeypatch, {"a:70b": 13000, "b:8b": 4000})
    busy_planner, _r2, busy_prov = _residency(
        monkeypatch, {"a:70b": 13000, "b:8b": 4000}, {"a:70b": 13000})
    assert _budget(idle_prov)["vram_budget_mb"] == 20000
    assert _budget(busy_prov)["vram_budget_mb"] == 20000     # NOT raised to 13000-and-consumed
    assert idle_planner is not None and busy_planner is not None
    assert idle_planner.free_vram_mb() == 20000
    # the resident model consumed exactly its own footprint out of an unchanged total. Under
    # `max(running, floor)` with the stand-in this was 0, and `b:8b` was unlaunchable.
    assert busy_planner.free_vram_mb() == 7000
    assert busy_planner.total_vram_mb() == 20000

    # …and the same property with no operator budget, where the stand-in constant is the total.
    monkeypatch.delenv("SOW_VRAM_BUDGET_MB")
    stand_in, _r3, stand_in_prov = _residency(monkeypatch, {"a:8b": 5000}, {"a:8b": 5000})
    assert _budget(stand_in_prov)["vram_budget_mb"] == FLOOR
    assert stand_in is not None and stand_in.free_vram_mb() == FLOOR - 5000


def test_a_busy_host_under_a_real_budget_still_has_the_free_vram_it_really_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validator's reproduction, byte for byte: a 24GB card serving 16GB. Under the old
    `max(running, floor)` rule total==used==16000 and free VRAM was structurally 0, so every local
    pane was refused with 8GB genuinely free."""
    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "24576")
    planner, _residency_map, prov = _residency(
        monkeypatch, {"a:70b": 10000, "b:32b": 6000, "qwen3:8b": 4983},
        {"a:70b": 10000, "b:32b": 6000})
    assert _budget(prov)["vram_budget_mb"] == 24576
    assert planner is not None
    assert planner.used_vram_mb() == 16000
    assert planner.free_vram_mb() == 8576          # not 0
    # …and the model the operator wanted fits in it
    assert planner.free_vram_mb() >= 4983


def test_the_operator_budget_is_used_verbatim_and_still_recorded_as_an_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "40000")
    _planner, _r, prov = _residency(monkeypatch, {"a:8b": 5000})
    budget = _budget(prov)
    assert budget["vram_budget_mb"] == 40000
    assert budget["established"] is True
    # nothing here queried the card, so no consumer may claim the fit was proven
    assert budget["estimate"] is True
    assert "SOW_VRAM_BUDGET_MB" in budget["budget_source"]


def test_the_stand_in_source_says_it_is_not_a_gpu_query(monkeypatch: pytest.MonkeyPatch) -> None:
    _planner, _r, prov = _residency(monkeypatch, {"a:8b": 5000})
    budget = _budget(prov)
    assert budget["estimate"] is True and budget["established"] is True
    assert "STAND-IN" in budget["budget_source"]
    assert "NOT a GPU query" in budget["budget_source"]


# -- falsification: the host contradicts the assumed budget ---------------------------------------

def test_a_budget_the_host_has_falsified_yields_no_planner_and_says_which_assumption_broke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """More is resident than the budget claims exists. That is not "no room" — it is evidence the
    budget is wrong, and gating on it would produce the structural refusal all over again."""
    planner, residency, prov = _residency(
        monkeypatch, {"big:70b": FLOOR + 4000}, {"big:70b": FLOOR + 4000})
    budget = _budget(prov)
    assert planner is None
    assert residency is None, "no planner means NO residency view, not an empty one"
    assert budget["vram_budget_mb"] is None
    assert budget["established"] is False
    assert "FALSIFIED" in budget["budget_source"]
    assert "big:70b" in budget["budget_source"]
    assert "SOW_VRAM_BUDGET_MB" in budget["budget_source"]   # the one-line fix is named


def test_an_operator_budget_smaller_than_a_resident_model_does_not_crash_the_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The crash regression the first fix introduced: `request_load` raised `ResidencyError` out of
    `_host_residency`, through `build_host_picker`, and the operator lost the WHOLE picker — frontier
    options included — because of one local model and a budget value they supplied themselves."""
    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "1")
    planner, residency, prov = _residency(
        monkeypatch, {"qwen2.5-coder:7b": 4528}, {"qwen2.5-coder:7b": 4528})
    assert planner is None and residency is None        # degraded, not raised
    assert _budget(prov)["established"] is False


def test_a_residency_fault_degrades_the_local_list_instead_of_escaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt-and-braces for the same class: whatever the planner raises during seeding, the
    enumeration returns a `None` planner with a recorded reason — it never propagates."""
    monkeypatch.setattr(epp, "_daemon_json", _daemon({"a:8b": 5000}, {"a:8b": 5000}))

    class _Exploding(epp.ResidencyPlanner):
        def request_load(self, name: str):                     # type: ignore[override]
            raise ResidencyError("induced seeding fault")

    monkeypatch.setattr(epp, "ResidencyPlanner", _Exploding)
    planner, residency, prov = epp._host_residency()
    assert planner is None and residency is None
    assert "induced seeding fault" in _budget(prov)["budget_source"]


# -- what occupies VRAM ---------------------------------------------------------------------------

def test_a_model_the_daemon_is_serving_but_does_not_list_still_occupies_vram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model in `/api/ps` but absent from `/api/tags` used to be skipped from registration, so the
    planner reported the whole budget free while the daemon was really serving it — an
    over-admission the authorization gate would then act on (validator MINOR-3)."""
    planner, residency, _prov = _residency(monkeypatch, {"qwen3:8b": 4983}, {"ghost:13b": 8000})
    assert planner is not None
    assert planner.used_vram_mb() == 8000
    assert planner.free_vram_mb() == FLOOR - 8000
    assert residency["ghost:13b"] == "resident"


def test_a_model_with_no_size_signal_is_skipped_from_residency_never_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(path: str, timeout: float = 3.0):
        if path == "/api/tags":
            return {"models": [{"name": "sized:8b", "size": 4000 * MB}, {"name": "unsized:8b"}]}
        if path == "/api/ps":
            return {"models": []}
        return None

    monkeypatch.setattr(epp, "_daemon_json", fake)
    planner, residency, prov = epp._host_residency()
    assert planner is not None
    assert "unsized:8b" not in residency and residency["sized:8b"] == "not_loaded"
    assert any(row.get("model") == "unsized:8b" and "skipped" in row.get("footprint_source", "")
               for row in prov)


def test_an_unreachable_daemon_reports_no_budget_and_no_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epp, "_daemon_json", lambda path, timeout=3.0: None)
    planner, residency, prov = epp._host_residency()
    budget = _budget(prov)
    assert planner is None and residency is None
    assert budget["vram_budget_mb"] is None and budget["established"] is False


# -- the operator's residency chips ---------------------------------------------------------------

def test_no_residency_view_renders_unknown_never_not_loaded() -> None:
    """gate-validator FAIL-1 / spec-audit MAJOR-2. On the degraded branch the picker used to receive
    an EMPTY residency map, and `pane_picker` defaults an absent name to `not_loaded` — so a model
    the daemon is actively serving was displayed to the operator as not in VRAM. That is a fabricated
    fact, not a missing one; the previous behaviour (a crash) was less wrong.

    `None` (no view) and an empty map (a planner reporting nothing resident) must render
    differently."""
    from control_plane.nodes.pane_picker import build_pane_picker
    from control_plane.profiles.live_authorization import LiveAuthorization
    from scheduler.residency_planner.residency_planner import NOT_LOADED, RESIDENT, UNKNOWN

    live = LiveAuthorization(authorized=False, providers=frozenset(), terminals_per_subscription=0,
                             register_row=None, source="(test)", reason="not authorized")

    def local_states(residency):
        picker = build_pane_picker(live, ollama_models=["qwen3:8b", "a:70b"], residency=residency)
        return sorted((o["model_slug"], o["residency"]) for o in picker["options"]
                      if o["locality"] == "local")

    assert local_states(None) == [("a:70b", UNKNOWN), ("qwen3:8b", UNKNOWN)]
    assert local_states({"a:70b": RESIDENT}) == [("a:70b", RESIDENT), ("qwen3:8b", NOT_LOADED)]
    assert local_states({}) == [("a:70b", NOT_LOADED), ("qwen3:8b", NOT_LOADED)]


def test_a_falsified_budget_does_not_tell_the_operator_a_running_model_is_unloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the daemon is serving `big:70b`, the budget is falsified, and the picker must not
    claim it is `not_loaded`."""
    from scheduler.residency_planner.residency_planner import NOT_LOADED, UNKNOWN

    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "1")
    _fake_host(monkeypatch, {"big:70b": 8000}, {"big:70b": 8000})
    picker, meta = epp.build_host_picker(op12_probes=epp.no_op12_probes())
    local = [o for o in picker["options"] if o["locality"] == "local"]
    assert local, "the host enumeration still offers the local models"
    assert all(o["residency"] == UNKNOWN for o in local), [o["residency"] for o in local]
    assert all(o["residency"] != NOT_LOADED for o in local)
    assert meta["residency_snapshot"] is None


# -- the public surface the emitter consumes ------------------------------------------------------

def test_host_residency_planner_carries_the_falsified_budget_to_the_authorization_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_authorize_local` repeats this `budget_source` in its refusal, so the operator is told the
    budget could not be established rather than that their model does not fit."""
    monkeypatch.setattr(epp, "_daemon_json", _daemon({"big:70b": FLOOR + 1}, {"big:70b": FLOOR + 1}))
    planner, budget = epp.host_residency_planner()
    assert planner is None
    assert budget["established"] is False and "FALSIFIED" in budget["budget_source"]


def test_the_whole_picker_survives_a_falsified_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through the shell's own `--emit-picker` source: a local-VRAM problem must never
    cost the operator the frontier options too."""
    monkeypatch.setenv("SOW_VRAM_BUDGET_MB", "1")
    _fake_host(monkeypatch, {"a:8b": 5000}, {"a:8b": 5000})
    picker, meta = epp.build_host_picker(op12_probes=epp.no_op12_probes())
    assert isinstance(picker.get("options"), list)
    assert meta["residency_snapshot"] is None
    assert any(o.get("locality") == "frontier" for o in picker["options"])
