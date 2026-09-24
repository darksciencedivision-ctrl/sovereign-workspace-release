"""End-to-end performance qualification of SOVEREIGN inference profiles (SW-27).

The finding: the only benchmark was a direct Ollama call (qwen3:8b, ctx 2048, 35 tokens). Nothing
qualified the declared context/output, DEEP workflows, concurrency, llama.cpp, or cold-vs-warm
behaviour *through the product*. This module is the qualification contract:

* **Profiles** (shipped, immutable): ``<install root>/qualification/profiles.json`` names each
  supported profile (backend + primary model), what it declares, the measurement ladder, and the
  service-level objectives a measurement must meet.
* **Results** (``qualification_harness.run``): one JSON per run, measured end-to-end through the
  running product's own HTTP API - cold and warm QUICK, varied prompts, an increasing-context ladder,
  concurrent jobs, cancellation, and DEEP (model swaps across the slate) - with peak VRAM/RAM.
* **Envelope** (per machine, in the state home): ``derive`` turns results into the largest context
  and concurrency that met the SLOs on THIS hardware, plus the p50/p95 latency, throughput, peak
  memory and failure rates that are published with it.
* **Gate** (``evaluate``): a configuration that EXCEEDS a measured envelope is REJECTED - the product
  reports itself degraded and refuses new jobs until it is re-qualified or reconfigured. A dimension
  that was never measured is reported UNQUALIFIED, never silently passed and never used to refuse.

Stdlib only; ``python -m sovereign_product.qualification --help``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .paths import resolve_state_home

PROFILES_RELATIVE = ("qualification", "profiles.json")
ENVELOPE_RELATIVE = ("qualification", "envelope.json")
PROFILES_SCHEMA = "sovereign.qualification-profiles.v1"
RESULTS_SCHEMA = "sovereign.qualification-results.v1"
ENVELOPE_SCHEMA = "sovereign.qualification-envelope.v1"

QUALIFIED = "qualified"
UNQUALIFIED = "unqualified"
REJECTED = "rejected"

_SLO_KEYS = ("max_failure_rate", "quick_p95_seconds", "deep_p95_seconds", "cancel_p95_seconds")


class QualificationError(ValueError):
    """A profile, results or envelope document is malformed (fail closed)."""


# --- profiles -------------------------------------------------------------------------------------

def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QualificationError(f"{label} must be a positive integer")
    return value


def validate_profiles(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("schema") != PROFILES_SCHEMA:
        raise QualificationError(f"profiles document must declare schema {PROFILES_SCHEMA}")
    slo = doc.get("slo")
    if not isinstance(slo, dict):
        raise QualificationError("profiles.slo must be an object")
    for key in _SLO_KEYS:
        value = slo.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise QualificationError(f"profiles.slo.{key} must be a positive number")
    if slo["max_failure_rate"] >= 1:
        raise QualificationError("profiles.slo.max_failure_rate must be below 1")
    profiles = doc.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise QualificationError("profiles.profiles must be a non-empty list")
    seen = set()
    for index, profile in enumerate(profiles):
        label = f"profiles[{index}]"
        if not isinstance(profile, dict):
            raise QualificationError(f"{label} must be an object")
        for key in ("id", "backend", "primary_model"):
            if not isinstance(profile.get(key), str) or not profile[key].strip():
                raise QualificationError(f"{label}.{key} must be non-empty text")
        if profile["id"] in seen:
            raise QualificationError(f"duplicate profile id {profile['id']!r}")
        seen.add(profile["id"])
        declared = profile.get("declared")
        if not isinstance(declared, dict):
            raise QualificationError(f"{label}.declared must be an object")
        for key in ("context_tokens", "max_output_tokens", "concurrent_jobs"):
            _positive_int(declared.get(key), f"{label}.declared.{key}")
        ladder = profile.get("ladder")
        if not isinstance(ladder, dict):
            raise QualificationError(f"{label}.ladder must be an object")
        for key in ("context_tokens", "concurrency"):
            steps = ladder.get(key)
            if not isinstance(steps, list) or not steps:
                raise QualificationError(f"{label}.ladder.{key} must be a non-empty list")
            values = [_positive_int(v, f"{label}.ladder.{key}[]") for v in steps]
            if values != sorted(set(values)):
                raise QualificationError(f"{label}.ladder.{key} must be strictly ascending")
        _positive_int(ladder.get("repetitions"), f"{label}.ladder.repetitions")
    return doc


def load_profiles(root: str | os.PathLike[str] | Path) -> dict[str, Any]:
    path = Path(root).joinpath(*PROFILES_RELATIVE)
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise QualificationError(f"no qualification profiles shipped at {path}") from exc
    except (OSError, ValueError) as exc:
        raise QualificationError(f"{path} is unreadable: {exc}") from exc
    return validate_profiles(doc)


def _normalize_backend(value: str) -> str:
    text = str(value or "").strip().lower()
    return "llama.cpp" if text in ("llamacpp", "llama_cpp", "llama-cpp") else text


def find_profile(profiles: Mapping[str, Any], backend: str,
                 primary_model: str) -> dict[str, Any] | None:
    for profile in profiles.get("profiles", []):
        if (_normalize_backend(profile["backend"]) == _normalize_backend(backend)
                and profile["primary_model"] == primary_model):
            return profile
    return None


# --- statistics -----------------------------------------------------------------------------------

def percentile(values: Iterable[float], q: float) -> float | None:
    """Nearest-rank percentile (q in (0, 100]); None for no samples."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return None
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarize_runs(runs: list[Mapping[str, Any]]) -> dict[str, Any]:
    completed = [r for r in runs if r.get("status") == "completed"]
    failed = [r for r in runs if r.get("status") not in ("completed", "cancelled")]
    latencies = [r["latency_seconds"] for r in completed if isinstance(r.get("latency_seconds"),
                                                                        (int, float))]
    tokens = [r.get("tokens") for r in completed if isinstance(r.get("tokens"), int)]
    tok_rates = [r["tokens"] / r["latency_seconds"] for r in completed
                 if isinstance(r.get("tokens"), int) and r.get("latency_seconds")]
    return {
        "runs": len(runs),
        "completed": len(completed),
        "failed": len(failed),
        "failure_rate": (len(failed) / len(runs)) if runs else None,
        "latency_p50_seconds": percentile(latencies, 50),
        "latency_p95_seconds": percentile(latencies, 95),
        "latency_max_seconds": max(latencies) if latencies else None,
        "tokens_max": max(tokens) if tokens else None,
        "throughput_tokens_per_second_p50": percentile(tok_rates, 50),
    }


# --- envelope -------------------------------------------------------------------------------------

def _passes(summary: Mapping[str, Any], slo: Mapping[str, Any], p95_key: str) -> bool:
    return (summary["runs"] > 0
            and summary["failure_rate"] is not None
            and summary["failure_rate"] <= slo["max_failure_rate"]
            and summary["latency_p95_seconds"] is not None
            and summary["latency_p95_seconds"] <= slo[p95_key])


def derive_envelope(results: Mapping[str, Any], profiles: Mapping[str, Any]) -> dict[str, Any]:
    """The measured envelope: the largest ladder steps that met the SLOs, contiguously."""
    if not isinstance(results, Mapping) or results.get("schema") != RESULTS_SCHEMA:
        raise QualificationError(f"results must declare schema {RESULTS_SCHEMA}")
    profile = next((p for p in profiles["profiles"] if p["id"] == results.get("profile")), None)
    if profile is None:
        raise QualificationError(f"results are for unknown profile {results.get('profile')!r}")
    slo = profiles["slo"]
    runs = results.get("runs")
    if not isinstance(runs, list):
        raise QualificationError("results.runs must be a list")

    def pick(**match: Any) -> list[Mapping[str, Any]]:
        return [r for r in runs if all(r.get(k) == v for k, v in match.items())]

    scenarios: dict[str, Any] = {}
    # Every ladder step is REPORTED; only the contiguous run of passing steps from the bottom
    # counts toward the limit. An unmeasured step ends the run - it is never extrapolated.
    context_limit, contiguous = 0, True
    for step in profile["ladder"]["context_tokens"]:
        summary = summarize_runs(pick(scenario="context", context_tokens=step))
        scenarios[f"context_{step}"] = summary
        contiguous = contiguous and _passes(summary, slo, "quick_p95_seconds")
        if contiguous:
            context_limit = step
    concurrency_limit, contiguous = 0, True
    for level in profile["ladder"]["concurrency"]:
        summary = summarize_runs(pick(scenario="concurrency", concurrency=level))
        scenarios[f"concurrency_{level}"] = summary
        contiguous = contiguous and _passes(summary, slo, "quick_p95_seconds")
        if contiguous:
            concurrency_limit = level
    for name in ("quick_cold", "quick_warm", "deep"):
        scenarios[name] = summarize_runs(pick(scenario=name))
    cancel = pick(scenario="cancel")
    cancel_latencies = [r["cancel_latency_seconds"] for r in cancel
                        if isinstance(r.get("cancel_latency_seconds"), (int, float))]
    scenarios["cancel"] = {
        "runs": len(cancel),
        "cancelled": sum(1 for r in cancel if r.get("status") == "cancelled"),
        "cancel_p50_seconds": percentile(cancel_latencies, 50),
        "cancel_p95_seconds": percentile(cancel_latencies, 95),
    }
    deep_ok = scenarios["deep"]["runs"] > 0 and _passes(scenarios["deep"], slo, "deep_p95_seconds")
    cancel_ok = (scenarios["cancel"]["runs"] > 0
                 and scenarios["cancel"]["cancelled"] == scenarios["cancel"]["runs"]
                 and (scenarios["cancel"]["cancel_p95_seconds"] or math.inf)
                 <= slo["cancel_p95_seconds"])
    observed_output = max((s.get("tokens_max") or 0) for s in scenarios.values()
                          if isinstance(s, Mapping) and "tokens_max" in s)
    return {
        "schema": ENVELOPE_SCHEMA,
        "profile": profile["id"],
        "backend": _normalize_backend(profile["backend"]),
        "primary_model": profile["primary_model"],
        "measured_utc": results.get("finished_utc"),
        "hardware": results.get("hardware") or {},
        "runtime": results.get("runtime") or {},
        "results_file": results.get("results_file"),
        "limits": {
            # Enforced by the gate: a configuration above these is REJECTED.
            "context_tokens": context_limit,
            "concurrent_jobs": concurrency_limit,
        },
        "qualified_workflows": {
            "QUICK": context_limit > 0,
            "DEEP": deep_ok,
            "cancellation": cancel_ok,
        },
        # Reported, not enforced: the largest output actually produced. A configured
        # MAX_OUTPUT_TOKENS above it has not been exercised and is flagged UNQUALIFIED.
        "observed_max_output_tokens": observed_output,
        "resources": results.get("resources") or {},
        "slo": dict(slo),
        "scenarios": scenarios,
    }


def envelope_path(root: str | os.PathLike[str] | Path) -> Path:
    return resolve_state_home(root).joinpath(*ENVELOPE_RELATIVE)


def load_envelope(root: str | os.PathLike[str] | Path) -> dict[str, Any] | None:
    path = envelope_path(root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QualificationError(f"{path} is unreadable: {exc}") from exc
    limits = doc.get("limits") if isinstance(doc, dict) else None
    if (not isinstance(doc, dict) or doc.get("schema") != ENVELOPE_SCHEMA
            or not isinstance(limits, dict)):
        raise QualificationError(f"{path} is not a qualification envelope")
    for key in ("context_tokens", "concurrent_jobs"):
        value = limits.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise QualificationError(f"{path} limits.{key} must be a non-negative integer")
    return doc


def write_envelope(root: str | os.PathLike[str] | Path, envelope: Mapping[str, Any]) -> Path:
    path = envelope_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


# --- the gate -------------------------------------------------------------------------------------

def evaluate(root: str | os.PathLike[str] | Path, *, backend: str, primary_model: str,
             num_ctx: int, num_predict: int, workers: int) -> dict[str, Any]:
    """Qualification verdict for the configuration the product is about to run."""
    config = {"backend": _normalize_backend(backend), "primary_model": primary_model,
              "num_ctx": num_ctx, "num_predict": num_predict, "workers": workers}
    try:
        profiles = load_profiles(root)
        envelope = load_envelope(root)
    except QualificationError as exc:
        return {"verdict": REJECTED, "profile": None, "config": config,
                "reasons": [f"qualification data invalid: {exc}"], "unqualified": []}
    profile = find_profile(profiles, backend, primary_model)
    if profile is None:
        return {"verdict": UNQUALIFIED, "profile": None, "config": config,
                "reasons": [f"no supported profile for backend {config['backend']!r} with "
                            f"primary model {primary_model!r}"], "unqualified": ["profile"]}
    if envelope is None or envelope.get("profile") != profile["id"]:
        return {"verdict": UNQUALIFIED, "profile": profile["id"], "config": config,
                "reasons": ["profile has not been measured on this machine "
                            "(run: python -m sovereign_product.qualification run/derive)"],
                "unqualified": ["context_tokens", "concurrent_jobs", "max_output_tokens"]}
    limits = envelope["limits"]
    reasons, unqualified = [], []
    if num_ctx > limits["context_tokens"]:
        reasons.append(f"context window {num_ctx} exceeds the measured envelope "
                       f"({limits['context_tokens']} tokens)")
    if workers > limits["concurrent_jobs"]:
        reasons.append(f"{workers} concurrent job worker(s) exceed the measured envelope "
                       f"({limits['concurrent_jobs']})")
    observed = envelope.get("observed_max_output_tokens") or 0
    if num_predict > observed:
        unqualified.append("max_output_tokens")
    verdict = REJECTED if reasons else QUALIFIED
    if not reasons and unqualified:
        reasons.append(f"max output {num_predict} tokens not exercised (largest measured "
                       f"{observed}); reported, not enforced")
    return {"verdict": verdict, "profile": profile["id"], "config": config, "reasons": reasons,
            "unqualified": unqualified, "limits": dict(limits),
            "measured_utc": envelope.get("measured_utc")}


def apply_envelope(root: str | os.PathLike[str] | Path,
                   envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Install a measured envelope and LOWER the runtime limits so the configuration fits it.

    Writes the envelope to the state home and, through the downward-only RUNTIME overrides,
    sets CONTEXT_WINDOW to at most the qualified context and MAX_OUTPUT_TOKENS to at most half of
    it. The shipped manifest is never written. Refuses an envelope below the product's 4096-token
    minimum: that profile failed qualification and must not be run.
    """
    import system_manifest

    from .manifest_overrides import ManifestOverrideError, write_overrides

    limit = int(envelope["limits"]["context_tokens"])
    if limit < 4096:
        raise QualificationError(
            f"profile {envelope.get('profile')!r} qualified only {limit} context tokens, below "
            "the product minimum of 4096; it failed qualification and cannot be applied")
    manifest_path = Path(root) / system_manifest.MANIFEST_FILENAME
    shipped = system_manifest.load_shipped_manifest(manifest_path=manifest_path)
    runtime = shipped["RUNTIME"]
    context = min(int(runtime["CONTEXT_WINDOW"]), limit)
    output = min(int(runtime["MAX_OUTPUT_TOKENS"]), context // 2)
    envelope_file = write_envelope(root, envelope)
    try:
        write_overrides(root, shipped, "RUNTIME",
                        {"CONTEXT_WINDOW": context, "MAX_OUTPUT_TOKENS": output})
    except ManifestOverrideError as exc:
        raise QualificationError(str(exc)) from exc
    effective = system_manifest.load_system_manifest(manifest_path=manifest_path)
    return {"envelope": str(envelope_file),
            "runtime_overrides": {"CONTEXT_WINDOW": context, "MAX_OUTPUT_TOKENS": output},
            "effective_runtime": {k: effective["RUNTIME"][k]
                                  for k in ("CONTEXT_WINDOW", "MAX_OUTPUT_TOKENS")}}


# --- CLI ------------------------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sovereign_product.qualification",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="the SOVEREIGN install root")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="measure a profile end-to-end through a running product")
    run.add_argument("--profile", required=True)
    run.add_argument("--base-url", default="http://127.0.0.1:5175")
    run.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    run.add_argument("--out", required=True)
    run.add_argument("--repetitions", type=int, default=None)
    run.add_argument("--job-timeout", type=float, default=1800.0)
    run.add_argument("--skip-deep", action="store_true")
    run.add_argument("--max-context", type=int, default=None,
                     help="stop the context ladder above this many tokens")
    derive = sub.add_parser("derive", help="turn results into this machine's envelope")
    derive.add_argument("--results", required=True)
    derive.add_argument("--write", action="store_true", help="install it in the state home")
    apply = sub.add_parser("apply", help="install the envelope and lower runtime limits to fit it")
    apply.add_argument("--results", required=True)
    check = sub.add_parser("check", help="gate a configuration against the envelope")
    check.add_argument("--backend", required=True)
    check.add_argument("--primary-model", required=True)
    check.add_argument("--num-ctx", type=int, required=True)
    check.add_argument("--num-predict", type=int, required=True)
    check.add_argument("--workers", type=int, required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    try:
        if args.command == "run":
            from .qualification_harness import run_qualification

            profiles = load_profiles(root)
            profile = next((p for p in profiles["profiles"] if p["id"] == args.profile), None)
            if profile is None:
                raise QualificationError(f"unknown profile {args.profile!r}")
            results = run_qualification(
                profile, base_url=args.base_url, ollama_url=args.ollama_url,
                repetitions=args.repetitions, job_timeout=args.job_timeout,
                include_deep=not args.skip_deep, max_context=args.max_context)
            out = Path(args.out)
            results["results_file"] = out.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps({"ok": True, "results": str(out), "runs": len(results["runs"])}))
            return 0
        if args.command == "derive":
            results = json.loads(Path(args.results).read_text(encoding="utf-8"))
            envelope = derive_envelope(results, load_profiles(root))
            if args.write:
                envelope["installed_utc"] = _utc_now()
                print(json.dumps({"envelope": str(write_envelope(root, envelope))}))
            print(json.dumps(envelope, indent=2, sort_keys=True))
            return 0
        if args.command == "apply":
            results = json.loads(Path(args.results).read_text(encoding="utf-8"))
            envelope = derive_envelope(results, load_profiles(root))
            envelope["installed_utc"] = _utc_now()
            print(json.dumps(apply_envelope(root, envelope), indent=2, sort_keys=True))
            return 0
        verdict = evaluate(root, backend=args.backend, primary_model=args.primary_model,
                           num_ctx=args.num_ctx, num_predict=args.num_predict,
                           workers=args.workers)
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return {QUALIFIED: 0, UNQUALIFIED: 2, REJECTED: 3}[verdict["verdict"]]
    except (QualificationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
