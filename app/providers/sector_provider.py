"""Best-effort industry data; independent sources can return partial snapshots."""
from __future__ import annotations

import asyncio
import json
import math
import re
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


def _ths_constituents(name: str, ak: Any) -> list[dict[str, Any]]:
    """Read bounded public THS industry pages when Eastmoney constituents fail."""
    import requests
    from bs4 import BeautifulSoup

    catalog = _records(ak.stock_board_industry_name_ths())
    code = next((str(r['code']) for r in catalog if r.get('name') == name), None)
    if not code or not re.fullmatch(r'\d{6}', code):
        return []
    base = f'https://q.10jqka.com.cn/thshy/detail/code/{code}/'
    rows: list[dict[str, Any]] = []
    pages = 1
    for page in range(1, 11):
        url = base if page == 1 else f'{base}page/{page}/'
        response = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.select_one('table.m-pager-table')
        if table is None:
            raise ValueError('同花顺成分股表缺失')
        if page == 1:
            pager = soup.select_one('.page_info')
            if pager:
                match = re.fullmatch(r'\d+/(\d+)', pager.get_text(strip=True))
                if match: pages = int(match[1])
        for tr in table.select('tr'):
            cells = [td.get_text(' ', strip=True) for td in tr.select('td')]
            if len(cells) < 5 or not re.fullmatch(r'\d{6}', cells[1]):
                continue
            def number(value: str) -> float | None:
                try:
                    value = float(value.rstrip('%'))
                    return value if math.isfinite(value) else None
                except ValueError:
                    return None
            rows.append({'代码': cells[1], '名称': cells[2], '最新价': number(cells[3]),
                         '涨跌幅': number(cells[4]), '_source': '同花顺'})
        if page >= pages: break
    if pages > 10 and rows: rows[0]['_truncated'] = True
    return rows


def _fetch_source(kind: str, name: str | None) -> list[dict[str, Any]]:
    import akshare as ak
    if kind == 'sectors':
        try:
            return [{**r, '_source': '东方财富'} for r in _records(ak.stock_board_industry_name_em())]
        except Exception:
            return [{**r, '板块名称': r['板块'], '_source': '同花顺'}
                    for r in _records(ak.stock_board_industry_summary_ths())]
    if kind == 'constituents':
        try:
            return [{**r, '_source': '东方财富'} for r in _records(ak.stock_board_industry_cons_em(symbol=name))]
        except Exception:
            return _ths_constituents(name, ak)
    try:
        return [{**r, '_source': '东方财富'} for r in _records(
            ak.stock_sector_fund_flow_rank(indicator='今日', sector_type='行业资金流'))]
    except Exception:
        rows=[]
        for r in _records(ak.stock_fund_flow_industry(symbol='即时')):
            try:
                net=float(r['净额'])*100_000_000
                if not math.isfinite(net):net=None
            except (TypeError,ValueError,KeyError):net=None
            rows.append({**r, '名称':r['行业'], '资金净额-元':net, '_source':'同花顺'})
        return rows


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
    if any(r.get('_truncated') for r in results.get('constituents', [])):
        errors['constituents_coverage'] = '同花顺成分股超过10页，仅返回前200只；不可据此推断全行业家数'
    sources={kind:next((r.get('_source') for r in results.get(kind,[]) if r.get('_source')), '东方财富')
             for kind in ('sectors','constituents','flow') if results.get(kind)}
    return {'name': name, 'market': 'CN', 'sectors': sectors, 'summary': summary,
            'constituents': results.get('constituents', []), 'flow': flow, 'errors': errors,
            'source': 'AKShare · '+ ' / '.join(sorted(set(sources.values()))) if sources else 'AKShare · 行业数据',
            'component_sources':sources,
            'received_at': datetime.now(timezone.utc).isoformat(), 'exchange_time': None,
            'freshness': 'unknown',
            'flow_note': ('同花顺行业资金净额，原站单位亿元，已换算为元；非东方财富主力净流入，也不是北向资金或基金真实申赎。'
                          if sources.get('flow')=='同花顺' else
                          '东方财富行业主力资金为来源按成交分类计算的统计，金额字段单位为元；不等于北向资金或基金真实申赎。')}


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
