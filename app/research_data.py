"""Bounded public research collection. Index identifiers never enter paper routing."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import math
import os
import re
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.providers.sector_provider import _records

INDEX_CATALOG = [
    {'id':'INDEX:SH000001','name':'上证指数','market':'CN','symbol':'sh000001'},
    {'id':'INDEX:SZ399001','name':'深证成指','market':'CN','symbol':'sz399001'},
    {'id':'INDEX:SH000300','name':'沪深300','market':'CN','symbol':'sh000300'},
    {'id':'INDEX:SH000905','name':'中证500','market':'CN','symbol':'sh000905'},
    {'id':'INDEX:SZ399006','name':'创业板指','market':'CN','symbol':'sz399006'},
    {'id':'INDEX:SH000688','name':'科创50','market':'CN','symbol':'sh000688'},
    {'id':'INDEX:HSI','name':'恒生指数','market':'HK','symbol':'恒生指数'},
    {'id':'INDEX:SPX','name':'标普500','market':'US','symbol':'标普500'},
    {'id':'INDEX:DJIA','name':'道琼斯','market':'US','symbol':'道琼斯'},
    {'id':'INDEX:NASDAQ','name':'纳斯达克','market':'US','symbol':'纳斯达克'},
]
INDEXES = {row['id']:row for row in INDEX_CATALOG}
JOBS: dict[str, asyncio.Task] = {}
LIMIT = asyncio.Semaphore(2)


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch(kind, key):
    if kind in {'omo','rotation','news_cls','news_em'}:
        from app.market_context import fetch_context
        return fetch_context(kind,key)
    import akshare as ak
    source = 'AKShare · 东方财富'
    if kind == 'index':
        meta = INDEXES[key]
        if meta['market'] == 'CN':
            frame = ak.stock_zh_index_daily(symbol=meta['symbol'])
            source = 'AKShare · stock_zh_index_daily · 新浪'
        else:
            try:
                if meta['market']=='HK':
                    frame=ak.stock_hk_index_daily_sina(symbol='HSI')
                    source='AKShare · stock_hk_index_daily_sina · 新浪'
                else:
                    frame=ak.index_us_stock_sina(symbol={'INDEX:SPX':'.INX','INDEX:DJIA':'.DJI','INDEX:NASDAQ':'.IXIC'}[key])
                    source='AKShare · index_us_stock_sina · 新浪'
            except Exception:
                frame=ak.index_global_hist_em(symbol=meta['symbol'])
                source='AKShare · index_global_hist_em · 东方财富' 
        frame = frame.rename(columns={'日期':'bar_time','date':'bar_time','今开':'open','最高':'high','最低':'low','最新价':'close'})
        cutoff = datetime.now(ZoneInfo('America/New_York' if meta['market']=='US' else 'Asia/Shanghai')).date().isoformat()
        rows = []
        for raw in _records(frame):
            stamp = str(raw.get('bar_time',''))[:10]
            try:
                date.fromisoformat(stamp)
                values = [float(raw[k]) for k in ('open','high','low','close')]
            except (ValueError, TypeError, KeyError):
                continue
            if stamp >= cutoff or not all(math.isfinite(v) and v > 0 for v in values):
                continue
            o,h,l,c = values
            if h < max(o,c,l) or l > min(o,c,h):
                continue
            rows.append({'bar_time':stamp, 'open':o, 'high':h, 'low':l, 'close':c,
                         'volume':raw.get('volume'), 'volume_unit':'unknown'})
        # Keep at most ten years and one row per date; do not synthesize missing days.
        rows = sorted({r['bar_time']:r for r in rows}.values(), key=lambda r:r['bar_time'])[-2600:]
        note = '指数点位，不能直接下单；仅收录当地日期早于今天的日线。成交量单位未确认，不跨源比较。'
    elif kind == 'market_flow':
        rows = _records(ak.stock_market_fund_flow())[-120:][::-1]
        source += ' · stock_market_fund_flow'
        note = '沪深大盘成交分类资金估计，金额单位元；不是机构账户真实流水、基金申赎或北向净买入。日期见原始字段。'
    elif kind == 'fund':
        code, year = key.split(':')
        if not re.fullmatch(r'\d{6}',code) or not 2000 <= int(year) <= date.today().year:
            raise ValueError('基金代码或年份不正确')
        rows = _records(ak.fund_portfolio_hold_em(symbol=code,date=year))[:100]
        source += ' · fund_portfolio_hold_em · 天天基金'
        note = '基金定期披露持仓，不代表实时仓位；报告期及金额单位以原始字段为准。'
    else:
        raise ValueError('未知采集类型')
    return {'rows':rows, 'source':source, 'note':note, 'received_at':now(), 'source_time':None,
            'state':'available' if rows else 'empty', 'freshness':'end_of_day' if kind=='index' and rows else 'unknown'}


class ProviderError(RuntimeError):
    pass


async def _worker(kind, key):
    async with LIMIT:
        allowed = {'PATH','LANG','LC_ALL','TZ','SSL_CERT_FILE','SSL_CERT_DIR','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy'}
        env = {k:v for k,v in os.environ.items() if k in allowed}
        env['PYTHONIOENCODING'] = 'utf-8'
        proc = await asyncio.create_subprocess_exec(sys.executable,'-m','app.research_data','--worker',kind,key,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env,cwd=str(Path(__file__).resolve().parents[1]))
        try:
            output,_ = await asyncio.wait_for(proc.communicate(),timeout=16)
            if proc.returncode or len(output)>3_000_000:
                raise ValueError('来源请求未完成')
            data=json.loads(output)
            if data.get('fetch_error'):
                raise ProviderError(data['fetch_error'])
            return data
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.communicate()


def index_freshness(data, key):
    if not data.get('rows'): return data
    market=INDEXES[key]['market']
    zone='America/New_York' if market=='US' else 'Asia/Shanghai'
    yesterday=datetime.now(ZoneInfo(zone)).date()-timedelta(days=1)
    expected=None
    try:
        import exchange_calendars as xcals
        calendar=xcals.get_calendar({'US':'XNYS','HK':'XHKG','CN':'XSHG'}[market])
        expected=calendar.date_to_session(yesterday.isoformat(),direction='previous').date().isoformat()
    except Exception:
        pass
    data['expected_last_bar']=expected
    if expected and data['rows'][-1]['bar_time']<expected:
        data['state']='stale'; data['freshness']='stale'
        data['error']='指数日线尚未覆盖最近已结束的交易日，保留来源实际返回的历史。'
    return data


def cached(db, kind, key):
    with db() as c:
        row = c.execute('SELECT * FROM workspace_cache WHERE cache_key=?',(f'research:{kind}:{key}',)).fetchone()
    if not row: return None
    data = json.loads(row['payload'])
    data['attempted_at'] = row['updated_at']
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])).total_seconds()
    data['cache_expired'] = age > (86400 if kind=='fund' else (180 if kind.startswith('news_') else 3600))
    if data['cache_expired'] and data.get('rows'):
        data['state']='stale'; data['freshness']='stale'
    return index_freshness(data,key) if kind=='index' else data


async def collect(db, kind, key, refresh=False):
    if kind == 'index' and key not in INDEXES: raise ValueError('请选择已配置的指数')
    old = cached(db,kind,key)
    ttl = 60 if old and old.get('state') in {'error','stale','empty'} else (86400 if kind=='fund' else (60 if kind.startswith('news_') else (600 if kind=='omo' else 300)))
    if old and not refresh and (datetime.now(timezone.utc)-datetime.fromisoformat(old['attempted_at'])).total_seconds()<ttl:
        return {**old,'cached':True}
    jobkey = f'{kind}:{key}'
    task = JOBS.get(jobkey)
    if task is None or task.done():
        # Persist inside the durable collection task, even if the caller stops waiting.
        task = asyncio.create_task(_collect_and_store(db,kind,key,old)); JOBS[jobkey]=task
        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    try:
        return await asyncio.wait_for(asyncio.shield(task),timeout=20)
    except asyncio.TimeoutError:
        return {**(old or {'rows':[],'received_at':None,'source':'公共数据采集','source_time':None}),
                'state':'stale' if old and old.get('rows') else 'pending','freshness':'stale' if old and old.get('rows') else 'unavailable',
                'collection_pending':True,'note':'来源正在采集或排队，任务将在后台保存结果，稍后可刷新查看。','error':'采集尚未完成'}


async def _collect_and_store(db,kind,key,old):
    try:
        data = await _worker(kind,key)
        if not data.get('rows'): raise ValueError('来源返回空数据')
        if kind=='index': data=index_freshness(data,key)
    except Exception as exc:
        error_type=str(exc) if isinstance(exc,ProviderError) else type(exc).__name__
        error = '数据源请求超时' if isinstance(exc,asyncio.TimeoutError) else f'来源未返回有效数据（{error_type}）'
        data = {**old,'state':'stale','freshness':'stale','error':error} if old and old.get('rows') else {
            'state':'error','rows':[],'error':error,'received_at':None,'source_time':None,'source':{'omo':'中国人民银行公告','news_cls':'财联社电报 · AKShare','news_em':'东方财富快讯 · AKShare','rotation':'东方财富行业资金流 · AKShare'}.get(kind,'AKShare 公共数据'),'freshness':'unavailable',
            'note':'来源未返回有效数据，空值不代表零。'}
    digest = hashlib.sha256(json.dumps(data['rows'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    data.update(content_hash=digest, key=key, kind=kind, attempted_at=now(), cached=False, cache_expired=False)
    with db() as c:
        c.execute('INSERT INTO workspace_cache(cache_key,payload,updated_at,last_error) VALUES(?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,last_error=excluded.last_error',
                  (f'research:{kind}:{key}',json.dumps(data,ensure_ascii=False),data['attempted_at'],data.get('error')))
        if kind in {'news_cls','news_em'}:
            from app.market_context import persist_context
            persist_context(c,kind,data)
        if kind=='index' and data['rows']:
            for row in data['rows']:
                c.execute('''INSERT INTO bars(instrument_id,interval,bar_time,open,high,low,close,volume,currency,adjustment,provider,received_at,price_unit,volume_unit)
                VALUES(?,'1d',?,?,?,?,?,?,'PTS','none',?,?,'points','unknown') ON CONFLICT(instrument_id,interval,bar_time,adjustment)
                DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume,provider=excluded.provider,received_at=excluded.received_at''',
                          (key,row['bar_time'],row['open'],row['high'],row['low'],row['close'],row.get('volume'),data['source'],data['received_at']))
    return data


async def refresh_research(db):
    """Collect indices and aggregate flow independently of the quote refresh loop."""
    first=True
    while True:
        for offset in range(0,len(INDEX_CATALOG),2):
            await asyncio.gather(*(collect(db,'index',m['id'],refresh=first) for m in INDEX_CATALOG[offset:offset+2]),return_exceptions=True)
        await collect(db,'market_flow','CN',refresh=first)
        first=False
        await asyncio.sleep(1800)


async def close_workers():
    active=[task for task in JOBS.values() if not task.done()]
    for task in active: task.cancel()
    if active: await asyncio.gather(*active,return_exceptions=True)



if __name__ == '__main__':
    if len(sys.argv)!=4 or sys.argv[1]!='--worker': raise SystemExit(2)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = fetch(sys.argv[2],sys.argv[3])
    except Exception as exc:
        result={'fetch_error':type(exc).__name__}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
