from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .common import SANDBOX_ROOT, load_json, read_text, utc_timestamp
except ImportError:
    from runtime.common import SANDBOX_ROOT, load_json, read_text, utc_timestamp


PROMOTION_QUEUE_ROOT = Path("workspace") / "promotion_queue"
REJECTED_ROOT = Path("workspace") / "rejected_promotions"
DEFERRED_ROOT = Path("workspace") / "deferred_promotions"
REVISION_ROOT = Path("workspace") / "revision_requested"
APPROVED_APPLIES_ROOT = Path("workspace") / "approved_sandbox_applies"


def load_promotion_queue_summary(root: Path | None = None) -> dict[str, Any]:
    sandbox_root = root or SANDBOX_ROOT
    items = _load_manifest_bundle(sandbox_root / PROMOTION_QUEUE_ROOT)
    approved = _load_manifest_bundle(sandbox_root / APPROVED_APPLIES_ROOT)
    rejected = _load_manifest_bundle(sandbox_root / REJECTED_ROOT)
    deferred = _load_manifest_bundle(sandbox_root / DEFERRED_ROOT)
    revision_requested = _load_manifest_bundle(sandbox_root / REVISION_ROOT)
    counts = {
        "pending": sum(1 for item in items if item.get("status") == "PENDING_REVIEW"),
        "deferred": len(deferred),
        "rejected": len(rejected),
        "revision_requested": len(revision_requested),
        "approved_sandbox_apply": sum(1 for item in items if item.get("latest_decision") == "approve_sandbox_apply"),
        "applied": sum(1 for item in items if item.get("sandbox_apply_status") == "APPLIED"),
        "apply_failed": sum(1 for item in items if item.get("sandbox_apply_status") == "APPLY_FAILED"),
    }
    return {
        "timestamp_utc": utc_timestamp(),
        "queue_count": len(items),
        "counts": counts,
        "items": items[:50],
        "approved_sandbox_applies": approved[:25],
        "rejected_promotions": rejected[:25],
        "deferred_promotions": deferred[:25],
        "revision_requested": revision_requested[:25],
    }


def load_promotion_detail(promotion_id: str, root: Path | None = None) -> dict[str, Any]:
    sandbox_root = root or SANDBOX_ROOT
    item_root = sandbox_root / PROMOTION_QUEUE_ROOT / promotion_id
    manifest = load_json(item_root / "promotion_manifest.json", {})
    if not manifest:
        return {}
    return {
        "manifest": manifest,
        "diff_patch": read_text(item_root / "diff.patch", ""),
        "risk_review": read_text(item_root / "risk_review.md", ""),
        "validation_report": read_text(item_root / "validation_report.md", ""),
        "rollback_plan": read_text(item_root / "rollback_plan.md", ""),
        "operator_decision": load_json(item_root / "operator_decision.json", {}),
    }


def _load_manifest_bundle(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.exists():
        return items
    for item_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda item: item.name, reverse=True):
        manifest = load_json(item_dir / "promotion_manifest.json", {})
        if manifest:
            manifest["bundle_root"] = str(item_dir)
            items.append(manifest)
    return items
