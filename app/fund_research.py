"""Cached fund directory and on-demand detail synchronization."""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

from app.providers import eastmoney_funds as source


def _read(db, key: str):
    with db() as conn:
        row = conn.execute("SELECT payload,updated_at FROM workspace_cache WHERE cache_key=?", (key,)).fetchone()
    return ({**json.loads(row["payload"]), "updated_at": row["updated_at"]} if row and row["payload"] else None)


def _write(db, key: str, value: dict):
    stamp = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        conn.execute("INSERT INTO workspace_cache(cache_key,payload,updated_at,last_error) VALUES(?,?,?,NULL) "
                     "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,last_error=NULL",
                     (key, json.dumps(value, ensure_ascii=False), stamp))
    return {**value, "updated_at": stamp}


def _fresh(data, seconds: int) -> bool:
    if not data:
        return False
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(data["updated_at"])).total_seconds() < seconds
    except (ValueError, TypeError, KeyError):
        return False


async def catalog(db, refresh: bool = False):
    old = _read(db, "funds:catalog")
    if old and not refresh and _fresh(old, 86400):
        return old
    try:
        rows = await asyncio.to_thread(source.fetch_catalog)
        return _write(db, "funds:catalog", {"rows": rows, "source": "东方财富基金代码目录",
            "source_url": source.CATALOG_URL, "state": "available"})
    except Exception:
        if old:
            return {**old, "state": "stale", "error": "基金目录同步失败，显示上次成功数据。"}
        raise


async def search(db, query: str = "", category: str = "all", page: int = 1, page_size: int = 20,
                 refresh: bool = False):
    data = await catalog(db, refresh)
    rows = data["rows"]
    categories = dict(sorted(Counter(tag for x in rows for tag in x.get("tags", [x["category"]])).items()))
    needle = query.casefold().strip()
    if needle:
        rows = [x for x in rows if needle in x["code"] or needle in x["name"].casefold() or
                needle in x["pinyin"].casefold()]
    if category != "all":
        rows = [x for x in rows if category in x.get("tags", [x["category"]])]
    total = len(rows)
    page = max(1, min(page, max(1, (total + page_size - 1) // page_size)))
    return {"rows": rows[(page - 1) * page_size: page * page_size], "total": total,
            "page": page, "page_size": page_size, "categories": categories,
            "state": data["state"], "error": data.get("error"), "updated_at": data["updated_at"],
            "source": data["source"], "source_url": data["source_url"],
            "coverage_note": "目录含来源列出的历史基金；是否仍可申购或交易需核对基金详情及交易平台。"}


async def detail(db, code: str, refresh: bool = False):
    old = _read(db, f"funds:detail:{code}")
    if old and not refresh and _fresh(old, 1800):
        return old
    directory = await catalog(db)
    item = next((x for x in directory["rows"] if x["code"] == code), None)
    if item is None:
        raise LookupError("基金代码不在东方财富目录中")
    try:
        value = await asyncio.to_thread(source.fetch_detail, code, item)
        return _write(db, f"funds:detail:{code}", {**value, "state": "available"})
    except Exception:
        if old:
            return {**old, "state": "stale", "error": "基金详情同步失败，显示上次成功数据。"}
        raise


async def flows(db, refresh: bool = False):
    def rotation_fallback():
        from app.research_data import cached as research_cached
        rotation = research_cached(db, "rotation", "今日") or {}
        rows = [{"name": x.get("名称"), "change_percent": x.get("今日涨跌幅"),
                 "net_flow_yuan": x.get("资金净额-元"), "main_net_ratio_percent": None}
                for x in rotation.get("rows", []) if x.get("名称") and x.get("资金净额-元") is not None]
        rows.sort(key=lambda x: x["net_flow_yuan"], reverse=True)
        if not rows:
            return None
        return {"rows": rows[:30], "state": "stale" if rotation.get("state") == "stale" else "partial",
                "source": "同花顺行业资金净额 · AKShare 备用数据", "flow_metric": "行业资金净额",
                "received_at": rotation.get("received_at"), "source_time": rotation.get("source_time"),
                "note": "东方财富行业资金接口暂不可用；以下为同花顺行业资金净额，单位元，口径与东方财富主力净流入不同，不可直接比较。"}

    async def one(kind, fetcher):
        old = _read(db, f"flows:{kind}")
        if old and not refresh and _fresh(old, 300):
            return old
        try:
            return _write(db, f"flows:{kind}", {**await asyncio.to_thread(fetcher), "state": "available"})
        except Exception:
            if kind == "sectors" and not old:
                try:
                    fallback = rotation_fallback()
                except Exception:
                    fallback = None
                if fallback:
                    return fallback
            return ({**old, "state": "stale", "error": "来源更新失败，显示上次成功数据。"}
                    if old else {"rows": [], "state": "error", "error": "来源暂不可用。"})
    north, sectors = await asyncio.gather(one("northbound", source.fetch_northbound),
                                           one("sectors", source.fetch_sector_flows))
    return {"northbound": north, "sectors": sectors}


async def refresh_catalog_loop(db):
    """Keep the broad directory current without crawling every fund detail."""
    while True:
        try:
            result = await catalog(db)
            await asyncio.sleep(1800 if result["state"] == "stale" else 3600)
        except Exception:
            await asyncio.sleep(1800)
