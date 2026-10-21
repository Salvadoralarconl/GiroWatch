const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web/design.js','utf8');
const container={children:[],append(node){this.children.push(node);},get firstElementChild(){return this.children[0];}};
function node(){return {dataset:{},append(){},setAttribute(){},addEventListener(){},remove(){const i=container.children.indexOf(this);if(i>=0)container.children.splice(i,1);}};}
const context={Date,Map,setTimeout(){},window:{},document:{addEventListener(){},createElement:node},$:()=>container,notificationPreferences:{errors:true,warnings:true,resolved:false,sound:false}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('let notificationBaseline='),source.indexOf('// Resize only the popup width')),context);
const error={id:'1',application:'Test',message:'Failure',severity:'Error',status:'Active',time:'12:00',occurrence_count:1};
context.announceIncidentChanges([error]);assert.equal(container.children.length,0,'Initial snapshot stays quiet');
context.announceIncidentChanges([error]);assert.equal(container.children.length,0,'Unchanged snapshot stays quiet');
const warning={...error,id:'2',severity:'Warning'};
context.announceIncidentChanges([error,warning]);assert.equal(container.children.length,1);
context.notificationPreferences.warnings=false;
context.announceIncidentChanges([error,warning,{...warning,id:'3'}]);assert.equal(container.children.length,1);
context.notificationPreferences.resolved=true;
context.announceIncidentChanges([{...error,status:'Resolved'},warning]);assert.equal(container.children.length,2);
console.log('Notification baseline, deduplication, severity preferences, and resolution passed');
