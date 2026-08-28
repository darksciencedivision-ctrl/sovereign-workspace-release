# Phase 1 Spike Report — 2026-07-17T02:27:13.486Z
Environment: {"platform":"win32","release":"10.0.26200","arch":"x64","cpus":20,"totalMemMB":65231,"node":"20.18.0","electron":"31.7.7","chrome":"126.0.6478.234","scenarioHost":"D:\\Program Files\\nodejs\\node.exe"}

## Verdict
**NO KILL CRITERIA TRIGGERED: evidence supports recommending Electron for D-UI-01 (operator ratifies)**

## Kill criteria
| Criterion | Value | Triggered |
|---|---|---|
| p95 input latency >= 50 ms sustained | 1.8772 | false |
| output loss (streamer SEQ gaps) | 0 | false |
| RAM above budget (2048 MB, Electron processes) | 587 | false |
| input crosses to the wrong pane | 0 | false |
| layout changes restart/corrupt sessions | {"mutations":20,"expectedAlive":["s1","s2","s3","s4","s5","s6"],"gapsBefore":0,"allAlive":true,"newGaps":0} | false |
| instability at 6 terminals (unexpected session deaths) | [] | false |
| resize unreliable (TUI never matches requested dims) | "29/56 ok" | false |
| process lifecycle not supervisable | {"ok":true,"checked":8,"missing":[]} | false |
| ConPTY ownership not safely containable | {"ok":true,"alivePtyPids":[],"orphanConsoleHosts":[],"scanError":null} | false |

## Latency (main-process echo path)
`{"n":190,"timeouts":0,"min":0.1717,"p50":0.6412,"p95":1.8772,"p99":3.274,"max":3.7842,"mean":0.8084178947368422}`

## Latency (renderer paint)
`{"n":0,"p50":null,"p95":null,"p99":null}`

## Streamer integrity
`{"received":1460030,"gaps":0,"dupes":0,"restarts":16,"last":1459864}`

## Resource envelope by pane count
`{"0":{"samples":2,"peakRssMB":448,"peakCpuPct":0.5,"meanRssMB":447,"meanCpuPct":0.3},"6":{"samples":55,"peakRssMB":470,"peakCpuPct":1.5000000000000002,"meanRssMB":454,"meanCpuPct":0.6},"8":{"samples":31,"peakRssMB":587,"peakCpuPct":1.5000000000000002,"meanRssMB":496,"meanCpuPct":1}}`

## Layout storm
`{"mutations":20,"expectedAlive":["s1","s2","s3","s4","s5","s6"],"gapsBefore":0,"allAlive":true,"newGaps":0}`

## Resize checks
- s3: req 55x15 rep 100x30 ok=false
- s3: req 55x15 rep 100x30 ok=false
- s3: req 55x15 rep 55x15 ok=true
- s3: req 76x16 rep 55x15 ok=false
- s3: req 76x16 rep 76x16 ok=true
- s3: req 60x21 rep 76x16 ok=false
- s3: req 60x21 rep 60x21 ok=true
- s3: req 93x22 rep 60x21 ok=false
- s3: req 93x22 rep 93x22 ok=true
- s3: req 106x19 rep 93x22 ok=false
- s3: req 106x19 rep 106x19 ok=true
- s3: req 71x25 rep 106x19 ok=false
- s3: req 71x25 rep 71x25 ok=true
- s3: req 92x20 rep 71x25 ok=false
- s3: req 92x20 rep 92x20 ok=true
- s3: req 96x17 rep 92x20 ok=false
- s3: req 96x17 rep 96x17 ok=true
- s3: req 85x26 rep 96x17 ok=false
- s3: req 85x26 rep 85x26 ok=true
- s3: req 80x34 rep 85x26 ok=false
- s3: req 80x34 rep 80x34 ok=true
- s3: req 85x28 rep 80x34 ok=false
- s3: req 85x28 rep 85x28 ok=true
- s3: req 55x17 rep 85x28 ok=false
- s3: req 55x17 rep 55x17 ok=true
- s3: req 55x17 rep 55x17 ok=true
- s3: req 171x37 rep 55x17 ok=false
- s3: req 171x37 rep 55x17 ok=false
- s3: req 171x37 rep 171x37 ok=true
- s3: req 171x37 rep 171x37 ok=true
- s3: req 171x37 rep 171x37 ok=true
- s3: req 171x37 rep 171x37 ok=true
- s3: req 171x37 rep 171x37 ok=true
- s3: req 70x31 rep 171x37 ok=false
- s3: req 70x31 rep 70x31 ok=true
- s3: req 108x27 rep 70x31 ok=false
- s3: req 108x27 rep 70x31 ok=false
- s3: req 108x27 rep 108x27 ok=true
- s3: req 108x34 rep 108x27 ok=false
- s3: req 108x34 rep 108x34 ok=true
- s3: req 81x32 rep 108x34 ok=false
- s3: req 81x32 rep 81x32 ok=true
- s3: req 90x25 rep 81x32 ok=false
- s3: req 90x25 rep 90x25 ok=true
- s3: req 85x17 rep 90x25 ok=false
- s3: req 85x17 rep 85x17 ok=true
- s3: req 78x29 rep 85x17 ok=false
- s3: req 78x29 rep 78x29 ok=true
- s3: req 75x25 rep 78x29 ok=false
- s3: req 75x25 rep 75x25 ok=true
- s3: req 105x29 rep 75x25 ok=false
- s3: req 105x29 rep 105x29 ok=true
- s3: req 65x22 rep 105x29 ok=false
- s3: req 65x22 rep 65x22 ok=true
- s3: req 171x37 rep 65x22 ok=false
- s3: req 171x37 rep 171x37 ok=true

*Gate reminder: Phase 1 exit = OPERATOR ratifies D-UI-01. This report is evidence, not a decision.*