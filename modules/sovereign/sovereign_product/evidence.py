"""Bounded, content-addressed evidence packets for grounded execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Sequence


TokenCounter = Callable[[str], int]
_RELEVANCE_WORD_RE = re.compile(r"[A-Za-z0-9]+")

# Continuity ranking (Proof-5 candidate qrc1). Reverse-recency packing filled
# the packet with newer questions and limitation echoes and omitted the required
# operator source in 20 of 20 Proof-2 continuity packets. These constants drive a
# deterministic lexical ranking so an authoritative prior source is reserved
# before the recency fallback. No model call and no stored state is involved.
_IDENTIFIER_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+"  # underscored or hyphenated keys
    r"|[A-Za-z]+[0-9]+[A-Za-z0-9]*"  # letter-then-digit tokens such as sha256
    r"|[0-9]+[A-Za-z]+[A-Za-z0-9]*"  # digit-then-letter tokens such as timestamps
)
_QUESTION_OPENER_RE = re.compile(
    r"^(?:what|which|who|whom|whose|when|where|why|how|is|are|was|were|do|does|"
    r"did|can|could|will|would|shall|should|may|might|have|has|had|list|show|"
    r"tell|describe|summarize|report|recall|remind)\b"
)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+\s+|[\r\n]+")
# Deliberately small and generic. A large curated list would start encoding the
# benchmark's vocabulary, which the adversarial review forbids.
_RELEVANCE_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
        "did", "do", "does", "for", "from", "had", "has", "have", "how", "i",
        "if", "in", "into", "is", "it", "its", "me", "my", "no", "not", "of",
        "on", "or", "our", "please", "so", "that", "the", "their", "them",
        "then", "there", "these", "they", "this", "to", "was", "we", "were",
        "what", "when", "where", "which", "who", "why", "will", "with", "you",
        "your",
    }
)
_IDENTIFIER_MATCH_WEIGHT = 4.0
_PHRASE_MATCH_WEIGHT = 2.0
_TERM_MATCH_WEIGHT = 1.0
# An original operator assertion outranks the assistant's echo of it.
_ROLE_RELEVANCE_WEIGHTS = {
    "user": 1.0,
    "operator": 1.0,
    "system": 0.6,
    "sovereign": 0.25,
    "assistant": 0.25,
}
_QUESTION_RELEVANCE_WEIGHT = 0.5
# How many ranked sources may be reserved ahead of the recency fallback. Bounded
# so a long history cannot crowd out recent turns entirely.
_MAX_RESERVED_RELEVANT_MESSAGES = 4
_PRODUCT_QUERY_REFERENCE_RE = re.compile(
    r"\b(?:"
    r"sovereign|"
    r"(?:this|the|our|your|current|local|installed|running)\s+"
    r"(?:product|application|app|installation|instance|build)"
    r")\b"
)
_SELF_QUERY_REFERENCE_RE = re.compile(r"\b(?:you|your|yours)\b")
_GENERIC_STATUS_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:what\s+is|what\s+s|show|report|summarize|check|give\s+me|tell\s+me)"
    r"\s+(?:the\s+)?(?:current\s+|overall\s+|product\s+|runtime\s+|"
    r"build\s+|release\s+)?(?:status|health)"
    r"(?:\s+(?:now|right\s+now))?|"
    r"(?:is|are)\s+(?:the\s+)?(?:product\s+|runtime\s+|build\s+|service\s+)?"
    r"(?:healthy|ready|running|available|operational)"
    r")$"
)
_GENERIC_CAPABILITY_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:what|which)\s+(?:product\s+)?(?:capabilities|features|functions)"
    r"(?:\s+(?:are\s+)?(?:available|enabled|configured|supported|"
    r"implemented|included|loaded))?(?:\s+(?:here|now))?|"
    r"(?:what|which)\s+(?:capabilities|features|functions)\s+"
    r"(?:does\s+(?:it|sovereign|the\s+product)|do\s+(?:you|we))\s+have|"
    r"what\s+can\s+(?:you|sovereign|this\s+product|the\s+product|"
    r"this\s+app|the\s+app)\s+do"
    r")$"
)
_GENERIC_CONFIGURATION_QUERY_RE = re.compile(
    r"^(?:(?:show|list|describe|summarize|what\s+is|what\s+s)"
    r"\s+(?:me\s+)?(?:the\s+)?(?:current\s+|product\s+|runtime\s+)?"
    r"(?:configuration|config|settings))$"
)
_VERSION_STATE_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:what\s+is|what\s+s|which\s+is)\s+(?:the\s+)?"
    r"(?:current|installed|running|product|release|build)\s+version|"
    r"what\s+version\s+(?:is\s+(?:this|installed|running)|"
    r"are\s+you\s+running|do\s+you\s+(?:use|run|have))"
    r")(?:\s+(?:now|right\s+now))?$"
)
_VERSION_RUNTIME_STATE_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:(?:what\s+(?:is|are)|show|report|summarize|check|"
    r"give\s+me|tell\s+me)\s+(?:the\s+)?(?:current\s+)?"
    r"(?:"
    r"(?:product\s+)?version\s+(?:and|with|plus)\s+(?:the\s+)?"
    r"runtime\s+(?:health|status)|"
    r"runtime\s+(?:health|status)\s+(?:and|with|plus)\s+"
    r"(?:the\s+)?(?:product\s+)?version"
    r")(?:\s+(?:now|right\s+now))?)|"
    r"(?:(?:what|which)\s+(?:product\s+)?version\s+"
    r"(?:and|with|plus)\s+(?:the\s+)?runtime\s+(?:health|status)\s+"
    r"(?:is|are)\s+(?:observed|reported|current|available|configured))"
    r")$"
)
_RUNTIME_STATE_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:what\s+is|what\s+s|how\s+is|show|report|summarize|check)"
    r"\s+(?:the\s+)?(?:current\s+)?runtime\s+"
    r"(?:health|status|state|configuration|config|readiness)|"
    r"(?:is|are)\s+(?:the\s+)?runtime\s+"
    r"(?:healthy|ready|running|available|operational)"
    r")(?:\s+(?:now|right\s+now))?$"
)
_MODEL_OPERATION_QUERY_RES = tuple(
    re.compile(pattern)
    for pattern in (
        r"^(?:which|what)\s+(?:the\s+)?models?\s+"
        r"(?:is|are|was|were)\s+(?:currently\s+)?"
        r"(?:configured|loaded|installed|available|running|active|"
        r"selected|assigned)(?:\s+(?:and|or)\s+"
        r"(?:configured|loaded|installed|available|running|active|"
        r"selected|assigned))*$",
        r"^(?:list|show)(?:\s+me)?\s+(?:the\s+)?"
        r"(?:(?:configured|loaded|installed|available|running|active|"
        r"selected|assigned)\s+)*models?$",
        r"^(?:what|which)\s+models?\s+(?:does|do)\s+"
        r"(?:sovereign|the\s+product|this\s+product|you)\s+"
        r"(?:use|have|run|load)$",
        r"^what\s+model\s+(?:are|is)\s+"
        r"(?:you|sovereign|the\s+product|this\s+product)\s+"
        r"(?:using|running|loading)$",
    )
)
_MODE_QUERY_RE = re.compile(
    r"\b(?:"
    r"(?:what|which)\s+mode\s+(?:is|are)\s+"
    r"(?:sovereign|you|the\s+product|this\s+product|the\s+app|this\s+app)|"
    r"(?:sovereign|the\s+product|this\s+product|the\s+app|this\s+app)"
    r"(?:\s+s)?\s+(?:current\s+)?mode"
    r")\b"
)
_FAILURE_QUERY_RES = tuple(
    re.compile(pattern)
    for pattern in (
        r"^what\s+(?:has\s+)?failed\s+(?:most\s+recently|last)$",
        r"^what\s+was\s+the\s+(?:last|latest|most\s+recent)\s+"
        r"(?:failure|error)$",
        r"^(?:show|report|list)(?:\s+me)?\s+(?:the\s+)?"
        r"(?:last|latest|most\s+recent|recent)\s+"
        r"(?:failure|error|failed\s+(?:job|run|execution))$",
        r"^why\s+did\s+(?:sovereign|it|the\s+product|the\s+app|you)"
        r"\s+fail$",
    )
)
_EXPLICIT_LOCATOR_TOKEN_RE = re.compile(
    r"(?<![a-z0-9_./-])"
    r"(?:\./)?(?:[a-z0-9_.-]+/)*[a-z0-9_.-]+\.[a-z][a-z0-9]{1,15}"
    r"(?![a-z0-9_./-])",
    re.IGNORECASE,
)
_HUMANIZED_PRODUCT_LOCATOR_ALIASES = {
    "system manifest": "SYSTEM_MANIFEST.json",
    "runtime profile": "runtime_profile.json",
    "sovereign version": "sovereign_version.py",
    "constitution state": "constitution/constitution_state.json",
    "model hierarchy": "synthesis/model_hierarchy.json",
}
#: EPC-02. The constitution's own vocabulary, taken from its headings and defined terms -
#: not a general keyword list. A query using one of these words is asking about governance,
#: and the constitution is the only file that can answer it.
_CONSTITUTIONAL_QUERY_WORDS = frozenset(
    {
        "constitution",
        "constitutional",
        "praxis",
        "canonical",
        "boundaries",
        "boundary",
        "governance",
        "governs",
        "promotion",
        "promote",
        "upgrade",
        "authority",
        "synthesis",
    }
)

_KNOWN_PRODUCT_FILE_INTENTS: dict[str, frozenset[str]] = {
    "system_manifest.json": frozenset(
        {"version", "runtime", "models", "configuration", "capabilities"}
    ),
    "sovereign_version.py": frozenset({"version"}),
    "constitution/constitution_state.json": frozenset(
        {"mode", "status", "configuration"}
    ),
    "synthesis/model_hierarchy.json": frozenset(
        {"models", "configuration", "capabilities"}
    ),
    "runtime_profile.json": frozenset(
        {
            "version",
            "runtime",
            "status",
            "failure",
            "configuration",
            "capabilities",
        }
    ),
    # EPC-02, operator-authorized. The constitution is PROSE, not product state, and the
    # content classifier that handles unlisted files derives intents from words like
    # "version" and "runtime" - which this document does not use in that sense. Left to the
    # classifier it would be admitted for the wrong questions and refused for its own.
    #
    # These are the subjects it genuinely covers, taken from its own headings: canonical
    # boundaries, the Praxis Answer as the sole synthesis channel, Sovereign Voice being
    # explicitly non-canonical, and the rules governing a controlled upgrade.
    "constitution/constitution_v1.md": frozenset(
        {
            "constitution",
            "governance",
            "boundaries",
            "canonical",
            "praxis",
            "voice",
            "synthesis",
            "promotion",
            "upgrade",
            "policy",
            "authority",
            "mode",
            "status",
        }
    ),
}


class EvidenceError(RuntimeError):
    """Base error for evidence-packet construction."""


class UnapprovedEvidencePath(EvidenceError, ValueError):
    """Raised when an evidence path is absolute, escaping, or not approved."""


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    kind: str
    locator: str
    content_sha256: str
    snippet_sha256: str
    snippet: str
    content_bytes: int
    snippet_bytes: int
    snippet_tokens: int
    truncated: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EvidencePacket:
    session_id: str
    query_sha256: str
    created_at: str
    sources: tuple[EvidenceSource, ...]
    omissions: tuple[dict[str, str], ...]
    text: str
    total_bytes: int
    total_tokens: int
    max_bytes: int
    max_tokens: int
    token_count_method: str
    packet_sha256: str

    @property
    def rendered(self) -> str:
        return self.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query_sha256": self.query_sha256,
            "created_at": self.created_at,
            "sources": [asdict(source) for source in self.sources],
            "omissions": [dict(item) for item in self.omissions],
            "text": self.text,
            "total_bytes": self.total_bytes,
            "total_tokens": self.total_tokens,
            "max_bytes": self.max_bytes,
            "max_tokens": self.max_tokens,
            "token_count_method": self.token_count_method,
            "packet_sha256": self.packet_sha256,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _default_token_counter(text: str) -> int:
    # UTF-8 byte count is intentionally conservative for the local model
    # tokenizers used here and never understates a byte-oriented packet budget.
    return len(text.encode("utf-8"))


def _safe_relative_path(root: Path, value: str | Path) -> tuple[str, Path]:
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise UnapprovedEvidencePath(f"evidence path must be root-relative: {value}")
    relative = path.as_posix()
    if relative in ("", "."):
        raise UnapprovedEvidencePath("evidence path must identify a file")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnapprovedEvidencePath(f"evidence path escapes the approved root: {value}") from exc
    return relative, resolved


def _fit_text(
    text: str,
    *,
    byte_limit: int,
    token_limit: int,
    token_counter: TokenCounter,
) -> str:
    if byte_limit <= 0 or token_limit <= 0 or not text:
        return ""
    if len(text.encode("utf-8")) <= byte_limit and token_counter(text) <= token_limit:
        return text
    low = 0
    high = len(text)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate = text[:midpoint]
        if (
            len(candidate.encode("utf-8")) <= byte_limit
            and token_counter(candidate) <= token_limit
        ):
            low = midpoint
        else:
            high = midpoint - 1
    return text[:low]


class EvidenceBuilder:
    """Build a deterministic, bounded packet from approved files and messages."""

    _MESSAGE_METHODS = (
        "get_session_messages",
        "list_messages",
        "get_messages",
        "messages_for_session",
        "load_messages",
    )

    def __init__(
        self,
        root: str | Path,
        *,
        approved_paths: Iterable[str | Path] = (),
        message_source: Any | None = None,
        max_bytes: int = 16_384,
        max_tokens: int = 4_096,
        max_source_bytes: int = 4_096,
        token_counter: TokenCounter | None = None,
        query_relevance: bool = False,
        now: Callable[[], str] = _utc_now,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise EvidenceError(f"evidence root is not a directory: {self.root}")
        for name, value in (
            ("max_bytes", max_bytes),
            ("max_tokens", max_tokens),
            ("max_source_bytes", max_source_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        self.max_bytes = int(max_bytes)
        self.max_tokens = int(max_tokens)
        self.max_source_bytes = min(int(max_source_bytes), self.max_bytes)
        self.token_counter = token_counter or _default_token_counter
        self.token_count_method = (
            getattr(token_counter, "__name__", None)
            if token_counter is not None
            else "utf8_bytes_upper_bound"
        ) or "custom"
        self.message_source = message_source
        self.query_relevance = bool(query_relevance)
        self._now = now
        approved: dict[str, Path] = {}
        for configured in approved_paths:
            relative, resolved = _safe_relative_path(self.root, configured)
            approved[relative] = resolved
        self._approved_paths = approved

    @property
    def approved_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._approved_paths))

    def _messages(self, session_id: str) -> Sequence[Any]:
        source = self.message_source
        if source is None:
            return ()
        if callable(source):
            result = source(session_id)
        else:
            result = None
            for method_name in self._MESSAGE_METHODS:
                method = getattr(source, method_name, None)
                if callable(method):
                    result = method(session_id)
                    break
            if result is None:
                raise EvidenceError("message source exposes no supported message method")
        if result is None:
            return ()
        if isinstance(result, Mapping):
            candidate = result.get("messages", ())
        else:
            candidate = result
        if isinstance(candidate, (str, bytes)) or not isinstance(candidate, Sequence):
            candidate = tuple(candidate)
        return candidate

    @staticmethod
    def _message_fields(message: Any, index: int) -> tuple[str, str, dict[str, Any]]:
        if isinstance(message, Mapping):
            data = dict(message)
        elif hasattr(message, "to_dict") and callable(message.to_dict):
            converted = message.to_dict()
            data = dict(converted) if isinstance(converted, Mapping) else {}
        else:
            data = {
                key: getattr(message, key)
                for key in ("id", "message_id", "role", "content", "text", "timestamp")
                if hasattr(message, key)
            }
        content = data.get("content", data.get("text", ""))
        if not isinstance(content, str):
            content = str(content)
        role = data.get("role", "unknown")
        if not isinstance(role, str):
            role = str(role)
        identifier = data.get("id", data.get("message_id", index))
        metadata = {
            "role": role,
            "message_id": str(identifier),
        }
        if data.get("timestamp") is not None:
            metadata["timestamp"] = str(data["timestamp"])
        return f"message:{identifier}", content, metadata

    @staticmethod
    def _relevance_terms(value: str) -> set[str]:
        words = EvidenceBuilder._normalized_relevance_text(value).split()
        return {word for word in words if word not in _RELEVANCE_STOPWORDS}

    @staticmethod
    def _relevance_phrases(value: str) -> set[tuple[str, str]]:
        words = EvidenceBuilder._normalized_relevance_text(value).split()
        return set(zip(words, words[1:]))

    @staticmethod
    def _relevance_identifiers(value: str) -> set[str]:
        return {
            match.group(0).casefold()
            for match in _IDENTIFIER_TOKEN_RE.finditer(value)
        }

    @staticmethod
    def _is_question_only(value: str) -> bool:
        """True when every sentence in the turn is question-shaped.

        A turn that mixes an assertion with a question keeps its assertion
        weight; the adversarial review requires that mixed turns are classified
        conservatively rather than discarded as mere questions.
        """

        sentences = [
            sentence.strip()
            for sentence in _SENTENCE_SPLIT_RE.split(value)
            if sentence.strip()
        ]
        if not sentences:
            return False
        for sentence in sentences:
            normalized = EvidenceBuilder._normalized_relevance_text(sentence)
            if not normalized:
                continue
            if not sentence.rstrip().endswith("?") and not (
                _QUESTION_OPENER_RE.match(normalized)
            ):
                return False
        return True

    @staticmethod
    def _message_relevance_score(
        *,
        query_terms: set[str],
        query_phrases: set[tuple[str, str]],
        query_identifiers: set[str],
        role: str,
        content: str,
    ) -> float:
        """Deterministic lexical relevance of one prior turn to the query.

        Exact identifier overlap outranks phrase overlap, which outranks bare
        term overlap, because the operator facts this must recover are carried
        by exact keys far more often than by prose similarity.
        """

        if not content.strip():
            return 0.0
        identifier_hits = len(
            query_identifiers & EvidenceBuilder._relevance_identifiers(content)
        )
        phrase_hits = len(
            query_phrases & EvidenceBuilder._relevance_phrases(content)
        )
        term_hits = len(query_terms & EvidenceBuilder._relevance_terms(content))
        score = (
            _IDENTIFIER_MATCH_WEIGHT * identifier_hits
            + _PHRASE_MATCH_WEIGHT * phrase_hits
            + _TERM_MATCH_WEIGHT * term_hits
        )
        if score <= 0.0:
            return 0.0
        score *= _ROLE_RELEVANCE_WEIGHTS.get(role.casefold(), 0.5)
        if EvidenceBuilder._is_question_only(content):
            score *= _QUESTION_RELEVANCE_WEIGHT
        return score

    def _ordered_session_messages(
        self,
        prior_messages: Sequence[Any],
        *,
        session_id: str,
        query: str,
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], list[dict[str, str]]]:
        """Order prior turns for packing, newest-first unless ranking applies.

        Returns the emission order plus any omissions to record. Nothing is
        dropped for being merely low-ranked: conflicting or superseded records
        are retained so the model must report an unresolved conflict rather than
        silently pick one.
        """

        prepared: list[tuple[int, str, str, dict[str, Any]]] = []
        omissions: list[dict[str, str]] = []
        normalized_query = self._normalized_relevance_text(query)

        for index in range(len(prior_messages) - 1, -1, -1):
            source_id, content, metadata = self._message_fields(
                prior_messages[index],
                index,
            )
            # The operator's current input is never its own evidence. It is
            # already in the prompt verbatim, and admitting it lets an answer
            # "cite" the question it was asked.
            if (
                normalized_query
                and self._normalized_relevance_text(content) == normalized_query
            ):
                omissions.append(
                    {
                        "source": f"session:{session_id}/{source_id}",
                        "reason": "current operator input is not citeable evidence",
                    }
                )
                continue
            prepared.append((index, source_id, content, metadata))

        if not self.query_relevance or not query.strip():
            return (
                [(item[1], item[2], item[3]) for item in prepared],
                omissions,
            )

        query_terms = self._relevance_terms(query)
        query_phrases = self._relevance_phrases(query)
        query_identifiers = self._relevance_identifiers(query)

        scored: list[tuple[float, int, str, str, dict[str, Any]]] = []
        for index, source_id, content, metadata in prepared:
            score = self._message_relevance_score(
                query_terms=query_terms,
                query_phrases=query_phrases,
                query_identifiers=query_identifiers,
                role=str(metadata.get("role", "unknown")),
                content=content,
            )
            scored.append((score, index, source_id, content, metadata))

        # Recency is only a tie-break between equally relevant records, so a
        # newer record never displaces a strictly more relevant older one.
        reserved = [
            item
            for item in sorted(
                (item for item in scored if item[0] > 0.0),
                key=lambda item: (-item[0], -item[1]),
            )
        ][:_MAX_RESERVED_RELEVANT_MESSAGES]
        reserved_ids = {item[2] for item in reserved}

        ordered: list[tuple[str, str, dict[str, Any]]] = []
        for score, _index, source_id, content, metadata in reserved:
            annotated = dict(metadata)
            annotated["selection"] = "query_relevance_reserved"
            annotated["relevance_score"] = round(score, 4)
            ordered.append((source_id, content, annotated))
        for score, _index, source_id, content, metadata in scored:
            if source_id in reserved_ids:
                continue
            annotated = dict(metadata)
            annotated["selection"] = "recency_fallback"
            annotated["relevance_score"] = round(score, 4)
            ordered.append((source_id, content, annotated))
        return ordered, omissions

    def _read_file(
        self,
        relative: str,
        path: Path,
    ) -> tuple[bytes, int, str]:
        before = path.stat()
        if not path.is_file():
            raise EvidenceError("approved evidence source is not a regular file")
        digest = hashlib.sha256()
        prefix = bytearray()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65_536)
                if not chunk:
                    break
                digest.update(chunk)
                if len(prefix) < self.max_source_bytes:
                    needed = self.max_source_bytes - len(prefix)
                    prefix.extend(chunk[:needed])
        after = path.stat()
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
        ):
            raise EvidenceError(f"approved evidence source changed while read: {relative}")
        return bytes(prefix), after.st_size, digest.hexdigest()

    @staticmethod
    def _normalized_relevance_text(value: str) -> str:
        return " ".join(
            match.group(0).casefold()
            for match in _RELEVANCE_WORD_RE.finditer(value)
        )

    @staticmethod
    def _query_relevance_intents(query: str) -> set[str]:
        """Recognize bounded requests for the product's packaged state."""

        normalized = EvidenceBuilder._normalized_relevance_text(query)
        if not normalized:
            return set()
        words = set(normalized.split())
        has_product_reference = bool(_PRODUCT_QUERY_REFERENCE_RE.search(normalized))
        has_self_reference = bool(_SELF_QUERY_REFERENCE_RE.search(normalized))
        has_version_runtime_request = bool(
            _VERSION_RUNTIME_STATE_QUERY_RE.fullmatch(normalized)
        )
        intents: set[str] = set()

        if "version" in words and (
            has_product_reference
            or bool(_VERSION_STATE_QUERY_RE.fullmatch(normalized))
            or has_version_runtime_request
            or bool(
                re.search(
                    r"\b(?:your\s+version|version\s+(?:are|do)\s+you)\b",
                    normalized,
                )
            )
        ):
            intents.add("version")

        if "runtime" in words and (
            has_product_reference
            or has_version_runtime_request
            or bool(_RUNTIME_STATE_QUERY_RE.fullmatch(normalized))
            or bool(
                re.fullmatch(
                    r"(?:what|which)\s+runtime\s+(?:is\s+)?"
                    r"(?:configured|installed|running|available|in\s+use)",
                    normalized,
                )
            )
            or bool(
                re.fullmatch(
                    r"(?:is|are)\s+(?:the\s+)?runtime\s+"
                    r"(?:healthy|ready|running|available|operational)",
                    normalized,
                )
            )
        ):
            intents.add("runtime")

        if words & {"model", "models"} and any(
            pattern.fullmatch(normalized)
            for pattern in _MODEL_OPERATION_QUERY_RES
        ):
            intents.add("models")
        elif (
            words & {"model", "models"}
            and has_product_reference
            and bool(
                words
                & {
                    "configured",
                    "loaded",
                    "installed",
                    "available",
                    "running",
                    "active",
                    "selected",
                    "assigned",
                    "use",
                    "uses",
                }
            )
        ):
            intents.add("models")

        if "mode" in words and (
            has_product_reference
            or bool(_MODE_QUERY_RE.search(normalized))
        ):
            intents.add("mode")

        if any(pattern.fullmatch(normalized) for pattern in _FAILURE_QUERY_RES):
            intents.add("failure")
        elif has_product_reference and words & {
            "failed",
            "failure",
            "error",
        }:
            intents.add("failure")

        qualified_runtime_state = bool(
            re.search(r"\bruntime\s+(?:health|status)\b", normalized)
        )
        if (
            words & {"status", "health", "healthy", "ready", "operational"}
            and not qualified_runtime_state
            and (
                has_product_reference
                or bool(_GENERIC_STATUS_QUERY_RE.fullmatch(normalized))
                or bool(
                    re.search(
                        r"\b(?:your\s+status|how\s+are\s+you)\b",
                        normalized,
                    )
                )
                or (
                    has_self_reference
                    and bool(words & {"healthy", "ready", "operational"})
                )
            )
        ):
            intents.add("status")

        if words & {"capability", "capabilities", "feature", "features", "functions"}:
            if (
                has_product_reference
                or has_self_reference
                or bool(_GENERIC_CAPABILITY_QUERY_RE.fullmatch(normalized))
            ):
                intents.add("capabilities")
        elif _GENERIC_CAPABILITY_QUERY_RE.fullmatch(normalized):
            intents.add("capabilities")

        if words & {"configuration", "config", "settings", "configured"} and (
            has_product_reference
            or bool(_GENERIC_CONFIGURATION_QUERY_RE.fullmatch(normalized))
        ):
            intents.add("configuration")

        # EPC-02, operator-authorized. Adding constitution_v1.md to the retriever's candidate
        # set was inert on its own: this classifier recognized only eight product-state
        # concepts, so "What is the Praxis Answer?" produced NO intent, and a query with no
        # intent omits every file. The constitution was a candidate that nothing could ever
        # reach.
        #
        # This intent stays deliberately narrow, and narrow in a specific way: it fires on
        # the document's OWN vocabulary rather than on a general relaxation of the rule. The
        # surrounding design is fail-closed - a query it does not recognize retrieves nothing
        # rather than everything - and that property is preserved. A question about the
        # weather still matches no intent and still cites no evidence.
        if words & _CONSTITUTIONAL_QUERY_WORDS:
            intents.add("constitution")

        return intents

    def _explicit_file_targets(
        self,
        query: str,
    ) -> tuple[bool, set[str]]:
        """Resolve explicit approved locators without basename guessing."""

        query_with_posix_separators = query.replace("\\", "/").casefold()
        relative_lookup = {
            relative.casefold(): relative
            for relative in self._approved_paths
        }
        basename_lookup: dict[str, list[str]] = {}
        for relative in self._approved_paths:
            basename_lookup.setdefault(
                Path(relative).name.casefold(),
                [],
            ).append(relative)

        locator_matches = tuple(
            _EXPLICIT_LOCATOR_TOKEN_RE.finditer(query_with_posix_separators)
        )
        if locator_matches:
            targets: set[str] = set()
            for match in locator_matches:
                locator = match.group(0)
                if locator.startswith("./"):
                    locator = locator[2:]
                if "/" in locator:
                    exact = relative_lookup.get(locator)
                    if exact is not None:
                        targets.add(exact)
                    continue
                basename_candidates = basename_lookup.get(locator, ())
                if len(basename_candidates) == 1:
                    targets.add(basename_candidates[0])
            # A locator-shaped reference is authoritative even when it names
            # an unapproved path or an ambiguous basename. Do not fall back to
            # topic matching in either case.
            return True, targets

        normalized_query = self._normalized_relevance_text(query)
        alias_targets: set[str] = set()
        alias_reference_seen = False
        for alias, canonical_relative in _HUMANIZED_PRODUCT_LOCATOR_ALIASES.items():
            alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
            source_reference = re.search(
                rf"\b(?:according\s+to|from|read|use|using|consult|open)"
                rf"\s+(?:the\s+)?{alias_pattern}\b|"
                rf"\bwhat\s+does\s+(?:the\s+)?{alias_pattern}\s+say\b",
                normalized_query,
            )
            if source_reference is None:
                continue
            alias_reference_seen = True
            approved = relative_lookup.get(canonical_relative.casefold())
            if approved is not None:
                alias_targets.add(approved)
        return alias_reference_seen, alias_targets

    @staticmethod
    def _file_relevance_intents(
        *,
        relative: str,
        text: str,
    ) -> set[str]:
        """Classify the narrow product-state subjects a file can support."""

        normalized_relative = relative.replace("\\", "/").casefold()
        known = _KNOWN_PRODUCT_FILE_INTENTS.get(normalized_relative)
        if known is not None:
            return set(known)

        locator_words = set(
            EvidenceBuilder._normalized_relevance_text(relative).split()
        )
        content_words = set(
            EvidenceBuilder._normalized_relevance_text(text).split()
        )
        all_words = locator_words | content_words
        folded = text.casefold()
        intents: set[str] = set()

        if (
            "version" in locator_words
            or re.search(
                r"(?:product|archive|release)[_-]*version|"
                r"(?:product|archive|release)_version",
                folded,
            )
        ):
            intents.add("version")
        if "runtime" in all_words:
            intents.add("runtime")
        if (
            "model" in locator_words
            or "models" in locator_words
            or re.search(
                r"""(?ix)
                ["'][a-z0-9_-]*models?[a-z0-9_-]*["']\s*:|
                \b[a-z0-9_]*model[a-z0-9_]*\s*=
                """,
                text,
            )
        ):
            intents.add("models")
        if (
            bool(locator_words & {"constitution", "mode"})
            or re.search(
                r"""(?ix)
                ["'][a-z0-9_-]*mode[a-z0-9_-]*["']\s*:|
                \b[a-z0-9_]*mode[a-z0-9_]*\s*=
                """,
                text,
            )
        ):
            intents.add("mode")
        if all_words & {"status", "health", "state", "profile", "blocker"}:
            intents.add("status")
        if all_words & {
            "failed",
            "failure",
            "error",
            "exception",
            "blocker",
        }:
            intents.add("failure")
        if locator_words & {
            "manifest",
            "profile",
            "config",
            "configuration",
            "settings",
        }:
            intents.add("configuration")
        if (
            all_words
            & {"capability", "capabilities", "feature", "features", "component"}
            or locator_words & {"manifest", "profile", "models", "model"}
        ):
            intents.add("capabilities")
        return intents

    def _file_is_query_relevant(
        self,
        *,
        query: str,
        relative: str,
        text: str,
    ) -> bool:
        if not self.query_relevance or not query.strip():
            return True
        has_explicit_targets, explicit_targets = self._explicit_file_targets(query)
        if has_explicit_targets:
            return relative in explicit_targets
        query_intents = self._query_relevance_intents(query)
        if not query_intents:
            return False
        file_intents = self._file_relevance_intents(
            relative=relative,
            text=text,
        )
        # Product-file evidence is fail-closed. A recognized product-state
        # request must also match a subject the individual file can support;
        # generic overlap on system, service, model, or version is insufficient.
        return bool(query_intents & file_intents)

    def build(
        self,
        session_id: str,
        *,
        query: str = "",
    ) -> EvidencePacket:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string")
        if not isinstance(query, str):
            raise TypeError("query must be a string")

        sources: list[EvidenceSource] = []
        blocks: list[str] = []
        omissions: list[dict[str, str]] = []

        def add_candidate(
            *,
            source_id: str,
            kind: str,
            locator: str,
            full_text: str,
            content_bytes: int,
            content_sha256: str,
            metadata: dict[str, Any],
        ) -> None:
            separator = "\n\n" if blocks else ""
            header_payload = json.dumps(
                {
                    "id": source_id,
                    "kind": kind,
                    "locator": locator,
                    "sha256": content_sha256,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            header = f"[source {header_payload}]\n"
            current = "\n\n".join(blocks)
            remaining_bytes = self.max_bytes - len(current.encode("utf-8"))
            remaining_tokens = self.max_tokens - self.token_counter(current)
            header_cost_bytes = len((separator + header).encode("utf-8"))
            header_cost_tokens = self.token_counter(separator + header)
            snippet_byte_limit = min(
                self.max_source_bytes,
                remaining_bytes - header_cost_bytes,
            )
            snippet_token_limit = remaining_tokens - header_cost_tokens
            snippet = _fit_text(
                full_text,
                byte_limit=snippet_byte_limit,
                token_limit=snippet_token_limit,
                token_counter=self.token_counter,
            )
            # A custom token counter is not necessarily additive. Tighten the
            # candidate against the complete rendered packet, not an estimate.
            low = 0
            high = len(snippet)
            while low < high:
                midpoint = (low + high + 1) // 2
                proposed = current + separator + header + snippet[:midpoint]
                if (
                    len(proposed.encode("utf-8")) <= self.max_bytes
                    and self.token_counter(proposed) <= self.max_tokens
                ):
                    low = midpoint
                else:
                    high = midpoint - 1
            snippet = snippet[:low]
            if not snippet:
                omissions.append({"source": locator, "reason": "packet budget exhausted"})
                return
            block = header + snippet
            proposed = current + separator + block
            proposed_bytes = len(proposed.encode("utf-8"))
            proposed_tokens = self.token_counter(proposed)
            if proposed_bytes > self.max_bytes or proposed_tokens > self.max_tokens:
                raise AssertionError("evidence packet bound calculation failed")
            blocks.append(block)
            snippet_bytes = len(snippet.encode("utf-8"))
            sources.append(
                EvidenceSource(
                    source_id=source_id,
                    kind=kind,
                    locator=locator,
                    content_sha256=content_sha256,
                    snippet_sha256=_sha256_bytes(snippet.encode("utf-8")),
                    snippet=snippet,
                    content_bytes=content_bytes,
                    snippet_bytes=snippet_bytes,
                    snippet_tokens=self.token_counter(snippet),
                    truncated=snippet_bytes < content_bytes,
                    metadata=dict(metadata),
                )
            )

        for index, relative in enumerate(sorted(self._approved_paths), start=1):
            path = self._approved_paths[relative]
            try:
                prefix, content_bytes, content_hash = self._read_file(relative, path)
                text = prefix.decode("utf-8", errors="replace")
                if not self._file_is_query_relevant(
                    query=query,
                    relative=relative,
                    text=text,
                ):
                    omissions.append(
                        {
                            "source": relative,
                            "reason": "not query-relevant",
                        }
                    )
                    continue
                add_candidate(
                    source_id=f"file:{index}",
                    kind="file",
                    locator=relative,
                    full_text=text,
                    content_bytes=content_bytes,
                    content_sha256=content_hash,
                    metadata={"root_relative_path": relative},
                )
            except (OSError, EvidenceError) as exc:
                omissions.append(
                    {
                        "source": relative,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )

        try:
            prior_messages = list(self._messages(session_id))
        except Exception as exc:
            omissions.append(
                {
                    "source": f"session:{session_id}",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            prior_messages = []

        # Reserve the highest-ranked prior sources for this query, then fall back
        # to most-recent-first for the remaining budget. Each source retains its
        # original stable message ID.
        ordered_messages, message_omissions = self._ordered_session_messages(
            prior_messages,
            session_id=session_id,
            query=query,
        )
        omissions.extend(message_omissions)
        for source_id, content, metadata in ordered_messages:
            raw = content.encode("utf-8")
            add_candidate(
                source_id=source_id,
                kind="session_message",
                locator=f"session:{session_id}/{source_id}",
                full_text=content,
                content_bytes=len(raw),
                content_sha256=_sha256_bytes(raw),
                metadata=metadata,
            )

        packet_text = "\n\n".join(blocks)
        total_bytes = len(packet_text.encode("utf-8"))
        total_tokens = self.token_counter(packet_text)
        if total_bytes > self.max_bytes or total_tokens > self.max_tokens:
            raise AssertionError("evidence packet exceeded configured bounds")
        hash_input = {
            "session_id": session_id,
            "query_sha256": _sha256_bytes(query.encode("utf-8")),
            "sources": [
                {
                    "source_id": source.source_id,
                    "kind": source.kind,
                    "locator": source.locator,
                    "content_sha256": source.content_sha256,
                    "snippet_sha256": source.snippet_sha256,
                }
                for source in sources
            ],
            "omissions": [dict(item) for item in omissions],
            "text": packet_text,
            "bounds": {
                "max_bytes": self.max_bytes,
                "max_tokens": self.max_tokens,
                "token_count_method": str(self.token_count_method),
            },
        }
        return EvidencePacket(
            session_id=session_id,
            query_sha256=hash_input["query_sha256"],
            created_at=self._now(),
            sources=tuple(sources),
            omissions=tuple(omissions),
            text=packet_text,
            total_bytes=total_bytes,
            total_tokens=total_tokens,
            max_bytes=self.max_bytes,
            max_tokens=self.max_tokens,
            token_count_method=str(self.token_count_method),
            packet_sha256=_canonical_hash(hash_input),
        )
