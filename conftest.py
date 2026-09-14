"""Repository-root pytest anchor.

EPC-01 P1-4 / P1-5. Before this file existed there was no way to run the product's tests
as one suite:

  * `modules/sow/conftest.py` raised `ValueError` on any item collected outside its own
    module and pytest turned that into an `INTERNALERROR` that aborted the entire run —
    including on a customer's extracted archive, where `pytest` at the root crashed rather
    than reporting. Fixed in that file.
  * Underneath the crash, five separate trees each ship a `tests/` package. Under pytest's
    default prepend import mode those collide by basename: the first `tests` package to be
    imported wins and every other module's `tests.*` submodule fails to resolve. That
    accounted for most of the 119 collection errors the crash was hiding.
  * Several modules import their own top-level packages (`distillery.*`, `piggybank`) which
    resolve only when that module's root is on `sys.path`.

The collision is solved by `--import-mode=importlib` in `pytest.ini` beside this file, which
imports test modules without touching `sys.path` at all. This file solves the third point:
each module root is placed on `sys.path` so a module's own packages import the same way they
do when that module is tested on its own.

Running a single module directly still works and still uses that module's own configuration:
pytest resolves the nearest ini file upward from the arguments, so `cd modules/sow && pytest`
continues to use `modules/sow/pytest.ini` and never sees this file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#: Roots whose own packages must be importable. Order is deliberate and stable — a
#: non-deterministic sys.path is a non-deterministic test run.
MODULE_ROOTS = [
    ROOT,
    ROOT / "modules" / "sow",
    ROOT / "modules" / "distillery",
    ROOT / "modules" / "debate",
    ROOT / "modules" / "sovereign",
    ROOT / "modules" / "tokencenter",
]

_ON_PATH = []
for path in reversed(MODULE_ROOTS):
    if path.is_dir():
        text = str(path)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
        _ON_PATH.insert(0, text)


# EPC-01. sys.path reaches THIS process. It does not reach the subprocesses the tests spawn,
# and several suites spawn one deliberately: debate drives `app.py` through `runpy` in a child
# to prove a bad config is rejected at startup, and distillery shells out to its own CLI.
#
# Run from modules/debate, the child inherits a cwd that is already the module root and
# `from debate import ...` resolves by accident of where it was launched. Run from the
# repository root — the whole-product invocation V-5 exists to make possible — the child's cwd
# is the repository and the import fails, so THIRTEEN debate tests and TWO distillery tests
# failed only in the combined run and passed in isolation. That is precisely the class of
# defect a whole-product run is for, and it would have been invisible without one.
#
# Exporting PYTHONPATH puts the same roots in front of every child. Any value already set is
# preserved and appended after, so a caller's own PYTHONPATH is never discarded.
_existing = os.environ.get("PYTHONPATH", "")
_wanted = os.pathsep.join(_ON_PATH)
if _wanted and _wanted not in _existing:
    os.environ["PYTHONPATH"] = (
        _wanted + (os.pathsep + _existing if _existing else "")
    )


# Bind the ambiguous top-level name `tests` DETERMINISTICALLY, before collection starts.
#
# Two trees ship a `tests` package: modules/sow (whose helpers are imported as
# `tests.support`, `tests.fixtures`, `tests.unit`, `tests.live_call_guard`,
# `tests.host_prerequisites`, `tests.js_skip_policy`) and modules/distillery (whose
# `__init__.py` is a lone docstring that nothing imports). Collection runs alphabetically, so
# distillery is reached first, `tests` lands in sys.modules bound to ITS package, and every
# one of SOW's eleven `from tests.…` modules then fails to collect — sys.path order cannot
# help, because the name is already cached.
#
# Importing it here, first, settles the name once. This is additive: distillery's package is
# left exactly as it is, and nothing in distillery imports `tests` by name, so nothing there
# changes behaviour.
_SOW_TESTS = ROOT / "modules" / "sow" / "tests" / "__init__.py"
if _SOW_TESTS.is_file() and "tests" not in sys.modules:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "tests", _SOW_TESTS, submodule_search_locations=[str(_SOW_TESTS.parent)]
    )
    if _spec is not None and _spec.loader is not None:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["tests"] = _module
        _spec.loader.exec_module(_module)


# --------------------------------------------------------------------------------------
# B-3 - the suite must be honest about what an EXTRACTED ARCHIVE can prove.
#
# Measured on the shipped archive, unpacked to a folder and run with `pytest .`:
# 21 failed and 10 errors before anyone touched anything. None of them is a defect. They are
# REPOSITORY validators - they check the tree the product was BUILT from, and an extraction is
# not that tree:
#
#   * several shell out to `git` (`git archive`, `git ls-files`, `git check-ignore`), and an
#     extraction has no `.git`;
#   * `test_freeze_manifest_check` binds `.claude/agents/*`, `.claude/hooks/guard.py` and
#     `.claude/settings.json`, every one of them `export-ignore`d ON PURPOSE;
#   * `test_archive_ships_only_operator_docs` and `test_developer_identifiers_are_bounded`
#     inspect the archive, which they cannot cut from inside it.
#
# WHY THIS MATTERS MORE THAN IT LOOKS. That is the first ten minutes of a recipient's
# experience. Nothing in the archive told them those tests need a checkout, so the reasonable
# conclusion was that the release is broken. It is not - but "trust me, those 31 do not count"
# is not something a recipient can verify, and an unexplained red suite is indistinguishable
# from a real one.
#
# WHAT THIS DOES NOT DO. It never weakens a test in a CHECKOUT. The skip is conditional on
# `.git` being absent, so in the tree these tests still run and still fail if the repository
# drifts - which is the only place they can mean anything. `_assert_enumeration_is_current`
# below fails loudly if a listed id stops existing, so the list cannot rot into a silent
# blanket exemption. That is the failure mode this codebase keeps finding, most recently in
# the quarantine lane F-2 removed, and it is designed against here rather than discovered
# later.
#
# The ids are enumerated EXPLICITLY, never by glob or by directory. `module_source_registry`
# states the house rule: "Enumeration is explicit ... consumers must never infer paths by
# glob." A directory rule is how a narrow exemption silently becomes a wide one.
_GIT_ARCHIVE = "reads the repository through `git`; an extracted archive has no .git"
_EXPORT_IGNORED = "binds files that are export-ignored on purpose and are absent from any archive"
_INSPECTS_ARCHIVE = "inspects the distribution, which it cannot cut from inside the distribution"
_TRACKED_BYTES = "validates tracked bytes against the repository index"

CHECKOUT_ONLY: dict[str, str] = {
    "shell/tests/test_developer_identifiers_are_bounded.py::DeveloperIdentifiersAreBounded::test_every_disclosed_entry_still_exists_and_still_needs_disclosing": _INSPECTS_ARCHIVE,
    "shell/tests/test_developer_identifiers_are_bounded.py::DeveloperIdentifiersAreBounded::test_no_undisclosed_file_carries_a_developer_identifier": _INSPECTS_ARCHIVE,
    "shell/tests/test_developer_identifiers_are_bounded.py::DeveloperIdentifiersAreBounded::test_the_archive_was_actually_read": _INSPECTS_ARCHIVE,
    "shell/tests/test_developer_identifiers_are_bounded.py::DeveloperIdentifiersAreBounded::test_the_build_harness_does_not_ship": _INSPECTS_ARCHIVE,
    "shell/tests/test_developer_identifiers_are_bounded.py::DeveloperIdentifiersAreBounded::test_the_product_code_that_was_fixed_stays_fixed": _INSPECTS_ARCHIVE,
    "shell/tests/test_archive_ships_only_operator_docs.py::ArchiveShipsOnlyOperatorDocs::test_every_operator_facing_document_still_ships": _INSPECTS_ARCHIVE,
    "shell/tests/test_archive_ships_only_operator_docs.py::ArchiveShipsOnlyOperatorDocs::test_no_internal_build_document_ships": _INSPECTS_ARCHIVE,
    "shell/tests/test_archive_ships_only_operator_docs.py::ArchiveShipsOnlyOperatorDocs::test_the_architecture_decisions_still_ship": _INSPECTS_ARCHIVE,
    "shell/tests/test_archive_ships_only_operator_docs.py::ArchiveShipsOnlyOperatorDocs::test_the_archive_is_not_empty": _INSPECTS_ARCHIVE,
    "shell/tests/test_archive_ships_only_operator_docs.py::ArchiveShipsOnlyOperatorDocs::test_the_build_harness_launchers_do_not_ship": _INSPECTS_ARCHIVE,
    "shell/tests/test_operator_documentation_exists.py::OperatorDocumentationExists::test_the_operator_documentation_actually_ships": _INSPECTS_ARCHIVE,
    "shell/tests/test_sbom_is_generated_from_locks.py::SbomIsGeneratedFromLocks::test_check_mode_agrees_the_committed_sbom_is_current": _GIT_ARCHIVE,
    "shell/tests/test_startup_evidence.py::TestStartupEvidenceLane::test_default_record_is_ignored_runtime_evidence": _GIT_ARCHIVE,
    "tools/release/test_package_boundary_gate.py::NoLaneCoversShippedBytes::test_no_lane_matches_a_file_in_the_distribution": _GIT_ARCHIVE,
    "tools/release/test_package_boundary_gate.py::TestCleanedWorktree::test_archive_passes": _GIT_ARCHIVE,
    "tools/release/test_release_manifest_check.py::HandledSectionsStillValidateTests::test_real_manifest_still_passes_after_hardening": _TRACKED_BYTES,
    "tools/release/test_release_manifest_check.py::ManifestValidatorTests::test_real_manifest_passes": _TRACKED_BYTES,
    "tools/release/test_runtime_writes_are_gitignored.py::RuntimeWritesLeaveTheTrackedTree::test_a_rotated_log_generation_is_gitignored_too": _GIT_ARCHIVE,
    "modules/sow/tests/unit/test_freeze_manifest_check.py::test_each_D1_provenance_bound_file_is_tracked_and_present[.claude/agents/gate-validator.md]": _EXPORT_IGNORED,
    "modules/sow/tests/unit/test_freeze_manifest_check.py::test_each_D1_provenance_bound_file_is_tracked_and_present[.claude/agents/spec-auditor.md]": _EXPORT_IGNORED,
    "modules/sow/tests/unit/test_freeze_manifest_check.py::test_each_D1_provenance_bound_file_is_tracked_and_present[.claude/hooks/guard.py]": _EXPORT_IGNORED,
    "modules/sow/tests/unit/test_freeze_manifest_check.py::test_each_D1_provenance_bound_file_is_tracked_and_present[.claude/settings.json]": _EXPORT_IGNORED,
    "modules/sow/tests/unit/test_mcp_registration_provenance.py::test_the_codex_registration_pins_the_mcp_server_working_directory": _GIT_ARCHIVE,
    "modules/sow/tests/unit/test_mcp_registration_provenance.py::test_the_registration_is_wired_from_the_repo_not_handwritten": _GIT_ARCHIVE,
    "modules/sow/tests/unit/test_text_integrity.py::test_no_tracked_text_file_carries_a_utf8_BOM": _TRACKED_BYTES,
    "modules/sow/tests/unit/test_text_integrity.py::test_no_tracked_text_file_differs_from_its_blob_by_line_endings": _TRACKED_BYTES,
    "modules/distillery/tests/test_operator_cli.py::OperatorCliTests::test_status_and_validate_and_hg3_preflight_are_honest": _GIT_ARCHIVE,
    "modules/distillery/tests/test_raw_source_classification.py::RawSourceClassificationTests::test_every_tracked_file_receives_exactly_one_non_ambiguous_class": _GIT_ARCHIVE,
    "modules/distillery/tests/test_raw_source_classification.py::RawSourceClassificationTests::test_historically_ambiguous_files_resolve_by_rule": _GIT_ARCHIVE,
    "modules/distillery/tests/test_version_identity.py::VersionIdentityTests::test_cli_version_command_exposes_identity": _GIT_ARCHIVE,
    "modules/distillery/tests/test_version_identity.py::VersionIdentityTests::test_resolve_identity_verifies_bundle_and_evidence_paths": _GIT_ARCHIVE,
}


def _is_git_checkout() -> bool:
    """True in a clone or a linked worktree. `.git` is a directory in one and a FILE in the
    other, so existence is the test rather than `is_dir()`."""
    return (ROOT / ".git").exists()


def _files_selected_by_node_id(args) -> set:
    """Files named on the command line with a `::` node-id suffix, as repository-relative paths.
    Such a run collects only the named ids, so the rest of that file's listed ids are absent by
    selection, not by rename."""
    selected = set()
    for arg in args or ():
        text = str(arg)
        if "::" not in text:
            continue
        path = Path(text.split("::", 1)[0])
        try:
            path = path.resolve().relative_to(ROOT)
        except (OSError, ValueError):
            pass
        selected.add(path.as_posix())
    return selected


def _assert_enumeration_is_current(collected: set, selected_by_id: set | None = None) -> None:
    """A listed id that no longer exists is a rename, and a stale exemption list is how a
    narrow skip quietly becomes a blanket one. Checked per FILE so a partial run
    (`pytest shell/tests`) does not trip on ids it never collected - and a file selected by
    node id (`pytest file.py::Test::one`) is skipped for the same reason: it aborted every
    targeted rerun of a test sharing a file with a listed id."""
    files_seen = {nid.split("::", 1)[0] for nid in collected} - (selected_by_id or set())
    stale = [nid for nid in CHECKOUT_ONLY
             if nid.split("::", 1)[0] in files_seen and nid not in collected]
    if stale:
        raise RuntimeError(
            "conftest.CHECKOUT_ONLY is stale — these ids no longer exist, so they are "
            "exempting nothing and hiding a rename:\n  " + "\n  ".join(stale))


def pytest_configure(config):  # noqa: D401
    config.addinivalue_line(
        "markers",
        "checkout_only: validates the repository rather than the product; skipped in an "
        "extracted archive, always run in a checkout")


def pytest_collection_modifyitems(config, items):
    checkout = _is_git_checkout()
    collected = set()
    for item in items:
        nodeid = item.nodeid.replace(os.sep, "/")
        reason = CHECKOUT_ONLY.get(nodeid)
        if reason is None:
            continue
        collected.add(nodeid)
        item.add_marker("checkout_only")
        if not checkout:
            import pytest  # noqa: PLC0415 - only needed on this branch

            item.add_marker(pytest.mark.skip(
                reason=f"repository validator: {reason}. Run it from a git checkout — "
                       f"see docs/INSTALL.md, 'Running the test suite'."))
    if checkout:
        _assert_enumeration_is_current(collected, _files_selected_by_node_id(config.args))
