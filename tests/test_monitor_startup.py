import unittest
from unittest.mock import Mock, patch
import web_app

class StartupTests(unittest.TestCase):
    def test_local_test_starts_monitor_without_opening_windows(self):
        store = Mock()
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        with patch('sys.argv', ['web_app.py', '--local-test']), \
             patch('local_test_mode.LocalTestStore', return_value=store), \
             patch('web_app.Accounts'), \
             patch('web_app.ThreadingHTTPServer', return_value=server):
            web_app.main()
        store.monitor.start.assert_called_once_with()
        store.open_simulators.assert_not_called()
        store.close.assert_called_once_with()
