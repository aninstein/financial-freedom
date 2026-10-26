"""Bounded read-only OpenD collector for indices and owned paper/watch symbols."""
from __future__ import annotations

import asyncio
import os
import queue
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.providers.futu_provider import FutuQuoteClient, INDEX_CODES, address, code_for

POLL_SECONDS = max(3, min(30, int(os.getenv('FUTU_POLL_SECONDS', '3'))))


class FutuFeed:
    def __init__(self):
        self.enabled = os.getenv('FUTU_ENABLED', 'false').lower() == 'true'
        self.connected = False
        self.last_success = None
        self.last_error = None
        self.market_errors = {}
        self.quote_count = 0
        self._task = None
        self._push_task = None
        self._executor = None
        self._client = None
        self._push_queue = queue.Queue(maxsize=1000)

    def start(self, targets, on_quotes, on_indices):
        if not self.enabled:
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='futu-quote')
        self._client = FutuQuoteClient(self._accept_push)
        self._task = asyncio.create_task(self._run(targets, on_quotes, on_indices))
        self._push_task = asyncio.create_task(self._consume_push(on_quotes, on_indices))

    def _accept_push(self, items):
        try:
            self._push_queue.put_nowait(items)
        except queue.Full:
            pass  # The next bounded snapshot repairs any dropped update.

    async def _consume_push(self, on_quotes, on_indices):
        while True:
            quotes, indices = [], []
            for _ in range(100):
                try:
                    items = self._push_queue.get_nowait()
                except queue.Empty:
                    break
                for kind, item in items:
                    (indices if kind == 'index' else quotes).append(item)
            try:
                if indices:
                    on_indices(indices)
                if quotes:
                    on_quotes(quotes)
            except Exception:
                self.last_error = '富途推送已到达，但本地行情写入失败'
                await asyncio.sleep(0.5)
                continue
            if indices or quotes:
                self.connected = True
                self.last_success = datetime.now(timezone.utc).isoformat()
                self.quote_count = len(indices) + len(quotes)
                self.last_error = None
            await asyncio.sleep(0.5)

    async def close(self):
        if self._push_task:
            self._push_task.cancel()
            await asyncio.gather(self._push_task, return_exceptions=True)
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._executor:
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(loop.run_in_executor(self._executor, self._client.close), timeout=3)
            except (TimeoutError, OSError):
                pass
            self._executor.shutdown(wait=False, cancel_futures=True)

    def status(self):
        reachable = False
        if self.enabled:
            try:
                host, port = address()
                with socket.create_connection((host, port), timeout=0.3):
                    reachable = True
            except (OSError, ValueError):
                pass
        return {
            'provider': 'futu', 'enabled': self.enabled, 'connected': self.connected,
            'opend_reachable': reachable,
            'opend_host': '127.0.0.1', 'opend_port': int(os.getenv('FUTU_OPEND_PORT', '11111')),
            'poll_seconds': POLL_SECONDS, 'last_success': self.last_success,
            'last_error': self.last_error, 'market_errors': dict(self.market_errors),
            'last_quote_count': self.quote_count,
            'login_method': '请在富途官方 OpenD 中登录；本网页不接收富途密码，也不连接交易接口。',
        }

    async def _run(self, targets, on_quotes, on_indices):
        loop = asyncio.get_running_loop()
        while True:
            started = time.monotonic()
            try:
                host, port = address()
                with socket.create_connection((host, port), timeout=0.5):
                    pass
            except (OSError, ValueError):
                self.connected = False
                self.last_error = '本机 OpenD 未监听；请在富途 OpenD 完成登录，并启用本地 API 端口'
                self.market_errors = {}
                await asyncio.sleep(POLL_SECONDS)
                continue
            try:
                selected = targets()
            except Exception:
                self.connected = False
                self.last_error = '本地关注列表暂不可读，等待数据存储恢复'
                await asyncio.sleep(POLL_SECONDS)
                continue
            grouped = {'CN': {}, 'HK': {}, 'US': {}}
            for code in INDEX_CODES:
                grouped['CN' if code.startswith(('SH.', 'SZ.')) else 'HK'][code] = None
            for instrument_id in selected:
                code = code_for(instrument_id)
                if code:
                    market = 'CN' if code.startswith(('SH.', 'SZ.')) else code.split('.', 1)[0]
                    if market in grouped and code not in grouped[market]:
                        grouped[market][code] = instrument_id
            # HK BMP snapshot rights cap a single request at 20 symbols. Leave
            # room for the HSI and preserve higher-priority positions first.
            grouped['HK'] = dict(list(grouped['HK'].items())[:20])
            all_quotes, all_indices = [], []
            failures = {}
            for market, target_map in grouped.items():
                if not target_map:
                    continue
                try:
                    items = await loop.run_in_executor(
                        self._executor, self._client.fetch, list(target_map), target_map)
                    for kind, item in items:
                        (all_indices if kind == 'index' else all_quotes).append(item)
                    self.market_errors.pop(market, None)
                except ImportError:
                    failures[market] = '富途 SDK 未安装；请安装项目依赖'
                except (ConnectionError, OSError):
                    failures[market] = '本机 OpenD 未运行或未登录'
                except Exception as exc:
                    # Upstream text can contain account details; expose type only.
                    failures[market] = 'OpenD 行情或权限不可用：' + type(exc).__name__
            self.market_errors = failures
            try:
                if all_indices:
                    on_indices(all_indices)
                if all_quotes:
                    on_quotes(all_quotes)
            except Exception:
                self.connected = False
                self.last_error = '富途快照已到达，但本地行情写入失败'
                await asyncio.sleep(POLL_SECONDS)
                continue
            if all_quotes or all_indices:
                self.connected = True
                self.last_success = datetime.now(timezone.utc).isoformat()
                self.quote_count = len(all_quotes) + len(all_indices)
                self.last_error = None
            else:
                self.connected = False
                self.last_error = next(iter(failures.values()), 'OpenD 未返回可用行情')
            await asyncio.sleep(max(0.5, POLL_SECONDS - (time.monotonic() - started)))


FEED = FutuFeed()
