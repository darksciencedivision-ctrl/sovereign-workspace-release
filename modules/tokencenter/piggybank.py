from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
DATA_ROOT = APP_ROOT / "data"
DB_PATH = DATA_ROOT / "piggybank.sqlite"
REFRESH_SECONDS = 300
LOOKBACK_DAYS = 45


@dataclass(frozen=True)
class UsageEvent:
    event_id: str
    timestamp: str
    provider: str
    model: str
    source: str
    locality: str
    confidence: str
    total_tokens: int
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None


@dataclass
class ProviderStatus:
    provider: str
    collector: str
    confidence: str
    coverage: str
    health: str
    detail: str
    events: int = 0
    models: list[str] | None = None
    latest_event: str | None = None


def _event_id(*parts: Any) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            if value > 10_000_000_000:
                value /= 1000
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_day(value: str) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "unknown"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().date().isoformat()


def _recent_file(path: Path, cutoff: datetime) -> bool:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= cutoff
    except OSError:
        return False


def _iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(value, dict):
                    yield line_no, value
    except OSError:
        return


def collect_codex(home: Path, cutoff: datetime) -> tuple[list[UsageEvent], ProviderStatus]:
    root = home / ".codex" / "sessions"
    events: list[UsageEvent] = []
    models: set[str] = set()
    latest: str | None = None
    if root.exists():
        for path_text in glob.iglob(str(root / "**" / "*.jsonl"), recursive=True):
            path = Path(path_text)
            if not _recent_file(path, cutoff):
                continue
            current_model = "unknown-codex-model"
            for line_no, item in _iter_jsonl(path):
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                if item.get("type") == "turn_context" and payload.get("model"):
                    current_model = str(payload["model"])
                    models.add(current_model)
                    continue
                if item.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                usage = info.get("last_token_usage")
                if not isinstance(usage, dict):
                    continue
                total = int(usage.get("total_tokens") or 0)
                if total <= 0:
                    continue
                ts = str(item.get("timestamp") or "")
                parsed = _parse_timestamp(ts)
                if parsed is None or parsed < cutoff:
                    continue
                input_total = int(usage.get("input_tokens") or 0)
                cache_read = int(usage.get("cached_input_tokens") or 0)
                cache_write = int(usage.get("cache_write_input_tokens") or 0)
                events.append(
                    UsageEvent(
                        event_id=_event_id("codex", path, line_no),
                        timestamp=parsed.isoformat(),
                        provider="OpenAI / Codex",
                        model=current_model,
                        source="Codex response metadata",
                        locality="hosted",
                        confidence="VERIFIED",
                        total_tokens=total,
                        input_tokens=max(0, input_total - cache_read - cache_write),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cache_read_tokens=cache_read,
                        cache_write_tokens=cache_write,
                        reasoning_tokens=int(usage.get("reasoning_output_tokens") or 0),
                    )
                )
                latest = max(latest or ts, ts)
    status = ProviderStatus(
        provider="OpenAI / Codex",
        collector="Codex local session ledger",
        confidence="VERIFIED" if events else "UNKNOWN",
        coverage="COMPLETE_FOR_LOCAL_CODEX_SESSIONS" if events else "NONE_OBSERVED",
        health="HEALTHY" if root.exists() else "UNKNOWN",
        detail="Counts provider-returned per-response token totals from local Codex sessions.",
        events=len(events),
        models=sorted(models),
        latest_event=latest,
    )
    return events, status


def _claude_total(usage: dict[str, Any]) -> int:
    return sum(
        int(usage.get(key) or 0)
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        )
    )


def collect_claude(home: Path, cutoff: datetime) -> tuple[list[UsageEvent], ProviderStatus]:
    root = home / ".claude" / "projects"
    by_message: dict[str, UsageEvent] = {}
    models: set[str] = set()
    latest: str | None = None
    if root.exists():
        for path_text in glob.iglob(str(root / "**" / "*.jsonl"), recursive=True):
            path = Path(path_text)
            if not _recent_file(path, cutoff):
                continue
            for line_no, item in _iter_jsonl(path):
                if item.get("type") != "assistant":
                    continue
                message = item.get("message")
                if not isinstance(message, dict):
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                total = _claude_total(usage)
                if total <= 0:
                    continue
                ts = str(item.get("timestamp") or "")
                parsed = _parse_timestamp(ts)
                if parsed is None or parsed < cutoff:
                    continue
                model = str(message.get("model") or "unknown-claude-model")
                models.add(model)
                message_id = str(message.get("id") or item.get("requestId") or f"{path}:{line_no}")
                record = UsageEvent(
                    event_id=_event_id("claude", message_id),
                    timestamp=parsed.isoformat(),
                    provider="Anthropic / Claude",
                    model=model,
                    source="Claude response metadata",
                    locality="hosted",
                    confidence="VERIFIED",
                    total_tokens=total,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                    cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                )
                previous = by_message.get(message_id)
                if previous is None or record.total_tokens > previous.total_tokens:
                    by_message[message_id] = record
                latest = max(latest or ts, ts)
    events = list(by_message.values())
    status = ProviderStatus(
        provider="Anthropic / Claude",
        collector="Claude local session ledger",
        confidence="VERIFIED" if events else "UNKNOWN",
        coverage="COMPLETE_FOR_LOCAL_CLAUDE_CODE_SESSIONS" if events else "NONE_OBSERVED",
        health="HEALTHY" if root.exists() else "UNKNOWN",
        detail="Deduplicates Claude message IDs and counts input, cache, and output usage metadata.",
        events=len(events),
        models=sorted(models),
        latest_event=latest,
    )
    return events, status


def _provider_label(provider_id: str) -> tuple[str, str]:
    key = provider_id.strip().lower()
    labels = {
        "opencode": ("OpenCode Zen", "hosted"),
        "openai": ("OpenAI", "hosted"),
        "anthropic": ("Anthropic", "hosted"),
        "google": ("Google", "hosted"),
        "gemini": ("Google / Gemini", "hosted"),
        "xai": ("xAI / Grok", "hosted"),
        "grok": ("xAI / Grok", "hosted"),
        "deepseek": ("DeepSeek", "hosted"),
        "qwen": ("Alibaba / Qwen", "hosted"),
        "kimi": ("Moonshot / Kimi", "hosted"),
        "ollama": ("Ollama", "local"),
        "lmstudio": ("LM Studio", "local"),
        "lm-studio": ("LM Studio", "local"),
        "vllm": ("vLLM", "local"),
    }
    return labels.get(key, (provider_id or "Unknown provider", "unknown"))


def collect_opencode(home: Path, cutoff: datetime) -> tuple[list[UsageEvent], list[ProviderStatus]]:
    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    events: list[UsageEvent] = []
    failure: str | None = None
    if db_path.exists():
        try:
            uri = db_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=2)
            try:
                rows = connection.execute(
                    "SELECT id, time_created, data FROM message WHERE time_created >= ? ORDER BY time_created",
                    (int(cutoff.timestamp() * 1000),),
                )
                for message_id, created, raw in rows:
                    try:
                        message = json.loads(raw)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    tokens = message.get("tokens")
                    if not isinstance(tokens, dict):
                        continue
                    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
                    total = int(tokens.get("total") or 0)
                    if total <= 0:
                        total = sum(
                            int(value or 0)
                            for value in (
                                tokens.get("input"),
                                tokens.get("output"),
                                tokens.get("reasoning"),
                                cache.get("read"),
                                cache.get("write"),
                            )
                        )
                    if total <= 0:
                        continue
                    provider_id = str(message.get("providerID") or "opencode")
                    provider, locality = _provider_label(provider_id)
                    stamp = (message.get("time") or {}).get("created") if isinstance(message.get("time"), dict) else created
                    parsed = _parse_timestamp(stamp)
                    if parsed is None or parsed < cutoff:
                        continue
                    cost = message.get("cost")
                    events.append(
                        UsageEvent(
                            event_id=_event_id("opencode", message_id),
                            timestamp=parsed.isoformat(),
                            provider=provider,
                            model=str(message.get("modelID") or "unknown-opencode-model"),
                            source="OpenCode message ledger",
                            locality=locality,
                            confidence="VERIFIED",
                            total_tokens=total,
                            input_tokens=int(tokens.get("input") or 0),
                            output_tokens=int(tokens.get("output") or 0),
                            cache_read_tokens=int(cache.get("read") or 0),
                            cache_write_tokens=int(cache.get("write") or 0),
                            reasoning_tokens=int(tokens.get("reasoning") or 0),
                            cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
                        )
                    )
            finally:
                connection.close()
        except (OSError, sqlite3.Error) as exc:
            failure = type(exc).__name__
    grouped: dict[str, list[UsageEvent]] = defaultdict(list)
    for event in events:
        grouped[event.provider].append(event)
    statuses: list[ProviderStatus] = []
    if grouped:
        for provider, rows in sorted(grouped.items()):
            statuses.append(
                ProviderStatus(
                    provider=provider,
                    collector="OpenCode SQLite ledger",
                    confidence="VERIFIED",
                    coverage="COMPLETE_FOR_OPENCODE_MESSAGES",
                    health="HEALTHY",
                    detail="Counts per-message token metadata recorded by OpenCode.",
                    events=len(rows),
                    models=sorted({row.model for row in rows}),
                    latest_event=max(row.timestamp for row in rows),
                )
            )
    else:
        statuses.append(
            ProviderStatus(
                provider="OpenCode",
                collector="OpenCode SQLite ledger",
                confidence="UNKNOWN",
                coverage="NONE_OBSERVED",
                health="WARNING" if failure else ("HEALTHY" if db_path.exists() else "UNKNOWN"),
                detail="Ledger could not be read." if failure else "No numeric assistant usage was recorded in this range.",
            )
        )
    return events, statuses


_LM_DATE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
_LM_MODEL = re.compile(r"loading model '([^']+)'", re.IGNORECASE)
_LM_PROMPT = re.compile(r"task\s+(\d+).*prompt eval time\s*=.*?/\s*(\d+) tokens", re.IGNORECASE)
_LM_OUTPUT = re.compile(r"task\s+(\d+).*?\beval time\s*=.*?/\s*(\d+) tokens", re.IGNORECASE)


def collect_lmstudio(home: Path, cutoff: datetime) -> tuple[list[UsageEvent], ProviderStatus]:
    root = home / ".lmstudio" / "server-logs"
    events: list[UsageEvent] = []
    models: set[str] = set()
    latest: str | None = None
    if root.exists():
        for path_text in glob.iglob(str(root / "**" / "*.log"), recursive=True):
            path = Path(path_text)
            if not _recent_file(path, cutoff):
                continue
            current_time: datetime | None = None
            current_model = "unknown-local-model"
            pending: dict[str, tuple[int, datetime, str, int, int]] = {}
            try:
                handle = path.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                for line_no, line in enumerate(handle, 1):
                    date_match = _LM_DATE.match(line)
                    if date_match:
                        try:
                            current_time = datetime.strptime(date_match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
                        except ValueError:
                            current_time = None
                    model_match = _LM_MODEL.search(line)
                    if model_match:
                        current_model = Path(model_match.group(1)).name
                        models.add(current_model)
                    prompt_match = _LM_PROMPT.search(line)
                    if prompt_match and current_time and current_time >= cutoff:
                        task = prompt_match.group(1)
                        pending[task] = (line_no, current_time, current_model, int(prompt_match.group(2)), 0)
                        continue
                    output_match = _LM_OUTPUT.search(line)
                    if output_match:
                        task = output_match.group(1)
                        if task in pending:
                            first_line, stamp, model, prompt_tokens, _ = pending[task]
                            pending[task] = (first_line, stamp, model, prompt_tokens, int(output_match.group(2)))
            for task, (line_no, stamp, model, prompt_tokens, output_tokens) in pending.items():
                total = prompt_tokens + output_tokens
                if total <= 0:
                    continue
                events.append(
                    UsageEvent(
                        event_id=_event_id("lmstudio", path, line_no, task),
                        timestamp=stamp.astimezone(timezone.utc).isoformat(),
                        provider="LM Studio",
                        model=model,
                        source="LM Studio server timing log",
                        locality="local",
                        confidence="VERIFIED",
                        total_tokens=total,
                        input_tokens=prompt_tokens,
                        output_tokens=output_tokens,
                    )
                )
                latest = max(latest or events[-1].timestamp, events[-1].timestamp)
    status = ProviderStatus(
        provider="LM Studio",
        collector="LM Studio server timing logs",
        confidence="VERIFIED" if events else "UNKNOWN",
        coverage="COMPLETE_FOR_RETAINED_SERVER_LOGS" if events else "NONE_OBSERVED",
        health="HEALTHY" if root.exists() else "UNKNOWN",
        detail="Counts prompt-evaluation and generation tokens retained in local server logs.",
        events=len(events),
        models=sorted(models),
        latest_event=latest,
    )
    return events, status


def _extract_grok_usage(error_text: Any) -> dict[str, Any] | None:
    if not isinstance(error_text, str) or '"promptUsage"' not in error_text:
        return None
    start = error_text.find("{")
    if start < 0:
        return None
    try:
        value = json.loads(error_text[start:])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    usage = value.get("promptUsage")
    return usage if isinstance(usage, dict) else None


def collect_grok(home: Path, cutoff: datetime) -> tuple[list[UsageEvent], ProviderStatus]:
    path = home / ".grok" / "logs" / "unified.jsonl"
    by_session_model: dict[tuple[str, str], UsageEvent] = {}
    if path.exists() and _recent_file(path, cutoff):
        for line_no, item in _iter_jsonl(path):
            ctx = item.get("ctx")
            if not isinstance(ctx, dict):
                continue
            usage = _extract_grok_usage(ctx.get("error"))
            if usage is None:
                continue
            ts = str(item.get("ts") or "")
            parsed = _parse_timestamp(ts)
            if parsed is None or parsed < cutoff:
                continue
            model_usage = usage.get("modelUsage")
            if not isinstance(model_usage, dict):
                continue
            session_id = str(item.get("sid") or f"line-{line_no}")
            for model, values in model_usage.items():
                if not isinstance(values, dict):
                    continue
                total = int(values.get("totalTokens") or 0)
                if total <= 0:
                    continue
                key = (session_id, str(model))
                record = UsageEvent(
                    event_id=_event_id("grok", session_id, model),
                    timestamp=parsed.isoformat(),
                    provider="xAI / Grok",
                    model=str(model),
                    source="Grok provider error usage metadata",
                    locality="hosted",
                    confidence="VERIFIED",
                    total_tokens=total,
                    input_tokens=max(0, int(values.get("inputTokens") or 0) - int(values.get("cachedReadTokens") or 0)),
                    output_tokens=int(values.get("outputTokens") or 0),
                    cache_read_tokens=int(values.get("cachedReadTokens") or 0),
                    cache_write_tokens=int(values.get("cacheCreationTokens") or 0),
                    reasoning_tokens=int(values.get("reasoningTokens") or 0),
                )
                previous = by_session_model.get(key)
                if previous is None or record.total_tokens > previous.total_tokens:
                    by_session_model[key] = record
    events = list(by_session_model.values())
    status = ProviderStatus(
        provider="xAI / Grok",
        collector="Grok local diagnostic log",
        confidence="VERIFIED" if events else "UNKNOWN",
        coverage="PARTIAL",
        health="HEALTHY" if path.exists() else "UNKNOWN",
        detail="Numeric usage is recorded only when Grok includes promptUsage metadata; successful calls without it remain unknown.",
        events=len(events),
        models=sorted({event.model for event in events}),
        latest_event=max((event.timestamp for event in events), default=None),
    )
    return events, status


def unknown_provider_statuses(home: Path) -> list[ProviderStatus]:
    probes = [
        (
            "Ollama",
            home / "AppData" / "Local" / "Ollama",
            "Ollama server logs do not retain per-response token counts; calls recorded by OpenCode are counted there.",
        ),
        (
            "Google / Gemini Antigravity",
            home / ".gemini" / "antigravity-cli",
            "Conversation storage is present but exposes no safe numeric token ledger in the inspected format.",
        ),
        (
            "Moonshot / Kimi",
            home / "AppData" / "Roaming" / "kimi-desktop",
            "Kimi stores context occupancy, not complete per-request daily token usage.",
        ),
        (
            "Alibaba / Qwen",
            home / "AppData" / "Roaming" / "Qwen",
            "Qwen desktop storage exposes no safe numeric token ledger in the inspected format.",
        ),
    ]
    return [
        ProviderStatus(
            provider=provider,
            collector="Installed client discovery",
            confidence="UNKNOWN",
            coverage="NONE",
            health="HEALTHY" if path.exists() else "UNKNOWN",
            detail=detail,
        )
        for provider, path, detail in probes
        if path.exists()
    ]


def collect_all(home: Path, lookback_days: int = LOOKBACK_DAYS) -> tuple[list[UsageEvent], list[ProviderStatus]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    events: list[UsageEvent] = []
    statuses: list[ProviderStatus] = []

    rows, status = collect_codex(home, cutoff)
    events.extend(rows)
    statuses.append(status)

    rows, status = collect_claude(home, cutoff)
    events.extend(rows)
    statuses.append(status)

    rows, open_statuses = collect_opencode(home, cutoff)
    events.extend(rows)
    statuses.extend(open_statuses)

    rows, status = collect_lmstudio(home, cutoff)
    events.extend(rows)
    statuses.append(status)

    rows, status = collect_grok(home, cutoff)
    events.extend(rows)
    statuses.append(status)

    present = {status.provider for status in statuses}
    for status in unknown_provider_statuses(home):
        if status.provider not in present:
            statuses.append(status)

    unique = {event.event_id: event for event in events}
    return sorted(unique.values(), key=lambda event: event.timestamp), statuses


def build_summary(
    events: list[UsageEvent],
    statuses: list[ProviderStatus],
    days: int = 14,
    collected_at: str | None = None,
) -> dict[str, Any]:
    days = max(1, min(days, LOOKBACK_DAYS))
    today = datetime.now().astimezone().date()
    first_day = today - timedelta(days=days - 1)
    day_keys = [(first_day + timedelta(days=index)).isoformat() for index in range(days)]
    day_map: dict[str, dict[str, Any]] = {
        key: {
            "date": key,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "cost_usd": 0.0,
            "events": 0,
        }
        for key in day_keys
    }
    model_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        day = _local_day(event.timestamp)
        if day not in day_map:
            continue
        bucket = day_map[day]
        for field in (
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
        ):
            bucket[field] += getattr(event, field)
        if event.cost_usd is not None:
            bucket["cost_usd"] += event.cost_usd
        bucket["events"] += 1
        key = (day, event.provider, event.model)
        if key not in model_map:
            model_map[key] = {
                "date": day,
                "provider": event.provider,
                "model": event.model,
                "locality": event.locality,
                "confidence": event.confidence,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "events": 0,
                "cost_usd": 0.0,
            }
        model = model_map[key]
        for field in (
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
        ):
            model[field] += getattr(event, field)
        model["events"] += 1
        if event.cost_usd is not None:
            model["cost_usd"] += event.cost_usd

    today_key = today.isoformat()
    observed_total = sum(bucket["total_tokens"] for bucket in day_map.values())
    all_time_observed = sum(event.total_tokens for event in events)
    unknown = [status.provider for status in statuses if status.confidence in ("UNKNOWN", "STALE") or status.coverage in ("NONE", "PARTIAL")]
    return {
        "schema": "token-piggy-bank.summary.v1",
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "timezone": str(datetime.now().astimezone().tzinfo),
        "coverage": "PARTIAL" if unknown else "COMPLETE_FOR_DISCOVERED_LOCAL_LEDGERS",
        "coverage_note": "Totals include only provider/model calls with numeric evidence in local ledgers. Missing telemetry is unknown, never zero.",
        "range": {"from": day_keys[0], "to": day_keys[-1], "days": days},
        "today": day_map[today_key],
        "range_total_tokens": observed_total,
        "lookback_observed_tokens": all_time_observed,
        "days": list(day_map.values()),
        "models": sorted(model_map.values(), key=lambda row: (row["date"], row["total_tokens"]), reverse=True),
        "providers": [asdict(status) for status in sorted(statuses, key=lambda item: item.provider.lower())],
        "unmeasured_or_partial": sorted(set(unknown)),
    }


def save_snapshot(summary: dict[str, Any]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (collected_at TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO snapshots(collected_at, payload) VALUES (?, ?)",
            (summary["collected_at"], json.dumps(summary, separators=(",", ":"))),
        )
        connection.execute(
            "DELETE FROM snapshots WHERE collected_at NOT IN (SELECT collected_at FROM snapshots ORDER BY collected_at DESC LIMIT 288)"
        )
        connection.commit()
    finally:
        connection.close()


class State:
    def __init__(self, home: Path, lookback_days: int) -> None:
        self.home = home
        self.lookback_days = lookback_days
        self.lock = threading.Lock()
        self.events: list[UsageEvent] = []
        self.statuses: list[ProviderStatus] = []
        self.error: str | None = None
        self.last_refresh_seconds = 0.0
        self.collected_at: str | None = None

    def refresh(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            events, statuses = collect_all(self.home, self.lookback_days)
            summary = build_summary(events, statuses)
            save_snapshot(summary)
            with self.lock:
                self.events = events
                self.statuses = statuses
                self.error = None
                self.last_refresh_seconds = time.monotonic() - started
                self.collected_at = summary["collected_at"]
            return summary
        except Exception as exc:  # collector failures must not crash the dashboard
            with self.lock:
                self.error = type(exc).__name__
                self.last_refresh_seconds = time.monotonic() - started
            raise

    def summary(self, days: int) -> dict[str, Any]:
        with self.lock:
            events = list(self.events)
            statuses = list(self.statuses)
            error = self.error
            elapsed = self.last_refresh_seconds
            collected_at = self.collected_at
        result = build_summary(events, statuses, days, collected_at=collected_at)
        result["collector_error"] = error
        result["refresh_seconds"] = round(elapsed, 3)
        return result


def make_handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "SovereignTokenCenter/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _static(self, filename: str, content_type: str) -> None:
            path = STATIC_ROOT / filename
            try:
                encoded = path.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/summary":
                query = parse_qs(parsed.query)
                try:
                    days = int(query.get("days", ["14"])[0])
                except ValueError:
                    days = 14
                self._json(state.summary(days))
                return
            if parsed.path == "/healthz":
                self._json({"ok": state.error is None, "collector_error": state.error})
                return
            if parsed.path in ("/", "/index.html"):
                self._static("index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._static("app.js", "text/javascript; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._static("styles.css", "text/css; charset=utf-8")
                return
            gold_assets = {
                "/assets/gold-drop.png": "assets/gold-drop.png",
                "/assets/gold-drop-sam.png": "assets/gold-drop-sam.png",
                "/assets/gold-drop-elon.png": "assets/gold-drop-elon.png",
                "/assets/gold-drop-dario.png": "assets/gold-drop-dario.png",
            }
            if parsed.path in gold_assets:
                self._static(gold_assets[parsed.path], "image/png")
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            nonce = self.headers.get("X-CSRF-Nonce", "")
            if host not in ("127.0.0.1:8765", "127.0.0.1:%d" % (self.server.server_address[1])):
                self.send_error(HTTPStatus.FORBIDDEN, "Host not loopback")
                return
            if origin is None or not origin.startswith("http://127.0.0.1"):
                self.send_error(HTTPStatus.FORBIDDEN, "Origin required (loopback)")
                return
            if not nonce:
                self.send_error(HTTPStatus.FORBIDDEN, "X-CSRF-Nonce required")
                return
            if urlparse(self.path).path != "/api/refresh":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                summary = state.refresh()
            except Exception:
                self._json({"ok": False, "error": state.error}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._json({"ok": True, "summary": summary})

    return Handler


def refresh_loop(state: State, stop: threading.Event) -> None:
    while not stop.wait(REFRESH_SECONDS):
        try:
            state.refresh()
        except Exception:
            continue


def main() -> int:
    parser = argparse.ArgumentParser(description="Local, read-only multi-model token usage monitor")
    parser.add_argument("--host", default="127.0.0.1", help="ignored; bind is pinned to 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    parser.add_argument("--once", action="store_true", help="Print a sanitized summary and exit")
    args = parser.parse_args()
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    state = State(home, max(1, min(args.lookback_days, 365)))
    summary = state.refresh()
    if args.once:
        print(json.dumps(summary, indent=2))
        return 0
    stop = threading.Event()
    worker = threading.Thread(target=refresh_loop, args=(state, stop), daemon=True)
    worker.start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    print(f"Sovereign Token Center: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
