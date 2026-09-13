"""Where a local CODING pane's git worktrees come from (EPC-04, W-3).

A coding pane is a model with WRITE HANDS, and `worker_pane_spawn` refuses to open one without a
worktree manager. This module is the one place that decides WHICH REPOSITORY those worktrees are
cut from, and it is separate from the spawn path on purpose: "what repo is the operator coding in"
is a host/configuration question, while "may this pane open at all" is a governance question, and
answering both in one function is how a configuration default quietly becomes a permission.

THE BASE REPO IS NEVER GUESSED INTO EXISTENCE. Three resolutions, in order, and a refusal:

  1. `SOW_CODING_BASE_REPO`, when set. The operator naming the repository explicitly outranks
     anything inferred, and it is the only way to point a pane at a project that is not this one.
  2. the nearest enclosing git repository of the pane's workspace. `WORKER_WORKSPACE` is
     `modules/sow`, which is NOT itself a repo — the enclosing checkout is.
  3. nothing. The caller then has no manager, and `_authorize_local_coding` refuses the pane. That
     refusal is the correct outcome: a coding pane with nowhere contained to write must not open.

WHY THE MANAGER IS CACHED PER BASE REPO. `WorktreeManager._nodes` is in-memory, and it is what
makes two panes in one process see each other's trees. Building a fresh manager per pane would
give each one an empty view, so `ensure` would find nothing registered in ITS map and fall through
to git — correct, but only because `ensure` reconciles against git. The cache keeps the cheap path
cheap and the in-process view consistent; correctness does not depend on it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from node_runtime.workspace.worktree import WorktreeError, WorktreeManager

#: The operator's explicit override. Named rather than inferred, per §1 of the resolution order.
BASE_REPO_ENV = "SOW_CODING_BASE_REPO"

_MANAGERS: dict[str, WorktreeManager] = {}


def resolve_base_repo(workspace: str | Path | None) -> Path | None:
    """The repository a coding pane's worktrees are cut from, or None if there is not one.

    None is a legitimate answer and must stay one. It becomes a refusal upstream, which is the
    behaviour wanted: no repository means no containment means no pane.
    """
    override = (os.environ.get(BASE_REPO_ENV) or "").strip()
    if override:
        candidate = Path(override)
        # An override that is NOT a repo is a configuration error and is reported as one. Falling
        # back to the inferred repo here would silently code in a different project than the
        # operator named — a worse outcome than refusing.
        return candidate if (candidate / ".git").exists() else None

    if not workspace:
        return None
    here = Path(workspace).resolve()
    product_root = _product_checkout_root()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            # F-131f. NEVER cut worktrees from the product's OWN install checkout. The enclosing
            # repo of WORKER_WORKSPACE (modules/sow) IS that checkout, so inferring it stamped
            # node/<id> branches, worktree admin records and working trees into the shipped tree
            # (the origin of the orphan worktrees/worker-pane-2). If the only enclosing repo is this
            # install, refuse -- the caller then denies the pane -- and let the operator point a
            # pane at a real project with SOW_CODING_BASE_REPO.
            if product_root is not None and candidate.resolve() == product_root:
                return None
            return candidate
    return None


def _product_checkout_root() -> Path | None:
    """The git checkout this module itself ships inside, or None. Used only to REFUSE cutting a
    coding pane's worktrees from the product's own install tree (F-131f)."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


def coding_worktree_manager(workspace: str | Path | None,
                            *, on_event: Any = None) -> WorktreeManager | None:
    """A manager for `workspace`'s repository, or None when there is no repository to contain in.

    Never raises. A manager that cannot be built is indistinguishable, to the caller, from one that
    was never configured — both mean "no containment available", and both must refuse the pane
    rather than surface as a spawn crash.
    """
    base = resolve_base_repo(workspace)
    if base is None:
        return None

    key = str(base.resolve())
    cached = _MANAGERS.get(key)
    if cached is not None:
        return cached
    try:
        manager = WorktreeManager(base, on_event)
    except (WorktreeError, OSError):
        return None
    _MANAGERS[key] = manager
    return manager
