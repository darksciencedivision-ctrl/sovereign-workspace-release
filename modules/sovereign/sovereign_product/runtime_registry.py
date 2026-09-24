from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import hashlib
import os
from pathlib import Path
import threading
import re
from typing import Any, Iterable, Mapping

from .runtime_contracts import CAPABILITY_STATES, CAPABILITY_UNKNOWN

# WS-0.4: FreeToken executable default resolves from SOVEREIGN_FREETOKEN_EXE, matching
# freetoken_service, with the historical build-host path as a last-resort default.
_DEFAULT_FREETOKEN_EXE = os.environ.get(
    "SOVEREIGN_FREETOKEN_EXE"
) or r"D:\SOVEREIGN_SYSTEM\migration_evidence\opencode_grok46_20260910\freetoken_env_rebuild\Scripts\ft.exe"


SCHEMA_ID = "sovereign.runtime-registry.v1"
PRODUCTION_ROLES = {
    "PRIMARY_REASONER": "qwen3:14b",
    "ADVERSARIAL_CHALLENGER": "qwen3:32b",
    "CRITIC": "qwen3:8b",
    "SYNTHESIZER": "qwen2.5:14b-instruct",
    "EMBEDDING_MODEL": "nomic-embed-text:latest",
}
PRODUCTION_WEIGHTS = {
    "qwen3:14b": "a8cc1361f3145dc01f6d77c6c82c9116b9ffe3c97b34716fe20418455876c40e",
    "qwen3:32b": "3291abe70f16ee9682de7bfae08db5373ea9d6497e614aaad63340ad421d6312",
    "qwen3:8b": "a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f",
    "qwen2.5:14b-instruct": "2049f5674b1e92b4464e5729975c9689fcfbf0b0e4443ccf10b5339f370f9a54",
    "nomic-embed-text:latest": "970aa74c0a90ef7482477cf803618e776e173c007bf957f635f1015bfcfef0e6",
}
DECLARED_CONTEXT_WINDOW = 131072
DECLARED_MAX_OUTPUT_TOKENS = 32768
N_CTX_TRAIN = {
    "nomic-embed-text:latest": 2048,
    "qwen3:8b": 40960,
    "qwen3:14b": 40960,
    "qwen3:32b": 40960,
    "qwen2.5:14b-instruct": 32768,
    "qwen3.8:27b": 262144,
}
SERVING_SLOTS = {
    "nomic-embed-text:latest": {"ctx": 2048, "ngl": 0, "tested": 2048},
    "qwen3:8b": {"ctx": 16384, "ngl": 16, "tested": 16384},
    "qwen3:14b": {"ctx": 40960, "ngl": 8, "tested": 7958},
    "qwen2.5:14b-instruct": {"ctx": 32768, "ngl": 8, "tested": 7958},
    "qwen3:32b": {"ctx": 40960, "ngl": 8, "tested": 3958},
}
CONSUMER_WEIGHTS = {
    "qwen3.8:27b": "f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d",
}
CONSUMER_SLOTS = {
    # ctx 131072 is a SUPPORTED configuration, not a metadata claim: llama.cpp
    # loaded this exact model/blob on this machine at ctx 32768/65536/131072/
    # 262144 (ngl 8, hybrid CPU) on 2026-09-11 (WORKLOG ladder; GGUF
    # qwen35.context_length=262144; VRAM was not the limiter). "tested" stays
    # 22409: a full-window 131072 production workload has NOT been run.
    "qwen3.8:27b": {"ctx": 131072, "ngl": 8, "tested": 22409},
}


class RegistryError(ValueError):
    """Invalid registry entity or unresolved identity."""


def _non_empty(value: str, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise RegistryError(f"{label} must be a non-empty string")
    return text


def _capability(value: str, label: str) -> str:
    state = _non_empty(value, label)
    if state not in CAPABILITY_STATES:
        raise RegistryError(f"{label} is not a valid capability state")
    return state


@dataclass(frozen=True)
class Artifact:
    identity: str
    paths: tuple[str, ...]
    sizes: tuple[int | None, ...]
    format: str
    declared_hash: str | None
    verified_hash: str | None
    provenance: str
    companions: tuple[str, ...] = ()
    shards: tuple[str, ...] = ()
    retention_owner: str = "index_in_place"
    integrity: str = "unverified"

    def __post_init__(self) -> None:
        _non_empty(self.identity, "artifact.identity")
        if not self.paths:
            raise RegistryError("artifact.paths must not be empty")
        if self.integrity not in {"unverified", "verified", "failed", "missing"}:
            raise RegistryError("artifact.integrity is invalid")


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    aliases: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    architecture: str
    metadata: dict[str, Any] = field(default_factory=dict)
    local_weights: bool = True
    disposition: str = "index_in_place"

    def __post_init__(self) -> None:
        _non_empty(self.model_id, "model.model_id")
        if not self.artifact_ids:
            raise RegistryError("model.artifact_ids must not be empty")


@dataclass(frozen=True)
class ServingProfile:
    profile_id: str
    model_id: str
    engine_id: str
    model_path: str
    embeddings: bool
    context_configured: int
    context_tested: int | None
    n_gpu_layers: int
    parallel: int = 1
    batch_size: int | None = None
    ubatch_size: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    thinking_policy: str = "omit"
    dimensions: int | None = None
    pooling: str | None = None
    stop: tuple[str, ...] = ()
    capability: str = CAPABILITY_UNKNOWN

    def __post_init__(self) -> None:
        _non_empty(self.profile_id, "profile.profile_id")
        _non_empty(self.model_id, "profile.model_id")
        _non_empty(self.engine_id, "profile.engine_id")
        _non_empty(self.model_path, "profile.model_path")
        if self.thinking_policy not in {"omit", "off", "on"}:
            raise RegistryError("profile.thinking_policy is invalid")
        if self.context_configured <= 0:
            raise RegistryError("profile.context_configured must be positive")
        _capability(self.capability, "profile.capability")


@dataclass(frozen=True)
class RuntimeInstallation:
    runtime_id: str
    backend: str
    version: str
    executable: str
    hashes: dict[str, str]
    platform: str
    toolchain: str
    supported_capabilities: tuple[str, ...]
    verified_capabilities: tuple[str, ...]
    provenance: str

    def __post_init__(self) -> None:
        _non_empty(self.runtime_id, "runtime.runtime_id")
        _non_empty(self.backend, "runtime.backend")
        _non_empty(self.executable, "runtime.executable")


@dataclass(frozen=True)
class RoleMapping:
    role: str
    model_id: str
    profile_id: str

    def __post_init__(self) -> None:
        _non_empty(self.role, "role.role")
        _non_empty(self.model_id, "role.model_id")
        _non_empty(self.profile_id, "role.profile_id")


@dataclass(frozen=True)
class QualificationRecord:
    consumer: str
    consumer_version: str
    profile_id: str
    runtime_id: str
    capability: str
    evidence: tuple[str, ...]
    bounds: dict[str, Any] = field(default_factory=dict)
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.consumer, "qualification.consumer")
        _capability(self.capability, "qualification.capability")


@dataclass
class RuntimeRegistry:
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    models: dict[str, ModelIdentity] = field(default_factory=dict)
    profiles: dict[str, ServingProfile] = field(default_factory=dict)
    runtimes: dict[str, RuntimeInstallation] = field(default_factory=dict)
    roles: dict[str, RoleMapping] = field(default_factory=dict)
    qualifications: list[QualificationRecord] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    production_default: bool = False

    def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts[artifact.identity] = artifact

    def add_model(self, model: ModelIdentity) -> None:
        self.models[model.model_id] = model
        self.aliases[_non_empty(model.model_id, "model.model_id")] = model.model_id
        for alias in model.aliases:
            self.aliases[_non_empty(alias, "model.alias")] = model.model_id

    def add_profile(self, profile: ServingProfile) -> None:
        if profile.model_id not in self.models:
            raise RegistryError(f"profile {profile.profile_id} references unknown model")
        self.profiles[profile.profile_id] = profile
        self.aliases[profile.profile_id] = profile.model_id
        self.aliases[profile.engine_id] = profile.model_id

    def add_runtime(self, runtime: RuntimeInstallation) -> None:
        self.runtimes[runtime.runtime_id] = runtime

    def add_role(self, role: RoleMapping) -> None:
        if role.model_id not in self.models:
            raise RegistryError(f"role {role.role} references unknown model")
        if role.profile_id not in self.profiles:
            raise RegistryError(f"role {role.role} references unknown profile")
        self.roles[role.role] = role
        self.aliases[role.role] = role.model_id

    def add_qualification(self, record: QualificationRecord) -> None:
        if record.profile_id not in self.profiles:
            raise RegistryError("qualification references unknown profile")
        if record.runtime_id not in self.runtimes:
            raise RegistryError("qualification references unknown runtime")
        self.qualifications.append(record)

    def resolve_model_id(self, name: str) -> str:
        key = _non_empty(name, "model identity")
        if key in self.models:
            return key
        if key in self.aliases:
            return self.aliases[key]
        raise RegistryError(f"unknown model identity: {name!r}")

    def resolve_profile(self, name: str) -> ServingProfile:
        key = _non_empty(name, "profile identity")
        if key in self.profiles:
            return self.profiles[key]
        model_id = self.resolve_model_id(key)
        matches = [item for item in self.profiles.values() if item.model_id == model_id]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise RegistryError(f"no serving profile for {name!r}")
        raise RegistryError(f"ambiguous serving profile for {name!r}")

    def engine_id(self, name: str) -> str:
        return self.resolve_profile(name).engine_id

    def validate_production_roles(self, manifest_models: Mapping[str, str]) -> None:
        expected = {key: str(value).strip() for key, value in manifest_models.items()}
        actual = {role: mapping.model_id for role, mapping in self.roles.items()}
        for key, model_id in PRODUCTION_ROLES.items():
            if expected.get(key) != model_id:
                raise RegistryError(
                    f"manifest role {key} is {expected.get(key)!r}, not {model_id!r}"
                )
            if actual.get(key) != model_id:
                raise RegistryError(f"registry role {key} does not preserve {model_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ID,
            "production_default": self.production_default,
            "artifacts": [asdict(item) for item in self.artifacts.values()],
            "models": [asdict(item) for item in self.models.values()],
            "profiles": [asdict(item) for item in self.profiles.values()],
            "runtimes": [asdict(item) for item in self.runtimes.values()],
            "roles": [asdict(item) for item in self.roles.values()],
            "qualifications": [asdict(item) for item in self.qualifications],
            "aliases": dict(self.aliases),
        }


def blob_path(digest: str) -> Path:
    return Path.home() / ".ollama" / "models" / "blobs" / f"sha256-{digest}"


def context_resolution(model_id: str) -> dict[str, Any]:
    """Separate requested/configured/advertised/supported context limits.

    - advertised_declared: the model's native/declared window (n_ctx_train
      backed; 2048 for the embedding model; product declaration 131072 for
      the production slate).
    - configured: the serving slot ctx actually rendered into the llama.cpp
      preset (a supported configuration must be load-proven on this machine).
    - tested: the largest genuine workload context evidenced for the slot.
    - effective_cap: min(n_ctx_train, configured) — what a request can use.
    - declared_requirement_supported: the original product requirement
      (DECLARED_CONTEXT_WINDOW=131072) is deliverable for this model by
      configuration (train and configured both >= 131072).
    Per-request "requested" limits are resolved and rejected explicitly in
    LlamaCppClient._resolve_generation_capacity (no silent truncation).
    """

    slot = SERVING_SLOTS.get(model_id) or CONSUMER_SLOTS.get(model_id) or {}
    embeddings = model_id == "nomic-embed-text:latest"
    advertised = 2048 if embeddings else DECLARED_CONTEXT_WINDOW
    if model_id == "qwen3.8:27b":
        advertised = 262144
    configured = int(slot["ctx"]) if "ctx" in slot else None
    tested = slot.get("tested")
    train = N_CTX_TRAIN.get(model_id)
    effective_cap = configured
    if train is not None and configured is not None:
        effective_cap = min(train, configured)
    declared_supported = (
        (not embeddings)
        and train is not None
        and configured is not None
        and train >= DECLARED_CONTEXT_WINDOW
        and configured >= DECLARED_CONTEXT_WINDOW
    )
    unmet = (
        (not embeddings)
        and configured is not None
        and not declared_supported
    )
    advertised_exceeds_configured = (
        advertised is not None and configured is not None and advertised > configured
    )
    reason = None
    if declared_supported:
        reason = (
            f"declared {DECLARED_CONTEXT_WINDOW} is deliverable by configuration: "
            f"n_ctx_train={train}, configured={configured}; tested={tested} "
            "(full-window 131072 production workload has not been run)"
        )
    elif unmet:
        reason = (
            f"declared {DECLARED_CONTEXT_WINDOW} is undeliverable for {model_id}: "
            f"native n_ctx_train={train} caps the model below the requirement; "
            f"serving uses configured={configured} tested={tested}; resolving this "
            "requires a production-grade model with n_ctx_train >= 131072 or a "
            "full-window-qualified rope-scaling configuration (neither exists; "
            "roles are not substituted and over-cap requests are rejected)"
        )
    return {
        "model_id": model_id,
        "advertised_declared": advertised,
        "n_ctx_train": train,
        "configured": configured,
        "tested": tested,
        "effective_cap": effective_cap,
        "unmet_declared_requirement": unmet,
        "declared_context_window": DECLARED_CONTEXT_WINDOW,
        "declared_requirement_supported": declared_supported,
        "advertised_exceeds_configured": advertised_exceeds_configured,
        "reason": reason,
    }


def freetoken_installation(
    *,
    executable: str | Path = _DEFAULT_FREETOKEN_EXE,
    version: str = "0.1.3",
) -> RuntimeInstallation:
    return RuntimeInstallation(
        runtime_id="freetoken-win-cuda13-0.1.3",
        backend="freetoken",
        version=version,
        executable=str(executable),
        hashes={
            "ft.exe": "0D5822FF159CF68096E980336BF76DC59EA4A545CA5855A2091C5BD27E9ED994",
            "_pinned_tensor.pyd": "8DEAC5A86922ACFA9CDD5CD695012756C843488132CE4CE6473A03AD78EEF8FB",
            "_cpu_moe.pyd": "E4972325FFCD14E95F758F0F1C174D34A8F341B0C7579A93FFE4D799F1FB8A3C",
            "wheel": "F8428441CE2B52AD1A7CA4B9668A3F1540970955AE710B21F2CEA9E55E922FED",
        },
        platform="win-x86_64-nvidia-cuda13-rtx5060ti",
        toolchain="MSVC 14.44.35207, pip nvidia-cuda-nvcc 13.0.88, torch 2.11.0+cu130, pin 46d27439",
        supported_capabilities=(
            "chat_completions",
            "streaming",
            "tool_calls",
            "moe_offload",
            "cpu_moe_native_extension",
        ),
        verified_capabilities=(
            "dummy_chat_completions",
            "qwen3_0.6b_dense_pong",
            "gpt_oss_20b_offload_pong",
            "stream_cancel_recover",
            "tool_call_and_continuation",
            "supervisor_job_object_start_stop",
        ),
        provenance=(
            "FlashML-org/FreeToken@46d27439a4fccf457e1a9a858841168ec7a1c65d plus Windows port patches "
            "(mp/cli/launch selector-loop, utils.h __always_inline, kernel JIT /std:c++20, setup.py MSVC "
            "_pinned_tensor+_cpu_moe, cpu_moe_compat.h, allocation-failure unwind, apache-tvm-ffi C++20 patch); "
            "final package 0.1.3 built/installed 2026-09-13 RUNS/freetoken_package_final_20260913T174647Z; "
            "capability verification evidence predates 0.1.3 and was not re-run for this build"
        ),
    )


def llama_cpp_installation(
    *,
    executable: str | Path,
    hashes: Mapping[str, str],
    version: str = "2.28.2",
    provenance: str = "lmstudio-distributed, upstream correspondence unverified",
) -> RuntimeInstallation:
    return RuntimeInstallation(
        runtime_id="llama.cpp-win-cuda12-2.28.2",
        backend="llama.cpp",
        version=version,
        executable=str(executable),
        hashes=dict(hashes),
        platform="win-x86_64-nvidia-cuda12-avx2",
        toolchain="CUDA 12.8, sm_120 observed, compiled targets include 12.0",
        supported_capabilities=(
            "chat_completions",
            "embeddings",
            "streaming",
            "router_load_unload",
        ),
        verified_capabilities=(),
        provenance=provenance,
    )


# SW-09: verified-digest cache keyed by (path, size, mtime_ns), so a multi-GB blob is hashed once and
# not re-hashed on every registry build; any size/mtime change invalidates the entry and forces a
# re-hash. Result is the actual sha256, compared against the declared digest by the caller.
_DIGEST_CACHE: dict[str, tuple[int, int, str]] = {}
_DIGEST_CACHE_LOCK = threading.Lock()


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _verify_blob_digest(path: Path, expected: str) -> bool:
    """SW-09: True ONLY when the file's bytes hash to `expected` — never mere existence."""
    try:
        st = path.stat()
    except OSError:
        return False
    key = str(path)
    with _DIGEST_CACHE_LOCK:
        cached = _DIGEST_CACHE.get(key)
    if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
        return cached[2] == expected
    actual = _file_sha256(path)
    if actual is None:
        return False
    with _DIGEST_CACHE_LOCK:
        _DIGEST_CACHE[key] = (st.st_size, st.st_mtime_ns, actual)
    return actual == expected


def build_production_registry(
    *,
    extra_paths: Mapping[str, Iterable[str]] | None = None,
    runtime: RuntimeInstallation | None = None,
) -> RuntimeRegistry:
    registry = RuntimeRegistry(production_default=True)
    extras = {key: tuple(str(path) for path in paths) for key, paths in dict(extra_paths or {}).items()}
    for model_id, digest in PRODUCTION_WEIGHTS.items():
        primary = blob_path(digest)
        paths = (str(primary),) + extras.get(model_id, ())
        sizes: list[int | None] = []
        for path in paths:
            item = Path(path)
            sizes.append(item.stat().st_size if item.is_file() else None)
        # SW-09: verification means the primary blob's BYTES hash to the declared digest — never mere
        # existence. present / declared / verified are distinct: a present file whose digest does not
        # match is "failed", not "verified", and never receives a verified_hash.
        if sizes[0] is None:
            integrity = "missing"
            verified = None
        elif _verify_blob_digest(Path(paths[0]), digest):
            integrity = "verified"
            verified = digest
        else:
            integrity = "failed"
            verified = None
        artifact = Artifact(
            identity=f"sha256:{digest}",
            paths=paths,
            sizes=tuple(sizes),
            format="gguf",
            declared_hash=digest,
            verified_hash=verified,
            provenance="ollama-blob-index-in-place",
            retention_owner="ollama-store",
            integrity=integrity,
        )
        registry.add_artifact(artifact)
        embeddings = model_id == "nomic-embed-text:latest"
        slot = SERVING_SLOTS[model_id]
        registry.add_model(
            ModelIdentity(
                model_id=model_id,
                aliases=(model_id,),
                artifact_ids=(artifact.identity,),
                architecture="nomic-bert" if embeddings else "qwen3" if model_id.startswith("qwen3:") else "qwen2",
                metadata={
                    "role_slate": True,
                    "declared_context_window": 2048 if embeddings else DECLARED_CONTEXT_WINDOW,
                    "declared_max_output_tokens": DECLARED_MAX_OUTPUT_TOKENS,
                    "serving_slot_is_not_production_qualification": not embeddings,
                },
                local_weights=True,
                disposition="migrate",
            )
        )
        profile_id = model_id.replace(":", "-")
        registry.add_profile(
            ServingProfile(
                profile_id=profile_id,
                model_id=model_id,
                engine_id=profile_id,
                model_path=str(primary),
                embeddings=embeddings,
                context_configured=int(slot["ctx"]),
                context_tested=slot["tested"],
                n_gpu_layers=int(slot["ngl"]),
                parallel=1,
                batch_size=2048 if embeddings else None,
                ubatch_size=2048 if embeddings else None,
                temperature=None if embeddings else 0.6,
                top_k=None if embeddings else 20,
                top_p=None if embeddings else 0.95,
                thinking_policy="off" if model_id.startswith("qwen3:") else "omit",
                dimensions=768 if embeddings else None,
                pooling="cls" if embeddings else None,
                capability="experimentally_demonstrated" if slot["tested"] is not None else "declared",
            )
        )
    if runtime is not None:
        registry.add_runtime(runtime)
    for role, model_id in PRODUCTION_ROLES.items():
        registry.add_role(
            RoleMapping(
                role=role,
                model_id=model_id,
                profile_id=model_id.replace(":", "-"),
            )
        )
    return registry


def add_consumer_model(registry: RuntimeRegistry, model_id: str) -> None:
    digest = CONSUMER_WEIGHTS[model_id]
    slot = CONSUMER_SLOTS[model_id]
    primary = blob_path(digest)
    size = primary.stat().st_size if primary.is_file() else None
    artifact = Artifact(
        identity=f"sha256:{digest}",
        paths=(str(primary),),
        sizes=(size,),
        format="gguf",
        declared_hash=digest,
        verified_hash=None,
        provenance="ollama-blob-index-in-place",
        retention_owner="ollama-store",
        integrity="unverified" if size is not None else "missing",
    )
    registry.add_artifact(artifact)
    registry.add_model(
        ModelIdentity(
            model_id=model_id,
            aliases=(model_id,),
            artifact_ids=(artifact.identity,),
            architecture="qwen3",
                metadata={
                    "role_slate": False,
                    "consumer": "hermes-terry",
                    "consumer_status": (
                        "removed_not_restored (see HERMES_TERRY_DISCOVERY.md); "
                        "slot retained for rollback/reinstall"
                    ),
                    "declared_context_window": 262144,
                    "hermes_software_floor": 65536,
                    "sovereign_declared_context_window": DECLARED_CONTEXT_WINDOW,
                    "context_configuration_evidence": (
                        "2026-09-11 ladder: llama.cpp loaded ctx 32768/65536/"
                        "131072/262144 at ngl 8 (hybrid CPU); 22409-token PONG "
                        "each rung; VRAM not the limiter; full-window 131072 "
                        "production workload not run"
                    ),
                    "serving_slot_is_not_production_qualification": True,
                },
            local_weights=True,
            disposition="migrate",
        )
    )
    profile_id = model_id.replace(":", "-")
    registry.add_profile(
        ServingProfile(
            profile_id=profile_id,
            model_id=model_id,
            engine_id=profile_id,
            model_path=str(primary),
            embeddings=False,
            context_configured=int(slot["ctx"]),
            context_tested=slot["tested"],
            n_gpu_layers=int(slot["ngl"]),
            parallel=1,
            thinking_policy="off",
            capability="declared",
        )
    )


def _manifest_model_id(manifest_root: Path, manifest: Path) -> str:
    """Return the human-facing local tag recorded by an Ollama manifest."""
    parts = manifest.relative_to(manifest_root).parts
    if len(parts) >= 4 and parts[:2] == ("registry.ollama.ai", "library"):
        return ":".join(parts[2:])
    if len(parts) >= 3 and parts[0] == "registry.ollama.ai":
        return ":".join(parts[1:])
    return ":".join(parts)


def _engine_id(model_id: str, digest: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", model_id).strip("-").lower()
    return stem[:60]


def add_local_ollama_library(
    registry: RuntimeRegistry,
    *,
    manifest_root: str | Path | None = None,
) -> int:
    """Index every locally installed, GGUF-backed Ollama model in place.

    This deliberately reads manifests and the first four bytes of a referenced
    blob only.  It never copies, moves, hashes, loads, or downloads a model.
    Models already assigned to the product role slate retain their curated
    serving profiles; every additional compatible model becomes a selectable
    on-demand router profile with conservative CPU-first defaults.
    """
    root = Path(manifest_root or (Path.home() / ".ollama" / "models" / "manifests"))
    blob_root = root.parent / "blobs"
    if not root.is_dir() or not blob_root.is_dir():
        return 0
    added = 0
    for manifest in sorted(root.rglob("*")):
        if not manifest.is_file():
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        layers = document.get("layers") if isinstance(document, dict) else None
        if not isinstance(layers, list):
            continue
        layer = next((item for item in layers if isinstance(item, dict)
                      and item.get("mediaType") == "application/vnd.ollama.image.model"), None)
        digest = str((layer or {}).get("digest") or "").removeprefix("sha256:").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        path = blob_root / f"sha256-{digest}"
        try:
            with path.open("rb") as handle:
                header = handle.read(4)
            if header != b"GGUF":
                continue
        except OSError:
            continue
        model_id = _manifest_model_id(root, manifest)
        if not model_id or model_id in registry.models:
            continue
        engine = _engine_id(model_id, digest)
        if engine in registry.profiles:
            engine = f"{engine[:47]}-{digest[:12]}"
        embeddings = "embed" in model_id.casefold()
        artifact_id = f"sha256:{digest}"
        registry.add_artifact(Artifact(
            identity=artifact_id,
            paths=(str(path),),
            sizes=(path.stat().st_size,),
            format="gguf",
            declared_hash=digest,
            verified_hash=None,
            provenance="ollama-manifest-index-in-place",
            retention_owner="ollama-store",
            integrity="unverified",
        ))
        registry.add_model(ModelIdentity(
            model_id=model_id,
            aliases=(model_id,),
            artifact_ids=(artifact_id,),
            architecture="unknown",
            metadata={"library": "ollama", "discovered_from": str(manifest)},
            local_weights=True,
            disposition="index_in_place",
        ))
        registry.add_profile(ServingProfile(
            profile_id=engine,
            model_id=model_id,
            engine_id=engine,
            model_path=str(path),
            embeddings=embeddings,
            context_configured=8192 if not embeddings else 2048,
            context_tested=None,
            n_gpu_layers=0,
            parallel=1,
            capability="declared",
        ))
        added += 1
    return added


def build_operational_registry(
    *,
    extra_paths: Mapping[str, Iterable[str]] | None = None,
    runtime: RuntimeInstallation | None = None,
) -> RuntimeRegistry:
    registry = build_production_registry(extra_paths=extra_paths, runtime=runtime)
    for model_id in CONSUMER_WEIGHTS:
        add_consumer_model(registry, model_id)
    add_local_ollama_library(registry)
    if "freetoken-win-cuda13-0.1.3" not in registry.runtimes:
        registry.add_runtime(freetoken_installation())
    return registry


def dump_registry(registry: RuntimeRegistry, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry.to_dict(), indent=2), encoding="utf-8")


def load_registry(path: str | Path) -> RuntimeRegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_ID:
        raise RegistryError("unsupported registry schema")
    registry = RuntimeRegistry(production_default=bool(payload.get("production_default")))
    for item in payload.get("artifacts", []):
        item = dict(item)
        item["paths"] = tuple(item.get("paths") or ())
        item["sizes"] = tuple(item.get("sizes") or ())
        item["companions"] = tuple(item.get("companions") or ())
        item["shards"] = tuple(item.get("shards") or ())
        registry.add_artifact(Artifact(**item))
    for item in payload.get("models", []):
        item = dict(item)
        item["aliases"] = tuple(item.get("aliases") or ())
        item["artifact_ids"] = tuple(item.get("artifact_ids") or ())
        registry.add_model(ModelIdentity(**item))
    for item in payload.get("profiles", []):
        item = dict(item)
        item["stop"] = tuple(item.get("stop") or ())
        registry.add_profile(ServingProfile(**item))
    for item in payload.get("runtimes", []):
        item = dict(item)
        item["supported_capabilities"] = tuple(item.get("supported_capabilities") or ())
        item["verified_capabilities"] = tuple(item.get("verified_capabilities") or ())
        item["hashes"] = dict(item.get("hashes") or {})
        registry.add_runtime(RuntimeInstallation(**item))
    for item in payload.get("roles", []):
        registry.add_role(RoleMapping(**item))
    for item in payload.get("qualifications", []):
        item = dict(item)
        item["evidence"] = tuple(item.get("evidence") or ())
        item["failures"] = tuple(item.get("failures") or ())
        registry.add_qualification(QualificationRecord(**item))
    return registry
