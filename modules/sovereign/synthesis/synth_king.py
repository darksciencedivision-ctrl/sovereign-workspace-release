from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
for candidate in (SCRIPT_DIR, ROOT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from praxis_report import build_praxis_report
from sovereign_voice import build_sovereign_voice
from system_manifest import load_system_manifest, model_name, runtime_value


SECTION_RE_TEMPLATE = r"(?ims)^\s*{name}\s*:\s*(.*?)(?=^\s*[A-Z_][A-Z_ ]{{2,40}}\s*:|\Z)"
VALID_MODES = {"OFF", "OBSERVE", "SANDBOX", "PROMOTE"}
REQUIRED_CANONICAL_SECTIONS = ["CLAIM", "EVIDENCE", "COUNTERARGUMENTS", "UNCERTAINTIES", "FINAL_SYNTHESIS"]
REQUIRED_DEBATE_SECTIONS = ["CLAIM", "CHALLENGE", "EVIDENCE", "UNCERTAINTY"]
OUTPUT_PREVIEW_MAX_CHARS = 900

# Phase 2.5 version constants
ROLE_CONTRACT_VERSION = "2.5G"
STRUCTURAL_PROBE_CONTRACT_VERSION = "2.5G"
KING_SYNTHESIZER_PROMPT_VERSION = "2.5G"
STANCE_LABEL_SANITIZED = True        # 2.5C: STANCE: label removed from position prompt
FORBIDDEN_LABEL_LIST_REMOVED = True  # 2.5E: forbidden-label lists removed from generation-visible prompts
ROLE_CONTEXT_LABEL_REMOVED = True    # 2.5G: Role-context: label removed from position prompt


class SynthesisError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_critical_json(path: Path) -> Any:
    if not path.exists():
        raise SynthesisError(f"Critical config missing: {path}")
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SynthesisError(f"Unable to read critical config {path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SynthesisError(f"Invalid JSON in critical config {path}: {exc}") from exc


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SynthesisError(f"{label} must be a JSON object")
    return dict(value)


def require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise SynthesisError(f"{label} must be a JSON array")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise SynthesisError(f"{label} must not be empty")
    return items


def validate_role_entry(role_cfg: Any, label: str) -> dict[str, Any]:
    cfg = require_mapping(role_cfg, label)
    role = str(cfg.get("role", "")).strip()
    model = str(cfg.get("model", "")).strip()
    if not role:
        raise SynthesisError(f"{label} is missing required field: role")
    if not model:
        raise SynthesisError(f"{label} is missing required field: model")
    return cfg


def validate_model_hierarchy(data: Any) -> dict[str, Any]:
    hierarchy = require_mapping(data, "model_hierarchy.json")
    king_cfg = hierarchy.get("king")
    if king_cfg is None:
        king_cfg = hierarchy.get("king_synthesizer")
    king = validate_role_entry(king_cfg, "model_hierarchy.json -> king_synthesizer")

    alpha_wing_raw = hierarchy.get("alpha_wing")
    if not isinstance(alpha_wing_raw, list) or not alpha_wing_raw:
        raise SynthesisError("model_hierarchy.json -> alpha_wing must be a non-empty array")
    alpha_wing = [validate_role_entry(item, f"model_hierarchy.json -> alpha_wing[{index}]") for index, item in enumerate(alpha_wing_raw)]

    beta_wing_raw = hierarchy.get("beta_wing")
    if not isinstance(beta_wing_raw, list) or not beta_wing_raw:
        raise SynthesisError("model_hierarchy.json -> beta_wing must be a non-empty array")
    beta_wing = [validate_role_entry(item, f"model_hierarchy.json -> beta_wing[{index}]") for index, item in enumerate(beta_wing_raw)]

    wing_reconciliation_raw = require_mapping(hierarchy.get("wing_reconciliation"), "model_hierarchy.json -> wing_reconciliation")
    wing_reconciliation = {
        "alpha": validate_role_entry(wing_reconciliation_raw.get("alpha"), "model_hierarchy.json -> wing_reconciliation.alpha"),
        "beta": validate_role_entry(wing_reconciliation_raw.get("beta"), "model_hierarchy.json -> wing_reconciliation.beta"),
    }

    cross_channel_raw = require_mapping(hierarchy.get("cross_channel"), "model_hierarchy.json -> cross_channel")
    cross_channel = {
        "critique": validate_role_entry(cross_channel_raw.get("critique"), "model_hierarchy.json -> cross_channel.critique"),
        "cross_exam": validate_role_entry(cross_channel_raw.get("cross_exam"), "model_hierarchy.json -> cross_channel.cross_exam"),
    }

    normalized = dict(hierarchy)
    normalized["king_synthesizer"] = king
    normalized["alpha_wing"] = alpha_wing
    normalized["beta_wing"] = beta_wing
    normalized["wing_reconciliation"] = wing_reconciliation
    normalized["cross_channel"] = cross_channel
    return normalized


def validate_contract(data: Any) -> dict[str, Any]:
    contract = require_mapping(data, "synthesis_contract.json")
    canonical_output = require_mapping(contract.get("canonical_output"), "synthesis_contract.json -> canonical_output")
    non_canonical_output = require_mapping(contract.get("non_canonical_output"), "synthesis_contract.json -> non_canonical_output")
    report_output = require_mapping(contract.get("report_output"), "synthesis_contract.json -> report_output")

    canonical_fields = require_string_list(canonical_output.get("required_fields"), "synthesis_contract.json -> canonical_output.required_fields")
    for field_name in ("session_id", "topic", "claim", "evidence", "counterarguments", "uncertainties", "final_synthesis", "canonical", "memory_allowed"):
        if field_name not in canonical_fields:
            raise SynthesisError(f"synthesis_contract.json -> canonical_output.required_fields is missing {field_name}")
    if not str(canonical_output.get("filename", "")).strip():
        raise SynthesisError("synthesis_contract.json -> canonical_output.filename is required")
    if "memory_allowed" not in canonical_output or "control_plane_allowed" not in canonical_output:
        raise SynthesisError("synthesis_contract.json -> canonical_output must declare memory_allowed and control_plane_allowed")

    non_canonical_markers = require_string_list(non_canonical_output.get("required_markers"), "synthesis_contract.json -> non_canonical_output.required_markers")
    for marker in ("NON_CANONICAL_CHANNEL: sovereign_voice", "PRAXIS_MEMORY_ALLOWED: false", "CONTROL_PLANE_ALLOWED: false"):
        if marker not in non_canonical_markers:
            raise SynthesisError(f"synthesis_contract.json -> non_canonical_output.required_markers is missing {marker}")
    if not str(non_canonical_output.get("filename", "")).strip():
        raise SynthesisError("synthesis_contract.json -> non_canonical_output.filename is required")
    if "memory_allowed" not in non_canonical_output or "control_plane_allowed" not in non_canonical_output:
        raise SynthesisError("synthesis_contract.json -> non_canonical_output must declare memory_allowed and control_plane_allowed")

    report_markers = require_string_list(report_output.get("required_markers"), "synthesis_contract.json -> report_output.required_markers")
    for marker in ("REPORT_CHANNEL: praxis_report", "PRAXIS_MEMORY_ALLOWED: false"):
        if marker not in report_markers:
            raise SynthesisError(f"synthesis_contract.json -> report_output.required_markers is missing {marker}")
    if not str(report_output.get("filename", "")).strip():
        raise SynthesisError("synthesis_contract.json -> report_output.filename is required")
    if "memory_allowed" not in report_output or "control_plane_allowed" not in report_output:
        raise SynthesisError("synthesis_contract.json -> report_output must declare memory_allowed and control_plane_allowed")

    canonical_sections = require_string_list(contract.get("canonical_sections"), "synthesis_contract.json -> canonical_sections")
    for section in REQUIRED_CANONICAL_SECTIONS:
        if section not in canonical_sections:
            raise SynthesisError(f"synthesis_contract.json -> canonical_sections is missing {section}")

    debate_sections = require_string_list(contract.get("debate_sections"), "synthesis_contract.json -> debate_sections")
    for section in REQUIRED_DEBATE_SECTIONS:
        if section not in debate_sections:
            raise SynthesisError(f"synthesis_contract.json -> debate_sections is missing {section}")

    return contract


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            if not payload.endswith("\n"):
                handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def append_log_line(path: Path, obj: dict[str, Any]) -> None:
    # F-125(g): append ONE line. This used to read the whole never-rotated system log and atomically
    # rewrite it for every stage event - O(n) per event, quadratic over an install's lifetime - and
    # a concurrent writer's line was lost between the read and the rename.
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(obj, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_section(text: str, names: list[str]) -> str:
    body = normalize_text(text)
    for name in names:
        pattern = SECTION_RE_TEMPLATE.format(name=re.escape(name))
        match = re.search(pattern, body)
        if match:
            return normalize_text(match.group(1))
    return ""


def split_bullets(text: str) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []

    # F-125(i): the class was the UTF-8 bullet double-decoded into three characters, so a real
    # U+2022 bullet from a model was never a bullet while lines starting with those stray
    # characters were stripped as if they were.
    bullet_pattern = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
    lines = cleaned.splitlines()

    if any(bullet_pattern.match(line) for line in lines):
        items: list[str] = []
        for raw_line in lines:
            line = bullet_pattern.sub("", raw_line).strip()
            if line:
                items.append(line)
        if items:
            return items

    if len(lines) > 1:
        items = [line.strip() for line in lines if line.strip()]
        if items:
            return items

    semicolon_items = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(semicolon_items) > 1:
        return semicolon_items

    paragraph = re.sub(r"\s+", " ", cleaned).strip()
    if not paragraph:
        return []

    sentence_parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', paragraph)
    abbreviations = ("e.g.", "i.e.", "etc.", "vs.", "U.S.", "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.")
    merged: list[str] = []
    for part in sentence_parts:
        item = part.strip()
        if not item:
            continue
        if merged and any(merged[-1].endswith(abbr) for abbr in abbreviations):
            merged[-1] = f"{merged[-1]} {item}"
        else:
            merged.append(item)

    meaningful = [item for item in merged if len(item.split()) >= 4]
    if len(meaningful) > 1:
        return meaningful
    return [paragraph]


def apply_model_overrides(hierarchy: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    hierarchy["king_synthesizer"]["model"] = args.model_synth or hierarchy["king_synthesizer"]["model"]
    hierarchy["alpha_wing"][0]["model"] = args.model_a or hierarchy["alpha_wing"][0]["model"]
    if len(hierarchy["alpha_wing"]) >= 2:
        hierarchy["alpha_wing"][1]["model"] = args.model_b or hierarchy["alpha_wing"][1]["model"]
    hierarchy["beta_wing"][0]["model"] = args.model_c or hierarchy["beta_wing"][0]["model"]
    if len(hierarchy["beta_wing"]) >= 2:
        hierarchy["beta_wing"][1]["model"] = args.model_b or hierarchy["beta_wing"][1]["model"]
    hierarchy["wing_reconciliation"]["alpha"]["model"] = args.model_a or hierarchy["wing_reconciliation"]["alpha"]["model"]
    hierarchy["wing_reconciliation"]["beta"]["model"] = args.model_c or hierarchy["wing_reconciliation"]["beta"]["model"]
    hierarchy["cross_channel"]["critique"]["model"] = args.model_b or hierarchy["cross_channel"]["critique"]["model"]
    hierarchy["cross_channel"]["cross_exam"]["model"] = args.model_synth or hierarchy["cross_channel"]["cross_exam"]["model"]
    return hierarchy


def load_hierarchy(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    hierarchy_path = root / "synthesis" / "model_hierarchy.json"
    hierarchy = validate_model_hierarchy(load_critical_json(hierarchy_path))
    return apply_model_overrides(hierarchy, args)


def load_contract(root: Path) -> dict[str, Any]:
    return validate_contract(load_critical_json(root / "synthesis" / "synthesis_contract.json"))


def load_constitution_state(root: Path) -> dict[str, Any]:
    state_path = root / "constitution" / "constitution_state.json"
    state = require_mapping(load_critical_json(state_path), "constitution_state.json")
    schema_version = str(state.get("schema_version", "")).strip()
    if not schema_version:
        raise SynthesisError("constitution_state.json is missing required field: schema_version")
    mode = str(state.get("mode", "")).strip().upper()
    if not mode:
        raise SynthesisError("constitution_state.json is missing required field: mode")
    if mode not in VALID_MODES:
        raise SynthesisError(f"constitution_state.json has invalid mode: {mode}")
    state["mode"] = mode
    return state


def build_output_preview(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return "[empty response]"
    if len(normalized) <= OUTPUT_PREVIEW_MAX_CHARS:
        return normalized
    return normalized[:OUTPUT_PREVIEW_MAX_CHARS].rstrip() + "\n...[truncated]"


def load_system_prompt(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(str(path_value)).expanduser()
    if not path.exists():
        raise SynthesisError(f"System prompt file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SynthesisError(f"Unable to read system prompt file {path}: {exc}") from exc
    prompt = normalize_text(text)
    if not prompt:
        raise SynthesisError(f"System prompt file is empty: {path}")
    return prompt


def ollama_generate(model: str, prompt: str, ollama_base: str, temperature: float, max_tokens: int, seed: int, timeout_sec: int, system_prompt: str | None = None) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # Contract-bound stages need final answer content in `response`, not
        # separated reasoning tokens that can consume the output budget.
        "think": False,
        "options": {
            "num_predict": int(max_tokens),
            "temperature": float(temperature),
            "seed": int(seed),
        },
    }
    if system_prompt:
        payload["system"] = system_prompt
    request = urllib.request.Request(
        ollama_base.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, socket.timeout) as exc:
        raise SynthesisError(f"Model timeout for {model}: {exc}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            raise SynthesisError(f"Model timeout for {model}: {exc.reason}") from exc
        raise SynthesisError(f"Ollama/API error for {model}: {exc}") from exc
    if not isinstance(body, dict):
        raise SynthesisError(f"Ollama/API error for {model}: non-object response")
    if body.get("error"):
        raise SynthesisError(f"Ollama/API error for {model}: {body['error']}")
    text = normalize_text(str(body.get("response", "")))
    if not text:
        raise SynthesisError(f"Empty response for {model}")
    return text


def missing_sections(text: str, required_sections: list[str]) -> list[str]:
    return [section for section in required_sections if not extract_section(text, [section])]


def section_headers(text: str) -> list[str]:
    body = normalize_text(text)
    if not body:
        return []
    return [match.group(1).strip().upper() for match in re.finditer(r"(?im)^\s*([A-Z_][A-Z_ ]{2,40})\s*:", body)]


def section_validation_details(text: str, required_sections: list[str]) -> tuple[str, list[str]]:
    body = normalize_text(text)
    missing = missing_sections(body, required_sections)
    reasons: list[str] = []

    if body:
        if not re.match(rf"(?is)^\s*{re.escape(required_sections[0])}\s*:", body):
            reasons.append(f"Output must start with {required_sections[0]}:")

        headers = section_headers(body)
        if headers and headers != required_sections:
            reasons.append(
                "Unexpected section structure: expected "
                + ", ".join(required_sections)
                + "; observed "
                + ", ".join(headers)
            )

    if missing:
        reasons.append(f"Missing sections: {', '.join(missing)}")

    return "; ".join(reasons), missing


def required_sections_for_stage(stage: str) -> list[str]:
    return REQUIRED_CANONICAL_SECTIONS if stage == "king_synthesis" else REQUIRED_DEBATE_SECTIONS


def has_section_header(text: str, section: str) -> bool:
    return bool(re.search(rf"(?im)^\s*{re.escape(section)}\s*:", text or ""))


def ensure_required_sections(text: str, stage: str) -> str:
    """Preserve model content exactly; missing required sections fail validation.

    Older fallback code appended invented placeholder content to turn a partial
    response into a structurally valid one.  Structural repair is not evidence
    and must never convert a contract failure into acceptance.
    """
    del stage
    return (text or "").strip()


def debate_validation_details(text: str) -> tuple[str, list[str]]:
    return section_validation_details(text, REQUIRED_DEBATE_SECTIONS)


def canonical_validation_details(text: str) -> tuple[str, list[str]]:
    return section_validation_details(text, REQUIRED_CANONICAL_SECTIONS)


def validate_debate_output(text: str) -> bool:
    reason, _ = debate_validation_details(text)
    return not reason


def validate_canonical_output(text: str) -> bool:
    reason, _ = canonical_validation_details(text)
    return not reason


def classify_stage_failure(exc: Exception) -> str:
    message = str(exc).lower()
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timeout" in message:
        return "model timeout"
    if "empty response" in message:
        return "empty response"
    if ".json" in message or "critical config" in message or "required field" in message or "config" in message:
        return "config load/validation failure"
    if "missing sections" in message or "schema validation" in message or "schema/section" in message:
        return "schema/section validation failure"
    if "ollama/api error" in message or "ollama" in message or "api error" in message:
        return "Ollama/API error"
    return "unexpected exception"


def log_stage_event(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    attempt: int,
    validation_passed: bool,
    raw_validation_passed: bool | None = None,
    failure_category: str | None = None,
    failure_reason: str | None = None,
    raw_missing_sections: list[str] | None = None,
    missing_sections_list: list[str] | None = None,
    guard_applied: bool = False,
    guard_inserted_sections: list[str] | None = None,
    raw_output_preview: str | None = None,
    raw_output_length: int | None = None,
    round_number: int | None = None,
    wing_name: str | None = None,
) -> None:
    append_log_line(
        root / "logs" / "system.txt",
        {
            "ts": utc_now_iso(),
            "source": "synth_king",
            "event": "stage_attempt",
            "session_id": session_id,
            "stage": stage,
            "round_number": round_number,
            "wing_name": wing_name,
            "role": role,
            "model": model,
            "attempt": attempt,
            "validation_passed": validation_passed,
            "raw_validation_passed": raw_validation_passed,
            "failure_category": failure_category,
            "failure_reason": failure_reason,
            "raw_missing_sections": raw_missing_sections or [],
            "missing_sections": missing_sections_list or [],
            "guard_applied": guard_applied,
            "guard_inserted_sections": guard_inserted_sections or [],
            "raw_output_preview": raw_output_preview,
            "raw_output_length": raw_output_length,
        },
    )


def log_terminal_stage_failure(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    retry_count: int,
    failure_category: str,
    failure_reason: str,
    missing_sections_list: list[str] | None = None,
    raw_output_preview: str | None = None,
    raw_output_length: int | None = None,
    round_number: int | None = None,
    wing_name: str | None = None,
) -> None:
    append_log_line(
        root / "logs" / "system.txt",
        {
            "ts": utc_now_iso(),
            "source": "synth_king",
            "event": "stage_terminal_failure",
            "session_id": session_id,
            "stage": stage,
            "round_number": round_number,
            "wing_name": wing_name,
            "role": role,
            "model": model,
            "retry_count": retry_count,
            "failure_category": failure_category,
            "failure_reason": failure_reason,
            "missing_sections": missing_sections_list or [],
            "raw_output_preview": raw_output_preview,
            "raw_output_length": raw_output_length,
        },
    )


def log_auto_inserted_sections(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    attempt: int,
    missing_sections_list: list[str],
    raw_output_preview: str | None = None,
    raw_output_length: int | None = None,
    post_guard_validation_passed: bool | None = None,
    round_number: int | None = None,
    wing_name: str | None = None,
) -> None:
    append_log_line(
        root / "logs" / "system.txt",
        {
            "ts": utc_now_iso(),
            "source": "synth_king",
            "event": "stage_structure_guard",
            "session_id": session_id,
            "stage": stage,
            "round_number": round_number,
            "wing_name": wing_name,
            "role": role,
            "model": model,
            "attempt": attempt,
            "action": "auto_inserted_sections",
            "missing_sections": missing_sections_list,
            "inserted_section_count": len(missing_sections_list),
            "raw_output_preview": raw_output_preview,
            "raw_output_length": raw_output_length,
            "post_guard_validation_passed": post_guard_validation_passed,
        },
    )


def build_position_prompt(topic: str, transcript: str, role: str, stance: str, stage: str, round_number: int) -> str:
    # 2.5G final state: no STANCE: label, no Role-context: label, no Round: label, no forbidden-label lists
    return f"""
You are {role} in the {stage} stage of a controlled dual-wing debate.
Preserve your role-specific analytical perspective while staying compact and parse-safe.

{stance}

TOPIC:
{topic}

TRANSCRIPT SO FAR:
{transcript if transcript else "[No prior transcript]"}

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- CHALLENGE is required and must directly pressure-test the claim.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- UNCERTAINTY is required. If confidence is high, still include a minimal uncertainty.
- Do not introduce section headers that are not listed in this prompt.
- Do not reproduce structural examples or label lists verbatim.

Return this exact structure:

CLAIM:
<one concise claim>

CHALLENGE:
<one concise critique>

EVIDENCE:
- <support point 1>
- <support point 2>

UNCERTAINTY:
<one concise unresolved issue>
""".strip()


def build_neutral_debate_prompt(topic: str, transcript: str, round_number: int | None = None) -> str:
    return f"""
SCENARIO:
{topic}

PRIOR TRANSCRIPT:
{transcript if transcript else "[No prior transcript]"}

TASK:
Analyze the scenario under the provided operating parameters.
Use prior arguments only on optimization merits.
Return one current strategic position with one direct challenge.

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- CHALLENGE is required and must directly test the claim.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- UNCERTAINTY is required.

Return this exact structure:

CLAIM:
<one concise claim>

CHALLENGE:
<one concise critique>

EVIDENCE:
- <support point 1>
- <support point 2>

UNCERTAINTY:
<one concise unresolved issue>
""".strip()


def build_reconciliation_prompt(topic: str, wing_name: str, wing_transcript: str, role: str) -> str:
    return f"""
You are {role}. Reconcile the {wing_name} wing into its strongest internally consistent position.
Preserve the reconciliation role while staying compact and parse-safe.

TOPIC:
{topic}

{wing_name.upper()} WING TRANSCRIPT:
{wing_transcript}

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- Reconcile competing claims into one coherent position while preserving important limits.
- CHALLENGE is required and must directly pressure-test the reconciled claim.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- UNCERTAINTY is required. If confidence is high, still include a minimal uncertainty.

Return this exact structure:

CLAIM:
<the strongest internally reconciled claim>

CHALLENGE:
<the main remaining weakness>

EVIDENCE:
- <support point 1>
- <support point 2>

UNCERTAINTY:
<one concise unresolved issue>
""".strip()


def build_cross_prompt(topic: str, alpha_summary: str, beta_summary: str, role: str, mode: str) -> str:
    return f"""
You are {role} performing {mode} in a controlled dual-wing debate.
Preserve the critique or cross-exam role while staying compact and parse-safe.

TOPIC:
{topic}

Alpha-wing:
{alpha_summary}

Beta-wing:
{beta_summary}

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- CHALLENGE is required and must directly pressure-test the claim.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- UNCERTAINTY is required. If confidence is high, still include a minimal uncertainty.

Return this exact structure:

CLAIM:
<the strongest contested point>

CHALLENGE:
<one concise critique>

EVIDENCE:
- <support point 1>
- <support point 2>

UNCERTAINTY:
<one concise unresolved issue>
""".strip()


def build_king_prompt(topic: str, transcript: str, session_id: str) -> str:
    return f"""
You are the KING_SYNTHESIZER. Produce the canonical Praxis Answer only.
Keep the output canonical, compact, and parse-safe.

SESSION_ID: {session_id}

TOPIC:
{topic}

FULL DEBATE TRANSCRIPT:
{transcript}

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- COUNTERARGUMENTS and UNCERTAINTIES are required.

Return this exact structure:

CLAIM:
<one concise balanced claim>

EVIDENCE:
- <support point 1>
- <support point 2>

COUNTERARGUMENTS:
- <objection 1>
- <objection 2>

UNCERTAINTIES:
- <unresolved issue 1>

FINAL_SYNTHESIS:
<one concise synthesis paragraph>
""".strip()


def build_structural_probe_king_prompt(topic: str, transcript: str, session_id: str) -> str:
    """
    Phase 2.5C full-section structural probe — 24 invariant instructions covering all 5 canonical sections.
    Replaces the Phase 18 CLAIM-only structural probe.
    STRUCTURAL_PROBE_CONTRACT_VERSION = "2.5G"
    """
    return f"""
You are the KING_SYNTHESIZER. Produce the canonical Praxis Answer only.
Keep the output canonical, compact, and parse-safe.

SESSION_ID: {session_id}

TOPIC:
{topic}

FULL DEBATE TRANSCRIPT:
{transcript}

STRUCTURAL INVARIANTS — read these carefully before writing:
1. Return exactly five sections: CLAIM, EVIDENCE, COUNTERARGUMENTS, UNCERTAINTIES, FINAL_SYNTHESIS.
2. Each section must appear exactly once.
3. Do not add any section not listed in invariant 1.
4. Do not omit any section listed in invariant 1.
5. Use the exact section headers shown in invariant 1. No markdown bold, no colons except the required one.
6. No text before CLAIM. No text after FINAL_SYNTHESIS.
7. No commentary outside the required sections.

CLAIM invariants:
8. CLAIM must be one concise, direct sentence asserting the synthesized position.
9. CLAIM must not contain sub-bullets or lists.
10. CLAIM must not begin with "I" or refer to the model by name.

EVIDENCE invariants:
11. EVIDENCE must contain at least two distinct support statements.
12. Each evidence statement must stand alone; do not collapse into one paragraph.
13. Prefer short bullets or short sentences. Each bullet begins with "- ".

COUNTERARGUMENTS invariants:
14. COUNTERARGUMENTS must contain at least two distinct objections drawn from the debate.
15. Each counterargument must stand alone; do not collapse into one paragraph.
16. Counterarguments must reflect genuine tension, not straw-man concessions.

UNCERTAINTIES invariants:
17. UNCERTAINTIES must contain at least one unresolved issue.
18. Uncertainties must identify gaps or open questions, not restate evidence.
19. If confidence is high, still include a minimal uncertainty.

FINAL_SYNTHESIS invariants:
20. FINAL_SYNTHESIS must be a single synthesis paragraph (one to three sentences).
21. FINAL_SYNTHESIS must integrate evidence and acknowledge counterarguments.
22. FINAL_SYNTHESIS must not introduce new claims absent from CLAIM or EVIDENCE.
23. FINAL_SYNTHESIS must not begin with "In conclusion" or "In summary".
24. FINAL_SYNTHESIS must be consistent with the CLAIM section.

Return this exact structure:

CLAIM:
<one concise balanced claim>

EVIDENCE:
- <support point 1>
- <support point 2>

COUNTERARGUMENTS:
- <objection 1>
- <objection 2>

UNCERTAINTIES:
- <unresolved issue 1>

FINAL_SYNTHESIS:
<one concise synthesis paragraph>
""".strip()


def build_neutral_king_prompt(topic: str, transcript: str, session_id: str) -> str:
    return f"""
SESSION_ID: {session_id}

SCENARIO:
{topic}

FULL DEBATE TRANSCRIPT:
{transcript}

TASK:
Analyze the scenario and transcript under the provided operating parameters.
Return one current strategic recommendation with supporting evidence, counterarguments, and unresolved uncertainties.

FORMAT RULES:
- Return all required sections exactly once. Missing section = invalid.
- Use the exact headers shown below. No markdown bold.
- No text before the first section or after the final section.
- No extra commentary outside the required sections.

CONTENT RULES:
- Keep each section concise and plain text.
- Prefer 3 to 4 distinct evidence statements when reasonably available.
- Prefer concrete support statements over generic summary phrases.
- Each evidence statement should stand alone.
- Prefer short bullets or short sentences.
- Do not collapse all evidence into one paragraph.
- COUNTERARGUMENTS and UNCERTAINTIES are required.

Return this exact structure:

CLAIM:
<one concise claim>

EVIDENCE:
- <support point 1>
- <support point 2>

COUNTERARGUMENTS:
- <objection 1>
- <objection 2>

UNCERTAINTIES:
- <unresolved issue 1>

FINAL_SYNTHESIS:
<one concise synthesis paragraph>
""".strip()


def run_stage(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    prompt: str,
    ollama_base: str,
    temperature: float,
    max_tokens: int,
    seed: int,
    timeout_sec: int,
    validation_details_fn,
    round_number: int | None = None,
    wing_name: str | None = None,
    max_attempts: int = 2,
    system_prompt: str | None = None,
) -> str:
    last_reason = "unknown failure"
    last_category = "unexpected exception"
    last_missing_sections: list[str] = []
    last_preview: str | None = None
    last_output_length = 0

    for attempt in range(1, max_attempts + 1):
        response_text: str | None = None
        try:
            response_text = ollama_generate(model, prompt, ollama_base, temperature, max_tokens, seed, timeout_sec, system_prompt=system_prompt)
            raw_preview = build_output_preview(response_text)
            raw_output_length = len(response_text)
            raw_validation_reason, raw_missing = validation_details_fn(response_text)
            completed_text = ensure_required_sections(response_text, stage)
            guard_applied = completed_text != response_text and bool(raw_missing)
            guard_inserted_sections = list(raw_missing)
            validation_reason, missing = validation_details_fn(completed_text)
            if guard_applied:
                log_auto_inserted_sections(
                    root=root,
                    session_id=session_id,
                    stage=stage,
                    role=role,
                    model=model,
                    attempt=attempt,
                    missing_sections_list=guard_inserted_sections,
                    raw_output_preview=raw_preview,
                    raw_output_length=raw_output_length,
                    post_guard_validation_passed=not validation_reason,
                    round_number=round_number,
                    wing_name=wing_name,
                )
            response_text = completed_text
            if not validation_reason:
                log_stage_event(
                    root=root,
                    session_id=session_id,
                    stage=stage,
                    role=role,
                    model=model,
                    attempt=attempt,
                    validation_passed=True,
                    raw_validation_passed=not raw_validation_reason,
                    raw_missing_sections=raw_missing,
                    guard_applied=guard_applied,
                    guard_inserted_sections=guard_inserted_sections,
                    raw_output_preview=raw_preview,
                    raw_output_length=raw_output_length,
                    round_number=round_number,
                    wing_name=wing_name,
                )
                return response_text

            last_reason = validation_reason
            last_category = "schema/section validation failure"
            last_missing_sections = missing
            last_preview = raw_preview
            last_output_length = raw_output_length
            log_stage_event(
                root=root,
                session_id=session_id,
                stage=stage,
                role=role,
                model=model,
                attempt=attempt,
                validation_passed=False,
                raw_validation_passed=not raw_validation_reason,
                failure_category=last_category,
                failure_reason=validation_reason,
                raw_missing_sections=raw_missing,
                missing_sections_list=missing,
                guard_applied=guard_applied,
                guard_inserted_sections=guard_inserted_sections,
                raw_output_preview=raw_preview,
                raw_output_length=raw_output_length,
                round_number=round_number,
                wing_name=wing_name,
            )
        except Exception as exc:
            last_reason = str(exc)
            last_category = classify_stage_failure(exc)
            last_missing_sections = []
            last_preview = build_output_preview(response_text)
            last_output_length = len(response_text) if response_text else 0
            log_stage_event(
                root=root,
                session_id=session_id,
                stage=stage,
                role=role,
                model=model,
                attempt=attempt,
                validation_passed=False,
                failure_category=last_category,
                failure_reason=str(exc),
                missing_sections_list=last_missing_sections,
                raw_output_preview=last_preview,
                raw_output_length=last_output_length,
                round_number=round_number,
                wing_name=wing_name,
            )

    log_terminal_stage_failure(
        root=root,
        session_id=session_id,
        stage=stage,
        role=role,
        model=model,
        retry_count=max_attempts,
        failure_category=last_category,
        failure_reason=last_reason,
        missing_sections_list=last_missing_sections,
        raw_output_preview=last_preview,
        raw_output_length=last_output_length,
        round_number=round_number,
        wing_name=wing_name,
    )
    raise SynthesisError(f"stage={stage} role={role} model={model} retries={max_attempts} reason={last_reason}")


def render_block(tag: str, model: str, text: str) -> str:
    return "\n".join([f"[{tag}] MODEL: {model}", normalize_text(text)]).strip()


def canonical_text(session_id: str, answer: dict[str, Any]) -> str:
    evidence = "\n".join(f"- {item}" for item in answer.get("evidence", []))
    counters = "\n".join(f"- {item}" for item in answer.get("counterarguments", []))
    uncertainties = "\n".join(f"- {item}" for item in answer.get("uncertainties", []))
    body = "\n\n".join(
        [
            f"CLAIM:\n{answer.get('claim', '')}".strip(),
            f"EVIDENCE:\n{evidence}".strip(),
            f"COUNTERARGUMENTS:\n{counters}".strip(),
            f"UNCERTAINTIES:\n{uncertainties}".strip(),
            f"FINAL_SYNTHESIS:\n{answer.get('final_synthesis', '')}".strip(),
        ]
    )
    return f"[SYNTH session_id={session_id}]\n{body}\n[/SYNTH]\n"


def build_answer_payload(session_id: str, topic: str, metrics: dict[str, float], governance: dict[str, Any], hierarchy: dict[str, Any], trace: list[dict[str, Any]], king_text: str, output_paths: dict[str, str]) -> dict[str, Any]:
    claim = extract_section(king_text, ["CLAIM"])
    evidence = split_bullets(extract_section(king_text, ["EVIDENCE"]))
    counterarguments = split_bullets(extract_section(king_text, ["COUNTERARGUMENTS"]))
    uncertainties = split_bullets(extract_section(king_text, ["UNCERTAINTIES"]))
    final_synthesis = extract_section(king_text, ["FINAL_SYNTHESIS"])
    return {
        "schema_version": "1.0",
        "generated_at": utc_now_iso(),
        "session_id": session_id,
        "topic": topic,
        "claim": claim,
        "evidence": evidence,
        "counterarguments": counterarguments,
        "uncertainties": uncertainties,
        "final_synthesis": final_synthesis,
        "canonical": True,
        "memory_allowed": True,
        "control_plane_allowed": True,
        "metrics": metrics,
        "governance": governance,
        "hierarchy": hierarchy,
        "trace": trace,
        "outputs": output_paths,
    }


def deterministic_metrics(answer_text: str) -> dict[str, float]:
    # STRUCTURAL metrics only: derived from bullet counts and final-synthesis length.
    # `structural_completeness` / `response_elaboration` measure the FORM/shape of the
    # response, not its correctness or calibrated confidence. (Historically mislabeled
    # "convergence"/"confidence".)
    evidence_count = len(split_bullets(extract_section(answer_text, ["EVIDENCE"])))
    counter_count = len(split_bullets(extract_section(answer_text, ["COUNTERARGUMENTS"])))
    uncertainty_count = len(split_bullets(extract_section(answer_text, ["UNCERTAINTIES"])))
    final_len = len(extract_section(answer_text, ["FINAL_SYNTHESIS"]))
    structural_completeness = min(0.98, 0.42 + evidence_count * 0.12 + final_len / 1200.0 - uncertainty_count * 0.04)
    response_elaboration = min(0.96, 0.38 + evidence_count * 0.1 + final_len / 1500.0 - counter_count * 0.03 - uncertainty_count * 0.05)
    return {
        "structural_completeness": round(max(0.0, structural_completeness), 4),
        "response_elaboration": round(max(0.0, response_elaboration), 4),
    }


def write_outputs(root: Path, session_id: str, answer: dict[str, Any], voice: str, report: str, dialog_text: str) -> dict[str, str]:
    praxis_dir = root / "output" / "praxis"
    voice_dir = root / "output" / "sovereign_voice"
    report_dir = root / "output" / "praxis_reports"
    dialog_dir = root / "output" / "dialog"
    praxis_dir.mkdir(parents=True, exist_ok=True)
    voice_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    dialog_dir.mkdir(parents=True, exist_ok=True)

    praxis_latest = praxis_dir / "praxis_answer.json"
    praxis_session = praxis_dir / f"{session_id}_praxis_answer.json"
    voice_latest = voice_dir / "sovereign_voice.md"
    voice_session = voice_dir / f"{session_id}_sovereign_voice.md"
    report_latest = report_dir / "praxis_report.md"
    report_session = report_dir / f"{session_id}_praxis_report.md"
    dialog_latest = dialog_dir / "debate_dialog.txt"
    dialog_session = dialog_dir / f"{session_id}_dialog.txt"

    write_json_atomic(praxis_latest, answer)
    write_json_atomic(praxis_session, answer)
    write_text_atomic(voice_latest, voice)
    write_text_atomic(voice_session, voice)
    write_text_atomic(report_latest, report)
    write_text_atomic(report_session, report)
    write_text_atomic(dialog_latest, dialog_text)
    write_text_atomic(dialog_session, dialog_text)

    synthesis_path = root / "praxis" / "logs" / "synthesis.txt"
    write_text_atomic(synthesis_path, canonical_text(session_id, answer))

    return {
        "praxis_answer_path": str(praxis_latest),
        "praxis_answer_session_path": str(praxis_session),
        "sovereign_voice_path": str(voice_latest),
        "sovereign_voice_session_path": str(voice_session),
        "praxis_report_path": str(report_latest),
        "praxis_report_session_path": str(report_session),
        "dialog_path": str(dialog_latest),
        "dialog_session_path": str(dialog_session),
        "synthesis_path": str(synthesis_path),
    }


def audit_synthesis(root: Path, session_id: str, answer: dict[str, Any], mode: str) -> str:
    audit = {
        "schema_version": "1.0",
        "generated_at": utc_now_iso(),
        "session_id": session_id,
        "mode": mode,
        "canonical": bool(answer.get("canonical")),
        "memory_allowed": bool(answer.get("memory_allowed")),
        "voice_memory_allowed": False,
        "report_memory_allowed": False,
        "control_plane_exclusion": ["sovereign_voice", "praxis_report"],
    }
    audit_path = root / "ledger" / "constitution_audits" / f"{session_id}_synthesis_audit.json"
    write_json_atomic(audit_path, audit)
    return str(audit_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOVEREIGN controlled king synthesis engine")
    parser.add_argument("--root", default=None,
                        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--ollama-base-url", default="")
    parser.add_argument("--model-a", default="")
    parser.add_argument("--model-b", default="")
    parser.add_argument("--model-c", default="")
    parser.add_argument("--model-synth", default="")
    parser.add_argument("--debate-rounds", type=int, default=2)
    parser.add_argument("--max-tokens-turn", type=int, default=768)
    parser.add_argument("--max-tokens-synth", type=int, default=1024)
    parser.add_argument("--debate-temp", type=float, default=0.7)
    parser.add_argument("--synth-temp", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--turn-timeout-sec", type=int, default=225)
    parser.add_argument("--synth-timeout-sec", type=int, default=300)
    parser.add_argument("--system-prompt-file", default="")
    return parser.parse_args()


def _resolve_root(cli_root: str | None) -> Path:
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    from tools.sovereign_paths import get_repo_root, configure_root
    return configure_root(cli_root) if cli_root else get_repo_root()


def main() -> int:
    args = _parse_args()
    root = _resolve_root(args.root)
    args.root = str(root)
    manifest = load_system_manifest(root)
    args.ollama_base_url = str(args.ollama_base_url).strip() or str(runtime_value("OLLAMA_BASE_URL", manifest)).strip()
    args.model_a = str(args.model_a).strip() or model_name("PRIMARY_REASONER", manifest)
    args.model_b = str(args.model_b).strip() or model_name("ADVERSARIAL_CHALLENGER", manifest)
    args.model_c = str(args.model_c).strip() or model_name("CRITIC", manifest)
    args.model_synth = str(args.model_synth).strip() or model_name("SYNTHESIZER", manifest)
    try:
        contract = load_contract(root)
        hierarchy = load_hierarchy(root, args)
        state = load_constitution_state(root)
        mode = state["mode"]
        system_prompt = load_system_prompt(args.system_prompt_file)
        neutral_prompt_mode = bool(system_prompt)
        trace: list[dict[str, Any]] = []
        transcript_blocks: list[str] = []
        wing_buffers: dict[str, list[str]] = {"alpha": [], "beta": []}

        for round_number in range(1, max(1, int(args.debate_rounds)) + 1):
            for wing_name in ("alpha", "beta"):
                wing_roles = hierarchy[f"{wing_name}_wing"]
                for role_cfg in wing_roles:
                    role = str(role_cfg.get("role", f"{wing_name.upper()}_ROLE")).strip()
                    model = str(role_cfg.get("model", args.model_a)).strip()
                    stance = str(role_cfg.get("stance", "Reason carefully.")).strip()
                    if neutral_prompt_mode:
                        prompt = build_neutral_debate_prompt(args.topic, "\n\n".join(transcript_blocks), round_number=round_number)
                    else:
                        prompt = build_position_prompt(args.topic, "\n\n".join(transcript_blocks), role, stance, f"{wing_name.upper()}_POSITIONS", round_number)
                    raw = run_stage(root, args.session_id, f"{wing_name}_positions", role, model, prompt, args.ollama_base_url, args.debate_temp, args.max_tokens_turn, args.seed, args.turn_timeout_sec, debate_validation_details, round_number=round_number, wing_name=wing_name, system_prompt=system_prompt)
                    trace.append({"stage": f"{wing_name}_positions", "round": round_number, "role": role, "model": model, "output": raw})
                    block = render_block(f"{role} R{round_number}", model, raw)
                    transcript_blocks.append(block)
                    wing_buffers[wing_name].append(block)

        for wing_name, rec_key in (("alpha", "alpha"), ("beta", "beta")):
            rec_cfg = hierarchy["wing_reconciliation"][rec_key]
            model = str(rec_cfg.get("model", args.model_a)).strip()
            role = str(rec_cfg.get("role", f"{wing_name.upper()}_RECONCILER")).strip()
            if neutral_prompt_mode:
                rec_prompt = build_neutral_debate_prompt(args.topic, "\n\n".join(wing_buffers[wing_name]))
            else:
                rec_prompt = build_reconciliation_prompt(args.topic, wing_name, "\n\n".join(wing_buffers[wing_name]), role)
            raw = run_stage(root, args.session_id, f"{wing_name}_reconciliation", role, model, rec_prompt, args.ollama_base_url, args.debate_temp, args.max_tokens_turn, args.seed, args.turn_timeout_sec, debate_validation_details, wing_name=wing_name, system_prompt=system_prompt)
            trace.append({"stage": f"{wing_name}_reconciliation", "role": role, "model": model, "output": raw})
            block = render_block(role, model, raw)
            transcript_blocks.append(block)
            wing_buffers[wing_name].append(block)

        alpha_summary = "\n\n".join(wing_buffers["alpha"])
        beta_summary = "\n\n".join(wing_buffers["beta"])

        critique_cfg = hierarchy["cross_channel"]["critique"]
        critique_role = str(critique_cfg.get("role", "CROSS_CRITIC")).strip()
        critique_model = str(critique_cfg.get("model", args.model_b)).strip()
        if neutral_prompt_mode:
            critique_prompt = build_neutral_debate_prompt(args.topic, alpha_summary + "\n\n" + beta_summary)
        else:
            critique_prompt = build_cross_prompt(args.topic, alpha_summary, beta_summary, critique_role, "cross critique")
        critique_raw = run_stage(root, args.session_id, "cross_critique", critique_role, critique_model, critique_prompt, args.ollama_base_url, args.debate_temp, args.max_tokens_turn, args.seed, args.turn_timeout_sec, debate_validation_details, system_prompt=system_prompt)
        trace.append({"stage": "cross_critique", "role": critique_role, "model": critique_model, "output": critique_raw})
        transcript_blocks.append(render_block(critique_role, critique_model, critique_raw))

        cross_exam_cfg = hierarchy["cross_channel"]["cross_exam"]
        cross_exam_role = str(cross_exam_cfg.get("role", "CROSS_EXAMINER")).strip()
        cross_exam_model = str(cross_exam_cfg.get("model", args.model_synth)).strip()
        if neutral_prompt_mode:
            cross_exam_prompt = build_neutral_debate_prompt(args.topic, alpha_summary + "\n\n" + beta_summary + "\n\n" + critique_raw)
        else:
            cross_exam_prompt = build_cross_prompt(args.topic, alpha_summary + "\n\n" + critique_raw, beta_summary + "\n\n" + critique_raw, cross_exam_role, "cross examination")
        cross_exam_raw = run_stage(root, args.session_id, "cross_exam", cross_exam_role, cross_exam_model, cross_exam_prompt, args.ollama_base_url, args.debate_temp, args.max_tokens_turn, args.seed, args.turn_timeout_sec, debate_validation_details, system_prompt=system_prompt)
        trace.append({"stage": "cross_exam", "role": cross_exam_role, "model": cross_exam_model, "output": cross_exam_raw})
        transcript_blocks.append(render_block(cross_exam_role, cross_exam_model, cross_exam_raw))

        king_cfg = hierarchy["king_synthesizer"]
        king_role = str(king_cfg.get("role", "KING_SYNTHESIZER")).strip()
        king_model = str(king_cfg.get("model", args.model_synth)).strip()
        if neutral_prompt_mode:
            king_prompt = build_neutral_king_prompt(args.topic, "\n\n".join(transcript_blocks), args.session_id)
        else:
            king_prompt = build_king_prompt(args.topic, "\n\n".join(transcript_blocks), args.session_id)
        king_raw = run_stage(root, args.session_id, "king_synthesis", king_role, king_model, king_prompt, args.ollama_base_url, args.synth_temp, args.max_tokens_synth, args.seed, args.synth_timeout_sec, canonical_validation_details, system_prompt=system_prompt)
        trace.append({"stage": "king_synthesis", "role": king_role, "model": king_model, "output": king_raw})

        metrics = deterministic_metrics(king_raw)
        answer = build_answer_payload(
            session_id=args.session_id,
            topic=args.topic,
            metrics=metrics,
            governance={
                "autonomy_mode": mode,
                "constitution_state_path": str(root / "constitution" / "constitution_state.json"),
                "contract_path": str(root / "synthesis" / "synthesis_contract.json"),
                "system_prompt_file": str(Path(args.system_prompt_file).resolve()) if args.system_prompt_file else None,
            },
            hierarchy=hierarchy,
            trace=trace,
            king_text=king_raw,
            output_paths={},
        )
        voice = build_sovereign_voice(answer, {"autonomy_mode": mode})
        report = build_praxis_report(answer, {"autonomy_mode": mode})
        dialog_text = "\n\n".join(transcript_blocks + [render_block(king_role, king_model, king_raw)])
        outputs = write_outputs(root, args.session_id, answer, voice, report, dialog_text)
        answer["outputs"] = outputs
        write_json_atomic(Path(outputs["praxis_answer_path"]), answer)
        write_json_atomic(Path(outputs["praxis_answer_session_path"]), answer)
        audit_path = audit_synthesis(root, args.session_id, answer, mode)

        summary = {
            "ok": True,
            "session_id": args.session_id,
            "topic": args.topic,
            "mode": mode,
            "contract": contract,
            "outputs": outputs,
            "constitution_audit_path": audit_path,
            "metrics": metrics,
        }
        append_log_line(root / "logs" / "system.txt", {"ts": utc_now_iso(), "source": "synth_king", "event": "synthesis_summary", "summary": summary, "session_id": args.session_id})
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except SynthesisError as exc:
        error_category = classify_stage_failure(exc)
        error = {
            "ok": False,
            "session_id": args.session_id,
            "topic": args.topic,
            "error": str(exc),
            "error_category": error_category,
        }
        append_log_line(root / "logs" / "system.txt", {"ts": utc_now_iso(), "source": "synth_king", "event": "synthesis_error", **error})
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


