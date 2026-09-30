import base64
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
os.environ['TIHO_MOCK_WG']='1'
os.environ['TIHO_SECRET']='a'*64
os.environ['WG_PUBLIC_KEY']=base64.b64encode(b'k'*32).decode()
os.environ['WG_ENDPOINT']='192.0.2.10:51820'
import core
import billing
import bot
from fastapi.testclient import TestClient
from api import app

class Billing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        core.DB=self.tmp.name+'/test.db'
        billing.init()
        self.uid=1001
        self.key=base64.b64encode(os.urandom(32)).decode()
    def tearDown(self): self.tmp.cleanup()
    def new_order(self,plan='m1',uid=None,event=None):
        with core.db() as c: c.execute('UPDATE orders SET created=created-4')
        return billing.order(uid or self.uid,plan,event=event)
    def payment(self,oid,stars=100,charge=None):
        return {'invoice_payload':oid,'currency':'XTR','total_amount':stars,'telegram_payment_charge_id':charge or 'charge:'+oid}
    def buy(self,plan='m1',uid=None):
        uid=uid or self.uid
        oid=self.new_order(plan,uid)
        amount=billing.PLANS[plan][1]
        self.assertTrue(billing.checkout(uid,oid,'XTR',amount))
        p=self.payment(oid,amount)
        self.assertTrue(billing.settle(uid,p))
        return p
    def test_no_access_for_invoice_or_checkout(self):
        oid=self.new_order()
        self.assertIsNone(billing.access(self.uid))
        self.assertTrue(billing.checkout(self.uid,oid,'XTR',100))
        self.assertIsNone(billing.access(self.uid))
    def test_validate_checkout(self):
        oid=self.new_order()
        self.assertFalse(billing.checkout(999,oid,'XTR',100))
        self.assertFalse(billing.checkout(self.uid,oid,'RUB',100))
        self.assertFalse(billing.checkout(self.uid,oid,'XTR',1))
        with core.db() as c: c.execute('UPDATE orders SET created=0')
        self.assertFalse(billing.checkout(self.uid,oid,'XTR',100))
    def test_payment_requires_approval_and_match(self):
        oid=self.new_order()
        p=self.payment(oid)
        with self.assertRaises(ValueError): billing.settle(self.uid,p)
        billing.checkout(self.uid,oid,'XTR',100)
        with self.assertRaises(ValueError): billing.settle(99,p)
        with self.assertRaises(ValueError): billing.settle(self.uid,{**p,'total_amount':1})
        with self.assertRaises(ValueError): billing.settle(self.uid,{**p,'currency':'RUB'})
        self.assertIsNone(billing.access(self.uid))
    def test_duplicate_payment_no_extra_days(self):
        p=self.buy()
        self.assertFalse(billing.settle(self.uid,p))
        self.assertEqual(billing.access(self.uid)['days'],30)
        with core.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM payments').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM outbox WHERE kind='access'").fetchone()[0],1)
    def test_different_charge_same_order_rejected(self):
        p=self.buy()
        with self.assertRaises(ValueError): billing.settle(self.uid,{**p,'telegram_payment_charge_id':'other-charge'})
        self.assertEqual(billing.access(self.uid)['days'],30)
    def test_pre_activation_renewal(self):
        self.buy(); self.buy('m3')
        a=billing.access(self.uid)
        self.assertEqual(a['days'],120)
        self.assertIsNone(a['expires'])
        result=core.activate(a['code'],self.key)
        self.assertAlmostEqual(result['expires_at']-int(time.time()),120*86400,delta=1)
    def test_active_renewal_same_code(self):
        self.buy()
        a=billing.access(self.uid)
        expiry=core.activate(a['code'],self.key)['expires_at']
        self.buy('y1')
        b=billing.access(self.uid)
        self.assertEqual(b['expires'],expiry+365*86400)
        self.assertEqual(a['code'],b['code'])
        self.assertEqual(b['key'],self.key)
    def test_expired_renewal_from_now(self):
        self.buy()
        a=billing.access(self.uid)
        core.activate(a['code'],self.key)
        with core.db() as c: c.execute('UPDATE accounts SET expires=1')
        self.buy()
        self.assertAlmostEqual(billing.access(self.uid)['expires']-int(time.time()),30*86400,delta=1)
    def test_concurrent_device_activation(self):
        self.buy()
        code=billing.access(self.uid)['code']
        def activate(key):
            try: core.activate(code,key); return True
            except PermissionError: return False
        keys=[self.key,base64.b64encode(os.urandom(32)).decode()]
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(activate,keys))
        self.assertEqual(sum(results),1)
    def test_device_reset_old_code_token_revoked(self):
        self.buy()
        a=billing.access(self.uid)
        token=core.activate(a['code'],self.key)['token']
        old_exp=billing.access(self.uid)['expires']
        with patch.object(core,'remove') as remove:
            billing.reset_device(self.uid,'reset-event')
            remove.assert_called_once_with(self.key)
        b=billing.access(self.uid)
        self.assertNotEqual(a['code'],b['code'])
        self.assertEqual(b['expires'],old_exp)
        with self.assertRaises(PermissionError): core.connect(token)
        with self.assertRaises(PermissionError): core.activate(a['code'],self.key)
        core.activate(b['code'],base64.b64encode(os.urandom(32)).decode())
        billing.reset_device(self.uid,'reset-event') # retry is harmless
        with self.assertRaises(PermissionError): billing.reset_device(self.uid,'another-event')
    def test_reset_failure_does_not_issue_new_code(self):
        self.buy(); a=billing.access(self.uid); core.activate(a['code'],self.key)
        with patch.object(core,'remove',side_effect=RuntimeError('wg down')):
            with self.assertRaises(RuntimeError): billing.reset_device(self.uid,'reset-event')
        self.assertEqual(billing.access(self.uid)['code'],a['code'])
    def test_refund_before_activation_and_rebuy(self):
        p=self.buy(); billing.refunded(self.uid,p); billing.refunded(self.uid,p)
        a=billing.access(self.uid)
        with self.assertRaises(PermissionError): core.activate(a['code'],self.key)
        self.buy('m3')
        self.assertAlmostEqual(billing.access(self.uid)['expires']-int(time.time()),90*86400,delta=1)
    def test_refund_does_not_remove_other_purchase(self):
        p=self.buy(); self.buy('m3'); billing.refunded(self.uid,p)
        self.assertEqual(billing.access(self.uid)['days'],90)
    def test_refund_after_activation_removes_peer(self):
        p=self.buy(); a=billing.access(self.uid); core.activate(a['code'],self.key)
        with patch.object(core,'remove') as remove:
            billing.refunded(self.uid,p); remove.assert_called_once_with(self.key)
        with self.assertRaises(PermissionError): core.activate(a['code'],self.key)
    def test_refund_arrives_before_delayed_payment(self):
        oid=self.new_order();billing.checkout(self.uid,oid,'XTR',100);p=self.payment(oid)
        billing.refunded(self.uid,p);billing.settle(self.uid,p)
        with self.assertRaises(PermissionError): core.activate(billing.access(self.uid)['code'],self.key)
    def test_unknown_or_mismatched_refund(self):
        p=self.buy()
        with self.assertRaises(ValueError): billing.refunded(999,p)
        with self.assertRaises(ValueError): billing.refunded(self.uid,{**p,'total_amount':50})
        self.assertEqual(billing.access(self.uid)['days'],30)
    def test_callback_order_is_idempotent(self):
        oid=billing.order(self.uid,'m1',event='777')
        self.assertEqual(oid,billing.order(self.uid,'m1',event='777'))
        with core.db() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
    def test_raw_code_not_saved(self):
        self.buy(); a=billing.access(self.uid)
        with open(core.DB,'rb') as f: self.assertNotIn(a['code'].encode(),f.read())
    def test_bot_payment_to_android_flow(self):
        oid=self.new_order()
        query={'update_id':1,'pre_checkout_query':{'id':'query','from':{'id':self.uid},'invoice_payload':oid,'currency':'XTR','total_amount':100}}
        with patch.object(bot,'telegram',return_value=True) as tg:
            bot.checkout_update(query)
            self.assertTrue(tg.call_args.args[1]['ok'])
        p=self.payment(oid)
        u={'update_id':2,'message':{'chat':{'id':self.uid,'type':'private'},'from':{'id':self.uid},'successful_payment':p}}
        bot.handle(u); bot.handle(u)
        self.assertIn('Код доступа',bot.access_text(self.uid))
        with TestClient(app) as client:
            r=client.post('/v1/activate',json={'code':billing.access(self.uid)['code'],'public_key':self.key})
            self.assertEqual(r.status_code,200)
            token=r.json()['token']
            self.assertEqual(client.post('/v1/connect',headers={'Authorization':'Bearer '+token},json={}).status_code,200)
    def test_bot_metadata(self):
        with core.db() as c: c.execute('INSERT INTO bot_state VALUES (?,?)',('bot_username','tiho_test_bot'))
        with TestClient(app) as client:
            self.assertEqual(client.post('/v1/public',json={}).json()['bot_url'],'https://t.me/tiho_test_bot')
    def test_durable_inbox_before_telegram_ack(self):
        updates=[{'update_id':42,'message':{'text':'/buy'}},{'update_id':43,'pre_checkout_query':{'id':'q'}}]
        bot.persist_updates(updates); bot.persist_updates(updates)
        billing.init()  # Simulate restart: schema creation preserves queue.
        with core.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],2)
            self.assertEqual(c.execute("SELECT value FROM bot_state WHERE key='offset'").fetchone()[0],'44')
            self.assertEqual(c.execute('SELECT done FROM inbox WHERE update_id=43').fetchone()[0],0)
    def test_storage_error_does_not_advance_offset(self):
        bot.persist_updates([{'update_id':5}])
        with self.assertRaises(KeyError): bot.persist_updates([{'update_id':6},{}])
        with core.db() as c:
            self.assertEqual(c.execute("SELECT value FROM bot_state WHERE key='offset'").fetchone()[0],'6')
            self.assertIsNone(c.execute('SELECT * FROM inbox WHERE update_id=6').fetchone())
    def test_concurrent_payment_deliveries(self):
        oid=self.new_order(); billing.checkout(self.uid,oid,'XTR',100);p=self.payment(oid)
        with ThreadPoolExecutor(4) as pool: results=list(pool.map(lambda _: billing.settle(self.uid,p),range(4)))
        self.assertEqual(sum(results),1)
        self.assertEqual(billing.access(self.uid)['days'],30)
    def test_revoked_accounts_cannot_pay(self):
        self.buy()
        with core.db() as c: c.execute('UPDATE accounts SET revoked=1')
        with self.assertRaises(PermissionError): self.new_order()

if __name__=='__main__': unittest.main()
