# Sovereign node operating policy

> ## STATUS — 2026-08-16 (W-07). READ THIS BEFORE OBEYING THE POLICY BELOW.
>
> The policy below mandates the Sovereign MCP path and forbids every alternative. On this baseline
> that combination can leave a conductor **blocked forever**: if the `sovereign` MCP server is not
> ready, `spawn_worker` never returns a governed node, and the rule "wait for `spawn_worker` to
> return a ready governed node" has no exit.
>
> **What is known about the MCP path right now:**
>
> - **Repaired 2026-08-16.** The stdio transport was not UTF-8 in either direction, and the
>   `tools/list` reply contained raw `0x97` bytes, making it invalid UTF-8. A strict-UTF-8 stdio
>   client (Codex's is Rust) fails on exactly that frame while a Node client decodes lossily and
>   never notices. Re-measured after the repair: `tools/list` is **valid UTF-8, zero raw `0x97`
>   bytes**.
> - **Still open.** `mcp_server/sovereign_tools.py` is **cwd-dependent** and no MCP config pins a
>   `cwd` — `.codex/config.toml` declares `command = "py"`,
>   `args = ["-3.12", "-m", "mcp_server.sovereign_tools"]` and nothing else, so a launcher whose cwd
>   is not the repository root gets `ModuleNotFoundError`. This is an open candidate for the same
>   failure and is **not** fixed.
> - Therefore: **whether the MCP path works end to end is not established.** It has not been
>   re-verified by a live conductor bring-up since the transport repair.
>
> **If `spawn_worker` does not return a ready governed node: do not loop, and do not fall back to a
> shell.** Stop, report the failure to the operator, and use the operator-facing sequence in
> [`docs/operator/PATH_A_PROVIDER_UNBLOCK_SHEET.md`](docs/operator/PATH_A_PROVIDER_UNBLOCK_SHEET.md).
> Launching a provider CLI from a shell to work around a broken MCP path produces exactly the naked
> session invariant 2 forbids — the prohibition below is not suspended by this notice.

When this repository is opened inside the Sovereign Electron application, use the connected
`sovereign` MCP server for application operations and node collaboration.

- Worker creation, worker termination, task assignment, status queries, node communication,
  progress, artifacts, and debate operations must use Sovereign MCP tools.
- Never create provider workers through `Start-Process`, `ShellExecute`, `cmd.exe /k`,
  `powershell.exe`, detached terminals, or provider CLIs launched from a shell.
- A conductor must wait for the Sovereign `spawn_worker` MCP tool to return a ready governed node before claiming
  that worker exists.
- Workers must publish meaningful progress and candidate results through MCP. Terminal output is for
  operator transparency and is not the authoritative coordination record.
- Node-to-node communication must stay within the assigned project/task and use messages, evidence
  references, artifact references, and bounded debate turns rather than full transcript forwarding.
