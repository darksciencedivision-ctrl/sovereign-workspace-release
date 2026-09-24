"""Local multi-model debate table orchestrator."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import json
import os
import shutil
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from debate import argument_memory, prompt_contract
from debate.control_plane_guard import LoopbackControlPlaneGuard
from debate.shutdown_watcher import install_shutdown_watcher
from debate import model_capabilities as mcap
from debate.config_policy import (
    ConfigurationError,
    _parse_config_document,
    _read_config_text,
    classify_ollama_endpoint,
    resolve_ollama_base,
)
from debate import turn_completion as tc
import debate.output_guard as _og
REASONING = _og.REASONING_TAG_NAME
from debate.output_guard import (
    CLOSE_TAG_RE,
    OPEN_TAG_RE,
    TAG_NAME_RE,
    OutputGuard,
)
from debate.sentence_buffer import SentenceBuffer


ROOT = Path(__file__).parent

#: The configuration the application READS AND REWRITES. Seat edits are saved back to it, so
#: it is runtime state as well as a shipped document.
#:
#: EPC-01 P4-4. It used to be `ROOT/config.json` unconditionally — a git-TRACKED path that the
#: product writes to, so merely using the Debate Table dirtied the release candidate. That is
#: the N-29 defect that `tools/release/test_runtime_writes_are_gitignored.py` exists to catch,
#: and debate was still carrying it after every other module's writes had moved out.
#:
#: `CONFIG_PATH` now points into the module's state root, set by the shell. The shipped
#: `ROOT/config.json` becomes a SEED: read once, copied to the state root the first time the
#: application starts there, and never written again. Running app.py directly with no
#: CONFIG_PATH set behaves exactly as before.
CONFIG_TEMPLATE = (ROOT / "config.json").resolve()
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", CONFIG_TEMPLATE)).resolve()


def _seed_config_from_template() -> None:
    """Place the shipped configuration in the state root the first time it is needed.

    Deliberately narrow: it copies ONLY when the target is absent, so an operator's edited
    configuration is never overwritten by the shipped one, and it never touches the template.
    """
    if CONFIG_PATH == CONFIG_TEMPLATE or CONFIG_PATH.exists():
        return
    if not CONFIG_TEMPLATE.is_file():
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONFIG_TEMPLATE, CONFIG_PATH)


_seed_config_from_template()

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    "allow_remote_ollama": False,
    "allow_originless_ws_clients": True,
    "port": 8700,
    "topic_rotate_turns": 24,
    "anchor_every_turns": 10,
    "turn_delay_ms": 1500,
    "context_turns": 8,
    "num_predict": 320,
    "temperature": 0.7,
    "top_p": 0.9,
    "insight_panel": False,
    "extractor_model": "dolphin-llama3:8b",
    "insight_timeout_seconds": 10,
    "insight_queue_max": 2,
    "empty_spoken_retry_count": 1,
    "repetition_overlap_threshold": 0.60,
    "repetition_min_tokens": 20,
    "turn_word_min": 110,
    "turn_word_max": 160,
    "consensus_window_turns": 4,
    "consensus_challenge_weight": 3.0,
}


# Central operator-input envelope (P0-16). Backend enforcement and the
# frontend maxlength attributes must both derive from these values.
INPUT_LIMITS = {
    "public_title": 300,
    "debate_brief": 20000,
    "seat_name": 100,
    "model_name": 200,
    "persona": 4000,
    "thesis": 8000,
    "interjection": 4000,
    "revision_reason": 2000,
}
PUBLIC_TITLE_MAX_CHARS = INPUT_LIMITS["public_title"]
DEBATE_BRIEF_MAX_CHARS = INPUT_LIMITS["debate_brief"]

# S16.3: bounded rotating structured log. JSON-lines; never given prompt or
# interjection payloads - only event metadata and numeric metrics.
import logging
from logging.handlers import RotatingFileHandler

_LOG_DIR = Path(os.environ.get("DEBATE_LOG_DIR", ROOT / "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("debate.table")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_handler = RotatingFileHandler(
    _LOG_DIR / "debate.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)


async def _capability_client_factory():
    outer = _http_client

    @asynccontextmanager
    async def _one():
        if outer is not None:
            yield _http_client
        else:
            async with httpx.AsyncClient(
                base_url=OLLAMA, timeout=MODELS_HTTP_TIMEOUT
            ) as client:
                yield client

    return _one()


def log_event(event: str, **fields) -> None:
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event}
    record.update(fields)
    try:
        _logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:
        pass

def _valid_number(value, default, minimum, maximum, integer=False):
    if isinstance(value, bool):
        return default
    try:
        converted = int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not minimum <= converted <= maximum:
        return default
    return converted


def atomic_write_json(path: Path, document: dict) -> None:
    data = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


_SEAT_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_seats(raw) -> list:
    # P0-17: seat identity schema. Structural defects are rejected with
    # path-specific diagnostics; nothing is truncated or invented (G-07).
    if not isinstance(raw, list) or not 2 <= len(raw) <= 4:
        received = str(len(raw)) if isinstance(raw, list) else type(raw).__name__
        raise ConfigurationError(
            f"config.seats: expected 2..4 seats, received {received}"
        )
    seen = {}
    validated = []
    for index, seat in enumerate(raw):
        where = f"config.seats[{index}]"
        if not isinstance(seat, dict):
            raise ConfigurationError(f"{where}: seat must be a JSON object")
        name = str(seat.get("name", "")).strip()
        if not name:
            raise ConfigurationError(f"{where}.name: must be a non-empty string")
        if len(name) > INPUT_LIMITS["seat_name"]:
            raise ConfigurationError(
                f"{where}.name exceeds {INPUT_LIMITS['seat_name']} characters"
            )
        key = name.casefold()
        if key in seen:
            raise ConfigurationError(
                f'{where}.name: duplicate seat name "{name}"'
                f" (config.seats[{seen[key]}] after normalization)"
            )
        seen[key] = index
        model = str(seat.get("model", "")).strip()
        if not model:
            raise ConfigurationError(f"{where}.model: must be a non-empty string")
        if len(model) > INPUT_LIMITS["model_name"]:
            raise ConfigurationError(
                f"{where}.model exceeds {INPUT_LIMITS['model_name']} characters"
            )
        persona = str(seat.get("persona", "A careful, direct debater.")).strip()
        if len(persona) > INPUT_LIMITS["persona"]:
            raise ConfigurationError(
                f"{where}.persona exceeds {INPUT_LIMITS['persona']} characters"
            )
        thesis = str(seat.get("thesis", "")).strip()
        if len(thesis) > INPUT_LIMITS["thesis"]:
            raise ConfigurationError(
                f"{where}.thesis exceeds {INPUT_LIMITS['thesis']} characters"
            )
        color = str(seat.get("color", "#7dd3fc")).strip()
        if not _SEAT_COLOR_RE.match(color):
            raise ConfigurationError(
                f'{where}.color: "{color}" is not a valid color format (#RRGGBB)'
            )
        validated.append(
            {
                "name": name,
                "model": model,
                "persona": persona,
                "color": color,
                "thesis": thesis,
            }
        )
    return validated


def load_config(path: Path) -> dict:
    # Fail closed: an unparseable or non-object configuration raises
    # ConfigurationError instead of degrading to defaults, so the branch below
    # can never write normalized defaults over corrupt original bytes (G-05).
    document = _parse_config_document(path, _read_config_text(path))
    normalized = dict(document)
    for key, default in DEFAULTS.items():
        normalized.setdefault(key, default)

    numeric_rules = {
        "port": (1, 65535, True),
        "topic_rotate_turns": (0, 10000, True),
        "anchor_every_turns": (0, 10000, True),
        "turn_delay_ms": (0, 60000, True),
        "context_turns": (1, 100, True),
        "num_predict": (32, 8192, True),
        "temperature": (0, 2, False),
        "top_p": (0.01, 1, False),
        "insight_timeout_seconds": (1, 120, False),
        "insight_queue_max": (1, 100, True),
        "empty_spoken_retry_count": (0, 3, True),
        "repetition_overlap_threshold": (0, 1, False),
        "repetition_min_tokens": (1, 1000, True),
        "turn_word_min": (20, 2000, True),
        "turn_word_max": (20, 4000, True),
        "consensus_window_turns": (1, 100, True),
        "consensus_challenge_weight": (1, 20, False),
    }
    for key, (minimum, maximum, integer) in numeric_rules.items():
        normalized[key] = _valid_number(
            normalized.get(key), DEFAULTS[key], minimum, maximum, integer
        )
    if normalized["turn_word_min"] > normalized["turn_word_max"]:
        raise ConfigurationError(
            f"config.turn_word_min ({normalized['turn_word_min']})"
            f" must be <= config.turn_word_max ({normalized['turn_word_max']})"
        )
    if not isinstance(normalized.get("insight_panel"), bool):
        normalized["insight_panel"] = False
    if not isinstance(normalized.get("allow_remote_ollama"), bool):
        normalized["allow_remote_ollama"] = False
    if not isinstance(normalized.get("allow_originless_ws_clients"), bool):
        normalized["allow_originless_ws_clients"] = True
    for key in ("ollama_url", "extractor_model"):
        if not isinstance(normalized.get(key), str) or not normalized[key].strip():
            normalized[key] = DEFAULTS[key]

    normalized["seats"] = _validate_seats(normalized.get("seats"))
    if normalized != document:
        atomic_write_json(path, normalized)
    return normalized


try:
    CONFIG = load_config(CONFIG_PATH)
    INFERENCE_BACKEND = os.environ.get("SOVEREIGN_INFERENCE_BACKEND", "ollama").strip().lower()
    LLAMACPP_ACTIVE = INFERENCE_BACKEND in {"llama.cpp", "llamacpp", "llama_cpp"}
    if LLAMACPP_ACTIVE:
        OLLAMA, OLLAMA_ENDPOINT_CLASS = resolve_ollama_base(
            os.environ.get("SOVEREIGN_LLAMACPP_HOST")
            or os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL")
            or "http://127.0.0.1:18080",
            None,
            False,
            CONFIG_PATH,
        )
        # The shared router exposes one admitted 8B model.  Keep the seat
        # personas distinct while using a model ID that actually exists.
        for seat in CONFIG["seats"]:
            seat["model"] = "qwen3-8b"
        CONFIG["extractor_model"] = "qwen3-8b"
    else:
        OLLAMA, OLLAMA_ENDPOINT_CLASS = resolve_ollama_base(
            CONFIG["ollama_url"],
            os.environ.get("OLLAMA_URL"),
            CONFIG["allow_remote_ollama"],
            CONFIG_PATH,
        )
except ConfigurationError as exc:
    log_event("startup_config_fatal", error=type(exc).__name__)
    print(f"FATAL: {exc}", file=sys.stderr)
    print(
        "FATAL: refusing to start; fix config.json"
        " (original bytes were left untouched).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None
if OLLAMA_ENDPOINT_CLASS == "remote":
    # Deliberate opt-in only. Never describe this deployment as local-only.
    print(
        "WARNING: remote Ollama endpoint enabled by operator opt-in;"
        f" traffic will leave this host ({OLLAMA})",
        file=sys.stderr,
    )
SEATS = CONFIG["seats"][:4]
TOPIC_ROTATE_TURNS = CONFIG["topic_rotate_turns"]
ANCHOR_EVERY_TURNS = CONFIG["anchor_every_turns"]
TURN_DELAY_S = CONFIG["turn_delay_ms"] / 1000.0
CONTEXT_TURNS = CONFIG["context_turns"]
GEN_OPTIONS = {
    "num_predict": CONFIG["num_predict"],
    "temperature": CONFIG["temperature"],
    "top_p": CONFIG["top_p"],
}


def _inference_headers() -> dict[str, str]:
    if not LLAMACPP_ACTIVE:
        return {}
    key = os.environ.get("SOVEREIGN_LLAMA_CPP_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}

argument_memory_tracker = argument_memory.ArgumentMemory(
    [seat["name"] for seat in SEATS]
)

LABEL_TOPIC = "TOPIC:"
LABEL_ANCHOR = "CONTINUITY ANCHOR:"
LABEL_TRANSCRIPT = "RECENT TABLE TRANSCRIPT:"
LABEL_OPERATOR_NOTE = "OPERATOR NOTE:"
LABEL_MOVE = "YOUR MOVE:"
LABEL_RECENT_ARGUMENTS = "YOUR RECENT ARGUMENTS:"
TURN_PROMPT_LABELS = (
    LABEL_TOPIC,
    LABEL_ANCHOR,
    LABEL_TRANSCRIPT,
    LABEL_OPERATOR_NOTE,
    LABEL_MOVE,
    LABEL_RECENT_ARGUMENTS,
)

TURN_WORD_MIN = int(CONFIG["turn_word_min"])
TURN_WORD_MAX = int(CONFIG["turn_word_max"])

MOVE_TEXT = {
    "challenge": "Test the strongest prior claim. State what evidence or logic would overturn it; do not invent disagreement.",
    "concur-extend": "Concede the best prior point explicitly, then extend it into new ground.",
    "analyze": "Analyze exactly where the positions at the table diverge and why it matters.",
    "cross-examine": "Ask one sharp directed question, then give your provisional answer.",
    "reframe": "Show why the current framing is incomplete and offer a more useful frame.",
    "evidence": "Supply or demand a concrete example, case, or thought experiment.",
    "synthesize": "Synthesize compatible claims, then identify what remains unresolved.",
    "escalate": "Trace the current claim to its hardest logical consequence.",
    "answer-then-advance": "Answer the directed question plainly first, then advance the debate with one new implication.",
}
MOVE_WEIGHTS = {
    "challenge": 3.0,
    "concur-extend": 2.0,
    "analyze": 2.0,
    "cross-examine": 2.0,
    "reframe": 1.0,
    "evidence": 2.0,
    "synthesize": 1.0,
    "escalate": 1.0,
}
# Explicit disagreement markers only. Register-noise singletons (but,
# however, challenge, incorrect, doubt) were measured to saturate every
# 4-turn window in the v1.2 acceptance corpus (snapshot D1), which kept the
# consensus-breaker permanently inert; they are deliberately not markers.
DISAGREEMENT_MARKERS = (
    "disagree",
    "counterpoint",
    "what evidence",
    "i reject",
    "not convinced",
    "on the contrary",
    "fails because",
)
_MARKER_RES = tuple(
    re.compile(r"\b" + r"\s+".join(re.escape(t) for t in m.split()) + r"\b", re.I)
    for m in DISAGREEMENT_MARKERS
)
INTERROGATIVE_WORDS = (
    "why",
    "how",
    "what",
    "when",
    "where",
    "which",
    "who",
    "would",
    "could",
    "can",
    "do",
    "does",
    "is",
    "are",
    "should",
)

TOPIC_DOMAINS = [
    "philosophy of mind",
    "ethics",
    "AI futures",
    "cosmology",
    "evolutionary biology",
    "economics",
    "game theory",
    "language and meaning",
    "consciousness",
    "political philosophy",
    "engineering trade-offs",
    "information theory",
    "epistemology",
    "complex systems",
    "human flourishing",
]
FALLBACK_TOPICS = [
    "Is intelligence better measured by what it builds or what it refuses to build?",
    "Can meaning be defined operationally without destroying it?",
    "Does compression explain understanding, or merely imitate it?",
    "What would a good post-human future actually optimize?",
    "Is disagreement between honest reasoners evidence that truth is plural?",
    "Does free will survive contact with good enough prediction?",
]


def speech_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def repetition_overlap(previous: str, current: str, minimum: int) -> float:
    prior_tokens = speech_tokens(previous)
    current_tokens = speech_tokens(current)
    if len(prior_tokens) < minimum or len(current_tokens) < minimum:
        return 0.0
    union = prior_tokens | current_tokens
    return len(prior_tokens & current_tokens) / len(union) if union else 0.0


def disagreement_present(turns: list[dict]) -> bool:
    joined = " ".join(turn.get("text", "") for turn in turns).lower()
    return any(pattern.search(joined) for pattern in _MARKER_RES)


def detect_directed_questions(text: str, speaker: str, seat_names: list[str]) -> set[str]:
    """Find explicit questions directed to another named seat.

    A clause must actually ask something of the target: it ends the
    question with '?' AND names the target AND either addresses them in
    second person or opens with a vocative ("Name, ..."). Narrative
    mentions ("Clue explained why X fails.") are not directed questions.
    """
    found = set()
    clauses = re.split(r"(?<=[.!?])\s+|\n+", text)
    for target in seat_names:
        if target == speaker:
            continue
        target_pattern = re.compile(rf"\b{re.escape(target)}\b", re.I)
        vocative_pattern = re.compile(rf"^\s*{re.escape(target)}\s*,", re.I)
        second_person = re.search(r"\b(?:you|your|yours|yourself)\b", text, re.I)
        for clause in clauses:
            if "?" not in clause:
                continue
            if not target_pattern.search(clause):
                continue
            if re.search(r"\b(?:you|your|yours|yourself)\b", clause, re.I) or (
                vocative_pattern.match(clause)
            ):
                found.add(target)
                break
        _ = second_person
    return found


class State:
    def __init__(self):
        self.topic = ""  # debate_brief: drawer + model prompt context (§6)
        self.public_title = ""  # stage-only caption, separate from topic/brief (§6)
        self.topic_epoch = 0
        self.turn = 0
        self.anchor = ""
        self.transcript: list[dict] = []
        self.paused = False
        self.interject: str | None = None
        self.pending_topic: dict | None = None
        self.speaker_idx = 0
        self.last_move: str | None = None
        self.status = "starting"
        self.interrupt_generation = asyncio.Event()
        self.pending_questions: dict[str, deque[str]] = {
            seat["name"]: deque() for seat in SEATS
        }
        self.previous_public: dict[str, str] = {}
        # P0-15/G-09: remediation is attributable to the seat whose output
        # caused it; never inherited by whoever happens to speak next.
        self.repetition_pending: dict[str, float] = {}
        # P0-15 accounting: cumulative process counters plus a topic-scoped
        # completed counter driving rotation/anchor cadence.
        self.attempted_turns = 0
        self.completed_public_turns = 0
        self.skipped_turns = 0
        self.completed_turns = 0
        self.repetition_alternator = False
        self.pending_reframe: dict[str, str] = {}
        self.recent_turns: deque[dict] = deque(
            maxlen=int(CONFIG["consensus_window_turns"])
        )
        self.last_move_reason = ""
        self.last_move_turn = 0
        self.generation_active = False
        self.shutting_down = False

    def reset_debate_state(self):
        self.pending_questions = {seat["name"]: deque() for seat in SEATS}
        self.previous_public = {}
        self.repetition_pending = {}
        # A queued interjection belongs to the current topic only (P0-20).
        self.interject = None
        self.completed_turns = 0
        self.repetition_alternator = False
        self.pending_reframe = {}
        self.recent_turns.clear()
        self.last_move = None
        self.last_move_reason = ""
        self.last_move_turn = 0

    def observe_public_turn(self, speaker: str, text: str):
        for target in detect_directed_questions(
            text, speaker, [seat["name"] for seat in SEATS]
        ):
            self.pending_questions[target].append(speaker)
        previous = self.previous_public.get(speaker, "")
        overlap = repetition_overlap(
            previous, text, int(CONFIG["repetition_min_tokens"])
        )
        self.previous_public[speaker] = text
        if overlap >= float(CONFIG["repetition_overlap_threshold"]):
            self.repetition_pending[speaker] = overlap
        self.recent_turns.append({"name": speaker, "text": text})


state = State()


CLIENT_QUEUE_MAX = 256
CLIENT_SEND_TIMEOUT_S = 10.0


class ClientConnection:
    """One WebSocket with its own bounded outbound queue (P1-ws-isolation)."""

    __slots__ = ("ws", "queue", "sender_task", "dropped", "closed")

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=CLIENT_QUEUE_MAX
        )
        self.sender_task: asyncio.Task | None = None
        self.dropped = 0
        self.closed = False


class Hub:
    """Broadcast hub that never lets a slow client delay the table.

    send() only enqueues; each connection has a sender task that writes to
    the socket under a timeout. Overflow policy is explicit: a client whose
    queue is full is counted and disconnected (1013 try-again-later).
    """

    def __init__(self):
        self.clients: set[ClientConnection] = set()
        self.broadcast_dropped_total = 0

    def register(self, ws: WebSocket) -> ClientConnection:
        conn = ClientConnection(ws)
        self.clients.add(conn)
        return conn

    def unregister(self, conn: ClientConnection) -> None:
        self.clients.discard(conn)
        conn.closed = True
        if not conn.queue.full():
            try:
                conn.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def _disconnect(self, conn: ClientConnection) -> None:
        if conn.closed:
            return
        conn.closed = True
        self.clients.discard(conn)
        if conn.sender_task and not conn.sender_task.done():
            conn.sender_task.cancel()
        try:
            await conn.ws.close(code=1013)
        except Exception:
            pass

    async def send(self, event: dict):
        message = json.dumps(event, ensure_ascii=False)
        for conn in list(self.clients):
            if conn.closed:
                continue
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                # Give this connection's sender one scheduling opportunity to
                # drain before declaring it too slow - protects healthy
                # clients from eviction during legitimate bursts.
                await asyncio.sleep(0)
                try:
                    conn.queue.put_nowait(message)
                except asyncio.QueueFull:
                    conn.dropped += 1
                    self.broadcast_dropped_total += 1
                    asyncio.create_task(self._disconnect(conn))


    async def _sender(self, conn: ClientConnection) -> None:
        try:
            while True:
                message = await conn.queue.get()
                if message is None or conn.closed:
                    break
                await asyncio.wait_for(
                    conn.ws.send_text(message), timeout=CLIENT_SEND_TIMEOUT_S
                )
        except (asyncio.TimeoutError, Exception):
            pass
        finally:
            self.clients.discard(conn)
            conn.closed = True
            # CR-023: when the sender terminates (a send failure/timeout, or the normal sentinel),
            # close the WebSocket so the receiver's blocked receive_text() unblocks promptly. The
            # old code left the socket open on a terminal send failure, so the endpoint task and its
            # socket lingered until the peer happened to disconnect (the review observed zero close
            # calls). Closing here coordinates sender/receiver teardown; a double close on the
            # normal path is a harmless no-op.
            try:
                await conn.ws.close()
            except Exception:
                pass


hub = Hub()
seat_mutation_lock = asyncio.Lock()


STREAM_INACTIVITY_SECONDS = 30.0
INSIGHT_INSTALLED_TTL_S = 30.0

# Centralized HTTP timeout policy (P1): one process-lifetime AsyncClient with
# keepalive is created in lifespan; per-call timeouts remain explicit.
CHAT_HTTP_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
MODELS_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
READY_HTTP_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

_http_client: httpx.AsyncClient | None = None
_STARTED_MONOTONIC = time.monotonic()


def _load_build_version() -> str:
    try:
        info = json.loads(
            (ROOT / "BUILD-INFO.json").read_text(encoding="utf-8-sig")
        )
        return str(info.get("phase") or "unknown")
    except Exception:
        return "unknown"


_BUILD_VERSION = _load_build_version()

@asynccontextmanager
async def _acquire_client(timeout: httpx.Timeout, transport=None):
    """Yield the shared keepalive client unless a test injected transport."""
    if transport is None and _http_client is not None:
        yield _http_client
    else:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            yield client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class StreamProtocolError(Exception):
    """A streamed Ollama line violated the NDJSON chat protocol."""


class StreamIncomplete(Exception):
    """The stream ended without Ollama's terminal done frame (P0-13)."""


class TurnInterrupted(Exception):
    """An operator action intentionally abandoned an in-flight generation."""


class PublicStreamFilter:
    """Incrementally remove hidden-reasoning regions before any broadcast.

    P0-09: tag recognition is tolerant of whitespace/attribute variants
    ("<think >", "<think a=\"b\">", "</think >", case differences) while
    remaining safe across arbitrary chunk boundaries.
    """

    MAX_TAG_LEN = 48  # longest plausible reasoning open/close tag

    def __init__(self):
        self.buffer = ""
        self.hidden_tag: str | None = None

    def _hold_index(self) -> int | None:
        """Index from which a trailing '<...' could still grow into a tag."""
        idx = self.buffer.rfind("<")
        if idx == -1:
            return None
        if len(self.buffer) - idx > self.MAX_TAG_LEN:
            return None
        return idx

    def feed(self, fragment: str, final: bool = False) -> str:
        self.buffer += fragment
        output = []
        while True:
            if self.hidden_tag:
                close = CLOSE_TAG_RE.search(self.buffer)
                if close:
                    self.buffer = self.buffer[close.end() :]
                    self.hidden_tag = None
                    continue
                hold = self._hold_index()
                if final or hold is None:
                    # Everything still buffered is hidden content.
                    self.buffer = ""
                else:
                    output.append(self.buffer[:hold])
                    self.buffer = self.buffer[hold:]
                break

            opener = OPEN_TAG_RE.search(self.buffer)
            closer = CLOSE_TAG_RE.search(self.buffer)
            if closer and (opener is None or closer.start() < opener.start()):
                # Stray closing tag with nothing to close: drop it silently.
                output.append(self.buffer[: closer.start()])
                self.buffer = self.buffer[closer.end() :]
                continue
            if opener:
                name_match = TAG_NAME_RE.match(
                    self.buffer[opener.start() : opener.end()]
                )
                output.append(self.buffer[: opener.start()])
                self.hidden_tag = (name_match.group(1) if name_match else "think").lower()
                self.buffer = self.buffer[opener.end() :]
                continue

            if final:
                output.append(self.buffer)
                self.buffer = ""
                break
            hold = self._hold_index()
            if hold is None:
                output.append(self.buffer)
                self.buffer = ""
            else:
                output.append(self.buffer[:hold])
                self.buffer = self.buffer[hold:]
            break
        return "".join(output)


def _clean_prefix_pattern() -> re.Pattern:
    # Narrowed on purpose (§4.4 of the v1.1 directive): the old pattern
    # stripped ANY leading "Word:", destroying legitimate openings like
    # "In short: ..." or "Fact: ...". This only matches the known control
    # labels (derived from turn_prompt, not hand-duplicated) and seat names.
    names = [label.rstrip(":") for label in TURN_PROMPT_LABELS]
    names += [seat["name"] for seat in SEATS]
    alternatives = "|".join(re.escape(name) for name in names if name)
    if not alternatives:
        return re.compile(r"(?!x)x")  # matches nothing
    return re.compile(rf"^\s*(?:\*\*)?(?:{alternatives})\s*:\s*", re.I)


def clean(text: str) -> str:
    text = re.sub(
        rf"<\s*{REASONING}\b[^<>]*?>.*?<\s*/\s*{REASONING}\b[^<>]*?>",
        "",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(rf"</?\s*{REASONING}\b[^<>]*?>", "", text, flags=re.I)
    text = _clean_prefix_pattern().sub("", text.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def _anext_line(lines_iter):
    return await lines_iter.__anext__()


def _consume_task(task):
    # Done-callback: retrieve outcome so no cancelled/failed helper task ever
    # leaks an "exception was never retrieved" warning.
    if not task.cancelled():
        task.exception()


def _tracked(task):
    task.add_done_callback(_consume_task)
    return task


async def ollama_chat(
    model: str,
    messages: list,
    on_public: Callable[[str], Awaitable[None]] | None = None,
    interruptible: bool = False,
    metrics: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> str:
    # EPC-01 P1-3 follow-on — MEASURING clock.
    #
    # These durations were read from `time.monotonic()`, whose resolution on Windows is 15.625 ms
    # (measured: two back-to-back reads differ by exactly 0.0). Any model response faster than one
    # clock tick therefore produced `duration_seconds == 0.0`, and the guard
    # `if isinstance(eval_count, ...) and duration:` treated that as falsy — so `tokens_per_second`
    # was silently never emitted. The metric did not go wrong; it vanished, which is worse, because
    # cost accounting downstream saw an absent key rather than a bad number.
    #
    # `perf_counter()` is monotonic too and resolves to 1e-07 s here. Deadline and uptime sites are
    # deliberately left on `monotonic()` — 15.6 ms means nothing to a timeout or an uptime counter.
    started_at = time.perf_counter()
    if metrics is not None:
        metrics.update(
            {
                "first_raw_seconds": None,
                "first_public_seconds": None,
                "duration_seconds": None,
                "hidden_reasoning_present": False,
                "budget_exhausted": False,
                "eval_count": None,
                "prompt_eval_count": None,
            }
        )
    payload = {
        "model": model,
        "messages": messages,
        "stream": on_public is not None,
        "options": GEN_OPTIONS,
    }
    if LLAMACPP_ACTIVE:
        payload = {
            "model": model,
            "messages": messages,
            "stream": on_public is not None,
            "max_tokens": GEN_OPTIONS["num_predict"],
            "temperature": GEN_OPTIONS["temperature"],
            "top_p": GEN_OPTIONS["top_p"],
        }
    chat_url = f"{OLLAMA}/v1/chat/completions" if LLAMACPP_ACTIVE else f"{OLLAMA}/api/chat"
    async with _acquire_client(CHAT_HTTP_TIMEOUT, transport) as client:
        if on_public is None:
            if interruptible and state.interrupt_generation.is_set():
                raise TurnInterrupted
            send_task = _tracked(
                asyncio.create_task(client.post(chat_url, json=payload, headers=_inference_headers()))
            )
            if interruptible:
                interrupt_wait = _tracked(
                    asyncio.create_task(state.interrupt_generation.wait())
                )
                done_set, _pending = await asyncio.wait(
                    {send_task, interrupt_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if interrupt_wait in done_set and send_task not in done_set:
                    send_task.cancel()
                    interrupt_wait.cancel()
                    raise TurnInterrupted
                interrupt_wait.cancel()
            else:
                done_set = {send_task}
                await asyncio.wait({send_task})
            response = send_task.result()
            response.raise_for_status()
            if LLAMACPP_ACTIVE:
                choices = response.json().get("choices") or []
                message = choices[0].get("message", {}) if choices else {}
                return clean(message.get("content", ""))
            return clean(response.json().get("message", {}).get("content", ""))

        public_parts = []
        filter_ = PublicStreamFilter()
        done_seen = False
        async with client.stream(
            "POST", chat_url, json=payload, headers=_inference_headers()
        ) as response:
            response.raise_for_status()
            lines_iter = response.aiter_lines().__aiter__()
            while True:
                next_line = _tracked(asyncio.create_task(_anext_line(lines_iter)))
                waiters = {next_line}
                inactivity = _tracked(
                    asyncio.create_task(asyncio.sleep(STREAM_INACTIVITY_SECONDS))
                )
                waiters.add(inactivity)
                interrupt_wait = None
                if interruptible:
                    interrupt_wait = _tracked(
                        asyncio.create_task(state.interrupt_generation.wait())
                    )
                    waiters.add(interrupt_wait)
                done_set, _pending = await asyncio.wait(
                    waiters, return_when=asyncio.FIRST_COMPLETED
                )
                for extra in (inactivity, interrupt_wait):
                    if extra is not None and extra not in done_set:
                        extra.cancel()
                if interrupt_wait is not None and interrupt_wait in done_set:
                    next_line.cancel()
                    if metrics is not None:
                        metrics["interrupt_reason"] = "operator_interruption"
                    raise TurnInterrupted
                if inactivity in done_set:
                    next_line.cancel()
                    # A silent stream is an interrupted generation, not a
                    # completed one; reason distinguishes it from operator pause.
                    if metrics is not None:
                        metrics["interrupt_reason"] = "stream_inactivity"
                    raise TurnInterrupted
                try:
                    line = next_line.result()
                except StopAsyncIteration:
                    break
                if not line.strip():
                    continue
                if LLAMACPP_ACTIVE:
                    if not line.startswith("data:"):
                        continue
                    encoded = line[5:].strip()
                    if encoded == "[DONE]":
                        done_seen = True
                        tail = filter_.feed("", final=True)
                        if tail:
                            public_parts.append(tail)
                            await on_public(tail)
                        break
                    line = encoded
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    snippet = line[:120]
                    raise StreamProtocolError(
                        f"malformed NDJSON at offset {exc.colno}: {snippet!r}"
                    ) from exc
                if LLAMACPP_ACTIVE:
                    choices = data.get("choices") or []
                    choice = choices[0] if choices else {}
                    message = choice.get("delta", {})
                    raw = message.get("content", "") or ""
                    thinking = ""
                    if choice.get("finish_reason") is not None:
                        done_seen = True
                else:
                    message = data.get("message", {})
                    raw = message.get("content", "")
                    thinking = message.get("thinking", "")
                if metrics is not None:
                    if metrics["first_raw_seconds"] is None and (raw or thinking):
                        metrics["first_raw_seconds"] = time.perf_counter() - started_at
                    if thinking or re.search(
                        r"<(?:think|analysis|reasoning)>", raw, re.I
                    ):
                        metrics["hidden_reasoning_present"] = True
                # Ollama's separate `thinking` field is intentionally ignored.
                public = filter_.feed(raw)
                if public:
                    if (
                        metrics is not None
                        and metrics["first_public_seconds"] is None
                    ):
                        metrics["first_public_seconds"] = time.perf_counter() - started_at
                    public_parts.append(public)
                    await on_public(public)
                if (not LLAMACPP_ACTIVE and data.get("done")) or (
                    LLAMACPP_ACTIVE and done_seen
                ):
                    done_seen = True
                    if metrics is not None:
                        if LLAMACPP_ACTIVE:
                            usage = data.get("usage") or {}
                            metrics["budget_exhausted"] = choice.get("finish_reason") == "length"
                            metrics["eval_count"] = usage.get("completion_tokens")
                            metrics["prompt_eval_count"] = usage.get("prompt_tokens")
                        else:
                            metrics["budget_exhausted"] = data.get("done_reason") == "length"
                            metrics["eval_count"] = data.get("eval_count")
                            metrics["prompt_eval_count"] = data.get("prompt_eval_count")
                    tail = filter_.feed("", final=True)
                    if tail:
                        if (
                            metrics is not None
                            and metrics["first_public_seconds"] is None
                        ):
                            metrics["first_public_seconds"] = (
                                time.perf_counter() - started_at
                            )
                        public_parts.append(tail)
                        await on_public(tail)
                    break
        if metrics is not None:
            metrics["duration_seconds"] = time.perf_counter() - started_at
            metrics["done_seen"] = done_seen
            eval_count = metrics.get("eval_count")
            duration = metrics.get("duration_seconds")
            if isinstance(eval_count, (int, float)) and duration:
                metrics["tokens_per_second"] = round(eval_count / duration, 2)
            metrics["stream_protocol"] = "ok" if done_seen else "incomplete"
        if not done_seen:
            raise StreamIncomplete(
                "stream ended without terminal done frame"
            )
        return clean("".join(public_parts))


#: The operator's LOCAL MODEL CEILING (OPERATOR-INSTRUCTIONS.log ENTRY 017): "We do not wanna use
#: anything above eight billion parameters in our local library." Expressed as the 8B NAMEPLATE
#: class, so the model the operator named to prove the system with - qwen3:8b, whose true count is
#: 8.2B - is admitted while the 9B class and upward is not.
#:
#: COUPLED VALUE (S-4). The same rule is implemented for the SOW shell in
#: `modules/sow/adapters/local/model_ceiling.py`. It is duplicated rather than imported because
#: Debate and SOW are separate products with separate install provenance and separate virtualenvs -
#: a cross-module import would tie Debate's startup to SOW's package tree. If the operator moves the
#: ceiling, BOTH sites move together, and this comment is the pointer to the other one.
CEILING_NAMEPLATE_B = 8
_CEILING_TRUE_PARAMS = 9.0e9

_PARAM_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12, "": 1.0}


def parse_parameter_count(raw) -> float | None:
    """`"8.2B"` -> 8.2e9. None when unreadable - never 0, which would sail under the ceiling."""
    if not isinstance(raw, str):
        return None
    match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMBT])?\s*$", raw.strip(), re.I)
    if not match:
        return None
    value = float(match.group(1)) * _PARAM_SUFFIX[(match.group(2) or "").upper()]
    return value if value > 0 else None


def ceiling_verdict(record: dict) -> dict:
    """Admit or refuse ONE `/api/tags` row against the operator's ceiling, with the reason.

    A refused seat is REPORTED, never silently dropped: `/ready` renders it so the operator can see
    which seat cannot run and why, which is the honest-degradation rule (S-19) applied to a debate
    table. Never raises - this feeds a readiness endpoint.
    """
    details = record.get("details") or {}
    shown = details.get("parameter_size")
    params = parse_parameter_count(shown)
    name = record.get("name") or "(unnamed)"
    if params is None:
        return {"within_ceiling": False, "parameter_size": shown,
                "reason": f"{name} reports no readable parameter count, so it cannot be shown to be "
                          f"within the operator's {CEILING_NAMEPLATE_B}B ceiling (fail closed)"}
    if params >= _CEILING_TRUE_PARAMS:
        return {"within_ceiling": False, "parameter_size": shown,
                "reason": f"{name} has {shown} parameters, above the operator's "
                          f"{CEILING_NAMEPLATE_B}B ceiling (ENTRY 017) - this host's GPU carries "
                          f"8 GB of VRAM and a larger model straddles it. Installed and kept, but "
                          f"not usable as a debate seat in this build"}
    return {"within_ceiling": True, "parameter_size": shown, "reason": None}


async def installed_model_records() -> dict[str, dict]:
    """Return registered local models in the Debate ceiling's record shape."""
    async with _acquire_client(MODELS_HTTP_TIMEOUT) as client:
        url = f"{OLLAMA}/v1/models" if LLAMACPP_ACTIVE else f"{OLLAMA}/api/tags"
        response = await client.get(url, headers=_inference_headers())
        response.raise_for_status()
    if LLAMACPP_ACTIVE:
        records: dict[str, dict] = {}
        for item in response.json().get("data", []):
            name = str(item.get("id", "")).strip()
            if not name:
                continue
            match = re.search(r"(?:^|[-:.])(\d+(?:\.\d+)?)b(?:$|[-:.])", name, re.I)
            parameter_size = f"{match.group(1)}B" if match else None
            records[name] = {
                "name": name,
                "details": {"parameter_size": parameter_size},
            }
        return records
    return {
        item["name"]: item
        for item in response.json().get("models", [])
        if item.get("name")
    }


async def installed_models() -> list[str]:
    return sorted(await installed_model_records())


def public_seats() -> list[dict]:
    return [
        {"name": seat["name"], "model": seat["model"], "color": seat["color"]}
        for seat in SEATS
    ]


def persist_seat_model(seat_name: str, model: str) -> None:
    document = _parse_config_document(
        CONFIG_PATH, _read_config_text(CONFIG_PATH)
    )
    target = next(
        (
            seat
            for seat in document.get("seats", [])
            if seat.get("name") == seat_name
        ),
        None,
    )
    if target is None:
        raise ValueError("seat is missing from persisted configuration")
    target["model"] = model
    atomic_write_json(CONFIG_PATH, document)


def persist_seat_thesis(seat_name: str, thesis: str) -> None:
    document = _parse_config_document(
        CONFIG_PATH, _read_config_text(CONFIG_PATH)
    )
    target = next(
        (
            seat
            for seat in document.get("seats", [])
            if seat.get("name") == seat_name
        ),
        None,
    )
    if target is None:
        raise ValueError("seat is missing from persisted configuration")
    target["thesis"] = thesis
    atomic_write_json(CONFIG_PATH, document)


def other_names(seat: dict) -> str:
    return " and ".join(
        candidate["name"] for candidate in SEATS if candidate["name"] != seat["name"]
    )


def system_prompt(seat: dict) -> str:
    thesis = str(seat.get("thesis", "")).strip()
    thesis_block = (
        f"Your thesis (durable; a tactical move may change every turn but "
        f"your thesis normally may not -- you may concede a subsidiary "
        f"point without abandoning it): {thesis}\n"
        if thesis
        else ""
    )
    return (
        f"You are {seat['name']}, one of {len(SEATS)} panelists at a live debate "
        f"table. The other panelist(s): {other_names(seat)}.\n"
        f"Your persona: {seat['persona']}\n"
        f"{thesis_block}"
        "Address other panelists directly by name when engaging them, but never "
        "in sentence 1. Use 4 to 8 sentences of "
        "plain prose with no lists, headings, stage directions, or meta-commentary. "
        "Engage a specific prior point and advance the discussion. Stay in character.\n"
        f"{prompt_contract.contract_instructions(TURN_WORD_MIN, TURN_WORD_MAX)}\n"
        "The user message below has two sections. PRIVATE CONTROL is an "
        "instruction to you, never dialogue: never quote, paraphrase, or "
        "restate a control label or its text. PUBLIC CONTEXT is background "
        "only. Output nothing but your own spoken contribution -- begin "
        "directly with public speech, with no label, heading, or prefix of "
        "any kind."
    )


PROMPT_BUDGET_MARGIN_TOKENS = 64
_NEWEST_TRANSCRIPT_TURNS = 4


def _apply_prompt_budget(sections: list[tuple[int, str, list[str]]], budget_tokens: int):
    """S18.2: drop lowest-priority material first; record every decision.

    sections: (priority, key, lines) with LOWER priority = more protected.
    Returns (kept_sections, decisions).
    """
    decisions = {
        "budget_tokens": budget_tokens,
        "estimated_tokens": sum(
            mcap.estimate_tokens("\n".join(lines)) for _p, _k, lines in sections
        ),
        "dropped": [],
        "truncated_older_transcript_turns": 0,
    }

    def total():
        return sum(mcap.estimate_tokens("\n".join(lines)) for _p, _k, lines in sections)

    # S18.2 ladder: shed OLDEST individual turns from the older-transcript
    # block (priority 9) first - truncation beats wholesale loss; then drop
    # whole sections from least to most important; never touch priorities
    # below 6 (core control, topic, operator note).
    while total() > budget_tokens:
        older = next((s for s in sections if s[1] == "transcript_older"), None)
        if older is not None and older[2]:
            sections.remove(older)
            decisions["truncated_older_transcript_turns"] += 1
            remaining_lines = older[2][1:]
            if remaining_lines:
                sections.insert(
                    len(sections),
                    (older[0], older[1], remaining_lines),
                )
                sections.sort(key=lambda s: (s[0], s[1]))
            continue

        droppable = [s for s in sections if s[0] >= 6]
        if not droppable:
            break
        victim = max(droppable, key=lambda s: s[0])
        sections.remove(victim)
        decisions["dropped"].append(victim[1])

    decisions["estimated_tokens"] = total()
    kept_lines = [line for _p, _k, lines in sections for line in lines]
    return kept_lines, decisions


def build_prompt_sections(
    seat: dict,
    move_text: str,
    interject: str | None,
    recent_arguments: list[str] | None,
) -> list[tuple[int, str, list[str]]]:
    """Priority ladder per S18.2 (lower number = protected first)."""
    core = [
        "PRIVATE CONTROL (instruction only -- never quote, paraphrase, or "
        "restate any label or text in this section; it is not dialogue):",
        f"{LABEL_MOVE} {move_text}",
    ]
    sections: list[tuple[int, str, list[str]]] = [
        (0, "core", core),
        (2, "topic", [f"{LABEL_TOPIC} {state.topic}"]),
    ]
    if interject:
        sections.append((4, "operator_note", [f"{LABEL_OPERATOR_NOTE} {interject}"]))
    public_header = [
        "",
        "PUBLIC CONTEXT (background for your response; do not restate these "
        "labels):",
    ]
    window = state.transcript[-CONTEXT_TURNS:]
    split_at = max(len(window) - _NEWEST_TRANSCRIPT_TURNS, 0)
    older_turns, newest_turns = window[:split_at], window[split_at:]
    transcript_block = []
    if state.transcript:
        transcript_block += ["", LABEL_TRANSCRIPT]
        transcript_block.extend(f"{t['name']}: {t['text']}" for t in newest_turns)
    else:
        transcript_block += ["", "The table is silent. Open the discussion."]
    sections.append((6, "transcript_newest", list(public_header) + transcript_block))
    if older_turns:
        sections.append(
            (
                9,
                "transcript_older",
                [f"{t['name']}: {t['text']}" for t in older_turns],
            )
        )
    if state.anchor:
        sections.append((7, "anchor", ["", LABEL_ANCHOR, state.anchor]))
    if recent_arguments:
        sections.append(
            (
                8,
                "recent_arguments",
                [
                    "",
                    f"{LABEL_RECENT_ARGUMENTS} {'; '.join(recent_arguments)} "
                    "-- do not reuse these unless directly rebutting a new challenge.",
                ],
            )
        )
    sections.sort(key=lambda s: (s[0], s[1]))
    return sections


def turn_prompt(
    seat: dict,
    move_text: str,
    interject: str | None,
    recent_arguments: list[str] | None = None,
    budget_tokens: int | None = None,
    budget_decisions_out: dict | None = None,
) -> str:
    sections = build_prompt_sections(seat, move_text, interject, recent_arguments)
    if budget_tokens is not None:
        kept, decisions = _apply_prompt_budget(sections, budget_tokens)
        if budget_decisions_out is not None:
            budget_decisions_out.update(decisions)
    else:
        kept = [line for _p, _k, lines in sections for line in lines]
    kept.append("")
    kept.append(f"Speak now as {seat['name']}. Begin directly with your public speech.")
    return "\n".join(kept)


def turn_prompt_dynamic_values(move_text: str, interject: str | None) -> list[str]:
    """The per-turn control values that must also be blocked if a model
    echoes them verbatim without their label (see debate/output_guard.py)."""
    values = [move_text]
    if interject:
        values.append(interject)
    return values


def _weighted_choice(weights: dict[str, float]) -> str:
    total = sum(weights.values())
    point = random.uniform(0, total)
    for key, weight in weights.items():
        point -= weight
        if point <= 0:
            return key
    return next(reversed(weights))


def pick_move(seat: dict, turn_id: int) -> tuple[str, str, str]:
    pending = state.pending_questions.get(seat["name"])
    if pending:
        source = pending.popleft()
        key = "answer-then-advance"
        reason = f"directed_question_from:{source}"
    elif seat["name"] in state.pending_reframe:
        concept = state.pending_reframe.pop(seat["name"])
        key = "reframe"
        reason = f"repeated_argument:{concept}"
    elif seat["name"] in state.repetition_pending:
        overlap = state.repetition_pending.pop(seat["name"])
        key = "challenge" if state.repetition_alternator else "reframe"
        state.repetition_alternator = not state.repetition_alternator
        reason = f"self_repetition_overlap:{overlap:.2f}"
    else:
        window = int(CONFIG["consensus_window_turns"])
        consensus = (
            len(state.recent_turns) >= window
            and not disagreement_present(list(state.recent_turns)[-window:])
        )
        weights = dict(MOVE_WEIGHTS)
        if consensus:
            multiplier = float(CONFIG["consensus_challenge_weight"])
            weights["challenge"] *= multiplier
            weights["cross-examine"] *= multiplier
            reason = f"consensus_breaker:no_disagreement_in_{window}_turns"
        else:
            reason = "weighted_fallback"
        if state.last_move in weights and len(weights) > 1:
            weights.pop(state.last_move)
        key = _weighted_choice(weights)
    state.last_move = key
    state.last_move_reason = reason
    state.last_move_turn = turn_id
    return key, MOVE_TEXT[key], reason


async def generate_topic(seed: str) -> str:
    first, second = random.sample(TOPIC_DOMAINS, 2)
    prompt = (
        "Return one provocative debate question under 25 words, and nothing else. "
        f"Combine {first} with {second}. Avoid factual lookup."
        + (f" Avoid resembling: {seed}" if seed else "")
    )
    try:
        output = await ollama_chat(
            SEATS[0]["model"],
            [{"role": "user", "content": prompt}],
            interruptible=True,
        )
        output = output.splitlines()[0].strip().strip('"')
        if 10 <= len(output) <= 300:
            return output
    except TurnInterrupted:
        raise
    except Exception:
        await hub.send({"type": "status", "text": "Topic generator unavailable; using fallback."})
    choices = [topic for topic in FALLBACK_TOPICS if topic != seed]
    return random.choice(choices or FALLBACK_TOPICS)


async def set_topic(brief: str, title: str | None = None):
    """`brief` is the debate_brief (drawer + model prompt context). `title`
    is the public_title (stage caption); a bare call (title=None) sets
    both to `brief`, so old callers and old clients keep working (§6)."""
    if title is None:
        title = brief
    state.topic = brief
    state.public_title = title
    state.topic_epoch += 1
    state.turn = 0
    state.anchor = ""
    state.transcript = []
    state.speaker_idx = 0
    state.reset_debate_state()
    argument_memory_tracker.reset()
    if insight_manager:
        await insight_manager.reset()
    await hub.send({"type": "topic", "text": title})
    await hub.send({"type": "brief", "text": brief})


async def refresh_anchor():
    conversation = "\n".join(
        f"{turn['name']}: {turn['text']}"
        for turn in state.transcript[-CONTEXT_TURNS:]
    )
    prompt = (
        "Write a compact continuity anchor using only claims actually made.\n"
        f"TOPIC: {state.topic}\nRECENT TRANSCRIPT:\n{conversation}"
    )
    try:
        state.anchor = await ollama_chat(
            SEATS[0]["model"],
            [{"role": "user", "content": prompt}],
            interruptible=True,
        )
        await hub.send({"type": "anchor", "text": state.anchor})
    except TurnInterrupted:
        raise
    except Exception:
        await hub.send({"type": "status", "text": "Continuity refresh unavailable."})


class InsightManager:
    """One bounded, preemptible heuristic extractor worker."""

    def __init__(self, queue_max: int, timeout: float, extractor_model: str):
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=queue_max)
        self.timeout = timeout
        self.extractor_model = extractor_model
        self.worker_task: asyncio.Task | None = None
        self.active_task: asyncio.Task | None = None
        self.installed: bool | None = None
        self.installed_checked_at: float = 0.0
        # S16.6 instrumentation
        self.counters = {
            "queued": 0,
            "completed": 0,
            "cancelled": 0,
            "dropped": 0,
            "unavailable": 0,
        }

    def start(self):
        if not self.worker_task:
            self.worker_task = asyncio.create_task(self._worker(), name="insight-worker")

    async def stop(self):
        await self.preempt()
        if self.worker_task:
            self.worker_task.cancel()
            await asyncio.gather(self.worker_task, return_exceptions=True)
            self.worker_task = None

    async def reset(self):
        await self.preempt()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.counters["dropped"] += 1
            except asyncio.QueueEmpty:
                break
        await hub.send({"type": "insight_reset", "heuristic": True})

    async def preempt(self):
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            await asyncio.gather(self.active_task, return_exceptions=True)
            self.counters["cancelled"] += 1
        self.active_task = None

    def enqueue(self, job: dict):
        if not job.get("text"):
            return
        if self.queue.full():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.counters["dropped"] += 1
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(job)
        self.counters["queued"] += 1

    def stats(self) -> dict:
        return {
            **self.counters,
            "extractor_model_installed": self.installed,
            "queue_depth": self.queue.qsize(),
        }

    async def _worker(self):
        while True:
            job = await self.queue.get()
            try:
                if job["topic_epoch"] != state.topic_epoch or state.generation_active:
                    continue
                self.active_task = asyncio.create_task(self._extract(job))
                try:
                    await self.active_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self.active_task = None
            finally:
                self.queue.task_done()

    async def _extract(self, job: dict):
        now = time.monotonic()
        if self.installed is None or (now - self.installed_checked_at) >= INSIGHT_INSTALLED_TTL_S:
            # S16.6: availability is never permanently cached; a transient
            # Ollama failure recovers after the TTL window.
            try:
                self.installed = self.extractor_model in await installed_models()
            except Exception:
                self.installed = False
            self.installed_checked_at = now
        if not self.installed:
            await self._unavailable(job)
            return
        names = ", ".join(seat["name"] for seat in SEATS)
        prompt = (
            "Heuristically extract the public statement below. Return one JSON object "
            'with keys "stance" (short string), "addressed_seat" (participant name or '
            'empty string), "claims" (array of 1-3 short strings), and "question" '
            "(short string or empty string). Do not infer hidden thoughts.\n"
            f"Participants: {names}\nPublic statement:\n{job['text']}"
        )
        try:
            output = await asyncio.wait_for(
                ollama_chat(
                    self.extractor_model,
                    [{"role": "user", "content": prompt}],
                ),
                timeout=self.timeout,
            )
            match = re.search(r"\{.*\}", output, re.S)
            parsed = json.loads(match.group(0) if match else output)
            claims = parsed.get("claims", [])
            if not isinstance(claims, list):
                claims = []
            self.counters["completed"] += 1
            event = {
                "type": "insight",
                "heuristic": True,
                "status": "complete",
                "seat": job["seat"],
                "turn": job["turn"],
                "stance": str(parsed.get("stance", ""))[:300] or "—",
                "addressed_seat": str(parsed.get("addressed_seat", ""))[:100] or "—",
                "claims": [str(item)[:300] for item in claims[:3]] or ["—"],
                "question": str(parsed.get("question", ""))[:300] or "—",
            }
            if job["topic_epoch"] == state.topic_epoch:
                await hub.send(event)
        except (asyncio.TimeoutError, httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
            await self._unavailable(job)

    async def _unavailable(self, job: dict):
        self.counters["unavailable"] += 1
        if job["topic_epoch"] == state.topic_epoch:
            await hub.send(
                {
                    "type": "insight",
                    "heuristic": True,
                    "status": "unavailable",
                    "seat": job["seat"],
                    "turn": job["turn"],
                    "stance": "—",
                    "addressed_seat": "—",
                    "claims": ["—"],
                    "question": "—",
                }
            )


insight_manager: InsightManager | None = None
if CONFIG["insight_panel"]:
    insight_manager = InsightManager(
        int(CONFIG["insight_queue_max"]),
        float(CONFIG["insight_timeout_seconds"]),
        CONFIG["extractor_model"],
    )


def _account_turn_outcome(outcome) -> None:
    """Single site for turn accounting (P0-15/P0-19)."""
    state.attempted_turns += 1
    if outcome is tc.TurnOutcome.COMPLETED:
        state.completed_public_turns += 1
        state.completed_turns += 1
    else:
        state.skipped_turns += 1


async def _emit_skip_turn(seat_name, turn_number, model, reason, attempt_metrics):
    log_event(
        "turn_skipped",
        topic_epoch=state.topic_epoch,
        turn=turn_number,
        seat=seat_name,
        model=model,
        outcome=reason,
    )
    await hub.send(
        {
            "type": "turn_skipped",
            "seat": seat_name,
            "turn": turn_number,
            "reason": reason,
        }
    )
    await hub.send(
        {"type": "turn_end", "seat": seat_name, "turn": turn_number, "text": ""}
    )
    await hub.send(
        {
            "type": "turn_metrics",
            "seat": seat_name,
            "turn": turn_number,
            "model": model,
            "attempts": attempt_metrics,
            "public_empty": True,
        }
    )


async def run_turn(seat: dict, turn_number: int):
    model = seat["model"]
    state.interrupt_generation.clear()
    state.generation_active = True
    if insight_manager:
        await insight_manager.preempt()
    move_key, move_text, move_reason = pick_move(seat, turn_number)
    interject, state.interject = state.interject, None
    await hub.send(
        {
            "type": "turn_start",
            "seat": seat["name"],
            "turn": turn_number,
            "move": move_key,
            "move_reason": move_reason,
            "model": model,
            "interjection": bool(interject),
        }
    )
    recent_arguments = argument_memory_tracker.recent(seat["name"])
    capabilities = await mcap.registry.get_or_load(
        model,
        int(CONFIG["num_predict"]),
        await _capability_client_factory(),
    )
    budget_tokens = max(
        512,
        capabilities.safe_context
        - int(CONFIG["num_predict"])
        - PROMPT_BUDGET_MARGIN_TOKENS,
    )
    budget_decisions: dict = {"model": model}
    user_content = turn_prompt(
        seat,
        move_text,
        interject,
        recent_arguments,
        budget_tokens=budget_tokens,
        budget_decisions_out=budget_decisions,
    )
    if budget_decisions.get("dropped") or budget_decisions.get(
        "truncated_older_transcript_turns"
    ):
        log_event(
            "prompt_budget_applied",
            topic_epoch=state.topic_epoch,
            seat=seat["name"],
            model=model,
            dropped=budget_decisions.get("dropped"),
            truncated_older_turns=budget_decisions.get(
                "truncated_older_transcript_turns"
            ),
            estimated_tokens=budget_decisions.get("estimated_tokens"),
            budget_tokens=budget_tokens,
        )
    messages = [
        {"role": "system", "content": system_prompt(seat)},
        {"role": "user", "content": user_content},
    ]
    dynamic_values = turn_prompt_dynamic_values(move_text, interject)

    text = ""
    attempt_metrics = []
    max_attempts = 1 + int(CONFIG["empty_spoken_retry_count"])
    for attempt in range(max_attempts):
        one_attempt = {
            "attempt": attempt + 1,
            "first_sentence_seconds": None,
            "prompt_budget": budget_decisions,
        }
        attempt_metrics.append(one_attempt)

        guard = OutputGuard(TURN_PROMPT_LABELS, dynamic_values)
        buffer = SentenceBuffer(guard)
        emitted_sentences: list[str] = []
        spoke = False
        attempt_started = time.perf_counter()

        async def emit_sentence(sentence: str):
            emitted_sentences.append(sentence)
            if one_attempt["first_sentence_seconds"] is None:
                one_attempt["first_sentence_seconds"] = (
                    time.perf_counter() - attempt_started
                )
            await hub.send({"type": "token", "seat": seat["name"], "text": sentence})

        async def emit_blocked(labels: list[str]):
            for label in labels:
                await hub.send(
                    {
                        "type": "diagnostic",
                        "kind": "CONTROL_TEXT_LEAK_BLOCKED",
                        "seat": seat["name"],
                        "turn": turn_number,
                        "model": model,
                        "label": label,
                    }
                )

        async def on_public(fragment: str):
            nonlocal spoke
            if not fragment:
                return
            if not spoke:
                spoke = True
                await hub.send(
                    {"type": "speaking", "seat": seat["name"], "turn": turn_number}
                )
            sentences, blocked = buffer.feed(fragment)
            await emit_blocked(blocked)
            for sentence in sentences:
                await emit_sentence(sentence)

        try:
            await ollama_chat(
                model,
                messages,
                on_public=on_public,
                interruptible=True,
                metrics=one_attempt,
            )
        except TurnInterrupted:
            raise
        except (StreamProtocolError, StreamIncomplete) as exc:
            state.generation_active = False
            one_attempt["error_type"] = type(exc).__name__
            reason = (
                "protocol_error"
                if isinstance(exc, StreamProtocolError)
                else "protocol_incomplete"
            )
            await hub.send(
                {
                    "type": "status",
                    "text": f"{seat['name']}: stream protocol fault; turn skipped.",
                }
            )
            await _emit_skip_turn(
                seat["name"], turn_number, model, reason, attempt_metrics
            )
            return (
                tc.TurnOutcome.PROTOCOL_ERROR
                if isinstance(exc, StreamProtocolError)
                else tc.TurnOutcome.PROTOCOL_INCOMPLETE
            )
        except Exception as exc:
            state.generation_active = False
            one_attempt["error_type"] = type(exc).__name__
            await hub.send(
                {
                    "type": "status",
                    "text": f"{seat['name']}: response unavailable; turn skipped.",
                }
            )
            await _emit_skip_turn(
                seat["name"], turn_number, model, "generation_error", attempt_metrics
            )
            return tc.TurnOutcome.SKIPPED_GENERATION_ERROR

        finish_sentences, tail, finish_blocked = buffer.finish()
        await emit_blocked(finish_blocked)
        for sentence in finish_sentences:
            await emit_sentence(sentence)

        joined_so_far = " ".join(s.strip() for s in emitted_sentences if s.strip())
        classify_text = (joined_so_far + (" " + tail if tail else "")).strip()
        completion_state, signals, confident = tc.classify(
            text=classify_text,
            budget_exhausted=bool(one_attempt.get("budget_exhausted")),
            hidden_reasoning_present=bool(one_attempt.get("hidden_reasoning_present")),
        )
        one_attempt["completion_state"] = completion_state
        one_attempt["completion_signals"] = signals

        if tail:
            if completion_state == tc.TURN_TRUNCATED_BY_BUDGET and confident:
                continuation_messages = messages + [
                    {"role": "assistant", "content": classify_text},
                    {
                        "role": "user",
                        "content": (
                            "Your previous message was cut off mid-sentence by a "
                            "length limit. Complete only that single unfinished "
                            "sentence, in 35 words or fewer. Output only the "
                            "missing words -- no new sentence, no new argument, "
                            "no restatement."
                        ),
                    },
                ]
                continuation_metrics = {"attempt": "continuation"}
                try:
                    continuation_text = await ollama_chat(
                        model, continuation_messages, metrics=continuation_metrics
                    )
                except Exception:
                    continuation_text = ""
                continuation_text = tc.bound_continuation(continuation_text)
                one_attempt["continuation_metrics"] = continuation_metrics
                if continuation_text.strip():
                    merged = tc.merge_continuation(tail, continuation_text)
                    one_attempt["continuation_overlap_trimmed"] = (
                        len(f"{tail.rstrip()} {continuation_text.strip()}".strip())
                        - len(merged)
                    )
                    await emit_sentence(merged)
                    one_attempt["continuation_applied"] = True
                else:
                    await emit_sentence(tail)
                    one_attempt["continuation_applied"] = False
            else:
                await emit_sentence(tail)

        text = " ".join(s.strip() for s in emitted_sentences if s.strip())

        # Make the turn contract measurable rather than aspirational (v1.1
        # targeted 110-160 words and shipped a measured mean of 188 / max 305,
        # unrecorded). Diagnostic only: speech is never rejected or rewritten.
        word_count, word_status = prompt_contract.word_count_status(
            text, TURN_WORD_MIN, TURN_WORD_MAX
        )
        one_attempt["word_count"] = word_count
        one_attempt["word_contract"] = word_status
        opener = prompt_contract.opens_with_agreement(text)
        if opener:
            one_attempt["agreement_opener"] = opener

        # Opening-move constraint (v1.1 closeout): sentence 1 must not
        # name, second-person-address, or opponent-validate. Diagnostic
        # only -- never used to reject or rewrite speech.
        opponent_names = [
            candidate["name"] for candidate in SEATS if candidate["name"] != seat["name"]
        ]
        opening_violation = prompt_contract.opening_move_violation(text, opponent_names)
        if opening_violation:
            one_attempt["opening_violation"] = opening_violation

        if text:
            break
        if attempt + 1 < max_attempts:
            await hub.send(
                {
                    "type": "status",
                    "text": f"{seat['name']}: retrying empty public response.",
                }
            )
            messages[1]["content"] += (
                "\n\nYour prior attempt contained no public speech. Respond now with "
                "plain public prose and no hidden reasoning."
            )
    state.generation_active = False
    if not text:
        await hub.send(
            {
                "type": "status",
                "text": f"{seat['name']}: empty public response; turn skipped.",
            }
        )
        await _emit_skip_turn(
            seat["name"], turn_number, model, "empty_public_response", attempt_metrics
        )
        return tc.TurnOutcome.SKIPPED_EMPTY_PUBLIC

    state.transcript.append({"name": seat["name"], "text": text})
    state.transcript = state.transcript[-40:]
    state.observe_public_turn(seat["name"], text)
    repeated_concept = argument_memory_tracker.check_and_record(seat["name"], text)
    if repeated_concept:
        state.pending_reframe[seat["name"]] = repeated_concept
    await hub.send(
        {
            "type": "turn_end",
            "seat": seat["name"],
            "turn": turn_number,
            "text": text,
        }
    )
    await hub.send(
        {
            "type": "turn_metrics",
            "seat": seat["name"],
            "turn": turn_number,
            "model": model,
            "attempts": attempt_metrics,
            "public_empty": False,
        }
    )
    final_attempt = attempt_metrics[-1] if attempt_metrics else {}
    log_event(
        "turn_completed",
        topic_epoch=state.topic_epoch,
        turn=turn_number,
        seat=seat["name"],
        model=model,
        outcome=tc.TurnOutcome.COMPLETED.value,
        completion_state=final_attempt.get("completion_state"),
        ttft_seconds=final_attempt.get("first_public_seconds"),
        duration_seconds=final_attempt.get("duration_seconds"),
        word_count=final_attempt.get("word_count"),
    )
    return tc.TurnOutcome.COMPLETED
    if insight_manager:
        insight_manager.enqueue(
            {
                "seat": seat["name"],
                "turn": turn_number,
                "text": text,
                "topic_epoch": state.topic_epoch,
                "queued_at": time.monotonic(),
            }
        )


async def orchestrator():
    state.status = "generating first topic"
    await hub.send({"type": "status", "text": "generating first topic"})
    try:
        first_topic = await generate_topic("")
    except TurnInterrupted:
        # A pause/cancel racing the very first topic must not kill the loop.
        first_topic = random.choice(FALLBACK_TOPICS)
    await set_topic(first_topic)
    state.status = "live"
    while not state.shutting_down:
        try:
            if state.paused:
                await asyncio.sleep(0.3)
                continue
            if state.pending_topic:
                payload, state.pending_topic = state.pending_topic, None
                await set_topic(payload["debate_brief"], payload["public_title"])
            if TOPIC_ROTATE_TURNS > 0 and state.completed_turns >= TOPIC_ROTATE_TURNS:
                await hub.send({"type": "status", "text": "rotating topic"})
                await set_topic(await generate_topic(state.topic))
            # A pause can arrive while a non-streaming topic generation call is
            # in flight. Re-check before selecting a seat so the completed topic
            # may publish, but no debate turn starts until resume.
            if state.paused:
                continue
            seat = SEATS[state.speaker_idx % len(SEATS)]
            next_turn = state.turn + 1
            outcome = await run_turn(seat, next_turn)
            _account_turn_outcome(outcome)
            state.turn = next_turn
            if outcome is tc.TurnOutcome.COMPLETED:
                # Microphone always rotates so one broken seat cannot stall the
                # table; only COMPLETED advances completed counters/cadence.
                state.speaker_idx += 1
            else:
                state.speaker_idx += 1
            if (
                ANCHOR_EVERY_TURNS > 0
                and state.completed_turns > 0
                and state.completed_turns % ANCHOR_EVERY_TURNS == 0
            ):
                await refresh_anchor()
            await asyncio.sleep(TURN_DELAY_S)
        except TurnInterrupted:
            state.generation_active = False
            log_event(
                "turn_interrupted",
                topic_epoch=state.topic_epoch,
                turn=state.turn + 1,
                seat=SEATS[state.speaker_idx % len(SEATS)]["name"]
                if SEATS
                else None,
                outcome="interrupted",
            )
            state.attempted_turns += 1
            state.skipped_turns += 1
            if state.shutting_down:
                break
            await hub.send(
                {
                    "type": "turn_skipped",
                    "seat": seat["name"],
                    "turn": next_turn,
                    "reason": "operator_interruption",
                }
            )
            await hub.send(
                {
                    "type": "turn_end",
                    "seat": seat["name"],
                    "turn": next_turn,
                    "text": "",
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            state.generation_active = False
            await hub.send(
                {"type": "status", "text": "Turn unavailable; continuing debate."}
            )
            await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _http_client
    state.shutting_down = False
    _http_client = httpx.AsyncClient(timeout=CHAT_HTTP_TIMEOUT)
    if insight_manager:
        insight_manager.start()
    log_event("app_lifespan_start", version=_BUILD_VERSION)
    task = asyncio.create_task(orchestrator(), name="debate-orchestrator")
    try:
        yield
    finally:
        state.shutting_down = True
        state.interrupt_generation.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if insight_manager:
            await insight_manager.stop()
        await close_http_client()
        log_event("app_lifespan_shutdown")


app = FastAPI(title="Debate Table", lifespan=lifespan)
app.add_middleware(LoopbackControlPlaneGuard, config=CONFIG)


class TextIn(BaseModel):
    text: str


class SeatModelIn(BaseModel):
    seat: str
    model: str


class BriefIn(BaseModel):
    public_title: str
    debate_brief: str


class SeatThesisIn(BaseModel):
    seat: str
    thesis: str
    reason: str = ""


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        models = await installed_models()
    except Exception:
        models = []
    await ws.send_text(
        json.dumps(
            {
                "type": "snapshot",
                "seats": public_seats(),
                "models": models,
                "topic": state.public_title,
                "public_title": state.public_title,
                "debate_brief": state.topic,
                "public_title_max_chars": PUBLIC_TITLE_MAX_CHARS,
                "debate_brief_max_chars": DEBATE_BRIEF_MAX_CHARS,
                "input_limits": dict(INPUT_LIMITS),
                "seat_theses": {seat["name"]: seat.get("thesis", "") for seat in SEATS},
                "transcript": state.transcript[-CONTEXT_TURNS:],
                "paused": state.paused,
                "status": state.status,
                "insight_enabled": bool(insight_manager),
                "diagnostics": {
                    "inference_backend": "llama.cpp" if LLAMACPP_ACTIVE else "ollama",
                    "inference_endpoint_class": OLLAMA_ENDPOINT_CLASS,
                    "move": state.last_move,
                    "move_reason": state.last_move_reason,
                    "turn": state.last_move_turn,
                },
            },
            ensure_ascii=False,
        )
    )
    conn = hub.register(ws)
    conn.sender_task = asyncio.create_task(
        hub._sender(conn), name=f"ws-sender-{id(ws):x}"
    )
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        hub.unregister(conn)
        if conn.sender_task:
            await asyncio.gather(conn.sender_task, return_exceptions=True)


@app.get("/health")
async def health():
    """Lightweight process health (P1): liveness only, no dependency probes."""
    return JSONResponse(
        {
            "status": "ok",
            "version": _BUILD_VERSION,
            "uptime_seconds": round(time.monotonic() - _STARTED_MONOTONIC, 3),
            "config_loaded": CONFIG is not None,
            "generation_active": bool(state.generation_active),
        }
    )


@app.get("/ready")
async def ready():
    """Dependency readiness (P1). Never exposes prompts or interjections."""
    try:
        records = await installed_model_records()
        models = sorted(records)
        reachable = True
        error_type = None
    except Exception as exc:
        reachable = False
        error_type = type(exc).__name__
        records = {}
        models = []

    seat_rows = []
    for seat in SEATS:
        caps = mcap.registry._cache.get(seat["model"])
        installed = (seat["model"] in models) if reachable else False
        # The operator's 8B ceiling, per seat, REPORTED rather than silently applied (S-19 /
        # ENTRY 017). A seat configured above the ceiling is a real state this table can be in, and
        # the operator has to be able to see which seat it is and why it cannot run - the same rule
        # the SOW picker follows when it greys a model instead of hiding it.
        verdict = (ceiling_verdict(records[seat["model"]])
                   if installed else {"within_ceiling": None, "parameter_size": None,
                                      "reason": None})
        seat_rows.append(
            {
                "name": seat["name"],
                "model": seat["model"],
                "installed": installed,
                "context_window": caps.context_window if caps else None,
                "qualification": caps.qualification if caps else None,
                "parameter_size": verdict["parameter_size"],
                "within_ceiling": verdict["within_ceiling"],
                "ceiling_reason": verdict["reason"],
            }
        )
    missing = [row["model"] for row in seat_rows if not row["installed"]]
    over_ceiling = [row["model"] for row in seat_rows if row["within_ceiling"] is False]
    extractor_row = None
    if CONFIG.get("insight_panel") and CONFIG.get("extractor_model"):
        extractor_model = CONFIG["extractor_model"]
        installed = extractor_model in models if reachable else False
        extractor_row = {"role": "extractor", "model": extractor_model, "installed": installed}
        if not installed:
            missing.append(extractor_model)

    if not reachable:
        status = "unavailable"
    elif missing or over_ceiling:
        # An over-ceiling seat degrades the table exactly as a missing one does: in both cases a
        # configured seat cannot take its turn, and reporting "ready" would be the silent-absence
        # defect wearing a green badge.
        status = "degraded"
    else:
        status = "ready"

    payload = {
        "status": status,
        "model_service": {
            "backend": "llama.cpp" if LLAMACPP_ACTIVE else "ollama",
            "base_url": OLLAMA,
            "reachable": reachable,
            "endpoint_class": OLLAMA_ENDPOINT_CLASS,
            "error_type": error_type,
        },
        "seats": seat_rows,
        "missing_models": sorted(set(missing)),
        "over_ceiling_models": sorted(set(over_ceiling)),
        "local_model_ceiling": {
            "nameplate_b": CEILING_NAMEPLATE_B,
            "authority": "OPERATOR-INSTRUCTIONS.log ENTRY 017",
        },
        "orchestrator": {
            "state": state.status,
            "paused": bool(state.paused),
            "topic_epoch": state.topic_epoch,
            "completed_public_turns": state.completed_public_turns,
            "skipped_turns": state.skipped_turns,
        },
        "http_client_active": _http_client is not None,
    }
    if extractor_row is not None:
        payload["extractor"] = extractor_row
    if insight_manager is not None:
        payload["insight"] = insight_manager.stats()
    return JSONResponse(payload, status_code=200 if status == "ready" else 503)


@app.get("/api/models")
async def api_models():
    try:
        return JSONResponse({"models": await installed_models()})
    except Exception:
        return JSONResponse({"error": "Ollama unavailable"}, status_code=502)


@app.post("/api/seat_model")
async def api_seat_model(body: SeatModelIn):
    body.model = body.model.strip()
    if not body.model or len(body.model) > INPUT_LIMITS["model_name"]:
        return JSONResponse({"error": "invalid model name"}, status_code=400)
    seat = next((item for item in SEATS if item["name"] == body.seat), None)
    if seat is None:
        return JSONResponse({"error": "unknown seat"}, status_code=400)
    try:
        models = await installed_models()
    except Exception:
        return JSONResponse(
            {"error": "could not validate installed models"}, status_code=502
        )
    if body.model not in models:
        return JSONResponse({"error": "model is not installed"}, status_code=400)
    async with seat_mutation_lock:
        try:
            persist_seat_model(body.seat, body.model)
        except Exception:
            return JSONResponse({"error": "configuration write failed"}, status_code=500)
        seat["model"] = body.model
        CONFIG["seats"] = SEATS
    await hub.send({"type": "seats", "seats": public_seats()})
    return JSONResponse({"ok": True})


@app.post("/api/topic")
async def api_topic(body: TextIn):
    topic = body.text.strip()
    if not topic:
        return JSONResponse({"error": "topic is empty"}, status_code=400)
    if len(topic) > PUBLIC_TITLE_MAX_CHARS:
        return JSONResponse(
            {
                "error": (
                    f"topic exceeds {PUBLIC_TITLE_MAX_CHARS} characters; use "
                    "/api/brief to set a longer debate_brief with a shorter "
                    "public_title"
                )
            },
            status_code=400,
        )
    state.pending_topic = {"public_title": topic, "debate_brief": topic}
    state.interrupt_generation.set()
    return JSONResponse({"ok": True})


@app.post("/api/brief")
async def api_brief(body: BriefIn):
    title = body.public_title.strip()
    brief = body.debate_brief.strip()
    if not title or not brief:
        return JSONResponse(
            {"error": "public_title and debate_brief are both required"},
            status_code=400,
        )
    if len(title) > PUBLIC_TITLE_MAX_CHARS:
        return JSONResponse(
            {"error": f"public_title exceeds {PUBLIC_TITLE_MAX_CHARS} characters"},
            status_code=400,
        )
    if len(brief) > DEBATE_BRIEF_MAX_CHARS:
        return JSONResponse(
            {"error": f"debate_brief exceeds {DEBATE_BRIEF_MAX_CHARS} characters"},
            status_code=400,
        )
    state.pending_topic = {"public_title": title, "debate_brief": brief}
    state.interrupt_generation.set()
    return JSONResponse({"ok": True})


@app.post("/api/seat_thesis")
async def api_seat_thesis(body: SeatThesisIn):
    seat = next((item for item in SEATS if item["name"] == body.seat), None)
    if seat is None:
        return JSONResponse({"error": "unknown seat"}, status_code=400)
    thesis = body.thesis.strip()
    reason = body.reason.strip()
    if not thesis:
        return JSONResponse({"error": "thesis is empty"}, status_code=400)
    if len(thesis) > INPUT_LIMITS["thesis"]:
        return JSONResponse(
            {"error": f"thesis exceeds {INPUT_LIMITS['thesis']} characters"},
            status_code=400,
        )
    if len(reason) > INPUT_LIMITS["revision_reason"]:
        return JSONResponse(
            {"error": f"revision reason exceeds {INPUT_LIMITS['revision_reason']} characters"},
            status_code=400,
        )
    previous = seat.get("thesis", "")
    async with seat_mutation_lock:
        try:
            persist_seat_thesis(body.seat, thesis)
        except Exception:
            return JSONResponse({"error": "configuration write failed"}, status_code=500)
        seat["thesis"] = thesis
        CONFIG["seats"] = SEATS
    await hub.send(
        {
            "type": "position_revision",
            "seat": body.seat,
            "previous_thesis": previous,
            "revised_thesis": thesis,
            "reason": reason or "operator_revision",
        }
    )
    return JSONResponse({"ok": True})


@app.post("/api/interject")
async def api_interject(body: TextIn):
    note = body.text.strip()
    if not note:
        return JSONResponse({"error": "interjection is empty"}, status_code=400)
    if len(note) > INPUT_LIMITS["interjection"]:
        return JSONResponse(
            {"error": f"interjection exceeds {INPUT_LIMITS['interjection']} characters"},
            status_code=400,
        )
    state.interject = note
    return JSONResponse({"ok": True})


@app.post("/api/pause")
async def api_pause():
    state.paused = True
    state.status = "paused"
    state.interrupt_generation.set()
    await hub.send({"type": "status", "text": "paused"})
    return JSONResponse({"ok": True})


@app.post("/api/resume")
async def api_resume():
    state.paused = False
    state.status = "live"
    await hub.send({"type": "status", "text": "live"})
    return JSONResponse({"ok": True})


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


if __name__ == "__main__":
    # SW-18: an explicit uvicorn.Server so the shell's graceful-shutdown Event can ask it to exit;
    # should_exit runs the normal lifespan shutdown (orchestrator stop, insight flush, http client
    # close, app_lifespan_shutdown log) before the shell's TerminateJobObject fallback would fire.
    _server = uvicorn.Server(uvicorn.Config(
        app,
        host="127.0.0.1",
        port=int(CONFIG["port"]),
        log_level="warning",
    ))
    install_shutdown_watcher(lambda: setattr(_server, "should_exit", True))
    _server.run()
