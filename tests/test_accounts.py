import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from accounts import Accounts, AccountError


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.accounts = Accounts(Path(self.temp.name))

    def create(self):
        return self.accounts.action({'action':'create', 'name':'Test User', 'email':'person@example.test', 'password':'test-password-123'})

    def test_setup_persistence_and_logout(self):
        self.assertTrue(self.accounts.needs_setup())
        result, cookie = self.create()
        self.assertEqual(result['user']['name'], 'Test User')
        self.assertFalse(self.accounts.needs_setup())
        other = Accounts(Path(self.temp.name))
        self.assertEqual(other.current_user(cookie)['email'], 'person@example.test')
        self.assertNotIn('password', str(result))
        self.assertNotIn('test-password-123', self.accounts.path.read_bytes().decode(errors='ignore'))
        other.action({'action':'logout'}, cookie)
        self.assertIsNone(self.accounts.current_user(cookie))

    def test_login_and_invited_user_do_not_replace_actor_session(self):
        _, cookie = self.create()
        body={'action':'create','name':'Another','email':'another@example.test','password':'another-password'}
        with self.assertRaises(AccountError):
            self.accounts.action(body)
        _, replacement=self.accounts.action(body, cookie)
        self.assertIsNone(replacement)
        self.assertEqual(self.accounts.current_user(cookie)['name'],'Test User')
        result, login=self.accounts.action({**body,'action':'login','email':'ANOTHER@example.test'})
        self.assertEqual(self.accounts.current_user(login)['name'],'Another')

    def test_failed_logins_throttle_and_expired_sessions_are_rejected(self):
        _, cookie=self.create()
        for _ in range(5):
            with self.assertRaisesRegex(AccountError,'incorrect'):
                self.accounts.action({'action':'login','email':'person@example.test','password':'wrong'})
        with self.assertRaises(AccountError) as caught:
            self.accounts.action({'action':'login','email':'person@example.test','password':'test-password-123'})
        self.assertEqual(caught.exception.status,429)
        with patch('accounts.time.time',return_value=9999999999):
            self.assertIsNone(self.accounts.current_user(cookie))
        self.assertIsNone(self.accounts.current_user('girowatch_session=bad'))

    def test_existing_setup_cannot_be_claimed_without_login(self):
        self.create()
        with self.assertRaises(AccountError) as caught:
            self.accounts.action({'action':'create','name':'Intruder','email':'new@example.test','password':'long-password'})
        self.assertEqual(caught.exception.status,401)


class AccountHTTPTests(unittest.TestCase):
    def test_api_requires_session_and_cross_origin_creation_is_blocked(self):
        import json
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from web_service import WatchStore
        from web_app import make_handler
        with tempfile.TemporaryDirectory() as folder:
            store=WatchStore(Path(folder))
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                for path in ('/api/state','/api/search','/api/application-log?application=Cam'):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(base+path)
                    self.assertEqual(caught.exception.code,401)
                payload=json.dumps({'action':'create','name':'HTTP Test','email':'test@example.test','password':'test-password-123'}).encode()
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base+'/api/account',data=payload,headers={'Content-Type':'application/json','Origin':'https://untrusted.example'}))
                self.assertEqual(caught.exception.code,403)
                with urlopen(Request(base+'/api/account',data=payload,headers={'Content-Type':'application/json'})) as response:
                    cookie=response.headers['Set-Cookie']
                    self.assertIn('HttpOnly',cookie)
                with urlopen(Request(base+'/api/state',headers={'Cookie':cookie})) as response:
                    self.assertEqual(response.status,200)
                with urlopen(Request(base+'/api/account',data=b'{"action":"logout"}',headers={'Cookie':cookie,'Content-Type':'application/json'})):
                    pass
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base+'/api/state',headers={'Cookie':cookie}))
                self.assertEqual(caught.exception.code,401)
            finally:
                server.shutdown();server.server_close();thread.join()
