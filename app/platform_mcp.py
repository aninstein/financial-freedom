"""Built-in, owner-bound MCP contract for the Finch workspace.

The model chooses a named resource, never a SQL statement or arbitrary URL.
Write operations are limited to user-authored state. Market observations and
derived research evidence are read-only.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException

from app import futu_trade, holdings, investment_memory as memory, investment_wiki as wiki, platform_workspace as workspace, security
from app.mysql_db import connect

READABLE = {
    "cards": "右侧工作台卡片顺序、显示状态、自定义内容和附注",
    "calendar": "用户计划、事件、订阅和提醒确认记录",
    "holdings": "当前用户的股票、基金、黄金持仓及估值",
    "paper_local_accounts": "本地模拟盘账户、虚拟现金、持仓与估值；可按 account_id 读取",
    "paper_local_orders": "本地模拟盘委托账本；可按 account_id 分页",
    "paper_local_ai_runs": "本地 AI 模拟交易任务和订单；可按 account_id 或 run_id 读取",
    "paper_futu_accounts": "富途 SIMULATE 账户目录；指定 connection_id 后读取资金与持仓",
    "paper_futu_orders": "本平台富途 SIMULATE 委托回报；可按 connection_id 分页",
    "live_futu_accounts": "富途 REAL 账户目录；指定 connection_id 后只读查询资金与持仓",
    "live_futu_orders": "本平台富途 REAL 委托回报；可按 connection_id 分页",
    "watchlist": "自选标的与缓存行情",
    "quotes": "各市场缓存行情与来源时间",
    "market_status": "交易状态与交易所时钟",
    "market_calendar": "交易所开闭市日历，最长 63 天",
    "indices": "指数目录与缓存收盘信息",
    "index": "单个指数的日线与分析",
    "index_live": "主要指数的实时或延迟快照",
    "providers": "行情源状态和数据覆盖",
    "news": "已采集的财经新闻",
    "liquidity": "央行流动性事件",
    "sectors": "板块轮动与资金",
    "flows": "市场资金统计及覆盖说明",
    "instrument": "标的详情、财务及快照",
    "instrument_search": "标的名称和代码搜索",
    "bars": "标的历史日线",
    "documents": "已导入研报资料目录",
    "document_page": "研报或财报指定页的已提取文字",
    "research": "当前用户的投研记录与证据",
    "backtests": "策略回测记录",
    "calendar_insights": "指定交易日的指数、自选与资金观察",
    "memory_settings": "当前用户的记忆保留期限与归档状态",
    "agent_status": "当前 Agent 运行时、模型名称和能力状态，不含密钥",
    "extensions": "已安装 Skills 与 MCP 的公开元数据，不含凭据",
    "wiki_tree": "投资记忆目录；不读取历史原始会话",
    "wiki_file": "投资记忆 Markdown 文档；不读取历史原始会话",
    "memory": "按当前问题召回已归档记忆",
}
WRITABLE = {
    "cards": "设置右栏顺序、显隐、宽度；创建或修改自定义卡片及内置卡片附注",
    "calendar": "创建、修改、删除日历计划/事件/订阅；确认提醒",
    "holdings": "登记当前用户某币种的完整持仓快照，需带 expected_updated_at",
    "watchlist": "添加或移除自选标的",
    "wiki_file": "编辑当前用户的 Markdown 记忆文件，需带 expected_sha256",
}


def definitions() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "mcp__finch__catalog",
         "description": "列出 Finch 平台可读数据源、可写用户内容及所需参数。操作页面前先查询。",
         "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
        {"type": "function", "function": {"name": "mcp__finch__read",
         "description": "读取平台页面同源数据。resource 从 catalog 选取；params 可指定日期、市场、标的、分页。",
         "parameters": {"type": "object", "properties": {"resource": {"type": "string", "enum": list(READABLE)},
         "params": {"type": "object"}}, "required": ["resource"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "mcp__finch__write",
         "description": "仅在用户要求创建或修改时写入本人内容：右栏卡片、日历、自选、持仓、wiki。先读取现状，使用版本/哈希防覆盖，写后再读验证。不能改行情、证据、凭据或下单。",
         "parameters": {"type": "object", "properties": {"resource": {"type": "string", "enum": list(WRITABLE)},
         "action": {"type": "string"}, "data": {"type": "object"}},
         "required": ["resource", "action", "data"], "additionalProperties": False}}},
    ]


def catalog() -> dict[str, Any]:
    return {"readable": READABLE, "writable": WRITABLE,
            "card_actions": ["set_layout", "create_note", "update_note", "delete_note", "set_builtin_note"],
            "calendar_actions": ["create", "update", "delete", "acknowledge"],
            "account_scope": "owner-bound; owner_id is supplied by the trusted runtime, never the model",
            "limits": "模拟与实盘交易数据仅只读；不提供下单、撤单、核对写入、账户凭据或历史原始会话工具"}


def _bounded(value: Any, default: int = 30, maximum: int = 100) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "limit 须为正整数") from exc
    if not 1 <= number <= maximum:
        raise HTTPException(422, "limit 超出范围")
    return number


def _offset(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "offset 须为非负整数") from exc
    if not 0 <= number <= 100000:
        raise HTTPException(422, "offset 超出范围")
    return number


def _paper_broker(owner_id: str):
    from app import main
    return main.Broker(main.db, main._session_status, main._quote_with_age,
                       main._observed_at, main.REFRESH_SECONDS, owner_id)


def _futu_owner(owner_id: str) -> None:
    if not owner_id or owner_id != security.primary_owner_id():
        raise HTTPException(403, "富途 OpenD 数据仅供本机拥有者读取")


def _futu_order_view(row: dict[str, Any], mode: str) -> dict[str, Any]:
    body = json.loads(row["body_json"])
    return {"order_id": row["order_id"], "connection_id": row["connection_id"],
            "mode": mode, "source": "futu", "instrument_id": body["instrument_id"],
            "side": body["side"], "quantity": body["quantity"],
            "limit_price": body["limit_price"], "notional": row["notional"],
            "status": row["status"], "broker_status": row["broker_status"],
            "filled_quantity": row["filled_quantity"], "error": row["error"],
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def _paper_order_view(row: dict[str, Any]) -> dict[str, Any]:
    fields = ("order_id", "account_id", "instrument_id", "side", "order_type",
              "quantity", "limit_price", "status", "fill_price", "fee",
              "actor", "ai_run_id", "reason", "created_at", "updated_at",
              "source_quote_at")
    return {"source": "local", "mode": "paper",
            **{key: row[key] for key in fields if key in row}}


async def read(owner_id: str, resource: str, params: dict[str, Any] | None = None) -> Any:
    if resource not in READABLE:
        raise HTTPException(404, "未开放的数据源")
    p = params or {}
    if not isinstance(p, dict):
        raise HTTPException(422, "params 必须是对象")
    if resource in {"cards", "calendar"}:
        return workspace.get_state(owner_id, resource)
    if resource == "holdings":
        return holdings.get_portfolios(owner_id, p.get("currency"))
    if resource == "wiki_tree":
        return wiki.list_directory(owner_id, str(p.get("path", "")))
    if resource == "wiki_file":
        path = str(p.get("path", ""))
        if path.startswith("sessions/") and path.endswith(".summary.md"):
            raise HTTPException(403, "跨会话只读取归档日报与分层记忆")
        return wiki.get_document(owner_id, path)
    if resource == "memory":
        return memory.recall(owner_id, str(p.get("query", "")), limit=min(_bounded(p.get("limit"), 10, 20), 20))
    if resource == "memory_settings":
        return memory.get_settings(owner_id)
    if resource == "paper_local_accounts":
        broker = _paper_broker(owner_id)
        account_id = str(p.get("account_id") or "")
        with connect() as db:
            if account_id:
                return {"source": "local", **broker.portfolio(db, account_id)}
            rows = db.execute(
                "SELECT account_id FROM paper_accounts WHERE owner_id=? AND state='active' ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (owner_id, _bounded(p.get("limit"), 30, 100), _offset(p.get("offset")))).fetchall()
            return [{"source": "local", **broker.portfolio(db, row["account_id"])} for row in rows]
    if resource == "paper_local_orders":
        broker = _paper_broker(owner_id)
        account_id = str(p.get("account_id") or "") or None
        with connect() as db:
            if account_id:
                broker._account(db, account_id)
            return [_paper_order_view(dict(row)) for row in db.execute(
                "SELECT o.* FROM paper_orders o JOIN paper_accounts a ON a.account_id=o.account_id WHERE a.owner_id=? AND a.state='active' AND (? IS NULL OR o.account_id=?) ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
                (owner_id, account_id, account_id, _bounded(p.get("limit"), 30, 100), _offset(p.get("offset"))))]
    if resource == "paper_local_ai_runs":
        from app import paper_agent
        broker = _paper_broker(owner_id)
        run_id = str(p.get("run_id") or "")
        if run_id:
            run = paper_agent.get_run(broker, run_id)
            run.pop("idempotency_key", None)
            run["orders"] = [_paper_order_view(row) for row in run["orders"]]
            return {"source": "local", "mode": "paper", **run}
        account_id = str(p.get("account_id") or "") or None
        with connect() as db:
            if account_id:
                broker._account(db, account_id)
            rows = db.execute(
                "SELECT r.run_id,r.account_id,r.status,r.created_at,r.completed_at FROM paper_ai_runs r JOIN paper_accounts a ON a.account_id=r.account_id WHERE a.owner_id=? AND a.state='active' AND (? IS NULL OR r.account_id=?) ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                (owner_id, account_id, account_id, _bounded(p.get("limit"), 20, 100), _offset(p.get("offset")))).fetchall()
            return [{"source": "local", "mode": "paper", **dict(row)} for row in rows]
    if resource in {"paper_futu_accounts", "live_futu_accounts"}:
        _futu_owner(owner_id)
        mode = "SIMULATE" if resource == "paper_futu_accounts" else "REAL"
        found, errors = await asyncio.to_thread(futu_trade._discover, mode)
        connection_id = str(p.get("connection_id") or "")
        if connection_id:
            account = next((item for item in found if item["id"] == connection_id), None)
            if not account:
                raise HTTPException(404, "富途账户未找到或当前环境不可用")
            try:
                return {"mode": mode, **await asyncio.to_thread(futu_trade.snapshot, account)}
            except futu_trade.FutuError as exc:
                raise HTTPException(502, str(exc)) from exc
        return {"source": "futu", "mode": mode,
                "accounts": [{k: v for k, v in account.items() if k != "acc_id"} for account in found],
                "as_of": datetime.now(timezone.utc).isoformat(),
                "note": "；".join(errors[:2]) if errors and not found else
                        "账户目录不等于已验证交易解锁；指定 connection_id 查询资金与持仓。"}
    if resource in {"paper_futu_orders", "live_futu_orders"}:
        _futu_owner(owner_id)
        mode = "SIMULATE" if resource == "paper_futu_orders" else "REAL"
        connection_id = str(p.get("connection_id") or "") or None
        rows = futu_trade._orders(mode, owner_id, _bounded(p.get("limit"), 30, 100),
                                  _offset(p.get("offset")), connection_id)
        return {"source": "futu", "mode": mode,
                "scope": "本平台记录的委托；不等于券商全部历史",
                "orders": [_futu_order_view(row, mode) for row in rows]}
    if resource == "extensions":
        from app import agent_extensions
        return {"skills": [{"name": row["name"], "description": row["description"]}
                           for row in agent_extensions.list_skills()],
                "mcp": [{"name": row["name"], "status": row["status"], "tools": row["tools"]}
                        for row in agent_extensions.list_mcp()]}

    # These adapters are the same ones used by the page API; no external fetch
    # is triggered by a broad resource read.
    from app import main
    if resource == "agent_status":
        return main.ai_status()
    if resource == "watchlist":
        return main.get_watchlist()[:_bounded(p.get("limit"), 50, 100)]
    if resource == "quotes":
        return main.quotes(market=p.get("market"), q=p.get("query"), limit=_bounded(p.get("limit"), 30, 100), offset=max(0, int(p.get("offset", 0))), browse=True)
    if resource == "market_status":
        return main.market_status(p.get("market"))
    if resource == "market_calendar":
        start = date.fromisoformat(str(p.get("start")))
        end = date.fromisoformat(str(p.get("end")))
        return main.market_calendar(start, end, str(p.get("markets", "CN,HK,US")))
    if resource == "indices":
        return main.research_indices()
    if resource == "index_live":
        return main.research_indices_live()
    if resource == "index":
        result = await main.research_index(str(p.get("index_id", "")), refresh=False)
        result["bars"] = result.get("bars", [])[-_bounded(p.get("limit"), 60, 250):]
        return result
    if resource == "providers":
        return main.providers()
    if resource == "news":
        from app.market_context import news_context
        return await news_context(main.db, str(p.get("query", "")), _bounded(p.get("limit"), 30, 100), False)
    if resource == "liquidity":
        from app.market_context import liquidity_context
        return await liquidity_context(main.db, False)
    if resource == "sectors":
        from app.market_context import sector_rotation
        return await sector_rotation(main.db, False)
    if resource == "flows":
        return await main.research_flows(False)
    if resource == "instrument":
        from app.providers.instrument_provider import dossier
        instrument_id = str(p.get("instrument_id", ""))
        if not re.fullmatch(r"[A-Z]+:[A-Z0-9._-]{1,48}", instrument_id, re.I):
            raise HTTPException(422, "标的编号无效")
        sections = p.get("sections") or ["profile", "snapshot", "financials"]
        return await dossier(main.db, instrument_id, sections)
    if resource == "instrument_search":
        return main.search_instruments(str(p.get("query", "")), _bounded(p.get("limit"), 10, 20))
    if resource == "bars":
        result = main.get_bars(str(p.get("instrument_id", "")), "1d",
                               date.fromisoformat(str(p["start"])) if p.get("start") else None,
                               date.fromisoformat(str(p["end"])) if p.get("end") else None)
        if isinstance(result, dict):
            for key in ("bars", "rows"):
                if isinstance(result.get(key), list):
                    result[key] = result[key][-_bounded(p.get("limit"), 100, 250):]
        return result
    if resource == "documents":
        with connect() as db:
            return [dict(row) for row in db.execute("SELECT document_id,filename,document_type,instrument_id,report_period,page_count,imported_at FROM ai_documents ORDER BY imported_at DESC LIMIT ?", (_bounded(p.get("limit"), 30, 100),))]
    if resource == "document_page":
        document_id = str(p.get("document_id", ""))
        page = int(p.get("page", 1))
        if not re.fullmatch(r"D-[A-Z0-9]{12}", document_id) or not 1 <= page <= 500:
            raise HTTPException(422, "资料编号或页码无效")
        with connect() as db:
            row = db.execute("SELECT d.filename,d.document_type,d.report_period,p.page_no,p.content FROM ai_document_pages p JOIN ai_documents d ON d.document_id=p.document_id WHERE p.document_id=? AND p.page_no=?", (document_id, page)).fetchone()
        if not row:
            raise HTTPException(404, "资料页不存在")
        return {**dict(row), "content": row["content"][:12000]}
    if resource == "research":
        run_id = str(p.get("run_id", ""))
        with connect() as db:
            if run_id:
                row = db.execute("SELECT run_id,question,status,answer,evidence_json,created_at,completed_at FROM ai_research_runs WHERE owner_id=? AND run_id=?", (owner_id, run_id)).fetchone()
                if not row:
                    raise HTTPException(404, "投研记录不存在")
                return {**dict(row), "evidence": json.loads(row["evidence_json"] or "[]")}
            return [dict(row) for row in db.execute("SELECT run_id,question,status,created_at,completed_at FROM ai_research_runs WHERE owner_id=? ORDER BY created_at DESC LIMIT ?", (owner_id, _bounded(p.get("limit"), 20, 100)))]
    if resource == "backtests":
        with connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM research_runs ORDER BY created_at DESC LIMIT ?", (_bounded(p.get("limit"), 30, 100),))]
    if resource == "calendar_insights":
        return await main.calendar_insights(date.fromisoformat(str(p.get("date"))))
    raise HTTPException(404, "数据源不可用")


async def write(owner_id: str, resource: str, action: str, data: dict[str, Any]) -> Any:
    if resource not in WRITABLE or not isinstance(data, dict):
        raise HTTPException(422, "写入的数据源或内容无效")
    if resource == "cards":
        state = workspace.get_state(owner_id, "cards")
        expected = data.get("expected_version")
        if expected is None or expected != state["version"]:
            raise HTTPException(409, "先读取当前卡片版本，再提交修改")
        if action == "set_layout":
            for key in ("cards", "wide", "visible", "width", "expanded_card"):
                if key in data:
                    state[key] = data[key]
        elif action == "create_note":
            import uuid
            ident = "note:" + uuid.uuid4().hex[:16]
            state["custom_cards"][ident] = {"title": data.get("title", ""), "body": data.get("body", "")}
            state["cards"].append(ident)
        elif action in {"update_note", "delete_note"}:
            ident = str(data.get("id", ""))
            if ident not in state["custom_cards"]:
                raise HTTPException(404, "自定义卡片不存在")
            if action == "delete_note":
                del state["custom_cards"][ident]
                state["cards"] = [x for x in state["cards"] if x != ident]
                if state.get("expanded_card") == ident:
                    state["expanded_card"] = None
            else:
                state["custom_cards"][ident].update({k: data[k] for k in ("title", "body") if k in data})
        elif action == "set_builtin_note":
            ident = str(data.get("id", ""))
            if ident not in workspace.BUILTIN_CARDS:
                raise HTTPException(404, "内置卡片不存在")
            state["overrides"][ident] = {"title": data.get("title", ""), "note": data.get("note", "")}
        else:
            raise HTTPException(422, "未知卡片操作")
        return workspace.put_state(owner_id, "cards", state, expected)
    if resource == "calendar":
        state = workspace.get_state(owner_id, "calendar")
        expected = data.get("expected_version")
        if expected is None or expected != state["version"]:
            raise HTTPException(409, "先读取当前日历版本，再提交修改")
        kind = str(data.get("kind", ""))
        collection = {"plan": "plans", "event": "events", "subscription": "subscriptions"}.get(kind)
        if action in {"create", "update", "delete"} and not collection:
            raise HTTPException(422, "kind 须为 plan/event/subscription")
        if action == "create":
            import uuid
            item = dict(data.get("item") or {})
            item["id"] = uuid.uuid4().hex
            item.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
            state[collection].append(item)
        elif action in {"update", "delete"}:
            ident = str(data.get("id", ""))
            if not any(x["id"] == ident for x in state[collection]):
                raise HTTPException(404, "日历记录不存在")
            if action == "delete":
                state[collection] = [x for x in state[collection] if x["id"] != ident]
            else:
                patch = dict(data.get("patch") or {})
                patch.pop("id", None)
                state[collection] = [{**x, **patch} if x["id"] == ident else x for x in state[collection]]
        elif action == "acknowledge":
            state["alarmAcknowledged"][str(data.get("id", ""))] = datetime.now(timezone.utc).isoformat()
        else:
            raise HTTPException(422, "未知日历操作")
        return workspace.put_state(owner_id, "calendar", state, expected)
    if resource == "holdings" and action == "replace_snapshot":
        return holdings.save_snapshot(owner_id, str(data.get("currency", "")), holdings.SnapshotInput.model_validate(data.get("snapshot", {})))
    if resource == "wiki_file" and action == "edit":
        return wiki.save_document(owner_id, str(data.get("path", "")), str(data.get("content", "")), str(data.get("expected_sha256", "")))
    if resource == "watchlist" and action in {"add", "remove"}:
        from app import main
        instrument = str(data.get("instrument_id", ""))
        return await main.add_watchlist(main.WatchItem(instrument_id=instrument)) if action == "add" else main.remove_watchlist(instrument)
    raise HTTPException(422, "该数据源不支持此写入操作")
