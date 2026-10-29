import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from monitoring_service import Monitor
from web_app import perform_application_action


class RestartWorkflowTests(unittest.TestCase):
    def test_run_arms_scan_after_processing(self):
        store = Mock()
        perform_application_action(store, {'application': 'TEST CAM', 'action': 'run'})
        store.application_action.assert_called_once_with({'application': 'TEST CAM', 'action': 'run'})
        store.monitor.scan_after_run.assert_called_once_with('TEST CAM')

    def test_restart_opens_then_runs_then_arms_scan(self):
        store = Mock()
        calls = []
        store.application_action.side_effect = lambda payload: calls.append(payload['action']) or {'ok': True}
        store.monitor.scan_after_run.side_effect = lambda name: calls.append('scan-after-run')
        perform_application_action(store, {'application': 'TEST CAM', 'action': 'restart'})
        self.assertEqual(calls, ['restart', 'run', 'scan-after-run'])

    def test_failed_restart_or_run_does_not_arm_scan(self):
        for failures in ([ValueError('open failed')], [{'ok': True}, ValueError('run failed')]):
            store = Mock()
            store.application_action.side_effect = failures
            with self.assertRaises(ValueError):
                perform_application_action(store, {'application': 'TEST CAM', 'action': 'restart'})
            store.monitor.scan_after_run.assert_not_called()

    def test_scan_waits_for_running_then_waiting_even_when_automatic_is_paused(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor = Monitor(Mock(root=Path(folder)))
            states = iter(['waiting', 'unavailable', 'running', 'running', 'waiting'])
            observed = []
            def state(name):
                value = next(states)
                observed.append(value)
                return value
            with patch.object(monitor, 'application_run_state', side_effect=state), \
                 patch.object(monitor, 'request_scan') as scan, \
                 patch.object(monitor.stop_event, 'wait'), \
                 patch('monitoring_service.threading.Thread') as thread:
                monitor.scan_after_run('TEST CAM')
                thread.call_args.kwargs['target']()
            self.assertFalse(monitor.change_driven)
            self.assertEqual(observed, ['waiting', 'unavailable', 'running', 'running', 'waiting'])
            scan.assert_called_once_with({'application': 'TEST CAM'})

