"""Read GGUF model metadata and tensor sizes without loading the model (sharded inference P2).

The memory planner needs a model's real shape - layers, KV heads, key/value widths, expert counts,
the training context - and the actual byte size of every tensor, to decide how much of the model
fits on the GPU and what stays in system RAM. GGUF puts all of that in its header; this reads only
the header (a few MB at most), never the weights. Stdlib only.

Tensor sizes are taken from the data offsets GGUF records (each tensor runs to the next one's offset;
the last runs to the end of the file), so no quantization-type size table is needed and new types are
handled without code changes.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

GGUF_MAGIC = b"GGUF"
_DEFAULT_ALIGNMENT = 32
_MAX_STRING = 1 << 24
_MAX_ARRAY = 1 << 24

# GGUF metadata value types.
_UINT8, _INT8, _UINT16, _INT16, _UINT32, _INT32, _FLOAT32, _BOOL, _STRING, _ARRAY, _UINT64, \
    _INT64, _FLOAT64 = range(13)
_SCALARS = {
    _UINT8: "<B", _INT8: "<b", _UINT16: "<H", _INT16: "<h", _UINT32: "<I", _INT32: "<i",
    _FLOAT32: "<f", _BOOL: "<?", _UINT64: "<Q", _INT64: "<q", _FLOAT64: "<d",
}
_LAYER_RE = re.compile(r"^blk\.(\d+)\.")
_EXPERT_RE = re.compile(r"_exps\b|\.ffn_(gate|up|down)_exps\.")


class GGUFError(ValueError):
    """Not a readable GGUF file (fail closed: the planner refuses to guess)."""


@dataclass(frozen=True)
class TensorInfo:
    name: str
    offset: int
    size: int
    layer: int | None
    expert: bool


@dataclass
class GGUFModel:
    path: str
    file_size: int
    version: int
    metadata: dict[str, Any]
    tensors: list[TensorInfo] = field(default_factory=list)

    # --- shape -----------------------------------------------------------------------------------
    @property
    def architecture(self) -> str:
        return str(self.metadata.get("general.architecture") or "")

    def arch_value(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(f"{self.architecture}.{key}", default)

    @property
    def block_count(self) -> int:
        return int(self.arch_value("block_count") or 0)

    @property
    def context_length(self) -> int | None:
        value = self.arch_value("context_length")
        return int(value) if value is not None else None

    @property
    def expert_count(self) -> int:
        return int(self.arch_value("expert_count") or 0)

    @property
    def expert_used_count(self) -> int:
        return int(self.arch_value("expert_used_count") or 0)

    @property
    def is_moe(self) -> bool:
        return self.expert_count > 1

    def kv_bytes_per_token(self, bytes_per_element: float) -> int:
        """KV cache bytes per token across all attention layers (an UPPER bound).

        key/value widths come from ``attention.key_length`` / ``value_length`` when present,
        else embedding_length / head_count. Architectures that interleave non-attention (linear /
        recurrent) layers keep less KV than this; when the file declares a full-attention
        interval, only those layers are counted.
        """
        heads_kv = self.arch_value("attention.head_count_kv")
        heads = self.arch_value("attention.head_count")
        if isinstance(heads_kv, list):
            heads_kv = max(heads_kv) if heads_kv else 0
        if isinstance(heads, list):
            heads = max(heads) if heads else 0
        heads_kv = int(heads_kv or heads or 0)
        embedding = int(self.arch_value("embedding_length") or 0)
        head_dim = (embedding // int(heads)) if heads else 0
        key_len = int(self.arch_value("attention.key_length") or head_dim)
        value_len = int(self.arch_value("attention.value_length") or key_len)
        layers = self.attention_layer_count
        return int(layers * heads_kv * (key_len + value_len) * bytes_per_element)

    @property
    def attention_layer_count(self) -> int:
        interval = self.arch_value("full_attention_interval")
        if isinstance(interval, int) and interval > 1:
            return max(1, self.block_count // interval)
        return self.block_count

    # --- sizes -----------------------------------------------------------------------------------
    def layer_bytes(self, layer: int, *, experts: bool | None = None) -> int:
        return sum(t.size for t in self.tensors if t.layer == layer
                   and (experts is None or t.expert == experts))

    @property
    def non_layer_bytes(self) -> int:
        return sum(t.size for t in self.tensors if t.layer is None)

    @property
    def expert_bytes(self) -> int:
        return sum(t.size for t in self.tensors if t.expert)

    @property
    def tensor_bytes(self) -> int:
        return sum(t.size for t in self.tensors)


def _read(handle: BinaryIO, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    data = handle.read(size)
    if len(data) != size:
        raise GGUFError("truncated GGUF header")
    return struct.unpack(fmt, data)[0]


def _read_string(handle: BinaryIO) -> str:
    length = _read(handle, "<Q")
    if length > _MAX_STRING:
        raise GGUFError("GGUF string too long")
    data = handle.read(length)
    if len(data) != length:
        raise GGUFError("truncated GGUF string")
    return data.decode("utf-8", errors="replace")


def _read_value(handle: BinaryIO, value_type: int, *, keep_arrays: bool) -> Any:
    if value_type in _SCALARS:
        return _read(handle, _SCALARS[value_type])
    if value_type == _STRING:
        return _read_string(handle)
    if value_type == _ARRAY:
        item_type = _read(handle, "<I")
        count = _read(handle, "<Q")
        if count > _MAX_ARRAY:
            raise GGUFError("GGUF array too long")
        if not keep_arrays and item_type in _SCALARS:
            # Skip large arrays (vocabularies, merges) without materializing them.
            handle.seek(count * struct.calcsize(_SCALARS[item_type]), 1)
            return None
        items = [_read_value(handle, item_type, keep_arrays=keep_arrays) for _ in range(count)]
        return items if keep_arrays else None
    raise GGUFError(f"unknown GGUF value type {value_type}")


def read_gguf(path: str | Path) -> GGUFModel:
    """Parse a GGUF header: metadata (small arrays kept) and per-tensor byte sizes."""
    path = Path(path)
    try:
        file_size = path.stat().st_size
        handle = path.open("rb")
    except OSError as exc:
        raise GGUFError(f"cannot open {path}: {exc}") from exc
    with handle:
        if handle.read(4) != GGUF_MAGIC:
            raise GGUFError(f"{path} is not a GGUF file")
        version = _read(handle, "<I")
        if version < 2:
            raise GGUFError(f"unsupported GGUF version {version}")
        tensor_count = _read(handle, "<Q")
        kv_count = _read(handle, "<Q")
        metadata: dict[str, Any] = {}
        for _ in range(kv_count):
            key = _read_string(handle)
            value_type = _read(handle, "<I")
            # Keep small arrays (per-layer head counts); skip vocab-sized ones.
            keep = not key.startswith("tokenizer.")
            metadata[key] = _read_value(handle, value_type, keep_arrays=keep)
        raw = []
        for _ in range(tensor_count):
            name = _read_string(handle)
            dims = _read(handle, "<I")
            handle.seek(8 * dims, 1)
            _ggml_type = _read(handle, "<I")
            offset = _read(handle, "<Q")
            raw.append((name, offset))
        alignment = int(metadata.get("general.alignment") or _DEFAULT_ALIGNMENT)
        header_end = handle.tell()
    data_start = (header_end + alignment - 1) // alignment * alignment
    raw.sort(key=lambda item: item[1])
    tensors = []
    for index, (name, offset) in enumerate(raw):
        end = raw[index + 1][1] if index + 1 < len(raw) else file_size - data_start
        match = _LAYER_RE.match(name)
        tensors.append(TensorInfo(
            name=name, offset=offset, size=max(0, end - offset),
            layer=int(match.group(1)) if match else None,
            expert=bool(_EXPERT_RE.search(name))))
    return GGUFModel(path=str(path), file_size=file_size, version=version, metadata=metadata,
                     tensors=tensors)
