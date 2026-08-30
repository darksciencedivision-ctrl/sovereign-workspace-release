# utc: 2026-08-30T03:42:00Z
# producer: grok-opencode LIVE-CENSUS-20260830
# host: DESKTOP-03PTABH

# shell.md — T-RW live bytes

Entry: Start-Shell.ps1 runs `py -3.12 -B -m shell.src --port 5180` from workspace root after py/port/theme checks. Theme warns, does not refuse. Start-Shell.ps1:106-108.

Compose: `__main__.py` → server + supervisor + adapters loaded from `shell/modules/*.json`. Live start log: Modules loaded: debate, distillery, llamacpp, sovereign, sow, tokencenter.

Stop: Job Object per adapter `stop.kind=job_object`. Start-Shell.ps1 finally Stop-Process on the python pid. H-9 tests assert EXTERNAL processes are not killed.

Exception path that can leave a module alive: EXTERNAL state (H-9); Start-Shell leaving process running if port does not come up within 10s (Start-Shell.ps1:129-131). This census stopped via Stop-Process on `-m shell.src`; 5180/5175/8700 free afterward.

DEFECT-G5-1: GET /static/app.js 200 on T-RW. Not live.

T-PW supervisor.py hash differs (bb09c62b… vs acb266cf…).
