import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from test_simulator import ServerTestInterface


class TimerTests(unittest.TestCase):
    def test_temporary_file_conflict_does_not_stop_timer_callbacks(self):
        with tempfile.TemporaryDirectory() as folder:
            app = object.__new__(ServerTestInterface)
            app.folder = Path(folder)
            app.name = 'TEST CAM'
            app.busy = False
            app.next_run = time.monotonic()+300
            app.display = Mock()
            app.window = Mock()
            with patch.object(Path, 'replace', side_effect=PermissionError('sharing violation')):
                app.tick()
            app.window.after.assert_called_once_with(250, app.tick)
