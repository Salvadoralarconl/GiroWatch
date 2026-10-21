"""GiroWatch-owned application launch and menu settings."""
import re
from pathlib import PureWindowsPath


def validate_control_profile(profile):
    fields=('executable','working_folder','process_name','window_title','menu_name','run_name')
    result={key:str(profile.get(key,'')).strip() for key in fields}
    if any(not result[key] or len(result[key])>1000 for key in fields):
        raise ValueError('Complete every application control field.')
    if not PureWindowsPath(result['executable']).is_absolute() or not result['executable'].lower().endswith('.exe'):
        raise ValueError('Enter an absolute .exe path.')
    if not PureWindowsPath(result['working_folder']).is_absolute():
        raise ValueError('Enter an absolute working folder.')
    if not re.fullmatch(r'[\w .-]+',result['process_name']):
        raise ValueError('Enter a process name without wildcards or a path.')
    timeout=profile.get('close_timeout',10)
    if type(timeout) is not int or not 1<=timeout<=60:
        raise ValueError('Close timeout must be between 1 and 60 seconds.')
    result['close_timeout']=timeout
    return result
