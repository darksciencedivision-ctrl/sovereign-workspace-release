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
    # Sharded inference: a big-model, big-workload run. Never chosen automatically - only by an
    # explicit override (route_override "LONG" or an inline "route: LONG").
    LONG = "LONG"

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
    RoutingRule(
        "evidence_research",
        Route.RESEARCH,
        "The request explicitly asks for external research, current sources, or citations.",
        (
            r"\bresearch\b",
            r"\bliterature\b",
            r"\bsource[sd]?\b",
            r"\bcitations?\b",
            r"\blook\s+(?:it\s+)?up\b",
            r"\bsearch\b",
            r"\bweb\b",
            r"\blatest\b",
            r"\bup[\s-]?to[\s-]?date\b",
            r"\bcurrent\s+(?:law|price|news|release|research)\b",
            r"\bevidence\s+(?:for|against|about|on)\b",
        ),
    ),
    RoutingRule(
        "deliberative_analysis",
        Route.DEEP,
        "The request calls for multi-step analysis, evaluation, comparison, or design.",
        (
            r"\banaly[sz]e\b",
            r"\bevaluate\b",
            r"\bcompare\b",
            r"\bcritique\b",
            r"\btrade[\s-]?offs?\b",
            r"\barchitecture\b",
            r"\broot\s+cause\b",
            r"\breason\s+through\b",
            r"\bstep[\s-]?by[\s-]?step\b",
            r"\bwhy\b",
            r"\bexplain\b",
            r"\bdesign\b",
            r"\bstrategy\b",
        ),
    ),
)

_INLINE_OVERRIDE = re.compile(
    r"^\s*(?:/route\s+|route\s*[:=]\s*)"
    r"(STATUS|QUICK|DEEP|RESEARCH|CONTINUITY|LONG)\b[\s:,-]*",
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
                "Default for concise requests that match no higher-priority rule."
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

    text = " ".join(str(query or "").split())
    if override is not None:
        selected = Route.parse(override)
        return RoutingDecision(
            selected,
            text,
            "explicit caller override",
            True,
            ("explicit_override",),
            (selected.value,),
        )

    if allow_inline_override:
        inline = _INLINE_OVERRIDE.match(text)
        if inline:
            selected = Route.parse(inline.group(1))
            stripped = text[inline.end() :].strip()
            return RoutingDecision(
                selected,
                stripped,
                "explicit inline route override",
                True,
                ("inline_override",),
                (selected.value,),
            )

    if _context_requests_continuity(context):
        return RoutingDecision(
            Route.CONTINUITY,
            text,
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
            if (match := re.search(pattern, text, flags=re.IGNORECASE))
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
            text,
            selected_rule.description,
            False,
            same_route_rules,
            selected_signals,
        )

    word_count = len(_WORD.findall(text))
    if word_count >= 30:
        return RoutingDecision(
            Route.DEEP,
            text,
            "long-form request threshold (30 or more words)",
            False,
            ("long_form_threshold",),
            (f"word_count={word_count}",),
        )
    return RoutingDecision(
        Route.QUICK,
        text,
        "no continuity, self-state, research, or deep-analysis signal matched",
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
