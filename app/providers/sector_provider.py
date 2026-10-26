"""Best-effort industry data; independent sources can return partial snapshots."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Callable

TTL_SECONDS = 300
RETRY_SECONDS = 60
_locks: dict[str, asyncio.Lock] = {}
_sources: dict[str, asyncio.Task] = {}


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, 'empty', True):
        return []

    def clean(value: Any) -> Any:
        if hasattr(value, 'item'):
            value = value.item()
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)

    return [{str(k): clean(v) for k, v in row.items()} for row in frame.to_dict(orient='records')]


def _fetch_source(kind: str, name: str | None) -> list[dict[str, Any]]:
    import akshare as ak
    if kind == 'sectors':
        return _records(ak.stock_board_industry_name_em())
    if kind == 'constituents':
        return _records(ak.stock_board_industry_cons_em(symbol=name))
    return _records(ak.stock_sector_fund_flow_rank(indicator='今日', sector_type='行业资金流'))


async def _fetch(name: str | None, timeout: int) -> dict[str, Any]:
    # Deduplicate active upstream calls, including calls that exceed the UI deadline.
    # A stalled catalog must not hide a successful constituents or flow response.
    tasks = {}
    for kind in (['sectors', 'constituents', 'flow'] if name else ['sectors']):
        key = kind + (':' + name if kind == 'constituents' else '')
        task = _sources.get(key)
        if task is None or task.done():
            task = asyncio.create_task(asyncio.to_thread(_fetch_source, kind, name))
            _sources[key] = task
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        tasks[kind] = task
    done, _ = await asyncio.wait(set(tasks.values()), timeout=timeout)
    errors, results = {}, {}
    for kind, task in tasks.items():
        if task not in done:
            errors[kind] = '数据源请求超时，稍后可重新拉取'
            continue
        try:
            results[kind] = task.result()
            if not results[kind]:
                errors[kind] = '来源返回空数据'
        except Exception as exc:
            errors[kind] = type(exc).__name__ + ': ' + str(exc)[:180]
    sectors = results.get('sectors', [])
    flow = next((r for r in results.get('flow', []) if (r.get('名称') or r.get('行业')) == name), None)
    if name and flow is None and 'flow' not in errors:
        errors['flow'] = '来源未返回此行业的资金数据'
    summary = next((r for r in sectors if r.get('板块名称') == name), None)
    if name and summary is None and 'sectors' not in errors:
        errors['summary'] = '来源行业目录中没有此名称，请使用目录中的完整行业名'
    return {'name': name, 'market': 'CN', 'sectors': sectors, 'summary': summary,
            'constituents': results.get('constituents', []), 'flow': flow, 'errors': errors,
            'source': 'AKShare · 东方财富行业板块 / 行业资金流',
            'received_at': datetime.now(timezone.utc).isoformat(), 'exchange_time': None,
            'freshness': 'unknown',
            'flow_note': '资金流为来源按成交分类计算的行业主力资金统计，金额字段单位为元；它不等于北向资金或基金真实申赎。'}


def _cached(db: Callable, key: str, force: bool) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    with db() as conn:
        row = conn.execute('SELECT payload,updated_at,last_error FROM workspace_cache WHERE cache_key=?', (key,)).fetchone()
    cached = json.loads(row['payload']) if row and row['payload'] else None
    if cached:
        cached.setdefault('state', 'partial' if cached.get('errors') else 'available')
    if cached and not force:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row['updated_at'])).total_seconds()
        if age < (RETRY_SECONDS if row['last_error'] else TTL_SECONDS):
            return cached, {**cached, 'cached': True}
    return cached, None


async def get_sector_data(db: Callable, name: str | None = None, force: bool = False, timeout: int = 20) -> dict[str, Any]:
    name = name.strip() if name else None
    key = 'sector:' + (name or '__catalog__')
    cached, fresh = _cached(db, key, force)
    if fresh:
        return fresh
    async with _locks.setdefault(key, asyncio.Lock()):
        cached, fresh = _cached(db, key, force)
        if fresh:
            return fresh
        data = await _fetch(name, timeout)
        has_data = bool((data['summary'] or data['constituents'] or data['flow']) if name else data['sectors'])
        error = '; '.join(data['errors'].values()) if data['errors'] else None
        if not has_data and cached and cached.get('received_at'):
            data = {**cached, 'state': 'stale', 'freshness': 'stale', 'last_error': error, 'cached': True}
        elif has_data:
            data.update(state='partial' if error else 'available', cached=False)
        else:
            data.update(state='unavailable', freshness='unavailable', received_at=None, last_error=error, cached=False)
        with db() as conn:
            conn.execute('INSERT INTO workspace_cache(cache_key,payload,updated_at,last_error) VALUES(?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,last_error=excluded.last_error',
                         (key, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), error))
        return data
