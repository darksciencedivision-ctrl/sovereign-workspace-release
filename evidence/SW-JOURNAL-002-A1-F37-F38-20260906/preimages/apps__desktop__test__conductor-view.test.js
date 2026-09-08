"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), Module = require("node:module");
const { spawnSync } = require("node:child_process");
const J = require("../control/workspace-journal");
const V = require("../control/conductor-view");
const { defaultPython, defaultPythonArgs } = require("../python-runtime");
// Profiles are computed by the SAME Python function, on stub hosts; no local model is queried.
const script = "import importlib.util,json; s=importlib.util.spec_from_file_location('j','apps/desktop/control/journal-store.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps([m.budget({'vram_mib':8151}),m.budget({'vram_mib':7400})]))";
const child=spawnSync(defaultPython(),[...defaultPythonArgs(),"-B","-c",script],
  {cwd:path.resolve(__dirname,"../../.."),encoding:"utf8",windowsHide:true});
assert.equal(child.status,0,child.stderr);
const [large,small]=JSON.parse(child.stdout);
function entry(id,text="worker answer") {
  return J.prepareEntry({node_id:"node-"+id,pane_id:"pane-"+id,model:"model-"+id,status:"answered",
    objective:"compare",prompt:"question",answer:text,source:J.SOURCE,self_published:false},
    "session-test",()=>"2026-09-06T00:00:00Z");
}
const e2=entry(2),e3=entry(3);
test("F-28: pane mention retrieves only that pane and labels attribution",()=>{
  const v=V.composeView("What is pane-3 doing?",[e2,e3],large);
  assert.match(v.view,/pane=pane-3/);assert.doesNotMatch(v.view,/pane=pane-2/);
  for(const s of ["node=node-3","model=model-3","time=2026-09-06","observed_pane_output",
    "self_published=false","U58 OWED"]) assert.ok(v.view.includes(s),s);
  assert.ok(v.message.length<=V.characterBudget(large));
});
test("F-28: shrinking the stub host shrinks the received view and explicitly truncates",()=>{
  const entries=[entry(2,"a".repeat(20000)),entry(3,"b".repeat(20000))];
  const a=V.composeView("combine those two answers",entries,large);
  const b=V.composeView("combine those two answers",entries,small);
  assert.ok(b.view.length<a.view.length);assert.ok(b.message.length<=V.characterBudget(small));
  assert.match(b.message,/TRUNCATED/);assert.equal(b.truncated,true);
  assert.match(a.view,/pane=pane-2/);assert.match(a.view,/pane=pane-3/);
});
test("F-28: unavailable journal states absence in what the conductor receives",async()=>{
  let written;
  const result=await V.retrieveAndDeliver({message:"compare workers",journal:{entries:async()=>{throw Error()}},
    budgetSource:async()=>large,write:async s=>{written=s;return {written:true,submitted:true}}});
  assert.match(written,/Worker journal unavailable/);assert.ok(written.startsWith("compare workers"));
  assert.equal(result.written,true);
});
test("F-28: unused rule does no store, observation, or host work; explicit rule is observable",async()=>{
  let calls=0,written;
  const result=await V.retrieveAndDeliver({message:"hello",journal:{entries:()=>calls++},
    budgetSource:()=>calls++,write:async s=>{written=s;return {written:true}}});
  assert.equal(calls,0);assert.equal(written,"hello");assert.equal(result.context.attached,false);
  assert.match(result.context.rule,/\/workspace/);assert.equal(V.wantsView("/workspace"),true);
});
test("F-28: missing and unreadable entries are named instead of silent gaps",()=>{
  assert.match(V.composeView("pane-9",[e2],large).view,/pane-9: no readable retained/);
  assert.match(V.composeView("workers",[{pane_id:"pane-3",unreadable:true}],large).view,/UNREADABLE entry: pane-3/);
});
test("F-28: runtime unknown budget refuses observations without guessing",async()=>{
  let reads=0;
  const r=await V.retrieveAndDeliver({message:"workers",budgetSource:async()=>({available:false}),
    journal:{entries:async()=>{reads++;return []}},write:async()=>({written:true})});
  assert.equal(reads,0);assert.equal(r.context.attached,false);
  assert.match(r.context.notice,/budget_unmeasurable/);
});
test("F-28: a message beyond the computed budget is refused before the writer",async()=>{
  let writes=0;
  const r=await V.retrieveAndDeliver({message:"workers "+"x".repeat(4000),budgetSource:async()=>small,
    journal:{},write:async()=>{writes++}});
  assert.equal(writes,0);assert.equal(r.written,false);assert.match(r.reason,/TRUNCATED/);
});
test("F-28: nondelegated panes go through journal observation; view delivery gets a receipt",async()=>{
  const rows=[],receipts=[];let observed=false;
  const journal={sessionId:"session-test",entries:async()=>rows,
    observe:async(_w,panes,budget)=>{observed=true;assert.equal(panes[0].pane_id,"pane-3");
      assert.ok(budget<=V.characterBudget(large));rows.push(e3)},
    record:async e=>receipts.push(e)};
  const result=await V.retrieveAndDeliver({message:"pane-3",journal,window:{},panes:[{pane_id:"pane-3"}],
    budgetSource:async()=>large,write:async()=>({written:true,submitted:true})});
  assert.equal(observed,true);assert.equal(result.context.attached,true);
  assert.deepEqual(receipts.map(e=>e.status),["view_prepared","view_delivered"]);
  assert.equal(receipts[1].answer,result.context.view);
  assert.equal(receipts[1].self_published,false);assert.equal(receipts[1].source,J.SOURCE);
});
test("F-28: view receipts are excluded from future retrieval",()=>{
  const recorded=entry(2);recorded.status="view_delivered";recorded.answer="recursive";
  const v=V.composeView("workers",[recorded,e3],large);
  assert.doesNotMatch(v.view,/recursive/);assert.match(v.view,/pane=pane-3/);
});
test("F-28 mutation control: removing the computed budget clamp permits an oversized view",()=>{
  const filename=require.resolve("../control/conductor-view"),source=fs.readFileSync(filename,"utf8");
  const anchor='const limit = Math.max(0, budget - message.length - separator.length);';
  assert.ok(source.includes(anchor));
  const mutant=new Module(filename,module);mutant.filename=filename;
  mutant.paths=Module._nodeModulePaths(path.dirname(filename));
  mutant._compile(source.replace(anchor,"const limit = Number.MAX_SAFE_INTEGER;"),filename);
  const raw={...e2,answer:"KEY ".repeat(2000)};
  const normal=V.composeView("workers",[raw],small), changed=mutant.exports.composeView("workers",[raw],small);
  assert.ok(normal.message.length<=V.characterBudget(small));
  assert.ok(changed.message.length>V.characterBudget(small));
});

test("F-28: unused chat never constructs the runtime journal",async()=>{
  let sourceCalls=0;
  const r=await V.retrieveAndDeliver({message:"hello",journalSource:()=>{sourceCalls++;throw Error()},
    budgetSource:()=>{throw Error()},write:async s=>({written:s==="hello"})});
  assert.equal(r.written,true);assert.equal(sourceCalls,0);
});

test("F-28: a full history window retains newest answers from both panes before older history",()=>{
  const newest=[entry(2,"NEWEST TWO"),entry(3,"NEWEST THREE")];
  const history=Array.from({length:126},(_,i)=>entry(i%2+2,"OLD "+i+" "+"x".repeat(900)));
  const v=V.composeView("combine those two answers",[...newest,...history],large);
  assert.match(v.view,/NEWEST TWO/);assert.match(v.view,/NEWEST THREE/);
  assert.ok(v.entry_ids.includes(newest[0].event_id));assert.ok(v.entry_ids.includes(newest[1].event_id));
  assert.ok(v.message.length<=V.characterBudget(large));assert.match(v.view,/TRUNCATED/);
});
