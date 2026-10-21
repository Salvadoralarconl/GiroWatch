"""Saved application log locations and read-only discovery of their log files."""
import os
import re
from datetime import datetime
from pathlib import Path


def validate_folder_profile(payload):
    application = str(payload.get('application', '')).strip()
    path = str(payload.get('path', '')).strip()
    recursive = payload.get('recursive', True)
    if not application or not path or not Path(path).is_absolute():
        raise ValueError('Enter an application name and an absolute folder path.')
    if not isinstance(recursive, bool):
        raise ValueError('Include subfolders must be true or false.')
    return application, {'path': path, 'recursive': recursive, 'extension': '.log'}


def discover_logs(profile):
    """Visit child folders without following links; never change source logs."""
    root = Path(profile['path'])
    if not root.is_dir():
        raise ValueError('Folder is unavailable. Check the path and your drive connection.')
    files = []
    def failed(error):
        raise OSError(f'Could not read folder: {error.filename}') from error
    for directory, children, names in os.walk(root, followlinks=False, onerror=failed):
        children[:] = [name for name in children if not Path(directory, name).is_symlink()
                       and not os.path.isjunction(Path(directory, name))]
        for name in names:
            candidate = Path(directory, name)
            if candidate.suffix.lower() == '.log' and not candidate.is_symlink():
                files.append(str(candidate.relative_to(root)))
        if not profile['recursive']:
            break
    return sorted(files, key=str.casefold)


def latest_log(profile):
    """Choose one real YYYYMMDD.log across all weekday folders, excluding copies."""
    candidates = []
    root = Path(profile['path'])
    for name in discover_logs(profile):
        filename = Path(name).name
        if not re.fullmatch(r'\d{8}\.log', filename, flags=re.I):
            continue
        try:
            date = datetime.strptime(filename[:8], '%Y%m%d').date()
        except ValueError:
            continue
        candidates.append((date, (root / name).stat().st_mtime_ns, name))
    if not candidates:
        raise ValueError('No dated logs found. Expected YYYYMMDD.log inside the configured folder or its subfolders.')
    return max(candidates)[2]
