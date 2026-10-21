import unittest
from application_control import parse_live_display


class LiveTimerTests(unittest.TestCase):
    def test_waiting_countdown_is_read_not_predicted(self):
        self.assertEqual(parse_live_display('CAM, waiting 00:09:24'),{'state':'waiting','seconds':564})

    def test_running_display(self):
        self.assertEqual(parse_live_display('INTERFACE RUNNING!'),{'state':'running'})

    def test_unrecognized_or_malformed_display(self):
        self.assertEqual(parse_live_display('CAM, waiting 00:99:00'),{'state':'unavailable'})
        self.assertEqual(parse_live_display(''),{'state':'unavailable'})
