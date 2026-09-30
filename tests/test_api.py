import os
import sys
import tempfile
import base64
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
os.environ['TIHO_MOCK_WG']='1'
os.environ['TIHO_SECRET']='a'*64
os.environ['WG_PUBLIC_KEY']=base64.b64encode(b'k'*32).decode()
os.environ['WG_ENDPOINT']='192.0.2.10:51820'
from fastapi.testclient import TestClient
import core
from api import app

class API(unittest.TestCase):
    def test_http_flow(self):
        with tempfile.TemporaryDirectory() as d:
            core.DB=d+'/db.sqlite'
            with TestClient(app) as client:
                self.assertEqual(client.get('/health').status_code,200)
                self.assertEqual(client.post('/v1/connect',json={}).status_code,401)
                _,code=core.issue(7)
                response=client.post('/v1/activate',json={'code':code,'public_key':base64.b64encode(b'a'*32).decode()})
                self.assertEqual(response.status_code,200)
                token=response.json()['token']
                response=client.post('/v1/connect',json={},headers={'Authorization':'Bearer '+token})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['endpoint'],'192.0.2.10:51820')
                self.assertEqual(client.post('/v1/activate',json={'code':'x','public_key':'x'}).status_code,422)
                with core.db() as c: c.execute('UPDATE accounts SET revoked=1')
                self.assertEqual(client.post('/v1/connect',json={},headers={'Authorization':'Bearer '+token}).status_code,403)
