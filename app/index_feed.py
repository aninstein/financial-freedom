"""Current index observations, separate from historical daily bars and trading quotes.

One backend collector serves every browser. Optional Longbridge quote pushes
replace sampled public observations where the owner has market-data permission.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.research_data import INDEX_CATALOG

ROOT = Path(__file__).resolve().parents[1]
INDEX_IDS = {row['id'] for row in INDEX_CATALOG}
CN_CODES = {
    '000001': 'INDEX:SH000001', '399001': 'INDEX:SZ399001',
    '000300': 'INDEX:SH000300', '000905': 'INDEX:SH000905',
    '399006': 'INDEX:SZ399006', '000688': 'INDEX:SH000688',
}
GLOBAL_CODES = {**CN_CODES, 'HSI': 'INDEX:HSI', 'SPX': 'INDEX:SPX', 'DJIA': 'INDEX:DJIA'}
# NDX is Nasdaq 100, not Nasdaq Composite. Do not substitute it.
LONGBRIDGE_SYMBOLS = {
    '000001.SH': 'INDEX:SH000001', '399001.SZ': 'INDEX:SZ399001',
    '000300.SH': 'INDEX:SH000300', '000905.SH': 'INDEX:SH000905',
    '399006.SZ': 'INDEX:SZ399006', '000688.SH': 'INDEX:SH000688',
    'HSI.HK': 'INDEX:HSI', 'SPX.US': 'INDEX:SPX', 'DJI.US': 'INDEX:DJIA',
}
SOURCE_KINDS = ('global', 'main', 'csi', 'sse')
POLL_SECONDS = max(10, min(300, int(os.getenv('INDEX_POLL_SECONDS', '15'))))


def _positive(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _exchange_time(value):
    if value is None or str(value).strip() in {'', 'NaT'}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _observation(index_id, raw, source, exchange_time=None):
    if index_id not in INDEX_IDS:
        return None
    last = _positive(raw.get('最新价'))
    if last is None:
        return None
    previous = _positive(raw.get('昨收', raw.get('昨收价')))
    change = _number(raw.get('涨跌幅'))
    if change is None and previous:
        change = (last / previous - 1) * 100
    return {
        'id': index_id, 'last': last, 'change_percent': change,
        'previous_close': previous, 'open': _positive(raw.get('今开', raw.get('开盘价'))),
        'high': _positive(raw.get('最高', raw.get('最高价'))),
        'low': _positive(raw.get('最低', raw.get('最低价'))),
        'volume': _number(raw.get('成交量')), 'turnover': _number(raw.get('成交额')),
        'source': source, 'source_time': exchange_time,
        'received_at': datetime.now(timezone.utc).isoformat(),
        'known_delay_seconds': None, 'feed': 'sampled',
    }


def _akshare_batch(kind):
    import akshare as ak
    from app.providers.sector_provider import _records

    if kind == 'global':
        frame = ak.index_global_spot_em()
        mapping = GLOBAL_CODES
        source = 'AKShare · 东方财富全球指数批量快照'
    else:
        category = {'main': '沪深重要指数', 'csi': '中证系列指数', 'sse': '上证系列指数'}[kind]
        frame = ak.stock_zh_index_spot_em(symbol=category)
        mapping = CN_CODES
        source = f'AKShare · 东方财富{category}批量快照'
    result = []
    for raw in _records(frame):
        index_id = mapping.get(str(raw.get('代码', '')).strip())
        if index_id:
            item = _observation(index_id, raw, source, _exchange_time(raw.get('最新行情时间')))
            if item:
                result.append(item)
    return result


class IndexFeed:
    def __init__(self):
        self._observations: dict[str, dict[str, dict]] = {}
        self._errors: dict[str, str] = {}
        self._attempted: dict[str, str] = {}
        self._tasks: list[asyncio.Task] = []
        self._longbridge_context = None
        self._longbridge_connected = False
        self._market_state = None
        self._current_cadence = POLL_SECONDS

    def start(self, market_state):
        self._market_state = market_state
        if os.getenv('AKSHARE_ENABLED', 'true').lower() == 'true':
            self._tasks.append(asyncio.create_task(self._poll_public()))
        if os.getenv('INDEX_FEED_PROVIDER', 'akshare').lower() == 'longbridge':
            self._tasks.append(asyncio.create_task(self._subscribe_longbridge()))

    async def close(self):
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._longbridge_context = None

    def _apply(self, provider, items):
        for item in items:
            if item and item['id'] in INDEX_IDS:
                old = self._observations.get(item['id'], {}).get(provider)
                if old and old.get('source_time') and item.get('source_time'):
                    if item['source_time'] < old['source_time'] or (
                        item['source_time'] == old['source_time'] and
                        old.get('feed') == 'push' and item.get('feed') != 'push'):
                        continue
                if (provider == 'akshare' and old and old.get('source_time')
                        and not item.get('source_time')
                        and (datetime.now(timezone.utc) - datetime.fromisoformat(old['received_at'])).total_seconds() < 45):
                    continue
                self._observations.setdefault(item['id'], {})[provider] = item

    def ingest_futu(self, items):
        self._apply('futu', items)
        self._errors.pop('futu', None)

    def _active_session(self):
        if not self._market_state:
            return False
        return any(self._market_state(market)['phase'] in {'open', 'preopen', 'pre_market'}
                   for market in ('CN', 'HK', 'US'))

    async def _poll_public(self):
        # Kill a hung public adapter. The browser never calls these sources.
        while True:
            started = asyncio.get_running_loop().time()
            limit = asyncio.Semaphore(2)
            async def collect(kind):
                async with limit:
                    self._attempted[kind] = datetime.now(timezone.utc).isoformat()
                    proc = None
                    try:
                        allowed = {'PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                                   'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy'}
                        env = {key: value for key, value in os.environ.items() if key in allowed}
                        env['PYTHONIOENCODING'] = 'utf-8'
                        proc = await asyncio.create_subprocess_exec(
                            sys.executable, '-m', 'app.index_feed', '--worker', kind,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                            env=env, cwd=str(ROOT),
                        )
                        output, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
                        if proc.returncode or len(output) > 300_000:
                            raise ValueError('adapter_failed')
                        items = json.loads(output)
                        if not isinstance(items, list) or not items:
                            raise ValueError('empty_batch')
                        self._apply('akshare', items)
                        self._errors.pop(kind, None)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self._errors[kind] = '公共指数源暂不可用：' + type(exc).__name__
                    finally:
                        if proc and proc.returncode is None:
                            proc.kill()
                            await proc.communicate()
            await asyncio.gather(*(collect(kind) for kind in SOURCE_KINDS))
            cadence = POLL_SECONDS if self._active_session() else 300
            self._current_cadence = cadence
            await asyncio.sleep(max(0, cadence - (asyncio.get_running_loop().time() - started)))

    async def _subscribe_longbridge(self):
        # Only a market-data context is constructed; no trade/order API.
        required = ('LONGBRIDGE_APP_KEY', 'LONGBRIDGE_APP_SECRET', 'LONGBRIDGE_ACCESS_TOKEN')
        if not all(os.getenv(key) for key in required):
            self._errors['longbridge'] = 'Longbridge 行情凭证尚未配置'
            return
        try:
            from longbridge.openapi import AsyncQuoteContext, Config, SubType
        except ImportError:
            self._errors['longbridge'] = 'Longbridge 行情 SDK 尚未安装'
            return
        backoff = 5
        while True:
            try:
                config = Config.from_apikey_env()
                ctx = AsyncQuoteContext.create(config, loop_=asyncio.get_running_loop())
                self._longbridge_context = ctx
                ctx.set_on_quote(self._on_longbridge_quote)
                subscribed = 0
                for market, symbols in (
                    ('CN', [s for s in LONGBRIDGE_SYMBOLS if s.endswith(('.SH', '.SZ'))]),
                    ('HK', ['HSI.HK']),
                    ('US', ['SPX.US', 'DJI.US']),
                ):
                    try:
                        await asyncio.wait_for(ctx.subscribe(symbols, [SubType.Quote]), timeout=12)
                        subscribed += len(symbols)
                        for quote in await asyncio.wait_for(ctx.quote(symbols), timeout=12):
                            self._on_longbridge_quote(quote.symbol, quote)
                        self._errors.pop('longbridge:' + market, None)
                    except Exception as exc:
                        self._errors['longbridge:' + market] = '订阅未就绪：' + type(exc).__name__
                if not subscribed:
                    raise RuntimeError('no_subscriptions')
                self._longbridge_connected = True
                self._errors.pop('longbridge', None)
                backoff = 5
                while True:
                    await asyncio.sleep(30 if self._active_session() else 300)
                    for market, symbols in (
                        ('CN', [s for s in LONGBRIDGE_SYMBOLS if s.endswith(('.SH', '.SZ'))]),
                        ('HK', ['HSI.HK']), ('US', ['SPX.US', 'DJI.US']),
                    ):
                        if 'longbridge:' + market in self._errors:
                            continue
                        for quote in await asyncio.wait_for(ctx.quote(symbols), timeout=12):
                            self._on_longbridge_quote(quote.symbol, quote)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._errors['longbridge'] = '订阅连接中断：' + type(exc).__name__
                self._longbridge_connected = False
                self._longbridge_context = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)

    def _on_longbridge_quote(self, symbol, event):
        index_id = LONGBRIDGE_SYMBOLS.get(symbol)
        last = _positive(getattr(event, 'last_done', None))
        if not index_id or last is None:
            return
        stamp = getattr(event, 'timestamp', None)
        try:
            source_time = datetime.fromtimestamp(int(stamp), timezone.utc).isoformat() if stamp else None
        except (TypeError, ValueError, OverflowError):
            source_time = None
        item = {
            'id': index_id, 'last': last, 'change_percent': None,
            'previous_close': _positive(getattr(event, 'prev_close', None)),
            'high': _positive(getattr(event, 'high', None)),
            'low': _positive(getattr(event, 'low', None)),
            'volume': _number(getattr(event, 'volume', None)),
            'turnover': _number(getattr(event, 'turnover', None)),
            'source': 'Longbridge OpenAPI · 订阅报价', 'source_time': source_time,
            'received_at': datetime.now(timezone.utc).isoformat(),
            'known_delay_seconds': None if index_id.startswith(('INDEX:SH', 'INDEX:SZ')) else 0,
            'feed': 'push',
        }
        old = self._observations.get(index_id, {}).get('longbridge')
        if old and source_time and old.get('source_time') and source_time < old['source_time']:
            if item['previous_close'] and not old.get('previous_close'):
                old['previous_close'] = item['previous_close']
                old['change_percent'] = (old['last'] / item['previous_close'] - 1) * 100
            return
        # Pushes contain changed fields only; keep prior full fields if omitted.
        if old:
            for key in ('previous_close', 'open', 'high', 'low', 'volume', 'turnover'):
                if item[key] is None:
                    item[key] = old.get(key)
        if item['previous_close']:
            item['change_percent'] = (last / item['previous_close'] - 1) * 100
        self._apply('longbridge', [item])

    def snapshot(self):
        now = datetime.now(timezone.utc)
        rows = []
        for meta in INDEX_CATALOG:
            variants = self._observations.get(meta['id'], {})
            item = None
            for provider in ('futu', 'longbridge', 'akshare'):
                candidate = variants.get(provider)
                if not candidate:
                    continue
                if provider != 'akshare':
                    age = (now - datetime.fromisoformat(candidate['received_at'])).total_seconds()
                    if age > 45:
                        continue
                if item is None:
                    item = candidate
                    continue
                # A scrape with no exchange timestamp must not displace an
                # OpenD observation merely because the scrape arrived later.
                candidate_time = candidate.get('source_time')
                current_time = item.get('source_time')
                if candidate_time and (not current_time or candidate_time > current_time):
                    item = candidate
            if not item:
                rows.append({**meta, 'state': 'unavailable', 'last': None})
                continue
            age = max(0, int((now - datetime.fromisoformat(item['received_at'])).total_seconds()))
            source_age = max(0, int((now - datetime.fromisoformat(item['source_time'])).total_seconds())) if item.get('source_time') else None
            rows.append({**meta, **item, 'state': 'fresh' if age <= 45 else 'stale',
                         'age_seconds': age, 'source_age_seconds': source_age,
                         'source_time_available': bool(item.get('source_time'))})
        return {'indices': rows, 'served_at': now.isoformat(),
                'display_interval_seconds': 1, 'akshare_poll_seconds': POLL_SECONDS,
                'current_poll_seconds': self._current_cadence,
                'provider': ('futu' if os.getenv('FUTU_ENABLED', 'false').lower() == 'true'
                             else 'longbridge' if os.getenv('INDEX_FEED_PROVIDER', 'akshare').lower() == 'longbridge'
                             else 'akshare' if os.getenv('AKSHARE_ENABLED', 'true').lower() == 'true' else 'disabled'),
                'longbridge_connected': self._longbridge_connected,
                'source_errors': dict(self._errors), 'source_attempted_at': dict(self._attempted)}


FEED = IndexFeed()


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--worker' or sys.argv[2] not in SOURCE_KINDS:
        raise SystemExit(2)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = _akshare_batch(sys.argv[2])
    except Exception:
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
