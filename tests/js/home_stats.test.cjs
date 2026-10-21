const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/design.js','utf8');
const start=source.indexOf('async function refreshHomeStats()');
assert.ok(start>=0,'Runs Today needs an independent request');
const end=source.indexOf('function sizeErrorInfo(',start);
const refresh=source.slice(source.indexOf('async function refreshHome()'),source.indexOf('const homeVisible='));
const rendered=[];
const context={AbortSignal,homeStatsLoading:false,homeStatsFailure:'',api:async()=>({today:13,days:[],scanned_at:'today'}),
 renderRunStats:stats=>rendered.push(stats.today),notify:()=>{},
 refreshHomeErrors:async()=>{throw new Error('Error table unavailable');}};
vm.createContext(context);vm.runInContext(source.slice(start,end)+refresh,context);
(async()=>{
 await context.refreshHome();
 assert.deepEqual(rendered,[13],'Error-table failure must not block Runs Today');
 context.api=async()=>{throw new Error('Temporary outage');};
 await context.refreshHome();
 context.api=async()=>({today:14,days:[],scanned_at:'today'});
 await context.refreshHome();
 assert.deepEqual(rendered,[13,14],'Stats request must recover after failure');
 console.log('Independent Runs Today loading and retry passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

