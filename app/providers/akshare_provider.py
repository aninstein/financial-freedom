from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MARKET_FUNCTIONS = {
    "CN": ("stock_zh_a_spot_em", "A股 / 创业板 / 科创板"),
    "HK": ("stock_hk_spot_em", "港股"),
    "US": ("stock_us_spot_em", "美股"),
    "FUND": ("fund_etf_spot_em", "ETF 行情 / 公募基金净值"),
    "GOLD": ("spot_quotations_sge", "上海黄金交易所"),
}

# Secondary endpoints stay inside AKShare and are attempted only when the
# primary market snapshot fails or is empty.
MARKET_FALLBACKS = {
    "CN": (("stock_zh_a_spot_tx", "AKShare · Tencent"), ("stock_zh_a_spot", "AKShare · Sina")),
    "HK": (("stock_hk_spot", "AKShare · Sina"),),
}
ACTIVE_ENDPOINTS: dict[str, str] = {}
LAST_ATTEMPTED_ENDPOINTS: dict[str, str] = {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except Exception:
        pass
    value = str(value).strip()
    return value if value and value.lower() not in {"nan", "none", "null", "-"} else None


def _number(value: Any) -> float | None:
    value = _text(value)
    if value is None:
        return None
    try:
        return float(value.replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def _pick(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row:
            value = row[name]
            if _text(value) is not None:
                return value
    return None


def _quote_from_row(market: str, row: dict[str, Any], received_at: str, source: str = "AKShare", endpoint: str = "") -> dict[str, Any] | None:
    symbol = _text(_pick(row, ("代码", "证券代码", "基金代码", "symbol", "code", "合约")))
    if market == "CN" and symbol and symbol[:2].lower() in {"sh", "sz", "bj"}:
        symbol = symbol[2:]
    if market == "US" and symbol and symbol.lower().startswith("gb_"):
        symbol = symbol[3:].upper()
    name = _text(_pick(row, ("名称", "证券简称", "基金简称", "中文名称", "cname", "name", "品种")))
    last = _number(_pick(row, ("最新价", "最新", "现价", "收盘", "价格", "最新报价", "最新价(元)", "trade", "zxj")))
    if market == "GOLD":
        symbol = symbol or name
        last = last or _number(_pick(row, ("中间价", "买价", "卖价", "Au99.99")))
    is_mutual_fund = market == "FUND" and "单位净值" in row
    if is_mutual_fund:
        last = _number(row.get("单位净值"))
        symbol = _text(row.get("基金代码")) or symbol
        name = _text(row.get("基金简称")) or name
    if not symbol or last is None:
        return None
    currency = {"CN": "CNY", "HK": "HKD", "US": "USD", "FUND": "CNY", "GOLD": "CNY"}[market]
    exch_time = _text(_pick(row, ("更新时间", "时间戳", "日期时间", "数据时间", "ticktime", "time", "时间", "日期")))
    is_sina_us = market == "US" and "stock_us_spot" in endpoint
    return {
        "instrument_id": f"{market}:{symbol}",
        "symbol": symbol,
        "name": name or symbol,
        "market": market,
        "asset_class": "gold_spot" if market == "GOLD" else ("mutual_fund" if is_mutual_fund else ("etf" if market == "FUND" else "equity")),
        "last": last,
        "currency": currency,
        "quote_kind": "trade" if market == "GOLD" else ("nav" if is_mutual_fund else "trade"),
        "price_unit": "CNY/g" if market == "GOLD" else ("CNY/unit" if is_mutual_fund else f"{currency}/share"),
        "exchange_time": exch_time,
        "received_at": received_at,
        "provider": f"{source} · 公募基金净值" if is_mutual_fund else (f"{source} · ETF" if market == "FUND" else source),
        "freshness": "end_of_day" if is_mutual_fund else ("delayed" if is_sina_us else "unknown"),
        "known_delay_seconds": 900 if is_sina_us else None,
        "change_percent": _number(_pick(row, ("涨跌幅", "涨跌幅(%)", "涨跌幅%", "change_percent", "changepercent", "zdf"))),
        "volume": _number(_pick(row, ("成交量", "成交量(手)", "volume"))),
    }


def fetch_market(market: str) -> list[dict[str, Any]]:
    """Fetch one documented AKShare snapshot and normalize its rows.

    Freshness is deliberately unknown unless the upstream response provides a
    trustworthy observation timestamp. Receive time is never treated as quote time.
    """
    import akshare as ak

    fn_name, _ = MARKET_FUNCTIONS[market]
    received_at = datetime.now(timezone.utc).isoformat()
    if market == "FUND":
        frames = []
        errors = []
        for fetch in (lambda: ak.fund_etf_spot_em(), lambda: ak.fund_open_fund_rank_em(symbol="全部")):
            try:
                current = fetch()
                if current is not None and not getattr(current, "empty", True):
                    frames.append(current)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        if not frames:
            raise RuntimeError("ETF quotes and mutual fund NAV are unavailable: " + " | ".join(errors))
        ACTIVE_ENDPOINTS[market] = "fund_etf_spot_em + fund_open_fund_rank_em"
        rows: list[dict[str, Any]] = []
        for current in frames:
            for record in current.to_dict(orient="records"):
                quote = _quote_from_row(market, record, received_at, "AKShare", "fund_etf_spot_em")
                if quote:
                    rows.append(quote)
        if not rows:
            raise RuntimeError("fund endpoints returned no normalizable rows")
        return rows
    else:
        endpoints = [(fn_name, "AKShare")] + list(MARKET_FALLBACKS.get(market, ()))
        failures = []
        for endpoint, source in endpoints:
            LAST_ATTEMPTED_ENDPOINTS[market] = endpoint
            try:
                fn = getattr(ak, endpoint)
                frame = fn(symbol="Au99.99") if market == "GOLD" else fn()
                if frame is None or getattr(frame, "empty", True):
                    raise RuntimeError("empty response")
                rows = []
                for record in frame.to_dict(orient="records"):
                    quote = _quote_from_row(market, record, received_at, source, endpoint)
                    if quote:
                        rows.append(quote)
                if not rows:
                    raise RuntimeError("no normalizable rows")
                ACTIVE_ENDPOINTS[market] = endpoint
                return rows
            except Exception as exc:
                failures.append(f"{endpoint}: {type(exc).__name__}: {str(exc)[:160]}")
        raise RuntimeError("all AKShare endpoints failed: " + " | ".join(failures))


def fetch_us_daily_closes(symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch explicitly labeled per-symbol end-of-day closes for the watchlist.

    This avoids the 917-page full-US-market Sina snapshot and never labels a
    daily close as a current/delayed quote.
    """
    import akshare as ak

    received_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for raw_symbol in symbols[:25]:
        symbol = raw_symbol.strip().upper()
        frame = ak.stock_us_daily(symbol=symbol, adjust="")
        if frame is None or getattr(frame, "empty", True):
            continue
        frame = frame.sort_values("date")
        last_row = frame.iloc[-1].to_dict()
        previous = frame.iloc[-2].to_dict() if len(frame) > 1 else {}
        try:
            last = float(last_row["close"])
            volume = float(last_row["volume"])
            date_value = last_row["date"]
        except (KeyError, TypeError, ValueError):
            continue
        if last <= 0:
            continue
        previous_close = previous.get("close")
        try:
            change = (last / float(previous_close) - 1) * 100 if previous_close else None
        except (TypeError, ValueError, ZeroDivisionError):
            change = None
        provider_symbol = symbol.upper()
        rows.append({
            "instrument_id": f"US:{provider_symbol}", "symbol": provider_symbol,
            "name": provider_symbol, "market": "US", "asset_class": "equity",
            "last": last, "currency": "USD", "quote_kind": "eod", "price_unit": "USD/share",
            "exchange_time": str(date_value), "received_at": received_at,
            "provider": "AKShare · Sina daily close", "freshness": "end_of_day",
            "known_delay_seconds": None, "change_percent": change, "volume": volume,
        })
    return rows


def fetch_us_watchlist_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch Sina's documented 15-minute-delayed US quote for watched symbols.

    AKShare's stock_us_spot() uses the same Sina market feed but downloads all
    917 pages. The per-symbol endpoint lets this app keep the request bounded
    to the user's watchlist. Sina's quote timestamp is Beijing local time.
    """
    import re
    from zoneinfo import ZoneInfo

    import requests

    normalized = []
    for raw in symbols[:25]:
        symbol = raw.strip().upper()
        if re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", symbol):
            normalized.append(symbol)
    normalized = list(dict.fromkeys(normalized))
    if not normalized:
        return []

    received_at = datetime.now(timezone.utc).isoformat()
    query = ",".join(f"gb_{symbol.lower()}" for symbol in normalized)
    response = requests.get(
        f"https://hq.sinajs.cn/list={query}",
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    values = {
        match.group(1).lower(): match.group(2).split(",")
        for match in re.finditer(r'var\s+hq_str_(gb_[a-z0-9._-]+)="([^"]*)";', response.text)
    }

    def number(value: str) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except (TypeError, ValueError):
            return None

    rows: list[dict[str, Any]] = []
    for symbol in normalized:
        fields = values.get(f"gb_{symbol.lower()}", [])
        if len(fields) < 11:
            continue
        last = number(fields[1])
        if not fields[0] or last is None or last <= 0:
            continue
        stamp = fields[3].strip()
        if stamp:
            try:
                observed = datetime.fromisoformat(stamp).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                stamp = observed.isoformat()
            except ValueError:
                pass
        rows.append({
            "instrument_id": f"US:{symbol}", "symbol": symbol,
            "name": fields[0].strip() or symbol, "market": "US", "asset_class": "equity",
            "last": last, "currency": "USD", "quote_kind": "trade", "price_unit": "USD/share",
            "exchange_time": stamp or None, "received_at": received_at,
            "provider": "Sina US delayed quote", "freshness": "delayed",
            "known_delay_seconds": 900, "change_percent": number(fields[2]),
            "volume": number(fields[10]),
        })
    return rows


def fetch_hk_watchlist_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch Sina single-symbol HK quotes when the bulk snapshot is unavailable."""
    import re
    from zoneinfo import ZoneInfo

    import requests

    normalized = []
    for raw in symbols[:25]:
        symbol = raw.strip()
        if symbol.isdigit() and len(symbol) <= 5:
            normalized.append(symbol.zfill(5))
    normalized = list(dict.fromkeys(normalized))
    if not normalized:
        return []

    received_at = datetime.now(timezone.utc).isoformat()
    query = ",".join(f"rt_hk{symbol}" for symbol in normalized)
    response = requests.get(
        f"https://hq.sinajs.cn/list={query}",
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    values = {
        match.group(1): match.group(2).split(",")
        for match in re.finditer(r'var\s+hq_str_rt_hk(\d{5})="([^"]*)";', response.text)
    }

    def number(value: str) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except (TypeError, ValueError):
            return None

    rows: list[dict[str, Any]] = []
    for symbol in normalized:
        fields = values.get(symbol, [])
        if len(fields) < 19:
            continue
        last = number(fields[6])
        if not fields[1] or last is None or last <= 0:
            continue
        stamp = None
        try:
            observed = datetime.strptime(f"{fields[17]} {fields[18]}", "%Y/%m/%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Hong_Kong"))
            stamp = observed.isoformat()
        except (IndexError, ValueError):
            pass
        rows.append({
            "instrument_id": f"HK:{symbol}", "symbol": symbol,
            "name": fields[1].strip() or symbol, "market": "HK", "asset_class": "equity",
            "last": last, "currency": "HKD", "quote_kind": "trade", "price_unit": "HKD/share",
            "exchange_time": stamp, "received_at": received_at,
            "provider": "Sina HK quote", "freshness": "unknown",
            "known_delay_seconds": None, "change_percent": number(fields[8]),
            "volume": number(fields[12]),
        })
    return rows


def fetch_cn_watchlist_quotes(symbols: list[str]) -> list[dict[str, Any]]:
    """Timestamped Sina single-stock fallback, using the same public source as AKShare Sina."""
    import httpx
    import re
    from zoneinfo import ZoneInfo
    symbols = [s for s in symbols if re.fullmatch(r'\d{6}', s) and s.startswith(('6','0','3'))][:25]
    if not symbols:
        return []
    mapping = {('sh' if s.startswith('6') else 'sz') + s: s for s in symbols}
    with httpx.Client(timeout=15, headers={'Referer':'https://finance.sina.com.cn/'}) as client:
        response = client.get('https://hq.sinajs.cn/list=' + ','.join(mapping))
        response.raise_for_status()
    received = datetime.now(timezone.utc).isoformat()
    text = response.content.decode('gb18030', errors='replace')
    rows = []
    for provider_symbol, content in re.findall(r'var hq_str_([a-z0-9]+)="([^"]*)"', text):
        fields = content.split(',')
        if provider_symbol not in mapping or len(fields) < 32:
            continue
        last = _number(fields[3]); previous = _number(fields[2])
        if last is None or last <= 0:
            continue
        try:
            observed = datetime.strptime(fields[30]+' '+fields[31], '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        except ValueError:
            continue
        symbol = mapping[provider_symbol]
        rows.append({'instrument_id':'CN:'+symbol,'symbol':symbol,'name':fields[0] or symbol,'market':'CN','asset_class':'equity','last':last,'currency':'CNY','quote_kind':'trade','price_unit':'CNY/share','exchange_time':observed.isoformat(),'received_at':received,'provider':'Sina CN quote · AKShare同源回退','freshness':'unknown','known_delay_seconds':None,'change_percent':(last/previous-1)*100 if previous else None,'volume':_number(fields[8])})
    return rows
