"""Monitoring follows the latest finished run and retains its color while running."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web_service import WatchStore


class MonitoringTests(unittest.TestCase):
    def test_one_second_quiet_period_persists(self):
        monitor=self.store.monitor
        monitor.configure_scanning({'action':'preferences','quiet_seconds':1})
        restored=WatchStore(self.root).monitor
        restored.restore_settings()
        self.assertEqual(restored.quiet_seconds,1)
        self.assertEqual(restored.status()['automatic_mode'],'paused')
    def test_manual_scan_targets_and_queue_merging(self):
        monitor = self.store.monitor
        name = self.store.state()['applications'][0]['name']
        monitor.request_scan({'application': name})
        self.assertEqual(monitor.queued_applications, {name})
        monitor.request_scan({'application': name})
        self.assertEqual(monitor.queued_applications, {name})
        with self.assertRaises(ValueError):
            monitor.request_scan({'application': 'Unknown app'})
        monitor.request_scan({})
        self.assertIsNone(monitor.queued_applications)
        monitor.request_scan({'application': name})
        self.assertIsNone(monitor.queued_applications)

    def test_source_is_closed_before_classifying_initial_and_appended_reads(self):
        import monitoring_service as monitoring
        self.file.write_text('BEGIN PROCESS\nactivity\nEND PROCESS\n',encoding='utf-8')
        classifier=monitoring.classifier_for({'messages':['BEGIN PROCESS','END PROCESS','activity'],'labels':['Run_Start','Run_End','Other']})
        opened=[];original_open=Path.open;original_classify=monitoring.classify_lines
        def tracked(path,*args,**kwargs):
            handle=original_open(path,*args,**kwargs)
            if path==self.file:opened.append(handle)
            return handle
        def classified(lines,model):
            self.assertTrue(opened)
            self.assertTrue(all(handle.closed for handle in opened),'Source log still open during classification')
            return original_classify(lines,model)
        with patch.object(Path,'open',tracked),patch.object(monitoring,'classify_lines',side_effect=classified):
            cursor,*_=monitoring.read_updates(self.file,{},classifier,'test')
            with original_open(self.file,'a') as file:file.write('BEGIN PROCESS\nactivity\n')
            monitoring.read_updates(self.file,cursor,classifier,'test')
        self.assertTrue(all(handle.closed for handle in opened))
        with patch.object(Path,'open',tracked),patch.object(monitoring,'classify_lines',side_effect=ValueError('simulated model failure')):
            with self.assertRaises(ValueError):
                monitoring.read_updates(self.file,{},classifier,'test')
        self.assertTrue(all(handle.closed for handle in opened),'Model failure leaked a source handle')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.logs = self.root / 'logs' / 'FRIDAY'
        self.logs.mkdir(parents=True)
        self.file = self.logs / '20261016.log'
        self.store = WatchStore(self.root)
        profile = {'messages': ['BEGIN PROCESS', 'END PROCESS', 'activity', 'WARN retry', 'FAIL request', 'IGNORE expected'],
                   'labels': ['Run_Start', 'Run_End'] + ['Other'] * 4}
        for section, value in [('run', profile), ('folders', {'path': str(self.logs.parent), 'recursive': True}),
                               ('errors', {'rules': [{'match': 'WARN', 'severity': 'Warning'},
                                                     {'match': 'FAIL', 'severity': 'Critical'},
                                                     {'match': 'IGNORE', 'severity': 'Ignore'}]})]:
            self.store.configure({'action': 'save', 'application': 'Monitor Test', 'section': section, 'profile': value})

    def tearDown(self):
        self.temp.cleanup()

    def test_preferences_persist_without_resuming_scanning(self):
        monitor=self.store.monitor
        monitor.restore_settings()
        monitor.configure_scanning({'action':'preferences','quiet_seconds':20,'notifications':{'resolved':True,'sound':True}})
        self.assertFalse(monitor.change_driven)
        self.assertEqual(monitor.quiet_seconds,20)
        restored=WatchStore(self.root).monitor
        restored.restore_settings()
        self.assertFalse(restored.change_driven)
        self.assertEqual(restored.quiet_seconds,20)
        self.assertTrue(restored.notifications['resolved'])
        restored.configure_scanning({'action':'resume'})
        self.assertEqual(restored.quiet_seconds,20)
        self.assertTrue(restored.notifications['sound'])
        for invalid in (0,60,90,True,'20',120):
            with self.assertRaises(ValueError):
                restored.configure_scanning({'action':'preferences','quiet_seconds':invalid})
        with self.assertRaises(ValueError):
            restored.configure_scanning({'action':'preferences','notifications':{'sound':'yes'}})

    def scan(self, text):
        self.file.write_text(text + '\n', encoding='utf-8')
        self.store.monitor.scan_once()
        return next(app for app in self.store.monitor.status()['applications'] if app['name'] == 'Monitor Test')

    def test_completed_run_colors_ignore_and_error_priority(self):
        for text, expected in [('activity', 'green'), ('IGNORE expected', 'green'),
                               ('WARN retry', 'yellow'), ('WARN retry\nFAIL request', 'red')]:
            result = self.scan(f'BEGIN PROCESS\n{text}\nEND PROCESS')
            self.assertEqual(result['color'], expected)
            self.assertFalse(result['pending'])

    def test_pending_run_promotes_warning_to_error_before_completion(self):
        self.assertEqual(self.scan('BEGIN PROCESS\nWARN retry\nEND PROCESS')['color'], 'yellow')
        result = self.scan('BEGIN PROCESS\nWARN retry\nEND PROCESS\nBEGIN PROCESS\nFAIL request')
        self.assertEqual(result['color'], 'red')
        self.assertTrue(result['pending'])
        result = self.scan('BEGIN PROCESS\nWARN retry\nEND PROCESS\nBEGIN PROCESS\nFAIL request\nEND PROCESS')
        self.assertEqual(result['color'], 'red')

    def test_pending_warning_turns_yellow_and_clean_run_must_finish_to_recover(self):
        self.assertEqual(self.scan('BEGIN PROCESS\nactivity\nEND PROCESS')['color'],'green')
        text='BEGIN PROCESS\nactivity\nEND PROCESS\nBEGIN PROCESS\nWARN retry'
        result=self.scan(text)
        self.assertEqual(result['color'],'yellow')
        self.assertTrue(result['pending'])
        text+='\nBEGIN PROCESS\nactivity'
        self.assertEqual(self.scan(text)['color'],'yellow')
        self.assertEqual(self.scan(text+'\nEND PROCESS')['color'],'green')

    def test_unresolved_incident_stays_visible_across_restarted_runs(self):
        self.scan('BEGIN PROCESS\nactivity\nEND PROCESS\nBEGIN PROCESS\nactivity')
        incident={'application':'Monitor Test','severity':'Warning','status':'Active'}
        with patch.object(self.store.home_errors,'results',return_value={'incidents':[incident]}):
            result=next(a for a in self.store.monitor.status()['applications'] if a['name']=='Monitor Test')
            self.assertEqual(result['color'],'yellow')
            incident['severity']='Error'
            self.assertEqual(next(a for a in self.store.monitor.status()['applications'] if a['name']=='Monitor Test')['color'],'red')
            incident['status']='Resolved'
            self.assertEqual(next(a for a in self.store.monitor.status()['applications'] if a['name']=='Monitor Test')['color'],'green')

    def test_new_day_with_only_pending_run_keeps_persisted_previous_color(self):
        self.assertEqual(self.scan('BEGIN PROCESS\nFAIL request\nEND PROCESS')['color'], 'red')
        (self.logs / '20261017.log').write_text('BEGIN PROCESS\nactivity\n', encoding='utf-8')
        restarted = WatchStore(self.root)
        restarted.monitor.scan_once()
        result = next(a for a in restarted.monitor.status()['applications'] if a['name'] == 'Monitor Test')
        self.assertEqual(result['color'], 'red')
        self.assertTrue(result['pending'])

    def test_first_pending_run_and_unavailable_folder_are_not_green(self):
        result = self.scan('BEGIN PROCESS\nactivity')
        self.assertIsNone(result['color'])
        self.assertTrue(result['pending'])
        self.file.unlink()
        self.logs.rmdir()
        result = self.scan_missing()
        self.assertIsNone(result['color'])
        self.assertIn('No dated logs', result['message'])

    def scan_missing(self):
        self.store.monitor.scan_once()
        return next(a for a in self.store.monitor.status()['applications'] if a['name'] == 'Monitor Test')

    def test_unchanged_snapshot_is_not_reprocessed_and_rules_change_invalidates_cache(self):
        self.scan('BEGIN PROCESS\nWARN retry\nEND PROCESS')
        with patch('monitoring_service.classify_lines', side_effect=AssertionError('must use cache')):
            self.store.monitor.scan_once()
        self.store.configure({'action': 'save', 'application': 'Monitor Test', 'section': 'errors',
                              'profile': {'rules': [{'match': 'WARN', 'severity': 'Ignore'}]}})
        self.store.monitor.scan_once()
        result = next(a for a in self.store.monitor.status()['applications'] if a['name'] == 'Monitor Test')
        self.assertEqual(result['color'], 'green')

    def test_append_only_reads_new_bytes_and_waits_for_partial_line(self):
        prefix = 'old historical activity\n' * 10000
        self.scan(prefix + 'BEGIN PROCESS\nactivity\nEND PROCESS')
        first = next(a for a in self.store.monitor.status()['applications'] if a['name'] == 'Monitor Test')
        self.assertLess(first['bytes_read'], self.file.stat().st_size)
        with self.file.open('ab') as file:
            file.write(b'BEGIN PROCESS\nWARN')
        self.store.monitor.scan_once()
        pending = next(a for a in self.store.monitor.status()['applications'] if a['name'] == 'Monitor Test')
        self.assertEqual(pending['bytes_read'], len(b'BEGIN PROCESS\nWARN'))
        self.assertEqual(pending['color'], 'green')
        self.assertTrue(pending['pending'])
        # Restart must keep the saved offset and unfinished UTF-8/line buffer.
        restarted = WatchStore(self.root)
        with self.file.open('ab') as file:
            file.write(b' retry\nEND PROCESS\n')
        restarted.monitor.scan_once()
        result = next(a for a in restarted.monitor.status()['applications'] if a['name'] == 'Monitor Test')
        self.assertEqual(result['bytes_read'], len(b' retry\nEND PROCESS\n'))
        self.assertEqual(result['color'], 'yellow')
        self.assertFalse(result['pending'])

    def test_scheduler_waits_one_minute_between_scans_without_real_sleep(self):
        monitor = self.store.monitor
        with patch.object(monitor, 'scan_once') as scan, patch.object(monitor.wake, 'wait') as wait:
            wait.side_effect = lambda interval: monitor.stop_event.set()
            monitor._loop()
            scan.assert_called_once()
            wait.assert_called_once_with(60)

    def test_status_exposes_next_scan_and_queued_manual_request(self):
        monitor = self.store.monitor
        with patch.object(monitor, 'scan_once'), patch.object(monitor.wake, 'wait') as wait:
            wait.side_effect = lambda interval: monitor.stop_event.set()
            monitor._loop()
        status = monitor.status()
        self.assertIsNotNone(status['next_scan_at'])
        monitor.request_scan()
        self.assertTrue(monitor.status()['queued'])
        self.assertIsNone(monitor.status()['next_scan_at'])

    def test_change_watch_waits_for_thirty_quiet_seconds_and_targets_changed_app(self):
        monitor=self.store.monitor
        self.file.write_text('BEGIN PROCESS\nactivity\nEND PROCESS\n',encoding='utf-8')
        with patch('monitoring_service.time.monotonic') as clock, patch.object(monitor,'application_waiting',return_value=True), patch.object(monitor,'scan_once') as scan:
            clock.return_value=0; monitor.watch_tick()
            clock.return_value=29; monitor.watch_tick();scan.assert_not_called()
            with self.file.open('a') as file:file.write('activity\n')
            clock.return_value=29; monitor.watch_tick()
            clock.return_value=58; monitor.watch_tick();scan.assert_not_called()
            clock.return_value=59; monitor.watch_tick();scan.assert_called_once_with({'Monitor Test'})
            clock.return_value=180; monitor.watch_tick();self.assertEqual(scan.call_count,1)
        self.assertIsNone(monitor.status()['next_scan_at'])

    def test_changed_log_requires_waiting_then_full_quiet_period(self):
        monitor=self.store.monitor
        monitor.quiet_seconds=10
        self.file.write_text('BEGIN PROCESS\nactivity\n',encoding='utf-8')
        with patch('monitoring_service.time.monotonic') as clock, patch.object(monitor,'application_waiting') as waiting, patch.object(monitor,'scan_once') as scan:
            waiting.return_value=False
            clock.return_value=0;monitor.watch_tick()
            clock.return_value=50;monitor.watch_tick();scan.assert_not_called()
            waiting.return_value=True
            clock.return_value=51;monitor.watch_tick();scan.assert_not_called()
            clock.return_value=60;monitor.watch_tick();scan.assert_not_called()
            clock.return_value=61;monitor.watch_tick();scan.assert_called_once_with({'Monitor Test'})
            clock.return_value=100;monitor.watch_tick();self.assertEqual(scan.call_count,1)

    def test_status_identifies_only_the_application_currently_scanning(self):
        self.file.write_text('BEGIN PROCESS\nactivity\nEND PROCESS\n',encoding='utf-8')
        observed=[]
        def during_scan(*args):
            rows=self.store.monitor.status()['applications']
            observed.append([row['name'] for row in rows if row['scanning']])
        with patch.object(self.store.home_errors,'update',side_effect=during_scan):
            self.store.monitor.scan_once({'Monitor Test'})
        self.assertEqual(observed,[['Monitor Test']])
        self.assertFalse(any(row['scanning'] for row in self.store.monitor.status()['applications']))

    def test_metadata_watch_never_opens_source_contents(self):
        self.file.write_text('activity\n',encoding='utf-8')
        original=Path.open
        def guarded(path,*args,**kwargs):
            if path.suffix.lower()=='.log':
                raise AssertionError('Metadata watcher opened a log')
            return original(path,*args,**kwargs)
        with patch('monitoring_service.time.monotonic',return_value=0), patch.object(Path,'open',guarded), patch.object(self.store.monitor,'scan_once'):
            self.store.monitor.watch_tick()
        self.assertEqual(self.store.monitor.watch_state['Monitor Test']['signature'][3],self.file.stat().st_size)

    def test_settings_pause_resume_persist_and_resume_waits_for_quiet_period(self):
        monitor=self.store.monitor
        with self.assertRaises(ValueError):monitor.configure_scanning({'action':'invalid'})
        monitor.configure_scanning({'action':'resume'})
        self.assertEqual(monitor.status()['automatic_mode'],'changes')
        self.assertTrue(monitor.wake.is_set())
        monitor.configure_scanning({'action':'pause'})
        self.assertEqual(monitor.status()['automatic_mode'],'paused')
        self.assertIsNone(monitor.next_scan_at)
        restored=WatchStore(self.root).monitor
        restored.restore_settings()
        self.assertEqual(restored.status()['automatic_mode'],'paused')
        monitor.configure_scanning({'action':'resume'})
        restored=WatchStore(self.root).monitor
        restored.restore_settings()
        self.assertEqual(restored.status()['automatic_mode'],'changes')
        self.assertEqual(restored.quiet_seconds,30)
        monitor.configure_scanning({'action':'pause'})
        monitor.request_scan()
        self.assertTrue(monitor.queued)
        self.assertEqual(monitor.status()['automatic_mode'],'paused')
