"""Bounded stock dossiers from public structured sources, with per-section provenance.
Eastmoney web endpoints are NOT the licensed Choice OpenAPI.
"""
from __future__ import annotations
import asyncio
import json
import math
import re
import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

from app.providers.sector_provider import _records

JOBS: dict[str, asyncio.Task] = {}
SEMAPHORE = asyncio.Semaphore(3)
SECTIONS = {'profile', 'snapshot', 'financials', 'ownership', 'dividends', 'flow', 'news', 'announcements', 'income', 'balance', 'cashflow', 'holders', 'business', 'reports'}
LABELS = {'profile':'公司概况', 'snapshot':'盘口与估值', 'financials':'财务摘要', 'ownership':'股东户数', 'dividends':'分红记录', 'flow':'个股资金流', 'news':'相关新闻', 'announcements':'公司公告','income':'利润表','balance':'资产负债表','cashflow':'现金流量表','holders':'十大股东','business':'主营业务构成','reports':'机构研报目录'}


def canonical(value: str) -> tuple[str, str]:
    market, _, symbol = value.strip().partition(':')
    market = market.upper()
    if market in {'CN','FUND'} and re.fullmatch(r'\d{6}', symbol):
        return market, symbol
    if market == 'HK' and re.fullmatch(r'\d{1,5}', symbol):
        return market, symbol.zfill(5)
    if market == 'US' and re.fullmatch(r'[A-Za-z0-9.^-]{1,24}', symbol):
        return market, symbol.upper()
    if market == 'GOLD' and re.fullmatch(r'[A-Za-z0-9.()_-]{1,24}', symbol):
        return market, symbol
    raise ValueError('标的代码格式不正确')


def reference_links(market: str, symbol: str):
    if market == 'CN':
        exchange = 'bj' if symbol.startswith(('4','8','92')) else ('sh' if symbol.startswith(('6','9')) else 'sz')
        return [{'label':'东方财富行情', 'url':f'https://quote.eastmoney.com/{exchange}{symbol}.html'},
                {'label':'东方财富个股资料', 'url':f'https://data.eastmoney.com/stockdata/{symbol}.html'},
                {'label':'公司公告原文', 'url':f'https://data.eastmoney.com/notices/stock/{symbol}.html'},
                {'label':'巨潮资讯检索', 'url':'https://www.cninfo.com.cn/new/fulltextSearch?keyWord='+quote(symbol)}]
    if market == 'HK':
        return [{'label':'东方财富港股行情','url':f'https://quote.eastmoney.com/hk/{symbol}.html'},
                {'label':'港交所披露易','url':'https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=zh'}]
    if market == 'US':
        return [{'label':'SEC 公司披露检索','url':'https://www.sec.gov/edgar/search/#/q='+quote(symbol)},
                {'label':'Nasdaq 个股资料','url':'https://www.nasdaq.com/market-activity/stocks/'+quote(symbol.lower())}]
    return [{'label':'东方财富数据中心','url':'https://data.eastmoney.com/'}]


def _futu_cn_snapshot(symbol: str) -> dict[str, Any]:
    """Read-only local OpenD snapshot with its own PE/PB labels and quote time."""
    from futu import OpenQuoteContext, RET_OK
    from app.providers.futu_provider import address, observed_time

    if symbol.startswith(('4', '8', '92')):
        raise ValueError('OpenD 未接入北交所股票快照')
    code = ('SH' if symbol.startswith(('6', '9')) else 'SZ') + '.' + symbol
    host, port = address()
    ctx = OpenQuoteContext(host=host, port=port)
    try:
        ret, frame = ctx.get_market_snapshot([code])
        if ret != RET_OK or getattr(frame, 'empty', True):
            raise RuntimeError('OpenD 未返回股票快照')
        raw = frame.iloc[0].to_dict()
    finally:
        ctx.close()

    def finite(field: str, positive: bool = False) -> float | None:
        try:
            value = float(raw.get(field))
            return value if math.isfinite(value) and (not positive or value > 0) else None
        except (TypeError, ValueError):
            return None

    if finite('last_price', True) is None:
        raise ValueError('OpenD 未返回有效最新价')
    fields = [('股票代码', code), ('股票简称', str(raw.get('name') or '')),
              ('最新价', finite('last_price', True)), ('今开', finite('open_price', True)),
              ('最高', finite('high_price', True)), ('最低', finite('low_price', True)),
              ('昨收', finite('prev_close_price', True)), ('成交量（股）', finite('volume')),
              ('成交额（元）', finite('turnover')), ('换手率（%）', finite('turnover_rate'))]
    if raw.get('equity_valid'):
        fields += [('市盈率（富途口径）', finite('pe_ratio', True)),
                   ('市盈率（TTM）', finite('pe_ttm_ratio', True)),
                   ('市净率', finite('pb_ratio', True))]
    source_time = observed_time(raw.get('update_time'), 'CN')
    return {'state':'available','rows':[{'item':label,'value':value} for label,value in fields],
            'source':'富途 OpenD · 只读市场快照',
            'unit_note':'价格=元/股；成交量=股；金额=元；换手率=百分比；PE/PB 为倍数，富途 PE 与东方财富动态 PE 口径不同。',
            'received_at':datetime.now(timezone.utc).isoformat(),'source_time':source_time,
            'freshness':'unknown','note':'行情权限可能是延迟报价；以来源更新时间判断时效，不用作交易撮合价格。'}


def _fetch(market: str, symbol: str, section: str) -> dict[str, Any]:
    import akshare as ak
    source, unit = 'AKShare · 东方财富公共网页数据', '保留来源字段单位；未标注时不推断'
    if market == 'CN':
        exchange = 'bj' if symbol.startswith(('4','8','92')) else ('sh' if symbol.startswith(('6','9')) else 'sz')
        if section == 'profile':
            rows = _records(ak.stock_profile_cninfo(symbol=symbol))
            source = 'AKShare · 巨潮资讯公司概况'
        elif section == 'snapshot':
            try:
                return _futu_cn_snapshot(symbol)
            except Exception:
                pass  # OpenD may be unavailable; retain the public source fallback.
            import httpx
            fields = {'f57':'股票代码','f58':'股票简称','f43':'最新价','f46':'今开','f44':'最高','f45':'最低',
                      'f60':'昨收','f169':'涨跌额','f170':'涨跌幅（%）','f47':'成交量（手）','f48':'成交额（元）',
                      'f168':'换手率（%）','f50':'量比','f162':'市盈率（动）','f167':'市净率',
                      'f116':'总市值（元）','f117':'流通市值（元）','f84':'总股本（股）','f85':'流通股（股）',
                      'f127':'行业','f189':'上市日期','f51':'涨停价','f52':'跌停价'}
            with httpx.Client(timeout=12, follow_redirects=False) as client:
                response = client.get('https://push2.eastmoney.com/api/qt/stock/get', params={
                    'fltt':'2','invt':'2','secid':('1' if exchange=='sh' else '0')+'.'+symbol,
                    'fields':','.join([*fields,'f86'])})
                response.raise_for_status()
                data = response.json().get('data')
            if not isinstance(data,dict):
                raise RuntimeError('来源未返回此标的报价')
            rows = [{'item':label,'value':data.get(code) if data.get(code)!='-' else None} for code,label in fields.items()]
            stamp = data.get('f86')
            source_time = datetime.fromtimestamp(float(stamp), timezone.utc).isoformat() if stamp and str(stamp).isdigit() else None
            return {'state':'available','rows':rows,'source':'东方财富公开行情查询（非 Choice OpenAPI）',
                    'unit_note':'价格=元/股；成交量=手；成交额/市值=元；换手率/涨跌幅=百分比。PE使用来源动态口径。',
                    'received_at':datetime.now(timezone.utc).isoformat(),'source_time':source_time,
                    'freshness':'unknown','note':'仅为来源返回的报价快照，不保证实时性；不用于覆盖交易撮合报价。'}
        elif section == 'financials':
            frame = ak.stock_financial_abstract(symbol=symbol)
            # Select latest source columns instead of inventing a fiscal period.
            rows = _records(frame.iloc[:24, :10])
            source = 'AKShare · 新浪财务摘要'
            unit = '按原始报告期列与指标名称读取；比率、每股与金额不可混用'
        elif section == 'ownership':
            frame = ak.stock_zh_a_gdhs_detail_em(symbol=symbol)
            rows = _records(frame.tail(12).iloc[::-1])
            unit = '股东户数为披露期统计；不是实时持有人或完整十大股东名册'
        elif section in {'income','balance','cashflow'}:
            functions = {'income':ak.stock_profit_sheet_by_report_em,'balance':ak.stock_balance_sheet_by_report_em,'cashflow':ak.stock_cash_flow_sheet_by_report_em}
            mappings = {
                'income':{'TOTAL_OPERATE_INCOME':'营业总收入（元）','OPERATE_INCOME':'营业收入（元）','OPERATE_PROFIT':'营业利润（元）','TOTAL_PROFIT':'利润总额（元）','NETPROFIT':'净利润（元）','PARENT_NETPROFIT':'归母净利润（元）','BASIC_EPS':'基本每股收益（元/股）','DILUTED_EPS':'稀释每股收益（元/股）'},
                'balance':{'TOTAL_ASSETS':'资产总计（元）','TOTAL_LIABILITIES':'负债合计（元）','TOTAL_EQUITY':'权益合计（元）','TOTAL_CURRENT_ASSETS':'流动资产（元）','TOTAL_CURRENT_LIAB':'流动负债（元）','MONETARYFUNDS':'货币资金（元）','ACCOUNTS_RECE':'应收账款（元）','INVENTORY':'存货（元）','GOODWILL':'商誉（元）','SHORT_LOAN':'短期借款（元）','LONG_LOAN':'长期借款（元）'},
                'cashflow':{'NETCASH_OPERATE':'经营活动现金净额（元）','NETCASH_INVEST':'投资活动现金净额（元）','NETCASH_FINANCE':'筹资活动现金净额（元）','NET_INCREASE_CASH_EQUI':'现金等价物净增加（元）','END_CASH_EQUI':'期末现金等价物（元）','SALES_SERVICES':'销售商品劳务收到现金（元）','PAY_STAFF_CASH':'支付职工现金（元）'}
            }
            frame = functions[section](symbol=exchange.upper()+symbol)
            if 'REPORT_DATE' in frame.columns:
                frame = frame.sort_values('REPORT_DATE',ascending=False)
            records = _records(frame.head(8))
            rows = [{'指标':label, **{str(row.get('REPORT_DATE','报告期未提供'))[:10]:row.get(field) for row in records}}
                    for field,label in mappings[section].items() if any(field in row for row in records)]
            rows += [{'指标':'披露/更新日期', **{str(row.get('REPORT_DATE','报告期未提供'))[:10]:row.get('NOTICE_DATE') or row.get('UPDATE_DATE') for row in records}}] if rows else []
            unit = '按来源报告期累计口径展示，金额为元/每股为元每股；未转换为单季度，未推算缺项。'
        elif section == 'holders':
            counts = ak.stock_zh_a_gdhs_detail_em(symbol=symbol)
            dates = [str(row.get('股东户数统计截止日',''))[:10] for row in _records(counts)]
            dates = [value for value in dates if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)]
            period = max(dates) if dates else None
            rows = [{'报告期':period,**row} for row in _records(ak.stock_gdfx_top_10_em(symbol=exchange+symbol,date=period.replace('-','')))[:10]] if period else []
            unit = '报告期取最近可得股东户数披露中的明确截止日；持股为股、占比按来源列。不是实时组合。'
        elif section == 'business':
            frame = ak.stock_zygc_em(symbol=exchange.upper()+symbol)
            rows = _records(frame.head(30))
            unit = '主营构成按原始报告期和分类，金额/占比保留来源列单位。'
        elif section == 'reports':
            rows = _records(ak.stock_research_report_em(symbol=symbol).head(20))
            unit = '仅聚合来源公开研报目录/评级等元信息；不自动抓取或保存付费研报全文。'
        elif section == 'dividends':
            rows = _records(ak.stock_history_dividend_detail(symbol=symbol, indicator='分红').head(20))
            source = 'AKShare · 新浪分红历史'
            unit = '分红/送转口径以原始列为准，未对除权前后价格重新复权'
        elif section == 'flow':
            rows = _records(ak.stock_individual_fund_flow(stock=symbol, market=exchange).tail(20).iloc[::-1])
            unit = '成交分类资金估计，金额单位元；不是北向实时成交或机构真实账户流水'
        elif section == 'news':
            rows = _records(ak.stock_news_em(symbol=symbol).head(20))
            unit = '来源相关新闻；不等同公司正式公告'
        elif section == 'announcements':
            import httpx
            with httpx.Client(timeout=12, follow_redirects=False) as client:
                response = client.get('https://np-anotice-stock.eastmoney.com/api/security/ann', params={
                    'sr':-1,'page_size':20,'page_index':1,'ann_type':'A','client_source':'web','stock_list':symbol,'f_node':0,'s_node':0})
                response.raise_for_status()
                records = response.json().get('data', {}).get('list', [])
            rows = [{'标题':str(row.get('title',''))[:300], '公告日期':str(row.get('notice_date',''))[:19],
                     '原文链接':f"https://data.eastmoney.com/notices/detail/{symbol}/{row['art_code']}.html"}
                    for row in records[:20] if re.fullmatch(r'[A-Za-z0-9]+', str(row.get('art_code','')))]
            source = '东方财富公告公开查询接口（非官方 OpenAPI 合约）'
            unit = '公告日期不是行情时间；以链接中的公告原文为准'
        else:
            rows = []
    elif market == 'HK' and section == 'profile':
        rows = _records(ak.stock_hk_company_profile_em(symbol=symbol))
    elif market == 'HK' and section == 'financials':
        rows = _records(ak.stock_financial_hk_analysis_indicator_em(symbol=symbol, indicator='年度').head(8))
    else:
        return {'state':'unsupported', 'rows':[], 'source':None, 'unit_note':'这个市场的此类资料尚未接入；可通过原始资料链接查询。', 'received_at':None, 'source_time':None}
    # Bound text, columns and row count before persistence or transmission to an LLM.
    rows = [{k:(v[:4000] if isinstance(v,str) else v) for k,v in list(row.items())[:40]} for row in rows[:40]]
    return {'state':'available' if rows else 'empty', 'rows':rows, 'source':source, 'unit_note':unit,
            'received_at':datetime.now(timezone.utc).isoformat(), 'source_time':None,
            'freshness':'unknown', 'note':'接收时间不代表来源行情或披露时间，报告期/日期以原始字段为准。'}


async def _job(market, symbol, section):
    # Kill stalled scrapers instead of leaving unbounded blocking threads behind.
    async with SEMAPHORE:
        allowed = {'PATH','HOME','LANG','LC_ALL','TZ','SSL_CERT_FILE','SSL_CERT_DIR','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy',
                   'CONTAINER_RUNTIME','FUTU_OPEND_HOST','FUTU_OPEND_PORT'}
        env = {k:v for k,v in os.environ.items() if k in allowed}
        env['PYTHONIOENCODING'] = 'utf-8'
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.providers.instrument_provider',
                    '--worker', market, symbol, section, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, env=env,
                    cwd=str(__import__('pathlib').Path(__file__).resolve().parents[2]))
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=16)
            if process.returncode or len(output)>2_000_000:
                raise RuntimeError('来源请求未完成')
            return json.loads(output)
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()


async def section_data(db: Callable, instrument_id: str, section: str, refresh: bool = False):
    market, symbol = canonical(instrument_id)
    if section not in SECTIONS:
        raise ValueError('不支持的资料类别')
    key = f'dossier:{market}:{symbol}:{section}'
    now = datetime.now(timezone.utc)
    with db() as c:
        row = c.execute('SELECT * FROM workspace_cache WHERE cache_key=?', (key,)).fetchone()
    cached = json.loads(row['payload']) if row and row['payload'] else None
    ttl = 120 if cached and cached.get('state') in {'error','stale','empty'} else (300 if section in {'snapshot','flow','news','announcements'} else 86400)
    if cached and not refresh and (now-datetime.fromisoformat(row['updated_at'])).total_seconds() < ttl:
        return {**cached,'cached':True}
    task = JOBS.get(key)
    if not task or task.done():
        task = asyncio.create_task(_job(market,symbol,section))
        JOBS[key] = task
        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=18)
    except Exception as exc:
        # Do not persist raw upstream errors or URLs that might contain credentials.
        error = '数据源请求超时' if isinstance(exc, asyncio.TimeoutError) else f'来源暂不可用（{type(exc).__name__}）'
        if cached and cached.get('rows'):
            result = {**cached, 'state':'stale', 'freshness':'stale','error':error}
        else:
            result = {'state':'error','rows':[],'error':error,'source':'公共数据适配器','received_at':None,'source_time':None,'unit_note':'未取得有效资料，保留为空。'}
    result.update(instrument_id=f'{market}:{symbol}', section=section, label=LABELS[section], cached=False)
    with db() as c:
        c.execute('INSERT INTO workspace_cache(cache_key,payload,updated_at,last_error) VALUES(?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,last_error=excluded.last_error',
                  (key,json.dumps(result,ensure_ascii=False),now.isoformat(),result.get('error')))
    return result


async def dossier(db: Callable, instrument_id: str, sections: list[str], refresh: bool = False):
    market, symbol = canonical(instrument_id)
    if not sections or len(sections)>8 or any(s not in SECTIONS for s in sections):
        raise ValueError('资料类别不正确')
    results = await asyncio.gather(*(section_data(db,f'{market}:{symbol}',s,refresh) for s in dict.fromkeys(sections)))
    return {'instrument_id':f'{market}:{symbol}', 'sections':{r['section']:r for r in results}, 'links':reference_links(market,symbol),
            'scope_note':'按分区查看实际来源：可能为富途只读快照或公开网页数据；公开网页与持牌 Choice OpenAPI 是不同服务。部分市场资料需要额外数据权限。'}


if __name__ == '__main__':
    import contextlib
    import io
    if len(sys.argv) != 5 or sys.argv[1] != '--worker':
        raise SystemExit(2)
    worker_market, worker_symbol = canonical(sys.argv[2] + ':' + sys.argv[3])
    if sys.argv[4] not in SECTIONS:
        raise SystemExit(2)
    with contextlib.redirect_stdout(io.StringIO()):
        worker_result = _fetch(worker_market, worker_symbol, sys.argv[4])
    print(json.dumps(worker_result, ensure_ascii=False))
