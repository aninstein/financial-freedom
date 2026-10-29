import asyncio
import sqlite3

from app import fund_research
from app.providers import eastmoney_funds


def test_catalog_filter_cache_and_stale_fallback(monkeypatch, tmp_path):
    path = tmp_path / "funds.sqlite"

    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    with db() as conn:
        conn.execute("CREATE TABLE workspace_cache (cache_key TEXT PRIMARY KEY,payload TEXT,updated_at TEXT,last_error TEXT)")
    sample = [
        {"code": "110022", "name": "易方达消费行业股票", "pinyin": "YFDXFHYGP", "category": "股票", "fund_type": "股票型", "venue": "场外或待核实"},
        {"code": "511010", "name": "国泰上证国债ETF", "pinyin": "GTGSZGETF", "category": "ETF", "tags": ["ETF", "债券"], "fund_type": "指数型-固收", "venue": "场内"},
        {"code": "000003", "name": "中海可转债债券", "pinyin": "ZHKZZZQ", "category": "债券", "fund_type": "债券型", "venue": "场外或待核实"},
    ]
    monkeypatch.setattr(eastmoney_funds, "fetch_catalog", lambda: sample)
    first = asyncio.run(fund_research.search(db, category="ETF"))
    assert first["total"] == 1 and first["rows"][0]["code"] == "511010"
    assert first["categories"]["债券"] == 2
    assert asyncio.run(fund_research.search(db, query="可转债"))["rows"][0]["code"] == "000003"
    monkeypatch.setattr(eastmoney_funds, "fetch_catalog", lambda: (_ for _ in ()).throw(ConnectionError()))
    assert asyncio.run(fund_research.search(db))["state"] == "available"
    assert asyncio.run(fund_research.search(db, refresh=True))["state"] == "stale"


def test_direct_source_parsers_keep_missing_values():
    assert eastmoney_funds._assignment('var fS_code="110022";var Data_netWorthTrend=[{"x":1,"y":2.5}];', "fS_code") == "110022"
    assert eastmoney_funds._assignment("var x=undefined;", "x") is None
    assert eastmoney_funds.classify("国债ETF", "指数型-固收") == "ETF"
    assert eastmoney_funds.classify("国债ETF联接A", "指数型-固收") == "指数"
    assert not eastmoney_funds._is_exchange_traded("国债ETF联接A")
    assert eastmoney_funds.classify("海外科技", "QDII-股票") == "QDII"
    assert eastmoney_funds._number(None) is None


def test_northbound_null_net_buy_is_not_replaced_by_turnover(monkeypatch):
    monkeypatch.setattr(eastmoney_funds, "_get", lambda *args, **kwargs:
                        '{"result":{"data":[{"TRADE_DATE":"2026-10-28 00:00:00","NET_DEAL_AMT":null,"DEAL_AMT":251393.34}]}}')
    row = eastmoney_funds.fetch_northbound()["rows"][0]
    assert row["net_buy"] is None
    assert row["turnover"] == 251393.34


def test_nav_analysis_uses_observed_values_and_discloses_method():
    history = [{"date": f"2026-01-{day:02d}", "nav": 1 + day / 100}
               for day in range(1, 21)]
    history[-1]["nav"] = 1.0
    result = eastmoney_funds.analyze_nav(history)
    assert result["observations"] == 20
    assert result["max_drawdown_percent"] < 0
    assert result["volatility_percent"] > 0
    assert "未计分红" in result["note"]


def test_sector_flow_falls_back_with_distinct_source_label(monkeypatch, tmp_path):
    path = tmp_path / "fallback.sqlite"

    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    with db() as conn:
        conn.execute("CREATE TABLE workspace_cache (cache_key TEXT PRIMARY KEY,payload TEXT,updated_at TEXT,last_error TEXT)")
    monkeypatch.setattr(eastmoney_funds, "fetch_northbound", lambda: {"rows": [{"date": "2026-10-28"}]})
    monkeypatch.setattr(eastmoney_funds, "fetch_sector_flows", lambda: (_ for _ in ()).throw(ConnectionError()))
    from app import research_data
    monkeypatch.setattr(research_data, "cached", lambda db, kind, key: {
        "state": "available", "received_at": "2026-10-29T00:00:00+00:00",
        "rows": [{"名称": "银行", "今日涨跌幅": 1.2, "资金净额-元": 12345}]})
    result = asyncio.run(fund_research.flows(db))
    assert result["sectors"]["rows"][0]["net_flow_yuan"] == 12345
    assert result["sectors"]["flow_metric"] == "行业资金净额"
    assert "同花顺" in result["sectors"]["source"]
