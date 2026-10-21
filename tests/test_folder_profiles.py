"""Verify per-application persistence and recursive source discovery."""
from pathlib import Path
import tempfile
import unittest
from web_service import WatchStore
from folder_profiles import latest_log


class FolderProfileTests(unittest.TestCase):
    def test_latest_dated_log_across_weekdays_ignores_copies_and_modification_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'FRIDAY').mkdir()
            (root / 'THURSDAY').mkdir()
            (root / 'FRIDAY' / '20261016.log').write_text('latest')
            (root / 'THURSDAY' / '20261015.log').write_text('older but written later')
            (root / 'FRIDAY' / '20261023 - Copy.log').write_text('copy')
            (root / 'FRIDAY' / '20269999.log').write_text('invalid date')
            self.assertEqual(latest_log({'path': str(root), 'recursive': True}), str(Path('FRIDAY/20261016.log')))
            with self.assertRaisesRegex(ValueError, 'YYYYMMDD'):
                latest_log({'path': str(root), 'recursive': False})
    def test_saved_profiles_survive_reload_and_discovery_respects_subfolders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / 'logs'
            (logs / 'THURSDAY').mkdir(parents=True)
            (logs / '20261016.log').write_text('BEGIN PROCESS')
            (logs / 'THURSDAY' / '20261015.LOG').write_text('END PROCESS')
            (logs / 'ignore.json').write_text('{}')
            payload = {'application': 'Test App', 'path': str(logs), 'recursive': True, 'action': 'save'}
            store = WatchStore(root)
            store.folder_profile(payload)
            reloaded = WatchStore(root)
            self.assertEqual(reloaded.profile('folders', 'test app')['profile']['path'], str(logs))
            self.assertTrue(next(a for a in reloaded.state()['applications'] if a['name'] == 'Test App')['folder_profile'])
            result = reloaded.folder_profile({**payload, 'action': 'check'})
            self.assertEqual(result['count'], 2)
            self.assertEqual(reloaded.folder_profile({**payload, 'action': 'check', 'recursive': False})['count'], 1)
            self.assertEqual((logs / '20261016.log').read_text(), 'BEGIN PROCESS')

    def test_disconnected_location_can_be_saved_but_check_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = WatchStore(temporary)
            payload = {'application': 'Cam', 'path': str(Path(temporary) / 'missing'), 'action': 'save'}
            self.assertTrue(store.folder_profile(payload)['saved'])
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                store.folder_profile({**payload, 'action': 'check'})
            with self.assertRaises(ValueError):
                store.folder_profile({**payload, 'path': 'relative/path'})
