"""Single-owner authentication: revocable sessions, Argon2id and CSRF.

Account creation/recovery is deliberately restricted to the local management CLI.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from app.mysql_db import connect as mysql_connect
from starlette.middleware.base import BaseHTTPMiddleware

DATA_DIR = Path(os.getenv('DATA_DIR', Path(__file__).resolve().parent.parent / 'data')).resolve()
ORIGIN = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
SECURE = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
COOKIE = '__Host-finch_session' if SECURE else 'finch_session'
TTL = min(28800, max(600, int(os.getenv('SESSION_TTL_SECONDS', '28800'))))
IDLE = min(1800, max(300, int(os.getenv('SESSION_IDLE_SECONDS', '1200'))))
CAPABILITIES = ['market.read', 'research.use', 'documents.manage', 'portfolio.read', 'portfolio.write', 'paper.trade', 'security.manage']
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY = HASHER.hash(secrets.token_urlsafe(32))
router = APIRouter(prefix='/api/v1/auth', tags=['identity'])
_current_owner = ContextVar('finch_owner', default=None)


def current_owner_id():
    owner = _current_owner.get()
    if not owner:
        fail('AUTH_REQUIRED', '请先登录。', 401)
    return owner


def primary_owner_id():
    with connection() as c:
        row = c.execute('SELECT id FROM users ORDER BY created_at,id LIMIT 1').fetchone()
    return row['id'] if row else None



def fail(code: str, message: str, status: int = 400):
    raise HTTPException(status, {'code': code, 'message': message})


@contextmanager
def connection():
    with mysql_connect('identity') as c:
        yield c


def cipher() -> Fernet:
    try:
        return Fernet(os.environ['AUTH_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError):
        raise RuntimeError('请先运行 scripts/configure-local.py 生成本机安全配置') from None


def initialize():
    parts = urlsplit(ORIGIN)
    if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.path or parts.username or parts.password:
        raise RuntimeError('APP_ORIGIN 必须是完整的应用源，不含路径或凭据')
    if parts.hostname not in {'127.0.0.1', 'localhost', '::1'} and (parts.scheme != 'https' or not SECURE):
        raise RuntimeError('非回环部署必须使用 HTTPS APP_ORIGIN 与 SESSION_COOKIE_SECURE=true')
    if SECURE != (parts.scheme == 'https'):
        raise RuntimeError('SESSION_COOKIE_SECURE 必须与 APP_ORIGIN 的 HTTPS 模式一致')
    container_loopback = os.getenv('APP_CONTAINER_LOOPBACK_ONLY') == 'true' and parts.hostname in {'127.0.0.1', 'localhost', '::1'}
    if os.getenv('HOST', '127.0.0.1') not in {'127.0.0.1', 'localhost', '::1'} and not SECURE and not container_loopback:
        raise RuntimeError('非回环监听必须配置 HTTPS 与安全 Cookie')
    cipher()
    if len(os.getenv('AUTH_AUDIT_KEY', '')) < 32:
        raise RuntimeError('缺少 AUTH_AUDIT_KEY；请运行本地配置脚本')
    with connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          totp_secret TEXT, last_totp_step INTEGER NOT NULL DEFAULT -1, version INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL, password_changed_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
          digest TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), csrf TEXT NOT NULL,
          created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, last_seen INTEGER NOT NULL,
          version INTEGER NOT NULL, mfa_verified INTEGER NOT NULL, reauth_at INTEGER NOT NULL DEFAULT 0,
          pending_totp TEXT, pending_at INTEGER, device TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recovery_codes (
          user_id TEXT REFERENCES users(id), digest TEXT NOT NULL UNIQUE, used_at INTEGER);
        CREATE TABLE IF NOT EXISTS auth_limits (key TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS wechat_bindings (
          openid_digest TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
          bound_version INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS wechat_tickets (
          digest TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id),
          user_version INTEGER NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at INTEGER NOT NULL, actor TEXT,
          action TEXT NOT NULL, target TEXT NOT NULL, prev_hash TEXT NOT NULL, signature TEXT NOT NULL);
        ''')
        c.execute('CREATE TABLE IF NOT EXISTS auth_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        columns={r['name'] for r in c.execute('PRAGMA table_info(sessions)')}
        if 'auth_method' not in columns:
            c.execute("ALTER TABLE sessions ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'legacy'")
        binding_columns = {r['name'] for r in c.execute('PRAGMA table_info(wechat_bindings)')}
        if 'bound_version' not in binding_columns:
            c.execute('ALTER TABLE wechat_bindings ADD COLUMN bound_version INTEGER NOT NULL DEFAULT 0')
        ticket_columns = {r['name'] for r in c.execute('PRAGMA table_info(wechat_tickets)')}
        if 'user_version' not in ticket_columns:
            c.execute('ALTER TABLE wechat_tickets ADD COLUMN user_version INTEGER NOT NULL DEFAULT 0')
        policy='password-only-v2'
        previous=c.execute("SELECT value FROM auth_metadata WHERE key='login_policy'").fetchone()
        if not previous or previous['value']!=policy:
            c.execute('DELETE FROM sessions')
            c.execute("INSERT OR REPLACE INTO auth_metadata VALUES('login_policy',?)",(policy,))
            audit(c,None,'auth.policy_migrated','password_only')
        c.execute('DELETE FROM sessions WHERE expires_at<?', (int(time.time()),))
    os.chmod(DATA_DIR, 0o700)


def audit(c, actor: str | None, action: str, target: str = ''):
    now = int(time.time())
    if not c.in_transaction:
        c.execute('BEGIN IMMEDIATE')
    previous = c.execute('SELECT signature FROM audit ORDER BY id DESC LIMIT 1').fetchone()
    prev = previous['signature'] if previous else ''
    body = json.dumps([now, actor, action, target, prev], separators=(',', ':'), ensure_ascii=False)
    signature = hmac.new(os.environ['AUTH_AUDIT_KEY'].encode(), body.encode(), hashlib.sha256).hexdigest()
    c.execute('INSERT INTO audit(occurred_at,actor,action,target,prev_hash,signature) VALUES(?,?,?,?,?,?)',
              (now, actor, action, target, prev, signature))


def rate_limit(request: Request, operation: str, username: str = ''):
    ip = request.client.host if request.client else 'unknown'
    now = int(time.time())
    keys = [(f'{operation}:ip:{ip}', 30)]
    if username:
        keys.append((f'{operation}:user:{username.casefold()}', 12))
    limited = False
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        for identity, maximum in keys:
            key = hashlib.sha256(identity.encode()).hexdigest()
            row = c.execute('SELECT * FROM auth_limits WHERE key=?', (key,)).fetchone()
            count = row['count'] + 1 if row and now - row['window'] < 900 else 1
            window = row['window'] if row and now - row['window'] < 900 else now
            c.execute('INSERT OR REPLACE INTO auth_limits VALUES(?,?,?)', (key, window, count))
            limited |= count > maximum
        c.execute('DELETE FROM auth_limits WHERE window<?', (now - 86400,))
        if limited:
            audit(c, None, 'auth.rate_limited', operation)
    if limited:
        fail('AUTH_RATE_LIMITED', '尝试次数过多，请 15 分钟后重试。', 429)


def origin_check(request: Request):
    if request.headers.get('origin') != ORIGIN or request.headers.get('sec-fetch-site') == 'cross-site':
        fail('CSRF_FAILED', '请求来源无效，请从应用页面重新操作。', 403)


def check_password(encoded, password):
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(value: str):
    if not 14 <= len(value) <= 256 or len(set(value)) < 4 or value.casefold() in {'passwordpassword','12345678901234','1234567890123456','qwertyuiopasdfgh'}:
        fail('PASSWORD_POLICY', '请使用 14–256 个字符的独立密码，建议使用密码管理器生成。', 422)


def login_policy():
    return 'password'


def describe(user, session):
    return {'user': {'id': user['id'], 'username': user['username'], 'role': 'owner'},
            'capabilities': CAPABILITIES if session['mfa_verified'] else [],
            'mfa_enabled':False,'setup_required':False,
            'login_verification':login_policy(),'auth_method':session.get('auth_method','password') if isinstance(session,dict) else session['auth_method'],
            'csrf_token':session['csrf'],'expires_at':session['expires_at'],
            'idle_seconds':IDLE,'reauthenticated_until':session['reauth_at']+300}


def authenticate(request: Request):
    raw = request.cookies.get(COOKIE, '')
    digest = hashlib.sha256(raw.encode()).hexdigest()
    now = int(time.time())
    with connection() as c:
        s = c.execute('SELECT * FROM sessions WHERE digest=?', (digest,)).fetchone()
        u = c.execute('SELECT * FROM users WHERE id=?', (s['user_id'],)).fetchone() if s else None
        if not s or not u or s['expires_at'] <= now or now - s['last_seen'] > IDLE or s['version'] != u['version']:
            if s:
                c.execute('DELETE FROM sessions WHERE digest=?', (digest,))
            fail('SESSION_EXPIRED', '会话已结束，请登录后继续。', 401)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin_check(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode(), s['csrf'].encode()):
                fail('CSRF_FAILED', '验证已过期，请刷新页面。', 403)
        # Background polling does not extend the idle window.
        if request.headers.get('x-finch-active') == '1':
            c.execute('UPDATE sessions SET last_seen=? WHERE digest=?', (now, digest))
    request.state.identity, request.state.session = dict(u), dict(s)
    return dict(u), dict(s)


def rotate_session(c, user, session, response):
    """Rotate the bearer and CSRF token after password reauthentication."""
    now = int(time.time())
    if session['expires_at'] <= now or now - session['last_seen'] > IDLE:
        fail('SESSION_EXPIRED', '会话已结束，请重新登录。', 401)
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    c.execute('DELETE FROM sessions WHERE digest=?', (session['digest'],))
    c.execute('INSERT INTO sessions(digest,user_id,csrf,created_at,expires_at,last_seen,version,mfa_verified,reauth_at,device,auth_method) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (digest,user['id'],csrf,session['created_at'],session['expires_at'],now,user['version'],1,now,session['device'],session.get('auth_method','password') if isinstance(session,dict) else session['auth_method']))
    response.set_cookie(COOKIE,raw,max_age=session['expires_at']-now,httponly=True,secure=SECURE,samesite='strict',path='/')
    return c.execute('SELECT * FROM sessions WHERE digest=?',(digest,)).fetchone()


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class Reauth(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(Reauth):
    new_password: str = Field(min_length=14, max_length=256)


class WechatExchange(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    username: str | None = Field(default=None, max_length=80)
    password: str | None = Field(default=None, max_length=256)


class WechatTicket(BaseModel):
    ticket: str = Field(min_length=32, max_length=128)


async def wechat_openid(code: str) -> str:
    appid = os.getenv('WECHAT_MINIPROGRAM_APPID', '').strip()
    secret = os.getenv('WECHAT_MINIPROGRAM_SECRET', '').strip()
    if not appid or not secret:
        fail('WECHAT_NOT_CONFIGURED', '服务端尚未配置微信小程序登录。', 503)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            result = await client.get('https://api.weixin.qq.com/sns/jscode2session', params={
                'appid': appid, 'secret': secret, 'js_code': code, 'grant_type': 'authorization_code',
            })
            result.raise_for_status()
            payload = result.json()
    except (httpx.HTTPError, ValueError):
        fail('WECHAT_UNAVAILABLE', '微信身份校验暂时不可用，请稍后重试。', 502)
    openid = payload.get('openid') if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get('errcode') or not isinstance(openid, str) or not openid:
        fail('WECHAT_CODE_INVALID', '微信登录凭证已失效，请重试。', 401)
    return openid


def wechat_openid_digest(openid: str) -> str:
    return hmac.new(os.environ['AUTH_AUDIT_KEY'].encode(),
                    ('wechat-openid:' + openid).encode(), hashlib.sha256).hexdigest()


@router.post('/wechat/exchange')
async def wechat_exchange(body: WechatExchange, request: Request):
    if 'application/json' not in request.headers.get('content-type', ''):
        fail('JSON_REQUIRED', '请使用JSON请求。', 415)
    origin = request.headers.get('origin')
    if (origin and origin != ORIGIN) or request.headers.get('sec-fetch-site') == 'cross-site':
        fail('CSRF_FAILED', '请求来源无效。', 403)
    rate_limit(request, 'wechat_exchange', body.username or '')
    digest = wechat_openid_digest(await wechat_openid(body.code))
    with connection() as c:
        binding = c.execute('SELECT b.user_id,b.bound_version,u.version FROM wechat_bindings b '
                            'LEFT JOIN users u ON u.id=b.user_id WHERE b.openid_digest=?', (digest,)).fetchone()
    if not binding or binding['version'] != binding['bound_version']:
        if not body.username or not body.password:
            return {'bind_required': True}
        username = body.username.strip().casefold()
        rate_limit(request, 'wechat_bind', username)
        with connection() as c:
            user = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        valid = await asyncio.to_thread(check_password, user['password_hash'] if user else DUMMY, body.password)
        if not user or not valid:
            with connection() as c:
                audit(c, None, 'auth.wechat_bind_failed')
            fail('AUTH_INVALID', '账号或密码不正确。', 401)
        with connection() as c:
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            if not current or current['password_hash'] != user['password_hash']:
                fail('AUTH_INVALID', '账户状态已变更，请重新验证。', 401)
            c.execute('INSERT OR IGNORE INTO wechat_bindings(openid_digest,user_id,bound_version,created_at) VALUES(?,?,?,?)',
                      (digest, current['id'], current['version'], int(time.time())))
            binding = c.execute('SELECT user_id FROM wechat_bindings WHERE openid_digest=?', (digest,)).fetchone()
            if binding['user_id'] != current['id']:
                fail('WECHAT_BOUND', '该微信身份已绑定其他账户。', 409)
            c.execute('UPDATE wechat_bindings SET bound_version=? WHERE openid_digest=?', (current['version'], digest))
            audit(c, current['id'], 'auth.wechat_bound')
    ticket = secrets.token_urlsafe(32)
    now = int(time.time())
    with connection() as c:
        current_binding = c.execute('SELECT b.user_id,b.bound_version,u.version FROM wechat_bindings b '
                                    'LEFT JOIN users u ON u.id=b.user_id WHERE b.openid_digest=?', (digest,)).fetchone()
        if not current_binding or current_binding['version'] != current_binding['bound_version']:
            fail('WECHAT_BIND_REQUIRED', '账户状态已变更，请重新绑定。', 409)
        c.execute('DELETE FROM wechat_tickets WHERE expires_at<?', (now,))
        c.execute('INSERT INTO wechat_tickets(digest,user_id,user_version,expires_at) VALUES(?,?,?,?)',
                  (hashlib.sha256(ticket.encode()).hexdigest(), current_binding['user_id'],
                   current_binding['version'], now + 60))
    return {'ticket': ticket, 'expires_in': 60}


@router.get('/wechat/entry', response_class=HTMLResponse)
def wechat_entry():
    return HTMLResponse('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>正在登录 Finch</title>
<link rel="stylesheet" href="/assets/wechat-entry.css"></head><body>
<main><div class="mark">✦</div><h1>正在进入私人工作台</h1><p id="state" role="status">正在建立安全会话…</p></main>
<script src="/assets/wechat-entry.js" defer></script></body></html>''')


@router.post('/wechat/consume')
def wechat_consume(body: WechatTicket, request: Request, response: Response):
    public_json(request)
    digest = hashlib.sha256(body.ticket.encode()).hexdigest()
    now = int(time.time())
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        ticket = c.execute('SELECT user_id,user_version,expires_at FROM wechat_tickets WHERE digest=?', (digest,)).fetchone()
        if not ticket or ticket['expires_at'] <= now:
            fail('WECHAT_TICKET_INVALID', '登录凭证已失效，请返回小程序重试。', 401)
        removed = c.execute('DELETE FROM wechat_tickets WHERE digest=?', (digest,))
        if removed.rowcount != 1:
            fail('WECHAT_TICKET_INVALID', '登录凭证已使用，请返回小程序重试。', 401)
        user = c.execute('SELECT * FROM users WHERE id=?', (ticket['user_id'],)).fetchone()
        if not user or user['version'] != ticket['user_version']:
            fail('AUTH_INVALID', '账户状态已变更，请返回小程序重试。', 401)
        identity = finish_login(c, user, request, response, 'wechat')
    return identity


def finish_login(c,user,request,response,method):
    current=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
    if not current or current['version']!=user['version']:
        fail('AUTH_INVALID','账户状态已变更，请重新登录。',401)
    now=int(time.time());raw=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    old=hashlib.sha256(request.cookies.get(COOKIE,'').encode()).hexdigest()
    c.execute('DELETE FROM sessions WHERE digest=? OR expires_at<?',(old,now))
    c.execute('INSERT INTO sessions(digest,user_id,csrf,created_at,expires_at,last_seen,version,mfa_verified,reauth_at,device,auth_method) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (digest,user['id'],csrf,now,now+TTL,now,user['version'],1,now if method == 'password' else 0,
               request.headers.get('user-agent','')[:160],method))
    audit(c,user['id'],'auth.login',method)
    response.set_cookie(COOKIE,raw,max_age=TTL,httponly=True,secure=SECURE,samesite='strict',path='/')
    return describe(current,c.execute('SELECT * FROM sessions WHERE digest=?',(digest,)).fetchone())


def public_json(request):
    origin_check(request)
    if 'application/json' not in request.headers.get('content-type',''):
        fail('JSON_REQUIRED','请使用JSON请求。',415)


@router.get('/status')
def status():
    with connection() as c:
        initialized=bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    return {'initialized':initialized,'registration':'closed','mfa_required':False,
            'login_verification':login_policy(),'password_only_trading':True}


@router.post('/login')
async def login(body: Credentials, request: Request, response: Response):
    public_json(request)
    username=body.username.strip().casefold();rate_limit(request,'login',username)
    with connection() as c:
        user=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
    valid=await asyncio.to_thread(check_password,user['password_hash'] if user else DUMMY,body.password)
    if not user or not valid:
        with connection() as c:audit(c,None,'auth.login_failed')
        fail('AUTH_INVALID','账号或密码不正确。',401)
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
        if not current or current['password_hash']!=user['password_hash']:
            fail('AUTH_INVALID','账号或密码不正确。',401)
        return finish_login(c,current,request,response,'password')


@router.get('/me')
def me(request: Request):
    return describe(request.state.identity, request.state.session)


@router.post('/logout')
def logout(request: Request, response: Response):
    with connection() as c:
        c.execute('DELETE FROM sessions WHERE digest=?', (request.state.session['digest'],))
        audit(c, request.state.identity['id'], 'auth.logout')
    response.delete_cookie(COOKIE, path='/', secure=SECURE, httponly=True, samesite='strict')
    return {'status': 'signed_out'}


@router.post('/reauth')
async def reauthenticate(body: Reauth, request: Request, response: Response):
    user = request.state.identity
    rate_limit(request, 'reauth', user['username'])
    valid = await asyncio.to_thread(check_password, user['password_hash'], body.password)
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        u = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        valid = valid and u is not None and u['password_hash'] == user['password_hash']
        if valid:
            renewed=rotate_session(c,u,request.state.session,response)
            identity=describe(u,renewed)
            audit(c, user['id'], 'auth.reauthenticated')
        else:
            audit(c, user['id'], 'auth.reauth_failed')
    if not valid:
        fail('AUTH_INVALID', '密码不正确。', 401)
    return {'status': 'verified', 'valid_for': 300,'identity':identity}


@router.get('/sessions')
def sessions(request: Request):
    with connection() as c:
        rows = c.execute('SELECT digest,created_at,expires_at,last_seen,device FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC', (request.state.identity['id'], int(time.time()))).fetchall()
    return [{'id': r['digest'], 'current': r['digest'] == request.state.session['digest'], **{k: r[k] for k in ('created_at', 'expires_at', 'last_seen', 'device')}} for r in rows]


@router.delete('/sessions/{session_id}')
def revoke_session(session_id: str, request: Request):
    if session_id=='current':
        session_id=request.state.session['digest']
    with connection() as c:
        c.execute('DELETE FROM sessions WHERE digest=? AND user_id=?', (session_id, request.state.identity['id']))
        audit(c, request.state.identity['id'], 'auth.session_revoked', session_id[:12])
    return {'status': 'revoked', 'current': session_id == request.state.session['digest']}


@router.get('/audit')
def audit_log(request: Request):
    with connection() as c:
        rows = c.execute('SELECT id,occurred_at,action,target FROM audit ORDER BY id DESC LIMIT 100').fetchall()
    return {'events': [dict(row) for row in rows], 'integrity': 'HMAC-SHA256 chained; verify with local management CLI'}


@router.post('/password')
async def change_password(body: PasswordChange, request: Request, response: Response):
    user = request.state.identity
    rate_limit(request, 'password', user['username'])
    validate_password(body.new_password)
    if body.new_password == body.password:
        fail('PASSWORD_POLICY', '新密码需与当前密码不同。', 422)
    valid = await asyncio.to_thread(check_password, user['password_hash'], body.password)
    new_hash = await asyncio.to_thread(HASHER.hash, body.new_password)
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        u = c.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        valid = valid and u is not None and u['password_hash'] == user['password_hash']
        if valid:
            c.execute('UPDATE users SET password_hash=?,password_changed_at=?,version=version+1 WHERE id=?', (new_hash, int(time.time()), user['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            audit(c, user['id'], 'auth.password_changed')
    if not valid:
        fail('AUTH_INVALID', '密码不正确。', 401)
    response.delete_cookie(COOKIE, path='/', secure=SECURE, httponly=True, samesite='strict')
    return {'status': 'reauthenticate'}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        try:
            if request.headers.get('host', '').lower() != urlsplit(ORIGIN).netloc.lower():
                fail('HOST_REJECTED', '无效的应用地址。', 400)
            if SECURE and request.url.scheme != 'https':
                fail('HTTPS_REQUIRED', '请通过 HTTPS 访问。', 403)
            if path.startswith('/api/v1/auth/') and int(request.headers.get('content-length', '0') or 0) > 8192:
                fail('BODY_TOO_LARGE', '请求过大。', 413)
            public = path in {'/api/v1/auth/status', '/api/v1/auth/login',
                              '/api/v1/auth/wechat/exchange', '/api/v1/auth/wechat/entry',
                              '/api/v1/auth/wechat/consume', '/api/v1/health'}
            protected = path.startswith('/api/') or path in {'/docs', '/redoc', '/openapi.json'}
            if protected and not public:
                user, session = authenticate(request)
                if not session['mfa_verified']:
                    fail('SESSION_EXPIRED','请重新使用密码登录。',401)
                sensitive = (request.method == 'POST' and (path in {'/api/v1/accounts/manual', '/api/v1/paper/orders'} or (path.startswith('/api/v1/paper/orders/') and path.endswith('/cancel')))) or (request.method == 'DELETE' and (path.startswith('/api/v1/ai/documents/') or path.startswith('/api/v1/auth/sessions/')))
                sensitive = sensitive or (request.method == 'POST' and path in {'/api/v1/paper/accounts', '/api/v1/paper/ai/runs'}) or (request.method == 'PUT' and path.startswith('/api/v1/paper/contracts/'))
                sensitive = sensitive or (request.method == 'POST' and path.startswith('/api/v1/paper/accounts/') and (path.endswith('/reset') or path.endswith('/reset-all')))
                sensitive = sensitive or (request.method in {'POST', 'DELETE'} and path.startswith('/api/v1/agent/extensions/'))
                sensitive = sensitive or (request.method == 'PUT' and path.startswith('/api/v1/agent/extensions/mcp/'))
                sensitive = sensitive or (request.method == 'PUT' and path.startswith('/api/v1/holdings/'))
                sensitive = sensitive or (request.method == 'POST' and (
                    path in {'/api/v1/live/orders', '/api/v1/futu-paper/orders'}
                    or (path.startswith('/api/v1/live/orders/') or path.startswith('/api/v1/futu-paper/orders/')) and path.endswith('/cancel')
                ))
                if sensitive and int(time.time()) - session['reauth_at'] > 300:
                    fail('REAUTH_REQUIRED', '请重新验证身份后执行敏感操作。', 428)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                    with connection() as c:
                        audit(c, user['id'], 'request.begin', f'{request.method} {path}'[:180])
            token = _current_owner.set(request.state.identity['id'] if protected and not public else None)
            try:
                response = await call_next(request)
            finally:
                _current_owner.reset(token)
            if protected and not public and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                with connection() as c:
                    audit(c, request.state.identity['id'], 'request.complete', f'{request.method} {path} {response.status_code}'[:180])
        except HTTPException as exc:
            response = JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
        except (ValueError, InvalidToken):
            response = JSONResponse({'detail': {'code': 'SECURITY_ERROR', 'message': '安全校验失败，请重新登录。'}}, status_code=403)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        })
        if SECURE:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response
