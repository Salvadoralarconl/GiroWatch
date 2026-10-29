import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from local_test_mode import LocalTestStore, allow_test_request
from web_app import make_handler
from simulator_controls import TEST_APPS
from test_interface import write_event
from accounts import Accounts


class LocalTestModeTests(unittest.TestCase):
    def test_seed_orders_are_searchable_alongside_live_simulator_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            self.addCleanup(store.close)
            query = '90000000000000002C00'
            self.assertEqual(store.search(query)['total'], len(TEST_APPS))
            name = TEST_APPS[0]
            logs = store.simulators.root / name / 'logs'
            for message in ('BEGIN PROCESS', 'ORDER START: LIVE123',
                            'Working on order #: LIVE123', 'ORDER END: LIVE123', 'END PROCESS'):
                write_event(logs, message)
            store.monitor.scan_once({name})
            self.assertEqual(store.search(query, name)['total'], 1)
            self.assertEqual(store.search('LIVE123', name)['total'], 1)
            self.assertEqual(store.search(query, start='2000-01-01', end='2000-01-01')['total'], 0)

    def test_pause_resume_only_watch_isolated_test_folders(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            allow_test_request('POST', '/api/monitoring-settings')
            self.assertEqual(store.monitor.status()['automatic_mode'], 'changes')
            self.assertEqual(store.monitor.configure_scanning({'action': 'pause'})['automatic_mode'], 'paused')
            self.assertEqual(store.monitor.configure_scanning({'action': 'resume'})['automatic_mode'], 'changes')
            self.assertTrue(all(Path(store.profile('folders', name)['profile']['path']).is_relative_to(Path(folder)) for name in TEST_APPS))

    def test_simulated_warning_and_error_reach_monitoring_and_incidents(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            for name, phrase, expected in [('TEST UNITELLER', 'SIMULATED WARNING: order needs review', 'yellow'),
                                            ('TEST UNITRANSFER', 'SIMULATED ERROR: order processing failed', 'red')]:
                logs = store.simulators.root / name / 'logs'
                for message in ('BEGIN PROCESS', phrase, 'END PROCESS'):
                    write_event(logs, message)
                store.monitor.scan_once({name})
                row = next(a for a in store.monitor.status()['applications'] if a['name'] == name)
                self.assertEqual(row['color'], expected)
            incidents = store.home_errors.results()['incidents']
            self.assertEqual({i['severity'] for i in incidents}, {'Warning', 'Error'})

    def test_only_fictional_apps_and_no_external_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('application_control.cam_command') as cam, patch('application_control.test_window') as window:
                store = LocalTestStore(Path(folder))
                state = store.state()
                self.assertTrue(state['local_test_mode'])
                self.assertEqual([a['name'] for a in state['applications']], list(TEST_APPS))
                self.assertEqual(len(state['datasets']), 4)
                status = store.monitor.status()
                self.assertTrue(all(a['control_available'] and not a['process_running'] for a in status['applications']))
                cam.assert_not_called()
                window.assert_not_called()
                self.assertIsNone(store.monitor.thread)

    def test_open_simulator_without_logs_is_waiting_for_first_run(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            store.monitor.scan_once()
            with patch.object(store.simulators, 'status', return_value={
                    'process_running': True, 'control_available': True, 'live_timer_state': 'waiting'}):
                rows = store.monitor.status()['applications']
            self.assertTrue(all(row['message'] == 'Waiting for first run' for row in rows))
            self.assertTrue(all(row['color'] is None for row in rows))

    def test_blocks_all_external_access_routes_before_dispatch(self):
        for method, route in [('POST', '/api/folder-profile'),
                              ('POST', '/api/configure'), ('POST', '/api/test-configuration'),
                              ('POST', '/api/unknown-route')]:
            with self.subTest(route=route), self.assertRaisesRegex(ValueError, 'Local test mode'):
                allow_test_request(method, route)
        allow_test_request('GET', '/api/state')
        allow_test_request('GET', '/api/monitoring')
        allow_test_request('POST', '/api/home-error-status')

    def test_http_requests_cannot_reach_windows_or_network_folders(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store))
            _, cookie = Accounts(store.root).action({'action':'create','name':'Tester','email':'tester@example.test','password':'test-password-123'})
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with patch('web_app.application_action') as control, patch('web_service.discover_logs') as discover:
                    for path, payload in [('/api/application-action', {'application': 'Cam', 'action': 'restart'}),
                                          ('/api/folder-profile', {'action': 'check', 'path': r'\\server\logs'}),
                                          ('/api/configure', {'section': 'folders', 'action': 'save'})]:
                        request = Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Cookie':cookie})
                        with self.assertRaises(HTTPError) as error:
                            urlopen(request)
                        self.assertEqual(error.exception.code, 400)
                    control.assert_not_called()
                    discover.assert_not_called()
                    with urlopen(Request(base + '/api/monitoring', headers={'Cookie':cookie})) as response:
                        self.assertEqual(len(json.load(response)['applications']), 4)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
