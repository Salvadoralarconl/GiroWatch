r"""Run the local website: .\.venv\Scripts\python.exe web_app.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from web_service import WatchStore
from application_control import application_action

ROOT = Path(__file__).resolve().parent


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {'error': 'Use the local GiroWatch address.'})
            path = urlparse(self.path).path
            try:
                if getattr(store, 'local_test_mode', False):
                    from local_test_mode import allow_test_request
                    allow_test_request('GET', path)
                if path == '/api/state':
                    return self.send(200, store.state())
                if path == '/api/contacts':
                    return self.send(200, store.contacts())
                if path == '/api/monitoring':
                    return self.send(200, store.monitor.status())
                if path == '/api/application-log':
                    query = parse_qs(urlparse(self.path).query)
                    return self.send(200, store.application_log(query.get('application', [''])[0]))
                if path == '/api/home-errors':
                    query = parse_qs(urlparse(self.path).query)
                    return self.send(200, store.home_errors.results(query.get('id', [''])[0]))
                if path == '/api/home-stats':
                    return self.send(200, store.run_stats.results())
                if path == '/api/profile':
                    query = parse_qs(urlparse(self.path).query)
                    return self.send(200, store.profile(query.get('section', [''])[0], query.get('application', [''])[0]))
                if path == '/api/search':
                    query = parse_qs(urlparse(self.path).query)
                    return self.send(200, store.search(query.get('q', [''])[0], query.get('application', [''])[0], query.get('offset', ['0'])[0], query.get('start', [''])[0], query.get('end', [''])[0]))
                # Explicit asset list: profile files and arbitrary paths are never served.
                assets = {'/': ('design.html', 'text/html'), '/design.js': ('design.js', 'text/javascript'),
                          '/design.css': ('design.css', 'text/css')}
                if path in assets:
                    filename, kind = assets[path]
                    return self.send(200, (ROOT / 'web' / filename).read_bytes(), kind + '; charset=utf-8')
                if re.fullmatch(r'/assets/[A-Za-z0-9_-]+\.png', path):
                    asset = ROOT / 'web' / 'assets' / path.rsplit('/', 1)[1]
                    if asset.is_file():
                        return self.send(200, asset.read_bytes(), 'image/png')
                return self.send(404, {'error': 'Not found.'})
            except (ValueError, OSError) as error:
                return self.send(400, {'error': str(error)})

        def do_POST(self):
            # JSON-only and same-origin. Local log contents never leave this machine.
            origin = self.headers.get('Origin')
            if not self.allowed_host() or (origin and origin != f"http://{self.headers.get('Host')}"):
                return self.send(403, {'error': 'Only the local GiroWatch page can make changes.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'Send JSON.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 25 * 1024 * 1024:
                    return self.send(413, {'error': 'Choose a file smaller than 25 MB.'})
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object.')
                if getattr(store, 'local_test_mode', False):
                    from local_test_mode import allow_test_request
                    allow_test_request('POST', urlparse(self.path).path)
                routes = {'/api/configure': store.configure, '/api/test-configuration': store.test_configuration,
                          '/api/application-action': getattr(store, 'application_action', application_action),
                          '/api/contacts': store.contacts,
                          '/api/home-error-status': store.home_errors.set_status,
                          '/api/monitoring-scan': store.monitor.request_scan,
                          '/api/monitoring-settings': store.monitor.configure_scanning,
                          '/api/folder-profile': store.folder_profile,
                          '/api/scan': store.scan, '/api/demo': lambda _: store.demo(), '/api/alert': store.set_alert}
                route = routes.get(urlparse(self.path).path)
                if not route:
                    return self.send(404, {'error': 'Not found.'})
                return self.send(200, route(payload))
            except (ValueError, OSError, TypeError, KeyError) as error:
                return self.send(400, {'error': str(error)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description='GiroWatch local browser interface')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--local-test', action='store_true', help='Use fictional applications with server access and application controls blocked')
    parser.add_argument('--test-windows', action='store_true', help='Open desktop simulators (requires --local-test)')
    args = parser.parse_args()
    if args.test_windows and not args.local_test:
        parser.error('--test-windows requires --local-test')
    if args.local_test:
        import tempfile
        from local_test_mode import LocalTestStore
        test_session = tempfile.TemporaryDirectory(prefix='girowatch-local-test-')
        store = LocalTestStore(Path(test_session.name))
    else:
        store = WatchStore(ROOT)
        store.monitor.restore_settings()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(store))
    if args.local_test and args.test_windows:
        store.open_simulators()
    if not args.local_test:
        store.monitor.start()
    print(f'GiroWatch is ready at http://127.0.0.1:{args.port}', flush=True)
    print('LOCAL TEST MODE: only local TEST simulators and logs; production access blocked.' if args.local_test else 'Scanning controls are available in Settings. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.monitor.stop()
        server.server_close()
        if args.local_test:
            store.close()
            test_session.cleanup()


if __name__ == '__main__':
    main()
