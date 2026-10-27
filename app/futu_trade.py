"""Owner-bound Futu OpenD trading. Quote connectivity never grants order access."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field

from app import security
from app.mysql_db import connect
from app.paper import StrictModel, amount, normalize
from app.providers.futu_provider import address, code_for

router = APIRouter(prefix="/api/v1", tags=["Futu trading"])
SESSION: Callable[[str], dict[str, Any]] | None = None
# The Futu SDK accepts CNH for CN simulated account queries, not CNY.
MARKETS = {"HK": "HKD", "US": "USD", "CN": "CNH"}


def configure(session: Callable[[str], dict[str, Any]]) -> None:
    global SESSION
    SESSION = session


def initialize() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS futu_trade_previews (
            preview_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, mode TEXT NOT NULL,
            connection_id TEXT NOT NULL, body TEXT NOT NULL, fingerprint TEXT NOT NULL,
            expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS futu_trade_orders (
            order_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, mode TEXT NOT NULL,
            connection_id TEXT NOT NULL, preview_id TEXT NOT NULL UNIQUE,
            request_key TEXT NOT NULL, body TEXT NOT NULL, client_serial TEXT NOT NULL,
            status TEXT NOT NULL, broker_order_id TEXT, broker_status TEXT,
            notional TEXT NOT NULL, filled_quantity DOUBLE NOT NULL DEFAULT 0,
            trade_day TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(owner_id,mode,request_key));
        """)
        db.execute("UPDATE futu_trade_orders SET status='unknown',error='服务重启，发送结果待核对' WHERE status='dispatching'")
        db.execute("UPDATE futu_trade_orders SET status='rejected',error='发送前中断' WHERE status='validating'")


def enabled(name: str, fallback: str = "false") -> bool:
    return os.getenv(name, fallback).lower() == "true"


def owner() -> str:
    current = security.current_owner_id()
    if current != security.primary_owner_id():
        raise HTTPException(403, "富途 OpenD 仅绑定本机拥有者")
    return current


def firm() -> str:
    value = os.getenv("FUTU_TRADE_SECURITY_FIRM", "FUTUSECURITIES").upper()
    if value not in {"FUTUSECURITIES", "FUTUINC", "FUTUSG"}:
        raise HTTPException(503, "富途交易主体配置无效")
    return value


def real_allowlist() -> set[str]:
    return {v.strip() for v in os.getenv("FUTU_REAL_ACCOUNT_IDS", "").split(",") if v.strip()}


def real_symbols() -> set[str]:
    return {normalize(v) for v in os.getenv("FUTU_REAL_SYMBOLS", "").split(",") if v.strip()}


def limits() -> tuple[Decimal, Decimal]:
    try:
        each = Decimal(os.getenv("FUTU_MAX_ORDER_NOTIONAL", "1000"))
        daily = Decimal(os.getenv("FUTU_MAX_DAILY_NOTIONAL", "3000"))
    except InvalidOperation as exc:
        raise HTTPException(503, "富途实盘限额配置无效") from exc
    if not each.is_finite() or not daily.is_finite() or each <= 0 or daily < each:
        raise HTTPException(503, "富途实盘限额配置无效")
    return each, daily


def _records(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        return data.to_dict(orient="records")
    if isinstance(data, list):
        return data
    raise HTTPException(502, "富途返回的数据格式无法识别")


class FutuError(RuntimeError):
    pass


class FutuClient:
    """One SDK context per call; easy to replace with a deterministic fake in tests."""

    def call(self, market: str, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            from futu import OpenSecTradeContext, RET_OK
            host, port = address()
            ctx = OpenSecTradeContext(filter_trdmarket=market, host=host, port=port, security_firm=firm())
            try:
                result, data = getattr(ctx, method)(**kwargs)
            finally:
                ctx.close()
            if result != RET_OK:
                raise FutuError(str(data)[:180])
            return _records(data)
        except FutuError:
            raise
        except Exception as exc:
            raise FutuError("富途 OpenD 交易连接失败：" + type(exc).__name__) from exc


CLIENT = FutuClient()


def connection_id(mode: str, market: str, acc_id: str) -> str:
    digest = hashlib.sha256(f"{firm()}:{mode}:{market}:{acc_id}".encode()).hexdigest()[:24]
    return f"futu-{mode.lower()}-{market.lower()}-{digest}"


def _market_auth(row: dict[str, Any], market: str) -> bool:
    value = row.get("trdmarket_auth")
    if isinstance(value, (list, tuple, set)):
        return market in value
    return market in re.findall(r"[A-Z]+", str(value or market).upper())


def _discover(mode: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not enabled("FUTU_TRADE_ENABLED"):
        return [], ["交易连接未启用（FUTU_TRADE_ENABLED=false）"]
    result: list[dict[str, Any]] = []
    errors: list[str] = []
    for market in ("HK", "US", "CN") if mode == "SIMULATE" else ("HK", "US"):
        try:
            rows = CLIENT.call(market, "get_acc_list")
        except FutuError as exc:
            errors.append(f"{market}: {exc}")
            continue
        for row in rows:
            acc_id = str(row.get("acc_id") or "")
            if not acc_id or acc_id == "0" or str(row.get("trd_env")).upper() != mode:
                continue
            if mode == "REAL" and acc_id not in real_allowlist():
                continue
            if mode == "REAL" and str(row.get("security_firm", firm())).upper() != firm():
                continue
            if not _market_auth(row, market):
                continue
            identifier = connection_id(mode, market, acc_id)
            if any(x["id"] == identifier for x in result):
                continue
            result.append({"id": identifier, "acc_id": acc_id, "market": market, "mode": mode,
                           "label": f"富途 {market} · 尾号 {acc_id[-4:]}",
                           "account_suffix": acc_id[-4:], "currency": MARKETS[market],
                           "account_status": str(row.get("acc_status") or "未知")})
    return result, errors


def _accounts(mode: str) -> list[dict[str, Any]]:
    return _discover(mode)[0]


async def accounts(mode: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_accounts, mode)


async def account(identifier: str, mode: str) -> dict[str, Any]:
    found = next((x for x in await accounts(mode) if x["id"] == identifier), None)
    if not found:
        raise HTTPException(404, "富途账户未找到或没有当前环境的交易权限")
    return found


def order_enabled(acc: dict[str, Any]) -> bool:
    if acc["mode"] == "SIMULATE":
        return enabled("FUTU_SIMULATE_ORDERS_ENABLED", "true")
    return (enabled("LIVE_TRADING_ENABLED") and enabled("FUTU_REAL_ORDERS_ENABLED")
            and acc["acc_id"] in real_allowlist() and bool(real_symbols()))


def _sdk(acc: dict[str, Any], method: str, **kwargs: Any) -> list[dict[str, Any]]:
    return CLIENT.call(acc["market"], method, trd_env=acc["mode"], acc_id=int(acc["acc_id"]), **kwargs)


def snapshot(acc: dict[str, Any]) -> dict[str, Any]:
    currency = acc["currency"]
    funds = _sdk(acc, "accinfo_query", refresh_cache=True, currency=currency)
    positions = _sdk(acc, "position_list_query", refresh_cache=True, currency=currency)
    if len(funds) != 1:
        raise FutuError("富途资金账户返回不唯一")
    f = funds[0]
    cash = f.get("cash")
    if cash is None:
        cash = f.get("available_funds")
    if cash is None:
        raise FutuError("富途未返回可核验现金")
    return {"connection_id": acc["id"], "account_suffix": acc["account_suffix"],
            "currency": currency, "cash": float(cash), "equity": f.get("total_assets"),
            "positions": [{"instrument_id": _instrument(p.get("code")),
                           "name": str(p.get("stock_name") or ""),
                           "quantity": float(p.get("qty") or 0),
                           "sellable": float(p.get("can_sell_qty") or 0),
                           "average_cost": p.get("cost_price")} for p in positions],
            "as_of": datetime.now(timezone.utc).isoformat(), "source": "富途 OpenD"}


def _instrument(code: Any) -> str:
    prefix, _, symbol = str(code or "").partition(".")
    return f"{'CN' if prefix in {'SH', 'SZ'} else prefix}:{symbol}" if symbol else str(code or "")


def _draft(body: dict[str, Any], acc: dict[str, Any]) -> tuple[dict[str, Any], str]:
    instrument = normalize(body["instrument_id"])
    market = instrument.split(":", 1)[0]
    if market != acc["market"]:
        raise HTTPException(422, "股票市场与富途账户不一致")
    if acc["mode"] == "REAL" and market not in {"HK", "US"}:
        raise HTTPException(422, "富途 CN A 股仅支持模拟；A 股通需另行验收")
    if acc["mode"] == "REAL" and instrument not in real_symbols():
        raise HTTPException(422, "股票不在实盘白名单")
    code = code_for(instrument)
    if not code:
        raise HTTPException(422, "富途不支持此股票代码")
    price = amount(body["limit_price"])
    quantity = int(body["quantity"])
    if price <= 0 or quantity <= 0 or (market == "US" and price.as_tuple().exponent < (-4 if price < 1 else -2)) or (market != "US" and price.as_tuple().exponent < -3):
        raise HTTPException(422, "限价或数量不符合该市场精度")
    if SESSION is None or SESSION(market)["phase"] != "open":
        raise HTTPException(422, "当前不在该市场的常规交易时段")
    return {**body, "instrument_id": instrument, "limit_price": str(price), "quantity": quantity}, code


def risk(acc: dict[str, Any], body: dict[str, Any], require_send: bool = True) -> dict[str, Any]:
    body, code = _draft(body, acc)
    if require_send and not order_enabled(acc):
        raise HTTPException(403, "该富途账户的订单发送尚未启用")
    price = amount(body["limit_price"])
    nominal = price * body["quantity"]
    if acc["mode"] == "REAL" and nominal > limits()[0]:
        raise HTTPException(422, "超过实盘单笔限额")
    capacity = _sdk(acc, "acctradinginfo_query", order_type="NORMAL", code=code, price=float(price), adjust_limit=0)
    if len(capacity) != 1:
        raise FutuError("富途未返回可核验交易数量")
    field = "max_cash_buy" if body["side"] == "buy" else "max_position_sell"
    available = capacity[0].get(field)
    if available is None or amount(available) < body["quantity"]:
        raise HTTPException(422, "富途现金可买或持仓可卖数量不足")
    funds = snapshot(acc)
    if body["side"] == "buy" and amount(funds["cash"]) < nominal * Decimal("1.01"):
        raise HTTPException(422, "现金不足，另需预留费用缓冲")
    return {"connection_id": acc["id"], "account_suffix": acc["account_suffix"],
            "instrument_id": body["instrument_id"], "side": body["side"],
            "quantity": body["quantity"], "limit_price": body["limit_price"],
            "notional": str(nominal), "currency": acc["currency"],
            "available_cash": funds["cash"], "broker_quantity_limit": str(available),
            "as_of": funds["as_of"], "mode": acc["mode"], "source": "富途 OpenD"}


def fingerprint(acc: dict[str, Any]) -> str:
    scope = [acc["id"], firm(), os.getenv("FUTU_REAL_ACCOUNT_IDS", ""),
             os.getenv("FUTU_REAL_SYMBOLS", ""), os.getenv("FUTU_MAX_ORDER_NOTIONAL", ""),
             os.getenv("FUTU_MAX_DAILY_NOTIONAL", ""), str(order_enabled(acc))]
    return hashlib.sha256(json.dumps(scope).encode()).hexdigest()


def market_day(market: str) -> str:
    zone = "America/New_York" if market == "US" else "Asia/Hong_Kong"
    return datetime.now(ZoneInfo(zone)).date().isoformat()


def _public(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["body_json"] = item.pop("body")
    item["client_serial"] = str(item["client_serial"])
    return item


class Draft(StrictModel):
    connection_id: str = Field(min_length=1, max_length=100)
    instrument_id: str = Field(min_length=4, max_length=30)
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(gt=0, le=1000000, strict=True)
    limit_price: Decimal = Field(gt=0, le=1000000, decimal_places=4)


class Confirmation(StrictModel):
    preview_id: str = Field(min_length=1, max_length=80)
    confirm: str = Field(pattern="^(REAL ORDER|SIMULATE ORDER)$")


async def _preview(body: Draft, mode: str) -> dict[str, Any]:
    owner_id = owner()
    acc = await account(body.connection_id, mode)
    request = body.model_dump(mode="json")
    try:
        view = await asyncio.to_thread(risk, acc, request, False)
    except FutuError as exc:
        raise HTTPException(502, str(exc)) from exc
    preview_id = "FP-" + uuid.uuid4().hex
    expiry = int(time.time()) + 45
    with connect() as db:
        db.execute("INSERT INTO futu_trade_previews(preview_id,owner_id,mode,connection_id,body,fingerprint,expires_at) VALUES(?,?,?,?,?,?,?)",
                   (preview_id, owner_id, mode, acc["id"], json.dumps(request), fingerprint(acc), expiry))
    return {**view, "preview_id": preview_id, "expires_at": expiry, "trading_enabled": order_enabled(acc)}


def _orders(mode: str, owner_id: str, limit: int = 100, offset: int = 0,
            connection_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as db:
        return [_public(r) for r in db.execute(
            "SELECT * FROM futu_trade_orders WHERE owner_id=? AND mode=? AND (? IS NULL OR connection_id=?) ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (owner_id, mode, connection_id, connection_id, limit, offset))]


async def _submit(body: Confirmation, key: str, mode: str) -> dict[str, Any]:
    owner_id = owner()
    expected = "REAL ORDER" if mode == "REAL" else "SIMULATE ORDER"
    if body.confirm != expected:
        raise HTTPException(422, "确认类型与交易环境不一致")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM futu_trade_orders WHERE owner_id=? AND mode=? AND request_key=?", (owner_id, mode, key)).fetchone()
        if prior:
            if prior["preview_id"] != body.preview_id:
                raise HTTPException(409, "同一请求标识已用于另一订单")
            return _public(prior)
        preview = db.execute("SELECT * FROM futu_trade_previews WHERE preview_id=? AND owner_id=? AND mode=?", (body.preview_id, owner_id, mode)).fetchone()
        if not preview:
            raise HTTPException(404, "订单预览不存在")
        if preview["expires_at"] < time.time():
            raise HTTPException(409, "预览已过期，请重新预览")
    acc = await account(preview["connection_id"], mode)
    if fingerprint(acc) != preview["fingerprint"] or not order_enabled(acc):
        raise HTTPException(409, "富途账户或风控配置已变化，请重新预览")
    request = json.loads(preview["body"])
    nominal = amount(request["limit_price"]) * request["quantity"]
    day = market_day(acc["market"])
    order_id = "FT-" + uuid.uuid4().hex[:20]
    serial = "F" + uuid.uuid4().hex[:20]
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM futu_trade_orders WHERE owner_id=? AND mode=? AND request_key=?", (owner_id, mode, key)).fetchone()
        if prior:
            if prior["preview_id"] != body.preview_id:
                raise HTTPException(409, "同一请求标识已用于另一订单")
            return _public(prior)
        if db.execute("SELECT 1 FROM futu_trade_orders WHERE preview_id=?", (body.preview_id,)).fetchone():
            raise HTTPException(409, "预览已被使用")
        if preview["expires_at"] < time.time():
            raise HTTPException(409, "预览已过期，请重新预览")
        if db.execute("SELECT 1 FROM futu_trade_orders WHERE connection_id=? AND status IN ('unknown','dispatching','cancel_unknown')", (acc["id"],)).fetchone():
            raise HTTPException(409, "该账户有结果未知的订单，请先核对")
        if mode == "REAL":
            used = sum((amount(r["notional"]) for r in db.execute("SELECT notional FROM futu_trade_orders WHERE connection_id=? AND trade_day=? AND status!='rejected'", (acc["id"], day))), Decimal(0))
            if used + nominal > limits()[1]:
                raise HTTPException(422, "超过当日实盘委托额度")
        db.execute("INSERT INTO futu_trade_orders(order_id,owner_id,mode,connection_id,preview_id,request_key,body,client_serial,status,notional,filled_quantity,trade_day,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (order_id, owner_id, mode, acc["id"], body.preview_id, key, json.dumps(request), serial, "validating", str(nominal), 0, day, now, now))
    dispatched = False
    try:
        await asyncio.to_thread(risk, acc, request)
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status='dispatching',updated_at=? WHERE order_id=?", (datetime.now(timezone.utc).isoformat(), order_id))
        dispatched = True
        code = code_for(request["instrument_id"])
        result = await asyncio.to_thread(_sdk, acc, "place_order", price=float(request["limit_price"]), qty=request["quantity"], code=code,
                                         trd_side="BUY" if request["side"] == "buy" else "SELL", order_type="NORMAL",
                                         adjust_limit=0, remark=serial, time_in_force="DAY", fill_outside_rth=False)
        if not result or not result[0].get("order_id"):
            raise FutuError("富途未返回可核验订单编号")
        broker_id = str(result[0]["order_id"])
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status='submitted',broker_order_id=?,broker_status=?,updated_at=? WHERE order_id=?",
                       (broker_id, str(result[0].get("order_status") or "已提交"), datetime.now(timezone.utc).isoformat(), order_id))
    except HTTPException as exc:
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status=?,error=?,updated_at=? WHERE order_id=?",
                       ("unknown" if dispatched else "rejected", str(exc.detail)[:180], datetime.now(timezone.utc).isoformat(), order_id))
    except FutuError as exc:
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status=?,error=?,updated_at=? WHERE order_id=?",
                       ("unknown" if dispatched else "rejected", str(exc)[:180], datetime.now(timezone.utc).isoformat(), order_id))
    return next(x for x in _orders(mode, owner_id) if x["order_id"] == order_id)


def _broker_status(raw: Any, filled: float) -> str:
    value = str(raw or "").upper()
    if "FILLED_ALL" in value or value in {"FILLED", "ALL_TRADED"}:
        return "filled"
    if "CANCEL" in value:
        return "canceled"
    if "FAIL" in value or "REJECT" in value or "DISABLED" in value:
        return "rejected"
    if "FILLED_PART" in value or filled > 0:
        return "partially_filled"
    return "submitted"


async def _reconcile(identifier: str, mode: str) -> dict[str, Any]:
    owner_id = owner()
    acc = await account(identifier, mode)
    local = _orders(mode, owner_id, limit=1000, connection_id=identifier)
    try:
        remote = await asyncio.to_thread(_sdk, acc, "order_list_query", refresh_cache=True)
    except FutuError as exc:
        raise HTTPException(502, str(exc)) from exc
    history_error = None
    history_queried = False
    today = market_day(acc["market"])
    if any(x["status"] in {"unknown", "cancel_unknown"} or x["trade_day"] < today for x in local):
        start = max(min((x["trade_day"] for x in local), default=today),
                    (datetime.now(ZoneInfo("America/New_York" if acc["market"] == "US" else "Asia/Hong_Kong")) - timedelta(days=90)).date().isoformat())
        try:
            history = await asyncio.to_thread(_sdk, acc, "history_order_list_query", start=start,
                                              end=today)
            remote.extend(history)
            history_queried = True
        except FutuError as exc:
            history_error = str(exc)
    unique_remote: dict[str, dict[str, Any]] = {}
    for broker_row in remote:
        broker_id = str(broker_row.get("order_id") or "")
        if broker_id:
            unique_remote[broker_id] = broker_row
    remote = list(unique_remote.values())
    for item in local:
        matches = [r for r in remote if str(r.get("order_id")) == str(item["broker_order_id"]) or
                   (item["client_serial"] and str(r.get("remark")) == item["client_serial"])]
        if len(matches) != 1:
            continue
        broker = matches[0]
        filled = float(broker.get("dealt_qty") or 0)
        status = _broker_status(broker.get("order_status"), filled)
        if item["status"] == "filled" and status != "filled":
            continue
        if item["status"] == "partially_filled" and status == "submitted":
            status = "partially_filled"
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status=?,broker_order_id=?,broker_status=?,filled_quantity=?,error=NULL,updated_at=? WHERE order_id=? AND owner_id=?",
                       (status, str(broker.get("order_id")), str(broker.get("order_status")), max(filled, float(item["filled_quantity"])),
                        datetime.now(timezone.utc).isoformat(), item["order_id"], owner_id))
    return {"connection_id": identifier, "orders": _orders(mode, owner_id, connection_id=identifier),
            "note": "已查询富途当前委托" + ("与近90日历史委托" if history_queried else "") +
                    (f"；历史委托查询失败：{history_error}" if history_error else "") + "；仍未知的订单不得自动重发。"}


async def _cancel(order_id: str, mode: str) -> dict[str, Any]:
    owner_id = owner()
    with connect() as db:
        stored = db.execute("SELECT * FROM futu_trade_orders WHERE owner_id=? AND mode=? AND order_id=?",
                            (owner_id, mode, order_id)).fetchone()
    row = _public(stored) if stored else None
    if not row or not row["broker_order_id"]:
        raise HTTPException(404, "没有可核验的富途委托")
    if row["status"] in {"filled", "canceled", "rejected", "cancel_requested", "cancel_unknown"}:
        return row
    acc = await account(row["connection_id"], mode)
    with connect() as db:
        db.execute("UPDATE futu_trade_orders SET status='cancel_requested',updated_at=? WHERE order_id=?", (datetime.now(timezone.utc).isoformat(), order_id))
    try:
        await asyncio.to_thread(_sdk, acc, "modify_order", modify_order_op="CANCEL", order_id=int(row["broker_order_id"]), qty=0, price=0)
    except FutuError as exc:
        with connect() as db:
            db.execute("UPDATE futu_trade_orders SET status='cancel_unknown',error=?,updated_at=? WHERE order_id=?",
                       (str(exc)[:180], datetime.now(timezone.utc).isoformat(), order_id))
    with connect() as db:
        updated = db.execute("SELECT * FROM futu_trade_orders WHERE owner_id=? AND mode=? AND order_id=?",
                             (owner_id, mode, order_id)).fetchone()
    return _public(updated)


@router.get("/live/status")
async def live_status():
    owner()
    found, errors = await asyncio.to_thread(_discover, "REAL")
    each, daily = limits()
    connections = [{**{k: v for k, v in a.items() if k != "acc_id"}, "provider": "futu", "configured": True,
                    "trading_enabled": order_enabled(a),
                    "read_state": "account_discovered", "order_state": "configured_unlock_unverified" if order_enabled(a) else "order_disabled",
                    "max_order_notional": str(each), "max_daily_notional": str(daily),
                    "symbols": sorted(real_symbols()), "error": None} for a in found]
    note = ("；".join(errors[:2]) if errors and not found else
            "未发现白名单内富途真实账户；请检查 OpenD 登录、主体和 FUTU_REAL_ACCOUNT_IDS。" if not found else
            "已登录账户并不等于实盘下单已授权。真实订单逐笔预览确认，默认关闭发送；解锁状态以富途回报为准。")
    return {"mode": "live", "connections": connections,
            "catalog": [{"name": "富途 OpenD", "market": "HK / US", "interface": "官方 OpenSecTradeContext",
                         "status": "真实账户需在 OpenD 登录和手动解锁；A 股 CN 仅支持模拟。"}],
            "note": note}


@router.get("/live/accounts/{identifier}")
async def live_account(identifier: str):
    owner()
    acc = await account(identifier, "REAL")
    try:
        return await asyncio.to_thread(snapshot, acc)
    except FutuError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/live/orders/preview")
async def live_preview(body: Draft):
    return await _preview(body, "REAL")


@router.post("/live/orders")
async def live_submit(body: Confirmation, idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100)):
    return await _submit(body, idempotency_key, "REAL")


@router.get("/live/orders")
def live_orders():
    return _orders("REAL", owner())


@router.post("/live/connections/{identifier}/reconcile")
async def live_reconcile(identifier: str):
    return await _reconcile(identifier, "REAL")


@router.post("/live/orders/{order_id}/cancel")
async def live_cancel(order_id: str):
    return await _cancel(order_id, "REAL")


@router.get("/futu-paper/status")
async def paper_status():
    owner()
    found, errors = await asyncio.to_thread(_discover, "SIMULATE")
    note = ("；".join(errors[:2]) if errors and not found else
            "未发现富途模拟账户；请在 OpenD 完成登录并检查账户权限。" if not found else
            "富途模拟盘由官方模拟环境撮合，不与本地模拟账本合并。")
    return {"mode": "paper", "source": "futu", "connections": [{**{k: v for k, v in a.items() if k != "acc_id"}, "trading_enabled": order_enabled(a)} for a in found],
            "enabled": enabled("FUTU_TRADE_ENABLED"), "note": note}


@router.get("/futu-paper/accounts/{identifier}")
async def paper_account(identifier: str):
    owner()
    acc = await account(identifier, "SIMULATE")
    try:
        return await asyncio.to_thread(snapshot, acc)
    except FutuError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/futu-paper/orders/preview")
async def paper_preview(body: Draft):
    return await _preview(body, "SIMULATE")


@router.post("/futu-paper/orders")
async def paper_submit(body: Confirmation, idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=100)):
    return await _submit(body, idempotency_key, "SIMULATE")


@router.get("/futu-paper/orders")
def paper_orders():
    return _orders("SIMULATE", owner())


@router.post("/futu-paper/connections/{identifier}/reconcile")
async def paper_reconcile(identifier: str):
    return await _reconcile(identifier, "SIMULATE")


@router.post("/futu-paper/orders/{order_id}/cancel")
async def paper_cancel(order_id: str):
    return await _cancel(order_id, "SIMULATE")
