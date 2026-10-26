"""Single-owner authentication: revocable sessions, Argon2id, optional SMS and CSRF.

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

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app import sms_provider
from app.mysql_db import connect as mysql_connect
from starlette.middleware.base import BaseHTTPMiddleware

DATA_DIR = Path(os.getenv('DATA_DIR', Path(__file__).resolve().parent.parent / 'data')).resolve()
ORIGIN = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
SECURE = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
COOKIE = '__Host-finch_session' if SECURE else 'finch_session'
LOGIN_COOKIE = '__Host-finch_login_flow' if SECURE else 'finch_login_flow'
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
    if login_policy() not in {'password','sms'}:
        raise RuntimeError('AUTH_LOGIN_VERIFICATION仅支持password或sms')
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
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at INTEGER NOT NULL, actor TEXT,
          action TEXT NOT NULL, target TEXT NOT NULL, prev_hash TEXT NOT NULL, signature TEXT NOT NULL);
        ''')
        c.executescript("""
        CREATE TABLE IF NOT EXISTS auth_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_challenges(
          digest TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),user_version INTEGER NOT NULL,
          browser_digest TEXT NOT NULL,config_fingerprint TEXT NOT NULL,created_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'ready',code_digest TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,send_count INTEGER NOT NULL DEFAULT 0,last_sent_at INTEGER);
        CREATE TABLE IF NOT EXISTS sms_deliveries(
          id TEXT PRIMARY KEY,challenge_digest TEXT NOT NULL,recipient_hash TEXT NOT NULL,
          created_at INTEGER NOT NULL,status TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_sms_recipient_time ON sms_deliveries(recipient_hash,created_at);
        """)
        columns={r['name'] for r in c.execute('PRAGMA table_info(sessions)')}
        if 'auth_method' not in columns:
            c.execute("ALTER TABLE sessions ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'legacy'")
        policy='password-sms-v1:'+login_policy()
        if login_policy()=='sms':
            try:policy+=':'+sms_provider.config().fingerprint
            except sms_provider.SMSUnavailable:policy+=':unconfigured'
        previous=c.execute("SELECT value FROM auth_metadata WHERE key='login_policy'").fetchone()
        if not previous or previous['value']!=policy:
            c.execute('DELETE FROM sessions')
            c.execute('DELETE FROM login_challenges')
            c.execute("INSERT OR REPLACE INTO auth_metadata VALUES('login_policy',?)",(policy,))
            audit(c,None,'auth.policy_migrated','password+optional_sms')
        c.execute('DELETE FROM login_challenges WHERE expires_at<?',(int(time.time())-86400,))
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
    return os.getenv('AUTH_LOGIN_VERIFICATION','password').strip().lower()


def describe(user, session):
    return {'user': {'id': user['id'], 'username': user['username'], 'role': 'owner'},
            'capabilities': CAPABILITIES if session['mfa_verified'] else [],
            'mfa_enabled':login_policy()=='sms','setup_required':False,
            'login_verification':login_policy(),'auth_method':session.get('auth_method','password') if isinstance(session,dict) else session['auth_method'],
            'sms':sms_provider.readiness(),'csrf_token':session['csrf'],'expires_at':session['expires_at'],
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
    code: str = Field(default='', max_length=64)


class Reauth(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(default='', max_length=64)


class PasswordChange(Reauth):
    new_password: str = Field(min_length=14, max_length=256)


def finish_login(c,user,request,response,method):
    current=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
    if not current or current['version']!=user['version']:
        fail('AUTH_INVALID','账户状态已变更，请重新登录。',401)
    now=int(time.time());raw=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    old=hashlib.sha256(request.cookies.get(COOKIE,'').encode()).hexdigest()
    c.execute('DELETE FROM sessions WHERE digest=? OR expires_at<?',(old,now))
    c.execute('INSERT INTO sessions(digest,user_id,csrf,created_at,expires_at,last_seen,version,mfa_verified,reauth_at,device,auth_method) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (digest,user['id'],csrf,now,now+TTL,now,user['version'],1,now,request.headers.get('user-agent','')[:160],method))
    audit(c,user['id'],'auth.login',method)
    response.set_cookie(COOKIE,raw,max_age=TTL,httponly=True,secure=SECURE,samesite='strict',path='/')
    response.delete_cookie(LOGIN_COOKIE,path='/',secure=SECURE,httponly=True,samesite='strict')
    return describe(current,c.execute('SELECT * FROM sessions WHERE digest=?',(digest,)).fetchone())


def public_json(request):
    origin_check(request)
    if 'application/json' not in request.headers.get('content-type',''):
        fail('JSON_REQUIRED','请使用JSON请求。',415)


@router.get('/status')
def status():
    with connection() as c:
        initialized=bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    return {'initialized':initialized,'registration':'closed','mfa_required':login_policy()=='sms',
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
        if login_policy()=='password':
            return finish_login(c,current,request,response,'password')
        if login_policy()!='sms':fail('AUTH_CONFIG_INVALID','登录配置无效，请联系本机管理员。',503)
        try:settings=sms_provider.config()
        except sms_provider.SMSUnavailable as exc:fail('SMS_NOT_CONFIGURED',str(exc),503)
        # A configured phone belongs only to the private owner, never a model-selected recipient.
        if current['id']!=primary_owner_id():fail('SMS_OWNER_ONLY','短信登录仅配置给本机拥有者。',403)
        raw=secrets.token_urlsafe(32);browser=secrets.token_urlsafe(32);now=int(time.time())
        digest=hashlib.sha256(raw.encode()).hexdigest()
        c.execute("UPDATE login_challenges SET status='expired',code_digest=NULL WHERE user_id=? AND status IN ('ready','sent','sending','unknown')",(current['id'],))
        c.execute('INSERT INTO login_challenges(digest,user_id,user_version,browser_digest,config_fingerprint,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',
                  (digest,current['id'],current['version'],hashlib.sha256(browser.encode()).hexdigest(),settings.fingerprint,now,now+300))
        audit(c,current['id'],'auth.sms_challenge_created')
    response.status_code=202
    response.set_cookie(LOGIN_COOKIE,browser,max_age=300,httponly=True,secure=SECURE,samesite='strict',path='/')
    return {'requires_sms':True,'challenge_id':raw,'masked_phone':settings.masked_phone,'expires_at':now+300,'resend_after':0}


class SMSChallenge(BaseModel):
    challenge_id: str = Field(min_length=20,max_length=100)


class SMSVerification(SMSChallenge):
    code: str = Field(pattern=r'^[0-9]{6}$')


def challenge(c,request,token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=c.execute('SELECT * FROM login_challenges WHERE digest=?',(digest,)).fetchone()
    browser=hashlib.sha256(request.cookies.get(LOGIN_COOKIE,'').encode()).hexdigest()
    if not row or not hmac.compare_digest(browser,row['browser_digest']) or row['expires_at']<=int(time.time()) or row['status'] in {'used','expired','locked'}:
        fail('SMS_CHALLENGE_EXPIRED','本次登录验证已失效，请返回重新输入密码。',401)
    try:settings=sms_provider.config()
    except sms_provider.SMSUnavailable as exc:fail('SMS_NOT_CONFIGURED',str(exc),503)
    user=c.execute('SELECT * FROM users WHERE id=?',(row['user_id'],)).fetchone()
    if login_policy()!='sms' or not user or user['version']!=row['user_version'] or settings.fingerprint!=row['config_fingerprint']:
        fail('SMS_CHALLENGE_EXPIRED','登录配置已变更，请重新输入密码。',401)
    return row,user,settings


def code_digest(digest,code):
    return hmac.new(os.environ['AUTH_AUDIT_KEY'].encode(),('sms:'+digest+':'+code).encode(),hashlib.sha256).hexdigest()


@router.post('/sms/send')
async def send_sms(body: SMSChallenge, request: Request):
    public_json(request);rate_limit(request,'sms_send')
    code=f'{secrets.randbelow(1000000):06d}';now=int(time.time());delivery=secrets.token_hex(16)
    with connection() as c:
        c.execute('BEGIN IMMEDIATE');row,user,settings=challenge(c,request,body.challenge_id)
        recipient=hmac.new(os.environ['AUTH_AUDIT_KEY'].encode(),settings.phone.encode(),hashlib.sha256).hexdigest()
        recent=c.execute('SELECT MAX(created_at) AS latest,COUNT(*) AS total FROM sms_deliveries WHERE recipient_hash=? AND created_at>=?',(recipient,now-86400)).fetchone()
        if recent['latest'] is not None and now-recent['latest']<60:
            fail('SMS_COOLDOWN','请稍后再发送，短信间隔至少60秒。',429)
        if recent['total']>=10 or row['send_count']>=3:
            fail('SMS_SEND_LIMIT','已达到短信发送上限，稍后再试或联系本机管理员。',429)
        c.execute('INSERT INTO sms_deliveries VALUES(?,?,?,?,?)',(delivery,row['digest'],recipient,now,'sending'))
        c.execute("UPDATE login_challenges SET status='sending',code_digest=?,attempts=0,send_count=send_count+1,last_sent_at=? WHERE digest=?",(code_digest(row['digest'],code),now,row['digest']))
        audit(c,user['id'],'auth.sms_send_requested')
    error=None;state='sent'
    try:await sms_provider.send_code(settings,code)
    except sms_provider.SMSRejected as exc:state='failed';error=str(exc)
    except sms_provider.SMSUnknown as exc:state='unknown';error=str(exc)
    except Exception:state='unknown';error='发送结果无法确认，请先查看手机，稍后再试。'
    finally:code=None
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('UPDATE sms_deliveries SET status=? WHERE id=?',(state,delivery))
        # A concurrent new login may already have invalidated this challenge.
        c.execute("UPDATE login_challenges SET status=?,code_digest=CASE WHEN ?='failed' THEN NULL ELSE code_digest END WHERE digest=? AND status='sending' AND last_sent_at=?",(state,state,row['digest'],now))
        audit(c,user['id'],'auth.sms_'+state)
    if error:fail('SMS_SEND_UNKNOWN' if state=='unknown' else 'SMS_SEND_FAILED',error,503)
    return {'status':'accepted','resend_after':60,'expires_at':row['expires_at'],'masked_phone':settings.masked_phone,
            'message':'短信服务已受理，请以手机实际收到为准。'}


@router.post('/sms/verify')
def verify_sms(body: SMSVerification, request: Request, response: Response):
    public_json(request);rate_limit(request,'sms_verify')
    invalid=False
    with connection() as c:
        c.execute('BEGIN IMMEDIATE');row,user,settings=challenge(c,request,body.challenge_id)
        if row['status'] not in {'sent','unknown','sending'} or not row['code_digest']:
            fail('SMS_NOT_SENT','请先发送验证码；发送处理中请稍候。',409)
        if row['attempts']>=5:fail('SMS_CODE_LOCKED','验证码错误次数过多，请重新输入密码。',401)
        valid=hmac.compare_digest(row['code_digest'],code_digest(row['digest'],body.code))
        if not valid:
            c.execute("UPDATE login_challenges SET attempts=attempts+1,status=CASE WHEN attempts+1>=5 THEN 'locked' ELSE status END WHERE digest=?",(row['digest'],))
            audit(c,user['id'],'auth.sms_code_failed');invalid=True
        else:
            c.execute("UPDATE login_challenges SET status='used',code_digest=NULL WHERE digest=?",(row['digest'],))
            result=finish_login(c,user,request,response,'password_sms')
    if invalid:fail('SMS_CODE_INVALID','短信验证码不正确。',401)
    return result


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
            public = path in {'/api/v1/auth/status', '/api/v1/auth/login', '/api/v1/auth/sms/send', '/api/v1/auth/sms/verify', '/api/v1/health'}
            protected = path.startswith('/api/') or path in {'/docs', '/redoc', '/openapi.json'}
            if protected and not public:
                user, session = authenticate(request)
                if not session['mfa_verified']:
                    fail('SESSION_EXPIRED','请重新使用密码登录。',401)
                sensitive = (request.method == 'POST' and (path in {'/api/v1/accounts/manual', '/api/v1/paper/orders'} or (path.startswith('/api/v1/paper/orders/') and path.endswith('/cancel')))) or (request.method == 'DELETE' and (path.startswith('/api/v1/ai/documents/') or path.startswith('/api/v1/auth/sessions/')))
                sensitive = sensitive or (request.method == 'POST' and path in {'/api/v1/paper/accounts', '/api/v1/paper/ai/runs'}) or (request.method == 'PUT' and path.startswith('/api/v1/paper/contracts/'))
                sensitive = sensitive or (request.method == 'POST' and path.startswith('/api/v1/paper/accounts/') and (path.endswith('/reset') or path.endswith('/reset-all')))
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
