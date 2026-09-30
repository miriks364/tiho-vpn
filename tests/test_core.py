import base64
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
os.environ['TIHO_MOCK_WG'] = '1'
os.environ['TIHO_SECRET'] = 'a' * 64
os.environ['WG_PUBLIC_KEY'] = base64.b64encode(b'k'*32).decode()
os.environ['WG_ENDPOINT'] = '192.0.2.10:51820'
import core

class Accounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        core.DB = self.tmp.name + '/db.sqlite'
        core.init()
        self.key = base64.b64encode(os.urandom(32)).decode()
    def tearDown(self):
        self.tmp.cleanup()
    def test_activate_and_connect(self):
        _, code = core.issue(30)
        result = core.activate(code, self.key)
        self.assertEqual(core.connect(result['token'])['address'], '10.66.0.2/32')
        self.assertEqual(result, core.activate(code, self.key))
    def test_wrong_code_and_key(self):
        with self.assertRaises(PermissionError): core.activate('incorrect', self.key)
        _, code = core.issue(30)
        with self.assertRaises(ValueError): core.activate(code, 'invalid')
        core.activate(code, self.key)
        with self.assertRaises(PermissionError): core.activate(code, base64.b64encode(b'z'*32).decode())
    def test_expired_and_revoked(self):
        account, code = core.issue(1)
        token = core.activate(code, self.key)['token']
        with core.db() as c: c.execute('UPDATE accounts SET expires=? WHERE id=?', (int(time.time())-1, account))
        with self.assertRaises(PermissionError): core.connect(token)
        with self.assertRaises(PermissionError): core.activate(code, self.key)
        with core.db() as c: c.execute('UPDATE accounts SET expires=?,revoked=1 WHERE id=?', (int(time.time())+100, account))
        with self.assertRaises(PermissionError): core.connect(token)
    def test_reconcile_removes_expired(self):
        account, code = core.issue(1)
        core.activate(code, self.key)
        with core.db() as c: c.execute('UPDATE accounts SET expires=1 WHERE id=?', (account,))
        with patch.object(core, 'wg', return_value=self.key+'\n'), patch.object(core, 'remove') as remove:
            core.reconcile(); remove.assert_called_once_with(self.key)
    def test_limits(self):
        for _ in range(12): self.assertTrue(core.rate_limit('1.2.3.4'))
        self.assertFalse(core.rate_limit('1.2.3.4'))
        self.assertTrue(core.rate_limit('2.3.4.5'))
    def test_hashes_only(self):
        _, code = core.issue(1)
        token = core.activate(code, self.key)['token']
        with open(core.DB, 'rb') as f: data = f.read()
        self.assertNotIn(code.encode(), data); self.assertNotIn(token.encode(), data)
    def test_unique_device(self):
        _, a = core.issue(1); _, b = core.issue(1)
        core.activate(a, self.key)
        with self.assertRaises(PermissionError): core.activate(b, self.key)
    def test_unknown_token(self):
        with self.assertRaises(PermissionError): core.connect('bad')

if __name__ == '__main__': unittest.main()
