"""Authenticated request to the Mac host's fixed OpenD window launcher."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path

PORT = 18731


class OpenDLaunchUnavailable(RuntimeError):
    pass


def open_login_window() -> dict:
    container = os.getenv('CONTAINER_RUNTIME') == 'true'
    secret_file = (Path('/run/secrets/futu_launcher_token') if container else
                   Path(__file__).resolve().parent.parent / '.runtime/secrets/futu-launcher-token')
    try:
        secret = secret_file.read_text().strip()
    except OSError as exc:
        raise OpenDLaunchUnavailable('本机 OpenD 登录入口尚未启动；请重新运行项目启动脚本') from exc
    if not secret:
        raise OpenDLaunchUnavailable('本机 OpenD 登录入口配置为空')
    host = 'host.docker.internal' if container else '127.0.0.1'
    try:
        conn = http.client.HTTPConnection(host, PORT, timeout=4)
        try:
            conn.request('POST', '/open', body=b'', headers={
                'X-Futu-Launcher-Token': secret, 'Content-Length': '0'})
            response = conn.getresponse()
            payload = json.loads(response.read(1024).decode())
        finally:
            conn.close()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise OpenDLaunchUnavailable('无法连接本机 OpenD 登录入口；请重新运行项目启动脚本') from exc
    if response.status != 200 or payload.get('ok') is not True:
        raise OpenDLaunchUnavailable(str(payload.get('message') or 'OpenD 官方窗口未能打开')[:120])
    return {'opened': True, 'message': '已打开富途 OpenD 官方窗口，请在其中完成或检查登录。'}
