"""Fictional data only; no production profiles, folders, or Windows controls."""
from datetime import datetime
import girowatch_core as core

from demo_data import demo_fixture
from web_service import WatchStore, read_json, write_json
from simulator_controls import SimulatorControls, TEST_APPS
from monitoring_service import Monitor


class TestMonitor(Monitor):
    def status(self):
        result = super().status()
        for app in result['applications']:
            app.update(self.store.simulators.status(app['name']))
            if app.get('process_running') and app.get('message', '').startswith('No dated logs found'):
                app['message'] = 'Waiting for first run'
        return result


def allow_test_request(method, path):
    # Allowlist: new API endpoints stay blocked until explicitly reviewed.
    allowed = {
        'GET': {'/api/state', '/api/contacts', '/api/monitoring', '/api/home-errors',
                '/api/home-stats', '/api/profile', '/api/search', '/api/application-log'},
        'POST': {'/api/home-error-status', '/api/alert', '/api/application-action', '/api/monitoring-scan', '/api/monitoring-settings', '/api/contacts'},
    }
    if path.startswith('/api/') and path not in allowed.get(method, set()):
        raise ValueError('Local test mode: server access, folder access, scanning, and application controls are disabled.')


class LocalTestStore(WatchStore):
    local_test_mode = True

    def __init__(self, root):
        super().__init__(root)
        self.simulators = SimulatorControls(self.root / 'simulators')
        self.monitor = TestMonitor(self)
        fixture = demo_fixture()
        folders = {}
        for name in TEST_APPS:
            # Use today's date so today's dashboard/search can show the samples.
            text = fixture['text'].replace('10/16/2026', datetime.now().strftime('%m/%d/%Y'))
            text = text.replace('ERROR E100', 'Sample retry').replace('ERROR E300', 'Sample completed').replace('ERROR E400', 'Sample connected')
            dataset = self._process(name, datetime.now().strftime('%Y%m%d.log'), text,
                          fixture['run_profile'], fixture['order_profile'], fixture['rules'],
                          'nearest_example', demo=True)
            # Keep test examples searchable even when today's live simulator log
            # replaces its own snapshot. Production demo imports remain excluded.
            self.index_results(name, dataset['filename'], dataset['source_runs'],
                               dataset['runs'], dataset['errors_assessed'],
                               source_id='demo:' + datetime.now().strftime('%Y%m%d'))
            log_folder = self.simulators.root / name / 'logs'
            log_folder.mkdir(parents=True, exist_ok=True)
            folders[name] = {'path': str(log_folder), 'recursive': False, 'extension': '.log'}
        write_json(self.root / 'folder_profiles.json', folders)
        self.monitor.restore_settings()

    def application_action(self, payload):
        return self.simulators.action(payload)

    def open_simulators(self):
        for name in TEST_APPS:
            self.simulators.action({'application': name, 'action': 'restart'})
        self.monitor.start()

    def close(self):
        self.monitor.stop()
        if self.monitor.thread:
            self.monitor.thread.join(timeout=10)
        self.simulators.close()

    def profiles(self):
        fixture = demo_fixture()
        names = TEST_APPS
        run_profile = {'messages': ['BEGIN PROCESS', 'END PROCESS', 'LOGIN OK SIMULATED', 'ORDER TEST SENDING ORDER', 'SIMULATED ORDER SUCCESS', 'SIMULATED WARNING order needs review', 'SIMULATED ERROR order processing failed', 'NO MORE PENDING ORDERS', 'ORDER START TEST', 'ORDER END TEST'],
                       'labels': ['Run_Start', 'Run_End'] + ['Other'] * 8}
        rules = fixture['rules'] + [
            {'match': 'SIMULATED WARNING', 'severity': 'Warning', 'message': 'TEST warning: order needs review'},
            {'match': 'SIMULATED ERROR', 'severity': 'Critical', 'message': 'TEST error: simulated processing failure'}]
        return ({n: run_profile for n in names},
                {n: {'messages': ['ORDER START:', 'ORDER END:', 'SIMULATED ORDER SUCCESS', 'Validating beneficiary account', 'SENDING ORDER TO PAYER', 'BEGIN PROCESS', 'END PROCESS'],
                     'labels': ['Order_Start', 'Order_End'] + ['Other'] * 5,
                     'selected_model': 'nearest_example'} for n in names},
                {n: {'rules': rules} for n in names})

    def state(self):
        with self.lock:
            state = read_json(self.path, {'datasets': []})
            state.update(local_test_mode=True, models=core.MODEL_NAMES)
            state['applications'] = [dict(name=name, run_profile=True, order_profile=True,
                                          error_profile=True, folder_profile=True,
                                          control_profile=False, selected_model='nearest_example')
                                     for name in TEST_APPS]
            return state
