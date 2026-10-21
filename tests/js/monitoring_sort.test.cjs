const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/design.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function sortMonitoringApplications('),source.indexOf('const applicationActions=')),ctx);
const apps=[{name:'Cam',color:'green'},{name:'UNITELLER',color:'red'},{name:'Banco Industrial',color:'green'},{name:'Zeta',color:'yellow'},{name:'Alpha',color:'yellow'}];
assert.deepEqual(Array.from(ctx.sortMonitoringApplications(apps),a=>a.name),['UNITELLER','Alpha','Zeta','Banco Industrial','Cam']);
assert.equal(apps[0].name,'Cam');
apps[1].color='green';
assert.deepEqual(Array.from(ctx.sortMonitoringApplications(apps),a=>a.name),['Alpha','Zeta','Banco Industrial','Cam','UNITELLER']);
console.log('Severity priority, alphabetical ordering, and recovery ordering passed');
