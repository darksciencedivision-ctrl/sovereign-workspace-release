"""L-1 / N-03 — .cmd-shim argv must refuse cmd.exe metacharacters.

INDEPENDENT_REVIEW_WINDOWS_HOST_20260816 N-03: `list2cmdline` quoting does not
stop `& | ^ < > %` from executing through a `.cmd` shim. These tests pin the
construction-site guard; they spawn nothing.
"""
from __future__ import annotations

import pytest

from adapters.cmd_shim import (
    CMD_SHIM_METACHARS,
    CmdShimMetacharacter,
    assert_cmd_shim_argv_safe,
)
from adapters.frontier.process_tree import run_managed_process
from adapters.frontier.provider_cli_common import FrontierProviderCliBackend


HOSTILE = ("&", "|", "^", "<", ">", "%")


def test_the_hostile_class_is_exactly_the_n03_payloads() -> None:
    assert CMD_SHIM_METACHARS == frozenset("&|^<>%")


@pytest.mark.parametrize("ch", HOSTILE)
def test_a_cmd_shim_argv_carrying_a_hostile_payload_is_refused(ch: str) -> None:
    argv = [r"C:\npm\claude.cmd", "--cwd", rf"C:\x\R{ch}echo INJECTED"]
    with pytest.raises(CmdShimMetacharacter) as caught:
        assert_cmd_shim_argv_safe(argv)
    assert ch in str(caught.value)


@pytest.mark.parametrize("ch", HOSTILE)
def test_a_cmd_shim_executable_path_carrying_a_hostile_payload_is_refused(ch: str) -> None:
    argv = [rf"C:\R{ch}D\grok.cmd", "-p", "hi"]
    with pytest.raises(CmdShimMetacharacter):
        assert_cmd_shim_argv_safe(argv)


def test_a_clean_cmd_shim_argv_is_allowed() -> None:
    assert_cmd_shim_argv_safe([r"C:\npm\claude.cmd", "--model", "opus", "-p", "hello"])


def test_a_non_cmd_executable_is_not_this_guard() -> None:
    argv = [r"C:\tools\claude.exe", "--cwd", r"C:\x\R&echo INJECTED"]
    assert_cmd_shim_argv_safe(argv)


def test_run_managed_process_refuses_before_spawn() -> None:
    with pytest.raises(CmdShimMetacharacter):
        run_managed_process(
            [r"C:\npm\probe.cmd", "--cwd", r"C:\x\R&echo INJECTED"],
            timeout=1.0,
            env={},
            stdin=None,
        )


def test_frontier_guard_refuses_cmd_shim_metacharacters() -> None:
    class _Probe(FrontierProviderCliBackend):
        provider = "probe"
        executable_candidates = ("probe.cmd",)

        def build_command(self, prompt: str) -> list[str]:
            return [r"C:\npm\probe.cmd", "-p", prompt]

    probe = _Probe(executable=r"C:\npm\probe.cmd")
    with pytest.raises(CmdShimMetacharacter):
        probe._guard([r"C:\npm\probe.cmd", "--cwd", r"C:\ws|evil"])
