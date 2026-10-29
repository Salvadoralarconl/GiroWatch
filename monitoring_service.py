"""Change-driven, incremental monitoring of each application's latest dated log.

Only complete lines appended since the saved byte offset are classified. On
first use/rotation we read backward in chunks to recover the latest run context.
No source logs, grouping exports, or Search assessments are modified here.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import json
from pathlib import Path
import threading
import time
import re

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import girowatch_core as core
from error_review import review_lines, validate_rules
from folder_profiles import latest_log

CHUNK = 64 * 1024
PRIORITY = {'None': 0, 'Warning': 1, 'Critical': 2}


def record_run_timing(row, line, label):
    match=re.match(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} [AP]M',line)
    if not match or label not in ('Run_Start','Run_End'):
        return
    stamp=datetime.strptime(match.group(),'%m/%d/%Y %I:%M:%S %p')
    if label=='Run_Start':
        row['last_started_at']=stamp.isoformat()
    else:
        row['last_completed_at']=stamp.isoformat()


def now():
    return datetime.now(timezone.utc).isoformat()


def classifier_for(profile):
    messages, labels = core.prepare_examples(profile, 'run')
    messages.append('System.IO.IOException: The process cannot access the file because it is being used by another process.')
    labels.append('Other')
    vectorizer = CountVectorizer()
    model = MultinomialNB(alpha=0.1).fit(vectorizer.fit_transform(messages), labels)
    return vectorizer, model


def classify_lines(lines, classifier):
    vectorizer, model = classifier
    messages = [core.clean_message(line) for line in lines]
    nonempty = [message for message in messages if message]
    predictions = iter(model.predict(vectorizer.transform(nonempty))) if nonempty else iter(())
    return [next(predictions) if message else 'Other' for message in messages]


def complete_lines(data):
    """Hold the final unterminated line, including any split UTF-8 sequence."""
    end = data.rfind(b'\n') + 1
    return data[:end].decode('utf-8-sig').splitlines(), data[end:]


def initial_tail(path, size, classifier):
    start, data, labels, lines = size, b'', [], []
    while start > 0:
        count = min(CHUNK, start)
        start -= count
        with path.open('rb') as file:
            file.seek(start)
            chunk=file.read(count)
        data = chunk + data
        # The first chunk can begin inside a long line or a UTF-8 codepoint.
        aligned = data if start == 0 else data[data.find(b'\n') + 1:] if b'\n' in data else b''
        lines, buffer = complete_lines(aligned)
        labels = classify_lines(lines, classifier)
        inside = found_complete = False
        for label in labels:
            if label == 'Run_Start':
                inside = True
            elif label == 'Run_End' and inside:
                found_complete, inside = True, False
        if found_complete or start == 0:
            return lines, labels, buffer, size - start
    return [], [], b'', 0


def read_updates(path, previous, classifier, fingerprint):
    stat = path.stat()
    identity = [stat.st_dev, stat.st_ino]
    same = (previous.get('file') == str(path) and previous.get('identity') == identity
            and previous.get('fingerprint') == fingerprint and stat.st_size >= previous.get('offset', 0))
    # Same-size modification means replacement/rewrite, rather than append.
    if same and stat.st_size == previous['offset'] and stat.st_mtime_ns != previous.get('mtime'):
        same = False
    cursor = deepcopy(previous) if same else {'running': False, 'severity': 'None', 'started': ''}
    if same and stat.st_size == previous['offset']:
        return cursor, [], [], 0
    with path.open('rb') as file:
        # A writer can replace content with a longer file. Verify the old EOF
        # still exists before assuming growth is an append (only up to 256 B).
        if same:
            file.seek(max(0, previous['offset'] - 256))
            anchor = file.read(min(256, previous['offset']))
            if hashlib.sha256(anchor).hexdigest() != previous.get('anchor'):
                same = False
                cursor = {'running': False, 'severity': 'None', 'started': ''}
        if same:
            file.seek(previous['offset'])
            appended = file.read(stat.st_size - previous['offset'])
        file.seek(max(0, stat.st_size - 256))
        anchor = hashlib.sha256(file.read(min(256, stat.st_size))).hexdigest()
    # Never hold a source-log handle while decoding or running the ML model.
    if same:
        data = base64.b64decode(previous.get('buffer', '')) + appended
        lines, buffer = complete_lines(data)
        labels = classify_lines(lines, classifier)
        bytes_read = len(appended)
    else:
        lines, labels, buffer, bytes_read = initial_tail(path, stat.st_size, classifier)
    cursor.update(file=str(path), identity=identity, fingerprint=fingerprint,
                  offset=stat.st_size, mtime=stat.st_mtime_ns,
                  anchor=anchor,
                  buffer=base64.b64encode(buffer).decode('ascii'))
    return cursor, lines, labels, bytes_read


class Monitor:
    def __init__(self, store, interval=60):
        self.store, self.interval = store, interval
        self.path = store.root / 'web_data' / 'monitoring.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'applications': {}}
        self.models = {}
        self.lock, self.scan_lock = threading.RLock(), threading.Lock()
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.scanning = False
        self.current_application = None
        self.queued = False
        self.queued_applications = None
        self.next_scan_at = None
        self.thread = None
        self.change_driven = False
        self.quiet_seconds = 1
        self.notifications = {'errors':True,'warnings':True,'resolved':False,'sound':False}
        self.metadata_poll_seconds = 2
        self.watch_state = {}
        self.run_states = {}
        self.pending_scans = set()
        self.settings_managed = False

    def restore_settings(self):
        from web_service import read_json
        # Automatic scanning is on unless the user has saved Pause.
        saved = read_json(self.store.root / 'web_data' / 'monitoring_settings.json', {'automatic_enabled': True})
        self.settings_managed = True
        self.interval = None
        self.change_driven = saved.get('automatic_enabled', True) is True
        self.quiet_seconds = saved.get('quiet_seconds',1) if saved.get('quiet_seconds',1) in (1,10,20,30) else 1
        self.notifications.update({key:value for key,value in saved.get('notifications',{}).items() if key in self.notifications and isinstance(value,bool)})

    def configure_scanning(self, payload):
        from web_service import write_json
        action = payload.get('action')
        if action not in ('pause', 'resume', 'preferences'):
            raise ValueError('Choose pause, resume, or preferences.')
        quiet=payload.get('quiet_seconds',self.quiet_seconds)
        notifications=payload.get('notifications',self.notifications)
        if type(quiet) is not int or quiet not in (1,10,20,30):
            raise ValueError('Choose a quiet period of 1, 10, 20, or 30 seconds.')
        if not isinstance(notifications,dict) or any(key not in self.notifications or not isinstance(value,bool) for key,value in notifications.items()):
            raise ValueError('Notification preferences must be true or false.')
        with self.lock:
            self.settings_managed = True
            self.interval = None
            if action != 'preferences':
                self.change_driven = action == 'resume'
                self.watch_state.clear()
                self.run_states.clear()
                self.next_scan_at = None
            self.quiet_seconds=quiet
            self.notifications.update(notifications)
            write_json(self.store.root / 'web_data' / 'monitoring_settings.json', {'automatic_enabled': self.change_driven,'quiet_seconds':self.quiet_seconds,'notifications':self.notifications})
        self.wake.set()
        return self.status()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, name='girowatch-monitor', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake.set()

    def _loop(self):
        if self.change_driven or self.settings_managed:
            return self._change_loop()
        while not self.stop_event.is_set():
            if self.interval is None:
                self.wake.wait()
                self.wake.clear()
                if self.stop_event.is_set():
                    break
            with self.lock:
                targets = self.queued_applications
                self.queued = False
                self.queued_applications = None
                self.next_scan_at = None
            try:
                self.scan_once(targets)
            except Exception as error:
                with self.lock:
                    self.data['error'] = str(error)
            with self.lock:
                self.next_scan_at = ((datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()
                                     if self.interval is not None else None)
            if self.interval is not None:
                self.wake.wait(self.interval)
                self.wake.clear()

    def _change_loop(self):
        while not self.stop_event.is_set():
            try:
                if self.queued:
                    with self.lock:
                        targets = self.queued_applications
                        self.queued = False
                        self.queued_applications = None
                    self.scan_once(targets)
                if self.change_driven:
                    self.watch_tick()
            except Exception as error:
                with self.lock:
                    self.data['error'] = str(error)
            self.wake.wait(min(self.metadata_poll_seconds,self.quiet_seconds))
            self.wake.clear()

    def scan_after_run(self, name):
        """A manual restart gets one scan after running returns to waiting."""
        if self.change_driven:
            # watch_tick already scans every application when its run ends.
            return
        def finish():
            deadline = time.monotonic() + 1800
            observed_running = False
            while not self.stop_event.is_set() and time.monotonic() < deadline:
                try:
                    state = self.application_run_state(name)
                    if state == 'running':
                        observed_running = True
                    elif state == 'waiting' and observed_running:
                        self.request_scan({'application': name})
                        return
                except Exception as error:
                    with self.lock:
                        self.data['error'] = f'{name}: post-restart scan failed: {error}'
                    return
                self.stop_event.wait(0.25)
            if not self.stop_event.is_set():
                with self.lock:
                    self.data['error'] = f'{name}: run completion was not confirmed; post-restart scan was not performed.'
        threading.Thread(target=finish, name=f'girowatch-restart-{name}', daemon=True).start()

    def application_run_state(self, name):
        if getattr(self.store, 'local_test_mode', False):
            status = self.store.simulators.status(name)
            return status.get('live_timer_state', 'unavailable') if status.get('process_running') is True else 'unavailable'
        profile = self.store.profile('controls', name)['profile']
        if not profile:
            return 'unavailable'
        from application_control import live_status
        status = live_status(profile)
        return status.get('state', 'unavailable') if status.get('running') is True else 'unavailable'

    def application_waiting(self, name):
        return self.application_run_state(name) == 'waiting'

    def run_ended(self, name):
        """True once per run, when an application goes from running back to waiting."""
        try:
            state = self.application_run_state(name)
        except (OSError, ValueError):
            state = 'unavailable'
        with self.lock:
            previous = self.run_states.get(name)
            self.run_states[name] = state
        return previous == 'running' and state == 'waiting'

    def awaiting_post_run_scan(self, name):
        """A scan is due for this app but hasn't started yet; shown as Scanning so the UI never gaps.
        Covers automatic post-run scans and queued manual ones (Scan, or Run/Restart while paused)."""
        if name in self.pending_scans:
            return True
        if self.queued and (self.queued_applications is None or name in self.queued_applications):
            return True
        if not self.change_driven or self.run_states.get(name) != 'running':
            return False
        try:
            return self.application_run_state(name) == 'waiting'
        except (OSError, ValueError):
            return False

    def watch_tick(self):
        """Stat only: each application's own changes restart its quiet timer.
        A finished run is scanned immediately, without waiting for the quiet period."""
        stamp = time.monotonic()
        due, active = set(), set()
        for app in self.store.state()['applications']:
            name = app['name']
            if not app['folder_profile']:
                continue
            active.add(name)
            ended = self.run_ended(name)
            try:
                folder = self.store.profile('folders', name)['profile']
                path = Path(folder['path']) / latest_log(folder)
                stat = path.stat()
                signature = (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
                with self.lock:
                    watched = self.watch_state.get(name)
                    if watched is None:
                        cursor = self.data['applications'].get(name, {}).get('cursor', {})
                        scanned = (cursor.get('file'), *(cursor.get('identity') or [None,None]), cursor.get('offset'), cursor.get('mtime'))
                        watched = {'signature': signature, 'changed': None if scanned[:4] == signature[:4] else stamp, 'ready_since': None}
                        self.watch_state[name] = watched
                    elif watched['signature'][:4] != signature[:4]:
                        watched.update(signature=signature, changed=stamp, ready_since=None)
                    if ended:
                        # This scan covers everything the run wrote, so don't wait for the quiet period too.
                        due.add(name)
                        self.pending_scans.add(name)
                        watched.update(changed=None, ready_since=None)
                    if watched['changed'] is not None:
                        if self.application_waiting(name):
                            if watched.get('ready_since') is None:
                                watched['ready_since'] = stamp
                        else:
                            watched['ready_since'] = None
                    if watched['changed'] is not None and watched.get('ready_since') is not None and stamp-watched['ready_since'] >= self.quiet_seconds:
                        due.add(name)
                        watched['changed'] = None
                        watched['ready_since'] = None
            except (OSError, ValueError):
                # A disconnected source is never opened; retry its metadata later.
                with self.lock:
                    self.watch_state.pop(name, None)
        with self.lock:
            self.watch_state = {name:item for name,item in self.watch_state.items() if name in active}
            self.run_states = {name:state for name,state in self.run_states.items() if name in active}
        if due and (self.change_driven or not self.settings_managed):
            try:
                self.scan_once(due)
            finally:
                with self.lock:
                    self.pending_scans.difference_update(due)
        else:
            with self.lock:
                self.pending_scans.difference_update(due)
        with self.lock:
            current_stamp = time.monotonic()
            remaining = [max(0,self.quiet_seconds-(current_stamp-item['ready_since'])) for item in self.watch_state.values() if item['changed'] is not None and item.get('ready_since') is not None]
            self.next_scan_at = (datetime.now(timezone.utc)+timedelta(seconds=min(remaining))).isoformat() if remaining and (self.change_driven or not self.settings_managed) else None

    def request_scan(self, payload=None):
        name = (payload or {}).get('application')
        targets = None
        if name is not None:
            names = {app['name'] for app in self.store.state()['applications']}
            if name not in names:
                raise ValueError('Unknown application')
            targets = {name}
        with self.lock:
            if not self.queued:
                self.queued_applications = targets
            elif targets is None:
                self.queued_applications = None
            elif self.queued_applications is not None:
                self.queued_applications.update(targets)
            self.queued = True
            self.next_scan_at = None
        self.wake.set()
        return {'scheduled': True}

    def status(self):
        applications = self.store.state()['applications']
        from application_control import test_window
        from application_control import live_status
        live={}
        for app in applications:
            if app['name']=='Cam' and app.get('control_profile'):
                profile=self.store.profile('controls',app['name'])['profile']
                if profile:live[app['name']]=live_status(profile)
        try:
            test_running=bool(test_window()) if any(app['name']=='Test Interface' for app in applications) else None
        except (OSError,ValueError,AttributeError):
            test_running=None
        active_severity={}
        for incident in self.store.home_errors.results()['incidents']:
            if incident['status'] not in ('Active','Investigating'):
                continue
            name=incident['application'].casefold()
            severity=2 if incident['severity']=='Error' else 1
            active_severity[name]=max(active_severity.get(name,0),severity)
        with self.lock:
            rows = []
            for app in applications:
                saved = self.data['applications'].get(app['name'], {})
                row = {key: deepcopy(value) for key, value in saved.items() if key != 'cursor'}
                row.update(name=app['name'])
                row['control_available']=bool(app.get('control_profile')) or app['name']=='Test Interface'
                row['process_running']=test_running if app['name']=='Test Interface' else None
                row['next_run_at']=None
                row['next_run_estimated']=False
                if app['name'] in live:
                    display=live[app['name']]
                    row['process_running']=display.get('running')
                    row['live_timer_state']=display['state']
                    if display['state']=='waiting':
                        row['next_run_at']=datetime.fromtimestamp(display['sampled_at']+display['seconds'],timezone.utc).isoformat()
                if app['name']=='Test Interface' and row.get('last_completed_at'):
                    row['next_run_at']=(datetime.fromisoformat(row['last_completed_at'])+timedelta(seconds=30)).isoformat()
                    row['next_run_estimated']=False
                row['scanning'] = (self.scanning and self.current_application == app['name']) or self.awaiting_post_run_scan(app['name'])
                row.setdefault('color', None)
                row.setdefault('message', 'Waiting for the first scan')
                severity=active_severity.get(app['name'].casefold(),0)
                if severity>{'red':2,'yellow':1}.get(row.get('color'),0):
                    row['color']='red' if severity==2 else 'yellow'
                    row['message']='Unresolved error' if severity==2 else 'Unresolved warning'
                rows.append(row)
            return {'applications': rows, 'interval_seconds': None if self.change_driven else self.interval, 'scanning': self.scanning,
                    'automatic_mode': 'changes' if self.change_driven else 'paused' if self.interval is None else 'interval',
                    'quiet_seconds': self.quiet_seconds,
                    'notifications': deepcopy(self.notifications),
                    'queued': self.queued, 'next_scan_at': self.next_scan_at,
                    'last_scan': self.data.get('last_scan'), 'error': self.data.get('error')}

    def scan_once(self, application_names=None):
        if not self.scan_lock.acquire(blocking=False):
            return
        with self.lock:
            self.scanning = True
        try:
            applications = self.store.state()['applications']
            for app in applications:
                name = app['name']
                if application_names is not None and name not in application_names:
                    continue
                with self.lock:
                    self.current_application = name
                with self.lock:
                    previous = deepcopy(self.data['applications'].get(name, {}))
                row = deepcopy(previous)
                row.update(checked_at=now(), bytes_read=0)
                if row.get('last_color'):
                    row['color'] = row['last_color']
                try:
                    folder = self.store.profile('folders', name)['profile']
                    profile = self.store.profile('run', name)['profile']
                    errors = self.store.profile('errors', name)['profile']
                    if not folder or not profile or not (errors or {}).get('rules'):
                        row.update(color=None, pending=False, message='Setup needed: run profile, log folder and error rules')
                    else:
                        rules = errors['rules']
                        validate_rules(rules)
                        fingerprint = hashlib.sha256(json.dumps([profile, rules, 'timing-v2'], sort_keys=True).encode()).hexdigest()
                        if row.get('cursor',{}).get('fingerprint') != fingerprint:
                            for key in ('last_started_at','last_completed_at','next_run_at','run_interval_seconds','run_interval_samples'):
                                row.pop(key,None)
                        model_key = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
                        if model_key not in self.models:
                            self.models[model_key] = classifier_for(profile)
                        relative = latest_log(folder)
                        path = Path(folder['path']) / relative
                        self.store.home_errors.update(name, path, relative, profile, rules, self.models[model_key])
                        cursor, lines, labels, read = read_updates(path, row.get('cursor', {}), self.models[model_key], fingerprint)
                        for line, label in zip(lines, labels):
                            record_run_timing(row,line,label)
                            if label == 'Run_Start':
                                cursor.update(running=True, severity='None', started=line)
                            elif cursor['running']:
                                severity = review_lines([line], rules)['highest_severity']
                                if PRIORITY[severity] > PRIORITY[cursor['severity']]:
                                    cursor['severity'] = severity
                                if label == 'Run_End':
                                    row.update(color={'None': 'green', 'Warning': 'yellow', 'Critical': 'red'}[cursor['severity']],
                                               assessed_run=cursor['started'], assessed_at=now())
                                    row['last_color'] = row['color']
                                    cursor['running'] = False
                        pending = cursor.get('running', False)
                        pending_severity=cursor.get('severity','None')
                        if pending and pending_severity in ('Warning','Critical'):
                            pending_color={'Warning':'yellow','Critical':'red'}[pending_severity]
                            rank={None:0,'green':0,'yellow':1,'red':2}
                            if rank[pending_color]>rank.get(row.get('color'),0):
                                row.update(color=pending_color,last_color=pending_color,assessed_run=cursor.get('started',''),assessed_at=now())
                        row.update(cursor=cursor, pending=pending, filename=relative, bytes_read=read,
                                   message=('Run in progress · '+{'yellow':'Warning detected','red':'Error detected'}.get(row.get('color'),'previous status retained')) if pending else
                                   {'green': 'No active errors', 'yellow': 'Warning', 'red': 'Error'}.get(row.get('color'), 'Waiting for a completed run'))
                except (OSError, ValueError, TypeError, KeyError) as error:
                    row.update(color=None, pending=False, message=str(error))
                with self.lock:
                    self.data['applications'][name] = row
                    watched = self.watch_state.get(name)
                    cursor = row.get('cursor', {})
                    scanned = (cursor.get('file'), *(cursor.get('identity') or [None,None]), cursor.get('offset'), cursor.get('mtime'))
                    if watched and watched['signature'] == scanned:
                        watched['changed'] = None
                self.store.run_stats.scan_once({name})
            with self.lock:
                active = {app['name'] for app in applications}
                self.data['applications'] = {name: row for name, row in self.data['applications'].items() if name in active}
                self.data['last_scan'] = now()
                self.data.pop('error', None)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(self.path)
        finally:
            with self.lock:
                self.scanning = False
                self.current_application = None
            self.scan_lock.release()
