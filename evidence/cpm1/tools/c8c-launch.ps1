# utc: 2026-08-26T22:02:00Z
# producer: ox-alpha CP-M1 ADD-08 C-8(c) builder tooling
# C-8(c): cmd /c start "" /B — no Start-Process, no -PassThru, no handle.
param(
  [Parameter(Mandatory = $true)][string]$Exe,
  [Parameter(Mandatory = $true)][string]$Arg,
  [Parameter(Mandatory = $true)][string]$OutFile,
  [Parameter(Mandatory = $true)][string]$ErrFile,
  [string]$ExtraArgs = ""
)
$q = [char]34
$line = "start " + $q + $q + " /B " + $q + $Exe + $q + " " + $q + $Arg + $q
if ($ExtraArgs) { $line = $line + " " + $ExtraArgs }
$line = $line + " > " + $q + $OutFile + $q + " 2> " + $q + $ErrFile + $q
cmd.exe /c $line
exit $LASTEXITCODE
