"""The one read-only union catalog of every local model library on this host.

The picker shows models the operator OWNS, not models some runtime happens to have loaded.
Four sources are scanned and merged here, in one place:

  * **C: — the Ollama store** (`~\\.ollama\\models`). Its manifests are read as a *library
    format*: tag → model-layer digest → blob path → on-disk size. Nothing is copied, moved, or
    renamed, and the daemon on 11434 is never contacted: the weights are ordinary GGUF files and
    the supervised llama.cpp router serves them from where they already sit.
  * **D: / E: — Hugging Face families** (flat or hub-cache layout), safetensors.
  * **The supervisor registry** (`runtime/llamacpp_supervisor/models.ini`), which is what makes a
    C: blob addressable on the router.
  * **The live router listing** (`/v1/models` on 18080), which is what makes a registered model
    *runnable now*, and which of those is currently resident.

WHY ONE MODULE OWNS THIS. `library_catalog` used to scan D:/E: only, and the llama.cpp rows came
straight from the router. That split is why the picker could report "the library" while knowing
nothing about 71 of the host's own model tags. A record shape decided in two places drifts; the
operator sees one list.

WHAT THIS MODULE DOES NOT DO. It never loads, downloads, copies, converts, or opens a weight file
(only directory entries, manifest JSON, and the registry are read). It never contacts anything
that is not loopback (`_router_rows` goes through `adapters.detect`, which refuses a non-loopback
endpoint). And it never claims a safetensors family is runnable: `runnable_now` is true only for a
record the llama.cpp router itself advertises from a local file.
"""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any

#: Operator-supplied roots. The defaults are this host's measured library locations; an env var
#: exists so a different machine answers from its own library instead of this file's assumptions.
OLLAMA_MODELS_DIR_ENV = "SOW_OLLAMA_MODELS_DIR"
SUPERVISOR_ROOT_ENV = "SOVEREIGN_LLAMA_SUPERVISOR_ROOT"
DEFAULT_SUPERVISOR_ROOT = r"D:\Sov 1\SOVEREIGN_PRODUCT_COMPLETION_WORK"
REGISTRY_RELATIVE = ("runtime", "llamacpp_supervisor", "models.ini")

#: The local Hugging Face libraries. A drive letter is part of the record: the operator asks which
#: disk a family lives on, and E: staying on E: is a requirement, not a detail.
_HF_ROOTS: tuple[tuple[str, Path], ...] = (
    ("D", Path(os.environ.get("SOW_HF_LIBRARY_D") or r"D:\_codex_tmp\sovereign_distillery_hf")),
    ("E", Path(os.environ.get("SOW_HF_LIBRARY_E") or r"E:\AI\Models")),
)

_EMBEDDING_MARKERS = ("embed", "bge-m3", "mxbai")
_CODING_MARKERS = ("coder", "devstral", "codestral", "starcoder", "codellama", "hammer")

_FORMAT_GGUF = "gguf"
_FORMAT_SAFETENSORS = "safetensors"
_FORMAT_OLLAMA_BLOB = "ollama-blob"      # a manifest with no local weight to serve


def ollama_models_dir() -> Path | None:
    """The Ollama store's `models` directory, or None when this host has none."""
    raw = (os.environ.get(OLLAMA_MODELS_DIR_ENV) or "").strip()
    candidate = Path(raw) if raw else Path.home() / ".ollama" / "models"
    return candidate if (candidate / "manifests").is_dir() else None


def registry_path() -> Path | None:
    """The supervisor's `models.ini`, or None. Read-only: this module never writes it."""
    raw = (os.environ.get(SUPERVISOR_ROOT_ENV) or "").strip() or DEFAULT_SUPERVISOR_ROOT
    candidate = Path(raw).joinpath(*REGISTRY_RELATIVE)
    return candidate if candidate.is_file() else None


def _registry_sections() -> dict[str, dict[str, str]]:
    """`alias -> section options` from the supervisor registry.

    `models.ini` has no `ini` header and is read with `default_section` pointed at a section that
    does not exist, so no stray keys leak into every entry. A registry that cannot be parsed
    yields `{}`: the router listing below still answers what is runnable, and an unreadable
    registry costs us the per-model flags (`embeddings`), not the catalog.
    """
    path = registry_path()
    if path is None:
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment]  # `ctx-size`/`n-gpu-layers` spellings
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}
    out: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if section == "*":
            continue
        opts = {str(k): str(v) for k, v in parser.items(section)}
        alias = (opts.get("alias") or "").strip()
        if alias:
            out[alias] = {"_section": section, **opts}
    return out


def _router_rows() -> list[dict[str, Any]]:
    """What the supervised llama.cpp router advertises right now (loopback only, never raises)."""
    from adapters import detect  # noqa: PLC0415 — keeps this catalog importable without a server

    try:
        return detect.llamacpp_model_records()
    except Exception:  # noqa: BLE001 — a detection helper must not take the picker down
        return []


def _manifest_rows(models_dir: Path) -> list[dict[str, Any]]:
    """One row per Ollama manifest tag: `registry/org/repo:tag` normalized the way `ollama list`
    spells it, plus the model-layer blob path and its size. Reads JSON sidecars only."""
    manifests = models_dir / "manifests"
    blobs = models_dir / "blobs"
    drive = (models_dir.drive or "?").rstrip(":").upper()
    rows: list[dict[str, Any]] = []
    try:
        files = sorted(p for p in manifests.rglob("*") if p.is_file())
    except OSError:
        return []
    for path in files:
        try:
            parts = path.relative_to(manifests).parts
        except ValueError:
            continue
        if len(parts) < 3:
            continue
        registry, tag = parts[0], parts[-1]
        repo = "/".join(parts[1:-1])
        if not repo:
            continue
        full = f"{repo}:{tag}" if registry == "registry.ollama.ai" else f"{registry}/{repo}:{tag}"
        if full.startswith("library/"):
            full = full[len("library/"):]
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        layers = [layer for layer in (manifest.get("layers") or [])
                  if isinstance(layer, dict)
                  and layer.get("mediaType") == "application/vnd.ollama.image.model"]
        digest = str((layers[0].get("digest") or "")) if layers else ""
        blob_name = "sha256-" + digest.split(":", 1)[1] if digest else ""
        blob = blobs / blob_name if blob_name else None
        rows.append({
            "tag": full,
            "disk": drive,
            "path": str(blob) if blob else "",
            "blob_present": bool(blob and blob.is_file()),
            "size_bytes": int(layers[0].get("size") or 0) if layers else 0,
        })
    return rows


def _family_name(tag: str) -> str:
    """The family a tag belongs to: `qwen3:8b` → `qwen3`, `hf.co/unsloth/Phi-4-mini…:Q4_K_M` →
    `Phi-4-mini-reasoning-GGUF`. A display concern only; it gates nothing."""
    repo, _, _tag = tag.rpartition(":")
    leaf = repo.rsplit("/", 1)[-1] if repo else tag
    return leaf or tag


def _capabilities(name: str, registry_opts: dict[str, str]) -> list[str]:
    """Coarse capability labels for grouping and disclosure.

    The registry's own `embeddings = true` flag is authoritative; the name markers are a fallback
    for a family the registry does not describe yet. This is a LABEL, not an admission test — the
    router's listing is what decides `runnable_now`, and a chat pane's real fitness is still
    resolved by the node's capability descriptor at spawn (I-SC1)."""
    lowered = name.casefold()
    if (registry_opts.get("embeddings") or "").strip().lower() in {"true", "1", "yes"}:
        return ["embed"]
    if any(marker in lowered for marker in _EMBEDDING_MARKERS):
        return ["embed"]
    labels = ["chat"]
    if any(marker in lowered for marker in _CODING_MARKERS):
        labels.append("code")
    return labels


def _safetensors_files(family: Path) -> list[Path]:
    """The weight files of one HF family, flat (`E:` layout) or hub-cache (`snapshots/<sha>/`).
    Two bounded globs under the family directory; never a recursive drive walk."""
    try:
        found = sorted(family.glob("*.safetensors"))
        if not found:
            found = sorted(family.glob("snapshots/*/*.safetensors"))
    except OSError:
        return []
    return found


def _hf_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for drive, root in _HF_ROOTS:
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir(), key=lambda entry: entry.name.casefold())
        except OSError:
            continue
        for item in entries:
            if not item.is_dir() or item.name.startswith("."):
                continue
            weights = _safetensors_files(item)
            if not weights:
                continue
            try:
                size = sum(weight.stat().st_size for weight in weights)
            except OSError:
                size = 0
            rows.append({
                "name": item.name,
                "disk": drive,
                "path": str(item),
                "shards": len(weights),
                "size_bytes": size,
            })
    return rows


def library_records(*, router: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The union catalog. One record per model tag or local HF family, never a copy of either.

    Record shape (all keys always present so a consumer need not guess):

      `id`, `display_name`, `family`, `disk` (C|D|E), `path` (absolute, original location),
      `format` (gguf | safetensors | ollama-blob), `capabilities` (chat|embed|code),
      `runnable_now` (llama.cpp can serve this file today), `active` (loaded on the router),
      `size_bytes`, `group` ("runnable" | "in_library"), `source`, `reason`.
    """
    served = router if router is not None else _router_rows()
    by_alias: dict[str, dict[str, Any]] = {}
    for row in served:
        model_id = str(row.get("id") or row.get("name") or "").strip()
        if not model_id:
            continue
        aliases = [str(a) for a in (row.get("aliases") or [])]
        status = str(((row.get("status") or {}).get("value")) if isinstance(row.get("status"), dict)
                     else (row.get("status") or "")).casefold()
        payload = {"id": model_id, "aliases": aliases, "active": status in {"loaded", "load"},
                   "status": status or "unknown", "path": "", "size_bytes": 0}
        # The preset router records the argv it would start the slot with; the `--model` value is
        # the file it actually serves. Reading it back keeps `path` the operator's own absolute
        # path rather than a re-derivation that could disagree with the registry.
        args = ((row.get("status") or {}).get("args") if isinstance(row.get("status"), dict) else None) or []
        for index, token in enumerate(args):
            if str(token) == "--model" and index + 1 < len(args):
                payload["path"] = str(args[index + 1])
                break
        for alias in (*aliases, model_id):
            by_alias[alias] = payload

    registry = _registry_sections()
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    models_dir = ollama_models_dir()
    for manifest in (_manifest_rows(models_dir) if models_dir else []):
        tag = manifest["tag"]
        # Ollama namespaces tags with `/`; the registry spells the same tag with `:` because a
        # Windows path cannot hold the slash. Both spellings address the same model.
        payload = by_alias.get(tag) or by_alias.get(tag.replace("/", ":")) or {}
        section = registry.get(tag) or registry.get(tag.replace("/", ":")) or {}
        model_id = str(payload.get("id") or section.get("_section") or tag)
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)
        runnable = bool(payload) and bool(manifest["blob_present"])
        path = str(payload.get("path") or manifest["path"] or "")
        size = int(manifest["size_bytes"] or payload.get("size_bytes") or 0)
        if not path and not manifest["blob_present"]:
            reason = ("an Ollama registry pointer with no local weights on this host; it is not a "
                      "file the local router can serve")
            fmt = _FORMAT_OLLAMA_BLOB
        elif not runnable:
            reason = ("its GGUF file is on disk but not registered on the supervised llama.cpp "
                      "router; register this path in models.ini to run it")
            fmt = _FORMAT_OLLAMA_BLOB
        else:
            reason = ""
            fmt = _FORMAT_GGUF
        source = (f"{manifest['disk']}: Ollama library (served by llama.cpp from its own file)"
                  if runnable else
                  f"{manifest['disk']}: Ollama library (weights read in place; never copied)")
        records.append({
            "id": model_id,
            "display_name": tag,
            "family": _family_name(tag),
            "disk": manifest["disk"],
            "path": path,
            "format": fmt,
            "capabilities": _capabilities(f"{tag} {model_id}", section),
            "runnable_now": runnable,
            "active": bool(payload.get("active")),
            "size_bytes": size,
            "group": "runnable" if runnable else "in_library",
            "source": source,
            "reason": reason,
        })

    for family in _hf_rows():
        model_id = f"hf-local/{family['disk'].lower()}/{family['name']}"
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)
        records.append({
            "id": model_id,
            "display_name": family["name"],
            "family": family["name"],
            "disk": family["disk"],
            "path": family["path"],
            "format": _FORMAT_SAFETENSORS,
            "capabilities": _capabilities(family["name"], {}),
            # NEVER true. safetensors checkpoints are not something llama.cpp serves, and a picker
            # that marked one runnable would be a control that cannot perform its action.
            "runnable_now": False,
            "active": False,
            "size_bytes": family["size_bytes"],
            "group": "in_library",
            "source": f"{family['disk']}: local Hugging Face library",
            "reason": (f"stored locally as {family['shards']} safetensors shard(s) at "
                       f"{family['path']}; it stays there and needs a configured local "
                       f"Transformers-compatible server before it can be run"),
        })

    return sorted(records, key=lambda r: (r["group"] != "runnable", r["disk"], r["display_name"].casefold()))


def runnable_chat_records(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Chat-capable records llama.cpp can serve right now. Embeddings stay in the catalog (`library_records`)
    and out of a chat picker: a model that cannot hold a conversation is not a greyed-out chat
    option, it is a different kind of thing."""
    rows = records if records is not None else library_records()
    return [r for r in rows
            if r["runnable_now"] and "embed" not in r["capabilities"]
            and "chat" in r["capabilities"]]


def embedding_records(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = records if records is not None else library_records()
    return [r for r in rows if "embed" in r["capabilities"]]


def in_library_records(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Everything the host owns that it cannot run on llama.cpp right now — D:/E: families, cloud
    pointers, and any unregistered C: GGUF file."""
    rows = records if records is not None else library_records()
    return [r for r in rows if not r["runnable_now"]]


def picker_rows(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The two picker groups, derived from one catalog read: (runnable rows, in-library rows).

    Each row keeps the keys `control_plane.nodes.pane_picker` already renders (`model_slug`,
    `label`, `source`, `reason`) and adds the catalog facts the operator asked for. The `label`
    carries the drive, because a 60-row list of names is not an answer to "where is this model".
    """
    runnable: list[dict[str, Any]] = []
    library: list[dict[str, Any]] = []
    for row in records:
        shaped = {
            "id": row["id"],
            "model_slug": row["id"],
            "label": f"{row['display_name']} [{row['disk']}:]",
            "source": row["source"],
            "reason": row["reason"],
            "family": row["family"],
            "disk": row["disk"],
            "path": row["path"],
            "format": row["format"],
            "capabilities": list(row["capabilities"]),
            "runnable_now": row["runnable_now"],
            "active": row["active"],
            "size_bytes": row["size_bytes"],
        }
        if row["runnable_now"]:
            runnable.append(shaped)
        else:
            library.append(shaped)
    return runnable, library


def catalog_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """Honest counts for the enumeration's provenance block. Derived, never declared."""
    return {
        "cataloged": len(records),
        "runnable_now": sum(1 for r in records if r["runnable_now"]),
        "in_library": sum(1 for r in records if not r["runnable_now"]),
        "embedding_only": sum(1 for r in records if "embed" in r["capabilities"]),
        "active": sum(1 for r in records if r["active"]),
        "by_disk": {drive: sum(1 for r in records if r["disk"] == drive)
                    for drive in sorted({r["disk"] for r in records})},
    }


def safetensors_families() -> list[dict[str, str]]:
    """Back-compat shim: the D:/E: families in the shape the picker used before the union catalog.

    Kept because it is a true subset of `in_library_records` and some callers only ever ask "what
    HF families exist". New callers should read `library_records()` instead — this one cannot see
    the C: library, which is exactly the gap the catalog closes."""
    return [{
        "model_slug": row["id"],
        "label": row["display_name"],
        "source": row["source"],
        "reason": row["reason"],
    } for row in in_library_records() if row["format"] == _FORMAT_SAFETENSORS]
