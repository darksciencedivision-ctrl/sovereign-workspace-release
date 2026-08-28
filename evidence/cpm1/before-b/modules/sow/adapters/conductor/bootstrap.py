"""Publish the operator-authored conductor files into MCP (Plan §2.10.4).

Conductor files are operator-created, model-independent assets living in conductor/. They
become governed project state by being published into MCP as kind=conductor_file — an
operator-only write (policy: canonical directive / conductor files are not worker-writable).
They are published ACCEPTED because they are operator-authored canonical assets. Returns a
manifest {filename: entry_id} the supervisor hands to a conductor adapter so it can load
them by name in declared order.

This is the Sovereign/operator bootstrap path; ordinary nodes never publish conductor files.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from adapters.conductor.adapter import CONDUCTOR_FILE_ORDER


def publish_conductor_files(operator_client: Any, operator_node_id: str, conductor_dir: Path,
                            directive_version: str = "v2.4") -> dict[str, str]:
    """operator_client must be authenticated as operator_node_id with role=operator (the
    only role permitted to write conductor_file entries)."""
    conductor_dir = Path(conductor_dir)
    manifest: dict[str, str] = {}
    for filename in CONDUCTOR_FILE_ORDER:
        content = (conductor_dir / filename).read_bytes()
        prov = {"author_node": operator_node_id, "task_id": None,
                "ts": _now(), "directive_version": directive_version, "confidence": "high"}
        pub = operator_client.call(
            "publish", kind="conductor_file", tier="shared_project",
            content_b64=base64.b64encode(content).decode("ascii"), provenance=prov, status="ACCEPTED",
        )
        manifest[filename] = pub["entry_id"]
    return manifest


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
