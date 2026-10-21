"""On-demand historical log grouping; cached files never require another read."""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import threading
import girowatch_core as core
from folder_profiles import discover_logs


def current_week():
    return datetime.now().astimezone().date().isocalendar()[:2]


def date_range(start, end):
    try:
        first = date.fromisoformat(start) if start else date.min
        last = date.fromisoformat(end) if end else date.max
    except ValueError as error:
        raise ValueError('Choose valid From and To dates.') from error
    if first > last:
        raise ValueError('From must be on or before To.')
    return first, last


def source_date(filename):
    match = re.search(r'(\d{8})\.log$', filename, re.I)
    if match:
        try:
            return datetime.strptime(match[1], '%Y%m%d').date()
        except ValueError:
            pass
    return None


class HistoricalSearch:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()

    def snapshots(self, application, first, last):
        from web_service import read_json, write_json, find_profile
        store = self.store
        warnings, snapshots, covered = [], [], set()
        # Historical work has its own lock, so monitoring/configuration stay responsive.
        with self.lock:
            cache_root = store.root / 'web_data' / 'search_weeks'
            weeks, dirty = {}, set()
            current_year, current_number = current_week()
            current_suffix = f'_{current_year}-W{current_number:02d}.json'
            # These are disposable derived groupings, never source logs/profiles.
            for old in cache_root.glob('*.json'):
                if not old.name.endswith(current_suffix):
                    old.unlink()
            with store.lock:
                folders = read_json(store.root / 'folder_profiles.json', {})
                run_profiles, order_profiles, error_profiles = store.profiles()
            for name, folder in folders.items():
                if application and name.casefold() != application.casefold():
                    continue
                run = find_profile(run_profiles, name)
                order = find_profile(order_profiles, name)
                rules = (find_profile(error_profiles, name) or {}).get('rules', [])
                if not run or not order:
                    warnings.append(f'{name}: save run and order profiles before searching logs.')
                    continue
                profile_key = hashlib.sha256(json.dumps([run, order, rules], sort_keys=True).encode()).hexdigest()
                try:
                    files = discover_logs(folder)
                except (OSError, ValueError) as error:
                    warnings.append(f'{name}: {error}')
                    continue
                # Prefer recent files rather than working through the oldest first.
                files.sort(key=lambda filename: source_date(filename) or date.min, reverse=True)
                for relative in files:
                    if not re.fullmatch(r'\d{8}\.log', Path(relative).name, re.I):
                        continue
                    day = source_date(relative)
                    if day is None or not first <= day <= last:
                        continue
                    path = Path(folder['path']) / relative
                    key = name.casefold() + ':' + str(path)
                    year, week, _ = day.isocalendar()
                    app_key = hashlib.sha256(name.casefold().encode()).hexdigest()[:16]
                    cache_path = cache_root / f'{app_key}_{year}-W{week:02d}.json'
                    keep = (year, week) == (current_year, current_number)
                    if keep and cache_path not in weeks:
                        weeks[cache_path] = read_json(cache_path, {})
                    cache = weeks[cache_path] if keep else {}
                    try:
                        stat = path.stat()
                        fingerprint = [stat.st_size, stat.st_mtime_ns, stat.st_ino, profile_key]
                        saved = cache.get(key)
                        if not saved or saved['fingerprint'] != fingerprint:
                            # Close the source handle before running classifiers.
                            text = path.read_text(encoding='utf-8-sig')
                            runs, _ = core.group_runs(text.splitlines(), run)
                            orders, _, _ = store._orders(runs, order, order.get('selected_model'), name)
                            reviewed = core.apply_rules(orders, rules, name)
                            saved = {'fingerprint': fingerprint, 'snapshot': {
                                'application': name, 'filename': relative, 'source_id': day.strftime('%Y%m%d'),
                                'source_runs': runs, 'runs': reviewed, 'errors_assessed': bool(rules)}}
                            cache[key] = saved
                            if keep:
                                dirty.add(cache_path)
                        snapshots.append(saved['snapshot'])
                        covered.add((name.casefold(), day.strftime('%Y%m%d')))
                    except (OSError, UnicodeError, ValueError) as error:
                        warnings.append(f'{name} / {relative}: {error}')
            for cache_path in dirty:
                write_json(cache_path, weeks[cache_path])
        return snapshots, covered, warnings
