"""Today's Home incidents, refreshed by manual monitoring scans only."""
from copy import deepcopy
from datetime import datetime
import base64
import hashlib
import json
from pathlib import Path
import re
import threading
from error_review import review_lines

STAMP = re.compile(r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} [AP]M')


def build_incidents(application, filename, lines, labels, findings):
    """Only a later clean completed run resolves outstanding application incidents."""
    rows, outstanding = [], []
    current, outside, run_number, timestamp = None, 0, 0, ''
    for index, (line, label, matched) in enumerate(zip(lines, labels, findings)):
        stamp = STAMP.match(line)
        if stamp:
            timestamp = datetime.strptime(stamp.group(), '%m/%d/%Y %I:%M:%S %p').isoformat()
        if label == 'Run_Start':
            if current:
                for row in current['rows']:
                    row['context'] = lines[current['start']:index]
            else:
                for row in rows:
                    if row.get('_outside') == outside:
                        row['context'] = lines[outside:index]
            run_number += 1
            current = {'start': index, 'rows': [], 'has_error': False}
        active = [item for item in matched if item['alert']]
        if current and active:
            current['has_error'] = True
        for number, finding in enumerate(active):
            row = {'id': hashlib.sha256(f'{application}:{filename}:{index}:{number}'.encode()).hexdigest()[:24],
                   'application': application, 'filename': filename, 'line_number': index+1,
                   'run_number': run_number if current else None, 'time': timestamp,
                   'severity': 'Error' if finding['severity']=='Critical' else 'Warning',
                   'message': finding['message'], 'match': finding.get('match',''),
                   'status': 'Active', 'line': line, 'context': []}
            if current:
                current['rows'].append(row)
            else:
                row['_outside'] = outside
            outstanding.append(row)
            rows.append(row)
        if label == 'Run_End' and current:
            for row in current['rows']:
                row['context'] = lines[current['start']:index+1]
            if not current['has_error']:
                for row in outstanding:
                    row['status'] = 'Resolved'
                    row['resolved_at'] = timestamp
                    row['resolved_by_run'] = run_number
                outstanding.clear()
            current = None
            outside = index+1
    if current:
        for row in current['rows']:
            row['context'] = lines[current['start']:]
    for row in rows:
        if not row['context']:
            row['context'] = lines[row.get('_outside',len(lines)):]
        row.pop('_outside',None)
    return rows


def merge_incidents(rows):
    """Merge the same application's same error within a bounded 60-second window."""
    groups, latest = [], {}
    for row in sorted(rows,key=lambda item:(item['time'],item['line_number'])):
        key=(row['application'].casefold(),row['filename'],row['severity'],
             row.get('match','').casefold(),row['message'])
        stamp=datetime.fromisoformat(row['time']) if row['time'] else None
        group=latest.get(key)
        if not stamp or group is None or not group['first_time'] or (stamp-datetime.fromisoformat(group['first_time'])).total_seconds()>60:
            group=deepcopy(row)
            group.update(first_time=row['time'],occurrences=[],occurrence_count=0)
            groups.append(group);latest[key]=group
        group['occurrences'].append(deepcopy(row))
        group['occurrence_count']+=1
        group['time']=row['time'];group['line_number']=row['line_number']
        group['status']='Active' if any(item['status']=='Active' for item in group['occurrences']) else 'Resolved'
        if group['status']=='Active':
            group.pop('resolved_by_run',None);group.pop('resolved_at',None)
        elif row.get('resolved_at','')>=group.get('resolved_at',''):
            for field in ('resolved_by_run','resolved_at'):
                if field in row:group[field]=row[field]
    for group in groups:
        contexts=[];seen=set()
        for occurrence in group['occurrences']:
            context=tuple(occurrence['context'])
            if context not in seen:
                if contexts:contexts.append('\n--- Additional occurrence context ---\n')
                contexts.extend(context);seen.add(context)
        group['context']=contexts
    return groups


class HomeErrors:
    def __init__(self, store):
        from web_service import read_json
        self.store = store
        self.path = store.root / 'web_data' / 'home_errors.json'
        self.data = read_json(self.path, {})
        self.status_path = store.root / 'web_data' / 'incident_statuses.json'
        self.statuses = read_json(self.status_path, {})
        self.lock = threading.RLock()

    def set_status(self, payload):
        from web_service import write_json
        identifier, status = payload.get('id'), payload.get('status')
        if status not in ('Active', 'Resolved', 'Investigating'):
            raise ValueError('Choose Active, Resolved, or Investigating.')
        with self.lock:
            incident = self.results(identifier)['incident']
            self.statuses[identifier] = {'status':status, 'resolved_by_run':incident.get('resolved_by_run')}
            write_json(self.status_path, self.statuses)
        return self.results(identifier)

    def update(self, application, path, filename, profile, rules, classifier):
        from historical_search import source_date
        from monitoring_service import complete_lines, classify_lines
        from web_service import write_json
        today = datetime.now().astimezone().date()
        if source_date(filename) != today:
            return
        fingerprint = hashlib.sha256(json.dumps([profile,rules],sort_keys=True).encode()).hexdigest()
        with self.lock:
            previous = self.data.get(application,{})
            stat = path.stat()
            same = (previous.get('filename')==filename and previous.get('profile')==fingerprint
                    and previous.get('identity')==[stat.st_dev,stat.st_ino]
                    and stat.st_size>=previous.get('offset',0))
            if same and stat.st_size==previous['offset'] and stat.st_mtime_ns==previous.get('mtime'):
                return
            # The source handle closes before any classification or rule matching.
            with path.open('rb') as file:
                if same:
                    file.seek(max(0,previous['offset']-256))
                    same = hashlib.sha256(file.read(min(256,previous['offset']))).hexdigest()==previous.get('anchor')
                if same and stat.st_size==previous['offset']:
                    same=False  # A same-size rewrite must be reviewed again.
                file.seek(previous['offset'] if same else 0)
                raw=file.read(stat.st_size-(previous['offset'] if same else 0))
                file.seek(max(0,stat.st_size-256))
                anchor=hashlib.sha256(file.read(min(256,stat.st_size))).hexdigest()
            added, buffer = complete_lines((base64.b64decode(previous.get('buffer','')) if same else b'')+raw)
            labels = classify_lines(added,classifier)
            per_line = [[] for _ in added]
            for finding in review_lines(added,rules)['findings']:
                per_line[finding['line_number']-1].append(finding)
            saved = deepcopy(previous) if same else {'lines':[],'labels':[],'findings':[]}
            saved['lines'].extend(added); saved['labels'].extend(labels); saved['findings'].extend(per_line)
            saved.update(filename=filename, profile=fingerprint, identity=[stat.st_dev,stat.st_ino],
                         offset=stat.st_size,mtime=stat.st_mtime_ns,anchor=anchor,
                         buffer=base64.b64encode(buffer).decode('ascii'))
            self.data[application]=saved
            write_json(self.path,self.data)

    def results(self, identifier=''):
        from historical_search import source_date
        from web_service import read_json, find_profile
        profiles=read_json(self.store.root / 'error_profiles.json', {})
        today = datetime.now().astimezone().date()
        active = {item['name'].casefold() for item in self.store.state()['applications']}
        with self.lock:
            rows=[]
            for application,saved in self.data.items():
                if application.casefold() not in active or source_date(saved['filename'])!=today:
                    continue
                rows.extend(build_incidents(application,saved['filename'],saved['lines'],saved['labels'],saved['findings']))
        rows=merge_incidents(rows)
        for row in rows:
            rules=(find_profile(profiles,row['application']) or {}).get('rules',[])
            rule=next((rule for rule in rules if rule.get('match')==row.get('match')),None)
            row['notes']=rule.get('notes','') if rule else ''
            override=self.statuses.get(row['id'])
            if override and override.get('resolved_by_run')==row.get('resolved_by_run'):
                row['status']=override['status']
        rows.sort(key=lambda item:(item['time'],item['line_number']),reverse=True)
        if identifier:
            match=next((row for row in rows if row['id']==identifier),None)
            if match is None:
                raise ValueError('This error is no longer available in today’s logs.')
            return {'incident':match}
        return {'date':today.isoformat(),'incidents':[{key:value for key,value in row.items() if key not in ('context','occurrences')} for row in rows]}
