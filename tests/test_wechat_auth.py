"""WeChat login binds explicitly and transfers only a one-time web ticket."""

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import security


class WechatAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        keys = ('DATA_DIR', 'MYSQL_PASSWORD', 'MYSQL_PASSWORD_FILE', 'CONTAINER_RUNTIME',
                'AUTH_ENCRYPTION_KEY', 'AUTH_AUDIT_KEY', 'WECHAT_MINIPROGRAM_APPID',
                'WECHAT_MINIPROGRAM_SECRET')
        self.old_env = {key: os.environ.get(key) for key in keys}
        os.environ['DATA_DIR'] = self.temporary.name
        os.environ['CONTAINER_RUNTIME'] = 'false'
        os.environ.pop('MYSQL_PASSWORD', None)
        os.environ.pop('MYSQL_PASSWORD_FILE', None)
        os.environ['AUTH_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
        os.environ['AUTH_AUDIT_KEY'] = 'test-audit-key-with-more-than-32-characters'
        os.environ['WECHAT_MINIPROGRAM_APPID'] = 'test-appid'
        os.environ['WECHAT_MINIPROGRAM_SECRET'] = 'test-secret'
        self.old_data_dir = security.DATA_DIR
        security.DATA_DIR = Path(self.temporary.name)
        security.initialize()
        with security.connection() as c:
            c.execute('INSERT INTO users(id,username,password_hash,version,created_at,password_changed_at) VALUES(?,?,?,?,?,?)',
                      ('owner-1', 'owner', security.HASHER.hash('a-long-owner-password!'), 1, int(time.time()), int(time.time())))
        app = FastAPI()
        app.add_middleware(security.SecurityMiddleware)
        app.include_router(security.router)
        self.client = TestClient(app, base_url=security.ORIGIN)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        security.DATA_DIR = self.old_data_dir
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temporary.cleanup()

    def test_bind_then_login_and_ticket_is_one_time(self):
        with patch.object(security, 'wechat_openid', new=AsyncMock(return_value='wx-openid-1')):
            endpoint = '/api/v1/auth/wechat/exchange'
            self.assertEqual(self.client.post(endpoint, json={'code': 'first'}).json(), {'bind_required': True})
            bad = self.client.post(endpoint, json={'code': 'second', 'username': 'owner', 'password': 'wrong'})
            self.assertEqual(bad.status_code, 401)
            self.assertEqual(self.client.post(endpoint, json={'code': 'third'}).json(), {'bind_required': True})
            bound = self.client.post(endpoint, json={'code': 'fourth', 'username': 'owner',
                                                     'password': 'a-long-owner-password!'})
            self.assertEqual(bound.status_code, 200)
            ticket = bound.json()['ticket']
            self.assertNotIn('password', bound.text)
            headers = {'Origin': security.ORIGIN}
            rejected = self.client.post('/api/v1/auth/wechat/consume', json={'ticket': ticket},
                                        headers={'Origin': 'https://another.example'})
            self.assertEqual(rejected.status_code, 403)
            consume = self.client.post('/api/v1/auth/wechat/consume', json={'ticket': ticket}, headers=headers)
            self.assertEqual(consume.status_code, 200)
            self.assertEqual(consume.json()['auth_method'], 'wechat')
            self.assertLess(consume.json()['reauthenticated_until'], int(time.time()))
            self.assertIn('httponly', consume.headers['set-cookie'].lower())
            self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 200)
            replay = self.client.post('/api/v1/auth/wechat/consume', json={'ticket': ticket}, headers=headers)
            self.assertEqual(replay.status_code, 401)
            subsequent = self.client.post(endpoint, json={'code': 'fifth'})
            self.assertIn('ticket', subsequent.json())
            with security.connection() as c:
                c.execute('UPDATE users SET version=version+1 WHERE id=?', ('owner-1',))
            self.assertEqual(self.client.post(endpoint, json={'code': 'sixth'}).json(), {'bind_required': True})
            stale = self.client.post('/api/v1/auth/wechat/consume',
                                     json={'ticket': subsequent.json()['ticket']}, headers=headers)
            self.assertEqual(stale.status_code, 401)

    def test_code2session_keeps_app_secret_on_server(self):
        def handler(request):
            self.assertEqual(request.url.host, 'api.weixin.qq.com')
            self.assertEqual(request.url.params['appid'], 'test-appid')
            self.assertEqual(request.url.params['secret'], 'test-secret')
            self.assertEqual(request.url.params['js_code'], 'one-time-code')
            return httpx.Response(200, json={'openid': 'wx-openid-2', 'session_key': 'server-only'})

        client_class = httpx.AsyncClient
        with patch.object(security.httpx, 'AsyncClient',
                          side_effect=lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs)):
            self.assertEqual(asyncio.run(security.wechat_openid('one-time-code')), 'wx-openid-2')

        def invalid(_request):
            return httpx.Response(200, json={'errcode': 40029, 'errmsg': 'invalid code'})

        with patch.object(security.httpx, 'AsyncClient',
                          side_effect=lambda **kwargs: client_class(transport=httpx.MockTransport(invalid), **kwargs)):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(security.wechat_openid('used-code'))
            self.assertEqual(raised.exception.status_code, 401)

    def test_existing_password_login_keeps_recent_password_verification(self):
        response = self.client.post('/api/v1/auth/login',
                                    json={'username': 'owner', 'password': 'a-long-owner-password!'},
                                    headers={'Origin': security.ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['auth_method'], 'password')
        self.assertGreater(response.json()['reauthenticated_until'], int(time.time()))


if __name__ == '__main__':
    unittest.main()
