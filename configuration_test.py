"""Run saved application profiles and prepare exactly three JSON downloads."""
from pathlib import Path
import girowatch_core as core
from folder_profiles import latest_log

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 100


def test_application(store, payload):
    application = str(payload.get('application', '')).strip()
    profiles = {section: store.profile(section, application)['profile']
                for section in ('run', 'order', 'errors', 'folders')}
    if not profiles['run']:
        raise ValueError('Save a run profile for this application before testing.')
    files = []
    if payload.get('source') == 'folder':
        if not profiles['folders']:
            raise ValueError('Save a folder profile or choose uploaded logs.')
        root = Path(profiles['folders']['path'])
        names = [latest_log(profiles['folders'])]
        total = 0
        for name in names:
            path = root / name
            total += path.stat().st_size
            if total > MAX_BYTES:
                raise ValueError('Test logs exceed 20 MB. Upload a smaller selection.')
            try:
                text = path.read_text(encoding='utf-8-sig')
            except UnicodeError as error:
                raise ValueError(f'{name} is not UTF-8 text. Save a UTF-8 copy before testing.') from error
            files.append({'filename': Path(name).as_posix(), 'text': text})
    elif payload.get('source') == 'upload':
        files = payload.get('files')
    else:
        raise ValueError('Choose uploaded logs or the saved folder.')
    if not isinstance(files, list) or not 0 < len(files) <= MAX_FILES:
        raise ValueError('Choose between 1 and 100 nonempty log files.')
    total = 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            raise ValueError('Each uploaded log needs text and a filename.')
        if not isinstance(item.get('filename'), str) or Path(item['filename']).suffix.lower() not in ('.log', '.txt'):
            raise ValueError('Choose raw .log or .txt files for this test.')
        if not item['text'].strip():
            raise ValueError(f"{item['filename']} is empty.")
        total += len(item['text'].encode('utf-8'))
        if total > MAX_BYTES:
            raise ValueError('Test logs exceed 20 MB. Choose a smaller selection.')
    run_results, order_results, sources = [], [], []
    model = payload.get('model') or (profiles['order'] or {}).get('selected_model')
    if profiles['order'] and model not in core.MODEL_NAMES:
        raise ValueError('Save an order model selection before testing.')
    pending_files = 0
    rules = (profiles['errors'] or {}).get('rules', [])
    for item in files:
        # Reset grouping for each source file; never merge orders across files/runs.
        runs, pending = core.group_runs(item['text'].splitlines(), profiles['run'])
        orders, assessed, _ = store._orders(runs, profiles['order'], model, application)
        reviewed = core.apply_rules(orders, rules, application)
        offset = len(order_results)
        for index, run in enumerate(reviewed, offset + 1):
            run['run_number'] = index
            if len(files) > 1:
                run['source_file'] = item['filename']
        if len(files) > 1:
            for run in runs:
                run['source_file'] = item['filename']
        store.index_results(application, item['filename'], runs, reviewed, bool(rules))
        run_results.extend(runs)
        order_results.extend(reviewed)
        pending_files += int(pending)
        sources.append({'filename': item['filename'], 'runs': len(runs), 'pending_run': pending})
    safe = ''.join(c if c.isalnum() or c in '_-' else '_' for c in application) or 'application'
    export_names = {'run':'run_profiles', 'order':'order_profiles', 'errors':'error_profiles', 'folders':'folder_profiles'}
    exported = {export_names[name]: {application: profile} if profile is not None else {}
                for name, profile in profiles.items()}
    exported['test'] = {'application': application, 'model': model, 'sources': sources,
                        'orders_assessed': bool(profiles['order']), 'errors_assessed': bool(rules)}
    return {'downloads': [
        {'kind': 'runs', 'filename': f'{safe}_runs.json', 'data': run_results},
        {'kind': 'orders', 'filename': f'{safe}_orders.json', 'data': order_results},
        {'kind': 'profiles', 'filename': f'{safe}_profiles.json', 'data': exported}],
        'summary': {'files': len(files), 'runs': len(run_results),
                    'orders': sum(len(run['orders']) for run in order_results),
                    'alert_groups': sum(group['has_alert'] for run in order_results for group in run['orders']),
                    'pending_files': pending_files, 'model': model, 'sources': sources,
                    'orders_assessed': bool(profiles['order']), 'errors_assessed': bool(rules)}}
