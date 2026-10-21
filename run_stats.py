"""Seven calendar days of distinct completed runs, updated on manual scans."""
from datetime import datetime,timedelta
import base64
import hashlib
import json
from pathlib import Path
import re
import threading


def dates():
    today=datetime.now().astimezone().date()
    return [today-timedelta(days=ago) for ago in range(6,-1,-1)]


class RunStats:
    def __init__(self,store):
        from web_service import read_json
        self.store=store
        self.path=store.root/'web_data'/'run_counts.json'
        self.data=read_json(self.path,{'applications':{},'warnings':[]})
        self.lock=threading.RLock()
        self.models={}

    def scan_once(self, application_names=None):
        from web_service import read_json,write_json,find_profile
        from folder_profiles import discover_logs
        from historical_search import source_date
        from monitoring_service import classifier_for,classify_lines,complete_lines
        wanted={day.isoformat() for day in dates()}
        with self.store.lock:
            folders=read_json(self.store.root/'folder_profiles.json',{})
            run_profiles,_,_=self.store.profiles()
        warnings=[]
        with self.lock:
            active=set()
            for application,folder in folders.items():
                profile=find_profile(run_profiles,application)
                if not profile:
                    continue
                active.add(application)
                if application_names is not None and application not in application_names:
                    continue
                fingerprint=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
                try:
                    # Only exact dated originals count, never Copy files.
                    chosen={}
                    for filename in discover_logs(folder):
                        day=source_date(filename)
                        if not re.fullmatch(r'\d{8}\.log',Path(filename).name,re.I) or not day or day.isoformat() not in wanted:
                            continue
                        path=Path(folder['path'])/filename
                        stat=path.stat()
                        if day.isoformat() not in chosen or stat.st_mtime_ns>chosen[day.isoformat()][1].st_mtime_ns:
                            chosen[day.isoformat()]=(path,stat)
                    saved=self.data['applications'].setdefault(application,{})
                    for day,(path,stat) in chosen.items():
                        old=saved.get(day,{})
                        same=(old.get('file')==str(path) and old.get('profile')==fingerprint
                              and old.get('identity')==[stat.st_dev,stat.st_ino] and stat.st_size>=old.get('offset',0))
                        if same and stat.st_size==old['offset'] and stat.st_mtime_ns==old.get('mtime'):
                            continue
                        with path.open('rb') as file:
                            if same:
                                file.seek(max(0,old['offset']-256))
                                same=hashlib.sha256(file.read(min(256,old['offset']))).hexdigest()==old.get('anchor')
                            if same and stat.st_size==old['offset']:
                                same=False
                            file.seek(old['offset'] if same else 0)
                            raw=file.read(stat.st_size-(old['offset'] if same else 0))
                            file.seek(max(0,stat.st_size-256))
                            anchor=hashlib.sha256(file.read(min(256,stat.st_size))).hexdigest()
                        lines,buffer=complete_lines((base64.b64decode(old.get('buffer','')) if same else b'')+raw)
                        if fingerprint not in self.models:
                            self.models[fingerprint]=classifier_for(profile)
                        labels=classify_lines(lines,self.models[fingerprint])
                        count=old['count'] if same else 0
                        running=old['running'] if same else False
                        for label in labels:
                            if label=='Run_Start':running=True
                            elif label=='Run_End' and running:count+=1;running=False
                        saved[day]={'file':str(path),'profile':fingerprint,'identity':[stat.st_dev,stat.st_ino],
                                    'offset':stat.st_size,'mtime':stat.st_mtime_ns,'anchor':anchor,
                                    'buffer':base64.b64encode(buffer).decode('ascii'),'running':running,'count':count}
                    self.data['applications'][application]={day:item for day,item in saved.items() if day in wanted}
                except (OSError,ValueError,UnicodeError) as error:
                    warnings.append(f'{application}: {error}')
            self.data['applications']={app:days for app,days in self.data['applications'].items() if app in active}
            self.data['warnings']=warnings
            self.data['scanned_at']=datetime.now().astimezone().isoformat()
            write_json(self.path,self.data)

    def results(self):
        active={app['name'].casefold() for app in self.store.state()['applications']}
        with self.lock:
            days=[{'date':day.isoformat(),'label':day.strftime('%a'),'count':sum(
                saved.get(day.isoformat(),{}).get('count',0) for app,saved in self.data['applications'].items()
                if app.casefold() in active)} for day in dates()]
            return {'today':days[-1]['count'],'days':days,'scanned_at':self.data.get('scanned_at'),
                    'warnings':list(self.data.get('warnings',[]))}
