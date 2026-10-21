"""External Windows controls for the local simulator only."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import sys
import threading
import time
import json
import re

ROOT = Path(__file__).resolve().parent
control_lock = threading.Lock()
live_lock=threading.Lock()
live_cache={}


def parse_live_display(text):
    if 'INTERFACE RUNNING!' in text.upper():
        return {'state':'running'}
    match=re.search(r'waiting\s+(\d{2}):(\d{2}):(\d{2})',text,re.I)
    if match:
        hours,minutes,seconds=map(int,match.groups())
        if minutes<60 and seconds<60:
            return {'state':'waiting','seconds':hours*3600+minutes*60+seconds}
    return {'state':'unavailable'}


def live_status(profile):
    key=json.dumps(profile,sort_keys=True)
    with live_lock:
        cached=live_cache.setdefault(key,{'checked':0,'busy':False,'value':{'running':None,'state':'unavailable'}})
        if not cached['busy'] and time.monotonic()-cached['checked']>=2:
            cached['busy']=True
            def refresh():
                try:
                    response=cam_command('status',profile)
                    value={'running':response.get('running'),**parse_live_display(response.get('display',''))}
                    value['sampled_at']=time.time()
                except Exception:
                    value={'running':None,'state':'unavailable'}
                with live_lock:
                    cached.update(value=value,checked=time.monotonic(),busy=False)
            threading.Thread(target=refresh,daemon=True).start()
        return dict(cached['value'])


def cam_command(action, profile=None):
    if action not in ('run','restart','status'):
        raise ValueError('Unknown Cam command.')
    # Inline commands do not require changing the machine's script-file policy.
    adapter=str(ROOT/'cam_accessibility.cs').replace("'","''")
    command='& {\n'+(ROOT/'cam_control.ps1').read_text(encoding='utf-8')+'\n} -Action '+action+" -AdapterPath '"+adapter+"'"
    if profile is None:
        profiles=json.loads((ROOT/'application_controls.json').read_text(encoding='utf-8'))
        profile=profiles.get('Cam')
    from control_profiles import validate_control_profile
    profile=validate_control_profile(profile or {})
    for field,parameter in {'executable':'Executable','working_folder':'WorkingFolder','process_name':'ProcessName','window_title':'WindowTitle','menu_name':'MenuName','run_name':'RunName'}.items():
        command+=" -"+parameter+" '"+profile[field].replace("'","''")+"'"
    command+=' -CloseTimeout '+str(profile['close_timeout'])
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                          capture_output=True,text=True,timeout=30,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        response=json.loads(result.stdout.strip())
    except (ValueError,TypeError):
        raise ValueError('Cam control could not complete. Check the app before retrying.')
    if result.returncode or response.get('error'):
        raise ValueError(response.get('error','Cam control failed.'))
    return response


def windows_api():
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetMenu.argtypes = [w.HWND]; api.GetMenu.restype = w.HMENU
    api.GetSubMenu.argtypes = [w.HMENU, ctypes.c_int]; api.GetSubMenu.restype = w.HMENU
    api.GetMenuItemID.argtypes = [w.HMENU, ctypes.c_int]; api.GetMenuItemID.restype = w.UINT
    api.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    return api


def test_window():
    api = windows_api()
    found = []
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    @callback_type
    def visit(hwnd, _):
        title = ctypes.create_unicode_buffer(256)
        api.GetWindowTextW(hwnd, title, len(title))
        if title.value == 'GiroWatch TEST Interface':
            found.append(hwnd)
        return True
    api.EnumWindows(visit, 0)
    if len(found) > 1:
        raise ValueError('Multiple Test Interface windows are open. Close extras first.')
    return found[0] if found else None


def send_command(action):
    hwnd = test_window()
    if not hwnd:
        raise ValueError('Test Interface is closed. Use Restart to open it.')
    api = windows_api()
    if action == 'run':
        menu = api.GetSubMenu(api.GetMenu(hwnd), 0)
        command = api.GetMenuItemID(menu, 0)
        if not menu or command == 0xffffffff:
            raise ValueError('Could not find the Test Interface Run menu.')
        if not api.PostMessageW(hwnd, 0x0111, command, 0):
            raise ValueError('Windows could not activate Run.')
    elif action == 'close':
        if not api.PostMessageW(hwnd, 0x0010, 0, 0):
            raise ValueError('Windows could not close the Test Interface.')
    return {'ok': True}


def application_action(payload):
    name=payload.get('application')
    profiles=json.loads((ROOT/'application_controls.json').read_text(encoding='utf-8')) if (ROOT/'application_controls.json').exists() else {}
    profile=next((value for key,value in profiles.items() if key==name),None)
    if name!='Test Interface' and profile is None:
        raise ValueError('Save an Application controls profile for this application first.')
    action = payload.get('action')
    if action not in ('run', 'restart'):
        raise ValueError('Choose Run or Restart.')
    with control_lock:
        if name!='Test Interface':
            try:
                return cam_command(action) if name=='Cam' else cam_command(action,profile)
            except subprocess.TimeoutExpired:
                raise ValueError('Cam control timed out. Check the app before retrying.')
        if action == 'run':
            return send_command('run')
        if test_window():
            send_command('close')
            deadline = time.monotonic() + 8
            while test_window():
                if time.monotonic() >= deadline:
                    raise ValueError('Test Interface did not close. No second copy was started.')
                time.sleep(.1)
        executable = Path(sys.executable).with_name('pythonw.exe')
        subprocess.Popen([str(executable), str(ROOT / 'test_interface.py')], cwd=ROOT)
        deadline = time.monotonic() + 8
        while not test_window():
            if time.monotonic() >= deadline:
                raise ValueError('Test Interface did not open in this Windows session.')
            time.sleep(.1)
        return {'ok': True}
