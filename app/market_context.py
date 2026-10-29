"""Public news, official OMO disclosures and descriptive sector rotation context."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

PBC_URL='https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html'
SECTOR_WORDS={
    '银行':['银行','降准','降息','存款利率'], '证券':['券商','证券','资本市场'],
    '半导体':['半导体','芯片','集成电路','光刻'], '计算机':['算力','人工智能','AI','数据中心','软件'],
    '通信':['通信','光模块','5G','6G'], '电力设备':['光伏','储能','锂电','新能源','电池'],
    '医药':['医药','创新药','医疗','集采'], '有色金属':['有色','铜','铝','黄金','稀土'],
    '煤炭':['煤炭','焦煤'], '房地产':['房地产','地产','住房'], '国防军工':['军工','国防','航天'],
    '汽车':['汽车','智驾','自动驾驶'], '食品饮料':['白酒','食品','消费'],
}


def stamp(): return datetime.now(timezone.utc).isoformat()


class TextPage(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[];self.links=[];self.tables=[];self.table=None;self.row=None;self.cell=None;self.anchor=None;self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}: self.skip+=1
        if self.skip: return
        if tag=='a': self.anchor=[dict(attrs).get('href',''),'']
        if tag=='table':
            if self.table is not None: self.tables.append(self.table)
            self.table=[]
        if tag=='tr': self.row=[]
        if tag in {'td','th'}: self.cell=''
        if tag in {'p','div','tr','br','h1','h2'}: self.text.append('\n')
    def handle_data(self,data):
        if self.skip:return
        self.text.append(data)
        if self.anchor is not None:self.anchor[1]+=data
        if self.cell is not None:self.cell+=data
    def handle_endtag(self,tag):
        if tag in {'script','style'} and self.skip: self.skip-=1;return
        if self.skip:return
        if tag=='a' and self.anchor is not None:self.links.append(tuple(self.anchor));self.anchor=None
        if tag in {'td','th'} and self.cell is not None:
            if self.row is not None:self.row.append(re.sub(r'\s+','',self.cell))
            self.cell=None
        if tag=='tr' and self.row is not None:
            if self.table is not None:self.table.append(self.row)
            self.row=None
        if tag=='table' and self.table is not None:self.tables.append(self.table);self.table=None
        if tag in {'p','div','tr','br'}:self.text.append('\n')
    def plain(self):return re.sub(r'[ \t\r]+',' ',''.join(self.text))


def _official_page(url):
    import httpx
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='www.pbc.gov.cn' or not parsed.path.startswith('/zhengcehuobisi/'):
        raise ValueError('非允许的央行公告来源')
    with httpx.Client(timeout=4,follow_redirects=False) as client:
        response=client.get(url,headers={'User-Agent':'Mozilla/5.0 finfreedom research personal use'})
        response.raise_for_status()
        if len(response.content)>2_000_000:raise ValueError('公告超出大小限制')
        page=TextPage(); page.feed(response.content.decode('utf-8',errors='replace'));return page


def _omo_article(url,title):
    try:
        page=_official_page(url);plain=page.plain()
        published=re.search(r'\b(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})',plain)
        if not published: return None
        body=plain[plain.find(published.group()):]
        end=body.find('中国人民银行公开市场业务操作室')
        if end>=0:body=body[:end]
        operations=[]
        for table in page.tables:
            for i,header in enumerate(table):
                if '期限' not in header or not any(k in header for k in ['操作量','中标量']):continue
                for row in table[i+1:]:
                    if len(row)!=len(header):continue
                    item=dict(zip(header,row));tenor=item.get('期限','')
                    amount=item.get('中标量',item.get('操作量',''))
                    match=re.fullmatch(r'([\d.,]+)亿元',amount)
                    if not re.fullmatch(r'\d+天|隔夜',tenor) or not match:continue
                    rate=re.fullmatch(r'([\d.]+)%',item.get('操作利率',''))
                    operations.append({'tenor':tenor,'amount_yi':float(match[1].replace(',','')),
                                       'rate_percent':float(rate[1]) if rate else None,'raw':item})
        # Supplemental overnight operations can be in prose outside the table.
        for amount,tenor in re.findall(r'开展(?:了)?\s*([\d,]+(?:\.\d+)?)亿元\s*(隔夜|\d+天)期?逆回购',body):
            amount=float(amount.replace(',',''))
            if not any(x['tenor']==tenor and x['amount_yi']==amount for x in operations):
                operations.append({'tenor':tenor,'amount_yi':amount,'rate_percent':None,'raw':'公告正文明确披露'})
        return {'title':title.strip(),'published_at':published[1]+'T'+published[2]+'+08:00',
                'operation_date':published[1],'url':url,'operations':operations,'excerpt':body[:4500],
                'maturity_amount_yi':None,'net_injection_yi':None,
                'note':'期限分别列示；没有足够到期数据，不计算净投放。利率未披露保持为空。'}
    except Exception:return None


def fetch_context(kind,key):
    from app.providers.sector_provider import _records
    if kind=='omo':
        page=_official_page(PBC_URL)
        links=[]
        for href,title in page.links:
            if re.search(r'公开市场业务交易公告\s*[\[［【]?20\d{2}',title):
                url=urljoin(PBC_URL,href)
                if url!=PBC_URL and (url,title) not in links:links.append((url,title))
        if not links:raise ValueError('公告目录未返回有效链接')
        with ThreadPoolExecutor(max_workers=3) as pool:rows=[x for x in pool.map(lambda x:_omo_article(*x),links[:6]) if x]
        rows.sort(key=lambda x:x['published_at'],reverse=True)
        return {'rows':rows,'state':'available' if rows else 'empty','source':'中国人民银行 · 公开市场业务交易公告',
                'source_url':PBC_URL,'received_at':stamp(),'source_time':rows[0]['published_at'] if rows else None,
                'freshness':'disclosure','note':'央行逆回购是公开市场流动性投放操作；不等同个人账户国债逆回购交易。按期限展示公告原文，到期/净投放未取得则为空。'}
    import akshare as ak
    if kind=='rotation':
        if key not in {'今日','5日','10日'}:raise ValueError('不支持的轮动周期')
        # Use one industry taxonomy for all windows. Eastmoney's push2 endpoint can
        # be unreachable from the deployed network; THS has independent 1/5/10d data.
        full=_ths_rotation_rows(_records(ak.stock_fund_flow_industry(
            symbol={'今日':'即时','5日':'5日排行','10日':'10日排行'}[key])),key)
        rows=full[:1000]
        return {'rows':rows,'state':'available' if rows else 'empty','source':f'AKShare · 同花顺行业资金流 · {key}',
                'source_row_count':len(full),'sample_truncated':len(full)>1000,'source_time':None,'received_at':stamp(),'freshness':'unknown','note':'行业涨跌和成交分类资金估计；源未提供明确行情时点，接收时间不是交易所时点。'}
    if kind not in {'news_cls','news_em'}:raise ValueError('不支持的数据源')
    raw=_records(ak.stock_info_global_cls(symbol='全部') if kind=='news_cls' else ak.stock_info_global_em())
    rows=[]
    for item in raw[:200]:
        published=str(item.get('发布时间',''))
        if item.get('发布日期'):published=str(item['发布日期'])+' '+published
        try:
            dt=datetime.fromisoformat(published)
            if not dt.tzinfo:dt=dt.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
            published=dt.isoformat()
        except ValueError:published=None
        title=str(item.get('标题',''))[:400]; content=str(item.get('内容') or item.get('摘要') or '')[:6000]
        url=str(item.get('链接') or ('https://www.cls.cn/telegraph' if kind=='news_cls' else 'https://kuaixun.eastmoney.com/7_24.html'))
        if urlsplit(url).scheme not in {'http','https'}:url=None
        text=title+' '+content
        sectors=[name for name,words in SECTOR_WORDS.items() if any(w.lower() in text.lower() for w in words)]
        rows.append({'title':title,'content':content,'published_at':published,'url':url,'matched_sectors':sectors,
                     'event_type':'货币政策/流动性' if any(w in text for w in ('逆回购','降准','降息','央行')) else '财经快讯',
                     'association_note':'关键词关联候选，不是已确认的板块影响或因果关系。'})
    rows.sort(key=lambda x:x['published_at'] or '',reverse=True)
    return {'rows':rows,'state':'available' if rows else 'empty','source':'财联社电报 · AKShare' if kind=='news_cls' else '东方财富财经快讯 · AKShare',
            'source_time':rows[0]['published_at'] if rows else None,'received_at':stamp(),'freshness':'unknown',
            'note':'公共快讯轮询，无秒级实时保证；发布时间与首次采集时间分开记录，历史策略不能使用当时未获取的新闻。'}


def initialize_context(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS research_news(news_id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT NOT NULL,published_at TEXT,url TEXT,first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,
            content_hash TEXT NOT NULL, associations_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_news_published ON research_news(published_at);
        CREATE TABLE IF NOT EXISTS sector_rotation_snapshots(observed_date TEXT PRIMARY KEY,received_at TEXT NOT NULL,
            payload TEXT NOT NULL,sample_hash TEXT NOT NULL);
        ''')


def persist_context(c,kind,data):
    if kind not in {'news_cls','news_em'} or data['state']!='available':return
    for row in data['rows']:
        digest=hashlib.sha256((row['title']+'\n'+row['content']).encode()).hexdigest()
        nid=hashlib.sha256((kind+str(row['published_at'])+row['title']).encode()).hexdigest()[:32]
        c.execute('''INSERT INTO research_news VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(news_id) DO UPDATE SET
                     last_seen_at=excluded.last_seen_at''',
                  (nid,data['source'],row['title'],row['content'],row['published_at'],row['url'],data['received_at'],data['received_at'],digest,json.dumps(row['matched_sectors'],ensure_ascii=False)))


async def news_context(db,query='',limit=30,refresh=False):
    from app.research_data import collect,cached
    enabled=__import__('os').getenv('AKSHARE_ENABLED','true').lower()=='true'
    datasets=await asyncio.gather(*(collect(db,k,'ALL',refresh) for k in ('news_cls','news_em'))) if enabled else [cached(db,k,'ALL') or {'source':k,'state':'disabled'} for k in ('news_cls','news_em')]
    with db() as c:
        rows=c.execute('SELECT * FROM research_news WHERE (?=\'\' OR title LIKE ? OR content LIKE ? OR associations_json LIKE ?) ORDER BY published_at DESC,first_seen_at DESC LIMIT ?',
                       (query,*[f'%{query}%']*3,min(100,max(1,limit)))).fetchall()
    results=[{**dict(r),'matched_sectors':json.loads(r['associations_json'])} for r in rows]
    available=any(x.get('state')=='available' for x in datasets)
    return {'rows':results,'state':('available' if all(x.get('state')=='available' for x in datasets) else 'partial') if available else ('stale' if results else 'unavailable'),
            'sources':[{k:d.get(k) for k in ('source','state','source_time','received_at','attempted_at','error')} for d in datasets],
            'query':query,'note':'最多返回100条本机已采集新闻，不是完整新闻档案；关键词板块关联需人工或模型核实。',
            'unverified_causality':True}


async def liquidity_context(db,refresh=False):
    from app.research_data import collect,cached
    if __import__('os').getenv('AKSHARE_ENABLED','true').lower()!='true':
        return cached(db,'omo','PBC') or {'rows':[],'state':'disabled','note':'公共采集已关闭'}
    return await collect(db,'omo','PBC',refresh)


def finite(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None


def _ths_rotation_rows(rows,key):
    """Normalize THS returns; its net flow is not Eastmoney's 主力净流入."""
    result=[]
    for row in rows:
        name=row.get('行业')
        change=finite(str(row.get('行业-涨跌幅' if key=='今日' else '阶段涨跌幅','')).rstrip('%'))
        net=finite(row.get('净额'))
        if not name or change is None:continue
        result.append({'名称':name,key+'涨跌幅':change,'资金净额-元':net*100_000_000 if net is not None else None,
                       '资金来源':'同花顺','资金口径':'行业资金净额；非东方财富主力净流入'})
    return result


async def sector_rotation(db,refresh=False):
    from app.research_data import collect,cached
    windows=['今日','5日','10日']
    enabled=__import__('os').getenv('AKSHARE_ENABLED','true').lower()=='true'
    datasets=await asyncio.gather(*(collect(db,'rotation',w,refresh) for w in windows)) if enabled else [cached(db,'rotation',w) or {'rows':[],'state':'disabled'} for w in windows]
    maps={w:{r['名称']:r for r in data.get('rows',[]) if r.get('名称')} for w,data in zip(windows,datasets)}
    names=set.union(*(set(m) for m in maps.values()))
    common={n for n in names if all(n in maps[w] and finite(maps[w][n].get(w+'涨跌幅')) is not None for w in windows)}
    ranks={w:{name:i+1 for i,name in enumerate(sorted(common,key=lambda n:(-float(maps[w][n][w+'涨跌幅']),n)))} for w in windows}
    rows=[];n=len(common);threshold=max(3,math.ceil(n*.15))
    for name in sorted(names):
        row={'name':name,'complete':name in common,'windows':{}}
        for w in windows:
            raw=maps[w].get(name,{})
            row['windows'][w]={'return_percent':finite(raw.get(w+'涨跌幅')),'main_net_yuan':finite(raw.get(w+'主力净流入-净额')),
                               'fund_net_yuan':finite(raw.get('资金净额-元')),
                               'main_net_ratio_percent':finite(raw.get(w+'主力净流入-净占比')),'rank':ranks[w].get(name)}
        r1,r5,r10=(ranks[w].get(name) for w in windows)
        row['rank_improvement']=r5-r1 if row['complete'] else None
        row['phase']='insufficient'
        if row['complete']:
            row['phase']='improving' if r5-r1>=threshold else ('weakening' if r1-r5>=threshold else ('persistent_leader' if max(r1,r5,r10)<=max(1,math.ceil(n*.3)) else 'mixed'))
        rows.append(row)
    rows.sort(key=lambda r:(not r['complete'],r['windows']['今日']['rank'] or 9999,r['name']))
    localday=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    with db() as c:
        previous=c.execute('SELECT * FROM sector_rotation_snapshots WHERE observed_date<? ORDER BY observed_date DESC LIMIT 1',(localday,)).fetchone()
        history=c.execute('SELECT observed_date,received_at,payload FROM sector_rotation_snapshots ORDER BY observed_date DESC LIMIT 10').fetchall()
        if previous:
            prior={r['name']:r for r in json.loads(previous['payload'])}
            for row in rows:
                old=prior.get(row['name'],{}).get('windows',{}).get('今日',{}).get('rank')
                old_names={r['name'] for r in prior.values() if r.get('complete')}
                # Different observed universes invalidate a temporal rank comparison.
                row['previous_capture_rank_change']=old-row['windows']['今日']['rank'] if old is not None and row['complete'] and old_names==common else None
        if n and all(d.get('state')=='available' for d in datasets):
            payload=json.dumps(rows,ensure_ascii=False,sort_keys=True)
            c.execute('INSERT INTO sector_rotation_snapshots VALUES(?,?,?,?) ON CONFLICT(observed_date) DO UPDATE SET received_at=excluded.received_at,payload=excluded.payload,sample_hash=excluded.sample_hash',
                      (localday,stamp(),payload,hashlib.sha256(payload.encode()).hexdigest()))
    return {'rows':rows,'common_universe':n,'state':'available' if n and all(d.get('state')=='available' for d in datasets) else ('partial' if names else 'unavailable'),
            'sources':[{k:d.get(k) for k in ('source','state','received_at','source_time','error','source_row_count','sample_truncated')} for d in datasets],
            'previous_capture_date':previous['observed_date'] if previous else None,
            'history':[{'capture_date':h['observed_date'],'received_at':h['received_at'],'leaders':[r['name'] for r in json.loads(h['payload']) if r['complete']][:5]} for h in history],
            'method':'以今日/5日/10日均有收益的共同板块集合按收益降序排名；5日排名减今日排名为跨窗口改善，变化至少max(3,15%板块数)标改善/转弱。三期均在前30%为持续领先；仅描述相对强弱，不是完整交易策略。',
            'note':'同花顺行业口径，资金净额单位元，不等同东方财富主力净流入；单源最多1000行，排名仅针对三个窗口的共同样本，不代表全部行业。今日和5/10日窗口重叠，跨窗口排名差不是历史名次变化。跨日变化只用本机不同采集日快照且相同板块集合；采集日不是来源交易日。源时点未知的窗口可能不同步，不做因果或收益承诺。'}


async def refresh_context(db):
    iteration=0
    while True:
        jobs=[news_context(db,refresh=iteration==0)]
        if iteration%5==0:jobs+=[sector_rotation(db,refresh=iteration==0)]
        if iteration%10==0:jobs+=[liquidity_context(db,refresh=iteration==0)]
        await asyncio.gather(*jobs,return_exceptions=True)
        iteration+=1
        await asyncio.sleep(60)
