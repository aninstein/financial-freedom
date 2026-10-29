"""Run on the owner's Windows miniQMT machine; expose only through loopback/SSH.

This module never asks for a broker password. Log into the official client yourself.
The vendor-supplied xtquant package must match the installed broker terminal.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from decimal import Decimal

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

LOCK=threading.RLock()
SDK=None
ACCOUNT=None
TOKEN=os.getenv('QMT_GATEWAY_TOKEN','')
ACCOUNT_ID=os.getenv('QMT_ACCOUNT_ID','')
DATA=Path(os.getenv('QMT_GATEWAY_DATA_DIR',str(Path.home()/'.finch-qmt')))
DB=DATA/('orders-'+hashlib.sha256(ACCOUNT_ID.encode()).hexdigest()[:16]+'.sqlite3')
ORDER_STRATEGY='finfreedom'
OWNED_ORDER_STRATEGIES={ORDER_STRATEGY,'Finch'}


def connection():
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row
    return c


def authorize(request: Request, authorization: str=Header(default='')):
    if request.client.host not in {'127.0.0.1','::1'}: raise HTTPException(403,'loopback only')
    if not hmac.compare_digest(authorization,'Bearer '+TOKEN): raise HTTPException(401,'gateway authorization required')


@asynccontextmanager
async def lifespan(app):
    global SDK,ACCOUNT
    if len(TOKEN)<32 or not ACCOUNT_ID or not os.getenv('QMT_USERDATA_PATH'): raise RuntimeError('QMT gateway needs local token, userdata path and stock account configuration')
    if os.name!='nt': raise RuntimeError('请在券商miniQMT支持的Windows环境运行此网关')
    from xtquant.xttrader import XtQuantTrader
    from xtquant.xttype import StockAccount
    DATA.mkdir(parents=True,exist_ok=True)
    with connection() as c:
        c.execute('CREATE TABLE IF NOT EXISTS requests(client_order_id TEXT PRIMARY KEY,body TEXT NOT NULL,status TEXT NOT NULL,broker_order_id TEXT)')
    SDK=XtQuantTrader(os.environ['QMT_USERDATA_PATH'],int(time.time()*1000)%2000000000)
    SDK.start()
    if SDK.connect()!=0: raise RuntimeError('miniQMT未登录或未连通')
    ACCOUNT=StockAccount(ACCOUNT_ID,'STOCK')
    if SDK.subscribe(ACCOUNT)!=0: raise RuntimeError('无法订阅所配置的股票账户')
    yield
    SDK.stop()


app=FastAPI(title='finfreedom private miniQMT gateway',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan,dependencies=[Depends(authorize)])


class Order(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    connection_id: str|None=None
    instrument_id: str=Field(pattern=r'^CN:\d{6}$')
    side: str=Field(pattern='^(buy|sell)$')
    quantity: int=Field(gt=0,le=1000000,strict=True)
    limit_price: Decimal=Field(gt=0,le=1000000,decimal_places=4)
    client_order_id: str|None=Field(default=None,max_length=24)


class Cancel(BaseModel):
    broker_order_id: str=Field(pattern=r'^\d+$')


def code(order):
    symbol=order.instrument_id.split(':')[1]
    if symbol.startswith(('600','601','603','605','688')): return symbol+'.SH'
    if symbol.startswith(('000','001','002','003','300','301')): return symbol+'.SZ'
    raise HTTPException(422,'unsupported common stock')


def assets():
    asset=SDK.query_stock_asset(ACCOUNT)
    if asset is None: raise HTTPException(502,'account unavailable')
    positions=SDK.query_stock_positions(ACCOUNT)
    if positions is None: raise HTTPException(502,'positions unavailable')
    return {'account_suffix':ACCOUNT_ID[-4:],'currency':'CNY','cash':asset.cash,'equity':asset.total_asset,
            'positions':[{'instrument_id':'CN:'+p.stock_code.split('.')[0],'quantity':p.volume,'sellable':p.can_use_volume,
                          'average_cost':p.open_price,'market_value':p.market_value} for p in positions],
            'as_of':int(time.time())}


@app.get('/snapshot')
def snapshot():
    with LOCK: return assets()


def check(order):
    from xtquant import xtdata
    ticker=code(order)
    tick=xtdata.get_full_tick([ticker]).get(ticker)
    if not tick or not tick.get('time') or not -5<time.time()-float(tick['time'])/1000<60:
        raise HTTPException(422,'broker quote unavailable or stale')
    detail=xtdata.get_instrument_detail(ticker)
    if not detail or ('IsTrading' in detail and not detail['IsTrading']): raise HTTPException(422,'instrument unavailable')
    lower,upper=detail.get('DownStopPrice'),detail.get('UpStopPrice')
    if lower and float(order.limit_price)<float(lower) or upper and float(order.limit_price)>float(upper): raise HTTPException(422,'limit price outside broker bounds')
    a=assets()
    position=next((p for p in a['positions'] if p['instrument_id']==order.instrument_id),None)
    buyable=int(Decimal(str(a['cash']))/(order.limit_price*Decimal('1.01')))
    return {'buyable':max(0,buyable),'sellable':position['sellable'] if position else 0,'lot_size':200 if ticker.startswith('688') else 100}


@app.post('/capacity')
def capacity(order:Order):
    with LOCK: return check(order)


@app.post('/orders')
def submit(order:Order):
    if os.getenv('QMT_GATEWAY_ALLOW_ORDERS','false').lower()!='true': raise HTTPException(403,'gateway write disabled')
    if not order.client_order_id: raise HTTPException(422,'stable client_order_id required')
    body=order.model_dump_json()
    with LOCK:
        with connection() as c:
            old=c.execute('SELECT * FROM requests WHERE client_order_id=?',(order.client_order_id,)).fetchone()
            if old:
                if old['body']!=body: raise HTTPException(409,'client_order_id conflict')
                if old['broker_order_id']: return {'broker_order_id':old['broker_order_id'],'broker_status':'已提交，请查询券商状态'}
                raise HTTPException(503,'previous write result unknown; do not resend')
        limits=check(order)
        if order.quantity>limits['buyable' if order.side=='buy' else 'sellable']: raise HTTPException(422,'insufficient cash-only capacity')
        if order.side=='buy' and ((limits['lot_size']==200 and order.quantity<200) or (limits['lot_size']==100 and order.quantity%100)): raise HTTPException(422,'lot size violation')
        with connection() as c:
            c.execute('INSERT INTO requests VALUES(?,?,?,NULL)',(order.client_order_id,body,'dispatching'))
        from xtquant import xtconstant
        try:
            oid=SDK.order_stock(ACCOUNT,code(order),xtconstant.STOCK_BUY if order.side=='buy' else xtconstant.STOCK_SELL,
                                order.quantity,xtconstant.FIX_PRICE,float(order.limit_price),ORDER_STRATEGY,order.client_order_id)
            if not oid or oid<0:
                with connection() as c: c.execute("UPDATE requests SET status='rejected' WHERE client_order_id=?",(order.client_order_id,))
                raise HTTPException(422,'broker explicitly rejected order')
            with connection() as c: c.execute("UPDATE requests SET status='submitted',broker_order_id=? WHERE client_order_id=?",(str(oid),order.client_order_id))
            return {'broker_order_id':str(oid),'broker_status':'已送券商，尚未核对成交'}
        except HTTPException: raise
        except Exception as exc: raise HTTPException(503,'broker write result unknown; do not resend') from exc


@app.get('/orders')
def orders():
    with LOCK:
        rows=SDK.query_stock_orders(ACCOUNT,False)
        if rows is None: raise HTTPException(502,'orders unavailable')
        # Only this application's tagged orders leave the gateway.
        return {'orders':[{'broker_order_id':str(o.order_id),'broker_status':str(o.order_status),'instrument_id':'CN:'+o.stock_code.split('.')[0],
                           'quantity':o.order_volume,'filled_quantity':o.traded_volume,'filled_price':o.traded_price,
                           'client_order_id':o.order_remark} for o in rows if o.strategy_name in OWNED_ORDER_STRATEGIES]}


@app.post('/cancel')
def cancel(body:Cancel):
    with LOCK:
        known=next((r for r in orders()['orders'] if r['broker_order_id']==body.broker_order_id),None)
        if not known: raise HTTPException(404,'not a finfreedom order')
        result=SDK.cancel_order_stock(ACCOUNT,int(body.broker_order_id))
        if result!=0: raise HTTPException(422,'broker rejected cancel request')
        return {'broker_order_id':body.broker_order_id,'broker_status':'撤单请求已发送，需查询券商结果'}
