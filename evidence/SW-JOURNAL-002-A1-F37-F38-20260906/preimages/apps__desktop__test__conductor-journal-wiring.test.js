"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const main=fs.readFileSync(path.resolve(__dirname,"../main.js"),"utf8");
test("F-28: real conversational handler supplies the view via its existing writer and captures a reply",async()=>{
  const from=main.indexOf("async function handleOperatorText(payload) {");
  const to=main.indexOf("// ---- renderer IPC",from);
  assert.ok(from>0&&to>from);
  let clock=0, delivered=null, contextCalls=0;const turns=[];
  const sandbox={Date:class extends Date { static now(){return clock;} },
    setTimeout:(fn,ms)=>{clock+=ms;fn();},String,Boolean,Array,Math,
    conductorDescriptor:()=>({provider_id:"test",model_id:"test"}),
    pushTranscriptTurn:t=>turns.push(t),
    conductorLaunch:{state:"running"},manager:{registry:new Map([["pane-1",{}]])},
    conductorPaneId:"pane-1",paneStreamPosition:()=>0,
    panes:{panes:new Map([["pane-1",{}],["pane-2",{}]])},readinessWindow:{},
    liveWorkerRecords:()=>[{nodeId:"node-2",paneId:"pane-2"}],
    paneChrome:new Map([["pane-2",{model_slug:"model-2"}]]),
    runtimeJournal:()=>({}),createStore:()=>({budget:()=>({})}),
    retrieveAndDeliver:async io=>{contextCalls++;assert.equal(io.panes[0].model,"model-2");
      const r=await io.write(io.message+"\n\nbounded retrieved view");
      return {...r,context:{notice:"Bounded worker view attached."}}},
    deliverConductorChat:async text=>{delivered=text;return {written:true,submitted:true}},
    paneEmittedSince:()=>"model reply",log:()=>{}};
  vm.createContext(sandbox);vm.runInContext(main.slice(from,to),sandbox);
  const result=await sandbox.handleOperatorText({text:"compare workers"});
  assert.equal(result.ok,true);assert.equal(contextCalls,1);
  assert.match(delivered,/bounded retrieved view/);
  assert.ok(turns.some(t=>t.dir==="in"&&t.text==="model reply"));
  assert.ok(turns.some(t=>t.dir==="sys"&&/view attached/.test(t.text)));
});
