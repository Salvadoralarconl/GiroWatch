import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from web_service import WatchStore
from web_app import make_handler


class LoadFailureAssetTests(unittest.TestCase):
    def test_couldnt_load_screen_files_are_served_without_signing_in(self):
        # The screen must load even when the session is gone or the server is failing.
        with tempfile.TemporaryDirectory() as folder:
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(WatchStore(Path(folder))))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for path, kind, text in (('/load-failure.js?v=1', 'text/javascript', 'This page couldn’t load'),
                                         ('/load-failure.css?v=1', 'text/css', '#load-failure'),
                                         ('/offline.html', 'text/html', 'data-load-failure'),
                                         ('/sw.js', 'text/javascript', "caches.match('/offline.html')")):
                    with urlopen(base + path) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.headers['Content-Type'].startswith(kind))
                        self.assertIn(text, response.read().decode('utf-8'))
                with urlopen(base + '/') as response:
                    page = response.read().decode('utf-8')
                self.assertLess(page.index('/load-failure.js'), page.index('/account.js'))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
