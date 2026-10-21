import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from demo_data import demo_fixture
from web_service import WatchStore

class HistoricalSearchTests(unittest.TestCase):
    def test_missing_dates_search_only_today(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as temp:
            store=WatchStore(Path(temp))
            with patch.object(store.historical_search,'snapshots',return_value=([],set(),[])) as snapshots:
                store.search('test','UNITELLER')
                today=datetime.now().astimezone().date()
                self.assertEqual(snapshots.call_args.args,('UNITELLER',today,today))

    def setUp(self):
        clock = patch('historical_search.current_week', return_value=(2026, 42))
        clock.start()
        self.addCleanup(clock.stop)

    def test_date_range_cache_and_profile_invalidation(self):
        fixture = demo_fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            logs = root / 'logs' / 'FRIDAY'
            logs.mkdir(parents=True)
            for date in ('20261009', '20261015', '20261016'):
                (logs / (date + '.log')).write_text(fixture['text'], encoding='utf-8')
            (logs / '20261016 - Copy.log').write_text(fixture['text'], encoding='utf-8')
            for name, value in [('girosol_profiles.json', {'Demo': fixture['run_profile']}),
                ('order_profiles.json', {'Demo': fixture['order_profile']}),
                ('error_profiles.json', {'Demo': {'rules': fixture['rules']}}),
                ('folder_profiles.json', {'Demo': {'path': str(root / 'logs'), 'recursive': True}})]:
                (root / name).write_text(json.dumps(value), encoding='utf-8')
            store = WatchStore(root)
            with patch('girowatch_core.group_runs', wraps=__import__('girowatch_core').group_runs) as grouped:
                result = store.search('anything', 'Demo', start='2026-10-16', end='2026-10-16')
                self.assertEqual(grouped.call_count, 1)
                store.search('other', 'Demo', start='2026-10-16', end='2026-10-16')
                self.assertEqual(grouped.call_count, 1)
                store.search('other', 'Demo', start='2026-10-15', end='2026-10-16')
                self.assertEqual(grouped.call_count, 2)
                (logs / '20261016.log').write_text(fixture['text'] + '\nextra\n', encoding='utf-8')
                store.search('other', 'Demo', start='2026-10-16', end='2026-10-16')
                self.assertEqual(grouped.call_count, 3)
            self.assertEqual(result['warnings'], [])
            result = store.search('90000000000000001C00', 'Demo', start='2026-10-09', end='2026-10-16')
            self.assertEqual(result['total'], 6)
            self.assertEqual({row['outcome'] for row in result['groups']}, {'Successful', 'Error'})
            weeks = list((root / 'web_data' / 'search_weeks').glob('*.json'))
            self.assertEqual(len(weeks), 1)
            with patch('girowatch_core.group_runs', wraps=__import__('girowatch_core').group_runs) as grouped:
                store.search('other', 'Demo', start='2026-10-09', end='2026-10-09')
                store.search('other', 'Demo', start='2026-10-09', end='2026-10-09')
                self.assertEqual(grouped.call_count, 2)
            self.assertEqual(store.search('90000000000000001C00', 'Demo', start='2026-10-16', end='2026-10-16')['total'], 2)
            with self.assertRaises(ValueError):
                store.search('x', start='2026-10-17', end='2026-10-01')
