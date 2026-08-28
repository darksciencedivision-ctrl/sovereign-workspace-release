"""
phase14p_routes.py — Phase 14P: read-only URI endpoints for cognitive continuity state.

Endpoints (all GET, visibility only):
  GET /api/sandbox/continuity
  GET /api/sandbox/self-model
  GET /api/sandbox/goals
  GET /api/sandbox/ontology
  GET /api/sandbox/emergence-scorecard
  GET /api/sandbox/drift
  GET /api/sandbox/anthropomorphic-flags
  GET /api/sandbox/consequences
  GET /api/sandbox/compression
  GET /api/sandbox/cognition-summary

No mutation. No auto-promotion. No goal execution. No live SOVEREIGN modification.
No path traversal. All payloads bounded.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PREFIX = "/api/sandbox"
_METHOD_ERROR_HANDLER_FLAG = "_phase14p_method_error_handler_registered"


def register_phase14p_routes(app) -> None:
    """Register Phase 14P read-only endpoints on the Flask app."""
    from flask import jsonify, request
    from .phase14p_state_reader import (
        get_continuity,
        get_self_model,
        get_goals,
        get_ontology,
        get_emergence_scorecard,
        get_drift,
        get_anthropomorphic_flags,
        get_consequences,
        get_compression,
        get_cognition_summary,
    )

    def _make_get(reader_fn):
        def view():
            try:
                result = reader_fn()
                return jsonify(result), 200
            except Exception as exc:
                logger.error("phase14p endpoint error: %s", exc)
                return jsonify({"ok": False, "error": str(exc), "mutation_blocked": True}), 500
        return view

    if not getattr(app, _METHOD_ERROR_HANDLER_FLAG, False):
        @app.errorhandler(405)
        def _phase14p_method_not_allowed(exc):
            if request.path.startswith(f"{_PREFIX}/"):
                return jsonify(
                    {
                        "ok": False,
                        "error": "method_not_allowed",
                        "endpoint": request.path,
                        "method": request.method,
                        "allowed_methods": ["GET"],
                        "mutation_blocked": True,
                    }
                ), 405
            return exc.get_response()

        setattr(app, _METHOD_ERROR_HANDLER_FLAG, True)

    route_defs = [
        ("p14p_continuity",          f"{_PREFIX}/continuity",            _make_get(get_continuity)),
        ("p14p_self_model",          f"{_PREFIX}/self-model",            _make_get(get_self_model)),
        ("p14p_goals",               f"{_PREFIX}/goals",                 _make_get(get_goals)),
        ("p14p_ontology",            f"{_PREFIX}/ontology",              _make_get(get_ontology)),
        ("p14p_emergence_scorecard", f"{_PREFIX}/emergence-scorecard",   _make_get(get_emergence_scorecard)),
        ("p14p_drift",               f"{_PREFIX}/drift",                 _make_get(get_drift)),
        ("p14p_anthropomorphic",     f"{_PREFIX}/anthropomorphic-flags", _make_get(get_anthropomorphic_flags)),
        ("p14p_consequences",        f"{_PREFIX}/consequences",          _make_get(get_consequences)),
        ("p14p_compression",         f"{_PREFIX}/compression",           _make_get(get_compression)),
        ("p14p_cognition_summary",   f"{_PREFIX}/cognition-summary",     _make_get(get_cognition_summary)),
    ]

    for endpoint, url, view_fn in route_defs:
        try:
            app.add_url_rule(url, endpoint=endpoint, view_func=view_fn, methods=["GET"])
            logger.debug("phase14p registered: GET %s", url)
        except AssertionError as exc:
            logger.warning("phase14p route already registered: %s — %s", url, exc)
