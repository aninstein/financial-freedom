"""Read-only Futu OpenD market data. No trading context or credentials here."""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

INDEX_CODES = {
    'SH.000001': 'INDEX:SH000001', 'SZ.399001': 'INDEX:SZ399001',
    'SH.000300': 'INDEX:SH000300', 'SH.000905': 'INDEX:SH000905',
    'SZ.399006': 'INDEX:SZ399006', 'SH.000688': 'INDEX:SH000688',
    'HK.800000': 'INDEX:HSI',
}


def address():
    host = os.getenv('FUTU_OPEND_HOST', '127.0.0.1').strip()
    allowed = {'127.0.0.1', 'localhost', '::1'}
    if os.getenv('CONTAINER_RUNTIME') == 'true':
        allowed.add('host.docker.internal')
    if host not in allowed:
        raise ValueError('OpenD 仅允许本机或 Docker 的 host.docker.internal 网关')
    port = int(os.getenv('FUTU_OPEND_PORT', '11111'))
    if not 1 <= port <= 65535:
        raise ValueError('FUTU_OPEND_PORT 超出范围')
    return host, port


def code_for(instrument_id):
    market, sep, symbol = instrument_id.partition(':')
    if not sep:
        return None
    if market == 'FUND' and not symbol.startswith(('5', '15', '16')):
        return None  # Open-end mutual fund NAV is not an exchange-traded quote.
    if market in {'CN', 'FUND'} and re.fullmatch(r'\d{6}', symbol):
        exchange = 'BJ' if symbol.startswith(('4', '8', '92')) else ('SH' if symbol.startswith(('6', '9', '5')) else 'SZ')
        return f'{exchange}.{symbol}' if exchange != 'BJ' else None
    if market == 'HK' and re.fullmatch(r'\d{1,5}', symbol):
        return f'HK.{symbol.zfill(5)}'
    if market == 'US' and re.fullmatch(r'[A-Za-z0-9.\-]{1,24}', symbol):
        return f'US.{symbol.upper()}'
    return None


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def observed_time(value, market):
    if value is None or str(value).strip() in {'', 'NaT'}:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo('America/New_York' if market == 'US' else 'Asia/Shanghai'))
        return stamp.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def normalize_snapshot(row, requested_id=None, pushed=False):
    code = str(row.get('code', '')).strip().upper()
    if not code or '.' not in code:
        return None
    last = _number(row.get('last_price'))
    if last is None or last <= 0:
        return None
    prefix, symbol = code.split('.', 1)
    market = {'SH': 'CN', 'SZ': 'CN', 'HK': 'HK', 'US': 'US'}.get(prefix)
    if market is None:
        return None
    previous = _number(row.get('prev_close_price'))
    received = datetime.now(timezone.utc).isoformat()
    raw_time = row.get('update_time') or (
        str(row.get('data_date', '')) + ' ' + str(row.get('data_time', '')))
    when = observed_time(str(raw_time).strip(), market)
    source = '富途 OpenD · 订阅推送' if pushed else '富途 OpenD · 官方行情快照'
    common = {
        'last': last, 'previous_close': previous,
        'change_percent': (last / previous - 1) * 100 if previous and previous > 0 else None,
        'open': _number(row.get('open_price')), 'high': _number(row.get('high_price')),
        'low': _number(row.get('low_price')), 'volume': _number(row.get('volume')),
        'turnover': _number(row.get('turnover')), 'source_time': when,
        'received_at': received, 'source': source,
        'known_delay_seconds': 0 if pushed else None,
        'feed': 'push' if pushed else 'sampled',
    }
    index_id = INDEX_CODES.get(code)
    if index_id:
        return 'index', {'id': index_id, **common}
    asset_class = 'etf' if market == 'CN' and symbol.startswith(('5', '15', '16')) else 'equity'
    quote_market = requested_id.split(':', 1)[0] if requested_id else ('FUND' if asset_class == 'etf' else market)
    currency = {'CN': 'CNY', 'HK': 'HKD', 'US': 'USD'}[market]
    # Timestamp and entitlement decide whether a quote is usable for paper
    # matching; a successfully fetched snapshot is not proof of zero delay.
    return 'quote', {
        'instrument_id': requested_id or f'{quote_market}:{symbol}', 'symbol': symbol,
        'name': str(row.get('name') or symbol)[:120], 'market': quote_market,
        'asset_class': asset_class, 'last': last, 'currency': currency,
        'quote_kind': 'realtime' if pushed else 'snapshot', 'price_unit': f'{currency}/share',
        'exchange_time': when, 'received_at': received,
        'provider': source,
        'freshness': 'unknown' if when is None else 'observed',
        'known_delay_seconds': 0 if pushed else None, 'change_percent': common['change_percent'],
        'volume': common['volume'],
    }


class FutuQuoteClient:
    """Persistent local quote connection; call from a single worker thread."""

    def __init__(self, on_push=None):
        self._ctx = None
        self._on_push = on_push
        self._subscribed = set()
        self._requested_ids = {}
        self._last_rows = {}

    def close(self):
        if self._ctx is not None:
            try:
                self._ctx.close()
            finally:
                self._ctx = None
                self._subscribed.clear()

    def fetch(self, codes, requested_ids=None):
        """OpenD login happens in the official app, never in this process."""
        from futu import OpenQuoteContext, RET_OK, StockQuoteHandlerBase, SubType

        if self._ctx is None:
            host, port = address()
            self._ctx = OpenQuoteContext(host=host, port=port)
            if self._on_push is not None:
                client = self
                class QuoteHandler(StockQuoteHandlerBase):
                    def on_recv_rsp(self, response):
                        ret, data = super().on_recv_rsp(response)
                        if ret == RET_OK:
                            try:
                                items = []
                                for raw in data.to_dict(orient='records'):
                                    code = str(raw.get('code', '')).upper()
                                    merged = {**client._last_rows.get(code, {}), **raw, 'update_time': None}
                                    client._last_rows[code] = merged
                                    item = normalize_snapshot(merged, client._requested_ids.get(code), True)
                                    if item:
                                        items.append(item)
                                if items:
                                    client._on_push(items)
                            except Exception:
                                pass
                        return ret, data
                self._ctx.set_handler(QuoteHandler())
        try:
            self._requested_ids.update(requested_ids or {})
            if len(self._subscribed) > 80:
                self.close()
                return self.fetch(codes, requested_ids)
            missing = [code for code in codes if code not in self._subscribed]
            if missing and self._on_push is not None:
                try:
                    ret, _ = self._ctx.subscribe(missing, [SubType.QUOTE], is_first_push=True)
                    if ret == RET_OK:
                        self._subscribed.update(missing)
                except Exception:
                    pass  # Snapshot remains available with BMP/delayed rights.
            ret, data = self._ctx.get_market_snapshot(codes)
            if ret != RET_OK:
                raise RuntimeError('OpenD 行情请求失败：' + str(data)[:180])
            requested_ids = requested_ids or {}
            items = []
            for raw in data.to_dict(orient='records'):
                code = str(raw.get('code', '')).upper()
                self._last_rows[code] = raw
                item = normalize_snapshot(raw, requested_ids.get(code))
                if item:
                    items.append(item)
            return items
        except Exception:
            self.close()
            raise


def fetch_history(instrument_id, start, end):
    """Daily unadjusted bars for one tracked security; consumes OpenD quota."""
    from futu import AuType, KLType, OpenQuoteContext, RET_OK
    import pandas as pd

    code = code_for(instrument_id)
    if not code:
        raise ValueError('富途不支持此标的历史日线')
    host, port = address()
    ctx = OpenQuoteContext(host=host, port=port)
    try:
        frames, page = [], None
        for _ in range(3):
            ret, frame, page = ctx.request_history_kline(
                code, start=start.isoformat(), end=end.isoformat(),
                ktype=KLType.K_DAY, autype=AuType.NONE,
                max_count=1000, page_req_key=page)
            if ret != RET_OK:
                raise RuntimeError('富途历史 K 线暂不可用')
            frames.append(frame)
            if page is None:
                break
        if page is not None:
            raise RuntimeError('富途历史 K 线分页超出本次上限')
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    finally:
        ctx.close()
