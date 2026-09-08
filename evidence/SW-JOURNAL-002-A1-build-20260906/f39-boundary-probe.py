# utc: 2026-09-06T17:57:45.553915+00:00
# producer: Codex F-39 boundary probe

from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[2]
js = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const base = 'modules/sow/apps/desktop/';
const main = fs.readFileSync(base + 'main.js', 'utf8');
const start = main.indexOf('  const EXECUTION_TYPES = Object.freeze(');
const end = main.indexOf('    ipcMain.handle("pane:new"', start);
assert.ok(start >= 0 && end > start);
let handler, launches = 0;
const pane = {state:'EMPTY', backend:'none', modelRef:null, pid:null};
const sandbox = {ipcMain:{handle:(name, fn)=>{assert.equal(name,'pane:select-execution');handler=fn;}},
  emptyPanes:new Map([['pane-2',pane]]), persistLayoutSnapshot(){}, pushState(){},
  spawnFromSelection(){launches++;}, workerLauncher(){launches++;throw Error('unexpected launch');}};
vm.runInNewContext(main.slice(start,end),sandbox);
const configured = handler(null,{id:'pane-2',executionType:'powershell'});
assert.equal(configured.state,'CONFIGURING'); assert.equal(configured.modelRef,null);
assert.equal(configured.pid,null); assert.equal(launches,0);
console.log('selectExecution powershell: CONFIGURING, modelRef=null, pid=null, launch calls=0');
const source = require('./' + base + 'picker/launch-source');
const fixtureSource = fs.readFileSync(base+'test/worker-launch-source.test.js','utf8');
const from=fixtureSource.indexOf('const FRONTIER_TICKET = {'),to=fixtureSource.indexOf('const REFUSAL = {',from);
assert.ok(from>=0 && to>from);
const fixture = vm.runInNewContext(fixtureSource.slice(from,to)+'; LOCAL_TICKET',
 {WORKER_TICKET_SCHEMA:source.WORKER_TICKET_SCHEMA,REPO_ROOT:process.cwd(),SESSION:'pane-2#77.1',PANE:'pane-2'});
assert.equal(source.isWellFormedWorkerTicket(fixture),true);
const shell = structuredClone(fixture);
shell.chrome.adapter='powershell'; shell.chrome.provider='powershell'; shell.chrome.model_label=null;
shell.launch.argv=['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'];
shell.launch.executable=shell.launch.argv[0];
assert.equal(source.isWellFormedWorkerTicket(shell),false);
assert.equal(Object.values(source.ADAPTER_EXECUTABLE).includes('powershell'),false);
console.log('existing local-model fixture accepted; PowerShell ticket rejected by same validator');
console.log('allowed adapter executables: '+JSON.stringify(source.ADAPTER_EXECUTABLE));
const py=fs.readFileSync('modules/sow/node_runtime/supervisor/worker_pane_spawn.py','utf8');
const pfrom=py.indexOf('def authorize_worker_pane('),pto=py.indexOf('# ---- frontier:',pfrom);
assert.ok(pfrom>=0 && pto>pfrom);
const dispatch=py.slice(pfrom,pto);
assert.ok(dispatch.includes('gate=GATE_UNKNOWN_ADAPTER'));
assert.equal(dispatch.includes('powershell'),false);
console.log('Python authorize_worker_pane: no PowerShell branch, ends in unknown_adapter refusal');
"""
result = subprocess.run(['node', '-'], input=js, text=True, cwd=root, capture_output=True)
print(result.stdout, end='')
print(result.stderr, end='')
raise SystemExit(result.returncode)
