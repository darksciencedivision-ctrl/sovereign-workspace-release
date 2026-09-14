"""SW-ORCH-001 F-22 — a stored conductor workspace is validated against THIS install.

The measured defect (operator host, 2026-09-05): `.runtime/conductor-selection.json` carried the
absolute literal `D:\\producttion software 2\\release-worktree\\modules\\sow` in BOTH installs,
because the file was copied along with the tree. `descriptor_from_mapping` passed it through
verbatim, `emit_conductor_launch` emitted it as the ConPTY `cwd`, and one session ran its worker
panes in `production software 3` while its conductor ran in `producttion software 2`.

These tests pin the containment, the honest report, and — the part that actually bit — the
component-wise comparison. §3.1a of the directive records why a string prefix cannot be used: on
this operator's disk `D:\\producttion` is a character-prefix of `D:\\producttion software 2`.
"""
from __future__ import annotations

import json

import pytest

from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER
from control_plane.conductor.registry import (
    _within_install,
    descriptor_from_mapping,
    load_runtime_conductor_descriptor,
)

#: A registered local conductor combination, so these tests exercise the workspace decision rather
#: than the registry lookup that precedes it.
LOCAL_MODEL = "granite4.2:3b"


class _Admitted:
    """The shape `adapters.local.model_ceiling` returns, reduced to what the registry reads."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.admitted = True


@pytest.fixture(autouse=True)
def _host_offers_the_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local conductor seats are enumerated from the live Ollama daemon. Without this the model
    above was "registered" only while the operator's daemon happened to be serving it, and every
    test here failed closed on the registry lookup on any host without it — never reaching the
    workspace decision they exist to pin. An explicitly injected verdict list is left alone."""
    import control_plane.conductor.registry as registry

    real = registry._local_conductor_registrations
    monkeypatch.setattr(
        registry, "_local_conductor_registrations",
        lambda verdicts=None: real([_Admitted(LOCAL_MODEL)] if verdicts is None else verdicts))


def _selection(workspace: str | None) -> dict[str, object]:
    raw: dict[str, object] = {
        "provider_id": OLLAMA_LOCAL_ADAPTER,
        "adapter_id": OLLAMA_LOCAL_ADAPTER,
        "model_id": LOCAL_MODEL,
        "permission_profile_id": "pp-conductor-pane",
    }
    if workspace is not None:
        raw["workspace"] = workspace
    return raw


# --- the measured defect -----------------------------------------------------------------------

def test_stored_workspace_outside_this_install_is_refused(tmp_path) -> None:
    """The exact shape measured on the operator's host: a workspace naming another install."""
    install = tmp_path / "production software 3" / "release-worktree" / "modules" / "sow"
    other = tmp_path / "producttion software 2" / "release-worktree" / "modules" / "sow"
    install.mkdir(parents=True)
    other.mkdir(parents=True)

    desc = descriptor_from_mapping(_selection(str(other)), workspace=str(install))

    assert desc.workspace == str(install)
    assert desc.workspace_refusal is not None
    # BOTH paths named — an operator told only "refused" cannot tell which install they are in.
    assert str(other) in desc.workspace_refusal
    assert str(install) in desc.workspace_refusal
    assert desc.selection_source.endswith("+workspace_refused")


def test_stored_workspace_inside_this_install_is_honoured_unchanged(tmp_path) -> None:
    install = tmp_path / "install"
    inner = install / "modules" / "sow"
    inner.mkdir(parents=True)

    desc = descriptor_from_mapping(_selection(str(inner)), workspace=str(install))

    assert desc.workspace == str(inner)
    assert desc.workspace_refusal is None
    assert "+workspace_refused" not in desc.selection_source


def test_the_install_root_itself_is_contained(tmp_path) -> None:
    """Exact-root handling is explicit, not incidental."""
    install = tmp_path / "install"
    install.mkdir()
    desc = descriptor_from_mapping(_selection(str(install)), workspace=str(install))
    assert desc.workspace == str(install)
    assert desc.workspace_refusal is None


# --- §3.1a: the prefix-confusion shape that exists on the real disk ------------------------------

def test_sibling_root_that_is_a_character_prefix_is_not_contained(tmp_path) -> None:
    """`D:\\producttion` vs `D:\\producttion software 2` — the live §3.1a shape.

    A `startswith` containment test admits the second as "inside" the first. This is the single
    most important negative in this module: it is not synthetic, it is the operator's actual disk.
    """
    short = tmp_path / "producttion"
    longer = tmp_path / "producttion software 2"
    short.mkdir()
    longer.mkdir()

    assert not _within_install(str(longer), str(short))
    assert not _within_install(str(short), str(longer))

    desc = descriptor_from_mapping(_selection(str(longer)), workspace=str(short))
    assert desc.workspace == str(short)
    assert desc.workspace_refusal is not None


def test_trailing_separator_and_case_do_not_change_containment(tmp_path) -> None:
    install = tmp_path / "install"
    inner = install / "modules"
    inner.mkdir(parents=True)
    assert _within_install(str(inner) + "\\", str(install))
    assert _within_install(str(inner) + "/", str(install))


# --- fail-closed negatives ----------------------------------------------------------------------

def test_traversal_escaping_the_install_is_refused(tmp_path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    (tmp_path / "elsewhere").mkdir()

    escape = str(install / ".." / "elsewhere")
    assert not _within_install(escape, str(install))

    desc = descriptor_from_mapping(_selection(escape), workspace=str(install))
    assert desc.workspace == str(install)
    assert desc.workspace_refusal is not None


def test_mixed_separators_resolve_to_the_same_containment_answer(tmp_path) -> None:
    install = tmp_path / "install"
    inner = install / "modules" / "sow"
    inner.mkdir(parents=True)

    mixed = f"{install}\\modules/sow"
    assert _within_install(mixed, str(install))

    outside_mixed = f"{tmp_path}\\elsewhere/sow"
    assert not _within_install(outside_mixed, str(install))


def test_an_unresolvable_workspace_is_not_contained(tmp_path) -> None:
    """Fail closed: an unreadable location is not evidence of containment."""
    install = tmp_path / "install"
    install.mkdir()
    assert not _within_install("\x00not-a-path", str(install))


def test_empty_or_absent_stored_workspace_uses_the_install_root(tmp_path) -> None:
    install = tmp_path / "install"
    install.mkdir()

    absent = descriptor_from_mapping(_selection(None), workspace=str(install))
    assert absent.workspace == str(install)
    assert absent.workspace_refusal is None

    blank = descriptor_from_mapping(_selection("   "), workspace=str(install))
    assert blank.workspace == str(install)
    # A blank field is not a REFUSAL — nothing was rejected, there was nothing there.
    assert blank.workspace_refusal is None


# --- U331 regression: a stale preference must not make the conductor unresolvable ----------------

def test_a_refused_workspace_still_yields_a_usable_descriptor(tmp_path) -> None:
    """The U331 property, extended to this repair.

    `load_runtime_conductor_descriptor` already refuses to let a stale preference take the whole
    conductor down (it falls through to the recorded default). A workspace refusal must be no
    different: it changes WHERE the conductor runs, never WHETHER one can be resolved.
    """
    install = tmp_path / "install"
    install.mkdir()
    desc = descriptor_from_mapping(_selection("D:\\somewhere\\else"), workspace=str(install))

    assert desc.role == "conductor"
    assert desc.model_id == LOCAL_MODEL
    assert desc.workspace == str(install)
    assert desc.conductor_capable


def test_absent_local_selection_file_still_resolves(tmp_path) -> None:
    """Unchanged U331 behaviour — pinned here because this repair touches the same function."""
    desc = load_runtime_conductor_descriptor(tmp_path / "no-such-live_operation.json")
    assert desc.selection_source == "recorded_default_selection"
    assert desc.workspace_refusal is None


def test_malformed_stored_selection_is_not_an_object(tmp_path) -> None:
    with pytest.raises(Exception):
        descriptor_from_mapping(json.loads("[]"), workspace=str(tmp_path))
