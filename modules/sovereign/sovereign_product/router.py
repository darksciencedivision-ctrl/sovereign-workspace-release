"""Deterministic and inspectable request routing.

The router chooses one of five product modes without consulting a model.  An
explicit caller override always wins; otherwise rules are applied in declared
precedence order and the complete decision evidence is returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class Route(str, Enum):
    STATUS = "STATUS"
    QUICK = "QUICK"
    DEEP = "DEEP"
    RESEARCH = "RESEARCH"
    CONTINUITY = "CONTINUITY"

    @classmethod
    def parse(cls, value: "Route | str") -> "Route":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper()
        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(route.value for route in cls)
            raise ValueError(f"Unknown route override {value!r}; expected one of {allowed}") from exc


@dataclass(frozen=True)
class RoutingRule:
    name: str
    route: Route
    description: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    normalized_query: str
    reason: str
    explicit: bool
    matched_rules: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "normalized_query": self.normalized_query,
            "reason": self.reason,
            "explicit": self.explicit,
            "matched_rules": list(self.matched_rules),
            "signals": list(self.signals),
        }


ROUTING_RULES: tuple[RoutingRule, ...] = (
    RoutingRule(
        "continuity_reference",
        Route.CONTINUITY,
        "The request explicitly depends on earlier work or asks to resume it.",
        (
            r"\bcontinue\b",
            r"\bresume\b",
            r"\bpick\s+up\s+where\b",
            r"\bprevious\s+(?:answer|conversation|session|work|result)\b",
            r"\bearlier\s+(?:answer|conversation|work|result)\b",
            r"\blast\s+(?:time|session|answer)\b",
            r"\bas\s+(?:we|you)\s+(?:discussed|said|found)\b",
            r"\bfollow[\s-]?up\b",
            r"\bremember\s+(?:our|the|that|when)\b",
        ),
    ),
    RoutingRule(
        "machine_self_state",
        Route.STATUS,
        "The request asks for machine-observable identity, health, status, or capability.",
        (
            r"\bstatus\b",
            r"\bhealth\b",
            r"\boperational\b",
            r"\bdiagnostic",
            r"\bwhat\s+(?:are|can)\s+you\b",
            r"\bwho\s+are\s+you\b",
            r"\byour\s+capabilit",
            r"\bwhich\s+models?\b",
            r"\bmodel\s+(?:status|state|roster)\b",
            r"\bversion\b",
            r"\bsentien",
            r"\bconscious",
            r"\bsubjective\s+experience\b",
            r"\bAGI\b",
            r"\bartificial\s+general\s+intelligence\b",
        ),
    ),
    # R20 and F-116. DEEP and RESEARCH are EXPLICIT-ONLY routes. The keyword-driven rules that
    # used to select them under AUTO ("evidence_research" -> RESEARCH on words like sources /
    # citations / search; "deliberative_analysis" -> DEEP on analyze / compare / why / explain)
    # were removed. SWS-BENCH-02 measured full orchestration LOSING to single-model QUICK, and an
    # ordinary "cite sources for X" or "explain recursion" would otherwise be dragged into a
    # multi-minute RESEARCH/DEEP run the operator never asked for. Both routes remain reachable at
    # any time through an explicit caller override or an inline `route: DEEP` / `/route RESEARCH`
    # prefix; only the implicit keyword triggering is gone. Do not re-add these as AUTO rules
    # without re-approving the product decision.
)

_INLINE_OVERRIDE = re.compile(
    r"^\s*(?:/route\s+|route\s*[:=]\s*)"
    r"(STATUS|QUICK|DEEP|RESEARCH|CONTINUITY)\b[\s:,-]*",
    re.IGNORECASE,
)
_WORD = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def inspect_router() -> list[dict[str, Any]]:
    """Return the ordered, machine-inspectable routing contract."""

    rules = [
        {
            "name": rule.name,
            "route": rule.route.value,
            "description": rule.description,
            "patterns": list(rule.patterns),
        }
        for rule in ROUTING_RULES
    ]
    rules.append(
        {
            "name": "quick-default",
            "route": Route.QUICK.value,
            "description": (
                "Default when no higher-priority rule matches, including long-form "
                "requests. SWS-BENCH-02: full orchestration lost to single-model "
                "QUICK; DEEP remains an explicit override."
            ),
            "patterns": [],
        }
    )
    return rules


def _context_requests_continuity(context: Mapping[str, Any] | None) -> bool:
    if not context:
        return False
    return bool(
        context.get("continuation")
        or context.get("resume")
        or context.get("prior_turn_id")
        or context.get("prior_job_id")
    )


def route_query(
    query: str,
    override: Route | str | None = None,
    *,
    context: Mapping[str, Any] | None = None,
    allow_inline_override: bool = True,
) -> RoutingDecision:
    """Route ``query`` and expose every deterministic reason for the choice."""

    # R19. Two distinct texts, deliberately kept apart:
    #   * `raw` is the EXECUTION PAYLOAD -- what the executor and the durable job must receive
    #     byte-for-byte. A multiline program's newlines, indentation and internal spacing are
    #     meaning, and collapsing them (as this function used to) silently corrupted the request
    #     before it ever ran.
    #   * `match_text` is a whitespace-collapsed copy used ONLY to test the routing rules, so a
    #     signal split across a newline still matches. It never becomes the payload.
    raw = str(query if query is not None else "")
    match_text = " ".join(raw.split())
    if override is not None:
        selected = Route.parse(override)
        return RoutingDecision(
            selected,
            raw,
            "explicit caller override",
            True,
            ("explicit_override",),
            (selected.value,),
        )

    if allow_inline_override:
        # Match the inline prefix against the RAW text so only the parsed route prefix (and its
        # trailing separator) is removed; the remainder keeps its exact bytes.
        inline = _INLINE_OVERRIDE.match(raw)
        if inline:
            selected = Route.parse(inline.group(1))
            payload = raw[inline.end():]
            return RoutingDecision(
                selected,
                payload,
                "explicit inline route override",
                True,
                ("inline_override",),
                (selected.value,),
            )

    if _context_requests_continuity(context):
        return RoutingDecision(
            Route.CONTINUITY,
            raw,
            "caller context identifies a prior turn or resumable job",
            False,
            ("continuity_context",),
            ("prior_context",),
        )

    matches: list[tuple[RoutingRule, tuple[str, ...]]] = []
    for rule in ROUTING_RULES:
        signals = tuple(
            match.group(0)
            for pattern in rule.patterns
            if (match := re.search(pattern, match_text, flags=re.IGNORECASE))
        )
        if signals:
            matches.append((rule, signals))

    if matches:
        # ROUTING_RULES is ordered by precedence.
        selected_rule, selected_signals = matches[0]
        same_route_rules = tuple(
            rule.name for rule, _signals in matches if rule.route == selected_rule.route
        )
        return RoutingDecision(
            selected_rule.route,
            raw,
            selected_rule.description,
            False,
            same_route_rules,
            selected_signals,
        )

    word_count = len(_WORD.findall(match_text))
    return RoutingDecision(
        Route.QUICK,
        raw,
        "no continuity, self-state, research, or deep-analysis signal matched; "
        "QUICK is the default including long-form requests (SWS-BENCH-02)",
        False,
        ("quick_default",),
        (f"word_count={word_count}",),
    )


def explain_route(
    query: str,
    override: Route | str | None = None,
    *,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return route_query(query, override, context=context).as_dict()


# Compact aliases for consumers that prefer router-like naming.
select_route = route_query
route = route_query
