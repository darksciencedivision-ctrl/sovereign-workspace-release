# Start-OpenCode.ps1 - operator tooling. Full auto-approval OpenCode in the Production Workspace.
# --auto approves every request that is not explicitly denied; opencode.json sets permission=allow.
# No preconditions, no checks, no blocking.

$Workspace = "D:\Product Software\Production Workspace"

Set-Location -LiteralPath $Workspace
Write-Host "OpenCode starting in $Workspace with --auto (no permission prompts)."
& opencode --auto
