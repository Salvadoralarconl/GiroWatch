"""Exercise the real local HTTP routes, rather than mocking the API."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from web_app import make_handler
from web_service import WatchStore


class WebHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WatchStore(Path(self.temp.name))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_demo_api_and_saved_state_deliver_reviewed_groups(self):
        request = Request(self.url + '/api/demo', data=b'{}', headers={'Content-Type': 'application/json'})
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            result = json.load(response)
        self.assertEqual(len(result['runs']), 4)
        self.assertEqual(len(result['alerts']), 3)
        with urlopen(self.url + '/api/state') as response:
            state = json.load(response)
        self.assertEqual(state['datasets'][0]['runs'][1]['orders'][0]['highest_severity'], 'Warning')

    def test_external_origin_cannot_trigger_a_scan(self):
        request = Request(self.url + '/api/demo', data=b'{}', headers={
            'Content-Type': 'application/json', 'Origin': 'https://unrelated.example'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.store.state()['datasets'], [])

    def test_monitoring_status_and_manual_scan_request(self):
        with urlopen(self.url + '/api/monitoring') as response:
            status = json.load(response)
        self.assertEqual(status['interval_seconds'], 60)
        self.assertTrue(all(app['color'] is None for app in status['applications']))
        request = Request(self.url + '/api/monitoring-scan', data=b'{}',
                          headers={'Content-Type': 'application/json'})
        with urlopen(request) as response:
            self.assertTrue(json.load(response)['scheduled'])
        self.assertTrue(self.store.monitor.wake.is_set())

    def test_monitoring_settings_can_pause_and_resume(self):
        for action,mode in [('pause','paused'),('resume','changes'),('pause','paused')]:
            request=Request(self.url+'/api/monitoring-settings',data=json.dumps({'action':action}).encode(),headers={'Content-Type':'application/json'})
            with urlopen(request) as response:
                result=json.load(response)
            self.assertEqual(result['automatic_mode'],mode)
            self.assertEqual(result['quiet_seconds'],30)
        with urlopen(self.url+'/api/monitoring') as response:
            self.assertEqual(json.load(response)['automatic_mode'],'paused')

    def test_configuration_routes_save_and_test_exactly_three_exports(self):
        from demo_data import demo_fixture
        fixture = demo_fixture()
        def post(route, payload):
            request = Request(self.url + route, data=json.dumps(payload).encode(),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                return json.load(response)
        for section in ('run', 'order'):
            profile = fixture[f'{section}_profile']
            if section == 'order':
                profile = {**profile, 'selected_model': 'nearest_example'}
            post('/api/configure', {'application': 'Browser Test', 'section': section,
                                   'action': 'save', 'profile': profile})
        result = post('/api/test-configuration', {'application': 'Browser Test', 'source': 'upload',
                      'files': [{'filename': '20261016.log', 'text': fixture['text']}]})
        self.assertEqual([file['kind'] for file in result['downloads']], ['runs', 'orders', 'profiles'])
        self.assertEqual(result['summary']['runs'], 4)
        self.assertEqual(result['summary']['orders'], 7)
        self.assertFalse(self.store.path.exists())
        with urlopen(self.url + '/api/search?q=90000000000000001C00&start=2026-10-01&end=2026-10-31') as response:
            found = json.load(response)
        self.assertEqual(found['total'], 2)
        self.assertEqual({group['application'] for group in found['groups']}, {'Browser Test'})
        self.assertIn('retry succeeded', '\n'.join(found['groups'][0]['lines']))

    def test_profile_files_cannot_be_downloaded_as_static_assets(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url + '/order_profiles.json')
        self.assertEqual(caught.exception.code, 404)
        with urlopen(self.url + '/') as response:
            self.assertIn(b'GiroWatch', response.read())

    def test_original_design_icon_is_served_but_asset_traversal_is_rejected(self):
        with urlopen(self.url + '/assets/logo.png') as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertTrue(response.read().startswith(b'\x89PNG'))
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url + '/assets/../order_profiles.json')
        self.assertEqual(caught.exception.code, 404)

    def test_selected_application_profile_details_do_not_mix_or_modify_examples(self):
        root = Path(self.temp.name)
        profiles = {
            'Alpha': {'messages': ['Alpha begins', 'Alpha ends', 'Alpha activity'], 'labels': ['Run_Start', 'Run_End', 'Other']},
            'Beta': {'messages': ['Beta starts', 'Beta finishes', 'Beta work'], 'labels': ['Run_Start', 'Run_End', 'Other']},
        }
        path = root / 'girosol_profiles.json'
        path.write_text(json.dumps(profiles))
        original = path.read_bytes()
        for application, wanted in [('alpha', 'Alpha begins'), ('Beta', 'Beta starts')]:
            with urlopen(self.url + '/api/profile?section=run&application=' + application) as response:
                result = json.load(response)
            self.assertTrue(result['exists'])
            self.assertEqual(result['profile']['messages'][0], wanted)
        self.assertEqual(path.read_bytes(), original)

    def test_order_model_and_all_error_rules_are_returned_for_the_selected_profile(self):
        root = Path(self.temp.name)
        order = {'messages': ['start', 'end', 'other'], 'labels': ['Order_Start', 'Order_End', 'Other'], 'selected_model': 'nearest_example'}
        rules = [{'match': 'E100', 'severity': 'Warning', 'message': 'Review request'}, {'match': 'E200', 'severity': 'Ignore', 'case_sensitive': True, 'message': 'Expected'}]
        (root / 'order_profiles.json').write_text(json.dumps({'Alpha': order}))
        (root / 'error_profiles.json').write_text(json.dumps({'Alpha': {'rules': rules}}))
        with urlopen(self.url + '/api/profile?section=order&application=Alpha') as response:
            self.assertEqual(json.load(response)['profile'], order)
        with urlopen(self.url + '/api/profile?section=errors&application=Alpha') as response:
            self.assertEqual(json.load(response)['profile']['rules'], rules)
        with urlopen(self.url + '/api/profile?section=order&application=Missing') as response:
            self.assertEqual(json.load(response)['profile'], None)


if __name__ == '__main__':
    unittest.main()
