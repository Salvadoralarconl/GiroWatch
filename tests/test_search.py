"""Search returns full occurrences and parent-run outcomes from saved results."""
import tempfile
import unittest
from web_service import WatchStore


class SearchTests(unittest.TestCase):
    def test_same_order_in_multiple_runs_and_apps_returns_full_groups_and_run_outcomes(self):
        with tempfile.TemporaryDirectory() as root:
            store = WatchStore(root)
            runs = [
                {'run_number': 1, 'run_status': 'complete', 'orders': [
                    {'lines': ['10/16/2026 09:00:00 AM Working on order #: ABC123', 'related line without ID'],
                     'status': 'complete', 'has_alert': False}],
                 'unassigned_review': {'has_alert': True, 'highest_severity': 'Critical'}},
                {'run_number': 2, 'run_status': 'complete', 'orders': [
                    {'lines': ['10/16/2026 09:02:00 AM Working on order #: ABC123', 'retry succeeded'],
                     'status': 'complete', 'has_alert': True, 'highest_severity': 'Warning'}],
                 'unassigned_review': {'has_alert': False}},
                {'run_number': 3, 'run_status': 'incomplete', 'orders': [
                    {'lines': ['Working on order #: ABC123'], 'status': 'unresolved'}], 'unassigned_review': {}},
            ]
            store.index_results('Cam', 'FRIDAY/20261016.log', [], runs, True)
            store.index_results('Other App', '20261016.log', [], runs[:1], False)
            result = store.search('ABC123',start='2026-10-16',end='2026-10-16')
            self.assertEqual(result['total'], 4)
            outcomes = {item['run_number']: item['outcome'] for item in result['groups'] if item['application'] == 'Cam'}
            self.assertEqual(outcomes, {1: 'Successful', 2: 'Error', 3: 'Incomplete'})
            first = next(item for item in result['groups'] if item['application'] == 'Cam' and item['run_number'] == 1)
            self.assertEqual(first['lines'], runs[0]['orders'][0]['lines'])
            warning = next(item for item in result['groups'] if item['application'] == 'Cam' and item['run_number'] == 2)
            self.assertEqual(warning['severity'], 'Warning')
            self.assertEqual(first['severity'], 'None')
            self.assertEqual(first['error_type'], 'None')
            self.assertEqual(warning['error_type'], 'Warning')
            self.assertEqual(store.search('ABC123', 'Other App',start='2026-10-16',end='2026-10-16')['groups'][0]['outcome'], 'Not assessed')
            self.assertEqual(store.search('ABC12')['total'], 0)
            self.assertEqual(store.search('')['total'], 0)

    def test_rescan_replaces_same_day_snapshot_but_keeps_other_days(self):
        with tempfile.TemporaryDirectory() as root:
            store = WatchStore(root)
            run = [{'run_number': 1, 'run_status': 'complete', 'orders': [
                {'lines': ['ORDER ID123'], 'status': 'complete'}], 'unassigned_review': {}}]
            store.index_results('Cam', 'FRIDAY/20261016.log', [], run, True)
            store.index_results('Cam', 'CAM 20261016.log', [], run, True)
            store.index_results('Cam', 'THURSDAY/20261015.log', [], run, True)
            self.assertEqual(WatchStore(root).search('ID123',start='2026-10-15',end='2026-10-16')['total'], 2)

    def test_large_result_set_can_be_read_without_dropping_occurrences(self):
        with tempfile.TemporaryDirectory() as root:
            store = WatchStore(root)
            groups = [{'lines': ['ORDER PAGED123', f'context {i}'], 'status': 'complete'} for i in range(61)]
            store.index_results('Cam', '20261016.log', [],
                                [{'run_number': 1, 'run_status': 'complete', 'orders': groups}], True)
            first = store.search('PAGED123',start='2026-10-16',end='2026-10-16')
            second = store.search('PAGED123', offset=first['next_offset'],start='2026-10-16',end='2026-10-16')
            self.assertEqual(first['total'], 61)
            self.assertEqual(len(first['groups']), 50)
            self.assertEqual(len(second['groups']), 11)
            self.assertIsNone(second['next_offset'])
            self.assertEqual(len({item['group_number'] for item in first['groups'] + second['groups']}), 61)
