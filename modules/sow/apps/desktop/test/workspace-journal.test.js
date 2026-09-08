"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const Module = require("node:module");
const J = require("../control/workspace-journal");
const { delegateToPane } = require("../control/conductor-delegation");
function setup(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "sow-journal-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root,"install"));
  const rows = [];
  const store = { append: async e => rows.push(structuredClone(e)), entries: async ({ sessionId, limit }) =>
    (sessionId ? rows.filter(e => e.session_id === sessionId) : rows.toReversed()).slice(0, limit) };
  const journal = J.createWorkspaceJournal({store,stateRoot:path.join(root,"state"),
    installRoot:path.join(root,"install"),sessionId:"session-test",now:()=>"2026-09-06T00:00:00Z"});
  return {root,rows,store,journal};
}
const entry = (extra={}) => ({node_id:"node-2",pane_id:"pane-2",model:"test-model",
  objective:"compare facts",task_id:"task-1",status:"answered",prompt:"question",answer:"answer",
  self_published:false,source:J.SOURCE,...extra});
test("F-27: completed delegation is stored and projected with both honesty fields",async t=>{
  const x=setup(t); let clock=0;
  const io={journal:x.journal, now:()=>clock,sleep:async ms=>{clock+=ms},
    window:{mark:()=>0,read:()=>({answerable:true,text:"worker answer",at:1})},
    writePrompt:async()=>({written:true})};
  const result=await delegateToPane(io,{paneId:"pane-2",nodeId:"node-2",model:"test-model",
    task:{task_id:"task-1",objective:"compare facts"},timeoutMs:20,pollMs:1,quietMs:2});
  assert.equal(result.answered,true);
  assert.ok(x.rows.some(e=>e.status==="prompt_written"));
  const e=x.rows.find(e=>e.status==="answered");
  assert.equal(e.self_published,false);assert.equal(e.source,J.SOURCE);
  assert.equal(e.answer,"worker answer");assert.ok(e.objective.includes("compare facts"));
  assert.equal(e.prompt,"");
  const md=fs.readFileSync((await x.journal.project()).file,"utf8");
  assert.match(md,/self_published: false/);assert.match(md,/observed_pane_output/);
  assert.match(md,/worker answer/);
});
test("F-27: refused write retains its own reason durably",async t=>{
  const x=setup(t);
  const result=await delegateToPane({journal:x.journal,window:{mark:()=>0},
    writePrompt:async()=>({written:false,refused:{reason:"permission modal OPEN"}})},
    {paneId:"pane-2",nodeId:"node-2",task:{task_id:"t",objective:"work"}});
  assert.equal(result.delivered,false);
  assert.ok(x.rows.some(e=>e.status==="write_refused"&&e.reason==="permission modal OPEN"));
});
test("F-27: nondelegated unreadable panes are named, using observePanes",async t=>{
  const x=setup(t);
  await x.journal.observe({read:()=>({answerable:false,reason:"pane unavailable"})},
    [{pane_id:"pane-3",node_id:"node-3",model:"test"}],300);
  assert.equal(x.rows[0].pane_id,"pane-3");assert.equal(x.rows[0].status,"unreadable");
  assert.match(x.rows[0].reason,/pane unavailable/);
});
test("F-27: redactions and truncation survive projection; names/host paths do not",async t=>{
  const x=setup(t);
  const result=await x.journal.record(entry({answer:"OPENAI_API_KEY=sk-"+"x".repeat(30)
    +"\nC:\\Users\\person\\private.txt",redactions:3,redaction_kinds:["api_key"],truncated:true}));
  assert.ok(result.entry.redactions>=3);assert.ok(result.entry.redaction_kinds.includes("api_key"));
  const md=fs.readFileSync(result.projection.file,"utf8");
  assert.doesNotMatch(md,/OPENAI_API_KEY|C:\\\\Users|sk-xxxxxxxx/);
  assert.match(md,/truncated: true/);
});
test("F-27: repeat render and deletion/reprojection preserve bytes and store",async t=>{
  const x=setup(t);await x.journal.record(entry());await x.journal.record(entry({answer:"later"}));
  const {file}=await x.journal.project(), before=fs.readFileSync(file), store=JSON.stringify(x.rows);
  await x.journal.project();assert.deepEqual(fs.readFileSync(file),before);
  fs.unlinkSync(file);await x.journal.project();
  assert.deepEqual(fs.readFileSync(file),before);assert.equal(JSON.stringify(x.rows),store);
});
test("F-27: install root and sibling-prefix containment, with no store write on refusal",async t=>{
  const x=setup(t);
  const bad=J.createWorkspaceJournal({store:x.store,stateRoot:path.join(x.root,"install","state"),
    installRoot:path.join(x.root,"install"),sessionId:"bad"});
  await assert.rejects(()=>bad.record(entry()),/inside install/);assert.equal(x.rows.length,0);
  const good=J.createWorkspaceJournal({store:x.store,stateRoot:path.join(x.root,"install-other"),
    installRoot:path.join(x.root,"install"),sessionId:"good"});
  await good.record(entry());
  assert.deepEqual(fs.readdirSync(path.join(x.root,"install")),[]);
});
test("F-27: cap is explicit and deterministic, with later history retained in store",async t=>{
  const x=setup(t);
  for(let n=0;n<J.MAX_SESSION_ENTRIES+2;n++)
    x.rows.push(J.prepareEntry(entry({event_id:"e-"+n}),"session-test",()=>"2026-09-06T00:00:00Z"));
  const {file}=await x.journal.project();
  assert.match(fs.readFileSync(file,"utf8"),/TRUNCATED: session projection cap/);
  assert.ok(fs.statSync(file).size<=J.MAX_FILE_BYTES);
  assert.equal(x.rows.length,J.MAX_SESSION_ENTRIES+2);
  await x.journal.project();
});
test("F-27: overcommitted observePanes floor never exceeds the shared budget",async t=>{
  const x=setup(t);
  await x.journal.observe({read:()=>({answerable:true,text:"z".repeat(500)})},
    [{pane_id:"pane-2"},{pane_id:"pane-3"}],100);
  assert.ok(x.rows.reduce((n,e)=>n+e.answer.length,0)<=100);
  assert.equal(x.rows[1].truncated,true);
});
test("F-27: store absence and drift fail closed; journal bytes cannot become authority",async t=>{
  const x=setup(t);await x.journal.record(entry());
  const {file}=await x.journal.project();fs.appendFileSync(file,"forged");
  await assert.rejects(()=>x.journal.project(),/projection mismatch/);
  x.store.entries=async()=>{throw Error("store unavailable")};
  await assert.rejects(()=>x.journal.entries(),/store unavailable/);
});
test("F-27 mutation control: omitting self_published is detected by the decisive assertion",()=>{
  const filename=require.resolve("../control/workspace-journal");
  const source=fs.readFileSync(filename,"utf8");
  const changed=source.replace("utc: raw.utc || now(), self_published: false, source: SOURCE,",
    "utc: raw.utc || now(), source: SOURCE,");
  assert.notEqual(changed,source);
  const mutant=new Module(filename,module);mutant.filename=filename;
  mutant.paths=Module._nodeModulePaths(path.dirname(filename));mutant._compile(changed,filename);
  assert.throws(()=>mutant.exports.prepareEntry(entry(),"session-test",()=>"2026-09-06T00:00:00Z"),
    /unreadable/);
  assert.equal(J.prepareEntry(entry(),"session-test",()=>"2026-09-06T00:00:00Z").self_published,false);
});

test("F-27: projection rechecks privacy on a readable store entry",()=>{
  const e=J.prepareEntry(entry(),"session-test",()=>"2026-09-06T00:00:00Z");
  e.answer="OPENAI_API_KEY=sk-"+"x".repeat(30);
  assert.doesNotMatch(J.renderSession([e],"session-test"),/OPENAI_API_KEY|sk-xxxx/);
});
test("F-27: a failed journal write remains visible without changing the pane gate result",async()=>{
  const r=await delegateToPane({journal:{record:async()=>{throw Error("unavailable")}},
    window:{mark:()=>0},writePrompt:async()=>({written:false,refused:{reason:"modal"}})},
    {paneId:"pane-2",nodeId:"node-2",task:{objective:"work"}});
  assert.equal(r.refused.reason,"modal");assert.match(r.journal_error,/unavailable/);
});
