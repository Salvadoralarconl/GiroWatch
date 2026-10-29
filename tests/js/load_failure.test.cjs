const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/design.js','utf8');
const start=source.indexOf('async function api(');
assert.ok(start>=0,'GiroWatch requests go through api()');
const api=source.slice(start,source.indexOf('async function refreshCatalog(',start));
// Each case gets its own fetch; the screen must appear only when the server is unreachable or failing.
async function run(fetch){
 const shown=[];const window={showLoadFailure:()=>shown.push(true),isUnreachable:error=>error instanceof TypeError,dispatchEvent:()=>{}};
 const context={fetch,window,Event:class{},Error,TypeError,JSON};vm.createContext(context);vm.runInContext(api,context);
 let failed=null;try{await context.api('/api/state');}catch(error){failed=error;}
 return {shown:shown.length,failed};
}
const reply=(status,body,json=true)=>async()=>({status,ok:status<400,json:async()=>{if(!json)throw new SyntaxError('Unexpected token <');return body;}});
(async()=>{
 let r=await run(async()=>{throw new TypeError('Failed to fetch');});
 assert.equal(r.shown,1,'Server stopped: show the screen');assert.ok(r.failed);
 r=await run(reply(502,null,false));
 assert.equal(r.shown,1,'Server error page instead of JSON: show the screen');
 r=await run(async()=>{const error=new Error('aborted');error.name='AbortError';throw error;});
 assert.equal(r.shown,0,'A request cancelled on purpose is not a load failure');
 r=await run(reply(400,{error:'Choose an application.'}));
 assert.equal(r.shown,0,'Ordinary errors keep using the existing notices');assert.equal(r.failed.message,'Choose an application.');
 r=await run(reply(200,{ok:true}));
 assert.equal(r.shown,0);assert.equal(r.failed,null);
 console.log('load failure screen: ok');
})().catch(error=>{console.error(error);process.exit(1);});
