"""Exercise saved configuration and the same three-file notebook test workflow."""
import json
from pathlib import Path
import tempfile
import unittest

import girowatch_core as core
from demo_data import demo_fixture
from web_service import WatchStore


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = WatchStore(self.root)
        self.fixture = demo_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, section, profile, application='Sandbox'):
        return self.store.configure({'action': 'save', 'section': section,
                                     'application': application, 'profile': profile})

    def seed(self):
        self.save('run', self.fixture['run_profile'])
        self.save('order', {**self.fixture['order_profile'], 'selected_model': 'nearest_example'})
        self.save('errors', {'rules': self.fixture['rules']})

    def test_save_edit_reload_copy_delete_restore_and_default_deletion(self):
        self.seed()
        self.assertEqual(WatchStore(self.root).profile('order', 'sandbox')['profile']['selected_model'], 'nearest_example')
        self.store.configure({'action': 'copy', 'section': 'order', 'application': 'Sandbox', 'target': 'Second'})
        self.assertTrue(self.store.profile('order', 'Second')['exists'])
        self.store.configure({'action': 'delete', 'section': 'order', 'application': 'Second'})
        self.assertFalse(self.store.profile('order', 'Second')['exists'])
        self.store.configure({'action': 'restore', 'section': 'order', 'application': 'Second'})
        self.assertTrue(self.store.profile('order', 'Second')['exists'])
        self.store.configure({'action': 'delete', 'section': 'run', 'application': 'Cam'})
        self.assertFalse(WatchStore(self.root).profile('run', 'Cam')['exists'])
        self.store.configure({'action': 'restore', 'section': 'run', 'application': 'Cam'})
        self.assertTrue(self.store.profile('run', 'Cam')['exists'])

    def test_invalid_examples_do_not_replace_saved_profile(self):
        self.seed()
        original = (self.root / 'order_profiles.json').read_bytes()
        with self.assertRaises(ValueError):
            self.save('order', {'messages': ['same', 'same', 'regular'],
                                'labels': ['Order_Start', 'Order_End', 'Other'], 'selected_model': 'linear_svm'})
        self.assertEqual((self.root / 'order_profiles.json').read_bytes(), original)

    def test_three_downloads_preserve_core_grouping_and_profiles_without_live_state_changes(self):
        self.seed()
        result = self.store.test_configuration({'application': 'Sandbox', 'source': 'upload',
                'files': [{'filename': 'example.log', 'text': self.fixture['text']}]})
        self.assertEqual(len(result['downloads']), 3)
        downloads = {file['kind']: file['data'] for file in result['downloads']}
        expected_runs, pending = core.group_runs(self.fixture['text'].splitlines(), self.fixture['run_profile'])
        self.assertEqual(downloads['runs'], expected_runs)
        expected_orders = core.group_orders(expected_runs, self.fixture['order_profile'], 'nearest_example', 'Sandbox')
        reviewed = core.apply_rules(expected_orders, self.fixture['rules'], 'Sandbox')
        self.assertEqual(downloads['orders'], reviewed)
        self.assertEqual(downloads['profiles']['order_profiles']['Sandbox']['selected_model'], 'nearest_example')
        self.assertEqual(result['summary']['pending_files'], int(pending))
        self.assertFalse(self.store.path.exists())

    def test_folder_testing_uses_only_latest_dated_file_and_model_override_does_not_save(self):
        self.seed()
        logs = self.root / 'logs'
        (logs / 'FRIDAY').mkdir(parents=True)
        (logs / 'FRIDAY' / '20261016.log').write_text(self.fixture['text'], encoding='utf-8')
        (logs / '20261015.log').write_text(self.fixture['text'], encoding='utf-8')
        self.save('folders', {'path': str(logs), 'recursive': True})
        before = (self.root / 'order_profiles.json').read_bytes()
        result = self.store.test_configuration({'application': 'Sandbox', 'source': 'folder', 'model': 'naive_bayes'})
        self.assertEqual(result['summary']['files'], 1)
        self.assertEqual(result['summary']['runs'], 4)
        orders = result['downloads'][1]['data']
        self.assertEqual(result['downloads'][2]['data']['test']['sources'][0]['filename'], 'FRIDAY/20261016.log')
        self.assertEqual([run['run_number'] for run in orders], list(range(1, 5)))
        self.assertEqual((self.root / 'order_profiles.json').read_bytes(), before)

    def test_missing_run_profile_and_invalid_test_sources_are_actionable(self):
        with self.assertRaisesRegex(ValueError, 'run profile'):
            self.store.test_configuration({'application': 'Unknown', 'source': 'upload', 'files': []})
        self.seed()
        with self.assertRaisesRegex(ValueError, 'folder profile'):
            self.store.test_configuration({'application': 'Sandbox', 'source': 'folder'})
        with self.assertRaises(ValueError):
            self.store.test_configuration({'application': 'Sandbox', 'source': 'upload',
                    'files': [{'filename': 'wrong.json', 'text': '{}'}]})

    def test_multiple_uploaded_logs_stay_separate_and_number_runs_globally(self):
        self.seed()
        result = self.store.test_configuration({'application': 'Sandbox', 'source': 'upload',
                    'files': [{'filename': name, 'text': self.fixture['text']}
                              for name in ('first.log', 'second.log')]})
        orders = result['downloads'][1]['data']
        self.assertEqual(len(orders), 8)
        self.assertEqual([run['run_number'] for run in orders], list(range(1, 9)))
        self.assertEqual({run['source_file'] for run in orders}, {'first.log', 'second.log'})
        self.assertEqual(result['summary']['orders'], 14)
