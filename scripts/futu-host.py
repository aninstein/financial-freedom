#!/usr/bin/env python3
"""Launch the official macOS OpenD window for the local, authenticated web app.

This bridge never accepts account details and only performs one fixed action:
opening the installed Futu_OpenD.app. It listens on host loopback and requires
a private token shared with the Docker web container.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import plistlib
import secrets
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path('/Applications/Futu_OpenD.app')
TOKEN_FILE = ROOT / '.runtime/secrets/futu-launcher-token'
PORT = 18731
_last_open = 0.0


def env_value(name: str, default: str = '') -> str:
    env_file = ROOT / '.env'
    if not env_file.exists():
        return default
    result = default
    for line in env_file.read_text().splitlines():
        if line.strip().startswith(name + '='):
            result = line.split('=', 1)[1].strip().strip('"\'')
    return result


def enabled() -> bool:
    return env_value('FUTU_ENABLED', 'false').lower() == 'true'


def token() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        fd = os.open(TOKEN_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(48) + '\n')
    TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()


def checked_app() -> Path:
    info = APP / 'Contents/Info.plist'
    if not info.is_file():
        raise FileNotFoundError('未找到 /Applications/Futu_OpenD.app')
    with info.open('rb') as stream:
        bundle = plistlib.load(stream)
    if bundle.get('CFBundleIdentifier') != 'cn.futu.FutuOpenDGUI':
        raise ValueError('OpenD 应用身份校验失败')
    return APP


def open_official_app() -> None:
    app = checked_app()
    subprocess.run(['/usr/bin/open', '-a', str(app)], check=True, timeout=8,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def bridge_healthy(secret: str) -> bool:
    try:
        conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=0.5)
        conn.request('GET', '/health', headers={'X-Futu-Launcher-Token': secret})
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status == 200
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _authorized(self) -> bool:
        supplied = self.headers.get('X-Futu-Launcher-Token', '')
        return hmac.compare_digest(supplied.encode(), token().encode())

    def _reply(self, status: int, body: dict):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path != '/health' or not self._authorized():
            self._reply(404, {'ok': False})
            return
        self._reply(200, {'ok': True})

    def do_POST(self):
        global _last_open
        if self.path != '/open' or not self._authorized() or self.headers.get('Content-Length', '0') != '0':
            self._reply(404, {'ok': False})
            return
        if not enabled():
            self._reply(409, {'ok': False, 'message': '富途行情尚未启用'})
            return
        now = time.monotonic()
        if now - _last_open < 3:
            self._reply(200, {'ok': True, 'message': '已请求打开富途 OpenD'})
            return
        try:
            open_official_app()
        except (FileNotFoundError, ValueError, subprocess.SubprocessError) as exc:
            self._reply(503, {'ok': False, 'message': str(exc)[:120]})
            return
        _last_open = now
        self._reply(200, {'ok': True, 'message': '已打开富途 OpenD 官方窗口'})


def ensure():
    secret = token()
    if sys.platform != 'darwin' or not enabled():
        return
    if not bridge_healthy(secret):
        log = ROOT / '.runtime/futu-launcher.log'
        with log.open('ab') as output:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'],
                             stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True, cwd=ROOT)
        for _ in range(30):
            if bridge_healthy(secret):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('本机 OpenD 登录入口未能启动；请检查 .runtime/futu-launcher.log')
    try:
        with socket.create_connection(('127.0.0.1', int(env_value('FUTU_OPEND_PORT', '11111'))), timeout=0.3):
            pass
    except (OSError, ValueError):
        open_official_app()
        print('已打开富途 OpenD；请在官方窗口完成登录。', flush=True)
    else:
        print('富途 OpenD 已登录并监听本地 API。', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'--ensure', '--serve'}:
        raise SystemExit('usage: futu-host.py --ensure|--serve')
    if sys.argv[1] == '--ensure':
        ensure()
    else:
        server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        server.serve_forever(poll_interval=0.25)
