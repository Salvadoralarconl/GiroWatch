import base64
from contextlib import closing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from accounts import Accounts, AccountError, match_totp, totp_code

PASSWORD = 'test-password-123'


class AccountManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.accounts = Accounts(Path(self.temp.name))
        _, self.manager = self.accounts.action({'action': 'create', 'name': 'Test Manager', 'email': 'manager@example.test', 'password': PASSWORD})
        self.accounts.action({'action': 'create', 'name': 'Test Member', 'email': 'member@example.test', 'password': PASSWORD}, self.manager)
        _, self.member = self.accounts.action({'action': 'login', 'email': 'member@example.test', 'password': PASSWORD})

    def act(self, body, cookie=''):
        return self.accounts.action(body, cookie)[0]

    def status(self, body, cookie=''):
        with self.assertRaises(AccountError) as caught:
            self.accounts.action(body, cookie)
        return caught.exception.status

    def test_first_account_is_the_manager_and_only_the_manager_manages_people(self):
        self.assertEqual(self.accounts.current_user(self.manager)['role'], 'Manager')
        member = self.accounts.current_user(self.member)
        self.assertEqual(member['role'], 'Member')
        self.assertEqual(self.status({'action': 'create', 'name': 'Blocked', 'email': 'blocked@example.test', 'password': PASSWORD}, self.member), 403)
        self.assertEqual(self.status({'action': 'people'}, self.member), 403)
        people = self.act({'action': 'people'}, self.manager)['people']
        self.assertEqual([(p['email'], p['role']) for p in people], [('manager@example.test', 'Manager'), ('member@example.test', 'Member')])
        self.assertNotIn('password_hash', people[0])

    def test_reset_signs_the_person_out_and_remove_deletes_them(self):
        member_id = self.accounts.current_user(self.member)['id']
        self.assertEqual(self.status({'action': 'reset', 'userId': member_id, 'password': 'short'}, self.manager), 400)
        self.act({'action': 'reset', 'userId': member_id, 'password': 'New-test-password-7'}, self.manager)
        self.assertIsNone(self.accounts.current_user(self.member))
        self.assertIsNotNone(self.accounts.current_user(self.manager))
        self.assertEqual(self.status({'action': 'login', 'email': 'member@example.test', 'password': PASSWORD}), 401)
        _, again = self.accounts.action({'action': 'login', 'email': 'member@example.test', 'password': 'New-test-password-7'})
        manager_id = self.accounts.current_user(self.manager)['id']
        self.assertEqual(self.status({'action': 'remove', 'userId': manager_id}, self.manager), 400)
        self.act({'action': 'remove', 'userId': member_id}, self.manager)
        self.assertIsNone(self.accounts.current_user(again))
        self.assertEqual(self.status({'action': 'remove', 'userId': member_id}, self.manager), 404)

    def test_authenticator_setup_and_two_step_recovery(self):
        self.assertEqual(self.status({'action': 'authenticator-begin', 'password': 'wrong-password'}, self.member), 401)
        begun = self.act({'action': 'authenticator-begin', 'password': PASSWORD}, self.member)
        self.assertRegex(begun['secret'], r'^[A-Z2-7]{32}$')
        self.assertTrue(begun['uri'].startswith('otpauth://totp/GiroWatch:member%40example.test?secret='))
        step = int(time.time() // 30)
        wrong = '000000' if totp_code(begun['secret'], step) != '000000' else '111111'
        self.assertEqual(self.status({'action': 'authenticator-confirm', 'code': wrong}, self.member), 400)
        self.assertTrue(self.act({'action': 'authenticator-confirm', 'code': totp_code(begun['secret'], step)}, self.member)['user']['authenticator'])
        recover = {'action': 'recover', 'email': 'member@example.test'}
        self.assertEqual(self.status({**recover, 'code': totp_code(begun['secret'], step)}), 401)
        self.assertEqual(self.status({**recover, 'email': 'nobody@example.test', 'code': totp_code(begun['secret'], step + 1)}), 401)
        token = self.act({**recover, 'code': totp_code(begun['secret'], step + 1)})['resetToken']
        self.assertIsNotNone(self.accounts.current_user(self.member))
        self.assertEqual(self.status({**recover, 'code': totp_code(begun['secret'], step + 1)}), 401)
        result, cookie = self.accounts.action({'action': 'recover-complete', 'token': token, 'password': 'Recovered-test-password-9'})
        self.assertEqual(result['user']['email'], 'member@example.test')
        self.assertIn('girowatch_session=', cookie)
        self.assertIsNone(self.accounts.current_user(self.member))
        with self.assertRaises(AccountError) as caught:
            self.accounts.action({'action': 'recover-complete', 'token': token, 'password': 'Another-test-password-1'})
        self.assertEqual((caught.exception.status, caught.exception.extra), (410, {'expired': True}))
        self.assertEqual(self.status({'action': 'authenticator-remove', 'password': PASSWORD}, cookie), 401)
        self.assertFalse(self.act({'action': 'authenticator-remove', 'password': 'Recovered-test-password-9'}, cookie)['user']['authenticator'])

    def test_recovery_is_throttled_and_expired_permissions_fail(self):
        for _ in range(5):
            self.assertEqual(self.status({'action': 'recover', 'email': 'manager@example.test', 'code': '123456'}), 401)
        self.assertEqual(self.status({'action': 'recover', 'email': 'manager@example.test', 'code': '123456'}), 429)
        with closing(sqlite3.connect(self.accounts.path)) as db, db:
            db.execute('INSERT INTO resets VALUES (?,?,?)', (self.accounts.digest('ab' * 32), 'x', time.time() - 1))
        self.assertEqual(self.status({'action': 'recover-complete', 'token': 'ab' * 32, 'password': 'Recovered-test-password-9'}), 410)

    def test_codes_match_the_rfc_example_and_accounts_from_before_roles_get_a_manager(self):
        secret = base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(totp_code(secret, 1), '287082')
        self.assertEqual(match_totp(secret, '287082', now=59), 1)
        self.assertIsNone(match_totp(secret, '287082', after=1, now=59))
        with closing(sqlite3.connect(self.accounts.path)) as db, db:
            db.execute("UPDATE users SET role='Member'")
        Accounts(Path(self.temp.name))
        self.assertEqual(self.accounts.current_user(self.manager)['role'], 'Manager')
        self.assertEqual(self.accounts.current_user(self.member)['role'], 'Member')


if __name__ == '__main__':
    unittest.main()
