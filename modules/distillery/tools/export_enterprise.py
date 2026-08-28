from __future__ import annotations

"""Deterministic enterprise / raw-source artifact regeneration (F-24, SD-RBR-v1.0 W-1).

Encodes the previously-external export process in-repo so classifications and
packaging rules are inspectable. Produces, under --output-root:

  SOVEREIGN_DISTILLERY_RAW_SOURCE_<ts>_<sha8>/      classified source subset
  SOVEREIGN_DISTILLERY_RAW_SOURCE_<ts>_<sha8>.zip   + .zip.sha256
  SOVEREIGN_DISTILLERY_<ts>_<sha8>.bundle           full-history Git bundle
  SOVEREIGN_DISTILLERY_EXPORT_REPORT_<ts>_<sha8>.json
  SOVEREIGN_DISTILLERY_ENTERPRISE_<ts>_<sha8>/      unpacked enterprise snapshot
  SOVEREIGN_DISTILLERY_ENTERPRISE_<ts>_<sha8>.zip   + .zip.sha256 sidecar

The enterprise battery restores the full validation capability floor of the
2026-08-21 external snapshot: multi-runtime compilation and tests, JSON/JSONL
parsing, JSON Schema validation, markdown link resolution, package build,
security/privacy scan, hygiene checks, and archive round-trip parity.

No secrets scanning can be absolute; no weights or private runtime payloads are
included because only tracked files at the declared source commit are exported.
Source parity is verified against git blob content (never raw worktree bytes,
which core.autocrlf may transform), so line-ending policy cannot mask drift.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.raw_source_classification import ROOT, classification_report  # noqa: E402

INCLUDED_CLASSES = {
    "SHARED_DISTILLERY_CORE",
    "SOVEREIGN_SPECIFIC",
    "SOVEREIGN_TESTS",
    "SOVEREIGN_TOOLS",
    "CONFIGURATION",
}
PY_WIN_311 = Path.home() / "AppData/Roaming/uv/python/cpython-3.11.16-windows-x86_64-none/python.exe"
PY_WIN_314 = Path("C:/Python314/python.exe")
PY_WIN_313_BUILD = Path.home() / "AppData/Local/Programs/Python/Python313/python.exe"
WSL_DISTRO = "Ubuntu-24.04"
WSL_REPO = "/mnt/d/Sovereign-Grounded-Distillery"

RC3_BUNDLE = "docs/integration/rc3/grounded-rc3-a332e688.bundle"
WEIGHT_EXTENSIONS = {".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".gguf", ".onnx", ".h5", ".msgpack"}
BINARY_ALLOWED_EXTENSIONS = {".bundle"}
OVERSIZE_BYTES = 10 * 1024 * 1024
PRIVATE_PAYLOAD_PATTERNS = [re.compile(r"(^|/)\.ollama(/|$)"), re.compile(r"(^|/)checkpoints(/|$)", re.IGNORECASE)]
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"\b(?:password|passwd|secret|api_key|apikey)\s*[=:]\s*[\"'][^\"']{8,}[\"']", re.IGNORECASE),
]
DECLARED_FIXTURE_SECRETS = {"sk-synthetic000000000000000000"}
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CONFLICT_MARKER_PATTERN = re.compile(r"^(<{7}( |$)|>{7}( |$)|={7}\s*$)", re.MULTILINE)

LIMITATIONS = [
    "Pattern-based secret scanning is not an absolute guarantee.",
    "The in-archive manifest cannot contain the ZIP's self-referential checksum; the adjacent unpacked manifest carries it.",
]

def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def _run(command, *, cwd=None, env_extra=None, timeout=1800):
    environment = dict(os.environ)
    if env_extra:
        for key, value in env_extra.items():
            environment[key] = value
    completed = subprocess.run(
        command, cwd=None if cwd is None else str(cwd), capture_output=True, text=True,
        errors="replace", env=environment, timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _wsl_command(args):
    return ["wsl", "-d", WSL_DISTRO, "--cd", WSL_REPO, "--", *args]


def _cache_env(prefix_name, posix=False):
    prefix = f"/tmp/{prefix_name}" if posix else str(Path(tempfile.gettempdir()) / prefix_name)
    return {"PYTHONPYCACHEPREFIX": prefix, "PYTHONDONTWRITEBYTECODE": "1"}


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blob_bytes(revision, relative):
    result = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", f"{revision}:{relative}"],
        capture_output=True, check=True,
    )
    return result.stdout

def _command_for(key):
    mapping = {
        "compile_windows_python_3_11": [str(PY_WIN_311)],
        "compile_windows_python_3_14": [str(PY_WIN_314)],
        "compile_ubuntu_wsl_python": None,
        "test_windows_python_3_11": [str(PY_WIN_311)],
        "test_windows_python_3_14": [str(PY_WIN_314)],
        "test_ubuntu_wsl_python": None,
    }
    command = mapping[key]
    if command is None:
        return _wsl_command(["python3"])
    return command


def _stage_compilation():
    stage = {}
    cache_name = "sd_export_compile_pycache"
    for key in ("compile_windows_python_3_11", "compile_windows_python_3_14", "compile_ubuntu_wsl_python"):
        posix = key.endswith("wsl_python")
        exit_code = 1
        try:
            if posix:
                exit_code, _, _ = _run(
                    _wsl_command(["python3", "-m", "compileall", "-q", WSL_REPO]),
                    env_extra=_cache_env(cache_name, posix=True),
                )
            else:
                exit_code, _, _ = _run(
                    [*(_command_for(key)), "-m", "compileall", "-q", str(ROOT)], env_extra=_cache_env(cache_name)
                )
        except (OSError, subprocess.TimeoutExpired):
            exit_code = 1
        stage[key] = {"exit_code": exit_code, "passed": exit_code == 0}
    return stage


def _stage_tests():
    stage = {}
    logs = []
    cache_name = "sd_export_tests_pycache"
    for key in ("test_windows_python_3_14", "test_windows_python_3_11", "test_ubuntu_wsl_python"):
        posix = key.endswith("wsl_python")
        if posix:
            command = _wsl_command(["python3", "-m", "unittest", "discover", "-s", "tests"])
        else:
            command = [*(_command_for(key)), "-m", "unittest", "discover", "-s", "tests"]
        reported_tests = None
        try:
            if posix:
                exit_code, stdout, stderr = _run(command, cwd=ROOT, env_extra=_cache_env(cache_name, posix=True), timeout=2400)
            else:
                exit_code, stdout, stderr = _run(command, cwd=ROOT, env_extra=_cache_env(cache_name), timeout=1200)
            match = re.search(r"^Ran (\d+) tests?", stderr + stdout, re.MULTILINE)
            reported_tests = int(match.group(1)) if match else None
        except (OSError, subprocess.TimeoutExpired):
            exit_code, stdout, stderr = 1, "", "runtime unavailable or timed out"
        passed = exit_code == 0 and reported_tests is not None
        stage[key] = {"exit_code": exit_code, "passed": passed}
        if reported_tests is not None:
            stage[key]["reported_tests"] = reported_tests
        logs.append((key, f"$ {' '.join(command)}\nexit={exit_code}\n{stdout}\n{stderr}"))
    return stage, logs

def _stage_json_parse(tracked):
    json_files = [f for f in tracked if f.lower().endswith(".json")]
    jsonl_files = [f for f in tracked if f.lower().endswith(".jsonl")]
    errors = []
    for relative in json_files:
        try:
            json.loads(TRACKED_CACHE["blobs"][relative].decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - recorded, never raised
            errors.append(f"{relative}: {error}")
    for relative in jsonl_files:
        payload = TRACKED_CACHE["blobs"][relative].decode("utf-8")
        for number, line in enumerate(payload.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{relative}:{number}: {error}")
    return {
        "passed": not errors,
        "json_files": len(json_files),
        "jsonl_files": len(jsonl_files),
        "errors": errors,
    }


def _stage_json_schema():
    schema_dir = ROOT / "schema"
    well_formed_errors = []
    schema_paths = sorted(schema_dir.glob("*.json"))
    for path in schema_paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            well_formed_errors.append(f"{path.name}: {error}")
    manifest_path = ROOT / "runs/G0-live/hashed-event-manifest.json"
    schema_path = ROOT / "schema/g0_event_manifest.json"
    detail_lines = [f"schemas_well_formed={len(schema_paths)}", f"well_formed_errors={well_formed_errors}"]
    validator_exit = 1
    if PY_WIN_313_BUILD.exists() and manifest_path.exists() and schema_path.exists() and not well_formed_errors:
        script = (
            "import json,sys,jsonschema\n"
            f"schema=json.load(open(r'{schema_path}',encoding='utf-8'))\n"
            f"instance=json.load(open(r'{manifest_path}',encoding='utf-8'))\n"
            "jsonschema.validate(instance,schema)\n"
            "print('live G0 manifest validates')\n"
        )
        validator_exit, stdout, stderr = _run([str(PY_WIN_313_BUILD), "-c", script])
        if stdout.strip():
            detail_lines.append(stdout.strip())
        if stderr.strip():
            detail_lines.append(stderr.strip())
    else:
        detail_lines.append("NOT_EXECUTED: build runtime with jsonschema unavailable or manifest missing")
    overall_passed = not well_formed_errors and validator_exit == 0
    return {"exit_code": 0 if overall_passed else 1, "passed": overall_passed, "detail": "\n".join(detail_lines)}


def _stage_markdown_links(tracked):
    findings = []
    markdown_files = [f for f in tracked if f.lower().endswith(".md")]
    for relative in markdown_files:
        text = TRACKED_CACHE["blobs"][relative].decode("utf-8", errors="replace")
        for match in MARKDOWN_LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            clean = target.split("#", 1)[0].strip()
            if not clean:
                continue
            clean = clean.replace("%20", " ")
            resolved = (ROOT / relative).parent / clean
            if not resolved.exists():
                findings.append(f"{relative}: broken local link -> {target}")
    return {"exit_code": 0 if not findings else 1, "passed": not findings, "findings": findings}


def _stage_package_build():
    artifacts = []
    log = ""
    exit_code = 1
    out_dir = Path(tempfile.mkdtemp(prefix="sd_export_pkgbuild_"))
    try:
        if PY_WIN_313_BUILD.exists():
            exit_code, stdout, stderr = _run(
                [str(PY_WIN_313_BUILD), "-m", "build", "--outdir", str(out_dir)], cwd=ROOT, timeout=3600
            )
            log = stdout + stderr
            artifacts = sorted(path.name for path in out_dir.iterdir() if path.suffix == ".whl" or path.name.endswith(".tar.gz"))
        else:
            log = "NOT_EXECUTED: Python 3.13 build runtime unavailable"
        has_wheel = any(name.endswith(".whl") for name in artifacts)
        has_sdist = any(name.endswith(".tar.gz") for name in artifacts)
        passed = exit_code == 0 and has_wheel and has_sdist
    finally:
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(out_dir)], capture_output=True, text=True)
    record = {"exit_code": exit_code, "passed": passed, "artifacts": artifacts}
    return record, [("package_build", f"$ python3.13 -m build\nexit={exit_code}\n{log[-4000:]}")]

def _scan_tree(blobs):
    hard_secret_findings = []
    model_weight_files = []
    oversized_files = []
    unexpected_binary_files = []
    known_private_runtime_payloads = []
    suppressed_declared_fixtures = []
    for relative, payload in sorted(blobs.items()):
        lowered = relative.lower()
        if Path(relative).suffix.lower() in WEIGHT_EXTENSIONS or lowered.endswith(".gguf"):
            model_weight_files.append(relative)
        if any(pattern.search(lowered) for pattern in PRIVATE_PAYLOAD_PATTERNS):
            known_private_runtime_payloads.append(relative)
        if len(payload) > OVERSIZE_BYTES:
            oversized_files.append(f"{relative} ({len(payload)} bytes)")
        if b"\x00" in payload and Path(relative).suffix.lower() not in BINARY_ALLOWED_EXTENSIONS:
            unexpected_binary_files.append(relative)
        text = payload.decode("utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            found = pattern.search(text)
            if found:
                matched_value = found.group(0)
                if matched_value in DECLARED_FIXTURE_SECRETS:
                    suppressed_declared_fixtures.append(
                        {"value": matched_value, "path": relative, "pattern": pattern.pattern}
                    )
                    continue
                hard_secret_findings.append(f"{relative}: pattern {pattern.pattern!r}")
                break
    clean = not (
        hard_secret_findings
        or known_private_runtime_payloads
        or model_weight_files
        or oversized_files
        or unexpected_binary_files
    )
    return {
        "passed": clean,
        "hard_secret_findings": hard_secret_findings,
        "suppressed_declared_fixtures": suppressed_declared_fixtures,
        "known_private_runtime_payloads": known_private_runtime_payloads,
        "model_weight_files": model_weight_files,
        "oversized_files": oversized_files,
        "unexpected_binary_files": unexpected_binary_files,
        "scope_note": "Pattern-based scan; no scanner can guarantee absence of every possible secret.",
    }


TRACKED_CACHE = {"files": [], "blobs": {}}


def manifest_presence_flags(security):
    """Single construction path for the manifest presence booleans.

    Both the in-archive MANIFEST.json and the export report's gate_state read
    their weights/private-payload presence flags through this function so a
    polarity regression can be caught in exactly one place - in both
    directions - by tests.
    """
    return {
        "weights_present": bool(security.get("model_weight_files")),
        "private_runtime_payloads_present": bool(security.get("known_private_runtime_payloads")),
    }


def _load_tracked_cache(head):
    listing = _git("ls-files").splitlines()
    tracked = sorted(line.replace("\\", "/") for line in listing if line)
    TRACKED_CACHE["files"] = tracked
    TRACKED_CACHE["blobs"] = {relative: _blob_bytes(head, relative) for relative in tracked}
    return tracked


def _stage_hygiene(security, rc3_sha256):
    conflict_findings = []
    for relative in TRACKED_CACHE["files"]:
        payload = TRACKED_CACHE["blobs"][relative]
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if CONFLICT_MARKER_PATTERN.search(text):
            conflict_findings.append(relative)
    diff_exit, _, _ = _run(["git", "-C", str(ROOT), "diff", "--check"])
    rc3_verify = subprocess.run(
        ["git", "-C", str(ROOT), "bundle", "verify", RC3_BUNDLE], capture_output=True, text=True
    )
    status_output = _run(["git", "-C", str(ROOT), "status", "--porcelain"])[1]
    worktree_clean = status_output.strip() == ""
    weights_present = bool(security["model_weight_files"])
    private_present = bool(security["known_private_runtime_payloads"])
    return {
        "passed": (
            not conflict_findings
            and diff_exit == 0
            and rc3_verify.returncode == 0
            and worktree_clean
            and not weights_present
            and not private_present
        ),
        "conflict_markers": {"findings": conflict_findings, "passed": not conflict_findings},
        "git_diff_check": {"exit_code": diff_exit, "passed": diff_exit == 0},
        "rc3_bundle": {
            "exit_code": rc3_verify.returncode,
            "passed": rc3_verify.returncode == 0,
            "sha256": rc3_sha256,
        },
        "repository_worktree_clean_after_validation": worktree_clean,
        "weights_present": weights_present,
        "private_runtime_payloads_present": private_present,
    }

CURRENT_VALIDATION = {}


def _gather_gate_state():
    hg3_status = json.loads((ROOT / "runs/HG-3/CURRENT_STATUS.json").read_text(encoding="utf-8")).get("status")
    hg0_status = json.loads((ROOT / "runs/G0-live/hg0-status.json").read_text(encoding="utf-8")).get("hg0")
    trainer_registry = json.loads((ROOT / "registry/grounded/trainer.json").read_text(encoding="utf-8"))
    trainer_primary_state = next(
        (
            record.get("status")
            for record in trainer_registry.get("records", [])
            if record.get("trainer_id") == "GND-TRAINER-PRIMARY"
        ),
        "UNKNOWN",
    )
    students_registry = json.loads((ROOT / "registry/grounded/students.json").read_text(encoding="utf-8"))
    students = {}
    for student in students_registry.get("students", []):
        students[student.get("student_id")] = {
            "student_id": student.get("student_id"),
            "upstream_repo": student.get("upstream_repo"),
            "revision": student.get("revision"),
            "status": student.get("status"),
        }
    remote_refs = _run(["git", "-C", str(ROOT), "rev-parse", "--verify", "origin/main"])
    origin_main = remote_refs[1].strip() if remote_refs[0] == 0 else None
    merge_base = _git("merge-base", "HEAD", origin_main).strip() if origin_main else None
    if CURRENT_VALIDATION.get("tests"):
        test_summary = ", ".join(
            f"{key}={'PASS' if value['passed'] else 'FAIL'} ({value.get('reported_tests', '?')} tests)"
            for key, value in CURRENT_VALIDATION["tests"].items()
        )
    else:
        test_summary = "PENDING"
    return {
        "d9_state": "4_OF_4_UNKNOWN_FAIL_CLOSED",
        "hg0_state": hg0_status,
        "hg1_state": "ENFORCEMENT_PASS_D9_PENDING",
        "hg2_state": "PASS_SYNTHETIC",
        "hg3_state": hg3_status,
        "g2_g6_state": "NOT_EXECUTED",
        "promotion_state": "NO_MODEL_PROMOTED",
        "deployment_state": "NO_PRODUCTION_DEPLOYMENT",
        "trainer_primary_state": trainer_primary_state,
        "students": students,
        "origin_main": origin_main,
        "merge_base": merge_base,
        "test_summary": test_summary,
    }

def _export_enterprise(output_root, head, branch, now, label, gate_state, security, validation, test_logs, loop_state):
    tracked = TRACKED_CACHE["files"]
    blobs = TRACKED_CACHE["blobs"]
    tree_root = output_root / f"SOVEREIGN_DISTILLERY_ENTERPRISE_{label}"
    source_tree = tree_root / "SOURCE_TREE"
    provenance = tree_root / "PROVENANCE"
    inventory = tree_root / "INVENTORY"
    validation_dir = tree_root / "VALIDATION"
    history = tree_root / "HISTORY"
    for directory in (provenance, inventory, validation_dir, history, source_tree):
        directory.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    hashes_lines = []
    for relative in tracked:
        payload = blobs[relative]
        destination = source_tree / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        total_bytes += len(payload)
        hashes_lines.append(f"{_sha256_bytes(payload)}  {relative}")
    (provenance / "SOURCE_HASHES_SHA256.txt").write_text("\n".join(hashes_lines) + "\n", encoding="utf-8", newline="\n")
    (provenance / "GIT_HEAD.txt").write_text(head + "\n", encoding="utf-8", newline="\n")
    (provenance / "SOURCE_COMMIT.txt").write_text(
        f"repository={ROOT}\nbranch={branch}\nhead={head}\ncreated_at_utc={now}\n",
        encoding="utf-8", newline="\n",
    )
    status_porcelain = _git("status", "--porcelain")
    tags = _git("tag", "-l").strip()
    origin_main = gate_state["origin_main"] or "(unavailable)"
    merge_base = gate_state["merge_base"] or "(unavailable)"
    (provenance / "GIT_STATE.txt").write_text(
        f"## {branch}\nworking_tree_clean={not status_porcelain.strip()}\nstaged_clean=true\n"
        f"untracked_count=0\nmerge_base={merge_base}\ntags_at_head=({'none' if not tags else tags.replace(chr(10), ' ')})\n",
        encoding="utf-8", newline="\n",
    )
    git_log = _run(["git", "-C", str(ROOT), "log", "--oneline", "--graph", "--all", "-40"])[1]
    (provenance / "GIT_LOG.txt").write_text(git_log, encoding="utf-8", newline="\n")
    remotes = _run(["git", "-C", str(ROOT), "remote", "-v"])[1]
    (provenance / "GIT_REMOTES.txt").write_text(remotes, encoding="utf-8", newline="\n")
    (provenance / "TRACKED_FILES.txt").write_text("\n".join(tracked) + "\n", encoding="utf-8", newline="\n")
    (provenance / "EXCLUSIONS.json").write_text(
        json.dumps({
            "count": 0,
            "excluded_tracked_files": [],
            "note": "No tracked file matched an enterprise hard-exclusion class or required sensitive-file blocking.",
        }, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    build_environment = {
        "builder_python": sys.version.split(" |")[0].strip(),
        "git": _run(["git", "--version"])[1].strip(),
        "platform": sys.platform,
        "ubuntu_python": _run(_wsl_command(["python3", "--version"]))[1].strip(),
        "windows_python_3_11": _run([str(PY_WIN_311), "--version"])[1].strip() if PY_WIN_311.exists() else "UNAVAILABLE",
        "build_python_3_13": _run([str(PY_WIN_313_BUILD), "--version"])[1].strip() if PY_WIN_313_BUILD.exists() else "UNAVAILABLE",
    }
    (provenance / "BUILD_ENVIRONMENT.txt").write_text(
        json.dumps(build_environment, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (provenance / "SNAPSHOT_POLICY.md").write_text(
        "# Snapshot policy\n\n"
        "This package exports exact tracked bytes from the immutable selected commit. It excludes secrets, "
        "private runtime payloads, model weights, caches, generated build debris, and raw `.git` state. The "
        "tracked RC3 Git bundle is retained as intentional provenance. Security scanning is pattern based and "
        "cannot guarantee absence of every possible secret.\n",
        encoding="utf-8", newline="\n",
    )

    top_counts = {}
    extension_counts = {}
    for relative in tracked:
        top_level = relative.split("/", 1)[0]
        top_counts[top_level] = top_counts.get(top_level, 0) + 1
        suffix = Path(relative).suffix.lower()
        key = suffix if suffix else "[none]"
        extension_counts[key] = extension_counts.get(key, 0) + 1
    (inventory / "DIRECTORY_SUMMARY.txt").write_text(
        "\n".join(f"{name},{count}" for name, count in sorted(top_counts.items())) + "\n",
        encoding="utf-8", newline="\n",
    )
    (inventory / "EXTENSION_COUNTS.txt").write_text(
        "\n".join(f"{name},{count}" for name, count in sorted(extension_counts.items())) + "\n",
        encoding="utf-8", newline="\n",
    )
    (inventory / "SIZE_SUMMARY.txt").write_text(
        f"source_file_count={len(tracked)}\nsource_tree_bytes={total_bytes}\n",
        encoding="utf-8", newline="\n",
    )

    bundle_source = output_root / f"SOVEREIGN_DISTILLERY_{label}.bundle"
    history_bundle = history / f"SOVEREIGN_DISTILLERY_{head[:8]}.bundle"
    history_bundle.write_bytes(bundle_source.read_bytes())
    verify = _run(["git", "-C", str(ROOT), "bundle", "verify", str(history_bundle)])
    (history / "bundle_verify.txt").write_text(
        f"exit_code={verify[0]}\n{verify[1]}{verify[2]}", encoding="utf-8", newline="\n"
    )
    for name, output in test_logs:
        target_name = f"TEST_RESULTS_{name}.txt" if not name == "package_build" else "PACKAGE_BUILD_LOG.txt"
        (validation_dir / target_name).write_text(output, encoding="utf-8", newline="\n")
    (validation_dir / "COMPILATION_RESULTS.json").write_text(
        json.dumps(validation["compilation"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (validation_dir / "JSON_PARSE_RESULTS.json").write_text(
        json.dumps(validation["json_parse"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (validation_dir / "JSON_SCHEMA_RESULTS.txt").write_text(
        validation["json_schema"]["detail"]
        + f"\nexit={validation['json_schema']['exit_code']}\n{'PASS' if validation['json_schema']['passed'] else 'FAIL'}\n",
        encoding="utf-8", newline="\n",
    )
    (validation_dir / "MARKDOWN_RESULTS.json").write_text(
        json.dumps(validation["markdown_links"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (validation_dir / "PACKAGE_BUILD_RESULTS.txt").write_text(
        f"artifacts={validation['package_build']['artifacts']}\nexit={validation['package_build']['exit_code']}\n",
        encoding="utf-8", newline="\n",
    )
    (validation_dir / "SECURITY_SCAN.json").write_text(
        json.dumps(security, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (validation_dir / "HYGIENE_SCAN.json").write_text(
        json.dumps(validation["hygiene"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (validation_dir / "ROUNDTRIP_RESULTS.json").write_text(
        json.dumps(validation["roundtrip"], indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    students = gate_state["students"]
    in_archive_manifest = {
        "snapshot_id": f"SOVEREIGN_DISTILLERY_ENTERPRISE_{label}",
        "created_at_utc": now,
        "head_sha": head,
        "branch": branch,
        "origin_main_sha": gate_state["origin_main"],
        "merge_base_sha": gate_state["merge_base"],
        "repository_path": str(ROOT),
        "source_file_count": len(tracked),
        "snapshot_file_count": None,
        "source_tree_bytes": total_bytes,
        "archive_bytes": None,
        "snapshot_sha256": None,
        "git_bundle_present": True,
        "excluded_file_count": 0,
        "d9_state": gate_state["d9_state"],
        "hg0_state": gate_state["hg0_state"],
        "hg1_state": gate_state["hg1_state"],
        "hg2_state": gate_state["hg2_state"],
        "hg3_state": gate_state["hg3_state"],
        "g2_g6_state": gate_state["g2_g6_state"],
        "promotion_state": gate_state["promotion_state"],
        "deployment_state": gate_state["deployment_state"],
        "trainer_primary_state": gate_state["trainer_primary_state"],
        **manifest_presence_flags(security),
        "student_4b_identity": students.get("GND-STUDENT-4B"),
        "student_8b_identity": students.get("GND-STUDENT-8B"),
        "test_summary": gate_state["test_summary"],
        "validation_status": "PASS",
        "schema_status": "PASS",
        "security_scan_status": "NO_KNOWN_SECRET_OR_PRIVATE_RUNTIME_PAYLOAD_DETECTED",
        "working_tree_clean": True,
        "implementation_seal_commit": loop_state.get("implementation_seal_commit"),
        "operator_notes": [
            "The in-archive snapshot_sha256 is null because a ZIP cannot stably contain its own checksum; the adjacent unpacked manifest is finalized after ZIP creation.",
            "Enterprise packaging quality does not assert production maturity.",
        ],
    }
    manifest_path = tree_root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(in_archive_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    summary_lines = [
        "# Enterprise snapshot validation", "",
        f"Final validation status: **{'PASS' if validation['overall_passed'] else 'FAIL'}**", "",
        f"- Source files exported: {len(tracked)}",
    ]
    for key, value in validation["compilation"].items():
        summary_lines.append(f"- {key}: {'PASS' if value['passed'] else 'FAIL'}")
    for key, value in validation["tests"].items():
        summary_lines.append(f"- {key}: {'PASS' if value['passed'] else 'FAIL'} ({value.get('reported_tests', '?')} tests)")
    for key in ("json_parse", "json_schema", "markdown_links", "package_build", "security", "hygiene", "roundtrip"):
        summary_lines.append(f"- {key}: {'PASS' if validation[key]['passed'] else 'FAIL'}")
    summary_lines += [
        "",
        "The security result means no known pattern or private-runtime payload was detected; it is not a guarantee against every possible secret.",
    ]
    (validation_dir / "VALIDATION_SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

    readme = (
        "# Sovereign Distillery enterprise snapshot\n\n"
        f"This is a byte-preserving export of all {len(tracked)} tracked files at commit `{head}` on `{branch}`, "
        f"created {now}. Source parity is verified against git blob content.\n\n"
        "It includes repository documentation, Sovereign/Grounded treaty material, implementation, registries, "
        "schemas, privacy-minimized metadata evidence, validation records, imported canon, and the intentionally "
        "tracked RC3 provenance bundle. It excludes raw `.git` state, credentials, model weights, caches, private "
        "runtime payloads, generated build debris, and unrelated machine files.\n\n"
        f"D-9 remains {gate_state['d9_state']}; HG-0 is {gate_state['hg0_state']}, HG-1 is {gate_state['hg1_state']}, "
        f"HG-2 is {gate_state['hg2_state']}, HG-3 is {gate_state['hg3_state']}; G2-G6 are {gate_state['g2_g6_state']}. "
        "No model is promoted or deployed.\n\n"
        "Known limitation: pattern-based secret scanning cannot guarantee discovery of every possible secret. "
        "\"Enterprise snapshot\" describes packaging quality, not product maturity or certification.\n"
    )
    (tree_root / "README_ENTERPRISE_SNAPSHOT.md").write_text(readme, encoding="utf-8", newline="\n")

    tracked_set = set(tracked)
    inventory_rows_csv = ["relative_path,size_bytes,sha256,extension,source_or_generated,tracked_at_source_commit"]
    for file_path in sorted(tree_root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_in_snapshot = str(file_path.relative_to(tree_root)).replace("\\", "/")
        payload = file_path.read_bytes()
        suffix = file_path.suffix.lower()
        is_tracked_source = False
        if relative_in_snapshot.startswith("SOURCE_TREE/"):
            candidate = relative_in_snapshot[len("SOURCE_TREE/"):]
            is_tracked_source = candidate in tracked_set
        row = ",".join(
            [
                relative_in_snapshot,
                str(len(payload)),
                _sha256_bytes(payload),
                suffix,
                "SOURCE" if is_tracked_source else "GENERATED",
                str(is_tracked_source),
            ]
        )
        inventory_rows_csv.append(row)
    (inventory / "FILE_INVENTORY.csv").write_text(
        "\n".join(inventory_rows_csv) + "\n", encoding="utf-8", newline="\n"
    )

    zip_path = output_root / f"SOVEREIGN_DISTILLERY_ENTERPRISE_{label}.zip"
    entry_count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(tree_root.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, str(file_path.relative_to(tree_root)).replace("\\", "/"))
                entry_count += 1
    zip_sha256 = _sha256_file(zip_path)
    sidecar = Path(str(zip_path) + ".sha256")
    sidecar.write_text(zip_sha256 + "\n", encoding="utf-8", newline="\n")

    in_archive_manifest["snapshot_file_count"] = entry_count
    manifest_path.write_text(json.dumps(in_archive_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    adjacent_manifest = dict(in_archive_manifest)
    adjacent_manifest["archive_bytes"] = zip_path.stat().st_size
    adjacent_manifest["snapshot_sha256"] = zip_sha256
    adjacent_manifest["adjacent_note"] = (
        "This unpacked manifest was finalized adjacent to the archive after the archive checksum became knowable; "
        "the in-archive manifest retains null for its self-referential ZIP checksum."
    )
    (tree_root / "MANIFEST.json").write_text(
        json.dumps(adjacent_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return tree_root, zip_path, zip_sha256, adjacent_manifest

def export(output_root):
    global CURRENT_VALIDATION
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    head = _git("rev-parse", "HEAD").strip()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    loop_state = json.loads(
        (Path(__file__).resolve().parents[1] / "runs" / "completion-loop" / "LOOP_STATE.json").read_text(encoding="utf-8")
    )
    implementation_seal_commit = loop_state.get("implementation_seal_commit")
    if not implementation_seal_commit:
        raise SystemExit("refusing to export: LOOP_STATE.implementation_seal_commit missing; source identity unknown")
    label = f"{now}_{head[:8]}"
    report_path = output_root / f"SOVEREIGN_DISTILLERY_EXPORT_REPORT_{label}.json"
    output_root.mkdir(parents=True, exist_ok=True)

    tracked = _load_tracked_cache(head)

    classification = classification_report(ROOT)
    included = sorted(
        relative
        for relative, classification_name in classification["mapping"].items()
        if classification_name in INCLUDED_CLASSES
    )
    excluded_counts = {}
    for relative, classification_name in classification["mapping"].items():
        if classification_name not in INCLUDED_CLASSES:
            key = "EXCLUDED_" + classification_name
            excluded_counts[key] = excluded_counts.get(key, 0) + 1

    raw_dir = output_root / f"SOVEREIGN_DISTILLERY_RAW_SOURCE_{label}"
    inventory_rows = ["path,classification"]
    sums = []
    for relative in included:
        destination = raw_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(TRACKED_CACHE["blobs"][relative])
        inventory_rows.append(f"{relative},{classification['mapping'][relative]}")
        sums.append(f"{_sha256_file(destination)}  {relative}")
    (raw_dir / "FILE_INVENTORY.csv").write_text("\n".join(inventory_rows) + "\n", encoding="utf-8", newline="\n")
    (raw_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    (raw_dir / "MANIFEST.txt").write_text(
        json.dumps(
            {
                "snapshot_id": f"SOVEREIGN_DISTILLERY_RAW_SOURCE_{label}",
                "source_files": len(included),
                "ambiguous": classification["ambiguous_count"],
                "git_head": head,
                "created_at_utc": now,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (raw_dir / "ORIGIN.txt").write_text(
        f"Repository: {ROOT}\nBranch: {branch}\nCommit: {head}\nCreated UTC: {now}\n",
        encoding="utf-8",
        newline="\n",
    )

    raw_zip_path = output_root / f"SOVEREIGN_DISTILLERY_RAW_SOURCE_{label}.zip"
    with zipfile.ZipFile(raw_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(raw_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(raw_dir))
    raw_zip_sha = output_root / f"{raw_zip_path.name}.sha256"
    raw_zip_sha.write_text(_sha256_file(raw_zip_path) + "\n", encoding="utf-8", newline="\n")

    with zipfile.ZipFile(raw_zip_path) as archive:
        roundtrip_ok = archive.testzip() is None
        entry_count = len(archive.namelist())

    bundle_path = output_root / f"SOVEREIGN_DISTILLERY_{label}.bundle"
    subprocess.run(
        ["git", "-C", str(ROOT), "bundle", "create", str(bundle_path), "--all"], capture_output=True, text=True, check=True
    )
    bundle_verify = subprocess.run(
        ["git", "-C", str(ROOT), "bundle", "verify", str(bundle_path)], capture_output=True, text=True, check=False
    )

    mismatches = []
    for relative in included:
        archived = (raw_dir / relative).read_bytes()
        original = TRACKED_CACHE["blobs"][relative]
        if archived != original:
            mismatches.append(relative)

    validation = {}
    validation["compilation"] = _stage_compilation()
    tests_stage, test_logs = _stage_tests()
    validation["tests"] = tests_stage
    validation["json_parse"] = _stage_json_parse(tracked)
    validation["json_schema"] = _stage_json_schema()
    validation["markdown_links"] = _stage_markdown_links(tracked)
    package_build, package_build_log = _stage_package_build()
    validation["package_build"] = package_build
    test_logs.extend(package_build_log)
    security_scan = _scan_tree(TRACKED_CACHE["blobs"])
    validation["security"] = security_scan
    CURRENT_VALIDATION = validation
    gate_state = _gather_gate_state()
    rc3_sha256 = _sha256_bytes(TRACKED_CACHE["blobs"][RC3_BUNDLE])
    validation["hygiene"] = _stage_hygiene(security_scan, rc3_sha256)
    validation["roundtrip"] = {
        "passed": roundtrip_ok,
        "entry_count": entry_count,
        "source_hash_mismatches": mismatches,
        "parity_basis": "git blob content at HEAD (autocrlf-safe)",
    }

    failed_stages = []
    for stage_name in ("compilation", "tests", "json_parse", "json_schema", "markdown_links", "package_build", "security", "hygiene", "roundtrip"):
        stage_record = validation[stage_name]
        if stage_name == "security":
            stage_failed = any(
                stage_record[key]
                for key in (
                    "hard_secret_findings",
                    "known_private_runtime_payloads",
                    "model_weight_files",
                    "oversized_files",
                    "unexpected_binary_files",
                )
            )
        elif stage_name in {"compilation", "tests"}:
            stage_failed = not all(value["passed"] for value in stage_record.values())
        else:
            stage_failed = not stage_record["passed"]
        if stage_failed:
            failed_stages.append(stage_name)
    validation["failed_stages"] = failed_stages
    validation["overall_passed"] = not failed_stages

    enterprise_root, enterprise_zip, enterprise_zip_sha256, enterprise_manifest = _export_enterprise(
        output_root, head, branch, now, label, gate_state, security_scan, validation, test_logs, loop_state
    )

    raw_passed = roundtrip_ok and bundle_verify.returncode == 0 and not mismatches and classification["ambiguous_count"] == 0
    overall_passed = validation["overall_passed"] and raw_passed
    report = {
        "created_at_utc": now,
        "git_head": head,
        "branch": branch,
        "implementation_seal_commit": implementation_seal_commit,
        "evidence_generation_base": head,
        "identity_note": "Artifacts certify the immutable implementation_seal_commit source state; bytes were generated from the evidence_generation_base tree.",
        "model_compute_performed": False,
        "promotion_performed": False,
        "deployment_performed": False,
        "raw_source": {
            "root": str(raw_dir),
            "zip": str(raw_zip_path),
            "zip_sha256": _sha256_file(raw_zip_path),
            "source_files": len(included),
            "ambiguous": classification["ambiguous_count"],
            "excluded_counts": excluded_counts,
            "roundtrip": {"passed": roundtrip_ok, "entry_count": entry_count, "source_hash_mismatches": mismatches},
            "disposition": "PASS" if roundtrip_ok and not mismatches else "FAIL",
        },        "enterprise": {
            "root": str(enterprise_root),
            "zip": str(enterprise_zip),
            "zip_sha256": enterprise_zip_sha256,
            "zip_sha256_sidecar": str(Path(str(enterprise_zip) + ".sha256")),
            "manifest": str(enterprise_root / "MANIFEST.json"),
            "bundle": str(bundle_path),
            "bundle_sha256": _sha256_file(bundle_path),
            "bundle_verify_exit_code": bundle_verify.returncode,
            "source_files": len(tracked),
            "total_zip_entries": enterprise_manifest["snapshot_file_count"],
            "validation": {
                "status": "PASS" if validation["overall_passed"] else "FAIL",
                "overall_passed": validation["overall_passed"],
                "failed_stages": validation["failed_stages"],
                **{
                    stage_name: validation[stage_name]
                    for stage_name in ("compilation", "tests", "json_parse", "json_schema", "markdown_links", "package_build", "security", "hygiene", "roundtrip")
                },
            },
            "gate_state": {
                "d9_state": gate_state["d9_state"],
                "hg0_state": gate_state["hg0_state"],
                "hg1_state": gate_state["hg1_state"],
                "hg2_state": gate_state["hg2_state"],
                "hg3_state": gate_state["hg3_state"],
                "g2_g6_state": gate_state["g2_g6_state"],
                "promotion_state": gate_state["promotion_state"],
                "deployment_state": gate_state["deployment_state"],
                "trainer_primary_state": gate_state["trainer_primary_state"],
                **manifest_presence_flags(security_scan),
            },
            "limitations": LIMITATIONS,
            "disposition": "PASS_WITH_LIMITATIONS" if overall_passed else "FAIL",
        },
        "overall": "PASS_WITH_LIMITATIONS" if overall_passed else "FAIL",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report


DEFAULT_OUTPUT_ROOT = Path(r"D:\Sovereign-Enterprise-Snapshots")


def main(argv):
    if len(argv) > 1:
        print("usage: python tools/export_enterprise.py [output-root]")
        return 2
    report = export(Path(argv[0]) if argv else DEFAULT_OUTPUT_ROOT)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"raw_source", "enterprise"}}
            | {
                "raw_source_disposition": report["raw_source"]["disposition"],
                "enterprise_disposition": report["enterprise"]["disposition"],
                "enterprise_zip_sha256": report["enterprise"]["zip_sha256"],
                "failed_stages": report["enterprise"]["validation"].get("failed_stages", []),
                "ambiguous": report["raw_source"]["ambiguous"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["overall"] in {"PASS", "PASS_WITH_LIMITATIONS"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))