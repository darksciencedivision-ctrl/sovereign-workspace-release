"""Scheduled live-Ollama soak. Writes raw evidence; not part of offline pytest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from websockets.sync.client import connect


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "audit" / "v1_1_soak_evidence.json"

# v1.1 §10: leak detection must be checked against the labels actually used
# by turn_prompt(), not a hand-written list (same rule as debate/output_guard.py).
CONTROL_LABELS = (
    "TOPIC:",
    "CONTINUITY ANCHOR:",
    "RECENT TABLE TRANSCRIPT:",
    "OPERATOR NOTE:",
    "YOUR MOVE:",
    "YOUR RECENT ARGUMENTS:",
    "PRIVATE CONTROL",
    "PUBLIC CONTEXT",
)


def scan_control_leak(text: str) -> list[str]:
    lowered = text.lower()
    return [label for label in CONTROL_LABELS if label.lower() in lowered]


def iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_http(url: str, process: subprocess.Popen, timeout=30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"app exited early with {process.returncode}")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.2)
    raise TimeoutError("app did not become ready")


def process_memory(pid: int) -> int | None:
    command = ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def ollama_processes() -> list[dict]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | "
        "Select-Object Id,ProcessName,WorkingSet64 | ConvertTo-Json -Compress",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if not result.stdout.strip():
        return []
    parsed = json.loads(result.stdout)
    return parsed if isinstance(parsed, list) else [parsed]


def start_app(config_path: Path, port: int, stdout_path: Path, stderr_path: Path) -> tuple[subprocess.Popen, object, object]:
    env = os.environ.copy()
    env.update({"CONFIG_PATH": str(config_path), "PYTHONUTF8": "1"})
    out = stdout_path.open("w", encoding="utf-8")
    err = stderr_path.open("w", encoding="utf-8")
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=env, stdout=out, stderr=err, creationflags=flags)
    try:
        wait_http(f"http://127.0.0.1:{port}/api/models", proc)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        out.close()
        err.close()
        raise
    return proc, out, err


def stop_app(proc: subprocess.Popen, out, err) -> int:
    if proc.poll() is None:
        if os.name == "nt":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                proc.terminate()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
    out.close(); err.close()
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--models", nargs=2, metavar=("MODEL_A", "MODEL_B"))
    parser.add_argument(
        "--topic",
        default=None,
        help="Fix a single topic for the whole run (disables auto-rotation) -- used for the v1.1 §10 text acceptance run.",
    )
    args = parser.parse_args()
    duration = args.minutes * 60
    production_hash = hash_file(ROOT / "config.json")
    temp_dir = Path(tempfile.mkdtemp(prefix=".soak-", dir=ROOT / "tests"))
    config_path = temp_dir / "config.json"
    shutil.copy2(ROOT / "config.json", config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.models:
        installed = {
            item["name"]
            for item in httpx.get("http://127.0.0.1:11434/api/tags", timeout=20).json().get("models", [])
            if item.get("name")
        }
        missing = [model for model in args.models if model not in installed]
        if missing:
            raise RuntimeError(f"soak model is not installed: {', '.join(missing)}")
        for seat, model in zip(config["seats"][:2], args.models):
            seat["model"] = model
    port = free_port()
    config["port"] = port
    config["topic_rotate_turns"] = 0 if args.topic else 4
    config["insight_panel"] = False
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    base = f"http://127.0.0.1:{port}"
    evidence = {
        "started_at": iso(), "requested_duration_seconds": duration, "config_path": str(config_path),
        "production_config_hash_before": production_hash, "schedule": [], "events": [], "turns": [], "skipped_turns": [],
        "memory_samples": [], "dead_air_gaps_over_10s": [], "reasoning_tag_leaks": [], "errors": [],
        "control_text_leaks_in_tokens": [], "skipped_after_streaming": [], "diagnostic_events": [],
        "checks": {},
        "commands": [
            "python tests/live_soak.py --minutes "
            + str(args.minutes)
            + (f" --models {args.models[0]} {args.models[1]}" if args.models else "")
        ],
        "selected_models": [seat["model"] for seat in config["seats"][:2]],
    }
    proc = out = err = None
    ws = None
    try:
        proc, out, err = start_app(config_path, port, ROOT / "audit" / "soak_app.stdout.log", ROOT / "audit" / "soak_app.stderr.log")
        evidence["app_pid"] = proc.pid
        evidence["ollama_processes_at_start"] = ollama_processes()
        if args.topic:
            topic_response = httpx.post(f"{base}/api/topic", json={"text": args.topic}, timeout=10)
            evidence["schedule"].append(
                {"at": iso(), "action": "fixed_topic_set", "status": topic_response.status_code, "topic": args.topic}
            )
        ws = connect(f"ws://127.0.0.1:{port}/ws", open_timeout=5)
        monitor_started = time.monotonic()
        clock_origin = None
        last_memory = -999.0
        active: dict | None = None
        topic_count = 0
        disconnected = paused = resumed = manual_topic = swapped = invalids = False
        swap_seat = swap_old = swap_new = None
        swap_next_verified = False
        rotating_status_seen = False
        pause_started = None
        turn_started_during_pause = False
        interjected = interjection_consumed = False
        interjection_attempted = False
        retry_status_count = 0
        while clock_origin is None or time.monotonic() - clock_origin < duration:
            now = time.monotonic()
            if clock_origin is None and now - monitor_started > 900:
                raise TimeoutError("no successful public turn within 15-minute warmup")
            elapsed = 0.0 if clock_origin is None else now - clock_origin
            if elapsed - last_memory >= 300 or last_memory < 0:
                last_memory = elapsed
                try:
                    ollama_ps = httpx.get("http://127.0.0.1:11434/api/ps", timeout=5).json()
                except Exception as exc:
                    ollama_ps = {"error": str(exc)}
                evidence["memory_samples"].append({
                    "at": iso(),
                    "elapsed": elapsed,
                    "app_working_set_bytes": process_memory(proc.pid),
                    "ollama_processes": ollama_processes(),
                    "ollama_models": ollama_ps,
                })
            if elapsed >= 180 and not disconnected:
                ws.close(); evidence["schedule"].append({"at": iso(), "action": "websocket_disconnect"})
                time.sleep(2)
                ws = connect(f"ws://127.0.0.1:{port}/ws", open_timeout=5)
                evidence["schedule"].append({"at": iso(), "action": "websocket_reconnect"})
                disconnected = True
            if elapsed >= 300 and not paused:
                response = httpx.post(f"{base}/api/pause", timeout=5)
                evidence["schedule"].append({"at": iso(), "action": "pause", "status": response.status_code})
                paused = True; pause_started = elapsed
            if elapsed >= 330 and paused and not resumed:
                response = httpx.post(f"{base}/api/resume", timeout=5)
                evidence["schedule"].append({"at": iso(), "action": "resume", "status": response.status_code})
                resumed = True
            if elapsed >= 480 and active and not manual_topic:
                response = httpx.post(f"{base}/api/topic", json={"text": "Can robust systems distinguish interruption from failure?"}, timeout=5)
                evidence["schedule"].append({"at": iso(), "action": "manual_topic_during_generation", "status": response.status_code})
                manual_topic = True
            if elapsed >= 600 and active and not swapped:
                models = httpx.get(f"{base}/api/models", timeout=10).json()["models"]
                swap_seat = active["seat"]; swap_old = active.get("model")
                preferred = [seat["model"] for seat in config["seats"][:2] if seat["model"] != swap_old]
                swap_new = next(
                    (name for name in preferred if name in models),
                    next(name for name in models if name != swap_old),
                )
                response = httpx.post(f"{base}/api/seat_model", json={"seat": swap_seat, "model": swap_new}, timeout=20)
                evidence["schedule"].append({"at": iso(), "action": "model_swap_during_active_turn", "seat": swap_seat, "old": swap_old, "new": swap_new, "status": response.status_code})
                swapped = True
            if elapsed >= 720 and not invalids:
                isolated_before_invalid = hash_file(config_path)
                bad_seat = httpx.post(f"{base}/api/seat_model", json={"seat": "NOT_A_SEAT", "model": config["seats"][0]["model"]}, timeout=10)
                bad_model = httpx.post(f"{base}/api/seat_model", json={"seat": config["seats"][0]["name"], "model": "NOT_INSTALLED"}, timeout=10)
                evidence["schedule"].append({"at": iso(), "action": "invalid_requests", "invalid_seat_status": bad_seat.status_code, "invalid_model_status": bad_model.status_code})
                evidence["checks"]["invalid_requests_return_400"] = bad_seat.status_code == bad_model.status_code == 400
                evidence["checks"]["invalid_requests_no_state_change"] = hash_file(config_path) == isolated_before_invalid
                invalids = True
            if elapsed >= 840 and not interjected:
                interjection_attempted = True
                response = httpx.post(
                    f"{base}/api/interject",
                    json={"text": "Identify one assumption that would reverse your conclusion."},
                    timeout=5,
                )
                evidence["schedule"].append({"at": iso(), "action": "operator_interjection", "status": response.status_code})
                interjected = response.status_code == 200
            try:
                event = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            received = time.monotonic()
            slim = {
                key: event.get(key)
                for key in ("type", "seat", "turn", "move", "move_reason", "model", "text", "reason", "kind", "label")
                if key in event
            }
            slim.update({"at": iso(), "elapsed": 0.0 if clock_origin is None else received - clock_origin})
            if event["type"] != "token":
                evidence["events"].append(slim)
            if event["type"] == "diagnostic":
                evidence["diagnostic_events"].append(slim)
            if event["type"] == "topic":
                topic_count += 1
            elif event["type"] == "status" and event.get("text") == "rotating topic":
                rotating_status_seen = True
            elif event["type"] == "status" and "retrying empty public response" in event.get("text", ""):
                retry_status_count += 1
            elif event["type"] == "turn_start":
                if paused and not resumed:
                    turn_started_during_pause = True
                if swapped and event["seat"] == swap_seat and event.get("model") == swap_new:
                    swap_next_verified = True
                if event.get("interjection"):
                    interjection_consumed = True
                active = {"seat": event["seat"], "model": event.get("model"), "turn": event.get("turn"), "start": received, "first": None, "first_sentence": None, "last": None, "fragment_events": 0, "characters": 0, "max_fragment_gap": 0, "token_texts": []}
            elif event["type"] == "speaking" and active and event.get("seat") == active["seat"]:
                active["speaking_at"] = received
            elif event["type"] == "token" and active and event.get("seat") == active["seat"]:
                if active["first"] is None: active["first"] = received
                if active["last"] is not None:
                    gap = received - active["last"]
                    active["max_fragment_gap"] = max(active["max_fragment_gap"], gap)
                    if gap > 10: evidence["dead_air_gaps_over_10s"].append({"at": iso(), "seat": active["seat"], "gap_seconds": gap})
                active["last"] = received; active["fragment_events"] += 1; active["characters"] += len(event.get("text", ""))
                active["token_texts"].append(event.get("text", ""))
            elif event["type"] == "turn_end" and active and event.get("seat") == active["seat"]:
                active["finish"] = received
                active["ttft_seconds"] = (active["first"] - active["start"]) if active["first"] else None
                active["speaking_signal_before_first_token"] = (
                    active.get("speaking_at") is not None
                    and active["first"] is not None
                    and active["speaking_at"] <= active["first"]
                )
                generation_s = (active["last"] - active["first"]) if active["first"] and active["last"] else None
                active["fragment_events_per_second"] = active["fragment_events"] / generation_s if generation_s and generation_s > 0 else None
                active["fragment_rate_measurement"] = "WebSocket public-fragment events per second; not tokenizer-exact tokens"
                active["intentional_pacing_seconds"] = config.get("turn_delay_ms", 0) / 1000
                active["text"] = event.get("text", "")
                active["public_text_from_token_events"] = "".join(active.pop("token_texts", []))
                if re.search(r"</?think>|<analysis>", active["text"], re.I): evidence["reasoning_tag_leaks"].append({"turn": active["turn"], "seat": active["seat"]})
                token_leak_hits = scan_control_leak(active["public_text_from_token_events"])
                if token_leak_hits:
                    evidence["control_text_leaks_in_tokens"].append({"turn": active["turn"], "seat": active["seat"], "labels": token_leak_hits})
                evidence["turns"].append(active); active = None
                if event.get("text") and clock_origin is None:
                    clock_origin = received
                    last_memory = -999.0
                    evidence["first_successful_public_turn_at"] = iso()
            elif event["type"] == "turn_skipped":
                evidence["skipped_turns"].append(slim)
                if active and active.get("seat") == event.get("seat") and active.get("turn") == event.get("turn"):
                    streamed_chars = active.get("characters", 0)
                    if streamed_chars > 0:
                        evidence["skipped_after_streaming"].append(
                            {
                                "turn": event.get("turn"),
                                "seat": event.get("seat"),
                                "reason": event.get("reason"),
                                "characters_streamed_before_skip": streamed_chars,
                            }
                        )
            elif event["type"] == "turn_metrics":
                for turn in reversed(evidence["turns"]):
                    if turn["seat"] == event.get("seat") and turn["turn"] == event.get("turn"):
                        turn["backend_attempts"] = event.get("attempts", [])
                        turn["public_empty"] = event.get("public_empty")
                        break
        evidence["checks"].update({
            "websocket_disconnect_reconnect": disconnected,
            "pause_resume_performed": paused and resumed,
            "no_turn_start_during_pause": not turn_started_during_pause,
            "manual_topic_during_generation": manual_topic,
            "model_swap_during_active_turn": swapped,
            "swap_applied_on_same_seat_next_turn": swap_next_verified,
            "automatic_topic_rotation_observed": "not_applicable_fixed_topic_run" if args.topic else rotating_status_seen,
            # An intervention that was never scheduled is NOT a failed check.
            # true = exercised and passed; false = exercised and failed;
            # "not_run" = never exercised. Recording an unscheduled action as
            # false made every short run appear to fail two checks, and made
            # all(checks.values()) meaningless. Same convention as
            # automatic_topic_rotation_observed above. The interjection step
            # fires at elapsed >= 840 s, so any run shorter than that never
            # reaches it.
            "operator_interjection_accepted": interjected if interjection_attempted else "not_run",
            "operator_interjection_consumed": interjection_consumed if interjection_attempted else "not_run",
            "no_control_text_leak_in_token_events": not evidence["control_text_leaks_in_tokens"],
            "no_hidden_reasoning_leak": not evidence["reasoning_tag_leaks"],
        })
        evidence["actual_duration_after_first_success_seconds"] = time.monotonic() - clock_origin
        evidence["retry_status_count"] = retry_status_count
        evidence["topic_event_count"] = topic_count

        # §8.3: measure actual token usage against num_predict so the
        # decision to raise it (or not) is backed by a real measurement,
        # not a guess. Sourced from turn_metrics.attempts[], which carries
        # Ollama's own eval_count plus this stage's completion classification.
        completion_counts: dict[str, int] = {}
        eval_counts: list[int] = []
        continuations_applied = 0
        for turn in evidence["turns"]:
            for attempt in turn.get("backend_attempts", []):
                state_name = attempt.get("completion_state")
                if state_name:
                    completion_counts[state_name] = completion_counts.get(state_name, 0) + 1
                if attempt.get("continuation_applied"):
                    continuations_applied += 1
                if isinstance(attempt.get("eval_count"), int):
                    eval_counts.append(attempt["eval_count"])
        evidence["completion_summary"] = {
            "completion_state_counts": completion_counts,
            "continuations_applied": continuations_applied,
            "num_predict_configured": config.get("num_predict"),
            "eval_count_samples": eval_counts,
            "eval_count_max": max(eval_counts) if eval_counts else None,
            "eval_count_mean": (sum(eval_counts) / len(eval_counts)) if eval_counts else None,
            "attempts_at_or_above_num_predict": sum(
                1 for value in eval_counts if config.get("num_predict") and value >= config["num_predict"]
            ),
        }

        # --- Check accounting -------------------------------------------------
        # Do not use all(checks.values()): non-boolean sentinels ("not_run",
        # "not_applicable_fixed_topic_run") are truthy strings, and a false
        # recorded for an unscheduled action is not a failure. Report the
        # three states separately.
        boolean_checks = {
            name: value
            for name, value in evidence["checks"].items()
            if isinstance(value, bool)
        }
        evidence["checks_summary"] = {
            "applicable_checks_passed": sum(1 for value in boolean_checks.values() if value),
            "applicable_checks_failed": sorted(
                name for name, value in boolean_checks.items() if not value
            ),
            "checks_not_run": sorted(
                f"{name}={value}"
                for name, value in evidence["checks"].items()
                if not isinstance(value, bool)
            ),
        }

        # --- Turn quality -----------------------------------------------------
        # v1.1 targeted a 110-160 word contract and shipped a measured mean of
        # 188 (max 305) without recording it anywhere, and banned five literal
        # stock openings while 53% of turns opened with an unlisted variant.
        # Both are now measured every run so the contract is falsifiable.
        word_counts: list[int] = []
        contract_bands: dict[str, int] = {}
        agreement_openers: list[str] = []
        repetition_reframes = 0
        # Opening-move constraint (v1.1 closeout): the historical baseline is
        # Neo-only (8 of 8 observed turns), but the live fraction below spans
        # both seats -- seat-split reporting keeps a Neo-to-Neo comparison
        # possible; any all-seat number must be labelled as such.
        opening_violation_reasons: list[str] = []
        opening_violations_by_seat: dict[str, int] = {}
        scored_by_seat: dict[str, int] = {}
        for turn in evidence["turns"]:
            seat_name = turn.get("seat")
            for attempt in turn.get("backend_attempts", []):
                if isinstance(attempt.get("word_count"), int):
                    word_counts.append(attempt["word_count"])
                band = attempt.get("word_contract")
                if band:
                    contract_bands[band] = contract_bands.get(band, 0) + 1
                    scored_by_seat[seat_name] = scored_by_seat.get(seat_name, 0) + 1
                if attempt.get("agreement_opener"):
                    agreement_openers.append(attempt["agreement_opener"])
                reason = attempt.get("opening_violation")
                if reason:
                    opening_violation_reasons.append(reason)
                    opening_violations_by_seat[seat_name] = (
                        opening_violations_by_seat.get(seat_name, 0) + 1
                    )
        for event in evidence["events"]:
            if str(event.get("move_reason", "")).startswith("repeated_argument:"):
                repetition_reframes += 1
        within = contract_bands.get("within", 0)
        scored = sum(contract_bands.values())
        opening_violations = len(opening_violation_reasons)
        evidence["turn_quality"] = {
            "word_count_min": min(word_counts) if word_counts else None,
            "word_count_mean": (sum(word_counts) / len(word_counts)) if word_counts else None,
            "word_count_max": max(word_counts) if word_counts else None,
            "contract_bands": contract_bands,
            "within_contract_fraction": (within / scored) if scored else None,
            "turns_opening_with_agreement": len(agreement_openers),
            "agreement_openers_observed": sorted(set(agreement_openers)),
            "repetition_reframes_fired": repetition_reframes,
            "opening_violations": opening_violations,
            "opening_violation_fraction": (opening_violations / scored) if scored else None,
            "opening_violation_reasons": sorted(set(opening_violation_reasons)),
            "opening_violations_by_seat": opening_violations_by_seat,
            "opening_violation_fraction_by_seat": {
                seat_name: (opening_violations_by_seat.get(seat_name, 0) / seat_scored)
                for seat_name, seat_scored in scored_by_seat.items()
                if seat_scored
            },
            "v1_1_baseline": {
                "word_count_mean": 188,
                "word_count_max": 305,
                "within_contract_fraction": 0.25,
                "turns_opening_with_agreement": 31,
                "turns_scored": 59,
                "repetition_reframes_fired": 0,
                "neo_opening_violations": "8 of 8 observed",
            },
        }

        # --- Turn accounting -------------------------------------------------
        # The `turns` array records every turn that produced a turn_end event,
        # INCLUDING skipped turns, which carry empty public text. Reporting
        # len(turns) as "completed turns" over-reports by the number of skips.
        # That exact error reached both the v1 closeout ("107 recorded / 105
        # non-empty") and the v1.1 acceptance report ("63 completed"), so these
        # quantities are now computed and published separately. A completed
        # turn requires non-empty public text, not mere membership in `turns`.
        completed_turns = [
            turn for turn in evidence["turns"] if (turn.get("text") or "").strip()
        ]
        evidence["turn_counts"] = {
            "turn_records": len(evidence["turns"]),
            "completed_turns": len(completed_turns),
            "skipped_turns": len(evidence["skipped_turns"]),
            "attempted_turns": sum(
                1 for event in evidence["events"] if event.get("type") == "turn_start"
            ),
            "definition": (
                "completed_turns requires non-empty public text and a completion "
                "classification. turn_records == completed_turns + skipped_turns. "
                "attempted_turns counts turn_start events and includes any turn "
                "still in flight at shutdown; use it only for per-attempt rates "
                "such as move-selection distribution, never as a completed count."
            ),
        }
        ws.close(); ws = None
        evidence["schedule"].append({"at": iso(), "action": "clean_shutdown"})
        evidence["app_exit_code"] = stop_app(proc, out, err); proc = out = err = None
        app_stdout = (ROOT / "audit" / "soak_app.stdout.log").read_text(encoding="utf-8", errors="replace")
        app_stderr = (ROOT / "audit" / "soak_app.stderr.log").read_text(encoding="utf-8", errors="replace")
        evidence["checks"]["primary_shutdown_traceback_free"] = "traceback" not in (app_stdout + app_stderr).lower()
        evidence["checks"]["primary_shutdown_stderr_empty"] = not app_stderr.strip()

        # Restart against the same isolated config to verify persisted seat selection.
        restart_port = port
        proc, out, err = start_app(config_path, restart_port, ROOT / "audit" / "soak_restart.stdout.log", ROOT / "audit" / "soak_restart.stderr.log")
        ws = connect(f"ws://127.0.0.1:{restart_port}/ws", open_timeout=10)
        snapshot = json.loads(ws.recv())
        persisted_model = next((seat["model"] for seat in snapshot["seats"] if seat["name"] == swap_seat), None)
        evidence["checks"]["model_swap_survives_restart"] = persisted_model == swap_new
        ws.close(); ws = None
        evidence["restart_exit_code"] = stop_app(proc, out, err); proc = out = err = None
        restart_stdout = (ROOT / "audit" / "soak_restart.stdout.log").read_text(encoding="utf-8", errors="replace")
        restart_stderr = (ROOT / "audit" / "soak_restart.stderr.log").read_text(encoding="utf-8", errors="replace")
        evidence["checks"]["restart_shutdown_traceback_free"] = "traceback" not in (restart_stdout + restart_stderr).lower()
    except Exception as exc:
        evidence["errors"].append({"at": iso(), "error": repr(exc)})
        return_code = 1
    else:
        return_code = 0
    finally:
        if ws is not None:
            try: ws.close()
            except Exception: pass
        if proc is not None:
            evidence["forced_cleanup_exit_code"] = stop_app(proc, out, err)
        evidence["finished_at"] = iso()
        evidence["production_config_hash_after"] = hash_file(ROOT / "config.json")
        evidence["checks"]["production_config_unchanged"] = evidence["production_config_hash_after"] == production_hash
        EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.rmtree(temp_dir, ignore_errors=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
