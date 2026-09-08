"use strict";
const {test}=require("node:test"),assert=require("node:assert/strict");
const {EventEmitter}=require("node:events"),{PassThrough}=require("node:stream");
const {callStore}=require("../control/journal-runtime");
test("F-27: runtime bridge preserves UTF-8 across split stdout chunks without app/MCP calls",async()=>{
  let invocation;
  const spawnProcess=(exe,args,opts)=>{
    invocation={exe,args,opts};
    const child=new EventEmitter();
    child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
    child.kill=()=>{};
    queueMicrotask(()=>{
      const bytes=Buffer.from(JSON.stringify({ok:true,result:"π🙂終"}));
      for(let i=0;i<bytes.length;i++)child.stdout.write(bytes.subarray(i,i+1));
      child.stdout.end();child.emit("close",0);
    });
    return child;
  };
  assert.equal(await callStore({op:"budget"},{spawnProcess}),"π🙂終");
  assert.ok(invocation.args.some(x=>x.endsWith("journal-store.py")));
  assert.ok(invocation.args.includes("-B"));assert.equal(invocation.opts.windowsHide,true);
});
