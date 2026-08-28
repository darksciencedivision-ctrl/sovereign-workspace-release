from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from distillery.common import ContractError, sha256_value, utc_now, write_new_json
from source_admission import assert_admitted, assert_seed_admitted


LABEL_ORIGINS = {"live_operator_mark", "import_time_classification", "implicit_runtime_signal", "synthetic_fixture"}


class TraceStore:
    """Append-only operational telemetry; collection is independent of admission."""

    def __init__(self, event_log: str | Path | None = None) -> None:
        self.event_log = Path(event_log) if event_log else None
        self._sessions: dict[str, dict] = {}
        self._events: list[dict] = []
        if self.event_log and self.event_log.exists():
            for line in self.event_log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._apply(json.loads(line), persist=False)

    def start(self, session_id: str, *, harness: str, provider: str, model_id: str, revision: str, source_admission_class: str = "UNKNOWN", fixture: bool = False, route: str | None = None, recorded_at: str | None = None) -> None:
        self._apply({"event": "start", "session_id": session_id, "harness": harness, "provider": provider, "model_id": model_id, "revision": revision, "source_admission_class": source_admission_class, "fixture": fixture, "route": route, "recorded_at": recorded_at or utc_now()})

    def turn(self, session_id: str, turn_id: str, *, content: str | None = None, content_hash: str | None = None, tool_status: str = "none", recovery: bool = False, superseded: bool = False, measured: dict | None = None, harness: str | None = None, provider: str | None = None, model_id: str | None = None, revision: str | None = None, recorded_at: str | None = None) -> None:
        if content is None and content_hash is None:
            raise ContractError("turn requires content or a privacy-preserving content hash")
        session = self._required(session_id)
        self._apply({"event": "turn", "session_id": session_id, "turn_id": turn_id, "content": content, "content_hash": content_hash or sha256_value(content), "tool_status": tool_status, "recovery": recovery, "superseded": superseded, "measured": measured or {}, "provenance": {"harness": harness or session["harness"], "provider": provider or session["provider"], "model_id": model_id or session["model_id"], "revision": revision or session["revision"]}, "recorded_at": recorded_at or utc_now()})

    def success(self, session_id: str, *, recorded_at: str | None = None) -> None:
        self._finish(session_id, "success", recorded_at=recorded_at)

    def fail(self, session_id: str, *, recorded_at: str | None = None) -> None:
        self._finish(session_id, "fail", recorded_at=recorded_at)

    def infer_clean_exit(self, session_id: str, *, retried_or_edited: bool, abandoned: bool) -> None:
        if retried_or_edited or abandoned:
            raise ContractError("implicit success requires clean, unedited, non-abandoned exit")
        self._finish(session_id, "implicit_success")

    def explicit_label(self, session_id: str, label: str, *, label_origin: str) -> None:
        if label not in {"success", "fail"}:
            raise ContractError("explicit label must be success or fail")
        if label_origin not in LABEL_ORIGINS:
            raise ContractError(f"label_origin must be one of {sorted(LABEL_ORIGINS)}")
        self._apply({"event": "label", "session_id": session_id, "label": label, "path": f"/{label}", "label_origin": label_origin, "recorded_at": utc_now()})

    def mark_fixture(self, session_id: str, *, persist: bool = True) -> None:
        self._apply({"event": "fixture", "session_id": session_id, "fixture": True, "recorded_at": utc_now()}, persist=persist)

    def implicit_signal(self, session_id: str, polarity: str, kind: str, *, evidence_hash: str) -> None:
        if polarity not in {"positive", "negative"} or not kind or not evidence_hash:
            raise ContractError("implicit signal requires polarity, kind, and evidence hash")
        self._apply({"event": "signal", "session_id": session_id, "polarity": polarity, "kind": kind, "evidence_hash": evidence_hash, "recorded_at": utc_now()})

    def get(self, session_id: str) -> dict:
        try:
            return deepcopy(self._sessions[session_id])
        except KeyError as exc:
            raise ContractError(f"unknown session: {session_id}") from exc

    def has(self, session_id: str) -> bool:
        return session_id in self._sessions

    def has_turn(self, session_id: str, turn_id: str) -> bool:
        return any(turn["turn_id"] == turn_id for turn in self._required(session_id)["turns"])

    def query_outcome(self, outcome: str) -> list[dict]:
        return [deepcopy(item) for item in self._sessions.values() if item["outcome"] == outcome]

    def summary(self) -> dict:
        outcomes: dict[str, int] = {}
        providers: dict[str, int] = {}
        models: dict[str, int] = {}
        for session in self._sessions.values():
            outcome = session["outcome"] or "open"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            providers[session["provider"]] = providers.get(session["provider"], 0) + 1
            models[session["model_id"]] = models.get(session["model_id"], 0) + 1
        return {"session_count": len(self._sessions), "outcomes": outcomes, "providers": providers, "models": models}

    def sessions(self) -> list[dict]:
        return deepcopy(list(self._sessions.values()))

    def event_history(self) -> list[dict]:
        return deepcopy(self._events)

    def dashboard(self) -> dict:
        sessions = list(self._sessions.values())
        finished = [item for item in sessions if item["outcome"] is not None]
        labels = [item for item in finished if item["explicit_label"] is not None]
        signals = [signal for item in sessions for signal in item["signals"]]
        rejections = [rejection for item in sessions for rejection in item["rejections"]]
        rejection_counts: dict[str, int] = {}
        for rejection in rejections:
            key = f"{rejection['channel']}:{rejection['reason']}"
            rejection_counts[key] = rejection_counts.get(key, 0) + 1
        return {
            "gold_accrual_candidates": sum(bool(item["turns"]) and item["outcome"] in {"success", "implicit_success"} for item in sessions),
            "explicit_label_compliance": {"labeled": len(labels), "finished": len(finished), "rate": len(labels) / len(finished) if finished else 0.0},
            "implicit_signals": {"positive": sum(item["polarity"] == "positive" for item in signals), "negative": sum(item["polarity"] == "negative" for item in signals)},
            "channel_rejections": rejection_counts,
            "session_count": len(sessions),
            "turn_count": sum(len(item["turns"]) for item in sessions),
        }

    def alerts(self) -> list[dict]:
        alerts = []
        for session in self._sessions.values():
            if not session["turns"]:
                alerts.append({"code": "NO_TRACE", "session_id": session["session_id"], "fixture": session["fixture"]})
            if session["turns"] and session["outcome"] is not None and session["explicit_label"] is None:
                alerts.append({"code": "NO_LABEL", "session_id": session["session_id"], "fixture": session["fixture"]})
        return alerts

    def hashed_event_manifest(self) -> dict:
        events: list[dict] = []
        for session in sorted(self._sessions.values(), key=lambda item: item["session_id"]):
            base = {
                "session_id_hash": sha256_value(session["session_id"]),
                "harness": session["harness"],
                "route": session["route"],
                "teacher_provider_identifier": f"{session['provider']}:{session['model_id']}:{session['revision']}",
                "source_admission_class": session["source_admission_class"],
                "content_payload_present": False,
                "fixture": session["fixture"],
            }

            def append_event(*, timestamp: str, signal_type: str, turn_id: str | None = None, outcome: str | None = None, label_origin: str | None = None, validator_result: str = "NOT_APPLICABLE", recovery_parent_hash: str | None = None) -> None:
                normalized_outcome = "failure" if outcome == "fail" else outcome
                body = {
                    **base,
                    "turn_id_hash": sha256_value(turn_id),
                    "timestamp": timestamp,
                    "outcome": normalized_outcome,
                    "signal_type": signal_type,
                    "label_origin": label_origin,
                    "validator_result": validator_result,
                    "recovery_parent_hash": recovery_parent_hash,
                }
                events.append({"event_id_hash": sha256_value(body), **body})

            append_event(timestamp=session["started_at"], signal_type="session_start")
            previous_turn_id: str | None = None
            for turn in session["turns"]:
                append_event(
                    timestamp=turn["recorded_at"],
                    signal_type="recovery_turn" if turn["recovery"] else "turn",
                    turn_id=turn["turn_id"],
                    outcome=session["outcome"],
                    label_origin=session["explicit_label"]["label_origin"] if session["explicit_label"] else None,
                    validator_result=turn["tool_status"],
                    recovery_parent_hash=sha256_value(previous_turn_id) if turn["recovery"] and previous_turn_id else None,
                )
                previous_turn_id = turn["turn_id"]
            if session["outcome"] is not None:
                append_event(timestamp=session["finished_at"], signal_type="outcome", outcome=session["outcome"], label_origin=session["explicit_label"]["label_origin"] if session["explicit_label"] else None)
            if session["explicit_label"]:
                append_event(timestamp=session["explicit_label"]["recorded_at"], signal_type="explicit", outcome=session["explicit_label"]["label"], label_origin=session["explicit_label"]["label_origin"], validator_result="operator_mark_recorded")
            for signal in session["signals"]:
                append_event(timestamp=signal["recorded_at"], signal_type=f"implicit_signal:{signal['polarity']}:{signal['kind']}", outcome=session["outcome"], label_origin="implicit_runtime_signal", validator_result="RECORDED")
            for rejection in session["rejections"]:
                append_event(timestamp=rejection["recorded_at"], signal_type=f"rejection:{rejection['channel']}", outcome=session["outcome"], label_origin=session["explicit_label"]["label_origin"] if session["explicit_label"] else None, validator_result=rejection["reason"])
        body = {"schema_version": "1.2", "content_payload_present": False, "events": events}
        return {**body, "manifest_hash": sha256_value(body)}

    def write_hashed_event_manifest(self, path: str | Path) -> Path:
        target = Path(path)
        write_new_json(target, self.hashed_event_manifest())
        return target

    def admit_for_corpus(self, session_id: str, use_class: str, *, internal_use_authorized: bool = False) -> dict:
        try:
            assert_admitted(use_class, internal_use_authorized=internal_use_authorized)
        except ContractError:
            self._record_rejection(session_id, "training_shard", use_class)
            raise
        self._required(session_id)["source_admission_class"] = use_class
        return self.get(session_id)

    def admit_as_seed(self, session_id: str, use_class: str, *, internal_use_authorized: bool = False) -> dict:
        try:
            assert_seed_admitted(use_class, internal_use_authorized=internal_use_authorized)
        except ContractError:
            self._record_rejection(session_id, "synthetic_seed", use_class)
            raise
        self._required(session_id)["source_admission_class"] = use_class
        return self.get(session_id)

    def _finish(self, session_id: str, outcome: str, *, recorded_at: str | None = None) -> None:
        self._apply({"event": "outcome", "session_id": session_id, "outcome": outcome, "recorded_at": recorded_at or utc_now()})

    def _record_rejection(self, session_id: str, channel: str, reason: str) -> None:
        self._apply({"event": "rejection", "session_id": session_id, "channel": channel, "reason": reason, "recorded_at": utc_now()})

    def _apply(self, event: dict, *, persist: bool = True) -> None:
        self._events.append(deepcopy(event))
        kind = event["event"]
        session_id = event["session_id"]
        if kind == "start":
            if not all(event.get(name) for name in ("session_id", "harness", "provider", "model_id", "revision")) or session_id in self._sessions:
                raise ContractError("session identity/provenance must be complete and unique")
            self._sessions[session_id] = {name: event[name] for name in ("session_id", "harness", "provider", "model_id", "revision")}
            self._sessions[session_id].update({"turns": [], "outcome": None, "explicit_label": None, "signals": [], "rejections": [], "started_at": event["recorded_at"], "source_admission_class": event.get("source_admission_class", "UNKNOWN"), "fixture": bool(event.get("fixture", False)), "route": event.get("route")})
        elif kind == "turn":
            session = self._required(session_id)
            if any(turn["turn_id"] == event["turn_id"] for turn in session["turns"]):
                raise ContractError("turn_id must be unique within a session")
            provenance = event.get("provenance") or {name: session[name] for name in ("harness", "provider", "model_id", "revision")}
            session["turns"].append({**{key: event[key] for key in ("turn_id", "content", "content_hash", "tool_status", "recovery", "superseded", "measured", "recorded_at")}, "provenance": provenance})
        elif kind == "outcome":
            session = self._required(session_id)
            if session["outcome"] is not None:
                raise ContractError("session outcome is immutable")
            session["outcome"] = event["outcome"]
            session["finished_at"] = event["recorded_at"]
        elif kind == "label":
            session = self._required(session_id)
            if session["explicit_label"] is not None:
                raise ContractError("explicit label is immutable")
            session["explicit_label"] = {"label": event["label"], "path": event["path"], "label_origin": event.get("label_origin", "import_time_classification"), "recorded_at": event["recorded_at"]}
        elif kind == "signal":
            self._required(session_id)["signals"].append({key: event[key] for key in ("polarity", "kind", "evidence_hash", "recorded_at")})
        elif kind == "rejection":
            self._required(session_id)["rejections"].append({key: event[key] for key in ("channel", "reason", "recorded_at")})
        elif kind == "fixture":
            self._required(session_id)["fixture"] = bool(event["fixture"])
        else:
            raise ContractError(f"unknown telemetry event: {kind}")
        if persist and self.event_log:
            self.event_log.parent.mkdir(parents=True, exist_ok=True)
            with self.event_log.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")

    def _required(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            raise ContractError(f"unknown session: {session_id}")
        return self._sessions[session_id]


def run_g0_probes() -> dict:
    store = TraceStore()
    store.start("success", harness="local", provider="eligible.example", model_id="teacher", revision="r1", fixture=True)
    store.turn("success", "s1", content="done")
    store.success("success")
    store.explicit_label("success", "success", label_origin="synthetic_fixture")
    store.start("fail", harness="local", provider="eligible.example", model_id="teacher", revision="r1", fixture=True)
    store.turn("fail", "f1", content="failed", tool_status="failed")
    store.fail("fail")
    store.explicit_label("fail", "fail", label_origin="synthetic_fixture")
    store.start("recovery", harness="local", provider="eligible.example", model_id="teacher", revision="r1", fixture=True)
    store.turn("recovery", "r1", content="tool error", tool_status="failed")
    store.turn("recovery", "r2", content="diagnosed", recovery=True)
    store.turn("recovery", "r3", content="fixed", tool_status="passed", recovery=True)
    store.success("recovery")
    store.explicit_label("recovery", "success", label_origin="synthetic_fixture")
    store.start("unknown", harness="local", provider="unknown.example", model_id="mystery", revision="r0", fixture=True)
    store.turn("unknown", "u1", content="observable")
    store.success("unknown")
    store.explicit_label("unknown", "success", label_origin="synthetic_fixture")
    corpus_rejected = seed_rejected = False
    try:
        store.admit_for_corpus("unknown", "UNKNOWN")
    except ContractError:
        corpus_rejected = True
    try:
        store.admit_as_seed("unknown", "UNKNOWN")
    except ContractError:
        seed_rejected = True
    recovery = store.get("recovery")
    assertions = {
        "G0-A": store.get("success")["outcome"] == "success",
        "G0-B": len(store.query_outcome("fail")) == 1,
        "G0-C": recovery["outcome"] == "success" and any(t["tool_status"] == "failed" for t in recovery["turns"]) and any(t["recovery"] for t in recovery["turns"]),
        "G0-D": corpus_rejected and seed_rejected and store.get("unknown")["provider"] == "unknown.example",
    }
    return {"passed": all(assertions.values()), "assertions": assertions}
