const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/design.js','utf8');
const start=source.indexOf('function bindIncidentRow(');
assert.ok(start>=0,'Whole incident rows should open their details');
const end=source.indexOf('async function refreshHomeErrors(',start);
const opened=[],handlers={},attributes={};
let selection='';
const row={setAttribute:(k,v)=>attributes[k]=v,addEventListener:(name,handler)=>handlers[name]=handler};
const context={openHomeError:id=>opened.push(id),window:{getSelection:()=>({toString:()=>selection})}};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
context.bindIncidentRow(row,'incident-1');
assert.equal(attributes.tabindex,'0');
handlers.click({target:{closest:()=>null}});
assert.equal(opened.length,1);
handlers.click({target:{closest:()=>({})}});
assert.equal(opened.length,1,'Info button handles its own click without a second request');
selection='copied log text';handlers.click({target:{closest:()=>null}});
assert.equal(opened.length,1,'Selecting text should not open the dialog');
selection='';
for(const key of ['Enter',' ']) {
  let prevented=false;handlers.keydown({key,target:row,preventDefault:()=>prevented=true});
  assert.ok(prevented);
}
assert.equal(opened.length,3);
handlers.keydown({key:'Enter',target:{},preventDefault:()=>{}});
assert.equal(opened.length,3,'Child controls handle their own keyboard input');
console.log('Incident row click, keyboard, text selection and button isolation passed.');
