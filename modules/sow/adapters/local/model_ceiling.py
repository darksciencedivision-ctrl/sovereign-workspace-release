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

#: EPC-02, operator correction: "It's not an eight billion parameter ceiling. The system is
#: agnostically scalable... It needs to be able to read a system and know how it needs to run.
#: But there is no ceiling on what it can run."
#:
#: So 8 was never a rule of the product. It was a fact about ONE machine - this host's 8 GB
#: card - written into the code as though it were policy, down to refusal messages citing
#: "the operator's 8B ceiling (ENTRY 017)". On a 24 GB card the same code would have reached
#: the same wrong conclusion with nobody noticing the constant was a local accident.
#:
#: What is DERIVED from the hardware actually present is the ADVISORY - what this card costs a
#: model that straddles it. That is the honest use of a measurement.
#:
#: It is NOT where the enforced ceiling comes from. It briefly was, and that produced a refusal
#: quoting a VRAM-derived figure (11B on this host) while comparing against a hardcoded 9.0e9 -
#: two numbers nothing kept in agreement. The enforced bound is declared at `CEILING_ENV` below.
#:
#: THE SPLIT THAT MATTERS. Hardware detection RECOMMENDS; it never selects. The operator pins
#: the slate. A model larger than the card is offered with a measured advisory saying what it
#: will cost, never withheld. The only thing still REFUSED outright is a model that would leave
#: this host, which is spend, not capacity, and is checked before any of this.
VRAM_ENV = "SOVEREIGN_VRAM_MIB"

#: Fallback when the hardware cannot be read. Chosen to match the historical constant so an
#: undetectable host behaves exactly as this code did before detection existed - a detection
#: failure must not silently change what the system recommends.
_FALLBACK_VRAM_MIB = 8192

#: Roughly the VRAM a Q4-quantised model needs per billion parameters, plus context overhead.
#: Deliberately approximate: this produces a RECOMMENDATION, and a recommendation that pretends
#: to more precision than the estimate supports would be worse than one that admits its basis.
_MIB_PER_BILLION_PARAMS = 700


def _detect_vram_mib() -> tuple[int, str]:
    """Total VRAM on the largest visible GPU, and how it was learned.

    Never raises: this runs on the operator's display path, and a detection helper must not be
    able to take a selector down. An unreadable host falls back and SAYS it fell back.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    override = (os.environ.get(VRAM_ENV) or "").strip()
    if override:
        try:
            value = int(override)
            if value > 0:
                return value, f"{VRAM_ENV}={value}"
        except ValueError:
            pass

    executable = shutil.which("nvidia-smi")
    if executable:
        try:
            result = subprocess.run(
                [executable, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20, check=False,
            )
            sizes = [int(line.strip()) for line in result.stdout.splitlines()
                     if line.strip().isdigit()]
            if sizes:
                return max(sizes), "nvidia-smi"
            # nvidia-smi ran and did NOT report a size. It writes NVML failures to stdout with a
            # non-zero return, so an empty size list here is a FAILED measurement, not an absent
            # GPU, and saying "not detected" would hide a fixable host problem.
            return _FALLBACK_VRAM_MIB, "nvidia-smi ran but reported no size; measurement failed"
        except (OSError, ValueError, subprocess.SubprocessError):
            return _FALLBACK_VRAM_MIB, "nvidia-smi could not be run; measurement failed"

    return _FALLBACK_VRAM_MIB, "not detected; assuming the historical default"


def hardware_profile() -> dict:
    """What this machine can comfortably run, measured rather than assumed."""
    vram_mib, source = _detect_vram_mib()
    comfortable_b = max(1.0, round(vram_mib / _MIB_PER_BILLION_PARAMS, 1))
    return {
        "vram_mib": vram_mib,
        "source": source,
        "comfortable_parameters_b": comfortable_b,
        "comfortable_parameters": comfortable_b * 1e9,
    }


#: The environment variable that sets the ENFORCED ceiling, as a nameplate class in billions.
#: Absent means ENTRY 017's eight.
#:
#: WHY THIS EXISTS (the defect it repairs). The enforced ceiling used to be TWO independent
#: numbers that nothing kept in agreement: `CEILING_NAMEPLATE_B` was derived from VRAM, while the
#: comparison below used a hardcoded `9.0e9`. On this host that produced a refusal reading
#: "ornith-1.5:9b has 9.0B parameters, above the operator's 11B ceiling" — a sentence stating a
#: threshold that was not the one applied, in the one place whose whole job is to justify a
#: refusal. The same split reached evidence: `enumerate_pane_picker` recorded `nameplate_b: 11`
#: under `authority: ENTRY 017`, attributing to that ruling a figure it does not contain.
#:
#: It also meant the ceiling could not be SET. Lowering `SOVEREIGN_VRAM_MIB` moved the displayed
#: nameplate and changed nothing about admission, so a run asked to stay at or under 4B still
#: admitted every 8B-class model in the library while reporting a 4B ceiling.
#:
#: WHAT DERIVES FROM HARDWARE AND WHAT DOES NOT (EPC-02, ENTRY 030/032). Hardware detection
#: RECOMMENDS and never selects: for the OPERATOR there is no ceiling at all, only the measured
#: advisory below, which still comes from `hardware_profile`. The TESTING refusal is a RULE, and a
#: rule's threshold is declared, not measured — deriving it from whichever card is installed was
#: the conflation. `hardware_profile` is untouched and keeps reporting what this machine measures.
CEILING_ENV = "SOVEREIGN_MODEL_CEILING_B"

#: ENTRY 017's figure, used when `CEILING_ENV` is absent or unreadable. Fail SAFE rather than
#: closed here: an unparseable value falls back to the declared default rather than raising on a
#: display path, matching how `resolve_audience` treats a typo.
_DEFAULT_CEILING_NAMEPLATE_B = 8


def resolve_ceiling_nameplate_b() -> int:
    """The enforced nameplate class in billions. Explicit environment wins; else ENTRY 017's 8."""
    import os  # noqa: PLC0415 - kept local so this module stays import-cheap for the UI path
    raw = (os.environ.get(CEILING_ENV) or "").strip()
    if raw:
        try:
            # OverflowError as well as ValueError: `float("inf")` parses, and `int(inf)` raises
            # OverflowError rather than ValueError. This runs on the operator's display path, so
            # every unreadable spelling has to land on the default instead of raising (W-36).
            value = int(float(raw))
            if value > 0:
                return value
        except (ValueError, OverflowError):
            pass
    return _DEFAULT_CEILING_NAMEPLATE_B


#: The nameplate class the refusal sentence QUOTES and the comparison below APPLIES — one number,
#: so the two can no longer disagree.
CEILING_NAMEPLATE_B = resolve_ceiling_nameplate_b()

#: The nameplate class expressed as a bound on the TRUE parameter count, derived from the nameplate
#: rather than written down beside it. At the default 8 this is 9.0e9 — exactly the value that was
#: hardcoded here — so it admits the whole 8B nameplate class (qwen3:8b at 8.2B, granite4.2:8b at
#: 8.8B) and refuses the 9B class upward, unchanged. At a nameplate of 4 it becomes 5.0e9 and the
#: 4B class is genuinely the top of the slate.
_TRUE_PARAM_LIMIT = (CEILING_NAMEPLATE_B + 1.0) * 1e9

#: EPC-02 B-2 (ENTRY 030/032). WHO is being served decides whether the ceiling REFUSES or WARNS.
#:
#: The ceiling's reason is hardware - 8 GB of VRAM, and a larger model straddles it and runs
#: partly on the CPU. That caveat is true for everyone and is never dropped. But it was
#: implemented as a global REFUSAL, which locked the operator out of 52 of his own 60 installed
#: models. His ruling (ENTRY 030): "You're only bound by the eight billion local models when
#: you're doing the testing, not me."
#:
#: So the same authority answers two audiences:
#:   OPERATOR  - an over-ceiling model is ADMITTED and carries an ADVISORY naming the cost.
#:               Choosing a slow model is his call to make; hiding it was not.
#:   TESTING   - an over-ceiling model is REFUSED, exactly as before. Automated runs stay fast,
#:               deterministic, and inside the VRAM envelope.
#:
#: What is NOT audience-dependent, at any setting: a model with no local weights (an Ollama
#: Cloud pointer - selecting it leaves the host and becomes provider spend), a model that
#: cannot hold a conversation, and a model whose size cannot be read. Those refusals come
#: BEFORE the ceiling and are proven independent of it by mutation in the test suite.
AUDIENCE_OPERATOR = "operator"
AUDIENCE_TESTING = "testing"

#: The environment variable an automated run sets to bind itself to the ceiling. Absent means
#: OPERATOR: a fresh install serves the person who owns the machine, and a test harness must
#: opt IN to the stricter rule rather than rely on a default it might not get.
AUDIENCE_ENV = "SOVEREIGN_MODEL_AUDIENCE"


def resolve_audience(audience: str | None = None) -> str:
    """The audience in force. Explicit argument wins; then the environment; then OPERATOR."""
    import os  # noqa: PLC0415 - kept local so this module stays import-cheap for the UI path
    if audience:
        return AUDIENCE_TESTING if audience == AUDIENCE_TESTING else AUDIENCE_OPERATOR
    value = (os.environ.get(AUDIENCE_ENV) or "").strip().lower()
    return AUDIENCE_TESTING if value == AUDIENCE_TESTING else AUDIENCE_OPERATOR


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
    #: EPC-02 B-2. Non-empty when the model is ADMITTED but carries a cost the operator should
    #: see before choosing it - today, only the VRAM straddle above the 8B nameplate class. An
    #: advisory never withholds a model; it is the honest half of no longer refusing one.
    #: Last, and defaulted, so every existing positional construction stays valid.
    advisory: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "admitted": self.admitted, "reason": self.reason,
            "advisory": self.advisory,
            "parameters": self.parameters, "parameter_size": self.parameter_size,
            "family": self.family, "quantization": self.quantization,
            "size_bytes": self.size_bytes, "capabilities": list(self.capabilities),
        }


def classify_local_model(record: Mapping[str, Any],
                         audience: str | None = None) -> LocalModelVerdict:
    """Admit or refuse ONE `/api/tags` record against the operator's ceiling.

    `record` is a row as `adapters.detect.ollama_model_records` returns it. Anything malformed is
    refused with a reason rather than raising: this runs on the operator's display path, and a
    detection helper must not be able to take a selector down (the W-36 rule `ollama_models`
    already follows).
    """
    audience = resolve_audience(audience)
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

    def verdict(admitted: bool, reason: str, advisory: str = "") -> LocalModelVerdict:
        return LocalModelVerdict(
            name=name, admitted=admitted, reason=reason, parameters=parameters,
            parameter_size=parameter_size if isinstance(parameter_size, str) else None,
            family=family, quantization=quantization, size_bytes=size_bytes,
            advisory=advisory, capabilities=capabilities)

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
        profile = hardware_profile()
        # The MEASURED half, true for both audiences and never dropped. It says what the hardware
        # costs and nothing about anyone's rule — so it can be handed to the operator as an
        # advisory without asserting a ceiling that does not bind him.
        straddle = (
            f"{name} has {shown} parameters. "
            f"Measured on this host: {profile['vram_mib']} MiB of VRAM ({profile['source']}), "
            f"comfortable to about {profile['comfortable_parameters_b']}B parameters. A larger "
            f"model straddles the card and runs partly on the CPU — expect it to be slow. "
            f"This is a RECOMMENDATION derived from the hardware present, not a rule: the "
            f"operator pins the slate.")
        if audience == AUDIENCE_TESTING:
            # Automated runs stay deterministic and inside a DECLARED bound. The refusal names
            # its authority (ENTRY 017) because a refused operator must be able to see WHOSE rule
            # refused him, and it names the ceiling it actually applied — `CEILING_NAMEPLATE_B` is
            # now the same number the comparison above used, so this sentence can no longer quote
            # a threshold that is not the one enforced. The advisory branch below deliberately
            # names no rule at all: for the operator there is only measured hardware.
            return verdict(False, straddle + (
                f" Refused for automated testing under ENTRY 017: above the {CEILING_NAMEPLATE_B}B "
                f"ceiling in force ({AUDIENCE_ENV}={AUDIENCE_TESTING}, {CEILING_ENV}="
                f"{CEILING_NAMEPLATE_B}); the operator's own selectors offer it."))
        # OPERATOR: his machine, his model, his call. The cost is named, not used to withhold.
        return verdict(True, "", advisory=straddle)

    return verdict(True, "")


def classify_local_models(records: Iterable[Mapping[str, Any]],
                          audience: str | None = None) -> list[LocalModelVerdict]:
    """Classify a whole enumeration, deterministically ordered by model name."""
    resolved = resolve_audience(audience)
    return sorted((classify_local_model(r, resolved) for r in records or ()),
                  key=lambda v: v.name)


def advisories_by_name(verdicts: Iterable[LocalModelVerdict]) -> dict[str, str]:
    """`{model tag: caveat}` for every ADMITTED model that carries one.

    Disjoint from `reasons_by_name` by construction: a refused model has a reason and no
    advisory, an admitted one may have an advisory and never a reason. A selector greys with
    the first map and annotates with the second, so "offered" and "offered with a warning"
    stay visibly different states rather than collapsing into each other.
    """
    return {v.name: v.advisory for v in verdicts if v.admitted and v.advisory}


def admitted_names(verdicts: Iterable[LocalModelVerdict]) -> list[str]:
    """Just the tags a selector may offer as runnable, in the order they were classified."""
    return [v.name for v in verdicts if v.admitted]


def reasons_by_name(verdicts: Iterable[LocalModelVerdict]) -> dict[str, str]:
    """`{model tag: refusal sentence}` for every REFUSED model — the map a selector greys with.

    Admitted models are absent from this map, so `map.get(name)` is None exactly when the model is
    offered, which is the shape `_local_options` already uses for `unavailable_reason`.
    """
    return {v.name: v.reason for v in verdicts if not v.admitted}
