const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/design.js','utf8');
const timer={dataset:{stopped:'false',pending:'false',nextRun:new Date(Date.now()+137000).toISOString()},textContent:''};
const ctx={Date,document:{querySelectorAll:()=>[timer]}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function updateApplicationTimers(){'),source.indexOf('setInterval(updateApplicationTimers,1000)')),ctx);
ctx.updateApplicationTimers();assert.match(timer.textContent,/^02:1[56]$/);
timer.dataset.pending='true';ctx.updateApplicationTimers();assert.equal(timer.textContent,'Running');
timer.dataset.pending='false';ctx.updateApplicationTimers();assert.notEqual(timer.textContent,'Running');
timer.dataset.stopped='true';ctx.updateApplicationTimers();assert.equal(timer.textContent,'—');
// A restart briefly stops the app; its label must win over the stopped dash and the Running label.
timer.dataset.pending='true';timer.dataset.activity='Restarting';ctx.updateApplicationTimers();assert.equal(timer.textContent,'Restarting');
timer.dataset.stopped='false';timer.dataset.activity='Scanning';ctx.updateApplicationTimers();assert.equal(timer.textContent,'Scanning');
timer.dataset.activity='';ctx.updateApplicationTimers();assert.equal(timer.textContent,'Running');
console.log('Waiting countdown, active Run, return to waiting, stopped badge, and Scanning/Restarting labels passed.');
