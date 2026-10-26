"""Local-only paper broker. Every mutation shares one serialized ledger transaction."""
from __future__ import annotations

import io
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

MARKETS = {
    "US": {"name": "美股", "quote_market": "US", "currency": "USD", "initial_cash": 100000, "rule": "整数股 · 可日内回转"},
    "HK": {"name": "港股", "quote_market": "HK", "currency": "HKD", "initial_cash": 1000000, "rule": "按证券每手股数 · 可日内回转"},
    "CN_MAIN": {"name": "A股主板", "quote_market": "CN", "currency": "CNY", "initial_cash": 1000000, "rule": "买入100股整数倍 · T+1可卖"},
    "CN_CHINEXT": {"name": "创业板", "quote_market": "CN", "currency": "CNY", "initial_cash": 1000000, "rule": "买入100股整数倍 · T+1可卖"},
    "CN_STAR": {"name": "科创板", "quote_market": "CN", "currency": "CNY", "initial_cash": 1000000, "rule": "至少200股，按1股递增 · T+1可卖"},
}
HK_LIST = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
FEE = Decimal("0.001")
CENT = Decimal("0.01")


def now():
    return datetime.now(timezone.utc).isoformat()


def amount(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise HTTPException(422, "金额或数量必须是有限数值")
    return result


def cashround(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def normalize(value):
    value = value.strip().upper()
    if value.startswith("HK:") and value[3:].isdigit():
        value = "HK:" + value[3:].zfill(5)
    if not re.fullmatch(r"(CN:[0-9]{6}|HK:[0-9]{5}|US:[A-Z][A-Z0-9.\-]{0,19})", value):
        raise HTTPException(422, "请使用 CN:600519、HK:00700 或 US:AAPL 格式的股票代码")
    return value


def board(instrument_id):
    if instrument_id.startswith("HK:"): return "HK"
    if instrument_id.startswith("US:"): return "US"
    code = instrument_id[3:]
    if code.startswith(("300", "301")): return "CN_CHINEXT"
    if code.startswith("688"): return "CN_STAR"
    if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")): return "CN_MAIN"
    raise HTTPException(422, "当前只支持主板、创业板、科创板及港美普通股票，不支持指数/基金/存托凭证")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AccountRequest(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    market: Literal["US", "HK", "CN_MAIN", "CN_CHINEXT", "CN_STAR"]
    initial_cash: Decimal = Field(gt=0, le=1000000000, decimal_places=2)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value):
        if not value.strip(): raise ValueError("账户名称不能为空")
        return value.strip()


class ResetRequest(AccountRequest):
    confirm: str = Field(min_length=1, max_length=80)


class OrderRequest(StrictModel):
    account_id: str = Field(default="paper-default", max_length=80)
    instrument_id: str = Field(max_length=30)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    quantity: int = Field(gt=0, le=1000000, strict=True)
    limit_price: Decimal | None = Field(default=None, gt=0, le=100000000, decimal_places=4)

    @field_validator("instrument_id")
    @classmethod
    def normalized(cls, value): return normalize(value)


class ContractRequest(StrictModel):
    lot_size: int = Field(ge=1, le=100000, strict=True)
    note: str = Field(min_length=3, max_length=160)


class AIRunRequest(StrictModel):
    account_id: str = Field(min_length=1, max_length=80)
    objective: str = Field(min_length=5, max_length=2000)
    instruments: list[str] = Field(min_length=1, max_length=10)
    max_notional: Decimal = Field(gt=0, le=1000000000, decimal_places=2)
    max_orders: int = Field(default=3, ge=1, le=5)
    authorize: Literal[True]

    @field_validator("instruments")
    @classmethod
    def normalized(cls, values): return list(dict.fromkeys(normalize(v) for v in values))


class Broker:
    def __init__(self, db, session, quote_age, observed_at, refresh, owner_id=None):
        self.db, self.session, self.quote_age, self.observed_at, self.refresh = db, session, quote_age, observed_at, refresh
        self.owner_id = owner_id

    def initialize(self):
        with self.db() as c:
            columns = {r["name"] for r in c.execute("PRAGMA table_info(paper_accounts)")}
            if "market" not in columns:
                c.execute("ALTER TABLE paper_accounts ADD COLUMN market TEXT NOT NULL DEFAULT 'CN_ALL'")
                c.execute("UPDATE paper_accounts SET market='US' WHERE currency='USD'")
                c.execute("UPDATE paper_accounts SET market='HK' WHERE currency='HKD'")
            for name, definition in (("owner_id", "TEXT"), ("state", "TEXT NOT NULL DEFAULT 'active'"), ("replaces_account_id", "TEXT")):
                if name not in columns:
                    c.execute(f"ALTER TABLE paper_accounts ADD COLUMN {name} {definition}")
            c.execute("CREATE TABLE IF NOT EXISTS paper_account_actions(owner_id TEXT NOT NULL, request_key TEXT NOT NULL, payload TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(owner_id,request_key))")
            columns = {r["name"] for r in c.execute("PRAGMA table_info(paper_orders)")}
            for name, definition in (("actor", "TEXT NOT NULL DEFAULT 'manual'"), ("ai_run_id", "TEXT"), ("reason", "TEXT"), ("reserved_cash", "REAL NOT NULL DEFAULT 0"), ("budget_charge", "REAL NOT NULL DEFAULT 0")):
                if name not in columns: c.execute(f"ALTER TABLE paper_orders ADD COLUMN {name} {definition}")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS paper_contract_overrides (
                owner_id TEXT NOT NULL, instrument_id TEXT NOT NULL, lot_size INTEGER NOT NULL,
                currency TEXT NOT NULL, source TEXT NOT NULL, source_kind TEXT NOT NULL, updated_at TEXT NOT NULL,
                note TEXT NOT NULL, PRIMARY KEY(owner_id,instrument_id));
            CREATE TABLE IF NOT EXISTS paper_contracts (
                instrument_id TEXT PRIMARY KEY, lot_size INTEGER NOT NULL, currency TEXT NOT NULL,
                source TEXT NOT NULL, source_kind TEXT NOT NULL, updated_at TEXT NOT NULL, note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_ai_runs (
                run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, account_id TEXT NOT NULL,
                request_json TEXT NOT NULL, status TEXT NOT NULL, answer TEXT, error TEXT, model TEXT,
                evidence_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, completed_at TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_running_account ON paper_ai_runs(account_id) WHERE status='running';
            CREATE INDEX IF NOT EXISTS idx_paper_orders_account ON paper_orders(account_id,status,created_at);
            """)
            c.execute("UPDATE paper_ai_runs SET status='interrupted',error='服务重启，任务已中断；已提交的订单仍在账本中，请先查看再启动新一轮。',completed_at=? WHERE status='running'", (now(),))
            # Migrate old accepted limit orders to explicit reservations without changing fills.
            c.execute("UPDATE paper_orders SET reserved_cash=ROUND(quantity*limit_price*1.001,2) WHERE status='accepted' AND side='buy' AND limit_price IS NOT NULL AND reserved_cash=0")

    def claim_legacy(self, primary_owner):
        if self.owner_id and self.owner_id == primary_owner:
            with self.db() as c:
                c.execute("UPDATE paper_accounts SET owner_id=? WHERE owner_id IS NULL", (self.owner_id,))
                c.execute("INSERT OR IGNORE INTO paper_contract_overrides SELECT ?,instrument_id,lot_size,currency,source,source_kind,updated_at,note FROM paper_contracts WHERE source_kind='manual'", (self.owner_id,))
                c.execute("DELETE FROM paper_contracts WHERE source_kind='manual'")

    def _account(self, c, account_id, active=True):
        row = c.execute("SELECT * FROM paper_accounts WHERE account_id=?", (account_id,)).fetchone()
        if not row or (self.owner_id is not None and row['owner_id'] != self.owner_id):
            raise HTTPException(404, "模拟账户不存在")
        if active and row['state'] != 'active':
            raise HTTPException(409, "这个模拟盘已清零重开，请选择新的模拟账户")
        return dict(row)

    def create_account(self, body, key):
        account_id = "paper-" + uuid.uuid5(uuid.NAMESPACE_URL, "paper-account:" + str(self.owner_id) + ":" + key).hex[:20]
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute("SELECT * FROM paper_accounts WHERE account_id=?", (account_id,)).fetchone()
            if existing:
                self._account(c, account_id)
                if (existing['label'], existing['market'], amount(existing['initial_cash'])) != (body.label, body.market, body.initial_cash):
                    raise HTTPException(409, "该开户请求标识已用于其他参数")
                return self.portfolio(c, account_id)
            if not self.owner_id: raise HTTPException(403, '开户必须绑定登录用户')
            meta = MARKETS[body.market]
            c.execute("INSERT INTO paper_accounts(account_id,label,currency,initial_cash,created_at,market,owner_id) VALUES(?,?,?,?,?,?,?)", (account_id, body.label, meta['currency'], str(body.initial_cash), now(), body.market, self.owner_id))
            return self.portfolio(c, account_id)

    def portfolio(self, c, account_id):
        a = self._account(c, account_id)
        rows = c.execute("SELECT * FROM paper_orders WHERE account_id=? ORDER BY created_at,order_id", (account_id,)).fetchall()
        cash, realized, fees, frozen = amount(a['initial_cash']), Decimal(0), Decimal(0), Decimal(0)
        positions = {}
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        for o in rows:
            p = positions.setdefault(o['instrument_id'], {'quantity':0, 'cost':Decimal(0), 'bought_today':0, 'frozen':0})
            if o['status'] == 'accepted':
                if o['side'] == 'buy': frozen += amount(o['reserved_cash'])
                else: p['frozen'] += int(o['quantity'])
            if o['status'] != 'filled': continue
            qty, price, fee = int(o['quantity']), amount(o['fill_price']), amount(o['fee'])
            fees += fee
            if o['side'] == 'buy':
                cash -= price * qty + fee
                p['cost'] += price * qty + fee
                p['quantity'] += qty
                if o['instrument_id'].startswith('CN:') and datetime.fromisoformat(o['updated_at']).astimezone(ZoneInfo('Asia/Shanghai')).date() == today:
                    p['bought_today'] += qty
            else:
                cost = p['cost'] * qty / p['quantity'] if p['quantity'] else Decimal(0)
                realized += price * qty - fee - cost
                cash += price * qty - fee
                p['cost'] -= cost
                p['quantity'] -= qty
        values, unrealized, complete, output = Decimal(0), Decimal(0), True, []
        for instrument, p in positions.items():
            if p['quantity'] <= 0: continue
            q = c.execute('SELECT * FROM quotes WHERE instrument_id=?', (instrument,)).fetchone()
            value = amount(q['last']) * p['quantity'] if q and q['last'] > 0 else None
            if value is None: complete = False
            else:
                values += value
                unrealized += value - p['cost']
            output.append({'instrument_id':instrument, 'name':q['name'] if q else instrument, 'quantity':p['quantity'], 'sellable': max(0,p['quantity']-p['bought_today']-p['frozen']), 'frozen':p['frozen'], 'cost_basis':float(cashround(p['cost'])), 'average_cost':float(p['cost']/p['quantity']), 'market_value':float(cashround(value)) if value is not None else None, 'unrealized_pnl':float(cashround(value-p['cost'])) if value is not None else None, 'last':q['last'] if q else None, 'quote_time':q['exchange_time'] if q else None, 'provider':q['provider'] if q else None, 'freshness':self.quote_age(q)['freshness'] if q else 'unknown'})
        return {**a, 'mode':'paper', 'market_name':MARKETS.get(a['market'], {'name':'A股兼容账户（全部板块）'})['name'], 'cash':float(cashround(cash)), 'frozen_cash':float(cashround(frozen)), 'available_cash':float(cashround(cash-frozen)), 'positions':output, 'market_value':float(cashround(values)) if complete else None, 'equity':float(cashround(cash+values)) if complete else None, 'realized_pnl':float(cashround(realized)), 'unrealized_pnl':float(cashround(unrealized)) if complete else None, 'fees':float(cashround(fees)), 'valuation_complete':complete, 'as_of':now()}

    def contract(self, c, instrument):
        b = board(instrument)
        if b != 'HK': return {'instrument_id':instrument,'lot_size':200 if b=='CN_STAR' else 100 if b.startswith('CN') else 1,'source_kind':'rules','source':'交易所基础数量规则','currency':MARKETS[b]['currency']}
        row = c.execute('SELECT instrument_id,lot_size,currency,source,source_kind,updated_at,note FROM paper_contract_overrides WHERE owner_id=? AND instrument_id=?', (self.owner_id,instrument)).fetchone() if self.owner_id else None
        if not row:
            row = c.execute('SELECT * FROM paper_contracts WHERE instrument_id=?', (instrument,)).fetchone()
        if not row: raise HTTPException(422, '缺少该港股每手股数，请先同步港交所清单，或录入明确的模拟买卖单位')
        result = dict(row)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(result['updated_at'])
        if age > timedelta(days=7): raise HTTPException(422, '港股买卖单位已超过7天，请重新同步或确认模拟规则')
        if result['currency'] != 'HKD': raise HTTPException(422, '当前港股账户仅支持港币证券，不支持其他币种柜台')
        return result

    def _scope(self, a, instrument):
        b = board(instrument)
        if a['market'] != b and not (a['market']=='CN_ALL' and b.startswith('CN_')):
            raise HTTPException(422, f"该股票不属于所选账户市场（{a['market']}）")
        return b

    def _quote(self, c, instrument):
        q = c.execute('SELECT * FROM quotes WHERE instrument_id=?', (instrument,)).fetchone()
        if q:
            q = dict(q)
            if q['asset_class'] not in {'equity','stock'}: raise HTTPException(422, '本期仅支持普通股票模拟交易')
            if not amount(q['last']) > 0: raise HTTPException(422, '报价价格无效')
        return q

    def _executable(self, q):
        if not q or q['quote_kind'] not in {'trade','realtime','delayed','snapshot'}: return False
        if self.session(q['market'])['phase'] != 'open': return False
        if q['market'] == 'CN':
            clock = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')
            if not ('09:30:00' <= clock < '11:30:00' or '13:00:00' <= clock < '14:57:00'): return False
        observed = self.observed_at(q)
        if observed is None: return False
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        received = (datetime.now(timezone.utc)-datetime.fromisoformat(q['received_at']).astimezone(timezone.utc)).total_seconds()
        allowed = max(self.refresh*2,600,(q.get('known_delay_seconds') or 0)*2)
        return -30 <= age <= allowed and -30 <= received <= max(self.refresh*2,600) and self.quote_age(q)['freshness'] != 'stale'

    def _preview(self, c, order):
        a = self._account(c, order.account_id)
        b = self._scope(a, order.instrument_id)
        contract = self.contract(c, order.instrument_id)
        portfolio = self.portfolio(c, order.account_id)
        p = next((p for p in portfolio['positions'] if p['instrument_id']==order.instrument_id), {'sellable':0,'quantity':0})
        if order.type=='limit' and order.limit_price is None: raise HTTPException(422,'限价单必须填写限价')
        if order.type=='market' and order.limit_price is not None: raise HTTPException(422,'市价单不能携带限价')
        lot, qty = contract['lot_size'], order.quantity
        if b=='CN_STAR':
            if qty < 200 and not (order.side=='sell' and qty==p['sellable']): raise HTTPException(422,'科创板单笔至少200股；不足200股的可卖余额须一次卖出')
            if qty > (50000 if order.type=='market' else 100000): raise HTTPException(422,'科创板单笔股数超过当前模拟规则上限')
        elif b.startswith('CN_'):
            if (order.side=='buy' and qty%100) or (order.side=='sell' and qty%100 and qty!=p['sellable']): raise HTTPException(422,'主板/创业板买入100股整数倍；零股可卖余额须一次卖出')
        elif b=='HK' and qty%lot: raise HTTPException(422,f'该港股每手{lot}股，本期不撮合碎股，请填写整手数量')
        q = self._quote(c, order.instrument_id)
        if q and q['currency'] != a['currency']: raise HTTPException(422,'报价与账户币种不一致')
        executable = self._executable(q)
        if order.type=='market' and not executable: raise HTTPException(422,'市价单需连续交易时段内有来源时点的新鲜实时/延迟行情；可改用限价挂单等待行情')
        price = amount(q['last']) if executable else order.limit_price
        crossed = executable and (order.type=='market' or (order.side=='buy' and price<=order.limit_price) or (order.side=='sell' and price>=order.limit_price))
        reserve_price = order.limit_price if order.type=='limit' else price
        reserve_cash = cashround(reserve_price*qty*(1+FEE)) if order.side=='buy' else Decimal(0)
        if order.side=='buy' and amount(portfolio['available_cash']) < reserve_cash: raise HTTPException(422,'可用模拟现金不足（已扣除其他挂单冻结资金）')
        if order.side=='sell' and p['sellable'] < qty: raise HTTPException(422,'可卖持仓不足：A股当日买入需T+1，且挂单占用持仓不能重复出售')
        notional = cashround(price*qty)
        return {'valid':True, 'mode':'paper', 'account_id':order.account_id,'instrument_id':order.instrument_id,'side':order.side,'type':order.type,'quantity':qty,'limit_price':float(order.limit_price) if order.limit_price else None,'estimated_price':float(price),'estimated_notional':float(notional),'estimated_fee':float(cashround(notional*FEE)),'estimated_cash_after':float(cashround(amount(portfolio['cash'])-(notional+cashround(notional*FEE) if order.side=='buy' else -notional+cashround(notional*FEE)))) if crossed else portfolio['cash'],'would_fill_at_observed_quote':bool(crossed),'reserved_cash':float(reserve_cash),'currency':a['currency'],'quote_provider':q['provider'] if q else '暂无行情，按委托限价冻结','quote_time':q['exchange_time'] if q else None,'quote_received_at':q['received_at'] if q else None,'freshness':self.quote_age(q)['freshness'] if q else 'unknown','fee_rate':float(FEE),'contract':contract,'execution_note':'报价快照全额模拟成交；费用10bp，未模拟盘口排队、滑点、部分成交及完整税费','budget_charge':float(cashround(max(price,reserve_price)*qty))}

    def preview(self, order):
        with self.db() as c: return self._preview(c,order)

    def _ai_guard(self,c,run_id,order,charge):
        run=c.execute('SELECT * FROM paper_ai_runs WHERE run_id=?',(run_id,)).fetchone()
        if not run or run['status']!='running': raise HTTPException(409,'AI任务已停止或结束，不能继续写入')
        rules=json.loads(run['request_json'])
        if order.account_id!=run['account_id'] or order.instrument_id not in rules['instruments']: raise HTTPException(403,'超出本轮授权的模拟账户/证券白名单')
        previous=c.execute('SELECT budget_charge FROM paper_orders WHERE ai_run_id=?',(run_id,)).fetchall()
        used=sum((amount(row['budget_charge']) for row in previous),Decimal(0))
        if len(previous)>=rules['max_orders'] or used+amount(charge)>amount(rules['max_notional']): raise HTTPException(422,'达到本轮AI委托笔数或委托名义金额上限（撤单不退回本轮额度）')

    def submit(self, order, key, run_id=None, reason=None):
        if not key or len(key)>180: raise HTTPException(422,'幂等请求标识需为1至180字符')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM paper_orders WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                self._account(c, old["account_id"])
                if (old['account_id'],old['instrument_id'],old['side'],old['order_type'],old['quantity'],amount(old['limit_price']) if old['limit_price'] is not None else None,old['ai_run_id']) != (order.account_id,order.instrument_id,order.side,order.type,order.quantity,order.limit_price,run_id): raise HTTPException(409,'该幂等标识已用于不同订单')
                return dict(old)
            view=self._preview(c,order)
            if run_id: self._ai_guard(c,run_id,order,view['budget_charge'])
            filled=view['would_fill_at_observed_quote']
            oid, stamp='P-'+uuid.uuid4().hex[:12].upper(),now()
            c.execute('''INSERT INTO paper_orders(order_id,idempotency_key,account_id,instrument_id,side,order_type,quantity,limit_price,status,risk_result,fill_price,fee,created_at,updated_at,source_quote_at,actor,ai_run_id,reason,reserved_cash,budget_charge) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(oid,key,order.account_id,order.instrument_id,order.side,order.type,order.quantity,str(order.limit_price) if order.limit_price else None,'filled' if filled else 'accepted',json.dumps(view,ensure_ascii=False),view['estimated_price'] if filled else None,view['estimated_fee'] if filled else 0,stamp,stamp,view['quote_received_at'],'ai' if run_id else 'manual',run_id,reason,0 if filled else view['reserved_cash'],view['budget_charge'] if run_id else 0))
            c.execute('INSERT OR IGNORE INTO watchlist VALUES(?,?)',(order.instrument_id,stamp))
            if filled: self._fill(c,oid,view,stamp)
            return dict(c.execute('SELECT * FROM paper_orders WHERE order_id=?',(oid,)).fetchone())

    def _fill(self,c,oid,view,stamp):
        c.execute('INSERT INTO paper_fills VALUES(?,?,?,?,?,?,?,?,?,?,?)',('F-'+uuid.uuid4().hex[:12],oid,view['instrument_id'],view['side'],view['quantity'],view['estimated_price'],view['estimated_fee'],view['currency'],view['quote_provider'],view['quote_received_at'],stamp))

    def cancel(self,oid,run_id=None):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM paper_orders WHERE order_id=?',(oid,)).fetchone()
            if not row: raise HTTPException(404,'模拟订单不存在')
            self._account(c, row['account_id'])
            if run_id:
                run=c.execute('SELECT * FROM paper_ai_runs WHERE run_id=?',(run_id,)).fetchone()
                if not run or run['status']!='running' or row['ai_run_id']!=run_id: raise HTTPException(403,'只能撤销本轮AI创建的订单')
            if row['status']=='cancelled': return dict(row)
            if row['status']!='accepted': raise HTTPException(409,'仅未成交挂单可以撤销')
            c.execute("UPDATE paper_orders SET status='cancelled',reserved_cash=0,updated_at=? WHERE order_id=?",(now(),oid))
            return dict(c.execute('SELECT * FROM paper_orders WHERE order_id=?',(oid,)).fetchone())

    def match(self,market):
        if self.session(market)['phase']!='open': return
        with self.db() as c:
            ids=c.execute("SELECT o.order_id FROM paper_orders o WHERE o.status='accepted' AND o.instrument_id LIKE ? ORDER BY created_at,order_id",(market+':%',)).fetchall()
        for row in ids:
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                o=c.execute("SELECT * FROM paper_orders WHERE order_id=? AND status='accepted'",(row['order_id'],)).fetchone()
                if not o: continue
                account_owner=c.execute('SELECT owner_id FROM paper_accounts WHERE account_id=?',(o['account_id'],)).fetchone()
                self.owner_id=account_owner['owner_id'] if account_owner else None
                q=self._quote(c,o['instrument_id'])
                if not self._executable(q): continue
                price=amount(q['last'])
                if not ((o['side']=='buy' and price<=amount(o['limit_price'])) or (o['side']=='sell' and price>=amount(o['limit_price']))): continue
                # Exclude this order's reservation inside this same transaction; rollback restores it on failure.
                c.execute("UPDATE paper_orders SET status='matching' WHERE order_id=?",(o['order_id'],))
                try:
                    view=self._preview(c,OrderRequest(account_id=o['account_id'],instrument_id=o['instrument_id'],side=o['side'],type='limit',quantity=int(o['quantity']),limit_price=o['limit_price']))
                except HTTPException as e:
                    c.execute("UPDATE paper_orders SET status='rejected',reserved_cash=0,risk_result=?,updated_at=? WHERE order_id=?",(json.dumps({'passed':False,'reason':str(e.detail)},ensure_ascii=False),now(),o['order_id']))
                    continue
                if not view['would_fill_at_observed_quote']:
                    c.execute("UPDATE paper_orders SET status='accepted' WHERE order_id=?",(o['order_id'],)); continue
                stamp=now()
                c.execute("UPDATE paper_orders SET status='filled',fill_price=?,fee=?,source_quote_at=?,reserved_cash=0,risk_result=?,updated_at=? WHERE order_id=?",(view['estimated_price'],view['estimated_fee'],view['quote_received_at'],json.dumps(view,ensure_ascii=False),stamp,o['order_id']))
                self._fill(c,o['order_id'],view,stamp)

    def reset(self, target, body, key):
        if not self.owner_id: raise HTTPException(403, '清零必须绑定登录用户')
        expected = 'RESET ALL PAPER ACCOUNTS' if target is None else 'RESET PAPER ACCOUNT'
        if body.confirm != expected: raise HTTPException(422, '请明确确认清零范围')
        payload = json.dumps({'target':target, **body.model_dump(mode='json')}, sort_keys=True, ensure_ascii=False)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = c.execute('SELECT * FROM paper_account_actions WHERE owner_id=? AND request_key=?', (self.owner_id,key)).fetchone()
            if previous:
                if previous['payload'] != payload: raise HTTPException(409,'同一清零请求标识不可用于不同参数')
                return json.loads(previous['result_json'])
            if target:
                self._account(c,target)
                ids=[target]
            else:
                ids=[r['account_id'] for r in c.execute("SELECT account_id FROM paper_accounts WHERE owner_id=? AND state='active'", (self.owner_id,))]
            stopped=[]; deleted=0
            for account_id in ids:
                stopped.extend(r['run_id'] for r in c.execute('SELECT run_id FROM paper_ai_runs WHERE account_id=?',(account_id,)))
                deleted += c.execute('SELECT COUNT(*) FROM paper_orders WHERE account_id=?',(account_id,)).fetchone()[0]
                c.execute('DELETE FROM paper_fills WHERE order_id IN (SELECT order_id FROM paper_orders WHERE account_id=?)',(account_id,))
                c.execute('DELETE FROM paper_orders WHERE account_id=?',(account_id,))
                c.execute('DELETE FROM paper_ai_runs WHERE account_id=?',(account_id,))
                c.execute("UPDATE paper_accounts SET state='reset' WHERE account_id=?",(account_id,))
            fresh='paper-'+uuid.uuid4().hex[:20]
            meta=MARKETS[body.market]
            c.execute('INSERT INTO paper_accounts(account_id,label,currency,initial_cash,created_at,market,owner_id,replaces_account_id) VALUES(?,?,?,?,?,?,?,?)',
                      (fresh,body.label,meta['currency'],str(body.initial_cash),now(),body.market,self.owner_id,target))
            result={'account':self.portfolio(c,fresh),'retired_accounts':len(ids),'deleted_orders':deleted,'stopped_run_ids':stopped,'reset_at':now()}
            c.execute('INSERT INTO paper_account_actions VALUES(?,?,?,?,?)',(self.owner_id,key,payload,json.dumps(result,ensure_ascii=False),now()))
            return result

    def set_contract(self,instrument,body):
        instrument=normalize(instrument)
        if board(instrument)!='HK': raise HTTPException(422,'仅港股需要录入逐证券买卖单位')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM paper_orders o JOIN paper_accounts a ON a.account_id=o.account_id WHERE o.instrument_id=? AND o.status='accepted' AND a.owner_id=?",(instrument,self.owner_id)).fetchone(): raise HTTPException(409,'该证券仍有挂单，请先撤单再修改模拟单位')
            c.execute('INSERT OR REPLACE INTO paper_contract_overrides VALUES(?,?,?,?,?,?,?,?)',(self.owner_id,instrument,body.lot_size,'HKD','用户确认的模拟规则','manual',now(),body.note))
            return self.contract(c,instrument)

    async def sync_hk(self):
        # Fixed official URL, never a model-supplied fetch target.
        async with httpx.AsyncClient(timeout=25,follow_redirects=True) as client:
            r=await client.get(HK_LIST); r.raise_for_status()
        if len(r.content)>12*1024*1024: raise HTTPException(502,'官方清单大小异常')
        import openpyxl
        book=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        headers=None; records=[]
        for row in book.active.iter_rows(values_only=True):
            cells=[str(v or '').strip() for v in row]
            if headers is None:
                lowered=[v.lower() for v in cells]
                if any('stock code' in v for v in lowered) and any('board lot' in v for v in lowered): headers=lowered
                continue
            def col(term):
                i=next((i for i,v in enumerate(headers) if term in v),None)
                return cells[i] if i is not None else ''
            code,lot,ccy=col('stock code'),col('board lot'),col('currency')
            category=col('category')
            if not code.isdigit() or not lot.replace(',','').isdigit() or ccy!='HKD' or ('equity' not in category.lower() and 'equities' not in category.lower()): continue
            records.append(('HK:'+code.zfill(5),int(lot.replace(',','')),ccy,HK_LIST,'official',now(),'HKEX full securities list'))
        book.close()
        if not records: raise HTTPException(502,'港交所清单字段发生变化或没有可用港币股票，未覆盖本地规则')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.executemany('INSERT OR REPLACE INTO paper_contracts VALUES(?,?,?,?,?,?,?)',records)
        return {'count':len(records),'source':HK_LIST,'updated_at':now()}
