import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from test_interface import write_event


class InterfaceLogTests(unittest.TestCase):
    def test_daily_log_appends_and_closes_each_write(self):
        with tempfile.TemporaryDirectory() as root:
            stamp = datetime(2026, 10, 21, 11, 30, 0)
            path = write_event(Path(root), 'BEGIN PROCESS', stamp)
            write_event(Path(root), 'END PROCESS', stamp)
            self.assertEqual(path.name, '20261021.log')
            self.assertEqual(len(path.read_text().splitlines()), 2)
            self.assertIn('10/21/2026 11:30:00 AM INFO', path.read_text())
            moved = path.with_suffix('.closed')
            path.rename(moved)
            self.assertTrue(moved.exists())
