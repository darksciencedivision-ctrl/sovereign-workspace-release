"""The operator's LOCAL MODEL CEILING — one authority, used by every selector (S-20, ENTRY 017).

ENTRY 017, in the operator's words: *"We do not wanna use anything above eight billion parameters
in our local library, but let's prove this system works."* ENTRY 017 also directs that models
already installed above the ceiling are **"excluded from selection with a stated reason, not
silently hidden"**, which is S-19 (honest degradation) applied to model choice.

This module is the ONLY place that decision is made. The picker, the Conductor, Debate and
SOVEREIGN all classify through `classify_local_model` so a model cannot be admissible in one
surface and refused in another — S-20's "every local model within the ceiling" has to mean the
same set everywhere, or the agnosticism it mandates is only nominal.

It decides nothing about *availability* (that is the VRAM residency planner's job) and it never
contacts the daemon itself: it is a pure function over records `adapters.detect.ollama_model_records`
already read from `/api/tags`. Pure so the headless suite can pin every branch without a host.

FOUR EXCLUSION CLASSES, in the order they are tested, each with operator-readable text:

  1. **not local weights** — Ollama Cloud rows (`deepseek-v4-pro:cloud`, `glm-5.2:cloud`) are
     manifest pointers of a few hundred bytes that execute on ollama.com. They are not local
     operation and they fall under the frontier authorization the operator has DENIED (OD-31).
     Tested by on-disk footprint, not by tag spelling: a `:cloud` suffix is a naming convention,
     while "carries no weights" is the fact that makes it non-local. The same test catches a model
     whose blobs are missing.
  2. **cannot hold a conversation** — an embedding model emits vectors, not replies. The daemon
     declares this itself in `capabilities`; we read its answer rather than guessing from the
     family name. Offering one would breach S-19's "no model offered that cannot run".
  3. **parameter count unreadable** — fail closed. A model whose size cannot be established cannot
     be shown to be under a size ceiling.
  4. **over the ceiling** — with the model's TRUE parameter count named in the reason, so the
     operator sees the real number rather than a nameplate.

ON THE 8.2B QUESTION, recorded because it is a real tension in the ruling and not a detail.
ENTRY 017 sets "no model above eight billion parameters" AND directs "Use the eight billion
parameters one so we can run through tests." The model it means — `qwen3:8b`, the same tag
punch-list S-8 pins for Debate — actually carries **8.2B** parameters. Read as a strict arithmetic
bound on the true count, the ceiling would exclude the very model the operator named to prove the
system with.

So the ceiling is the **8B nameplate class**: admitted when the vendor nameplate is 8B or smaller,
with the TRUE count always displayed so nothing is concealed. `_TRUE_PARAM_LIMIT` implements it.
On the operator's library the two readings select an identical set (nameplate <= 8B and true < 9.0B
both admit exactly the same models), so this choice changes no behaviour today; it is written down
because it would matter on a library holding a 9B-nameplate model. Moving to a strict 8.0B bound is
a one-line change here — and would drop `qwen3:8b` itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

#: The operator's ceiling, as the nameplate the vendor prints (ENTRY 017).
CEILING_NAMEPLATE_B = 8

#: The nameplate class expressed as a bound on the TRUE parameter count. 9.0e9 admits the whole 8B
#: nameplate class (qwen3:8b at 8.2B, granite4.2:8b at 8.8B) and refuses the 9B class upward.
_TRUE_PARAM_LIMIT = 9.0e9

#: Below this, a row carries no weights: it is an Ollama Cloud pointer (a few hundred bytes) or a
#: model whose blobs are absent. The smallest real local model in the operator's library is 274 MB.
_MIN_LOCAL_WEIGHTS_BYTES = 64 * 1024 * 1024

#: The capability the daemon reports for a model that can answer a typed message.
_CHAT_CAPABILITY = "completion"

_PARAM_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMBT])?\s*$", re.I)
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12, "": 1.0}


def parse_parameter_count(raw: Any) -> float | None:
    """`"8.2B"` -> 8.2e9. Returns None for anything unparseable — never a guess, never 0.

    0 would be indistinguishable from "a very small model" and would sail under the ceiling; None
    is the honest answer and is refused by class 3 above.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else None
    if not isinstance(raw, str):
        return None
    m = _PARAM_RE.match(raw)
    if not m:
        return None
    value = float(m.group(1)) * _SUFFIX[(m.group(2) or "").upper()]
    return value if value > 0 else None


def format_parameter_count(params: float | None) -> str:
    """A human figure for a reason string. `8.2e9` -> `8.2B`."""
    if params is None:
        return "an unknown number of"
    for suffix, unit in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if params >= unit:
            return f"{params / unit:.6g}{suffix}"
    return f"{params:.6g}"


@dataclass(frozen=True)
class LocalModelVerdict:
    """One model's admission decision, and the sentence the operator reads when it is refused."""

    name: str
    admitted: bool
    reason: str                      # "" when admitted
    parameters: float | None
    parameter_size: str | None       # the daemon's own string, e.g. "8.2B"
    family: str | None
    quantization: str | None
    size_bytes: int
    capabilities: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "admitted": self.admitted, "reason": self.reason,
            "parameters": self.parameters, "parameter_size": self.parameter_size,
            "family": self.family, "quantization": self.quantization,
            "size_bytes": self.size_bytes, "capabilities": list(self.capabilities),
        }


def classify_local_model(record: Mapping[str, Any]) -> LocalModelVerdict:
    """Admit or refuse ONE `/api/tags` record against the operator's ceiling.

    `record` is a row as `adapters.detect.ollama_model_records` returns it. Anything malformed is
    refused with a reason rather than raising: this runs on the operator's display path, and a
    detection helper must not be able to take a selector down (the W-36 rule `ollama_models`
    already follows).
    """
    name = str((record or {}).get("name") or "").strip()
    details = (record or {}).get("details") or {}
    if not isinstance(details, Mapping):
        details = {}
    parameter_size = details.get("parameter_size")
    parameters = parse_parameter_count(parameter_size)
    family = details.get("family") or None
    quantization = details.get("quantization_level") or None
    raw_caps = (record or {}).get("capabilities") or ()
    capabilities = tuple(str(c) for c in raw_caps if isinstance(c, str))
    try:
        size_bytes = int((record or {}).get("size") or 0)
    except (TypeError, ValueError):
        size_bytes = 0

    def verdict(admitted: bool, reason: str) -> LocalModelVerdict:
        return LocalModelVerdict(
            name=name, admitted=admitted, reason=reason, parameters=parameters,
            parameter_size=parameter_size if isinstance(parameter_size, str) else None,
            family=family, quantization=quantization, size_bytes=size_bytes,
            capabilities=capabilities)

    if not name:
        return verdict(False, "this row carries no model name — refused (fail closed)")

    # 1. Carries no local weights: an Ollama Cloud pointer, or blobs that are not on this disk.
    if size_bytes < _MIN_LOCAL_WEIGHTS_BYTES:
        return verdict(False, (
            f"{name} holds no model weights on this machine ({size_bytes} bytes on disk). It is a "
            f"pointer to a model that runs remotely on Ollama Cloud, so selecting it would leave "
            f"this host — that is frontier operation, which the operator has not authorized "
            f"(live_operation.json is deliberately absent). Local models only in this build."))

    # 2. Cannot hold a conversation. The daemon's own capability list is the authority.
    if capabilities and _CHAT_CAPABILITY not in capabilities:
        kind = "/".join(capabilities)
        return verdict(False, (
            f"{name} is an {kind} model ({format_parameter_count(parameters)} parameters, family "
            f"{family or 'unknown'}). It turns text into vectors and cannot answer a typed "
            f"message, so it is not offered as something to talk to."))

    # 3. Unreadable size — fail closed rather than assume it is small.
    if parameters is None:
        return verdict(False, (
            f"{name} does not report a parameter count, so it cannot be shown to be within the "
            f"operator's {CEILING_NAMEPLATE_B}B ceiling. Refused rather than assumed (fail closed)."))

    # 4. Over the ceiling, with the true count named. The daemon's OWN string is quoted verbatim
    # when it has one, so the figure the operator reads here is the figure `ollama list` shows him
    # — reformatting 9.0B into 9B would be a small dishonesty in the one sentence that has to
    # justify refusing his model.
    if parameters >= _TRUE_PARAM_LIMIT:
        shown = parameter_size if isinstance(parameter_size, str) and parameter_size.strip() \
            else format_parameter_count(parameters)
        return verdict(False, (
            f"{name} has {shown} parameters, above the operator's "
            f"{CEILING_NAMEPLATE_B}B ceiling (ENTRY 017). This host's GPU carries 8 GB of VRAM and "
            f"a larger model straddles it, running partly on the CPU. Installed and kept — not "
            f"selectable in this build."))

    return verdict(True, "")


def classify_local_models(records: Iterable[Mapping[str, Any]]) -> list[LocalModelVerdict]:
    """Classify a whole enumeration, deterministically ordered by model name."""
    return sorted((classify_local_model(r) for r in records or ()), key=lambda v: v.name)


def admitted_names(verdicts: Iterable[LocalModelVerdict]) -> list[str]:
    """Just the tags a selector may offer as runnable, in the order they were classified."""
    return [v.name for v in verdicts if v.admitted]


def reasons_by_name(verdicts: Iterable[LocalModelVerdict]) -> dict[str, str]:
    """`{model tag: refusal sentence}` for every REFUSED model — the map a selector greys with.

    Admitted models are absent from this map, so `map.get(name)` is None exactly when the model is
    offered, which is the shape `_local_options` already uses for `unavailable_reason`.
    """
    return {v.name: v.reason for v in verdicts if not v.admitted}
