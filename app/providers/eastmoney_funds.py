"""Bounded adapters for public Eastmoney / Tiantian fund pages.

These are website data endpoints, not a contracted trading API. Every field keeps
its source date and absent intraday estimates remain null.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; finfreedomResearch/1.0)",
           "Referer": "https://fund.eastmoney.com/"}
CATALOG_URL = "https://fund.eastmoney.com/js/fundcode_search.js"
FUND_ROOT = "https://fund.eastmoney.com"
DATA_ROOT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SECTOR_URL = "https://push2.eastmoney.com/api/qt/clist/get"
QUOTE_URL = "https://push2his.eastmoney.com/api/qt/stock/get"


def _get(url: str, *, params: dict | None = None) -> str:
    response = requests.get(url, params=params, headers=HEADERS, timeout=10)
    response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ValueError("来源响应过大")
    return response.text.lstrip("\ufeff")


def _assignment(source: str, name: str):
    match = re.search(r"\bvar\s+" + re.escape(name) + r"\s*=\s*", source)
    if not match:
        return None
    try:
        return json.JSONDecoder().raw_decode(source[match.end():].lstrip())[0]
    except (ValueError, TypeError):
        return None


def _number(value):
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _stamp(milliseconds):
    try:
        return datetime.fromtimestamp(int(milliseconds) / 1000, timezone.utc).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def analyze_nav(history: list[dict]) -> dict:
    """Descriptive risk metrics from published, unadjusted unit NAV only."""
    sample = history[-253:]
    values = [x["nav"] for x in sample if x.get("nav") is not None and x["nav"] > 0]
    if len(values) < 20:
        return {"observations": len(values), "volatility_percent": None, "max_drawdown_percent": None,
                "note": "净值样本不足20条，暂不计算波动和回撤。"}
    returns = [values[i] / values[i - 1] - 1 for i in range(1, len(values))]
    mean = sum(returns) / len(returns)
    variance = sum((x - mean) ** 2 for x in returns) / (len(returns) - 1) if len(returns) > 1 else 0
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return {"observations": len(values), "first_date": sample[0]["date"], "last_date": sample[-1]["date"],
            "volatility_percent": round(math.sqrt(variance) * math.sqrt(252) * 100, 2),
            "max_drawdown_percent": round(drawdown * 100, 2),
            "note": "最近最多253条已公布单位净值；波动按相邻净值收益年化，回撤按单位净值峰值计算。未计分红及份额变化，不是总回报或预测。"}


def _is_exchange_traded(name: str, fund_type: str = "") -> bool:
    upper = name.upper()
    return (("ETF" in upper and "联接" not in name and "连接" not in name)
            or "LOF" in upper or "REIT" in upper or fund_type.lower() == "reits")


def classify(name: str, fund_type: str) -> str:
    if "ETF" in name.upper() and _is_exchange_traded(name, fund_type):
        return "ETF"
    if "LOF" in name.upper():
        return "LOF"
    if "REIT" in name.upper() or "Reits" in fund_type:
        return "REITs"
    if fund_type.startswith("QDII") or "海外" in fund_type:
        return "QDII"
    if fund_type.startswith("债券"):
        return "债券"
    if fund_type.startswith("货币"):
        return "货币"
    if fund_type.startswith("FOF"):
        return "FOF"
    if fund_type.startswith("指数"):
        return "指数"
    if fund_type.startswith("股票"):
        return "股票"
    if fund_type.startswith("混合"):
        return "混合"
    return "其他"


def fetch_catalog() -> list[dict]:
    source = _get(CATALOG_URL)
    match = re.search(r"\bvar\s+r\s*=\s*", source)
    if not match:
        raise ValueError("基金目录格式已变化")
    raw = json.JSONDecoder().raw_decode(source[match.end():].lstrip())[0]
    rows = []
    for item in raw:
        if not isinstance(item, list) or len(item) < 4 or not re.fullmatch(r"\d{6}", str(item[0])):
            continue
        code, pinyin, name, fund_type = map(str, item[:4])
        category = classify(name, fund_type)
        tags = {category}
        if fund_type.startswith("QDII") or "海外" in fund_type:
            tags.add("QDII")
        if fund_type.startswith("债券") or "固收" in fund_type:
            tags.add("债券")
        if "REIT" in name.upper() or "Reits" in fund_type:
            tags.add("REITs")
        rows.append({"code": code, "name": name, "pinyin": pinyin,
                     "fund_type": fund_type, "category": category, "tags": sorted(tags),
                     "venue": "场内" if _is_exchange_traded(name, fund_type) else "场外或待核实"})
    if len(rows) < 10000:
        raise ValueError("基金目录条数异常")
    return rows


def _basic_info(code: str) -> dict:
    html = _get(f"{FUND_ROOT}/f10/jbgk_{code}.html")
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for th in soup.select("th"):
        key = th.get_text(" ", strip=True)
        td = th.find_next_sibling("td")
        if key and td:
            fields[key] = td.get_text(" ", strip=True)
    manager_cell = next((th.find_next_sibling("td") for th in soup.select("th")
                         if th.get_text(" ", strip=True) == "基金管理人"), None)
    company_href = manager_cell.select_one("a[href]") if manager_cell else None
    company_url = ("https:" + company_href["href"] if company_href and company_href["href"].startswith("//fund.eastmoney.com/company/")
                   else None)
    return {"full_name": fields.get("基金全称"), "company": fields.get("基金管理人"),
            "company_url": company_url,
            "custodian": fields.get("基金托管人"), "founded": fields.get("成立日期/规模"),
            "asset_size": fields.get("净资产规模"), "management_fee": fields.get("管理费率"),
            "custody_fee": fields.get("托管费率"), "sales_service_fee": fields.get("销售服务费率"),
            "purchase_fee": fields.get("最高申购费率"), "redemption_fee": fields.get("最高赎回费率"),
            "benchmark": fields.get("业绩比较基准"), "tracking_target": fields.get("跟踪标的"),
            "source_url": f"{FUND_ROOT}/f10/jbgk_{code}.html"}


def _holdings(code: str, year: int, month: int, kind: str = "stock") -> tuple[list[dict], str | None]:
    source = _get(f"{FUND_ROOT}/f10/FundArchivesDatas.aspx",
                  params={"type": "zqcc" if kind == "bond" else "jjcc", "code": code,
                          "topline": 10, "year": year, "month": month})
    match = re.search(r'content:"((?:\\.|[^"\\])*)"', source)
    if not match:
        return [], None
    soup = BeautifulSoup(json.loads('"' + match.group(1) + '"'), "html.parser")
    title = soup.select_one("h4")
    result = []
    for tr in soup.select("table tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]
        if len(cells) < (5 if kind == "bond" else 9) or not re.fullmatch(r"[A-Za-z0-9.]{1,16}", cells[1]):
            continue
        result.append({"code": cells[1], "name": cells[2],
                       "weight_percent": _number(cells[3] if kind == "bond" else cells[6]),
                       "shares_10k": None if kind == "bond" else _number(cells[7]),
                       "market_value_10k": _number(cells[4] if kind == "bond" else cells[8])})
    return result[:10], title.get_text(" ", strip=True) if title else None


def _trade_status(code: str) -> dict:
    source = _get(f"{FUND_ROOT}/Data/Fund_JJJZ_Data.aspx", params={
        "t": "1", "lx": "1", "text": code, "sort": "zdf,desc", "page": "1,10", "onlySale": "0"})
    match = re.search(r"\bdatas\s*:\s*", source)
    if not match:
        return {}
    rows = json.JSONDecoder().raw_decode(source[match.end():])[0]
    row = next((x for x in rows if x and x[0] == code), None)
    return {"purchase": row[9] or None, "redemption": row[10] or None} if row and len(row) > 10 else {}


def _exchange_quote(code: str) -> dict | None:
    secid = ("1" if code.startswith(("5", "6")) else "0") + "." + code
    payload = json.loads(_get(QUOTE_URL, params={"secid": secid,
        "fields": "f43,f170,f57,f58,f124", "fltt": "2", "invt": "2"}))
    data = payload.get("data") or {}
    if data.get("f57") != code or _number(data.get("f43")) is None:
        return None
    return {"last": _number(data["f43"]), "change_percent": _number(data.get("f170")),
            "source_time": (datetime.fromtimestamp(data["f124"], timezone.utc).isoformat()
                            if isinstance(data.get("f124"), (int, float)) and data["f124"] > 0 else None),
            "source": "东方财富场内行情快照", "note": "来源未返回行情时点时，延迟未知。"}


def fetch_detail(code: str, catalog_row: dict | None = None) -> dict:
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("请使用六位基金代码")
    raw = _get(f"{FUND_ROOT}/pingzhongdata/{code}.js")
    if _assignment(raw, "fS_code") != code:
        raise ValueError("基金详情来源未返回该代码")
    source_clock = re.search(r"/\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\*/", raw[:200])
    source_time = (datetime.fromisoformat(source_clock.group(1)).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat()
                   if source_clock else None)
    trend = _assignment(raw, "Data_netWorthTrend") or []
    history = [{"date": _stamp(point.get("x")), "nav": _number(point.get("y")),
                "daily_change_percent": _number(point.get("equityReturn"))}
               for point in trend if isinstance(point, dict)]
    history = [row for row in history if row["date"] and row["nav"] is not None]
    managers = _assignment(raw, "Data_currentFundManager") or []
    allocations = _assignment(raw, "Data_assetAllocation") or {}
    now = datetime.now(timezone.utc)
    quarter_month = ((now.month - 1) // 3) * 3 or 12
    quarter_year = now.year if quarter_month != 12 else now.year - 1
    holdings_kind = "bond" if (catalog_row or {}).get("category") == "债券" or "固收" in (catalog_row or {}).get("fund_type", "") else "stock"
    previous_month = quarter_month - 3 or 12
    previous_year = quarter_year if quarter_month > 3 else quarter_year - 1
    try:
        holdings, report = _holdings(code, quarter_year, quarter_month, holdings_kind)
        if not holdings:
            holdings, report = _holdings(code, previous_year, previous_month, holdings_kind)
            previous_month, previous_year = (previous_month - 3 or 12), (previous_year if previous_month > 3 else previous_year - 1)
        old_holdings, old_report = _holdings(code, previous_year, previous_month, holdings_kind) if holdings else ([], None)
    except (requests.RequestException, ValueError):
        holdings, report, old_holdings, old_report = [], None, [], None
    try:
        basic = _basic_info(code)
    except (requests.RequestException, ValueError):
        basic = {}
    try:
        trade_status = _trade_status(code)
    except (requests.RequestException, ValueError):
        trade_status = {}
    exchange_quote = None
    if (catalog_row or {}).get("venue") == "场内":
        try:
            exchange_quote = _exchange_quote(code)
        except (requests.RequestException, ValueError, OverflowError):
            pass
    old_weights = {x["code"]: x["weight_percent"] for x in old_holdings}
    changes = [{"code": x["code"], "name": x["name"], "weight_percent": x["weight_percent"],
                "previous_weight_percent": old_weights[x["code"]],
                "change_pp": round(x["weight_percent"] - old_weights[x["code"]], 2)}
               for x in holdings if x["code"] in old_weights and x["weight_percent"] is not None
               and old_weights[x["code"]] is not None]
    return {"code": code, "name": _assignment(raw, "fS_name") or (catalog_row or {}).get("name"),
            "fund_type": (catalog_row or {}).get("fund_type"), "category": (catalog_row or {}).get("category"),
            "venue": (catalog_row or {}).get("venue"), "basic": basic,
            "nav_history": history, "latest_nav": history[-1] if history else None,
            "analysis": analyze_nav(history),
            "returns_percent": {"1m": _number(_assignment(raw, "syl_1y")),
                                "3m": _number(_assignment(raw, "syl_3y")),
                                "6m": _number(_assignment(raw, "syl_6y")),
                                "1y": _number(_assignment(raw, "syl_1n"))},
            "managers": [{"name": x.get("name"), "tenure": x.get("workTime")}
                         for x in managers if isinstance(x, dict)],
            "asset_allocation": allocations if isinstance(allocations, dict) else {},
            "holdings": holdings, "holdings_kind": holdings_kind, "holdings_report": report, "previous_holdings_report": old_report,
            "holding_weight_changes": changes,
            "estimate": None, "estimate_note": "当前接入的接口未返回可核实的当日净值估算；不以已公布净值冒充估算。",
            "purchase_status": trade_status.get("purchase"), "redemption_status": trade_status.get("redemption"),
            "exchange_quote": exchange_quote,
            "source": "天天基金 / 东方财富公开网页", "source_url": f"{FUND_ROOT}/{code}.html",
            "source_time": source_time, "received_at": now.isoformat()}


def fetch_northbound() -> dict:
    payload = json.loads(_get(DATA_ROOT, params={"sortColumns": "TRADE_DATE", "sortTypes": "-1",
        "pageSize": "20", "pageNumber": "1", "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL", "source": "WEB", "client": "WEB", "filter": '(MUTUAL_TYPE="005")'}))
    raw = (payload.get("result") or {}).get("data") or []
    if not raw:
        raise ValueError("北向历史来源返回空数据")
    rows = [{"date": str(x.get("TRADE_DATE") or "")[:10],
             "net_buy": x.get("NET_DEAL_AMT"), "buy": x.get("BUY_AMT"),
             "sell": x.get("SELL_AMT"), "turnover": x.get("DEAL_AMT"),
             "deal_count": x.get("DEAL_NUM")}
            for x in raw if x.get("TRADE_DATE")]
    return {"rows": rows, "source": "东方财富沪深港通历史数据", "source_url":
            "https://data.eastmoney.com/hsgt/hsgtV2.html", "received_at": datetime.now(timezone.utc).isoformat(),
            "note": "北向资金收盘后披露。成交净买额等字段上游为空时保留空值；成交额不是净流入。金额保留来源单位，不作跨口径相加。"}


def fetch_sector_flows() -> dict:
    payload = json.loads(_get(SECTOR_URL, params={"pn": "1", "pz": "30", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f62", "fs": "m:90 t:2",
        "fields": "f12,f14,f2,f3,f62,f184,f124"}))
    rows = (payload.get("data") or {}).get("diff") or []
    if not rows:
        raise ValueError("行业资金来源返回空数据")
    return {"rows": [{"code": x.get("f12"), "name": x.get("f14"),
                       "change_percent": x.get("f3"), "net_flow_yuan": x.get("f62"),
                       "main_net_ratio_percent": x.get("f184"), "source_time": x.get("f124")}
                      for x in rows], "source": "东方财富行业板块资金流向排行",
            "flow_metric": "主力净流入",
            "source_url": "https://data.eastmoney.com/bkzj/hy.html",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "note": "主力净流入为成交分类估算，单位元；不代表公募基金申赎或北向资金。"}
