const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('an in-flight monitoring response does not replace an open Actions trigger', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../web/design.js'), 'utf8');
  const refresh = source.slice(source.indexOf('async function refreshMonitoring()'), source.indexOf('function updateApplicationTimers()'));
  let open = false, replacements = 0, respond;
  const element = {replaceChildren(){replacements++;},append(){},textContent:'',title:''};
  const context = {monitoringLoading:false, monitoringBusy:false, monitoringManual:false,
    applicationActions:{matches:()=>open}, api:()=>new Promise(resolve=>respond=resolve),
    renderSystemHealth(){}, sortMonitoringApplications:()=>[], $:()=>element,
    document:{querySelector:()=>null,createElement:()=>({...element,cloneNode:()=>element})},
    renderMonitoringPreferences(){}, updateMonitoringCountdown(){}, updateApplicationTimers(){},
    setTimeout(){}, Date, AbortSignal};
  vm.createContext(context);
  const pending = vm.runInContext(refresh+'\nrefreshMonitoring()', context);
  open = true;
  respond({applications:[], scanning:false});
  await pending;
  assert.equal(replacements, 0);
  assert.equal(context.monitoringLoading, false);
});
