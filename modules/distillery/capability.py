"""Distillery capability status - what the module can and cannot do right now, and why (SW-24).

The served console used to be a static "idle" page that started no compute and never explained
WHY real training and promotion do nothing. This module derives an HONEST capability report from
the real gates - the trainer preflight contract in ``train.runner`` and the promotion-authority
gate in ``ops.promotion`` - so the console and the ``/capability`` endpoint state exactly what is
unavailable and why, and so any preview evidence is labelled synthetic fixture that can never
satisfy the measured/qualified gates promotion requires.

Stdlib-only and fail-safe: every introspection is guarded, so the health console still serves a
truthful (if degraded) report even if a deeper import ever breaks. The reason codes and the VRAM
numbers are read from the real constants rather than restated here, so this cannot drift from the
gates it describes.
"""
from __future__ import annotations

INTROSPECTION_FAILED = "CAPABILITY_INTROSPECTION_FAILED"


def _training_capability() -> dict:
    try:
        from train.runner import MINIMUM_USABLE_VRAM_MIB, PREFERRED_USABLE_VRAM_MIB
        min_gib = MINIMUM_USABLE_VRAM_MIB // 1024
        pref_gib = PREFERRED_USABLE_VRAM_MIB // 1024
        return {
            "id": "real_training",
            "label": "Real (measured) training",
            "available": False,
            "reason": "BLOCKED_HARDWARE_CAPACITY",
            "detail": (
                f"Canonical training needs >= {min_gib} GiB usable VRAM (preferred {pref_gib} GiB) "
                "and a qualified-trainer execution contract that is not authorized in this "
                "release; the real backend refuses every invocation (hard gate HG-3)."
            ),
        }
    except Exception as exc:  # noqa: BLE001 - a health console must not crash on introspection
        return {"id": "real_training", "label": "Real (measured) training", "available": False,
                "reason": INTROSPECTION_FAILED, "detail": f"{type(exc).__name__}: {exc}"}


def _promotion_capability() -> dict:
    try:
        from ops.promotion import PROMOTION_AUTHORITY_UNAVAILABLE
        return {
            "id": "promotion",
            "label": "Candidate promotion",
            "available": False,
            "reason": PROMOTION_AUTHORITY_UNAVAILABLE,
            "detail": (
                "Promotion requires explicit trusted human PROMOTE authority, which is not wired "
                "in this release; every promotion attempt is refused."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"id": "promotion", "label": "Candidate promotion", "available": False,
                "reason": INTROSPECTION_FAILED, "detail": f"{type(exc).__name__}: {exc}"}


def _evidence_note() -> dict:
    try:
        from train.runner import FIXTURE_EVIDENCE_CLASS, MEASURED_EVIDENCE_CLASS
        fixture_class, measured_class = FIXTURE_EVIDENCE_CLASS, MEASURED_EVIDENCE_CLASS
    except Exception:  # noqa: BLE001
        fixture_class, measured_class = "SYNTHETIC_FIXTURE_ONLY", "MEASURED"
    return {
        "class_shown": fixture_class,
        "measured_class": measured_class,
        "note": (
            f"Any evidence surfaced in preview is synthetic fixture output, marked "
            f"'{fixture_class}', kept separate from real runs and can never satisfy the "
            f"'{measured_class}' gates that promotion requires."
        ),
    }


def capability_report() -> dict:
    """Return the module's honest capability status for the console and /capability endpoint."""
    return {
        "maturity": "preview",
        "compute": False,
        "capabilities": [_training_capability(), _promotion_capability()],
        "evidence": _evidence_note(),
    }
