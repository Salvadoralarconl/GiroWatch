import unittest
from simulated_workload import build_run_events


class WorkloadTests(unittest.TestCase):
    def test_live_batch_stays_between_fifty_and_sixty_log_lines(self):
        from simulated_workload import build_live_run_events
        for outcome in ('Stable', 'Warning', 'Error'):
            events = build_live_run_events('TEST CAM', outcome, 'TESTBATCH')
            self.assertGreaterEqual(len(events), 50)
            self.assertLessEqual(len(events), 60)

    def test_batch_has_multiple_orders_and_balanced_boundaries(self):
        events = build_run_events('TEST CAM', 12, 'Stable', 'TESTBATCH')
        messages = [message for message, _ in events]
        self.assertGreater(len(events), 150)
        self.assertEqual(sum('ORDER START:' in m for m in messages), 12)
        self.assertEqual(sum('ORDER END:' in m for m in messages), 12)
        self.assertEqual(sum('SIMULATED ORDER SUCCESS' in m for m in messages), 12)
        self.assertIn('completed=12 failed=0', messages[-4])
        self.assertIn('BEGIN PROCESS', messages[0])
        self.assertIn('END PROCESS', messages[-1])
        self.assertTrue(all(level == 'INFO' for _, level in events))

    def test_error_is_limited_to_one_order_in_batch(self):
        events = build_run_events('TEST CAM', 20, 'Error', 'TESTBATCH')
        self.assertEqual(sum(level == 'ERROR' for _, level in events), 1)
        self.assertEqual(sum('SIMULATED ORDER SUCCESS' in message for message, _ in events), 19)
        self.assertTrue(any('completed=19 failed=1' in message for message, _ in events))

    def test_monitoring_treats_the_entire_batch_as_one_run(self):
        import tempfile
        from local_test_mode import LocalTestStore
        from monitoring_service import classifier_for, classify_lines
        with tempfile.TemporaryDirectory() as root:
            store = LocalTestStore(root)
            lines = [message for message, _ in build_run_events('TEST CAM', 12, 'Stable', 'TESTBATCH')]
            labels = classify_lines(lines, classifier_for(store.profiles()[0]['TEST CAM']))
            self.assertEqual([i for i, label in enumerate(labels) if label == 'Run_Start'], [0])
            self.assertEqual([i for i, label in enumerate(labels) if label == 'Run_End'], [len(lines)-1])
