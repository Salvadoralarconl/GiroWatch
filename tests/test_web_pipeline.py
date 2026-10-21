"""Real model tests: group boundaries, order context and local persistence."""
import json
from pathlib import Path
import tempfile
import unittest


class PipelineTests(unittest.TestCase):
    def test_synthetic_girosol_pipeline_keeps_occurrences_and_error_context(self):
        import girowatch_core as core
        from demo_data import demo_fixture

        fixture = demo_fixture()
        grouped, pending = core.group_runs(fixture['text'].splitlines(), fixture['run_profile'])
        self.assertEqual([r['status'] for r in grouped], ['complete', 'complete', 'incomplete', 'complete'])
        self.assertTrue(pending)
        orders = core.group_orders(grouped, fixture['order_profile'], 'nearest_example', 'INTERBANK Demo')
        self.assertEqual([len(r['orders']) for r in orders], [3, 2, 1, 1])
        self.assertEqual(orders[2]['orders'][0]['status'], 'unresolved')
        reviewed = core.apply_rules(orders, fixture['rules'], 'INTERBANK Demo')
        self.assertEqual(reviewed[1]['orders'][0]['highest_severity'], 'Warning')
        self.assertEqual(reviewed[1]['orders'][1]['has_alert'], False)
        self.assertEqual(reviewed[2]['orders'][0]['highest_severity'], 'Critical')
        self.assertTrue(reviewed[0]['unassigned_review']['has_alert'])
        matches = core.search_orders(reviewed, '90000000000000001C00')
        self.assertEqual([m['run_number'] for m in matches], [1, 2])
        self.assertIn('retry succeeded', '\n'.join(matches[1]['lines']))
        self.assertEqual(matches[1]['lines'], orders[1]['orders'][0]['lines'])
        self.assertNotIn('90000000000000007C00', json.dumps(orders))

    def test_scan_persists_and_rescan_replaces_instead_of_duplicating(self):
        from web_service import WatchStore
        from demo_data import demo_fixture
        fixture = demo_fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, data in [
                ('girosol_profiles.json', {'INTERBANK Demo': fixture['run_profile']}),
                ('order_profiles.json', {'INTERBANK Demo': fixture['order_profile']}),
                ('error_profiles.json', {'INTERBANK Demo': {'rules': fixture['rules']}}),
            ]:
                (root / name).write_text(json.dumps(data), encoding='utf-8')
            store = WatchStore(root)
            payload = {'application': 'INTERBANK Demo', 'filename': 'synthetic.log', 'text': fixture['text']}
            store.scan(payload)
            store.scan(payload)
            state = WatchStore(root).state()
            self.assertEqual(len(state['datasets']), 1)
            self.assertEqual(len(state['datasets'][0]['runs']), 4)
            self.assertEqual(len(state['datasets'][0]['alerts']), 3)
            self.assertEqual(state['datasets'][0]['pending_run'], True)
            alert = state['datasets'][0]['alerts'][0]
            store.set_alert({'application': 'INTERBANK Demo', 'id': alert['id'], 'status': 'Investigating'})
            self.assertEqual(WatchStore(root).state()['datasets'][0]['alerts'][0]['status'], 'Investigating')

    def test_foreign_application_json_cannot_be_imported_under_wrong_name(self):
        from web_service import WatchStore
        with tempfile.TemporaryDirectory() as temp:
            store = WatchStore(Path(temp))
            with self.assertRaisesRegex(ValueError, 'application'):
                store.scan({'application': 'Cam', 'filename': 'orders.json', 'text': json.dumps([
                    {'application': 'UNITRANSFER', 'run_status': 'complete', 'orders': [], 'unassigned_lines': []}
                ])})

    def test_missing_error_policy_is_not_shown_as_no_errors(self):
        from web_service import WatchStore
        with tempfile.TemporaryDirectory() as temp:
            store = WatchStore(Path(temp))
            store.scan({'application': 'Cam', 'filename': 'runs.json', 'text': json.dumps([
                {'status': 'complete', 'lines': ['BEGIN PROCESS', 'Other line', 'END PROCESS']}
            ])})
            data = store.state()['datasets'][0]
            self.assertFalse(data['errors_assessed'])
            self.assertFalse(data['orders_assessed'])
            self.assertTrue(data['notes'])

    def test_website_export_can_be_imported_without_losing_run_context(self):
        from web_service import WatchStore
        with tempfile.TemporaryDirectory() as temp:
            store = WatchStore(Path(temp))
            original = store.demo()
            store.scan({'application': 'INTERBANK Demo', 'filename': 'GiroWatch_results.json',
                        'text': json.dumps({'datasets': [original]})})
            restored = store.state()['datasets'][0]
            self.assertEqual(restored['source_runs'], original['source_runs'])
            self.assertTrue(restored['pending_run'])
            self.assertEqual([len(r['orders']) for r in restored['runs']], [3, 2, 1, 1])

    def test_web_grouping_matches_the_actual_terminal_workflows(self):
        import contextlib
        import io
        import os
        import runpy
        from unittest.mock import patch
        import girowatch_core as core
        from demo_data import demo_fixture
        fixture = demo_fixture()
        project = Path(__file__).resolve().parents[1]
        before = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sample.log').write_text(fixture['text'], encoding='utf-8')
            (root / 'girosol_profiles.json').write_text(json.dumps({'Fixture': fixture['run_profile']}))
            (root / 'order_profiles.json').write_text(json.dumps({'Fixture': fixture['order_profile']}))
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=['existing', 'Fixture', str(root / 'sample.log')]):
                    runpy.run_path(str(project / 'run_groups.py'), run_name='__main__')
                cli_runs = json.loads((root / 'results/Fixture_sample_runs.json').read_text())
                web_runs, _ = core.group_runs(fixture['text'].splitlines(), fixture['run_profile'])
                self.assertEqual(web_runs, cli_runs)
                for number, key in [('1', 'naive_bayes'), ('2', 'nearest_example'), ('3', 'linear_svm')]:
                    with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=['existing', 'Fixture', str(root / 'results/Fixture_sample_runs.json'), number, 'stop']):
                        runpy.run_path(str(project / 'order_groups.py'), run_name='__main__')
                    cli_orders = json.loads((root / f'results/Fixture_{key}_Fixture_sample_runs_orders.json').read_text())
                    self.assertEqual(core.group_orders(cli_runs, fixture['order_profile'], key, 'Fixture'), cli_orders)
            finally:
                os.chdir(before)


if __name__ == '__main__':
    unittest.main()
