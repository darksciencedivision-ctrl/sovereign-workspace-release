"""An INTERACTIVE OpenCode pane — the coding slot the operator picks and loads a model into.

EPC-04. The operator's ask:

    "I want open code, the harness, an available slot to be picked in one of the terminals, and
     then I'll load a model into it."

WHY THIS EXISTS BESIDE `harness.py` RATHER THAN INSIDE IT. That module builds
`opencode run … <prompt>` — one prompt in, JSON out. It is the right shape for the DRIVER, which
hands OpenCode a task and reads back what changed. It is the wrong shape for a terminal: a pane is
something the operator types into, repeatedly, and watches.

MEASURED on the operator's host before this was written, because whether an interactive mode
exists at all is a fact about the installed binary and not something to assume (opencode 1.18.25):

    opencode [project]        start opencode tui                         [default]
    -m, --model               model to use in the format of provider/model
    --pure                    run without external plugins
    --auto                    auto-approve permissions that are not explicitly denied (dangerous!)

So the TUI is the DEFAULT command and takes the project directory positionally. That is exactly a
ConPTY pane, and it is why this is a command builder rather than a redesign.

WHAT IS INHERITED, NOT REBUILT. `_require_local_model` and the credential scrub are applied
unchanged from `harness.py`. They are the reason an OpenCode pane spends nothing: the model is
pinned to the workspace's own loopback llama.cpp provider, every cloud provider credential is
stripped from the child environment, and any endpoint that is not loopback is dropped so a "local"
model cannot be routed off-box. Re-implementing either here would be a second copy of the spend
wall, and the two would drift.

WHAT THIS DOES NOT DO. It builds argv. The ConPTY spawn, the worktree, the residency reservation
and the supervised admission all stay with the caller — the same division `ollama_session.py`
keeps, and for the same reason: a command builder that could also spawn is a command builder that
can bypass the gates.

MEASURED on this host against the supervised router (opencode 1.18.x, `--format json`): a ref of
`sovereign-llamacpp/<router id>` returns text with `"cost":0`, and it does so for a router id the
provider config never listed — the openai-compatible provider passes the id through. That is why
the coding pane can be offered the whole runnable catalog rather than the handful of models
somebody happened to write into a config file by hand.
"""
from __future__ import annotations

from pathlib import Path

from adapters.cmd_shim import assert_cmd_shim_argv_safe
from adapters.coding.opencode.harness import (
    ModelNotLocal,
    _require_local_model,
    local_model_ref,
)

#: The adapter id for a local OpenCode coding pane. Distinct from `ollama_local`: both run local
#: models, but one is a bare REPL and the other is a harness with WRITE HANDS inside a worktree.
#: A single id for both would make the node record unable to say which one it is describing.
OPENCODE_LOCAL_ADAPTER = "opencode_local"


def build_interactive_opencode_command(
    executable: str,
    *,
    worktree: str | Path,
    model: str,
    pure: bool = True,
    auto: bool = False,
) -> list[str]:
    """Argv for an interactive OpenCode session pinned to `worktree` and a local model.

    `auto` defaults to FALSE and that is a containment decision, not a preference. OpenCode's own
    help calls `--auto` "auto-approve permissions that are not explicitly denied (dangerous!)". A
    coding pane is a model with write hands; the operator approving each permission is the whole
    reason the pane is safe to offer. A caller may pass True, and doing so is that caller's
    disclosure to make.

    `pure` defaults to TRUE: external plugins are code this workspace has not measured and cannot
    vouch for, running beside a model that can edit files.
    """
    exe = (executable or "").strip()
    if not exe:
        # No `or "opencode"` fallback. That is the `exe = resolved or "claude"` shape the
        # worker-pane `binary_unresolved` gate exists to close: a blank executable becomes a BARE
        # NAME the shell PATH-searches at spawn time, so what runs is whatever the PATH says
        # rather than what was resolved and checked.
        raise ValueError("an interactive OpenCode session needs a resolved executable — fail closed")

    root = str(worktree or "").strip()
    if not root:
        raise ValueError(
            "an interactive OpenCode session needs a worktree — a coding pane without one is a "
            "model with write hands and no containment (fail closed)")
    if root.startswith("-"):
        raise ValueError(
            f"refuse to build an opencode command whose project path {root!r} would be read as a "
            f"flag (fail closed)")

    # REFUSE A PROVIDER-QUALIFIED NON-LOCAL REF BEFORE PREFIXING, not after.
    #
    # `local_model_ref` prefixes anything that does not already start with `ollama/`, so
    # `anthropic/claude-3` becomes `ollama/anthropic/claude-3` — and `_require_local_model` then
    # passes, because the string does start with the prefix. Called in that order the pin can
    # never fire; it is dead code that reads like a gate.
    #
    # The spend wall still HOLDS either way: the rewritten ref is sent to the local daemon, which
    # does not have that model, so nothing paid is ever reached. What is lost is the diagnosis. A
    # caller asking for a cloud model should be told no, not handed a local ref that fails later
    # for a reason that names the wrong thing.
    name = (model or "").strip()
    if not name:
        raise ValueError("an interactive OpenCode session needs a model — fail closed")
    if "/" in name and not name.startswith("sovereign-llamacpp/"):
        raise ModelNotLocal(
            f"model {name!r} names a non-local provider — an OpenCode pane is pinned to "
            f"`sovereign-llamacpp/*` so it can spend nothing (§2.3, fail closed). Pass a local model tag.")

    ref = local_model_ref(name)
    _require_local_model(ref)          # the §2.3 spend wall, restated at the build site

    argv: list[str] = [exe, root]
    if pure:
        argv.append("--pure")
    if auto:
        argv.append("--auto")
    argv += ["-m", ref]
    assert_cmd_shim_argv_safe(argv)
    return argv
