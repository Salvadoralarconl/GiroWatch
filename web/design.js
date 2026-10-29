/* Manual application profiles, isolated tests, and exactly three JSON exports. */
'use strict';
let profileCatalog = [], selectedApplication = '', selectedSection = 'errors', profileRequest = 0;
const modelNames = {naive_bayes:'Naive Bayes',nearest_example:'Nearest example',linear_svm:'Linear SVM · backup'};
const profileFields = {errors:'error_profile',run:'run_profile',order:'order_profile',folders:'folder_profile',controls:'control_profile'};
const drafts = new Map();
let testDownloads = [];
const $ = selector => document.querySelector(selector);
function updateGreeting() {
  const hour=new Date().getHours();
  const greeting=hour<12?'Good Morning':hour<18?'Good Afternoon':'Good Evening';
  $('.greeting h1').textContent=`${greeting}, ${window.giroWatchUser?.name || 'there'}`;
}
updateGreeting();
setInterval(updateGreeting,60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateGreeting();});
const draftKey = () => `${selectedApplication}\n${selectedSection}`;

let notificationTimer;
function positionNotification() {
  const toast=$('#configuration-status');
  const panel=location.hash==='#search'?$('.search-screen'):null;
  const bounds=panel?.getBoundingClientRect();
  toast.style.left=bounds?`${bounds.left+bounds.width/2}px`:'50%';
}
window.addEventListener('resize',positionNotification);
window.addEventListener('hashchange',positionNotification);
function notify(text, undo, isError=false) {
  const toast = $('#configuration-status');
  clearTimeout(notificationTimer);
  toast.classList.toggle('notification-error',isError);
  toast.setAttribute('role',isError?'alert':'status');
  toast.replaceChildren(document.createTextNode(text));
  if (undo) {
    const button = document.createElement('button');
    button.textContent = 'Undo';
    button.addEventListener('click', undo);
    toast.append(button);
  }
  toast.hidden = false;
  positionNotification();
  if(isError || !undo) notificationTimer=setTimeout(()=>{toast.hidden=true;},5000);
}
async function api(url, payload, options={}) {
  let response, result;
  try {response = await fetch(url, payload === undefined ? options : {...options,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});}
  catch(error) {if(window.isUnreachable?.(error))window.showLoadFailure?.();throw error;}
  // A server error page instead of JSON means the page failed.
  try {result = await response.json();}
  catch {if(response.status>=500)window.showLoadFailure?.();throw new Error('Request failed.');}
  if(response.status===401)window.dispatchEvent(new Event('account-expired'));
  if (!response.ok) throw new Error(result.error || 'Request failed.');
  return result;
}
async function refreshCatalog(application = selectedApplication) {
  const state = await api('/api/state');
  if (state.local_test_mode) {
    document.title='GiroWatch · Local test mode';
  }
  profileCatalog = state.applications;
  const select = $('[aria-label="Configure application"]');
  select.replaceChildren(...profileCatalog.map(item => new Option(item.name,item.name)));
  selectedApplication = profileCatalog.find(item => item.name === application)?.name || select.value;
  select.value = selectedApplication;
  await renderFolders();
}

// The same error-row editor is used in the saved profile and the creation popup.
function fillErrorRules(rules, list = $('.error-rule-rows')) {
  list.replaceChildren();
  (rules.length ? rules : [{}]).forEach((rule,index) => {
    const row = document.createElement('div');
    row.className = 'error-editor-row';
    const match = document.createElement('input');
    match.placeholder = 'Error phrase or code'; match.value = rule.match || '';
    match.setAttribute('aria-label', `Error match text ${index + 1}`);
    const severity = document.createElement('select');
    severity.setAttribute('aria-label', `Error severity ${index + 1}`);
    ['Warning','Critical','Ignore'].forEach(value => severity.add(new Option(value,value)));
    severity.value = rule.severity || 'Warning';
    const message = document.createElement('input');
    message.placeholder = 'Message to display'; message.value = rule.message || '';
    message.setAttribute('aria-label', `Error display message ${index + 1}`);
    row.append(match,severity,message);
    const notesLabel=document.createElement('label');notesLabel.className='error-rule-notes';
    const notes=document.createElement('textarea');notes.rows=3;notes.placeholder='Possible fixes or troubleshooting notes…';notes.value=rule.notes||'';
    notes.setAttribute('aria-label',`Error notes ${index + 1}`);notesLabel.append(notes);row.append(notesLabel);
    const options = document.createElement('div'); options.className = 'rule-options';
    const label = document.createElement('label');
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = !!rule.case_sensitive;
    label.append(checkbox,document.createTextNode('Case sensitive'));
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
    remove.addEventListener('click', () => { row.remove(); list.dispatchEvent(new Event('input',{bubbles:true})); });
    options.append(label,remove); row.append(options); list.append(row);
  });
}
function readRules(list) {
  return [...list.querySelectorAll('.error-editor-row')].map(row => ({
    match: row.querySelector('input').value.trim(), severity: row.querySelector('select').value,
    message: row.querySelectorAll('input')[1].value.trim(), notes:row.querySelector('textarea').value, case_sensitive: row.querySelector('[type=checkbox]').checked
  })).filter(rule => rule.match || rule.message);
}
function examplesProfile(fields, section, model) {
  const prefix = section === 'run' ? 'Run' : 'Order';
  const profile = {messages:[],labels:[]};
  [`${prefix}_Start`,`${prefix}_End`,'Other'].forEach((label,index) => {
    fields[index].value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).forEach(message => {
      profile.messages.push(message); profile.labels.push(label);
    });
  });
  if (section === 'order') profile.selected_model = model;
  return profile;
}
function readEditor() {
  const card = $(`#${selectedSection}-settings`);
  if (selectedSection === 'errors') return {rules:readRules(card.querySelector('.error-rule-rows'))};
  if (selectedSection === 'folders') return {path:$('#folder-path').value.trim(),recursive:$('#folder-recursive').checked};
  if(selectedSection==='controls')return Object.fromEntries([...card.querySelectorAll('[data-control-field]')].map(input=>[input.dataset.controlField,input.type==='number'?Number(input.value):input.value.trim()]));
  return examplesProfile([...card.querySelectorAll('textarea')],selectedSection,card.querySelector('select')?.value);
}
function fillEditor(section, profile) {
  const card = $(`#${section}-settings`);
  if (section === 'errors') return fillErrorRules(profile?.rules || []);
  if(section==='controls') {card.querySelectorAll('[data-control-field]').forEach(input=>input.value=profile?.[input.dataset.controlField]??(input.type==='number'?10:''));return;}
  if (section === 'folders') {
    $('#folder-path').value = profile?.path || ''; $('#folder-recursive').checked = profile?.recursive !== false;
    $('#folder-check-results').textContent = ''; return;
  }
  const prefix = section === 'run' ? 'Run' : 'Order';
  const fields = [...card.querySelectorAll('textarea')];
  [`${prefix}_Start`,`${prefix}_End`,'Other'].forEach((label,index) => {
    fields[index].value = (profile?.messages || []).filter((_,i) => profile.labels[i] === label).join('\n');
    fields[index].readOnly = false;
  });
  if (section === 'order') { card.querySelector('select').disabled = false; card.querySelector('select').value = profile?.selected_model || 'naive_bayes'; }
}
async function loadSelectedProfile() {
  const request = ++profileRequest, section = selectedSection, application = selectedApplication;
  const card = $(`#${section}-settings`), badge = card.querySelector('.preview-label');
  fillEditor(section,null);
  card.querySelectorAll('input,textarea,select,.configuration-save,.add-example').forEach(field => field.disabled = true);
  if (!application) { badge.textContent = 'Create a profile with +'; return; }
  badge.textContent = 'Loading…';
  try {
    const result = await api(`/api/profile?${new URLSearchParams({application,section})}`);
    if (request !== profileRequest) return;
    const key = `${application}\n${section}`;
    fillEditor(section,drafts.get(key) || result.profile);
    card.querySelectorAll('input,textarea,select,.configuration-save,.add-example').forEach(field => field.disabled = false);
    badge.textContent = drafts.has(key) ? 'Unsaved changes' : result.exists ? 'Saved profile' : 'Not configured';
  } catch (error) { if (request === profileRequest) { badge.textContent = 'Could not load'; notify(error.message,null,true); } }
}
async function renderFolders() {
  const list = $('#profile-folder-list'); list.replaceChildren();
  const available = profileCatalog;
  $('#folder-count').textContent = available.length;
  for (const application of available) {
    const button = document.createElement('button'); button.type = 'button';
    button.className = `profile-folder${application.name === selectedApplication ? ' selected' : ''}`;
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M3 9h18"/></svg><span><strong></strong><small></small></span>';
    button.querySelector('strong').textContent = application.name;
    button.querySelector('small').textContent = !application[profileFields[selectedSection]]?'Not configured':selectedSection === 'order' ? modelNames[application.selected_model] || 'Select model' : 'Saved profile';
    button.setAttribute('aria-pressed',String(application.name === selectedApplication)); button.setAttribute('aria-haspopup','menu');
    const select = () => { selectedApplication = application.name; $('[aria-label="Configure application"]').value = application.name; return renderFolders(); };
    button.addEventListener('click',select);
    button.addEventListener('contextmenu',async event => {
      event.preventDefault(); await select();
      const menu = $('.profile-context-menu'); menu.querySelector('.context-profile-name').textContent = application.name; menu.hidden = false;
      menu.style.left = `${Math.max(8,Math.min(event.clientX,innerWidth-menu.offsetWidth-8))}px`;
      menu.style.top = `${Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))}px`;
    });
    list.append(button);
  }
  if (!available.length) { const empty = document.createElement('p'); empty.className='no-profiles'; empty.textContent='No profiles yet. Use + to create one.'; list.append(empty); }
  await loadSelectedProfile();
}
function showPage() {
  const requested = location.hash.slice(1);
  // Settings moved into the account pop-up; old links open it there.
  if (requested === 'settings') { history.replaceState(null, '', '#home'); window.openAccountView?.('settings'); }
  const page = ['home','monitoring','search','configuration','contacts'].includes(requested) ? requested : 'home';
  $('.sonda-shell').dataset.page = page;
  for (const name of ['home','monitoring','search','configuration','contacts']) {
    $(`.${name}-screen`).hidden = name !== page;
    const link = $(`.nav-link[href="#${name}"]`); link.classList.toggle('active',name===page);
    if (name===page) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  }
  $('#current-page').textContent = page[0].toUpperCase()+page.slice(1);
  $('#current-icon').src = `/assets/${page==='configuration'||page==='contacts'?'layout':page}.png`;
  if(page==='contacts')$('#current-icon').src='data:image/svg+xml,'+encodeURIComponent($('.nav-link[href="#contacts"] svg').outerHTML.replace('<svg','<svg xmlns="http://www.w3.org/2000/svg"'));
  document.title = `GiroWatch · ${$('#current-page').textContent}`;
}
window.addEventListener('hashchange',showPage); showPage();
document.querySelectorAll('.configuration-tab').forEach(tab => tab.addEventListener('click',async () => {
  selectedSection = tab.dataset.section;
  // Keep the chosen application when changing sections, including unconfigured sections.
  document.querySelectorAll('.configuration-tab').forEach(button => {
    const selected=button===tab; button.classList.toggle('selected',selected); button.setAttribute('aria-selected',String(selected));
    document.getElementById(button.getAttribute('aria-controls')).hidden=!selected;
  });
  await renderFolders();
}));
$('[aria-label="Configure application"]').addEventListener('change',event => { selectedApplication=event.target.value; renderFolders(); });
$('.profile-editor').addEventListener('input', () => {
  if (!selectedApplication) return;
  drafts.set(draftKey(),readEditor());
  $(`#${selectedSection}-settings .preview-label`).textContent='Unsaved changes';
});
window.addEventListener('beforeunload',event => { if(drafts.size) { event.preventDefault(); event.returnValue=''; } });

async function saveCurrent() {
  const application=selectedApplication, section=selectedSection;
  const button=$(`#${section}-settings .configuration-save`); button.disabled=true;
  try {
    const result=await api('/api/configure',{action:'save',section,application,profile:readEditor()});
    drafts.delete(`${application}\n${section}`); await refreshCatalog(result.application); notify('Profile saved.');
  } catch(error) { notify(error.message,null,true); } finally { button.disabled=false; }
}
document.querySelectorAll('.profile-editor .configuration-save').forEach(button => {
  button.addEventListener('click',saveCurrent);
});
$('.add-example').addEventListener('click',() => { fillErrorRules([...readRules($('.error-rule-rows')),{}]); $('.error-rule-rows').dispatchEvent(new Event('input',{bubbles:true})); });

async function openNew(copy = false) {
  if(selectedSection==='controls'){notify('Choose an application, fill in its controls, and save.');return;}
  const section=selectedSection, order=section==='order', errors=section==='errors', folders=section==='folders';
  const dialog=$('.new-profile-dialog');
  const profile=copy ? (await api(`/api/profile?${new URLSearchParams({application:selectedApplication,section})}`)).profile : null;
  $('#new-profile-title').textContent=`${copy?'Copy':'New'} ${{run:'run grouping',order:'order grouping',errors:'error',folders:'log folder'}[section]} profile`;
  $('.new-profile-header p').textContent=''; $('.new-profile-footer > span').textContent='';
  $('[aria-label="New profile application name"]').value=copy ? `${selectedApplication} Copy` : '';
  $('.new-folder-fields').hidden=!folders; $('.new-profile-model').hidden=!order;
  $('.new-profile-boundaries').hidden=errors||folders; $('.new-other-examples').hidden=errors||folders; $('.new-error-fields').hidden=!errors;
  $('#new-start-label').textContent=`${order?'Order':'Run'}_Start examples`; $('#new-end-label').textContent=`${order?'Order':'Run'}_End examples`;
  const fields=[...dialog.querySelectorAll('textarea')], prefix=order?'Order':'Run';
  [`${prefix}_Start`,`${prefix}_End`,'Other'].forEach((label,index) => fields[index].value=(profile?.messages||[]).filter((_,i)=>profile.labels[i]===label).join('\n'));
  $('[aria-label="New profile order model"]').value=profile?.selected_model||'naive_bayes';
  $('[aria-label="New log root folder"]').value=profile?.path||''; $('[aria-label="New folder include subfolders"]').checked=profile?.recursive!==false;
  fillErrorRules(profile?.rules||[],$('.new-error-rule-rows'));
  dialog.showModal();
}
$('.new-profile-button').addEventListener('click',()=>openNew().catch(error=>notify(error.message,null,true)));
document.querySelectorAll('.close-profile-dialog,.cancel-new-profile').forEach(button=>button.addEventListener('click',()=>$('.new-profile-dialog').close()));
$('.new-add-rule').addEventListener('click',()=>fillErrorRules([...readRules($('.new-error-rule-rows')),{}],$('.new-error-rule-rows')));
$('.new-profile-footer .configuration-save').addEventListener('click',async event=>{
  const button=event.currentTarget; button.disabled=true;
  try {
    const application=$('[aria-label="New profile application name"]').value.trim(), section=selectedSection;
    let profile;
    if(section==='folders') profile={path:$('[aria-label="New log root folder"]').value.trim(),recursive:$('[aria-label="New folder include subfolders"]').checked};
    else if(section==='errors') profile={rules:readRules($('.new-error-rule-rows'))};
    else profile=examplesProfile([...$('.new-profile-dialog').querySelectorAll('textarea')],section,$('[aria-label="New profile order model"]').value);
    const result=await api('/api/configure',{action:'save',create:true,application,section,profile});
    $('.new-profile-dialog').close(); await refreshCatalog(result.application); notify('Profile created.');
  } catch(error) { $('.new-profile-footer > span').textContent=error.message; } finally {button.disabled=false;}
});

document.querySelectorAll('[data-profile-action]').forEach(button=>button.addEventListener('click',async()=>{
  const action=button.dataset.profileAction; $('.profile-context-menu').hidden=true;
  try {
    if(action==='edit') { $(`#${selectedSection}-settings input, #${selectedSection}-settings textarea, #${selectedSection}-settings select`)?.focus(); return; }
    if(action==='copy') return await openNew(true);
    const application=selectedApplication,section=selectedSection;
    await api('/api/configure',{action:'delete',application,section}); drafts.delete(draftKey()); await refreshCatalog();
    notify('Profile deleted. A recovery copy is saved locally.',async()=>{
      try {await api('/api/configure',{action:'restore',application,section}); await refreshCatalog(application); notify('Profile restored.');} catch(error){notify(error.message,null,true);}
    });
  } catch(error){notify(error.message,null,true);}
}));
document.addEventListener('click',event=>{if(!event.target.closest('.profile-context-menu')) $('.profile-context-menu').hidden=true;});
document.addEventListener('keydown',event=>{if(event.key==='Escape') $('.profile-context-menu').hidden=true;});
$('#check-folder').addEventListener('click',async event=>{
  const button=event.currentTarget; button.disabled=true; $('#folder-check-results').textContent='Checking…';
  try {
    const result=await api('/api/folder-profile',{action:'check',application:selectedApplication,...readEditor()});
    $('#folder-check-results').textContent=`Latest log: ${result.latest_file}`;
  } catch(error){$('#folder-check-results').textContent=error.message;} finally{button.disabled=false;}
});

// Testing uses saved profiles; selecting another test model never changes the saved choice.
function openTest(compare = false) {
  if(!selectedApplication) return notify('Create an application profile first.');
  if([...drafts.keys()].some(key=>key.startsWith(`${selectedApplication}\n`))) return notify('Save the changes for this application before testing.');
  const application=profileCatalog.find(item=>item.name===selectedApplication);
  if(!application?.run_profile) return notify('Create a run profile for this application before testing.');
  $('#test-title').textContent=`Test · ${selectedApplication}`;
  $('#test-source').value=application.folder_profile?'folder':'upload';
  $('#test-model').value=''; $('#test-model-row').hidden=!compare;
  $('#test-output').textContent=''; $('#test-downloads').replaceChildren(); testDownloads=[];
  $('#test-upload-row').hidden=$('#test-source').value!=='upload';
  $('#test-files').value=''; $('#start-profile-test').disabled=false;
  $('.test-profile-dialog').showModal();
}
$('.profile-test-button').addEventListener('click',()=>openTest());
$('#order-settings .test-model').addEventListener('click',()=>openTest(true));
$('.close-test-dialog').addEventListener('click',()=>$('.test-profile-dialog').close());
$('#test-source').addEventListener('change',()=>$('#test-upload-row').hidden=$('#test-source').value!=='upload');
function downloadJSON(file) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(file.data,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url; link.download=file.filename; document.body.append(link); link.click(); link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),60000);
}
$('#start-profile-test').addEventListener('click',async event=>{
  const button=event.currentTarget; button.disabled=true; $('#test-output').textContent='Testing…'; $('#test-downloads').replaceChildren();
  try {
    const payload={application:selectedApplication,source:$('#test-source').value};
    if($('#test-model').value) payload.model=$('#test-model').value;
    if(payload.source==='upload') {
      const files=[...$('#test-files').files];
      if(!files.length) throw new Error('Choose a raw log file.');
      if(files.reduce((sum,file)=>sum+file.size,0)>20*1024*1024) throw new Error('Choose logs smaller than 20 MB in total.');
      payload.files=await Promise.all(files.map(async file=>({filename:file.name,text:await file.text()})));
    }
    const result=await api('/api/test-configuration',payload); testDownloads=result.downloads;
    const s=result.summary;
    $('#test-output').textContent=`${s.sources.map(item=>item.filename).join("\n")}\n${s.files} file(s) · ${s.runs} runs · ${s.orders} order groups\n${s.pending_files} file(s) with a pending final run${s.orders_assessed?'':'\nOrder profile missing: order grouping was not assessed.'}${s.errors_assessed?'':'\nError rules missing: error detection was not assessed.'}\nThree JSON downloads prepared. If your browser blocks automatic downloads, use the buttons below.`;
    testDownloads.forEach(file=>{
      const link=document.createElement('button'); link.type='button'; link.className='test-model'; link.textContent=`Download ${file.kind}`;
      link.addEventListener('click',()=>downloadJSON(file)); $('#test-downloads').append(link);
    });
    // Some browsers block multiple automatic downloads; the three buttons remain available.
    testDownloads.forEach(downloadJSON);
  } catch(error){$('#test-output').textContent=error.message;} finally{button.disabled=false;}
});
refreshCatalog().catch(error=>notify(error.message,null,true));

// Render original lines with textContent: log contents are never treated as HTML.
let searchRequest = 0, searchOffset = null, activeSearch = null;
// The header sits outside the scrolling results; reserve the same scrollbar space.
function alignSearchColumns() {
  const results=$('#order-search-results');
  $('.search-screen > .table-heading').style.paddingRight=`${results.offsetWidth-results.clientWidth}px`;
}
new ResizeObserver(alignSearchColumns).observe($('#order-search-results'));
// Start with today's local logs; the date filters still allow historical searches.
const searchToday=new Date();
const searchTodayValue=`${searchToday.getFullYear()}-${String(searchToday.getMonth()+1).padStart(2,'0')}-${String(searchToday.getDate()).padStart(2,'0')}`;
$('#order-search-from').value=searchTodayValue;
$('#order-search-to').value=searchTodayValue;
$('#search-date-filter').classList.add('has-dates');
function renderOrderOccurrence(group) {
  const card = document.createElement('article'); card.className='search-run';
  const app = document.createElement('div'); app.className='search-app';
  const name = document.createElement('strong'); name.textContent=group.application;
  const meta = document.createElement('small'); meta.textContent=`Run ${group.run_number} · Group ${group.group_number}\n${group.run_time}\n${group.source_file}`;
  app.append(name,meta);
  const lines = document.createElement('div'); lines.className='search-log-lines';
  group.lines.forEach(line=>{
    const row=document.createElement('div'), time=document.createElement('span'), message=document.createElement('span');
    const match=line.match(/^(\d{2}\/\d{2}\/\d{4})\s+(\d{2}:\d{2}:\d{2}\s+[AP]M)\s+(.*)$/);
    time.textContent=match?match[2]:'';
    message.textContent=match?match[3]:line; row.append(time,message); lines.append(row);
  });
  const status=document.createElement('div'); status.className='search-run-status';
  const pill=document.createElement('span'); pill.className=`pill ${{Successful:'stable',Error:'error',Incomplete:'warning','Not assessed':'investigating'}[group.outcome]}`;
  pill.textContent=group.outcome==='Successful'?'Successful':group.outcome==='Error'?'Unsuccessful':group.outcome;
  status.append(pill);
  if (['Error','Warning','Ignore'].includes(group.error_type)) {
    const alert=document.createElement('span');
    alert.className=`pill ${{Error:'error',Warning:'warning',Ignore:'investigating'}[group.error_type]}`;
    alert.textContent=group.error_type;
    status.append(alert);
  }
  const info=document.createElement('button');info.type='button';info.className='info-button';info.textContent='Info';
  info.setAttribute('aria-label',`Run log and contacts for ${group.application}, run ${group.run_number}`);
  info.addEventListener('click',()=>openSearchRun(group));status.append(info);
  card.append(app,lines,status); return card;
}
async function searchOrders(more=false) {
  const query=$('#order-search-query').value.trim(), application=$('#order-search-application').value;
  if(!query) return;
  const request=++searchRequest;
  if(!more) { $('#order-search-results').replaceChildren(); activeSearch={query,application,start:$('#order-search-from').value,end:$('#order-search-to').value}; }
  const parameters=new URLSearchParams({q:activeSearch.query,application:activeSearch.application,start:activeSearch.start,end:activeSearch.end,offset:more?searchOffset:0});
  $('#order-search-status').textContent=''; $('#order-search-more').hidden=true;
  $('#search-progress').hidden=false; $('.search-screen').setAttribute('aria-busy','true');
  try {
    const result=await api(`/api/search?${parameters}`);
    if(request!==searchRequest) return;
    result.groups.forEach(group=>$('#order-search-results').append(renderOrderOccurrence(group)));
    searchOffset=result.next_offset; $('#order-search-more').hidden=searchOffset===null;
    const message=[result.total ? '' : 'No matching order groups.',...(result.warnings||[])].filter(Boolean).join(' ');
    if(message) notify(message,null,!!result.warnings?.length);
  } catch(error){if(request===searchRequest) {$('#order-search-status').textContent='';notify(error.message,null,true);}}
  finally {if(request===searchRequest) {$('#search-progress').hidden=true;$('.search-screen').setAttribute('aria-busy','false');}}
}
$('#order-search-form').addEventListener('submit',event=>{event.preventDefault();searchOrders();});
$('#order-search-more').addEventListener('click',()=>searchOrders(true));
// Keep chosen dates when the compact filter menu is dismissed.
document.addEventListener('click',event=>{
  const filter=$('#search-date-filter');
  if(!filter.contains(event.target)) filter.open=false;
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape' && $('#search-date-filter').open) {
    $('#search-date-filter').open=false;
    $('#search-date-filter summary').focus();
  }
});
for(const id of ['#order-search-from','#order-search-to']) $(id).addEventListener('change',()=>{
  $('#search-date-filter').classList.toggle('has-dates',!!($('#order-search-from').value||$('#order-search-to').value));
});
async function refreshSearchApplications() {
  try {
    const result=await api('/api/search');
    const select=$('#order-search-application'), previous=select.value;
    select.replaceChildren(new Option('All applications',''),...result.applications.map(name=>new Option(name,name)));
    if(result.applications.includes(previous)) select.value=previous;
  } catch(error){notify(error.message,null,true);}
}
window.addEventListener('hashchange',()=>{if(location.hash==='#search')refreshSearchApplications();});
refreshSearchApplications();

// Both monitoring views share saved status and the same manual scan action.
// Polling reads status only; automatic log scanning remains paused on the server.
let monitoringLoading=false, monitoringNextScan=null, monitoringBusy=false, monitoringManual=false, monitoringLastScan=null, monitoringBeforeManual=null, monitoringMode='paused';
let monitoringQuiet=1,notificationPreferences={errors:true,warnings:true,resolved:false,sound:false};
let scanSuccessUntil=0;
function renderScanButton(button,idle,busy) {
  const state=busy?'loading':Date.now()<scanSuccessUntil?'success':'idle';
  button.disabled=busy;
  button.setAttribute('aria-busy',String(busy));
  button.setAttribute('aria-label',state==='loading'?'Scanning':state==='success'?'Scan complete':idle);
  if(button.dataset.scanState===state) return;
  button.dataset.scanState=state;
  if(state==='loading') button.innerHTML='<span class="scan-dots" aria-hidden="true"><i></i><i></i><i></i></span>';
  else if(state==='success') button.innerHTML='<svg class="scan-check" aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>';
  else button.textContent=idle;
}
function systemHealth(applications) {
  const healthy=applications.filter(app=>app.color==='green').length;
  const warnings=applications.filter(app=>app.color==='yellow').length;
  const total=applications.length;
  const percentage=total?100*(healthy+warnings*.5)/total:null;
  return {healthy,total,percentage,stable:percentage!==null && percentage>=80};
}
function renderSystemHealth(applications) {
  const health=systemHealth(applications);
  $('#system-health-value').textContent=health.percentage===null?'—':`${Math.round(health.percentage)}%`;
  const label=$('#system-health-label');
  const failure=health.percentage!==null && health.percentage<50;
  label.textContent=health.percentage===null?'Waiting':health.stable?'Stable':failure?'Failure':'Attention';
  label.className=`pill ${health.percentage===null?'neutral':health.stable?'stable':failure?'error':'warning'}`;
  const track=$('#system-health-track');
  track.firstElementChild.style.width=`${health.percentage||0}%`;
  if(health.percentage===null) track.removeAttribute('aria-valuenow');
  else track.setAttribute('aria-valuenow',String(health.percentage));
  track.setAttribute('aria-valuetext',health.percentage===null?'No applications':`${Math.round(health.percentage)}% system health. Healthy 100%, warning 50%, error 0%.`);
  
}
function updateMonitoringCountdown() {
  const button=$('#monitoring-scan-now');
  const busy=monitoringBusy||monitoringManual;
  renderScanButton(button,'Scan now',busy);
  const sidebarButton=$('#sidebar-monitoring-scan');
  renderScanButton(sidebarButton,'Scan',busy);
  updateScanningSettings();
  const seconds=monitoringNextScan?Math.max(0,Math.ceil((monitoringNextScan-Date.now())/1000)):null;
  $('#monitoring-countdown').textContent=busy?'Scanning…':seconds===null?(monitoringMode==='changes'?'Watching':'Paused'):`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}
function sortMonitoringApplications(applications) {
  const priority={red:0,yellow:1,green:2};
  return [...applications].sort((a,b)=>(priority[a.color]??3)-(priority[b.color]??3)||a.name.localeCompare(b.name,undefined,{sensitivity:'base',numeric:true}));
}
const applicationActions=document.createElement('div');
applicationActions.className='custom-select-menu application-actions-menu';
applicationActions.setAttribute('popover','manual');
applicationActions.setAttribute('role','group');
document.body.append(applicationActions);
let applicationActionsTrigger=null;
const applicationLogDialog=document.createElement('dialog');
applicationLogDialog.className='application-log-dialog';
applicationLogDialog.innerHTML='<header><h2>Application logs</h2><button type="button" aria-label="Close logs">×</button></header><p></p><pre tabindex="0"></pre>';
document.body.append(applicationLogDialog);
applicationLogDialog.querySelector('button').addEventListener('click',()=>applicationLogDialog.close());
applicationLogDialog.addEventListener('click',event=>{if(event.target===applicationLogDialog){const r=applicationLogDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)applicationLogDialog.close();}});
function sizeApplicationLog() {
  const top=$('.topbar').getBoundingClientRect().top;
  const table=$('.error-table').getBoundingClientRect();
  const frame=$('.workspace-frame'), bounds=frame.getBoundingClientRect(), style=getComputedStyle(frame);
  const bottom=table.height>0?table.bottom:bounds.bottom-parseFloat(style.paddingBottom)-parseFloat(style.borderBottomWidth);
  applicationLogDialog.style.top=`${top}px`;
  applicationLogDialog.style.height=`${Math.max(120,bottom-top)}px`;
}
window.addEventListener('resize',()=>{if(applicationLogDialog.open)sizeApplicationLog();});
applicationLogDialog.addEventListener('close',()=>{applicationLogDialog.style.width='';});
async function openApplicationLog(application) {
  applicationLogDialog.querySelector('h2').textContent=`${application} · Logs`;
  applicationLogDialog.querySelector('p').textContent='Loading…';
  const pre=applicationLogDialog.querySelector('pre');pre.textContent='';
  applicationLogDialog.showModal();
  sizeApplicationLog();
  try{
    const result=await api(`/api/application-log?application=${encodeURIComponent(application)}`);
    applicationLogDialog.querySelector('p').textContent=result.filename+' · Full log';
    pre.textContent=result.text;pre.scrollTop=pre.scrollHeight;
  }catch(error){applicationLogDialog.querySelector('p').textContent=error.message;}
}
applicationActions.addEventListener('toggle',event=>{
  applicationActionsTrigger?.setAttribute('aria-expanded',String(event.newState==='open'));
});
document.addEventListener('pointerdown',event=>{
  if(applicationActions.matches(':popover-open')&&!applicationActions.contains(event.target)&&!applicationActionsTrigger?.contains(event.target)) {
    applicationActions.hidePopover();
  }
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&applicationActions.matches(':popover-open')) {
    applicationActions.hidePopover();
    applicationActionsTrigger?.focus();
    event.preventDefault();
  }
});
window.addEventListener('hashchange',()=>applicationActions.hidePopover());
// Restart has no server flag: the request itself lasts until the app reopens, so track it here.
const applicationActivity=new Map(),scanVisibleUntil=new Map();
function setApplicationActivity(name,activity) {
  if(activity)applicationActivity.set(name,activity);else applicationActivity.delete(name);
  document.querySelectorAll('[data-activity-app]').forEach(element=>{
    if(element.dataset.activityApp!==name)return;
    if(element.classList.contains('status-dot')){element.classList.toggle('status-processing',!!activity||element.dataset.processing==='true');if(activity)element.style.animationDelay=`-${Date.now()%800}ms`;}
    else element.dataset.activity=activity||element.dataset.serverActivity||'';
  });
  updateApplicationTimers();
}
function openApplicationActions(trigger,app,busy) {
  if(applicationActions.matches(':popover-open')&&applicationActionsTrigger===trigger){applicationActions.hidePopover();return;}
  applicationActions.hidePopover();
  applicationActionsTrigger=trigger;
  applicationActions.setAttribute('aria-label',`${app.name} actions`);
  applicationActions.replaceChildren();
  for(const action of ['Scan','Logs','Run','Restart']) {
    const item=document.createElement('button');item.type='button';item.textContent=action;
    item.disabled=action==='Scan'?busy:['Run','Restart'].includes(action)&&!app.control_available;
        item.addEventListener('click',async()=>{
      applicationActions.hidePopover();
      if(action==='Logs'){await openApplicationLog(app.name);return;}
      trigger.disabled=true;
      const activity={Scan:'Scanning',Restart:'Restarting'}[action];
      if(activity)setApplicationActivity(app.name,activity);
      try{
        if(action==='Scan')await api('/api/monitoring-scan',{application:app.name});
        else await api('/api/application-action',{application:app.name,action:action.toLowerCase()});
      }
      catch(error){notify(error.message,null,true);}
      finally{
        trigger.disabled=false;
        // A scan keeps showing while the server reports it; a restart hands over to Running.
        if(activity)setApplicationActivity(app.name,null);
        await refreshMonitoring();
      }
    });
    applicationActions.append(item);
  }
  const rect=trigger.getBoundingClientRect();
  applicationActions.style.left=`${Math.max(8,Math.min(rect.right-160,innerWidth-168))}px`;
  applicationActions.style.top=`${Math.max(8,Math.min(rect.bottom+6,innerHeight-180))}px`;
  applicationActions.showPopover();trigger.setAttribute('aria-expanded','true');
  applicationActions.querySelector('button:not(:disabled)')?.focus();
}
async function refreshMonitoring() {
  if(monitoringLoading||applicationActions.matches(':popover-open')||document.querySelector('.monitoring-run-button:hover, .mini-actions-button:hover')) return;
  monitoringLoading=true;
  try {
    const result=await api('/api/monitoring');
    // A user can open Actions while this request is awaiting its response.
    if(applicationActions.matches(':popover-open')||document.querySelector('.monitoring-run-button:hover, .mini-actions-button:hover')) return;
    renderSystemHealth(result.applications);
    const list=$('#monitoring-applications'); list.replaceChildren();
    const miniList=$('#sidebar-monitoring-applications'); miniList.replaceChildren();
    for(const app of sortMonitoringApplications(result.applications)) {
      const row=document.createElement('div');
      const tone={green:'stable',yellow:'warning',red:'error'}[app.color]||'neutral';
      row.className=`application-strip ${tone}-strip`;
      row.classList.toggle('application-stopped',app.process_running===false);
      row.classList.toggle('application-scanning',!!app.scanning);
      row.setAttribute('aria-busy',String(!!app.scanning));
      const name=document.createElement('span'); name.textContent=app.name;
      const state=document.createElement('span'); state.className='monitoring-state';
      const timing=document.createElement('span');timing.className=`application-timer ${tone}-timer`;
      timing.dataset.nextRun=app.next_run_at||'';timing.dataset.stopped=String(app.process_running===false);timing.dataset.pending=String(app.live_timer_state?app.live_timer_state==='running':!!app.pending);

      // Scans often finish between polls; keep "Scanning" up long enough to be seen.
      if(app.scanning)scanVisibleUntil.set(app.name,Date.now()+1200);
      const showScanning=app.scanning||(scanVisibleUntil.get(app.name)||0)>Date.now();
      timing.dataset.activityApp=app.name;timing.dataset.serverActivity=showScanning?'Scanning':'';
      timing.dataset.activity=applicationActivity.get(app.name)||timing.dataset.serverActivity;
      const label=document.createElement('span');
      label.textContent=({green:'No errors',yellow:'Warning',red:'Error'}[app.color]||'Waiting');
      if(!app.color && !app.pending) label.textContent=app.message?.startsWith('Setup needed')?'Setup needed':app.message?.startsWith('Waiting')?'Waiting':'Unavailable';
      const stopped=app.process_running===false;
      if(stopped)label.textContent='Stopped';
      const dot=document.createElement('span'); dot.className=`status-dot ${stopped?'stopped':tone}-dot`; dot.setAttribute('aria-hidden','true');
      const processing=app.process_running!==false&&(app.live_timer_state?app.live_timer_state==='running':!!app.pending);
      dot.dataset.activityApp=app.name;dot.dataset.processing=String(processing);
      const spinning=processing||!!timing.dataset.activity;
      dot.classList.toggle('status-processing',spinning);
      if(spinning)dot.style.animationDelay=`-${Date.now()%800}ms`;
      const actionsButton=document.createElement('button');actionsButton.type='button';actionsButton.className='monitoring-run-button';
      const actionsText=document.createElement('span');actionsText.textContent='Actions';actionsText.style.whiteSpace='nowrap';actionsButton.append(actionsText);
      actionsButton.setAttribute('aria-label',`Actions for ${app.name}`);actionsButton.setAttribute('aria-expanded','false');
      actionsButton.addEventListener('click',()=>openApplicationActions(actionsButton,app,!!(result.scanning||result.queued)));
      state.append(label,actionsButton,timing,dot); row.append(name,state);
      row.setAttribute('aria-label',`${app.name}: ${label.textContent}${app.color?` (${app.color})`:''}`);
      list.append(row);
      const mini=document.createElement('div'); mini.className='application-row';
      mini.classList.toggle('application-scanning',!!app.scanning);
      mini.setAttribute('aria-label',row.getAttribute('aria-label'));
      const miniControls=document.createElement('span');miniControls.className='mini-application-controls';
      const miniActions=document.createElement('button');miniActions.type='button';miniActions.className='mini-actions-button';
      miniActions.setAttribute('aria-label',`Actions for ${app.name} in Logs Monitored`);
      miniActions.setAttribute('aria-expanded','false');
      miniActions.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m7 10 5 5 5-5"/></svg>';
      miniActions.addEventListener('click',()=>openApplicationActions(miniActions,app,!!(result.scanning||result.queued)));
      miniControls.append(miniActions,dot.cloneNode(true));
      mini.append(name.cloneNode(true),miniControls);
      miniList.append(mini);
    }
    if(!result.applications.length) {const empty=document.createElement('p');empty.textContent='No configured applications.';list.append(empty);miniList.append(empty.cloneNode(true));}
    $('#monitoring-update').textContent=result.error?result.error:result.scanning?'Scanning…':result.last_scan?`Last scan ${new Date(result.last_scan).toLocaleTimeString()}`:'No scans yet';
    const wasScanning=monitoringBusy||monitoringManual;
    monitoringBusy=!!(result.scanning||result.queued);
    if(monitoringManual&&!monitoringBusy&&result.last_scan&&result.last_scan!==monitoringLastScan&&!result.error) {
      scanSuccessUntil=Date.now()+2200;
      setTimeout(updateMonitoringCountdown,2250);
    }
    monitoringMode=result.automatic_mode||'paused';
    monitoringQuiet=result.quiet_seconds||1;
    notificationPreferences=result.notifications||notificationPreferences;
    renderMonitoringPreferences();
    monitoringNextScan=result.next_scan_at?Date.parse(result.next_scan_at):null;
    monitoringLastScan=result.last_scan;
    if(monitoringManual&&result.last_scan!==monitoringBeforeManual&&!monitoringBusy) monitoringManual=false;
    updateMonitoringCountdown();
    updateApplicationTimers();
  } catch(error) {$('#monitoring-update').textContent=error.message; monitoringBusy=false; monitoringManual=false; monitoringNextScan=null; updateMonitoringCountdown(); $('#monitoring-countdown').textContent='Scan unavailable';}
  finally {monitoringLoading=false;}
}
function updateApplicationTimers(){
  document.querySelectorAll('[data-next-run]').forEach(timer=>{
    if(timer.dataset.activity){timer.textContent=timer.dataset.activity;return;}
    if(timer.dataset.stopped==='true'){timer.textContent='—';return;}
    if(timer.dataset.pending==='true'){timer.textContent='Running';return;}
    if(!timer.dataset.nextRun){timer.textContent='—';return;}
    const seconds=Math.max(0,Math.floor((Date.parse(timer.dataset.nextRun)-Date.now())/1000));
    timer.textContent=`${seconds>=3600?String(Math.floor(seconds/3600)).padStart(2,'0')+':':''}${String(Math.floor(seconds/60)%60).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
  });
}
setInterval(updateApplicationTimers,1000);
async function requestMonitoringScan() {
  if(monitoringManual||monitoringBusy) return;
  monitoringBeforeManual=monitoringLastScan; monitoringManual=true; monitoringNextScan=null; updateMonitoringCountdown();
  try {await api('/api/monitoring-scan',{}); await refreshMonitoring();}
  catch(error) {monitoringManual=false;monitoringBusy=false;updateMonitoringCountdown();$('#monitoring-countdown').textContent='Scan failed';$('#sidebar-monitoring-scan').textContent='Scan failed · Retry';}
}
$('#monitoring-scan-now').addEventListener('click',requestMonitoringScan);
$('#sidebar-monitoring-scan').addEventListener('click',requestMonitoringScan);
setInterval(()=>{if(location.hash==='#monitoring')updateMonitoringCountdown();},1000);
window.addEventListener('hashchange',refreshMonitoring);
setInterval(()=>{if(!document.hidden&&location.hash!=='#monitoring')refreshMonitoring();},5000);
setInterval(()=>{if(!document.hidden&&location.hash==='#monitoring')refreshMonitoring();},1000);
// Poll faster around a scheduled scan so short per-application activity is visible.
setInterval(()=>{
  const imminent=monitoringNextScan && monitoringNextScan-Date.now()<2500;
  if(!document.hidden && (monitoringBusy||monitoringManual||imminent))refreshMonitoring();
},250);
refreshMonitoring();

let scanningSettingsSaving=false;
function updateScanningSettings() {
  const enabled=monitoringMode==='changes';
  const busy=monitoringBusy||monitoringManual;
  $('#monitoring-settings-state').textContent=enabled?`Automatic scanning on · ${monitoringQuiet}-second quiet period`:busy?'Automatic scanning paused · current scan finishing':'Automatic scanning paused';
  $('#pause-automatic-scanning').disabled=scanningSettingsSaving;
  $('#resume-automatic-scanning').disabled=scanningSettingsSaving;
  $('#pause-automatic-scanning').setAttribute('aria-pressed',String(!enabled));
  $('#resume-automatic-scanning').setAttribute('aria-pressed',String(enabled));
  const scan=$('#settings-manual-scan');renderScanButton(scan,'Scan now',busy);scan.disabled=busy||scanningSettingsSaving;
}
async function setAutomaticScanning(action) {
  if(scanningSettingsSaving||(action==='pause'&&monitoringMode!=='changes')||(action==='resume'&&monitoringMode==='changes'))return;
  scanningSettingsSaving=true;updateScanningSettings();
  let failure='';
  try {
    const result=await api('/api/monitoring-settings',{action});
    monitoringMode=result.automatic_mode;
    monitoringNextScan=result.next_scan_at?Date.parse(result.next_scan_at):null;
    await refreshMonitoring();
  } catch(error) {failure=error.message;}
  finally {scanningSettingsSaving=false;updateMonitoringCountdown();if(failure)$('#monitoring-settings-state').textContent=failure;}
}
$('#pause-automatic-scanning').addEventListener('click',()=>setAutomaticScanning('pause'));
$('#resume-automatic-scanning').addEventListener('click',()=>setAutomaticScanning('resume'));
$('#settings-manual-scan').addEventListener('click',requestMonitoringScan);

// One shared option panel for every select, including dynamically added rules.
// Keep the real select as the data source so existing profile handlers still work.
(() => {
  const menu=document.createElement('div');
  menu.className='custom-select-menu'; menu.id='custom-select-menu';
  menu.setAttribute('popover','manual'); menu.setAttribute('role','listbox');
  document.body.append(menu);
  let owner=null, options=[], focused=0, prefix='', typedAt=0;
  function close(restore=false) {
    if(!owner) return;
    const select=owner; owner=null;
    select.setAttribute('aria-expanded','false');
    menu.hidePopover();
    if(restore && select.isConnected) select.focus();
  }
  function focusOption(index) {
    focused=(index+options.length)%options.length;
    const item=menu.querySelectorAll('[role="option"]')[focused];
    item?.focus({preventScroll:true}); item?.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function choose(index) {
    if(!owner || !options[index]) return;
    const select=owner, value=options[index].value;
    const changed=select.value!==value;
    select.value=value; close(true);
    if(changed) {
      select.dispatchEvent(new Event('input',{bubbles:true}));
      select.dispatchEvent(new Event('change',{bubbles:true}));
    }
  }
  function open(select) {
    if(select.disabled || select.multiple || select.size>1) return;
    if(owner===select) {close(true);return;}
    close(); owner=select; prefix='';
    // A modal makes elements outside it inert, including body-level popovers.
    (select.closest('dialog')||document.body).append(menu);
    options=Array.from(select.options).filter(option=>!option.disabled && !option.hidden && !option.parentElement.disabled);
    if(!options.length) {owner=null;return;}
    menu.replaceChildren();
    menu.setAttribute('aria-label',select.getAttribute('aria-label')||'Options');
    const allOptions=options.slice();
    const search=document.createElement('input');
    search.type='search'; search.className='dropdown-search'; search.placeholder='Search options…';
    search.setAttribute('aria-label','Search '+(select.getAttribute('aria-label')||'options'));
    const searchHeader=document.createElement('div');searchHeader.className='dropdown-search-header';
    searchHeader.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></svg>';
    searchHeader.append(search);menu.append(searchHeader);
    const list=document.createElement('div');list.className='dropdown-options';menu.append(list);
    function renderOptions() {
    list.replaceChildren();
    options.forEach((option,index)=>{
      const item=document.createElement('button'); item.type='button';
      if(select.dataset.status) item.dataset.status=option.value;
      item.setAttribute('role','option'); item.setAttribute('aria-selected',String(option.selected)); item.tabIndex=-1;
      const text=document.createElement('span'); text.textContent=option.text;
      const check=document.createElement('span'); check.textContent=option.selected?'✓':''; check.setAttribute('aria-hidden','true');
      item.append(text,check); item.addEventListener('click',()=>choose(index)); list.append(item);
    });
    if(!options.length) {const empty=document.createElement('p');empty.className='dropdown-empty';empty.textContent='No matching options';list.append(empty);}
    }
    renderOptions();
    search.addEventListener('input',()=>{options=allOptions.filter(option=>option.text.toLowerCase().includes(search.value.trim().toLowerCase()));focused=0;renderOptions();});
    select.setAttribute('aria-expanded','true'); select.setAttribute('aria-controls',menu.id);
    const rect=select.getBoundingClientRect();
    const desiredWidth=select.id==='home-filter-application'?240:Math.max(rect.width,220);
    menu.style.width=`${Math.min(desiredWidth,innerWidth-16)}px`;
    menu.style.minWidth='0';
    menu.style.maxWidth=`${Math.max(160,innerWidth-16)}px`;
    menu.showPopover();
    const box=menu.getBoundingClientRect();
    menu.style.left=`${Math.max(8,Math.min(rect.right-box.width,innerWidth-box.width-8))}px`;
    const below=innerHeight-rect.bottom-12;
    const above=rect.top-12;
    const upwards=below<Math.min(box.height,160) && above>below;
    menu.style.maxHeight=`${Math.max(60,Math.min(300,upwards?above:below))}px`;
    menu.style.top=`${upwards?Math.max(8,rect.top-Math.min(box.height,above)-6):rect.bottom+6}px`;
    focused=Math.max(0,options.findIndex(option=>option.selected));
    search.focus({preventScroll:true});
  }
  document.addEventListener('pointerdown',event=>{
    const select=event.target.closest('select');
    if(select && !select.multiple && select.size<=1) {event.preventDefault();open(select);}
    else if(owner && !menu.contains(event.target)) close();
  });
  document.addEventListener('keydown',event=>{
    if(owner && menu.contains(event.target)) {
      if(event.target.matches('.dropdown-search')) {
        if(event.key==='ArrowDown'&&options.length){event.preventDefault();focusOption(focused);}
        else if(event.key==='Escape'||event.key==='Tab'){if(event.key==='Escape')event.preventDefault();close(true);}
        return;
      }
      if(['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape','Tab'].includes(event.key)) {
        if(event.key!=='Tab') event.preventDefault();
        if(event.key==='ArrowDown') focusOption(focused+1);
        if(event.key==='ArrowUp') focusOption(focused-1);
        if(event.key==='Home') focusOption(0);
        if(event.key==='End') focusOption(options.length-1);
        if(event.key==='Enter'||event.key===' ') choose(focused);
        if(event.key==='Escape'||event.key==='Tab') close(true);
      } else if(event.key.length===1 && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        prefix=(Date.now()-typedAt<700?prefix:'')+event.key.toLowerCase(); typedAt=Date.now();
        const index=options.findIndex(option=>option.text.toLowerCase().startsWith(prefix));
        if(index>=0) focusOption(index);
      }
    } else if(event.target.matches('select') && ['Enter',' ','ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      event.preventDefault();open(event.target);
    }
  });
  window.addEventListener('resize',()=>close());
  document.addEventListener('scroll',event=>{if(owner && !menu.contains(event.target))close();},true);
  window.addEventListener('hashchange',()=>close());
})();


// Home's error table reads only the saved incident cache. Manual Scan refreshes it.
let homeErrorsLoading=false, homeErrorsFailure='';
let homeStatsLoading=false, homeStatsFailure='';
function renderRunStats(stats) {
  $('#runs-today-count').textContent=stats.scanned_at?stats.today.toLocaleString():'—';
  const chart=$('#daily-runs-chart');chart.replaceChildren();
  const maximum=Math.max(1,...stats.days.map(day=>day.count));
  chart.setAttribute('aria-label',stats.days.map(day=>`${day.date}: ${day.count} completed runs`).join('; '));
  stats.days.forEach((day,index)=>{
    const column=document.createElement('div');column.className='daily-runs-column';
    const track=document.createElement('div');track.className='daily-runs-track';
    const bar=document.createElement('span');bar.style.height=`${day.count/maximum*100}%`;
    if(index===stats.days.length-1)bar.className='today';
    const label=document.createElement('small');label.textContent=day.label;
    track.append(bar);column.append(track,label);chart.append(column);
  });
}
async function refreshHomeStats() {
  if(homeStatsLoading) return;
  homeStatsLoading=true;
  try {
    const stats=await api('/api/home-stats',undefined,{signal:AbortSignal.timeout(10000)});
    renderRunStats(stats);homeStatsFailure='';
  } catch(error) {
    if(homeStatsFailure!==error.message)notify(error.message,null,true);
    homeStatsFailure=error.message;
  } finally {homeStatsLoading=false;}
}
function sizeErrorInfo() {
  const top=$('.topbar').getBoundingClientRect().top;
  // Search opens the same dialog while the home error table is hidden.
  const anchor=$('.error-table').offsetParent?$('.error-table'):$('.search-screen');
  const bottom=anchor.getBoundingClientRect().bottom;
  const dialog=$('#home-error-details');
  dialog.style.top=`${top}px`;
  dialog.style.height=`${bottom-top}px`;
  dialog.style.setProperty('--error-info-height',`${bottom-top}px`);
}
window.addEventListener('resize',()=>{if($('#home-error-details').open)sizeErrorInfo();});
async function openHomeError(id) {
  try {
    const {incident}=await api(`/api/home-errors?id=${encodeURIComponent(id)}`);
    $('#home-error-title').textContent=`${incident.application} · ${incident.severity}`;
    $('#home-error-summary').textContent=[incident.message,incident.filename,incident.run_number?`Run ${incident.run_number}`:'Outside a run',incident.occurrence_count>1?`${incident.occurrence_count} occurrences (${incident.first_time.replace('T',' ')} – ${incident.time.replace('T',' ')})`:'',incident.status,incident.resolved_by_run?`Resolved by clean run ${incident.resolved_by_run}`:''].filter(Boolean).join(' · ');
    $('#home-error-context').textContent=incident.context.join('\n');
    const info=$('#home-error-info');info.replaceChildren();
    const details=document.createElement('dl');details.className='error-info-details';
    for(const [label,value] of Object.entries({Error:incident.message,When:incident.time?.replace('T',' '),Run:incident.run_number||'Outside a run'})) {
      const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=label;detail.textContent=value||'—';details.append(term,detail);
    }
    const heading=document.createElement('h3');heading.textContent='Overview';info.append(heading,details);
    for(const field of ['Notes','Fix']) {
      const label=document.createElement('label');label.className='error-info-field';label.textContent=field;
      const input=document.createElement('textarea');input.rows=3;input.placeholder=field==='Notes'?'Add your notes…':'Describe the fix…';
      const key=`girowatch:error:${id}:${field.toLowerCase()}`;
      if(field==='Notes') {
        input.readOnly=true;input.value=incident.notes||'';input.placeholder='No notes configured for this error.';
      } else {
        try {input.value=localStorage.getItem(key)||'';} catch {}
        input.addEventListener('input',()=>{try {localStorage.setItem(key,input.value);} catch {notify('Could not save this note in your browser.',null,true);}});
      }
      label.append(input);info.append(label);
    }
    const statusLabel=document.createElement('label');statusLabel.className='error-info-field';statusLabel.textContent='Status';
    const statusSelect=document.createElement('select');
    for(const value of ['Active','Resolved','Investigating'])statusSelect.add(new Option(value,value));
    statusSelect.value=incident.status;
    statusSelect.dataset.status=incident.status;
    statusSelect.addEventListener('change',async()=>{
      statusSelect.disabled=true;
      try {await api('/api/home-error-status',{id,status:statusSelect.value});incident.status=statusSelect.value;await refreshHomeErrors();}
      catch(error){statusSelect.value=incident.status;notify(error.message,null,true);}
      finally {statusSelect.dataset.status=statusSelect.value;statusSelect.disabled=false;}
    });
    statusLabel.append(statusSelect);info.append(statusLabel);
    const previewHeading=document.createElement('h3');previewHeading.textContent='Log preview';
    const preview=document.createElement('pre');preview.className='error-info-preview';
    const lines=incident.context||[];
    const match=lines.findIndex(line=>line.includes(incident.message)||/exception|error|warning/i.test(line));
    preview.textContent=lines.slice(Math.max(0,match-2),Math.max(0,match-2)+8).join('\n');
    info.append(previewHeading,preview);
    selectErrorTab('info');
    loadDetailContacts(incident.application);
    sizeErrorInfo();$('#home-error-details').showModal();
  } catch(error) {notify(error.message,null,true);}
}
function loadDetailContacts(application) {
  const contactPanel=$('#home-error-contact');contactPanel.textContent='Loading contact information…';
  api('/api/contacts').then(result=>{
    const records=Object.entries(result.applications).find(([name])=>name.toLowerCase()===application.toLowerCase())?.[1]||[];
    contactPanel.replaceChildren();
    const heading=document.createElement('h3');heading.textContent=`${application} · Contact information`;contactPanel.append(heading);
    if(!records.length||!records.some(record=>Object.values(record).some(value=>value.trim()))) {
      const empty=document.createElement('p');empty.textContent='No contact information saved for this application yet.';contactPanel.append(empty);return;
    }
    for(const record of records) {
      const list=document.createElement('dl');
      for(const [field,label] of Object.entries({payer:'Payer name',country:'Country',code:'Payer code(s)',phone:'Phone number(s)',email:'Email address(es)',notes:'Notes'})) {
        const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=record[field]||'—';list.append(term,value);
      }
      contactPanel.append(list);
    }
  }).catch(()=>{contactPanel.textContent='Contact information could not be loaded. Close and reopen this window to retry.';});
}
// Search results reuse the error dialog: Info is the occurrence, Log is the whole run.
function openSearchRun(group) {
  const outcome=group.outcome==='Error'?'Unsuccessful':group.outcome;
  $('#home-error-title').textContent=`${group.application} · Run ${group.run_number}`;
  $('#home-error-summary').textContent=[group.source_file,`Run ${group.run_number}`,group.run_time,`${group.run_lines.length} lines`,outcome].filter(Boolean).join(' · ');
  $('#home-error-context').textContent=group.run_lines.join('\n');
  const info=$('#home-error-info');info.replaceChildren();
  const details=document.createElement('dl');details.className='error-info-details';
  for(const [label,value] of Object.entries({Order:activeSearch?.query,Run:group.run_number,Group:group.group_number,Started:group.run_time,File:group.source_file,Status:outcome,Alert:group.error_type==='None'?'':group.error_type})) {
    const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=label;detail.textContent=value||'—';details.append(term,detail);
  }
  const heading=document.createElement('h3');heading.textContent='Overview';
  const previewHeading=document.createElement('h3');previewHeading.textContent='Order lines';
  const preview=document.createElement('pre');preview.className='error-info-preview';preview.textContent=group.lines.join('\n');
  info.append(heading,details,previewHeading,preview);
  selectErrorTab('info');loadDetailContacts(group.application);
  sizeErrorInfo();$('#home-error-details').showModal();
}
$('#home-error-details header button').addEventListener('click',()=>$('#home-error-details').close());
$('#home-error-details').addEventListener('click',event=>{
  const dialog=event.currentTarget;
  if(event.target!==dialog)return;
  const box=dialog.getBoundingClientRect();
  if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();
});
function selectErrorTab(view) {
  for(const name of ['info','log','contact']) {
    const tab=$(`#error-tab-${name}`),selected=name===view;
    tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
  }
  $('#home-error-context').hidden=view!=='log';$('#home-error-info').hidden=view!=='info';
  $('#home-error-contact').hidden=view!=='contact';
  $('#home-error-summary').hidden=view!=='log';
}
for(const name of ['info','log','contact']) {
  const tab=$(`#error-tab-${name}`);
  tab.addEventListener('click',()=>selectErrorTab(name));
  tab.addEventListener('keydown',event=>{
    if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const names=['info','log','contact'],direction=['ArrowUp','ArrowLeft'].includes(event.key)?-1:1;const next=event.key==='Home'?'info':event.key==='End'?'contact':names[(names.indexOf(name)+direction+3)%3];selectErrorTab(next);$(`#error-tab-${next}`).focus();
  });
}
function activeIncidentSummary(incidents) {
  const active=incidents.filter(item=>item.status==='Active'||item.status==='Investigating');
  const error=active.some(item=>item.severity==='Error');
  return {count:active.length,label:error?'Error':active.length?'Warning':'Clear',
    tone:error?'error':active.length?'warning':'stable',
    caption:error?'Errors need attention':active.length?'Warnings need review':'No active incidents'};
}
function renderActiveIncidents(incidents) {
  const summary=activeIncidentSummary(incidents);
  $('#active-incidents-count').textContent=summary.count.toLocaleString();
  const label=$('#active-incidents-label');label.textContent=summary.label;label.className=`pill ${summary.tone}`;
  $('#active-incidents-caption').textContent=summary.caption;
}
function matchesIncidentFilters(incident, application, severity) {
  return (!application || incident.application===application) && (!severity || incident.severity===severity);
}
function createLogsEmptyState(message) {
  const empty=document.createElement('div');empty.className='home-errors-empty';
  empty.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/></svg><h3>All clear here.</h3><p></p>';
  empty.querySelector('p').textContent=message;
  return empty;
}
function applyHomeErrorFilters() {
  const app=$('#home-filter-application').value;
  const severity=document.querySelector('[data-incident-severity][aria-pressed="true"]')?.dataset.incidentSeverity||'';
  const counts={'':0,Error:0,Warning:0};let visible=0;
  for(const row of document.querySelectorAll('#home-error-rows .table-row')) {
    if(matchesIncidentFilters(row.dataset,app,'')) {counts['']++;counts[row.dataset.severity]++;}
    row.hidden=!matchesIncidentFilters(row.dataset,app,severity);
    if(!row.hidden)visible++;
  }
  for(const button of document.querySelectorAll('[data-incident-severity]'))button.querySelector('span').textContent=counts[button.dataset.incidentSeverity]||0;
  $('#incident-total-count').textContent=visible;
  for(const id of ['application'])$(`#home-filter-${id}`).classList.toggle('filter-active',!!$(`#home-filter-${id}`).value);
  const empty=$('#home-filter-empty');if(empty)empty.remove();
  if(document.querySelector('#home-error-rows .table-row')&&!document.querySelector('#home-error-rows .table-row:not([hidden])')) {
    const text=createLogsEmptyState('No errors match these filters.');text.id='home-filter-empty';$('#home-error-rows').append(text);
  }
}
for(const name of ['application'])$(`#home-filter-${name}`).addEventListener('change',applyHomeErrorFilters);
for(const button of document.querySelectorAll('[data-incident-severity]'))button.addEventListener('click',()=>{
  for(const tab of document.querySelectorAll('[data-incident-severity]'))tab.setAttribute('aria-pressed',String(tab===button));
  applyHomeErrorFilters();
});
function updateHomeErrorFilters(incidents) {
  for(const field of ['application']) {
    const select=$(`#home-filter-${field}`),selected=select.value,counts=new Map();
    for(const item of incidents)counts.set(item[field],(counts.get(item[field])||0)+1);
    const choices=[...counts].sort((a,b)=>field==='message'?b[1]-a[1]:a[0].localeCompare(b[0]));
    const options=[new Option(field==='application'?'All applications':'All messages',''),...choices.map(([value,count])=>new Option(`${value} (${count})`,value))];
    if(selected&&!counts.has(selected))options.push(new Option(selected,selected));
    select.replaceChildren(...options);select.value=selected;
  }
}
function bindIncidentRow(row, id) {
  row.setAttribute('tabindex','0');
  row.setAttribute('aria-haspopup','dialog');
  row.addEventListener('click',event=>{
    if(event.target.closest('button,a,input,select,textarea') || window.getSelection()?.toString())return;
    openHomeError(id);
  });
  row.addEventListener('keydown',event=>{
    if(event.target!==row || !['Enter',' '].includes(event.key))return;
    event.preventDefault();
    openHomeError(id);
  });
}
async function refreshHomeErrors() {
  if(homeErrorsLoading) return;
  homeErrorsLoading=true;
  try {
    const result=await api('/api/home-errors',undefined,{signal:AbortSignal.timeout(10000)});
    renderActiveIncidents(result.incidents);
    announceIncidentChanges(result.incidents);
    updateHomeErrorFilters(result.incidents);
    homeErrorsFailure='';
    const body=$('#home-error-rows');
    body.replaceChildren();
    for(const item of result.incidents) {
      const row=document.createElement('div');row.className='error-columns table-row';row.setAttribute('role','row');
      row.dataset.application=item.application;row.dataset.message=item.message;row.dataset.severity=item.severity;
      const cell=(text)=>{const node=document.createElement('span');node.setAttribute('role','cell');if(text)node.textContent=text;row.append(node);return node;};
      cell(item.application);
      cell(item.time?new Date(item.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—');
      const badge=(text,tone)=>{const node=document.createElement('span');node.className=`pill ${tone}`;node.textContent=text;return node;};
      cell().append(badge(item.severity,item.severity==='Error'?'error':'warning'));
      const message=cell(item.message);message.className='home-error-message';
      cell().append(badge(item.status,item.status==='Resolved'?'stable':'error'));
      const button=document.createElement('button');button.type='button';button.className='info-button';button.textContent='Info';button.setAttribute('aria-label',`Details for ${item.application}: ${item.message}`);button.addEventListener('click',()=>openHomeError(item.id));cell().append(button);
      bindIncidentRow(row,item.id);
      body.append(row);
    }
    if(!result.incidents.length) body.append(createLogsEmptyState('No warnings or errors in today’s scanned logs.'));
    applyHomeErrorFilters();
    const heading=$('.error-table > .table-heading');heading.style.paddingRight=`${body.offsetWidth-body.clientWidth}px`;
  } catch(error) {if(homeErrorsFailure!==error.message)notify(error.message,null,true);homeErrorsFailure=error.message;}
  finally {homeErrorsLoading=false;}
}
async function refreshHome() {
  await Promise.allSettled([refreshHomeErrors(),refreshHomeStats()]);
}
const homeVisible=()=>$('.sonda-shell').dataset.page==='home';
window.addEventListener('hashchange',()=>{if(homeVisible())refreshHome();});
document.addEventListener('visibilitychange',()=>{if(homeVisible()&&!document.hidden)refreshHome();});
setInterval(()=>{if(!document.hidden){if(homeVisible())refreshHome();else refreshHomeErrors();}},5000);
if(homeVisible())refreshHome();

// Contact records are separate from monitoring and configuration profiles.
let contactRecords={},contactApplication='',contactDirty=false,contactSaving=false;
const contactDrafts=new Map();
function contactNames() {
  return [...new Set([...profileCatalog.map(item=>item.name),...Object.keys(contactRecords)])].sort((a,b)=>a.localeCompare(b));
}
function renderContactApps() {
  const list=$('#contacts-app-list'),query=$('#contacts-app-search').value.toLowerCase();list.replaceChildren();
  for(const name of contactNames().filter(name=>name.toLowerCase().includes(query))) {
    const button=document.createElement('button');button.type='button';button.className='contact-app'+(name===contactApplication?' selected':'');
    const title=document.createElement('strong');title.textContent=name;
    const count=document.createElement('small');const records=contactDrafts.get(name)||contactRecords[name]||[];count.textContent=records.some(item=>Object.values(item).some(value=>value.trim()))?'Contact information':'Not configured';
    button.append(title,count);button.addEventListener('click',()=>{contactApplication=name;renderContactApps();renderContacts();});list.append(button);
  }
  if(!list.children.length){const empty=document.createElement('p');empty.className='contacts-empty';empty.textContent='No applications found.';list.append(empty);}
}
function currentContacts() {const records=contactDrafts.get(contactApplication)||contactRecords[contactApplication]||[];return records.length?records:contactApplication?[{payer:'',country:'',code:'',phone:'',email:'',notes:''}]:[];}
function markContactDraft(records) {
  contactDrafts.set(contactApplication,records);contactDirty=true;$('#contacts-save-state').textContent='Unsaved changes';renderContactApps();
}
function renderContacts() {
  const records=currentContacts(),cards=$('#contacts-cards');cards.replaceChildren();
  $('#contacts-app-title').textContent=contactApplication||'Select an application';
  $('#contacts-count').textContent=contactApplication?`${records.length} contact${records.length===1?'':'s'}`:'';
  $('#contacts-save').disabled=!contactApplication||contactSaving;
  $('#contacts-save-state').textContent=contactDrafts.has(contactApplication)?'Unsaved changes':'';
  if(!records.length){const empty=document.createElement('div');empty.className='contacts-empty';const title=document.createElement('h3');title.textContent=contactApplication?'No contacts yet':'Your application contacts';const text=document.createElement('p');text.textContent=contactApplication?'Add a contact to keep payer details and support information here.':'Choose an application or add one to get started.';empty.append(title,text);cards.append(empty);}
  records.forEach((record,index)=>{
    const card=document.createElement('article');card.className='contact-card';
    const header=document.createElement('header'),heading=document.createElement('h3'),remove=document.createElement('button');heading.textContent=record.payer||`Contact ${index+1}`;remove.type='button';remove.textContent='Remove';remove.className='contact-remove';
    remove.addEventListener('click',()=>{const next=structuredClone(currentContacts());next.splice(index,1);markContactDraft(next);renderContacts();});heading.textContent='Contact information';header.append(heading);card.append(header);
    const grid=document.createElement('div');grid.className='contact-fields';
    for(const [field,title] of Object.entries({payer:'Payer name',country:'Country',code:'Payer code(s)',phone:'Phone number(s)',email:'Email address(es)',notes:'Notes'})) {
      const label=document.createElement('label');label.textContent=title;label.className=`contact-field contact-field-${field}`;
      const input=document.createElement(field==='notes'||field==='email'||field==='phone'?'textarea':'input');if(input.tagName==='TEXTAREA')input.rows=field==='notes'?3:2;
      input.value=record[field]||'';input.placeholder={payer:'Payer or support team',country:'Country',code:'Code or codes',phone:'Phone numbers and extensions',email:'Email addresses',notes:'Instructions, support hours, or escalation details'}[field];input.maxLength=10000;
      if(field==='phone'||field==='email')input.rows=Math.max(5,input.value.split('\n').length+1);
      input.addEventListener('input',()=>{const next=structuredClone(currentContacts());next[index][field]=input.value;markContactDraft(next);if(field==='payer')heading.textContent=input.value||`Contact ${index+1}`;});label.append(input);grid.append(label);
    }
    card.append(grid);cards.append(card);
  });
}
async function loadContacts() {
  try {const [result,state]=await Promise.all([api('/api/contacts'),api('/api/state')]);contactRecords=result.applications;profileCatalog=state.applications;if(!contactApplication)contactApplication=contactNames()[0]||'';renderContactApps();renderContacts();}
  catch(error){notify(error.message,null,true);}
}
$('#contacts-app-search').addEventListener('input',renderContactApps);
$('#contacts-save').addEventListener('click',async()=>{
  if(contactSaving||!contactApplication)return;
  const name=contactApplication,records=structuredClone(currentContacts());contactSaving=true;$('#contacts-save').disabled=true;
  try {const result=await api('/api/contacts',{application:name,contacts:records});contactRecords=result.applications;
    if(JSON.stringify(contactDrafts.get(name))===JSON.stringify(records))contactDrafts.delete(name);
    contactDirty=contactDrafts.size>0;$('#contacts-save-state').textContent=contactDrafts.has(name)?'Unsaved changes':'Contacts saved';renderContactApps();
  } catch(error){notify(error.message,null,true);}finally{contactSaving=false;$('#contacts-save').disabled=!contactApplication;}
});
$('#contacts-new-app').addEventListener('click',()=>{$('#contacts-create-name').value='';$('#contacts-create').showModal();});
$('#contacts-create-close').addEventListener('click',()=>$('#contacts-create').close());
$('#contacts-create-form').addEventListener('submit',event=>{
  event.preventDefault();const name=$('#contacts-create-name').value.trim();if(!name)return;
  contactApplication=contactNames().find(item=>item.toLowerCase()===name.toLowerCase())||name;
  if(!Object.hasOwn(contactRecords,contactApplication)&&!contactDrafts.has(contactApplication))contactDrafts.set(contactApplication,[]);
  contactDirty=contactDrafts.size>0;$('#contacts-create').close();renderContactApps();renderContacts();
});
window.addEventListener('beforeunload',event=>{if(contactDirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',()=>{if(location.hash==='#contacts')loadContacts();});
if(location.hash==='#contacts')loadContacts();

const displaySizes={out:.8,normal:1,in:1.2};
function applyDisplaySize(mode) {
  if(!Object.hasOwn(displaySizes,mode))mode='normal';
  document.documentElement.style.setProperty('--ui-scale',displaySizes[mode]);
  document.querySelectorAll('[data-zoom]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.zoom===mode)));
  window.dispatchEvent(new Event('resize'));
}
for(const button of document.querySelectorAll('[data-zoom]'))button.addEventListener('click',()=>{
  applyDisplaySize(button.dataset.zoom);
  try{localStorage.setItem('girowatch:display-size',button.dataset.zoom);}catch{}
});
try{applyDisplaySize(localStorage.getItem('girowatch:display-size')||'normal');}catch{applyDisplaySize('normal');}

const systemTheme=window.matchMedia('(prefers-color-scheme: dark)');
let selectedTheme='system';
try {const saved=localStorage.getItem('girowatch:theme');if(['light','dark','system'].includes(saved))selectedTheme=saved;}catch{}
function applyTheme(choice) {
  selectedTheme=choice;
  document.documentElement.dataset.theme=choice==='system'?(systemTheme.matches?'dark':'light'):choice;
  document.querySelectorAll('[data-theme-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.themeChoice===choice)));
}
for(const button of document.querySelectorAll('[data-theme-choice]'))button.addEventListener('click',()=>{applyTheme(button.dataset.themeChoice);try{localStorage.setItem('girowatch:theme',selectedTheme);}catch{}});
systemTheme.addEventListener('change',()=>{if(selectedTheme==='system')applyTheme('system');});
applyTheme(selectedTheme);

let preferencesSaving=false;
function renderMonitoringPreferences() {
  document.querySelectorAll('[data-quiet]').forEach(button=>{button.setAttribute('aria-pressed',String(Number(button.dataset.quiet)===monitoringQuiet));button.disabled=preferencesSaving;});
  document.querySelectorAll('[data-notification]').forEach(input=>{input.checked=!!notificationPreferences[input.dataset.notification];input.disabled=preferencesSaving;});
}
async function saveMonitoringPreferences(changes) {
  if(preferencesSaving)return;
  preferencesSaving=true;renderMonitoringPreferences();
  try {
    const result=await api('/api/monitoring-settings',{action:'preferences',...changes});
    monitoringQuiet=result.quiet_seconds;notificationPreferences=result.notifications;
  }catch(error){notify(error.message,null,true);}
  finally {preferencesSaving=false;renderMonitoringPreferences();}
}
for(const button of document.querySelectorAll('[data-quiet]'))button.addEventListener('click',()=>saveMonitoringPreferences({quiet_seconds:Number(button.dataset.quiet)}));
for(const input of document.querySelectorAll('[data-notification]'))input.addEventListener('change',()=>saveMonitoringPreferences({notifications:{[input.dataset.notification]:input.checked}}));
let notificationBaseline=null,notificationDate='',alertAudio=null;
document.addEventListener('pointerdown',()=>{
  if(!alertAudio&&window.AudioContext)alertAudio=new AudioContext();
  if(alertAudio?.state==='suspended')alertAudio.resume().catch(()=>{});
});
function playIncidentTone() {
  if(!notificationPreferences.sound||!alertAudio||alertAudio.state!=='running')return;
  const oscillator=alertAudio.createOscillator(),gain=alertAudio.createGain(),now=alertAudio.currentTime;
  oscillator.type='sine';oscillator.frequency.setValueAtTime(660,now);oscillator.frequency.setValueAtTime(880,now+.13);
  gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(.07,now+.02);gain.gain.exponentialRampToValueAtTime(.001,now+.35);
  oscillator.connect(gain);gain.connect(alertAudio.destination);oscillator.start(now);oscillator.stop(now+.36);
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
}
function announceIncidentChanges(incidents) {
  const date=new Date().toLocaleDateString(),previous=notificationDate===date?notificationBaseline:null;
  const next=new Map(incidents.map(item=>[item.id,{status:item.status,time:item.time,count:item.occurrence_count}]));
  notificationBaseline=next;notificationDate=date;
  if(!previous)return;
  const alerts=incidents.filter(item=>{
    const old=previous.get(item.id),resolved=item.status==='Resolved';
    if(old&&old.status!==item.status&&resolved)return notificationPreferences.resolved;
    const newOccurrence=!old||old.time!==item.time||old.count!==item.occurrence_count;
    return newOccurrence&&!resolved&&notificationPreferences[item.severity==='Error'?'errors':'warnings'];
  });
  if(!alerts.length)return;
  playIncidentTone();
  for(const item of alerts.slice(0,3)) {
    const toast=document.createElement('div');toast.className='incident-toast';toast.dataset.tone=item.status==='Resolved'?'resolved':item.severity==='Error'?'error':'warning';
    const title=document.createElement('strong');title.textContent=`${item.application} · ${item.status==='Resolved'?'Resolved':item.severity}`;
    const message=document.createElement('span');message.textContent=item.message;
    const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Dismiss notification');close.addEventListener('click',()=>toast.remove());
    toast.append(title,message,close);$('#incident-notifications').append(toast);setTimeout(()=>toast.remove(),8000);
  }
  while($('#incident-notifications').children.length>3)$('#incident-notifications').firstElementChild.remove();
}

// Resize only the popup width; keep its existing vertical alignment.
function resizeErrorWidth(width) {
  const dialog=$('#home-error-details'),box=dialog.getBoundingClientRect(),tabs=dialog.querySelector('.error-detail-tabs').getBoundingClientRect();
  const center=box.left+box.width/2;
  const maximum=Math.max(260,2*Math.min(center-12,innerWidth-center-tabs.width-28));
  dialog.style.width=`${Math.max(Math.min(320,maximum),Math.min(maximum,width))}px`;
}
const errorResize=$('#resize-error-details');
let errorResizeStart=null;
errorResize.addEventListener('pointerdown',event=>{
  if(event.button!==0)return;
  event.preventDefault();errorResizeStart={x:event.clientX,width:$('#home-error-details').getBoundingClientRect().width};errorResize.setPointerCapture(event.pointerId);
});
errorResize.addEventListener('pointermove',event=>{if(errorResizeStart)resizeErrorWidth(errorResizeStart.width+2*(event.clientX-errorResizeStart.x));});
for(const event of ['pointerup','pointercancel','lostpointercapture'])errorResize.addEventListener(event,()=>{errorResizeStart=null;});
errorResize.addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();resizeErrorWidth($('#home-error-details').getBoundingClientRect().width+(event.key==='ArrowRight'?40:-40));}});
$('#home-error-details').addEventListener('close',()=>{$('#home-error-details').style.width='';errorResizeStart=null;});
