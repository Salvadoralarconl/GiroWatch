"""Local data service for the Sonda-style GiroWatch interface."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import re

import girowatch_core as core
from error_review import validate_rules, validate_runs, review_lines
from run_defaults import DEFAULT_RUN_PROFILES
from folder_profiles import validate_folder_profile, discover_logs, latest_log


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else deepcopy(default)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def default_run_profiles():
    return deepcopy(DEFAULT_RUN_PROFILES)


def find_profile(profiles, application):
    return next((value for key, value in profiles.items() if key.casefold() == application.casefold()), None)


def validate_raw_runs(runs):
    if not isinstance(runs, list):
        raise ValueError('Run JSON must contain a list.')
    for run in runs:
        if (not isinstance(run, dict) or run.get('status') not in ('complete', 'incomplete')
                or not isinstance(run.get('lines'), list) or not all(isinstance(x, str) for x in run['lines'])):
            raise ValueError('Choose grouped-runs JSON or grouped-order JSON from GiroWatch.')


class WatchStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'web_data' / 'state.json'
        self.lock = threading.RLock()
        from monitoring_service import Monitor
        self.monitor = Monitor(self)
        from historical_search import HistoricalSearch
        self.historical_search = HistoricalSearch(self)
        from home_errors import HomeErrors
        self.home_errors = HomeErrors(self)
        from run_stats import RunStats
        self.run_stats = RunStats(self)

    def profiles(self):
        run = default_run_profiles()
        run.update(read_json(self.root / 'girosol_profiles.json', {}))
        order = read_json(self.root / 'order_profiles.json', {})
        errors = read_json(self.root / 'error_profiles.json', {})
        deleted = read_json(self.root / 'web_data' / 'deleted_profiles.json', {})
        for section, profiles in (('run', run), ('order', order), ('errors', errors)):
            for name in list(profiles):
                if f'{section}:{name.casefold()}' in deleted:
                    del profiles[name]
        return run, order, errors

    def application_log(self, application):
        folder = self.profile('folders', application)['profile']
        if not folder:
            raise ValueError('Configure a log folder for this application first.')
        relative = latest_log(folder)
        path = Path(folder['path']) / relative
        with path.open('rb') as stream:
            content = stream.read()
        return {'application': application, 'filename': relative,
                'text': content.decode('utf-8-sig', errors='replace'), 'truncated': False}

    def contacts(self, payload=None):
        path=self.root / 'web_data' / 'contacts.json'
        with self.lock:
            data=read_json(path,{})
            if payload is not None:
                application=payload.get('application','').strip()
                entries=payload.get('contacts')
                if not application or len(application)>120:
                    raise ValueError('Enter an application name (up to 120 characters).')
                fields=('country','code','payer','phone','email','notes')
                if not isinstance(entries,list) or len(entries)>200:
                    raise ValueError('Use up to 200 contacts per application.')
                for entry in entries:
                    if not isinstance(entry,dict) or any(not isinstance(entry.get(field,''),str) or len(entry.get(field,''))>10000 for field in fields):
                        raise ValueError('Contact fields must be text (up to 10,000 characters).')
                key=next((name for name in data if name.casefold()==application.casefold()),application)
                data[key]=[{field:entry.get(field,'') for field in fields} for entry in entries]
                write_json(path,data)
            return {'applications':data}

    def state(self):
        with self.lock:
            state = read_json(self.path, {'datasets': []})
            run, order, errors = self.profiles()
            folders = read_json(self.root / 'folder_profiles.json', {})
            contacts = read_json(self.root / 'web_data' / 'contacts.json', {})
            controls = read_json(self.root / 'application_controls.json', {})
            canonical={}
            for name in list(run)+list(order)+list(errors)+list(folders)+list(contacts)+list(controls):
                canonical.setdefault(name.casefold(),name)
            names = sorted(canonical.values(), key=str.casefold)
            state['applications'] = [
                {'name': name, 'run_profile': bool(find_profile(run, name)),
                 'control_profile': bool(find_profile(controls,name)),
                 'folder_profile': bool(find_profile(folders, name)),
                 'order_profile': bool(find_profile(order, name)),
                 'error_profile': find_profile(errors, name) is not None,
                 'selected_model': (find_profile(order, name) or {}).get('selected_model')}
                for name in names
            ]
            state['models'] = core.MODEL_NAMES
            return state

    def profile(self, section, application):
        """Return one application's actual stored examples without writing files."""
        sections = dict(zip(('run', 'order', 'errors'), self.profiles()))
        sections['folders'] = read_json(self.root / 'folder_profiles.json', {})
        sections['controls'] = read_json(self.root / 'application_controls.json', {})
        if section not in sections:
            raise ValueError('Choose errors, run, or order.')
        profiles = sections[section]
        canonical = next((name for name in profiles if name.casefold() == application.casefold()), application)
        profile = profiles.get(canonical)
        return {'application': canonical, 'section': section, 'exists': profile is not None,
                'profile': deepcopy(profile)}

    def folder_profile(self, payload):
        """Save locations even when a network drive is temporarily disconnected."""
        application, profile = validate_folder_profile(payload)
        action = payload.get('action')
        if action == 'check':
            files = discover_logs(profile)
            return {'count': len(files), 'files': files[:100], 'truncated': len(files) > 100,
                    'latest_file': latest_log(profile)}
        if action != 'save':
            raise ValueError('Choose save or check.')
        with self.lock:
            path = self.root / 'folder_profiles.json'
            profiles = read_json(path, {})
            canonical = next((name for name in profiles if name.casefold() == application.casefold()), application)
            profiles[canonical] = profile
            write_json(path, profiles)
        return {'application': canonical, 'profile': profile, 'saved': True}

    def configure(self, payload):
        """Manage one section without changing the application's other profiles."""
        section, action = payload.get('section'), payload.get('action')
        filenames = {'run': 'girosol_profiles.json', 'order': 'order_profiles.json',
                     'errors': 'error_profiles.json', 'folders': 'folder_profiles.json','controls':'application_controls.json'}
        application = str(payload.get('application', '')).strip()
        if section not in filenames or not application or len(application) > 120:
            raise ValueError('Choose a section and an application name (up to 120 characters).')
        with self.lock:
            # Canonicalize names across sections, including newly created applications.
            application = next((a['name'] for a in self.state()['applications']
                                if a['name'].casefold() == application.casefold()), application)
            path = self.root / filenames[section]
            stored = read_json(path, {})
            trash_path = self.root / 'web_data' / 'deleted_profiles.json'
            trash = read_json(trash_path, {})
            key = f'{section}:{application.casefold()}'
            existing = self.profile(section, application)['profile']
            if action == 'delete':
                if existing is None:
                    raise ValueError('That profile no longer exists.')
                trash[key] = {'application': application, 'section': section, 'profile': existing}
                write_json(trash_path, trash)
                stored = {name: value for name, value in stored.items() if name.casefold() != application.casefold()}
                write_json(path, stored)
                return {'application': application, 'deleted': True}
            if action == 'restore':
                if key not in trash:
                    raise ValueError('No deleted profile to restore.')
                profile = trash[key]['profile']
                application = trash[key]['application']
            elif action == 'copy':
                if existing is None:
                    raise ValueError('Select a saved profile to copy.')
                application = str(payload.get('target', '')).strip()
                if not application or len(application) > 120:
                    raise ValueError('Enter a name for the copied application profile.')
                application = next((a['name'] for a in self.state()['applications']
                                    if a['name'].casefold() == application.casefold()), application)
                if self.profile(section, application)['exists']:
                    raise ValueError('That application already has a profile in this section.')
                key = f'{section}:{application.casefold()}'
                profile = existing
            elif action == 'save':
                if payload.get('create') and existing is not None:
                    raise ValueError('This profile already exists. Select it to edit.')
                profile = payload.get('profile')
            else:
                raise ValueError('Choose save, copy, delete, or restore.')
            if not isinstance(profile, dict):
                raise ValueError('A profile must be an object.')
            if section in ('run', 'order'):
                core.prepare_examples(profile, section)
                if section == 'order' and profile.get('selected_model') not in core.MODEL_NAMES:
                    raise ValueError('Select an order grouping model.')
                # Verify vocabulary is usable before replacing a working profile.
                if section == 'run':
                    core.group_runs([], profile)
                else:
                    core.group_orders([], profile, profile['selected_model'], application)
            elif section == 'errors':
                validate_rules(profile.get('rules'))
            elif section == 'controls':
                from control_profiles import validate_control_profile
                profile=validate_control_profile(profile)
            else:
                _, profile = validate_folder_profile({'application': application, **profile})
            stored = {name: value for name, value in stored.items() if name.casefold() != application.casefold()}
            stored[application] = deepcopy(profile)
            write_json(path, stored)
            if key in trash:
                del trash[key]
                write_json(trash_path, trash)
            return {'application': application, 'profile': profile, 'saved': True}

    def test_configuration(self, payload):
        """Use saved profiles for isolated tests; never replace live monitoring state."""
        from configuration_test import test_application
        with self.lock:
            return test_application(self, payload)

    def index_results(self, application, filename, source_runs, runs, errors_assessed):
        """Keep a searchable snapshot per application/day; rescans replace it."""
        with self.lock:
            path = self.root / 'web_data' / 'search_index.json'
            snapshots = read_json(path, [])
            date = re.search(r'(\d{8})\.log$', filename, re.I)
            source_id = date.group(1) if date else filename.casefold()
            snapshots = [item for item in snapshots if
                         (item['application'].casefold(), item['source_id']) != (application.casefold(), source_id)]
            snapshots.append({'application': application, 'filename': filename, 'source_id': source_id,
                              'source_runs': source_runs, 'runs': runs, 'errors_assessed': errors_assessed})
            write_json(path, snapshots)

    def search(self, query, application='', offset=0, start='', end=''):
        from order_search import search_snapshots
        from historical_search import date_range, source_date
        if not start and not end:
            start=end=datetime.now().astimezone().date().isoformat()
        first, last = date_range(start, end)
        with self.lock:
            snapshots = read_json(self.root / 'web_data' / 'search_index.json', [])
            applications = [item['name'] for item in self.state()['applications']]
        warnings = []
        if str(query).strip():
            historical, covered, warnings = self.historical_search.snapshots(application, first, last)
            snapshots = [item for item in snapshots if (item['application'].casefold(), item['source_id']) not in covered]
            snapshots.extend(historical)
        if start or end:
            snapshots = [item for item in snapshots if (day := source_date(item['filename'])) is not None and first <= day <= last]
        result = search_snapshots(snapshots, query, application, offset)
        result['applications'] = sorted(set(applications) | set(result['applications']), key=str.casefold)
        result['warnings'] = warnings
        return result

    def scan(self, payload):
        with self.lock:
            application = payload.get('application', '').strip()
            filename = Path(payload.get('filename', '')).name
            text = payload.get('text')
            if not application or not filename or not isinstance(text, str) or not text.strip():
                raise ValueError('Choose an application and a nonempty log or JSON file.')
            run_profiles, order_profiles, error_profiles = self.profiles()
            return self._process(application, filename, text,
                                 find_profile(run_profiles, application),
                                 find_profile(order_profiles, application),
                                 (find_profile(error_profiles, application) or {}).get('rules', []),
                                 payload.get('model'))

    def _process(self, application, filename, text, run_profile, order_profile, rules, model_key=None, demo=False):
        pending, notes = False, []
        original_runs = []
        orders_assessed = True
        if rules:
            validate_rules(rules)
        if filename.lower().endswith('.json'):
            try:
                imported = json.loads(text.lstrip('\ufeff'))
            except json.JSONDecodeError as error:
                raise ValueError('This file is not valid JSON. Choose a .log for raw logs.') from error
            # Also accept the separate error-review cell's export wrapper.
            if isinstance(imported, dict):
                if 'datasets' in imported:
                    candidates = imported['datasets']
                    if not isinstance(candidates, list):
                        raise ValueError('The export has invalid datasets.')
                    imported = next((d for d in candidates if isinstance(d, dict) and
                                     str(d.get('application', '')).casefold() == application.casefold()), None)
                    if imported is None:
                        raise ValueError('The export does not contain the selected application.')
                named = imported.get('application')
                if named and named.casefold() != application.casefold():
                    raise ValueError('The file application does not match the selected application.')
                original_runs = imported.get('source_runs', [])
                validate_raw_runs(original_runs)
                pending = bool(imported.get('pending_run', False))
                demo = bool(imported.get('demo', demo))
                imported = imported.get('runs')
            if not isinstance(imported, list):
                raise ValueError('The JSON must contain grouped runs or grouped orders.')
            for item in imported:
                if not isinstance(item, dict):
                    raise ValueError('Each run must be an object.')
                if item.get('application') and item['application'].casefold() != application.casefold():
                    raise ValueError('The file application does not match the selected application.')
            if imported and 'orders' in imported[0]:
                validate_runs(imported)
                orders = deepcopy(imported)
                # Imported order exports lack the original interleaving of
                # unassigned lines. Do not manufacture a chronological full run.
                for number, run in enumerate(orders, 1):
                    if run.get('run_status') not in ('complete', 'incomplete'):
                        raise ValueError('An imported run has an invalid grouping status.')
                    run['run_number'] = number
                    run['application'] = application
                model_key = orders[0].get('model', 'imported')
                notes.append('Imported existing order groups; their boundaries were preserved.')
            else:
                validate_raw_runs(imported)
                original_runs = imported
                orders, orders_assessed, model_key = self._orders(imported, order_profile, model_key, application)
        elif filename.lower().endswith(('.log', '.txt')):
            if not run_profile:
                raise ValueError(f'No saved run profile for {application}. Create it with run_groups.py, or import its grouped-runs JSON.')
            original_runs, pending = core.group_runs(text.splitlines(), run_profile)
            orders, orders_assessed, model_key = self._orders(original_runs, order_profile, model_key, application)
        else:
            raise ValueError('Choose a .log, .txt, or GiroWatch .json file.')
        if not orders_assessed:
            notes.append('No saved order profile: run lines are available, but order grouping was not assessed.')
        if not rules:
            notes.append('No saved error rules: error detection was not assessed.')
        if pending:
            notes.append('The final run is pending and excluded from the saved groups. Scan a newer log snapshot when it finishes.')
        reviewed = core.apply_rules(orders, rules, application)
        alerts = []
        for run in reviewed:
            contexts = [(f"r{run['run_number']}-g{i}", i, group) for i, group in enumerate(run['orders'], 1)]
            contexts.append((f"r{run['run_number']}-unassigned", None, run['unassigned_review']))
            for identifier, group_number, context in contexts:
                if not context['has_alert']:
                    continue
                active = [f for f in context['findings'] if f['alert']]
                alerts.append({'id': identifier, 'run_number': run['run_number'], 'group_number': group_number,
                               'severity': context['highest_severity'], 'message': active[0]['message'],
                               'line': context['lines'][active[0]['line_number'] - 1], 'status': 'Active'})
        dataset = {'application': application, 'filename': filename,
                   'imported_at': datetime.now(timezone.utc).isoformat(), 'demo': demo,
                   'pending_run': pending, 'model': model_key, 'orders_assessed': orders_assessed,
                   'errors_assessed': bool(rules), 'notes': notes, 'runs': reviewed,
                   'source_runs': original_runs, 'alerts': alerts,
                   'line_count': len(text.splitlines()) if filename.lower().endswith(('.log', '.txt')) else
                                 sum(len(r['lines']) for r in original_runs) if original_runs else
                                 sum(len(g['lines']) for r in reviewed for g in r['orders']) +
                                 sum(len(r['unassigned_lines']) for r in reviewed)}
        state = read_json(self.path, {'datasets': []})
        # One latest snapshot per application; rescanning never accumulates duplicates.
        state['datasets'] = [d for d in state['datasets'] if d['application'].casefold() != application.casefold()] + [dataset]
        write_json(self.path, state)
        # Export is self-contained and separate from the original files.
        safe = ''.join(c if c.isalnum() or c in '_-' else '_' for c in application)
        write_json(self.root / 'web_data' / 'exports' / f'{safe}_review.json', dataset)
        if not demo:
            self.index_results(application, filename, original_runs, reviewed, bool(rules))
        return dataset

    @staticmethod
    def _orders(runs, profile, model_key, application):
        if profile:
            model_key = model_key or profile.get('selected_model') or 'naive_bayes'
            return core.group_orders(runs, profile, model_key, application), True, model_key
        return [{'application': application, 'model': None, 'run_number': i, 'run_status': r['status'],
                 'orders': [], 'unassigned_lines': list(r['lines'])} for i, r in enumerate(runs, 1)], False, None

    def demo(self):
        from demo_data import demo_fixture
        fixture = demo_fixture()
        with self.lock:
            return self._process('INTERBANK Demo', 'synthetic_girosol.log', fixture['text'],
                                 fixture['run_profile'], fixture['order_profile'], fixture['rules'],
                                 'nearest_example', demo=True)

    def set_alert(self, payload):
        if payload.get('status') not in ('Active', 'Investigating', 'Resolved'):
            raise ValueError('Choose Active, Investigating, or Resolved.')
        with self.lock:
            state = read_json(self.path, {'datasets': []})
            for dataset in state['datasets']:
                if dataset['application'] == payload.get('application'):
                    for alert in dataset['alerts']:
                        if alert['id'] == payload.get('id'):
                            alert['status'] = payload['status']
                            write_json(self.path, state)
                            return alert
            raise ValueError('That alert was not found. Refresh the page.')
