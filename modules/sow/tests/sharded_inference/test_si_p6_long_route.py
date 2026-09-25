"""Sharded inference P6: the LONG route - config, planned serving, model port, executor, product lane.

LONG is chosen only explicitly. The message is the objective; material after a `---` line is
sharded map/reduce, no material means agentic plan steps; `@input: <file>` reads ONLY from the state
home's long_inputs inbox. The supervisor serves configured LONG models with the planner's GPU/RAM
split. LONG runs on its own worker lane so hours-long runs never block QUICK/DEEP. Failure
injection: non-llama backend, bad config, inbox escapes, oversized input, unplannable model, resume
after a product restart.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import memory_planner as MP  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product.router import Route, route_query  # noqa: E402
from sovereign_product.runtime_registry import (  # noqa: E402
    Artifact, ModelIdentity, RuntimeRegistry, ServingProfile)
from sovereign_product import gguf_meta as G  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_ROOT")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    return tmp_path / "LocalAppData"


def _root(tmp_path: Path, config: dict | None = None) -> Path:
    root = tmp_path / "install"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": "external"}),
                                            encoding="utf-8")
    shipped = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    (root / LW.CONFIG_FILE).write_text(json.dumps(config or shipped), encoding="utf-8")
    return root


def _small_root(tmp_path: Path) -> Path:
    """The shipped config with every model at an 8k window (as FakeLlama serves by default), so a
    few KB of material already needs several shards."""
    doc = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    for entry in doc["models"]:
        entry["context"] = 8192
        if entry.get("thinking") == "on":
            entry["reasoning_tokens"] = 2048
    return _root(tmp_path, doc)


# --- routing --------------------------------------------------------------------------------------

def test_si_p6_long_is_never_chosen_automatically_only_explicitly():
    auto = route_query("summarize this very long document about warnings " * 50)
    assert auto.route is not Route.LONG
    assert route_query("anything", Route.LONG).route is Route.LONG
    assert route_query("route: LONG analyse the logs").route is Route.LONG


# --- config ---------------------------------------------------------------------------------------

def test_si_p6_shipped_config_is_valid_and_matches_the_operator_decisions():
    config = LW.load_config(SOV_ROOT)
    assert config.ram_budget_gib == 32
    assert {m.model for m in config.models} == {"qwen3.8:27b", "qwen3:30b-a3b"}
    assert config.model().model == "qwen3.8:27b"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema=2),
    lambda d: d.update(models=[]),
    lambda d: d["models"][0].update(context=1024),
    lambda d: d.update(ram_budget_gib=0),
    lambda d: d.update(default_model="not-configured"),
    lambda d: d["models"][0].update(thinking="maybe"),
])
def test_si_p6_bad_config_fails_closed(tmp_path, mutate):
    doc = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    mutate(doc)
    root = tmp_path / "r"
    root.mkdir()
    (root / LW.CONFIG_FILE).write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(LW.LongWorkloadError):
        LW.load_config(root)


# --- planned serving ------------------------------------------------------------------------------

def _registry_with(model_id: str) -> RuntimeRegistry:
    registry = RuntimeRegistry()
    registry.add_artifact(Artifact(identity="sha256:x", paths=("m.gguf",), sizes=(1,),
                                   format="gguf", declared_hash=None, verified_hash=None,
                                   provenance="test"))
    registry.add_model(ModelIdentity(model_id=model_id, aliases=(model_id,),
                                     artifact_ids=("sha256:x",), architecture="qwen35"))
    registry.add_profile(ServingProfile(profile_id="old", model_id=model_id, engine_id="old",
                                        model_path="m.gguf", embeddings=False,
                                        context_configured=8192, context_tested=None,
                                        n_gpu_layers=0))
    return registry


def _fake_gguf(path):
    tensors = [G.TensorInfo(f"blk.{i}.w", i * 300 * MP.MIB, 300 * MP.MIB, i, False)
               for i in range(40)]
    meta = {"general.architecture": "qwen35", "qwen35.block_count": 40,
            "qwen35.context_length": 262144, "qwen35.attention.head_count_kv": 4,
            "qwen35.attention.head_count": 24, "qwen35.embedding_length": 5120,
            "qwen35.attention.key_length": 256, "qwen35.full_attention_interval": 4}
    return G.GGUFModel(path=path, file_size=40 * 300 * MP.MIB, version=3, metadata=meta,
                       tensors=tensors)


def test_si_p6_supervisor_serves_long_models_with_the_planned_split():
    registry = _registry_with("qwen3.8:27b")
    config = LW.load_config(SOV_ROOT)
    report = LW.apply_hybrid_plans(registry, config, vram_bytes=int(7.17 * MP.GIB),
                                   reader=_fake_gguf)
    assert report["qwen3.8:27b"]["applied"] is True
    assert report["qwen3:30b-a3b"] == {"applied": False, "reason": "model not installed"}
    (profile,) = [p for p in registry.profiles.values() if p.model_id == "qwen3.8:27b"]
    assert profile.profile_id != "old" and profile.context_configured == 131072
    assert profile.cache_type == "q8_0" and profile.fit == "off" and profile.n_gpu_layers > 0


def test_si_p6_an_unplannable_model_keeps_its_profile_and_says_why():
    registry = _registry_with("qwen3.8:27b")
    config = LW.load_config(SOV_ROOT)
    tiny_budget = LW.LongConfig(**{**config.__dict__, "ram_budget_gib": 4})
    report = LW.apply_hybrid_plans(registry, tiny_budget, vram_bytes=int(7.17 * MP.GIB),
                                   reader=_fake_gguf)
    assert report["qwen3.8:27b"]["applied"] is False
    assert "inference budget" in report["qwen3.8:27b"]["reason"]
    assert "old" in registry.profiles
    unknown = LW.apply_hybrid_plans(registry, config, vram_bytes=None, reader=_fake_gguf)
    assert all(not r["applied"] for r in unknown.values())


# --- request parsing ------------------------------------------------------------------------------

def test_si_p6_request_forms(clean_env, tmp_path):
    root = _root(tmp_path)
    assert LW.parse_request("Plan the migration.", root) == ("Plan the migration.", None)
    objective, material = LW.parse_request("Find the errors.\n---\nline 1\nline 2", root)
    assert objective == "Find the errors." and material == "line 1\nline 2"
    inbox = P.resolve_state_home(root) / LW.INBOX_DIRNAME
    inbox.mkdir(parents=True)
    (inbox / "big log.txt").write_text("from the inbox", encoding="utf-8")
    assert LW.parse_request("Read it.\n---\n@input: big log.txt", root)[1] == "from the inbox"


@pytest.mark.parametrize("text", [
    "\n---\nmaterial only",
    "Objective.\n---\n   ",
    "Objective.\n---\n@input: missing.txt",
    "Objective.\n---\n@input: ../escape.txt",
])
def test_si_p6_bad_requests_are_refused(clean_env, tmp_path, text):
    root = _root(tmp_path)
    (tmp_path / "escape.txt").write_text("x", encoding="utf-8")
    with pytest.raises(LW.LongWorkloadError):
        LW.parse_request(text, root)


def test_si_p6_oversized_inbox_input_is_refused(clean_env, tmp_path, monkeypatch):
    root = _root(tmp_path)
    inbox = P.resolve_state_home(root) / LW.INBOX_DIRNAME
    inbox.mkdir(parents=True)
    (inbox / "a.txt").write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(LW, "MAX_INPUT_BYTES", 10)
    with pytest.raises(LW.LongWorkloadError, match="exceeds"):
        LW.parse_request("O.\n---\n@input: a.txt", root)


# --- the executor with a fake llama.cpp client ----------------------------------------------------

class FakeLlama:
    def __init__(self, context=8192):
        self.context = context
        self.chats = []

    def native_context_length(self, model):
        return self.context

    def count_text_tokens(self, model, text):
        return len(text) // 4

    def chat(self, *, model, messages, options, think, cancel_requested):
        self.chats.append({"model": model, "messages": messages, "options": options,
                           "think": think})
        prompt = messages[-1]["content"]
        if "INSTRUCTION (plan)" in prompt:
            result = json.dumps(["gather facts", "decide"])
        elif "INSTRUCTION (review)" in prompt:
            result = "[]"
        else:
            result = "done: " + prompt.split("\n", 2)[1][:40]
        return SimpleNamespace(text=json.dumps({"result": result, "ledger_update": {}}))


def _executor(root, client):
    return LW.LongWorkloadExecutor(root=root, evidence_dir=root / "ev", client=client,
                                   config=LW.load_config(root))


def test_si_p6_long_requires_the_llama_cpp_backend(clean_env, tmp_path):
    root = _root(tmp_path)
    with pytest.raises(LW.LongWorkloadError, match="llama.cpp backend"):
        _executor(root, SimpleNamespace(chat=lambda **k: None))


def test_si_p6_material_runs_map_reduce_fresh_sessions(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = FakeLlama(context=8192)
    material = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(40))
    progress = []
    result = _executor(root, client).run("job-1", f"Count entries.\n---\n{material}",
                                         cancel_requested=lambda: False,
                                         progress_callback=progress.append)
    assert result["status"] == "completed" and result["answer"].startswith("done")
    assert result["telemetry"]["mode"] == "input_shards" and result["telemetry"]["shards"] > 3
    assert all(len(c["messages"]) == 2 for c in client.chats)  # system + one user: fresh
    assert all(c["options"]["num_ctx"] == 8192 and c["think"] is False for c in client.chats)
    assert any("percent" in p for p in progress)


def test_si_p6_objective_only_runs_plan_steps(clean_env, tmp_path):
    root = _small_root(tmp_path)
    result = _executor(root, FakeLlama()).run("job-2", "Draft a rollout plan.",
                                              cancel_requested=lambda: False,
                                              progress_callback=lambda p: None)
    assert result["status"] == "completed" and result["telemetry"]["mode"] == "plan_steps"


def test_si_p6_a_restarted_product_resumes_the_same_run(clean_env, tmp_path):
    root = _small_root(tmp_path)
    material = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(40))
    stop = {"now": False}
    client = FakeLlama()
    real_chat = client.chat

    def chat_then_stop(**kw):
        stop["now"] = True
        return real_chat(**kw)

    client.chat = chat_then_stop
    first = _executor(root, client).run("job-3", f"Count.\n---\n{material}",
                                        cancel_requested=lambda: stop["now"],
                                        progress_callback=lambda p: None)
    assert first["status"] == "cancelled"
    done_before = first["telemetry"]["completed"]
    again = FakeLlama()
    second = _executor(root, again).run("job-3", f"Count.\n---\n{material}",
                                        cancel_requested=lambda: False,
                                        progress_callback=lambda p: None)
    assert second["status"] == "completed"
    assert len(again.chats) == second["telemetry"]["model_calls"] - done_before


# --- the product lane -----------------------------------------------------------------------------

def test_si_p6_long_jobs_get_their_own_lane():
    from sovereign_product.server import ProductService

    fake = SimpleNamespace(
        store=SimpleNamespace(get_job=lambda job_id: {"route": "LONG" if job_id == "L"
                                                      else "QUICK"}),
        _queue_lock=threading.RLock(), _enqueued=set(), _queue=queue.Queue(),
        _long_queue=queue.Queue())
    ProductService._enqueue(fake, "L")
    ProductService._enqueue(fake, "Q")
    assert fake._long_queue.get_nowait() == "L" and fake._queue.get_nowait() == "Q"
    assert fake._long_queue.empty() and fake._queue.empty()


def test_si_p6_long_route_readiness_reflects_the_backend(clean_env, tmp_path):
    from sovereign_product.server import ProductService

    root = _root(tmp_path)
    paths = P.resolve_product_paths(root, create=True)
    ollama_like = SimpleNamespace(root=root, paths=paths, model_client=SimpleNamespace(),
                                  _long_executor=lambda: ProductService._long_executor(ollama_like))
    assert ProductService.long_route_ready(ollama_like) is False
    llama_like = SimpleNamespace(root=root, paths=paths, model_client=FakeLlama(),
                                 _long_executor=lambda: ProductService._long_executor(llama_like))
    assert ProductService.long_route_ready(llama_like) is True


def test_si_p6_health_counts_the_long_lane_separately_from_the_workers():
    # Found live: the long-lane thread made len(_workers) != worker_count, so /v1/health reported
    # "durable job workers are not ready" and the shell would have shown the product DEGRADED.
    from sovereign_product.server import LONG_WORKER_NAME, ProductService

    def thread(name):
        return SimpleNamespace(name=name, is_alive=lambda: True)

    ready = SimpleNamespace(worker_count=1,
                            _workers=[thread("sovereign-worker-1"), thread(LONG_WORKER_NAME)])
    assert ProductService.workers_ready(ready) is True
    no_lane = SimpleNamespace(worker_count=1, _workers=[thread("sovereign-worker-1")])
    assert ProductService.workers_ready(no_lane) is False
    dead = SimpleNamespace(worker_count=1, _workers=[
        thread("sovereign-worker-1"),
        SimpleNamespace(name=LONG_WORKER_NAME, is_alive=lambda: False)])
    assert ProductService.workers_ready(dead) is False


# --- choosing the LONG model ----------------------------------------------------------------------

def test_si_p6_model_directive_picks_a_configured_model(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = FakeLlama(context=8192)
    material = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(10))
    result = _executor(root, client).run(
        "job-m1", f"@model: qwen3:30b-a3b\nCount entries.\n---\n{material}",
        cancel_requested=lambda: False, progress_callback=lambda p: None)
    assert result["status"] == "completed" and result["model"] == "qwen3:30b-a3b"
    assert {c["model"] for c in client.chats} == {"qwen3:30b-a3b"}
    assert all("@model" not in c["messages"][-1]["content"] for c in client.chats)


def test_si_p6_without_a_directive_the_default_model_runs(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = FakeLlama()
    result = _executor(root, client).run("job-m2", "Draft a rollout plan.",
                                         cancel_requested=lambda: False,
                                         progress_callback=lambda p: None)
    assert result["model"] == LW.load_config(root).default_model
    assert {c["model"] for c in client.chats} == {result["model"]}


@pytest.mark.parametrize("text,match", [
    ("@model: qwen3:14b\nDraft a plan.", "not configured for the LONG route"),
    ("@model: ../../etc\nDraft a plan.", "not configured for the LONG route"),
    ("@model:\nDraft a plan.", "needs a model name"),
])
def test_si_p6_model_directive_refuses_unconfigured_or_empty(clean_env, tmp_path, text, match):
    root = _root(tmp_path)
    client = FakeLlama()
    with pytest.raises(LW.LongWorkloadError, match=match):
        _executor(root, client).run("job-m3", text, cancel_requested=lambda: False,
                                    progress_callback=lambda p: None)
    assert client.chats == []


def test_si_p6_model_directive_only_counts_on_the_first_line():
    assert LW.split_model_directive("Plan it.\n@model: qwen3:30b-a3b") == (
        None, "Plan it.\n@model: qwen3:30b-a3b")
    assert LW.split_model_directive("  @model: qwen3:30b-a3b  \r\nPlan it.") == (
        "qwen3:30b-a3b", "Plan it.")


# --- progress through the product's monotonic filter ----------------------------------------------

def test_si_p6_growing_task_lists_keep_n_of_n_progress_flowing(clean_env, tmp_path):
    """Live: after the plan (1 of 1 -> 99%) every later update regressed and the product dropped it."""
    from sovereign_product.server import ProductService

    stored = []
    store = SimpleNamespace(get_job=lambda job_id: {"job_id": job_id, "status": "running"},
                            update_job_progress=lambda job_id, safe: stored.append(dict(safe)))
    product_callback = ProductService._progress_callback(SimpleNamespace(store=store), "job-p")
    sent = []

    def executor_progress(update):
        sent.append(dict(update))
        product_callback(update)

    root = _small_root(tmp_path)
    result = _executor(root, FakeLlama()).run("job-p", "Draft a rollout plan.",
                                              cancel_requested=lambda: False,
                                              progress_callback=executor_progress)
    assert result["status"] == "completed"
    counted = [p for p in sent if "total" in p]
    assert len(counted) > 4 and len(stored) == len(counted), "the product dropped progress updates"
    assert [(p["current"], p["total"]) for p in stored] == [(p["current"], p["total"])
                                                            for p in counted]
    assert stored[-1]["total"] == result["telemetry"]["shards"] > 1
    percents = [p["percent"] for p in stored]
    assert percents == sorted(percents) and max(percents) <= 99
    assert stored[1]["percent"] < 90, "finishing the plan is not nearly finishing the job"


# --- the request through /v1/message keeps its structure -------------------------------------------

LONG_REQUEST = ("@model: qwen3:30b-a3b\nList the components.\n---\n"
                "@input: distillery-design-validation.md")


def _submitting_product(tmp_path):
    from sovereign_product.server import ProductService
    from sovereign_product.store import SovereignStore

    store = SovereignStore(tmp_path / "sovereign.db")
    session = store.create_session(None, title="t")
    enqueued = []
    fake = SimpleNamespace(store=store, qualification=lambda: {"verdict": "qualified"},
                           active_job=lambda sid: None, _enqueue=enqueued.append,
                           public_job=lambda job: {"job_id": job["job_id"]})
    fake.route = lambda text, override: ProductService.route(fake, text, override)
    return ProductService, fake, store, session["session_id"]


@pytest.mark.parametrize("text,override", [
    (LONG_REQUEST, "LONG"),
    ("route: LONG\n" + LONG_REQUEST, None),
])
def test_si_p6_long_job_keeps_the_request_lines(tmp_path, text, override):
    """Live: routing collapsed whitespace, so '---' and '@model:' lines never reached the executor."""
    service, fake, store, session_id = _submitting_product(tmp_path)
    payload, status = service.submit(fake, session_id, text, route_override=override)
    assert status == 202
    job = store.get_job(payload["job_id"])
    assert job["route"] == "LONG" and job["input"] == LONG_REQUEST
    requested, rest = LW.split_model_directive(job["input"])
    objective, material = LW.parse_request(rest.replace("@input: distillery-design-validation.md",
                                                        "inline material"), tmp_path)
    assert requested == "qwen3:30b-a3b" and objective == "List the components."
    assert material == "inline material"
    store.close()


def test_si_p6_other_routes_still_run_on_the_normalized_query(tmp_path):
    service, fake, store, session_id = _submitting_product(tmp_path)
    payload, status = service.submit(fake, session_id, "what   is\n\nthe  time", route_override="QUICK")
    assert status == 202 and store.get_job(payload["job_id"])["input"] == "what is the time"
    store.close()


# --- reasoning models ------------------------------------------------------------------------------

def _config_with(tmp_path, **moe):
    doc = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    entry = next(m for m in doc["models"] if m["model"] == "qwen3:30b-a3b")
    entry.clear()
    entry.update({"model": "qwen3:30b-a3b", "context": 32768, **moe})
    return _root(tmp_path, doc)


def test_si_p6_shipped_moe_is_a_thinking_model_with_room_to_reason(clean_env, tmp_path):
    """Live: Ollama's qwen3:30b-a3b is Qwen3-30B-A3B-Thinking-2507; with thinking 'off' it spent
    all 2048 tokens reasoning, returned an empty answer, and the reduce failed three times."""
    entry = LW.load_config(_root(tmp_path)).model("qwen3:30b-a3b")
    assert entry.thinking == "on" and entry.reasoning_tokens >= 4096


@pytest.mark.parametrize("moe,match", [
    ({"thinking": "on"}, "reasoning_tokens >= 512"),
    ({"thinking": "on", "reasoning_tokens": 100}, "reasoning_tokens >= 512"),
    ({"thinking": "on", "reasoning_tokens": -1}, "integer >= 0"),
    ({"thinking": "on", "reasoning_tokens": 9000}, "quarter"),
])
def test_si_p6_reasoning_budget_is_validated(clean_env, tmp_path, moe, match):
    with pytest.raises(LW.LongWorkloadError, match=match):
        LW.load_config(_config_with(tmp_path, **moe))


def test_si_p6_reasoning_budget_reaches_every_model_call(clean_env, tmp_path):
    root = _config_with(tmp_path, thinking="on", reasoning_tokens=4096)
    client = FakeLlama(context=32768)
    result = _executor(root, client).run("job-t1", "@model: qwen3:30b-a3b\nDraft a plan.",
                                         cancel_requested=lambda: False,
                                         progress_callback=lambda p: None)
    assert result["status"] == "completed"
    assert all(c["think"] is True for c in client.chats)
    assert all(c["options"]["num_predict"] == 2048 + 4096 for c in client.chats)


class _ReasonsAnyway(FakeLlama):
    """A thinking-only model: whatever enable_thinking says, it reasons and runs out of room."""

    def chat(self, *, model, messages, options, think, cancel_requested):
        self.chats.append({"model": model, "think": think})
        return SimpleNamespace(text="", reasoning="Okay, let's tackle this step. " * 200,
                               finish_reason="length")


def test_si_p6_a_thinking_only_model_configured_off_fails_fast_and_says_why(clean_env, tmp_path):
    from sovereign_product.shard_runner import ModelConfigurationError

    root = _config_with(tmp_path, thinking="off")
    client = _ReasonsAnyway(context=32768)
    with pytest.raises(ModelConfigurationError, match="thinking-only model"):
        _executor(root, client).run("job-t2", "@model: qwen3:30b-a3b\nDraft a plan.",
                                    cancel_requested=lambda: False,
                                    progress_callback=lambda p: None)
    assert len(client.chats) == 1, "no retries spent on a call that cannot succeed"


# --- a model served without its LONG plan ----------------------------------------------------------

def test_si_p6_a_model_served_without_its_plan_is_refused_with_the_reason(clean_env, tmp_path):
    """Live: with the GPU busy the supervisor refused the MoE's plan and served it at its 8k default;
    the job then failed with a misleading 'no room for shard content'."""
    root = _root(tmp_path)
    service = P.resolve_runtime_dir(root) / "llamacpp_supervisor"
    service.mkdir(parents=True)
    (service / "hybrid_plans.json").write_text(json.dumps({"qwen3:30b-a3b": {
        "applied": False, "reason": "even with every expert in RAM, attention weights + KV "
                                    "(2.3 GiB) exceed usable VRAM 0.6 GiB"}}), encoding="utf-8")
    client = FakeLlama(context=8192)
    with pytest.raises(LW.LongWorkloadError) as refused:
        _executor(root, client).run("job-np", "@model: qwen3:30b-a3b\nDraft a plan.",
                                    cancel_requested=lambda: False,
                                    progress_callback=lambda p: None)
    message = str(refused.value)
    assert "8192-token context, below the 32768" in message
    assert "plan refused: even with every expert in RAM" in message and "usable VRAM" in message
    assert client.chats == [], "refused before any model call"


def test_si_p6_missing_plan_report_still_refuses_clearly(clean_env, tmp_path):
    root = _root(tmp_path)
    with pytest.raises(LW.LongWorkloadError, match="no plan report from the supervisor"):
        _executor(root, FakeLlama(context=4096)).run("job-np2", "Draft a plan.",
                                                     cancel_requested=lambda: False,
                                                     progress_callback=lambda p: None)


# --- the operator's view of a LONG run (GET /v1/jobs/<id>/ledger) ----------------------------------

def _long_view_service(root, job):
    from sovereign_product.server import ProductService

    fake = SimpleNamespace(store=SimpleNamespace(get_job=lambda job_id: job),
                           paths=SimpleNamespace(evidence_dir=root / "ev"))
    return lambda job_id: ProductService.long_run(fake, job_id)


def test_si_p6_ledger_view_shows_every_chunk_and_the_carried_ledger(clean_env, tmp_path):
    root = _small_root(tmp_path)
    result = _executor(root, FakeLlama()).run("job-v1", "Draft a rollout plan.",
                                              cancel_requested=lambda: False,
                                              progress_callback=lambda p: None)
    view = _long_view_service(root, {"job_id": "job-v1", "route": "LONG",
                                     "status": "completed"})("job-v1")
    assert view["started"] is True and view["mode"] == "plan_steps"
    assert view["objective"] == "Draft a rollout plan." and view["job_status"] == "completed"
    assert view["run_status"] == "completed"
    assert view["total"] == result["telemetry"]["shards"] == view["completed"]
    assert [t["kind"] for t in view["tasks"]][0] == "plan"
    assert all(t["status"] == "completed" and t["attempts"] == 1 for t in view["tasks"])
    assert view["model_calls"] == result["telemetry"]["model_calls"]
    assert set(view["ledger"]) >= {"facts", "decisions", "open_questions", "results"}
    assert any("done:" in (r.get("summary") or "") for r in view["ledger"]["results"])


def test_si_p6_ledger_view_of_a_queued_job_reports_not_started(clean_env, tmp_path):
    root = _small_root(tmp_path)
    view = _long_view_service(root, {"job_id": "job-q", "route": "LONG",
                                     "status": "queued"})("job-q")
    assert view["started"] is False and view["tasks"] == []
    assert not (root / "ev" / "long" / "job-q").exists(), "a read never creates run state"


def test_si_p6_ledger_view_is_only_for_long_jobs(clean_env, tmp_path):
    root = _small_root(tmp_path)
    with pytest.raises(ValueError, match="not LONG"):
        _long_view_service(root, {"job_id": "job-quick", "route": "QUICK",
                                  "status": "completed"})("job-quick")


def test_si_p6_ledger_view_refuses_tampered_checkpoints(clean_env, tmp_path):
    root = _small_root(tmp_path)
    _executor(root, FakeLlama()).run("job-t", "Draft a rollout plan.",
                                     cancel_requested=lambda: False,
                                     progress_callback=lambda p: None)
    checkpoint = sorted((root / "ev" / "long" / "job-t" / "checkpoints").glob("*.json"))[1]
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    record["payload"]["summary"] = "tampered"
    checkpoint.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoints cannot be read"):
        _long_view_service(root, {"job_id": "job-t", "route": "LONG",
                                  "status": "completed"})("job-t")


def test_si_p6_health_lists_the_long_models(clean_env, tmp_path):
    from sovereign_product.server import ProductService

    info = ProductService.long_models(SimpleNamespace(root=_root(tmp_path)))
    assert info["default_model"] == "qwen3.8:27b"
    assert {m["model"] for m in info["models"]} == {"qwen3.8:27b", "qwen3:30b-a3b"}
    broken = tmp_path / "broken"
    broken.mkdir()
    assert ProductService.long_models(SimpleNamespace(root=broken))["models"] == []


def test_si_p6_a_cancelled_run_says_how_far_it_got(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = FakeLlama()
    result = _executor(root, client).run("job-c", "Draft a rollout plan.",
                                         cancel_requested=lambda: len(client.chats) >= 1,
                                         progress_callback=lambda p: None)
    assert result["status"] == "cancelled"
    assert result["reason"].startswith("cancelled after 1 of ")
    assert "stay in the ledger" in result["reason"] and "[]" not in result["reason"]
