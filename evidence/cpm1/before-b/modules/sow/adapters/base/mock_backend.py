"""Deterministic mock reasoning backend (Phase 4/5/6 substitution for a real model).

Stands in for a model behind the adapter contract so the governed orchestration path is
exercised with zero provider network use (build prohibition §2.4). Output is a pure
function of (objective, loaded conductor files, cycle) so runs are replayable. It produces
a conductor DECISION shape, not free text — the point under test is orchestration
mechanics, not generation quality.
"""
from __future__ import annotations

import hashlib
from typing import Any


class MockReasoningBackend:
    def __init__(self, model_name: str = "mock-reasoner-v1") -> None:
        self.model_name = model_name
        self.calls = 0

    def propose_plan(self, objective: str, conductor_files: dict[str, str], cycle: int) -> dict[str, Any]:
        """Deterministically decompose an objective into candidate task descriptions. Phase 4
        only records the decision; Phase 5 turns these into assigned worker nodes."""
        self.calls += 1
        seed = hashlib.sha256(
            (objective + "|" + "|".join(sorted(conductor_files)) + f"|{cycle}").encode("utf-8")
        ).hexdigest()
        n_tasks = 2 + (int(seed[:2], 16) % 2)  # 2 or 3, deterministic
        tasks = [
            {"desc": f"subtask {i + 1} of: {objective[:60]}",
             "capability": ["reasoning", "coding", "review"][i % 3]}
            for i in range(n_tasks)
        ]
        return {
            "model": self.model_name, "cycle": cycle, "seed": seed[:16],
            "objective_ack": objective, "proposed_tasks": tasks,
            "files_considered": sorted(conductor_files),
            "rationale": f"deterministic mock decomposition into {n_tasks} tasks",
        }
