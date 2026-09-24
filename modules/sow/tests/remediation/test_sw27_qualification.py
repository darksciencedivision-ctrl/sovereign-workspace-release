"""SW-27: end-to-end performance qualification - profile schema, envelope, and the reject gate.

The finding: nothing qualified the declared large context/output, DEEP, concurrency, llama.cpp or cold
vs warm behaviour through the product; the only benchmark was one direct Ollama call. SW-27 ships:
the supported-profile schema (qualification/profiles.json), a harness that measures a RUNNING product
through its own HTTP API, `derive` (results -> this machine's envelope), `apply` (install it and lower
runtime limits DOWNWARD ONLY to fit), and the gate: a configuration above a measured envelope is
REJECTED (jobs refused, health degraded); an unmeasured dimension is UNQUALIFIED (reported, never
used to refuse). Failure injection: malformed profiles/envelopes, an over-envelope configuration, an
unmeasured ladder step, a failed cancellation, a runtime override that tries to RAISE a limit.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOV_ROOT = RELEASE_ROOT / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

import system_manifest as SM  # noqa: E402
from sovereign_product import manifest_overrides as MO  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import qualification as Q  # noqa: E402
from sovereign_product import qualification_harness as H  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_EVIDENCE_DIR", "SOVEREIGN_DB_PATH", "SOVEREIGN_ROOT")
SHIPPED_PROFILES = json.loads((SOV_ROOT / "qualification" / "profiles.json").read_text(
    encoding="utf-8"))


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    local = tmp_path / "LocalAppData"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "install root"
    (root / "qualification").mkdir(parents=True)
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": "external"}),
                                            encoding="utf-8")
    (root / "SYSTEM_MANIFEST.json").write_bytes((SOV_ROOT / "SYSTEM_MANIFEST.json").read_bytes())
    (root / "qualification" / "profiles.json").write_text(json.dumps(SHIPPED_PROFILES),
                                                          encoding="utf-8")
    return root


def _run(scenario, status="completed", latency=10.0, tokens=100, **extra):
    return {"scenario": scenario, "status": status, "latency_seconds": latency,
            "tokens": tokens, **extra}


def _results(**overrides):
    runs = []
    for step, latency in ((2048, 20.0), (8192, 60.0), (16384, 900.0)):  # 16384 blows the SLO
        runs += [_run("context", latency=latency, context_tokens=step) for _ in range(3)]
    runs += [_run("concurrency", latency=30.0, concurrency=1) for _ in range(3)]
    runs += [_run("concurrency", latency=45.0, concurrency=2) for _ in range(2)]
    runs += [_run("quick_cold", latency=80.0, cold=True)]
    runs += [_run("quick_warm", latency=15.0, tokens=400) for _ in range(3)]
    runs += [_run("cancel", status="cancelled", cancel_latency_seconds=2.0)]
    runs += [_run("deep", latency=1200.0, tokens=6000)]
    doc = {"schema": Q.RESULTS_SCHEMA, "profile": "ollama-production-slate",
           "finished_utc": "2026-09-24T00:00:00Z", "hardware": {"gpu": {"name": "test"}},
           "runtime": {"num_ctx": 40960}, "resources": {"peak_vram_mib": 7000}, "runs": runs}
    doc.update(overrides)
    return doc


# --- profiles -------------------------------------------------------------------------------------

def test_sw27_shipped_profiles_validate_and_cover_both_backends():
    doc = Q.load_profiles(SOV_ROOT)
    backends = {p["backend"] for p in doc["profiles"]}
    assert backends == {"ollama", "llama.cpp"}
    assert Q.find_profile(doc, "llamacpp", "qwen3:14b")["id"] == "llamacpp-production-slate"


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d.update(schema="v0"), "schema"),
    (lambda d: d["slo"].update(max_failure_rate=1.5), "below 1"),
    (lambda d: d["profiles"][0]["ladder"].update(context_tokens=[8192, 2048]), "ascending"),
    (lambda d: d["profiles"].append(copy.deepcopy(d["profiles"][0])), "duplicate"),
    (lambda d: d["profiles"][0]["declared"].update(context_tokens=0), "positive integer"),
])
def test_sw27_malformed_profiles_fail_closed(mutate, match):
    doc = copy.deepcopy(SHIPPED_PROFILES)
    mutate(doc)
    with pytest.raises(Q.QualificationError, match=match):
        Q.validate_profiles(doc)


# --- envelope derivation --------------------------------------------------------------------------

def test_sw27_envelope_is_the_largest_contiguous_ladder_step_meeting_the_slo():
    envelope = Q.derive_envelope(_results(), SHIPPED_PROFILES)
    # The enforced window is the num_ctx measured; the passing prompt size is reported apart.
    assert envelope["limits"] == {"context_tokens": 40960, "concurrent_jobs": 2}
    assert envelope["qualified_prompt_tokens"] == 8192
    assert envelope["scenarios"]["context_16384"]["latency_p95_seconds"] == 900.0
    assert envelope["scenarios"]["context_32768"]["runs"] == 0  # never extrapolated
    assert envelope["qualified_workflows"] == {"QUICK": True, "DEEP": True, "cancellation": True}
    assert envelope["observed_max_task_tokens"] == 6000
    assert envelope["scenarios"]["quick_cold"]["latency_p50_seconds"] == 80.0


def test_sw27_failures_above_the_slo_rate_disqualify_a_step():
    results = _results()
    for run in results["runs"]:
        if run["scenario"] == "context" and run["context_tokens"] == 2048:
            run["status"] = "failed"
    envelope = Q.derive_envelope(results, SHIPPED_PROFILES)
    assert envelope["limits"]["context_tokens"] == 0 and envelope["qualified_prompt_tokens"] == 0


def test_sw27_results_without_the_measured_window_are_refused():
    results = _results()
    results["runtime"] = {}
    with pytest.raises(Q.QualificationError, match="num_ctx"):
        Q.derive_envelope(results, SHIPPED_PROFILES)


def test_sw27_a_cancel_that_does_not_cancel_is_not_qualified():
    results = _results()
    for run in results["runs"]:
        if run["scenario"] == "cancel":
            run["status"] = "completed"
    assert Q.derive_envelope(results, SHIPPED_PROFILES)["qualified_workflows"]["cancellation"] is False


def test_sw27_results_for_an_unknown_profile_are_refused():
    with pytest.raises(Q.QualificationError, match="unknown profile"):
        Q.derive_envelope(_results(profile="nope"), SHIPPED_PROFILES)


# --- the gate -------------------------------------------------------------------------------------

def _evaluate(root, **over):
    config = dict(backend="ollama", primary_model="qwen3:14b", num_ctx=8192,
                  num_predict=4096, workers=1)
    config.update(over)
    return Q.evaluate(root, **config)


def test_sw27_unmeasured_profile_is_unqualified_not_refused(clean_env, tmp_path):
    root = _install(tmp_path)
    verdict = _evaluate(root)
    assert verdict["verdict"] == Q.UNQUALIFIED and verdict["profile"] == "ollama-production-slate"
    assert _evaluate(root, primary_model="unknown:1b")["verdict"] == Q.UNQUALIFIED


def test_sw27_configuration_above_the_measured_envelope_is_rejected(clean_env, tmp_path):
    root = _install(tmp_path)
    Q.write_envelope(root, Q.derive_envelope(_results(), SHIPPED_PROFILES))
    assert _evaluate(root)["verdict"] == Q.QUALIFIED
    assert _evaluate(root, num_ctx=40960)["verdict"] == Q.QUALIFIED  # exactly what was measured
    over_ctx = _evaluate(root, num_ctx=65536)
    assert over_ctx["verdict"] == Q.REJECTED and "65536" in over_ctx["reasons"][0]
    assert _evaluate(root, workers=3)["verdict"] == Q.REJECTED
    output = _evaluate(root, num_predict=32000)
    assert output["verdict"] == Q.QUALIFIED and output["unqualified"] == ["max_output_tokens"]


def test_sw27_corrupt_envelope_fails_closed(clean_env, tmp_path):
    root = _install(tmp_path)
    path = Q.envelope_path(root)
    path.parent.mkdir(parents=True)
    path.write_text('{"schema": "wrong"}', encoding="utf-8")
    assert _evaluate(root)["verdict"] == Q.REJECTED


def test_sw27_apply_installs_envelope_and_lowers_limits_downward_only(clean_env, tmp_path):
    root = _install(tmp_path)
    envelope = Q.derive_envelope(_results(), SHIPPED_PROFILES)
    shipped_before = (root / "SYSTEM_MANIFEST.json").read_bytes()
    applied = Q.apply_envelope(root, envelope)
    assert applied["effective_runtime"] == {"CONTEXT_WINDOW": 40960, "MAX_OUTPUT_TOKENS": 20480}
    assert (root / "SYSTEM_MANIFEST.json").read_bytes() == shipped_before
    assert Q.envelope_path(root).is_file()
    effective = SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")
    assert effective["RUNTIME"]["CONTEXT_WINDOW"] == 40960


def test_sw27_apply_refuses_a_profile_that_failed_below_the_product_minimum(clean_env, tmp_path):
    root = _install(tmp_path)
    envelope = Q.derive_envelope(_results(), SHIPPED_PROFILES)
    envelope["limits"]["context_tokens"] = 2048
    with pytest.raises(Q.QualificationError, match="below the product minimum"):
        Q.apply_envelope(root, envelope)
    assert not Q.envelope_path(root).exists()


@pytest.mark.parametrize("runtime", [
    {"CONTEXT_WINDOW": 262144},            # raising a limit
    {"OLLAMA_BASE_URL": 1},                # not lowerable
    {"CONTEXT_WINDOW": "8192"},            # wrong type
])
def test_sw27_runtime_overrides_can_only_lower_limits(clean_env, tmp_path, runtime):
    root = _install(tmp_path)
    path = MO.overrides_path(root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "RUNTIME": runtime}), encoding="utf-8")
    with pytest.raises(SM.ManifestConfigError):
        SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")


def test_sw27_product_refuses_jobs_on_a_rejected_configuration():
    from sovereign_product.router import Route
    from sovereign_product.server import ProductService

    fake = SimpleNamespace(
        store=SimpleNamespace(get_session=lambda *a, **k: {}),
        route=lambda text, override: SimpleNamespace(route=Route.QUICK),
        qualification=lambda: {"verdict": "rejected", "reasons": ["context window 40960 "
                                                                  "exceeds the measured envelope"]},
    )
    payload, status = ProductService.submit(fake, "s1", "hello")
    assert status == 409 and "measured qualification envelope" in payload["error"]


def test_sw27_status_route_stays_available_when_rejected():
    from sovereign_product.router import Route
    from sovereign_product.server import ProductService

    def boom():
        raise AssertionError("STATUS must not be gated")

    fake = SimpleNamespace(
        store=SimpleNamespace(get_session=lambda *a, **k: {}),
        route=lambda text, override: SimpleNamespace(route=Route.STATUS),
        qualification=boom,
        active_job=lambda sid: {"job_id": "j"},
        public_job=lambda job: {"job_id": job["job_id"]},
    )
    _payload, status = ProductService.submit(fake, "s1", "status?")
    assert status == 409  # the session's active-job refusal, not the qualification gate


# --- harness mechanics ----------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, statuses, submit_status=202):
        self.statuses = list(statuses)
        self.submit_status = submit_status
        self.cancelled = []

    def new_session(self, title):
        return "s"

    def submit(self, session, text, route):
        if self.submit_status >= 400:
            return self.submit_status, {"error": "refused"}
        return self.submit_status, {"job_id": "j1", "status": "queued"}

    def job(self, job_id):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"status": status, "metrics": {"tokens": 321, "elapsed_seconds": 4.0}}

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return {}


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def test_sw27_harness_records_a_completed_job_end_to_end():
    clock = _Clock()
    record = H.run_job(_FakeClient(["running", "running", "completed"]), "hi", "QUICK",
                       timeout=60, clock=clock, sleep=clock.sleep, poll=1.0)
    assert record["status"] == "completed" and record["tokens"] == 321
    assert record["latency_seconds"] == 3.0


def test_sw27_harness_records_refusals_timeouts_and_cancellation():
    clock = _Clock()
    refused = H.run_job(_FakeClient(["completed"], submit_status=409), "hi", "QUICK",
                        timeout=60, clock=clock, sleep=clock.sleep)
    assert refused["status"] == "failed" and refused["http_status"] == 409
    client = _FakeClient(["running"])
    timed_out = H.run_job(client, "hi", "QUICK", timeout=5, clock=clock, sleep=clock.sleep,
                          poll=1.0)
    assert timed_out["status"] == "timeout" and client.cancelled == ["j1"]
    client = _FakeClient(["running"] * 4 + ["cancelled"])
    cancelled = H.run_job(client, "hi", "QUICK", timeout=60, cancel_after=2.0, clock=clock,
                          sleep=clock.sleep, poll=1.0)
    assert cancelled["status"] == "cancelled" and cancelled["cancel_latency_seconds"] >= 0
    assert client.cancelled == ["j1"]


def test_sw27_context_prompt_targets_the_requested_size_within_input_limits():
    prompt = H.context_prompt(26214)
    assert abs(len(prompt) - 26214 * H.CHARS_PER_TOKEN) < 200
    from sovereign_product.server import MAX_INPUT_CHARACTERS
    assert len(H.context_prompt(int(32768 * 0.8))) <= MAX_INPUT_CHARACTERS


def test_sw27_harness_reads_every_model_from_the_products_deep_slate():
    # The real /v1/health shape: nested members and generation constraints, not a flat mapping.
    slate = {"critic": "qwen3:8b", "synthesizer": "qwen2.5:14b-instruct", "verifier": "qwen3:32b",
             "members": [{"model": "qwen3:14b", "role_id": "a", "think": False},
                         {"model": "qwen2.5:14b-instruct", "role_id": "b", "think": None}],
             "generation_constraints": {"think_by_model": {"qwen3:14b": False}}}
    assert H.slate_models(slate) == {"qwen3:8b", "qwen2.5:14b-instruct", "qwen3:32b", "qwen3:14b"}
    assert H.slate_models(None) == set()


def test_sw27_report_is_rendered_from_the_results_and_envelope():
    results = _results(results_file="r.json", started_utc="2026-09-24T00:00:00Z", repetitions=3)
    results["runs"].append(_run("context", status="failed", latency=5.0, context_tokens=32768,
                                error="model out of memory"))
    envelope = Q.derive_envelope(results, SHIPPED_PROFILES)
    text = Q.render_report(envelope, results)
    assert "Qualified context window (the num_ctx measured): **40960 tokens**" in text
    assert "Largest prompt meeting the SLOs through the product: **~8192 tokens**" in text
    assert "| context_16384 | 3 | 3 |" in text
    assert "DEEP=yes" in text and "cancellation=yes" in text
    assert "model out of memory" in text
    assert "`r.json`" in text


def test_sw27_deep_options_fit_every_model_in_the_slate():
    # Found by the first real qualification run: DEEP sent the primary's 40960 window to
    # qwen2.5:14b-instruct (cap 32768) and every DEEP run failed its capability check.
    from sovereign_product.server import ProductService

    manifest = json.loads((SOV_ROOT / "SYSTEM_MANIFEST.json").read_text(encoding="utf-8-sig"))
    quick = ProductService._runtime_model_options(manifest)
    deep = ProductService._runtime_model_options(
        manifest, ("qwen3:14b", "qwen2.5:14b-instruct", "qwen3:8b", "qwen3:32b"))
    from sovereign_product.runtime_registry import context_resolution
    caps = [context_resolution(m)["effective_cap"] for m in
            ("qwen3:14b", "qwen2.5:14b-instruct", "qwen3:8b", "qwen3:32b")]
    assert quick["num_ctx"] == context_resolution("qwen3:14b")["effective_cap"]
    assert deep["num_ctx"] == min(caps) and deep["num_predict"] < deep["num_ctx"]
