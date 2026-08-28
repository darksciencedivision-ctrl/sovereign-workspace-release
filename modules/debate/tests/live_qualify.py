"""Live qualification of configured candidate seats through the real app path."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from websockets.sync.client import connect


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Python314\python.exe")
CANDIDATES = tuple(
    item.strip()
    for item in os.environ.get(
        "QUALIFICATION_CANDIDATES",
        "qwen3:14b,deepseek-r1:14b,qwen3.6:35b,gpt-oss:20b",
    ).split(",")
    if item.strip()
)
RESULT_PATH = Path(
    os.environ.get("QUALIFICATION_OUTPUT", ROOT / "audit" / "v1_qualification.json")
)


def iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_port(port: int, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"app exited before opening port: {process.returncode}")
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"app did not open port {port}")


def stop(process: subprocess.Popen) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return process.returncode


def config_for(model: str, port: int) -> dict:
    return {
        "ollama_url": "http://127.0.0.1:11434",
        "port": port,
        "seats": [
            {
                "name": "Neo",
                "model": model,
                "color": "#4fd1ff",
                "persona": "Constructive systems thinker; answer directly and advance the issue.",
            },
            {
                "name": "Clue",
                "model": model,
                "color": "#7dffa0",
                "persona": "Skeptical challenger; test assumptions and concede strong points.",
            },
        ],
        "topic_rotate_turns": 0,
        "anchor_every_turns": 0,
        "turn_delay_ms": 300,
        "context_turns": 8,
        "min_turn_chars": 0,
        "num_predict": 320,
        "temperature": 0.7,
        "top_p": 0.9,
        "insight_panel": False,
        "extractor_model": "dolphin-llama3:8b",
        "insight_timeout_seconds": 10,
        "insight_queue_max": 2,
        "empty_spoken_retry_count": 1,
        "repetition_overlap_threshold": 0.6,
        "repetition_min_tokens": 20,
        "consensus_window_turns": 4,
        "consensus_challenge_weight": 3.0,
    }


def qualify_one(model: str, temp_dir: Path) -> dict:
    port = available_port()
    config_path = temp_dir / f"{model.replace(':', '_').replace('/', '_')}.json"
    config_path.write_text(
        json.dumps(config_for(model, port), indent=2) + "\n", encoding="utf-8"
    )
    stdout_path = temp_dir / f"{config_path.stem}.stdout.log"
    stderr_path = temp_dir / f"{config_path.stem}.stderr.log"
    out = stdout_path.open("w", encoding="utf-8")
    err = stderr_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CONFIG_PATH": str(config_path),
            "OLLAMA_URL": "http://127.0.0.1:11434",
            "PYTHONUTF8": "1",
        }
    )
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [str(PYTHON), str(ROOT / "app.py")],
        cwd=ROOT,
        env=env,
        stdout=out,
        stderr=err,
        creationflags=creationflags,
    )
    record = {
        "model": model,
        "started_at": iso(),
        "port": port,
        "pid": process.pid,
        "turns": [],
        "responsive": False,
        "leakage": [],
        "errors": [],
    }
    ws = None
    active = {}
    ended = {}
    try:
        wait_for_port(port, process, timeout=30)
        ws = connect(f"ws://127.0.0.1:{port}/ws", open_timeout=20)
        snapshot = json.loads(ws.recv(timeout=20))
        record["topic_at_connect"] = snapshot.get("topic")
        responsiveness_start = time.monotonic()
        response = httpx.get(f"http://127.0.0.1:{port}/api/models", timeout=20)
        record["responsive"] = (
            response.status_code == 200
            and time.monotonic() - responsiveness_start < 20
        )
        deadline = time.monotonic() + 900
        while len(record["turns"]) < 3 and time.monotonic() < deadline:
            try:
                event = json.loads(
                    ws.recv(timeout=min(30, max(1, deadline - time.monotonic())))
                )
            except TimeoutError:
                health = httpx.get(
                    f"http://127.0.0.1:{port}/api/models", timeout=20
                )
                if health.status_code != 200:
                    record["errors"].append(
                        f"app health check returned {health.status_code}"
                    )
                    break
                continue
            event_type = event.get("type")
            key = (event.get("seat"), event.get("turn"))
            if event_type == "turn_start":
                active[key] = {
                    "turn": event["turn"],
                    "seat": event["seat"],
                    "model": event.get("model"),
                    "move": event.get("move"),
                    "move_reason": event.get("move_reason"),
                    "started_at": iso(),
                    "first_public_observed_at": None,
                    "fragment_events": 0,
                    "characters": 0,
                }
            elif event_type == "token":
                # Public token events intentionally omit the numeric turn for
                # backward compatibility. Associate with the active seat turn.
                seat_keys = [
                    candidate_key
                    for candidate_key in active
                    if candidate_key[0] == event.get("seat")
                ]
                if seat_keys:
                    key = seat_keys[-1]
                else:
                    continue
                if active[key]["first_public_observed_at"] is None:
                    active[key]["first_public_observed_at"] = iso()
                text = event.get("text", "")
                active[key]["fragment_events"] += 1
                active[key]["characters"] += len(text)
                if any(tag in text.lower() for tag in ("<think", "<analysis", "<reasoning")):
                    record["leakage"].append({"key": key, "event": "token"})
            elif event_type == "turn_end":
                ended[key] = event.get("text", "")
                if any(
                    tag in ended[key].lower()
                    for tag in ("<think", "<analysis", "<reasoning")
                ):
                    record["leakage"].append({"key": key, "event": "turn_end"})
            elif event_type == "turn_metrics" and key in active:
                turn = active.pop(key)
                turn["finished_at"] = iso()
                turn["public_text"] = ended.pop(key, "")
                turn["public_nonempty"] = bool(turn["public_text"].strip())
                turn["retry_needed"] = len(event.get("attempts", [])) > 1
                turn["retry_succeeded"] = turn["retry_needed"] and turn["public_nonempty"]
                turn["attempts"] = event.get("attempts", [])
                turn["hidden_reasoning_present"] = any(
                    attempt.get("hidden_reasoning_present")
                    for attempt in turn["attempts"]
                )
                turn["budget_exhausted"] = any(
                    attempt.get("budget_exhausted") for attempt in turn["attempts"]
                )
                turn["cold_or_warm"] = "cold" if not record["turns"] else "warm"
                record["turns"].append(turn)
        if len(record["turns"]) < 3:
            record["errors"].append("qualification deadline before three completed turns")
    except Exception as exc:
        record["errors"].append(repr(exc))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        record["app_exit_code"] = stop(process)
        out.close()
        err.close()
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        record["traceback"] = "traceback" in (stdout + stderr).lower()
        record["stderr"] = stderr[-4000:]
        record["finished_at"] = iso()

    nonempty = sum(turn["public_nonempty"] for turn in record["turns"])
    reasoning_budget_burns = 0
    for turn in record["turns"]:
        first_attempt = turn["attempts"][0] if turn["attempts"] else {}
        first_public = first_attempt.get("first_public_seconds")
        duration = first_attempt.get("duration_seconds") or 0
        exhausted_in_reasoning = (
            turn["budget_exhausted"]
            and (
                not turn["public_nonempty"]
                or first_public is None
                or (duration and first_public / duration >= 0.80)
            )
        )
        reasoning_budget_burns += bool(exhausted_in_reasoning)
    bounded = len(record["turns"]) == 3 or bool(record["errors"])
    record["qualified"] = (
        nonempty >= 2
        and not record["leakage"]
        and bounded
        and reasoning_budget_burns < 2
        and record["responsive"]
        and not record["traceback"]
    )
    record["qualification_basis"] = {
        "nonempty_public_turns": nonempty,
        "zero_stage_leakage": not record["leakage"],
        "bounded_outcomes": bounded,
        "reasoning_budget_burns": reasoning_budget_burns,
        "repeated_reasoning_budget_burn": reasoning_budget_burns >= 2,
        "app_responsive": record["responsive"],
        "traceback_free": not record["traceback"],
    }
    return record


def main() -> int:
    production_hash = hash_file(ROOT / "config.json")
    tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=20).json()
    installed = {item["name"] for item in tags.get("models", [])}
    temp_dir = Path(tempfile.mkdtemp(prefix=".qualification-", dir=ROOT / "tests"))
    evidence = {
        "started_at": iso(),
        "production_config_hash_before": production_hash,
        "candidates": [],
    }
    try:
        for model in CANDIDATES:
            if model not in installed:
                evidence["candidates"].append(
                    {
                        "model": model,
                        "qualified": False,
                        "outcome": "NOT TESTED — MODEL NOT INSTALLED",
                    }
                )
                continue
            evidence["candidates"].append(qualify_one(model, temp_dir))
    finally:
        evidence["finished_at"] = iso()
        evidence["production_config_hash_after"] = hash_file(ROOT / "config.json")
        evidence["production_config_unchanged"] = (
            evidence["production_config_hash_after"] == production_hash
        )
        RESULT_PATH.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
    return 0 if evidence["production_config_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
