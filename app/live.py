"""Explicitly confirmed real orders. This service is never exposed as an LLM tool."""
from __future__ import annotations
import hashlib
import json
import os
import secrets
import time
import uuid
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field
from app.paper import StrictModel, amount, normalize, board, now
from app.brokers.adapters import adapter, BrokerFailure, BrokerUnknown

CATALOG = [
    {'id':'citic','name':'中信证券','market':'CN','interface':'券商授权的QMT/miniQMT本地网关','status':'需确认终端和API权限','adapter':'qmt_http'},
    {'id':'sinolink','name':'国金证券','market':'CN','interface':'券商授权的QMT/miniQMT本地网关','status':'需确认终端和API权限；PTrade不能直接使用QMT驱动','adapter':'qmt_http'},
    {'id':'usmart','name':'盈立美股','market':'US','interface':'uSMART官方OpenAPI（HK版协议）','status':'需申请API并核对账户所属实体及接口版本','adapter':'usmart'},
    {'id':'futu','name':'富途 / moomoo','market':'HK/US','interface':'OpenD + 官方SDK','status':'已调研，未实现适配；港股实盘暂缓','adapter':None},
    {'id':'ibkr','name':'盈透','market':'US/HK','interface':'官方TWS / IB Gateway','status':'已调研，未实现适配','adapter':None},
]


def initialize(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS live_previews (
            preview_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, connection_id TEXT NOT NULL,
            body_json TEXT NOT NULL, fingerprint TEXT NOT NULL, view_json TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS live_orders (
            order_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, connection_id TEXT NOT NULL,
            preview_id TEXT UNIQUE NOT NULL, request_key TEXT NOT NULL, body_json TEXT NOT NULL,
            client_serial INTEGER NOT NULL UNIQUE, status TEXT NOT NULL, broker_order_id TEXT,
            broker_status TEXT, notional TEXT NOT NULL, trade_day TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT,
            UNIQUE(owner_id,request_key));
        ''')
        c.execute("UPDATE live_orders SET status='unknown',error='服务重启，发送结果待核对；禁止自动重发' WHERE status='dispatching'")
        c.execute("UPDATE live_orders SET status='rejected',error='服务在发送前中断，订单未发送' WHERE status='validating'")


def configurations():
    try:
        rows=json.loads(os.getenv('BROKER_CONNECTIONS_JSON','[]'))
        if not isinstance(rows,list): raise ValueError()
        ids=set()
        for row in rows:
            if not isinstance(row,dict) or row.get('provider') not in {'qmt_http','usmart'} or row.get('market') not in {'CN','US'}: raise ValueError()
            name=row.get('id','')
            if not name or len(name)>50 or name in ids: raise ValueError()
            ids.add(name)
            for field in ('max_order_notional','max_daily_notional'):
                if amount(row.get(field,0))<=0: raise ValueError()
            if not isinstance(row.get('symbols',[]),list): raise ValueError()
            row['symbols']=[normalize(v) for v in row.get('symbols',[])]
            if any(v.split(':')[0]!=row['market'] for v in row['symbols']): raise ValueError()
            if row.get('provider')=='qmt_http' and row['market']!='CN': raise ValueError()
            if row.get('provider')=='usmart' and row['market']!='US': raise ValueError()
        return rows
    except Exception as exc:
        raise HTTPException(503,'BROKER_CONNECTIONS_JSON配置无效，请检查协议、限额及股票白名单') from exc


def public_order(row):
    result = dict(row)
    result['client_serial'] = str(result['client_serial'])
    return result


class LiveDraft(StrictModel):
    connection_id: str = Field(min_length=1,max_length=50)
    instrument_id: str = Field(min_length=4,max_length=30)
    side: str = Field(pattern='^(buy|sell)$')
    quantity: int = Field(gt=0,le=1000000,strict=True)
    limit_price: Decimal = Field(gt=0,le=1000000,decimal_places=4)


class LiveConfirmation(StrictModel):
    preview_id: str = Field(min_length=1,max_length=80)
    confirm: str = Field(pattern='^REAL ORDER$')


class LiveService:
    def __init__(self,db,owner,primary,session):
        self.db,self.owner,self.primary,self.session=db,owner,primary,session

    def config(self,identifier):
        if self.owner!=self.primary: raise HTTPException(403,'当前券商接入仅绑定本机拥有者；未配置其他用户的独立券商授权')
        config=next((r for r in configurations() if r['id']==identifier),None)
        if not config: raise HTTPException(404,'未配置这条实盘连接')
        return config

    def enabled(self,config):
        return os.getenv('LIVE_TRADING_ENABLED','false').lower()=='true' and config.get('trading_enabled') is True

    def fingerprint(self,config):
        credentials=[os.getenv(str(v),'') for k,v in config.items() if k.endswith('_env')]
        return hashlib.sha256((json.dumps(config,sort_keys=True)+'|'.join(credentials)).encode()).hexdigest()

    def status(self):
        rows=[]
        for config in configurations() if self.owner==self.primary else []:
            error=None
            try: adapter(config)
            except Exception: error='服务端凭据或网关配置尚不完整'
            rows.append({'id':config['id'],'label':str(config.get('label') or config['id'])[:80],
                         'provider':config['provider'],'market':config['market'],'configured':error is None,
                         'trading_enabled':self.enabled(config),'error':error,
                         'max_order_notional':str(config['max_order_notional']),
                         'max_daily_notional':str(config['max_daily_notional']),'symbols':config['symbols']})
        return {'mode':'live','connections':rows,'catalog':CATALOG,'ai_mode':'research_only',
                'note':'配置完成不代表已联通。仅在本人确认后发送现金限价单，API联调尚待券商权限和凭据。'}

    async def snapshot(self,identifier):
        config=self.config(identifier)
        try: return {'connection_id':identifier,**await adapter(config).snapshot()}
        except Exception as exc: raise HTTPException(502,'券商账户读取失败：'+type(exc).__name__) from exc

    async def risk(self,config,body):
        instrument=normalize(body['instrument_id']); body={**body,'instrument_id':instrument}
        board(instrument)
        if instrument not in config['symbols']: raise HTTPException(422,'股票不在这条实盘连接的白名单中')
        price,quantity=amount(body['limit_price']),body['quantity']
        notional=price*quantity
        if notional>amount(config['max_order_notional']): raise HTTPException(422,'超过单笔实盘限额')
        if self.session(config['market'])['phase']!='open': raise HTTPException(422,'本期实盘仅开放交易所常规开市时段')
        if config['market']=='CN':
            clock=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')
            if not ('09:30:00'<=clock<'11:30:00' or '13:00:00'<=clock<'14:57:00'): raise HTTPException(422,'本期A股实盘仅开放连续竞价时段')
        client=adapter(config)
        snapshot=await client.snapshot(); capacity=await client.capacity(body)
        expected_currency='USD' if config['market']=='US' else 'CNY'
        if snapshot.get('currency')!=expected_currency: raise HTTPException(422,'券商账户币种与连接市场不一致')
        limit=capacity.get('buyable' if body['side']=='buy' else 'sellable')
        if limit is None or amount(limit)<quantity: raise HTTPException(422,'券商现金可买/可卖数量不足或缺失，不使用融资额度替代')
        if body['side']=='buy':
            if snapshot.get('cash') is None or amount(snapshot['cash']) < notional*Decimal('1.01'): raise HTTPException(422,'现金不足（另预留1%费用缓冲，不使用融资）')
        if config['market']=='CN':
            star=instrument.startswith('CN:688')
            if body['side']=='buy' and ((star and quantity<200) or (not star and quantity%100)): raise HTTPException(422,'A股买入数量不符合主板/创业板/科创板规则')
            if body['side']=='sell' and ((star and quantity<200 and quantity!=amount(limit)) or (not star and quantity%100 and quantity!=amount(limit))): raise HTTPException(422,'不足整手的可卖余额必须一次卖出')
            if star and quantity>100000: raise HTTPException(422,'科创板限价申报超过单笔数量上限')
        return {'mode':'live','connection_id':config['id'],'instrument_id':instrument,'side':body['side'],
                'quantity':quantity,'limit_price':str(price),'notional':str(notional),
                'currency':'USD' if config['market']=='US' else 'CNY','available_cash':snapshot.get('cash'),
                'broker_quantity_limit':str(limit),'account_suffix':snapshot.get('account_suffix'),'as_of':now(),
                'note':'这是实盘限价委托预览。成交与费用以券商回报为准，提交不代表成交。'}

    async def preview(self,body):
        config=self.config(body.connection_id)
        request=body.model_dump(mode='json');request['instrument_id']=normalize(request['instrument_id'])
        try: view=await self.risk(config,request)
        except (BrokerFailure,BrokerUnknown) as exc: raise HTTPException(502,str(exc)) from exc
        identifier='LP-'+uuid.uuid4().hex
        expiry=int(time.time())+45
        with self.db() as c:
            c.execute('INSERT INTO live_previews VALUES(?,?,?,?,?,?,?)',(identifier,self.owner,config['id'],json.dumps(request),self.fingerprint(config),json.dumps(view),expiry))
        return {**view,'preview_id':identifier,'expires_at':expiry,'trading_enabled':self.enabled(config)}

    def orders(self):
        with self.db() as c:
            return [public_order(r) for r in c.execute('SELECT * FROM live_orders WHERE owner_id=? ORDER BY created_at DESC LIMIT 100',(self.owner,))]

    async def submit(self,body,key):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT * FROM live_orders WHERE owner_id=? AND request_key=?',(self.owner,key)).fetchone()
            if prior:
                if prior['preview_id']!=body.preview_id: raise HTTPException(409,'同一请求标识已用于另一笔实盘订单')
                return public_order(prior)
            used_preview=c.execute('SELECT * FROM live_orders WHERE preview_id=? AND owner_id=?',(body.preview_id,self.owner)).fetchone()
            if used_preview: return public_order(used_preview)
            preview=c.execute('SELECT * FROM live_previews WHERE preview_id=? AND owner_id=?',(body.preview_id,self.owner)).fetchone()
            if not preview: raise HTTPException(404,'实盘预览不存在')
            if preview['expires_at']<time.time(): raise HTTPException(409,'预览已超过45秒，请重新预览并确认')
            config=self.config(preview['connection_id'])
            if not self.enabled(config): raise HTTPException(403,'实盘发送未启用，请先由本人完成ENV接入与开通')
            if self.fingerprint(config)!=preview['fingerprint']: raise HTTPException(409,'券商配置已变化，请重新预览')
            if c.execute("SELECT 1 FROM live_orders WHERE connection_id=? AND status IN ('unknown','dispatching','validating')",(config['id'],)).fetchone(): raise HTTPException(409,'这条连接有处理中或结果未知的订单，请先核对；不能叠加发送')
            request=json.loads(preview['body_json'])
            nominal=amount(request['limit_price'])*request['quantity']
            day=datetime.now(ZoneInfo('America/New_York' if config['market']=='US' else 'Asia/Shanghai')).date().isoformat()
            used=sum((amount(r['notional']) for r in c.execute("SELECT notional FROM live_orders WHERE connection_id=? AND trade_day=? AND status!='rejected'",(config['id'],day))),Decimal(0))
            if used+nominal>amount(config['max_daily_notional']): raise HTTPException(422,'超过此连接当日委托名义总额限额，撤单不返还额度')
            order_id='L-'+uuid.uuid4().hex[:20]
            serial=10**18+secrets.randbelow(8*10**18)
            c.execute('INSERT INTO live_orders(order_id,owner_id,connection_id,preview_id,request_key,body_json,client_serial,status,notional,trade_day,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(order_id,self.owner,config['id'],body.preview_id,key,preview['body_json'],serial,'validating',str(nominal),day,now(),now()))
        dispatched=False
        try:
            await self.risk(config,request)
            with self.db() as c:
                c.execute("UPDATE live_orders SET status='dispatching',updated_at=? WHERE order_id=?",(now(),order_id))
            dispatched=True
            result=await adapter(config).place(request,serial)
            with self.db() as c:
                c.execute("UPDATE live_orders SET status='submitted',broker_order_id=?,broker_status=?,updated_at=? WHERE order_id=?",(result['broker_order_id'],result.get('broker_status'),now(),order_id))
        except Exception as exc:
            status='unknown' if dispatched and not isinstance(exc,BrokerFailure) else 'rejected'
            error=str(exc.detail) if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,(BrokerFailure,BrokerUnknown)) else '券商处理异常：'+type(exc).__name__
            with self.db() as c:
                c.execute('UPDATE live_orders SET status=?,error=?,updated_at=? WHERE order_id=?',(status,error[:240],now(),order_id))
        with self.db() as c:
            return public_order(c.execute('SELECT * FROM live_orders WHERE order_id=? AND owner_id=?',(order_id,self.owner)).fetchone())

    async def reconcile(self,identifier):
        config=self.config(identifier)
        try: remote=await adapter(config).orders()
        except Exception as exc: raise HTTPException(502,'券商委托读取失败：'+type(exc).__name__) from exc
        by_id={str(o['broker_order_id']):o for o in remote}
        by_serial={str(o['client_order_id']):o for o in remote if o.get('client_order_id')}
        with self.db() as c:
            rows=c.execute('SELECT * FROM live_orders WHERE owner_id=? AND connection_id=?',(self.owner,identifier)).fetchall()
            for row in rows:
                report=by_id.get(str(row['broker_order_id'])) or (by_serial.get(str(row['client_serial'])) if config['provider']=='qmt_http' else None)
                if report:
                    c.execute("UPDATE live_orders SET status='broker_reported',broker_order_id=?,broker_status=?,updated_at=? WHERE order_id=?",(report['broker_order_id'],report.get('broker_status'),now(),row['order_id']))
        return {'connection_id':identifier,'broker_orders':remote,'orders':[r for r in self.orders() if r['connection_id']==identifier],
                'note':'缺失券商订单号的未知委托仍会阻止发送，需使用请求流水号与券商核对，不会自动重试。'}

    async def cancel(self,identifier):
        with self.db() as c:
            row=c.execute('SELECT * FROM live_orders WHERE order_id=? AND owner_id=?',(identifier,self.owner)).fetchone()
        if not row or not row['broker_order_id']: raise HTTPException(404,'没有可核验的本平台实盘委托')
        config=self.config(row['connection_id'])
        # Risk-reducing cancellation remains available after turning new-order sends off.
        try:
            result=await adapter(config).cancel(row['broker_order_id'])
            status='cancel_requested';error=None
        except Exception as exc:
            status='cancel_unknown';error='撤单结果待券商核对：'+type(exc).__name__;result={}
        with self.db() as c:
            c.execute('UPDATE live_orders SET status=?,broker_status=COALESCE(?,broker_status),error=?,updated_at=? WHERE order_id=?',(status,result.get('broker_status'),error,now(),identifier))
        return next(o for o in self.orders() if o['order_id']==identifier)
