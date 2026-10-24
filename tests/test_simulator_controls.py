import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simulator_controls import SimulatorControls, TEST_APPS
from test_simulator import scheduled_outcome


class SimulatorTests(unittest.TestCase):
    def test_one_error_per_ten_minutes_and_next_run_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertTrue(all(scheduled_outcome(root,name,0)=='Stable' for name in TEST_APPS))
            self.assertTrue(all(scheduled_outcome(root,name,599)=='Stable' for name in TEST_APPS))
            first=[scheduled_outcome(root,name,600) for name in TEST_APPS]
            self.assertEqual(first,['Error','Stable','Stable','Stable'])
            self.assertTrue(all(scheduled_outcome(root,name,900)=='Stable' for name in TEST_APPS))
            second=[scheduled_outcome(root,name,1200) for name in TEST_APPS]
            self.assertEqual(second,['Stable','Error','Stable','Stable'])

    def test_rejects_production_names_and_unrecognized_actions_without_launch(self):
        with tempfile.TemporaryDirectory() as folder, patch('simulator_controls.subprocess.Popen') as launch:
            controls = SimulatorControls(Path(folder))
            for name, action in [('Cam', 'restart'), ('UNITELLER', 'run'), ('../TEST CAM', 'run'), ('TEST CAM', 'delete')]:
                with self.assertRaises(ValueError):
                    controls.action({'application': name, 'action': action})
            launch.assert_not_called()

    @patch.object(SimulatorControls, '_wait_for_window')
    def test_only_owned_test_process_is_launched_and_command_is_local(self, ready):
        with tempfile.TemporaryDirectory() as folder, patch('simulator_controls.subprocess.Popen') as launch:
            launch.return_value.poll.return_value = None
            controls = SimulatorControls(Path(folder))
            controls.action({'application': TEST_APPS[0], 'action': 'restart'})
            controls.action({'application': TEST_APPS[0], 'action': 'run'})
            self.assertEqual(launch.call_count, 1)
            self.assertIn('test_simulator.py', launch.call_args.args[0][1])
            self.assertTrue((Path(folder) / TEST_APPS[0] / 'run.request').exists())

    @patch.object(SimulatorControls, '_wait_for_window')
    def test_launch_tracks_interpreter_instead_of_windows_venv_redirector(self, ready):
        with tempfile.TemporaryDirectory() as folder, patch('simulator_controls.subprocess.Popen') as launch:
            launch.return_value.poll.return_value = None
            with patch('simulator_controls.sys.platform', 'win32'), patch('simulator_controls.sys._base_executable', 'C:/Python/python.exe', create=True):
                SimulatorControls(folder).action({'application': TEST_APPS[0], 'action': 'restart'})
            self.assertEqual(launch.call_args.args[0][0], 'C:/Python/python.exe')

    def test_restart_reports_startup_crash_instead_of_success(self):
        with tempfile.TemporaryDirectory() as folder, patch('simulator_controls.subprocess.Popen') as launch:
            launch.return_value.poll.return_value = 1
            with self.assertRaisesRegex(ValueError, 'could not open'):
                SimulatorControls(folder).action({'application': TEST_APPS[0], 'action': 'restart'})
