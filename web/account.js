'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  let setup=false, busy=false, loaded=false, user=null, resetToken='';
  const form=$('#account-form'), recoverForm=$('#account-recover-form'), dialog=$('#account-profile-dialog');
  async function request(payload) {
    let response,result;
    try {response=await fetch('/api/account',payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{cache:'no-store'});}
    catch(error) {if(window.isUnreachable?.(error))window.showLoadFailure?.();throw error;}
    try {result=await response.json();}
    catch {if(response.status>=500)window.showLoadFailure?.();throw new Error('Could not sign in. Please retry.');}
    if(!response.ok)throw Object.assign(new Error(result.error || 'Could not sign in. Please retry.'),{expired:!!result.expired});
    return result;
  }
  const initials=name=>name.trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase();
  const element=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
  const svg=paths=>{const node=document.createElementNS('http://www.w3.org/2000/svg','svg');node.setAttribute('viewBox','0 0 24 24');node.setAttribute('aria-hidden','true');for(const d of paths){const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',d);node.append(path);}return node;};
  const KEY=['M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z','M16.5 7.5h.01'];
  const TRASH=['M3 6h18','M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6','M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2','M10 11v6','M14 11v6'];
  async function enter(next, transition=false) {
    user=next;window.giroWatchUser=next;
    if(!loaded) {
      await new Promise((resolve,reject)=>{
        const script=document.createElement('script');script.src='/design.js?v=12';
        script.onload=resolve;script.onerror=()=>{script.remove();window.showLoadFailure?.();reject(new Error('Could not load GiroWatch. Please retry.'));};document.head.append(script);
      });
      loaded=true;
    }
    const shell=$('.sonda-shell');
    if(transition && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      shell.classList.add('app-enter');
      setTimeout(()=>shell.classList.remove('app-enter'),600);
    }
    $('#account-screen').hidden=true;shell.hidden=false;
    $('#account-profile-name').textContent=next.name;$('#account-profile-email').textContent=next.email;
    $('#account-profile-role').textContent=next.role;$('#account-open-people').hidden=next.role!=='Manager';
    $('#account-profile-initials').textContent=initials(next.name);
    $('.user-initials').textContent=$('#account-profile-initials').textContent;
    $('.user-icon').setAttribute('aria-label',`Account for ${next.name}`);
    if(location.hash==='#settings')openView('settings');
  }
  function showError(message) {$('#account-error').textContent=message;$('#account-error').hidden=false;}
  async function check() {
    $('#account-retry').hidden=true;$('#account-error').hidden=true;
    try {
      const result=await request();
      if(result.user){await enter(result.user);return;}
      setup=result.needsSetup;
      $('#account-heading').textContent=setup?'Your workspace starts here':'Welcome back';
      $('#account-description').textContent=setup?'Create your account to get started.':'Sign in to your workspace.';
      $('#account-name-row').hidden=!setup;form.elements.name.required=setup;
      form.elements.password.minLength=setup?10:1;form.elements.password.autocomplete=setup?'new-password':'current-password';
      $('#account-password-hint').hidden=!setup;$('#account-submit').textContent=setup?'Create account':'Sign in';
      $('#account-forgot').hidden=setup;
      $('#account-note').textContent=setup?'Your existing applications and monitoring data stay in place.':'Need an account? Ask someone in your workspace to add you.';
      form.hidden=false;
    }catch(error){showError(error.message);$('#account-retry').hidden=false;}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;busy=true;$('#account-error').hidden=true;
    $('#account-submit').disabled=true;$('#account-submit').textContent='Please wait…';
    try {
      const result=await request({...Object.fromEntries(new FormData(form)),action:setup?'create':'login'});
      form.elements.password.value='';await enter(result.user,true);
    }catch(error){showError(error.message);}
    finally{busy=false;$('#account-submit').disabled=false;$('#account-submit').textContent=setup?'Create account':'Sign in';}
  });
  $('#account-password-toggle').addEventListener('click',()=>{
    const input=form.elements.password;input.type=input.type==='password'?'text':'password';
    $('#account-password-toggle').setAttribute('aria-label',input.type==='password'?'Show password':'Hide password');
    $('#account-password-toggle').setAttribute('aria-pressed',String(input.type==='text'));
  });
  $('#account-retry').addEventListener('click',check);
  window.addEventListener('account-expired',()=>location.reload());

  // Forgot password: email + authenticator code, then a pop-up that stays until a new password is saved.
  function showRecovery(on) {
    form.hidden=on;recoverForm.hidden=!on;$('#account-error').hidden=true;
    $('#account-heading').textContent=on?'Reset your password':'Welcome back';
    $('#account-description').textContent=on?'Enter the current code from the GiroWatch entry in your authenticator app.':'Sign in to your workspace.';
    $('#account-note').textContent=on?'No authenticator set up? Ask your Manager to reset your password.':'Need an account? Ask someone in your workspace to add you.';
    (on?recoverForm.elements.email:form.elements.email).focus();
  }
  $('#account-forgot').addEventListener('click',()=>showRecovery(true));
  $('#account-recover-back').addEventListener('click',()=>showRecovery(false));
  recoverForm.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;busy=true;$('#account-error').hidden=true;
    const button=$('#account-recover-submit');button.disabled=true;button.textContent='Checking…';
    try {
      resetToken=(await request({...Object.fromEntries(new FormData(recoverForm)),action:'recover'})).resetToken;
      $('#account-reset-form').hidden=false;$('#account-reset-expired').hidden=true;$('#account-reset-title').textContent='Choose a new password';
      $('#account-reset-error').hidden=true;$('#account-reset-dialog').showModal();$('#account-reset-form').elements.password.focus();
    }catch(error){showError(error.message);}
    finally{busy=false;button.disabled=false;button.textContent='Continue';}
  });
  // Escape must not close it. Chrome can ignore a prevented cancel, so reopen if it closes before a password is saved.
  const resetDialog=$('#account-reset-dialog');
  resetDialog.addEventListener('cancel',event=>event.preventDefault());
  resetDialog.addEventListener('keydown',event=>{if(event.key==='Escape')event.preventDefault();});
  resetDialog.addEventListener('close',()=>{if(resetToken)resetDialog.showModal();});
  $('#account-reset-show').addEventListener('change',event=>{for(const name of ['password','confirm'])$('#account-reset-form').elements[name].type=event.target.checked?'text':'password';});
  $('#account-reset-form').addEventListener('submit',async event=>{
    event.preventDefault();const target=event.currentTarget,problem=$('#account-reset-error');problem.hidden=true;
    const {password,confirm}=Object.fromEntries(new FormData(target));
    if(password!==confirm){problem.textContent='The passwords do not match.';problem.hidden=false;return;}
    const button=$('#account-reset-save');button.disabled=true;button.textContent='Saving…';
    try {
      const result=await request({action:'recover-complete',token:resetToken,password});
      resetToken='';target.reset();$('#account-reset-dialog').close();recoverForm.reset();recoverForm.hidden=true;await enter(result.user,true);
    }catch(error){
      if(error.expired){target.hidden=true;$('#account-reset-expired').hidden=false;$('#account-reset-title').textContent='Reset expired';}
      else {problem.textContent=error.message;problem.hidden=false;}
    }finally{button.disabled=false;button.textContent='Save and sign in';}
  });
  $('#account-reset-restart').addEventListener('click',()=>{resetToken='';$('#account-reset-dialog').close();$('#account-reset-form').reset();recoverForm.elements.code.value='';recoverForm.elements.code.focus();});

  // The account pop-up: one view at a time.
  const TITLES={home:'Your account',people:'People',add:'Add a person',notifications:'Notifications',settings:'Settings',appearance:'Appearance',security:'Security'};
  const message=text=>{$('#account-profile-message').textContent=text||'';};
  function openView(name) {
    if(name==='people'&&user?.role!=='Manager')name='home';
    dialog.dataset.view=name;$('#account-profile-heading').textContent=TITLES[name];
    for(const view of dialog.querySelectorAll('[data-account-view]'))view.hidden=view.dataset.accountView!==name;
    message('');
    if(name==='people')loadPeople();
    if(name==='security')renderSecurity();
    if(name==='add')$('#account-add-form').reset();
    if(!dialog.open)dialog.showModal();
    dialog.querySelector(`[data-account-view="${name}"] :is(input,button)`)?.focus();
  }
  window.openAccountView=openView;
  $('.user-icon').addEventListener('click',()=>openView('home'));
  dialog.addEventListener('click',event=>{const target=event.target.closest('[data-open-view]');if(target)openView(target.dataset.openView);});
  $('#account-profile-close').addEventListener('click',()=>dialog.close());
  $('#account-add-form').addEventListener('submit',async event=>{
    event.preventDefault();const target=event.currentTarget,button=target.querySelector('[type="submit"]');
    button.disabled=true;message('');
    try {await request({...Object.fromEntries(new FormData(target)),action:'create'});openView('people');message('Account created. They can now sign in.');}
    catch(error){message(error.message);}
    finally{button.disabled=false;}
  });
  $('#account-logout').addEventListener('click',async()=>{
    $('#account-logout').disabled=true;
    try{await request({action:'logout'});location.reload();}
    catch(error){message(error.message);$('#account-logout').disabled=false;}
  });

  // People: the Manager adds people, resets passwords and removes accounts.
  let people=[], resetting='', removing='';
  async function loadPeople() {
    resetting='';removing='';$('#account-people').replaceChildren(element('li','account-view-intro','Loading people…'));
    try{people=(await request({action:'people'})).people;renderPeople();}
    catch(error){$('#account-people').replaceChildren();message(error.message);}
  }
  function renderPeople() {
    const list=$('#account-people');list.replaceChildren();
    for(const person of people) {
      const item=element('li'),row=element('div','account-person'),details=element('div'),title=element('div','account-profile-title');
      title.append(element('b','',person.name),element('span','account-role',person.role));details.append(title,element('p','',person.email));
      row.append(element('span','account-avatar',initials(person.name)),details);
      if(resetting!==person.id&&removing!==person.id) {
        const actions=element('div','account-person-actions');
        if(person.id!==user.id) {
          const remove=element('button','account-remove account-remove-icon');remove.type='button';remove.title=`Remove ${person.name}`;remove.setAttribute('aria-label',`Remove ${person.name}`);
          remove.append(svg(TRASH));remove.addEventListener('click',()=>{removing=person.id;resetting='';message('');renderPeople();});actions.append(remove);
        }
        const reset=element('button');reset.type='button';reset.append(svg(KEY),'Reset password');
        reset.addEventListener('click',()=>{resetting=person.id;removing='';message('');renderPeople();});actions.append(reset);row.append(actions);
      }
      item.append(row);
      if(resetting===person.id)item.append(resetForm(person));
      if(removing===person.id)item.append(removeConfirm(person));
      list.append(item);
    }
  }
  function resetForm(person) {
    const box=element('form','account-inline'),label=element('label','',`New password for ${person.name}`),input=element('input');
    Object.assign(input,{name:'password',type:'password',autocomplete:'new-password',minLength:10,maxLength:256,required:true});
    label.append(input,element('small','',`At least 10 characters. ${person.id===user.id?'Your other devices will be signed out.':'They will be signed out everywhere.'}`));
    const actions=element('div','account-view-actions'),cancel=element('button','','Cancel'),save=element('button','account-primary','Save password');
    cancel.type='button';save.type='submit';cancel.addEventListener('click',()=>{resetting='';renderPeople();});actions.append(cancel,save);box.append(label,actions);
    box.addEventListener('submit',async event=>{
      event.preventDefault();save.disabled=true;message('');
      try{await request({action:'reset',userId:person.id,password:input.value});resetting='';renderPeople();message(person.id===user.id?'Your password was changed.':`Password reset. ${person.name} now signs in with the new password.`);}
      catch(error){message(error.message);save.disabled=false;}
    });
    setTimeout(()=>input.focus());return box;
  }
  function removeConfirm(person) {
    const box=element('div','account-inline');box.setAttribute('role','group');box.setAttribute('aria-label',`Remove ${person.name}`);
    box.append(element('p','account-view-intro',`Remove ${person.name}? They will be signed out and can no longer sign in.`));
    const actions=element('div','account-view-actions'),cancel=element('button','','Cancel'),confirm=element('button','account-remove','Remove person');
    cancel.type=confirm.type='button';cancel.addEventListener('click',()=>{removing='';renderPeople();});
    confirm.addEventListener('click',async()=>{
      confirm.disabled=true;message('');
      try{await request({action:'remove',userId:person.id});people=people.filter(item=>item.id!==person.id);removing='';renderPeople();message(`${person.name} was removed.`);}
      catch(error){message(error.message);confirm.disabled=false;}
    });
    actions.append(cancel,confirm);box.append(actions);setTimeout(()=>cancel.focus());return box;
  }

  // Security: an authenticator app lets each person reset a forgotten password from the sign-in page.
  let setupKey=null, unlinking=false;
  function passwordForm(labelText,hint,buttonText,danger,onSubmit,onCancel) {
    const box=element('form','account-inline'),label=element('label','',labelText),input=element('input');
    Object.assign(input,{name:'password',type:'password',autocomplete:'current-password',maxLength:256,required:true});
    label.append(input);if(hint)label.append(element('small','',hint));
    const actions=element('div','account-view-actions'),back=element('button','',onCancel?'Cancel':'Back'),submit=element('button',danger?'account-remove':'account-primary',buttonText);
    back.type='button';submit.type='submit';back.addEventListener('click',onCancel||(()=>openView('home')));actions.append(back,submit);box.append(label,actions);
    box.addEventListener('submit',async event=>{event.preventDefault();submit.disabled=true;message('');try{await onSubmit(input.value);}catch(error){message(error.message);submit.disabled=false;}});
    return box;
  }
  async function renderSecurity() {
    const box=$('#account-security');box.replaceChildren();
    if(user.authenticator) {
      const state=element('p','account-security-state','Authenticator is on');
      box.append(state,element('p','account-view-intro','If you forget your password, choose Forgot password? on the sign-in page and enter the code from your app.'));
      if(unlinking) {
        box.append(passwordForm('Enter your password to remove the authenticator',user.role==='Manager'?'Without it, nobody can reset your password if you forget it.':'Without it, you can only reset a forgotten password through your Manager.','Remove',true,
          async password=>{user=(await request({action:'authenticator-remove',password})).user;unlinking=false;renderSecurity();message('Authenticator removed.');},()=>{unlinking=false;renderSecurity();}));
      } else {
        const actions=element('div','account-view-actions'),back=element('button','','Back'),remove=element('button','account-remove','Remove authenticator');
        back.type=remove.type='button';back.addEventListener('click',()=>openView('home'));remove.addEventListener('click',()=>{unlinking=true;message('');renderSecurity();});
        actions.append(back,remove);box.append(actions);
      }
      box.querySelector('input,button')?.focus();return;
    }
    if(setupKey) {
      const steps=element('ol','account-security-steps');
      steps.append(element('li','','Open your authenticator app (Google or Microsoft Authenticator) and add an account.'),element('li','','Scan this QR code, or enter the setup key.'));
      const qr=element('div','account-qr'),image=element('img');image.width=image.height=184;image.alt='QR code for adding GiroWatch to your authenticator app';
      image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(await window.QRCode.toString(setupKey.uri,{type:'svg',margin:1,color:{dark:'#1d2830',light:'#ffffff'}}));
      const key=element('code','',setupKey.secret.match(/.{1,4}/g).join(' '));key.setAttribute('aria-label','Setup key');qr.append(image,key);
      const confirm=element('form','account-inline'),label=element('label','','Enter the 6-digit code shown for GiroWatch'),input=element('input');
      Object.assign(input,{name:'code',inputMode:'numeric',autocomplete:'one-time-code',pattern:'[0-9 ]{6,7}',maxLength:7,required:true});label.append(input);
      const actions=element('div','account-view-actions'),cancel=element('button','','Cancel'),turnOn=element('button','account-primary','Turn on');
      cancel.type='button';turnOn.type='submit';cancel.addEventListener('click',()=>{setupKey=null;renderSecurity();});actions.append(cancel,turnOn);confirm.append(label,actions);
      confirm.addEventListener('submit',async event=>{
        event.preventDefault();turnOn.disabled=true;message('');
        try{user=(await request({action:'authenticator-confirm',code:input.value})).user;setupKey=null;renderSecurity();message('Authenticator is on. You can now reset your password from the sign-in page.');}
        catch(error){message(error.message);turnOn.disabled=false;}
      });
      box.append(steps,qr,confirm);input.focus();return;
    }
    box.append(element('p','account-view-intro','Add GiroWatch to an authenticator app, like the one you use for ScreenConnect. If you forget your password, you can reset it with a code from the app.'),
      passwordForm('Current password','','Set up authenticator',false,async password=>{setupKey=await request({action:'authenticator-begin',password});renderSecurity();}));
    box.querySelector('input')?.focus();
  }
  dialog.addEventListener('close',()=>{setupKey=null;unlinking=false;resetting='';removing='';});
  check();
})();
