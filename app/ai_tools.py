from __future__ import annotations

import asyncio
import json
import math
import inspect
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from app.cycle_analysis import analyze as analyze_cycles
from app.mysql_db import connect as mysql_connect, Row
from app.market_context import news_context, liquidity_context, sector_rotation
from app.research_data import INDEX_CATALOG, INDEXES, collect as collect_research


ROOT = Path(__file__).resolve().parent.parent
PROVIDER_TIMEOUT = max(5, int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "30")))
MARKETS = {"CN": "A股 / 创业板 / 科创板", "HK": "港股", "US": "美股", "FUND": "基金 / ETF", "GOLD": "黄金 / SGE"}


def _db():
    return mysql_connect()


class ResearchTools:
    def __init__(self, market_status: Callable[[str], dict[str, Any]], market_error: Callable[[str], str | None],
                 quote_with_age: Callable[[Row], dict[str, Any]], backtest: Callable[[dict[str, Any]], dict[str, Any]],
                 account_reader: Callable[[str], dict[str, Any] | None], account_allowed: str | None):
        self.market_status = market_status
        self.market_error = market_error
        self.quote_with_age = quote_with_age
        self.backtest = backtest
        self.account_reader = account_reader
        self.account_allowed = account_allowed
        self.evidence: list[dict[str, Any]] = []
        self.sector_reader: Any = None
        self.dossier_reader: Any = None
        self.history_refresher: Any = None
        self._history_attempted: set[str] = set()

    def _evidence(self, kind: str, title: str, source: str, as_of: str | None, detail: dict[str, Any]) -> dict[str, Any]:
        detail = json.loads(json.dumps(detail, ensure_ascii=False, default=str))
        item = {"evidence_id": f"E{len(self.evidence) + 1:03d}", "type": kind, "title": title,
                "source": source, "as_of": as_of, "detail": detail}
        self.evidence.append(item)
        return item

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "get_watchlist":
            with _db() as conn:
                rows = conn.execute("""
                    SELECT w.instrument_id, q.name, q.last, q.currency, q.exchange_time,
                           q.received_at, q.provider, q.freshness
                    FROM watchlist w LEFT JOIN quotes q ON q.instrument_id=w.instrument_id
                    ORDER BY w.added_at DESC LIMIT 8
                """).fetchall()
            data = {"instruments": [dict(row) for row in rows], "limit": 8,
                    "note": "仅返回最近8只自选；报价须按来源时间与新鲜度核对。"}
            item = self._evidence("watchlist", "最近自选与缓存报价", "本地自选/行情库", None, data)
            return {"evidence": [item], **data}
        if name == 'get_market_news':
            data=await news_context(_db,str(args.get('query',''))[:80],min(30,max(1,int(args.get('limit',20)))))
            # Keep timestamps, first-seen and source attached to every headline excerpt.
            data['rows']=[{**r,'content':r['content'][:600]} for r in data['rows'][:10]]
            item=self._evidence('market_news','财经快讯及行业关联','分源状态见sources',None,data)
            return {'evidence':[item],**data}
        if name == 'get_macro_liquidity':
            data=await liquidity_context(_db)
            data['rows']=[{**r,'excerpt':r['excerpt'][:1200]} for r in data['rows'][:4]]
            item=self._evidence('macro_liquidity','央行逆回购与流动性公告',data.get('source','中国人民银行'),data.get('source_time'),data)
            return {'evidence':[item],**data}
        if name == 'get_sector_rotation':
            data=await sector_rotation(_db)
            data['total_sectors']=len(data['rows'])
            selected=str(args.get('name','')).strip()[:80]
            if selected: data['rows']=[r for r in data['rows'] if selected in r['name']]
            else:
                full=data['rows']; chosen=[]
                for phase in ('persistent_leader','improving','weakening','mixed'):
                    chosen += [r for r in full if r['phase']==phase][:4]
                data['rows']=chosen or full[:16]
            data['returned_sectors']=len(data['rows'])
            data['coverage_note']='摘要每阶段最多4个；未返回行业不可推断，可传name查询指定行业。'
            item=self._evidence('sector_rotation','行业轮动与相对强弱','东方财富 · AKShare + 本机采集快照',None,data)
            return {'evidence':[item],**data}
        if name == 'get_historical_cycles':
            data = analyze_cycles(_db,str(args['instrument_id']),args.get('years',5))
            item = self._evidence('historical_cycles',f"{data['instrument_id']} 历史周期统计",'本机日线确定性统计',data['last_bar'],data)
            return {'evidence':[item],**data}
        if name == 'get_index_analysis':
            index_id = str(args.get('index_id','')).upper()
            if not index_id:
                return {'indices':INDEX_CATALOG,'note':'选择目录中的指数ID查询；指数不能直接交易。'}
            if index_id not in INDEXES: raise ValueError('指数不在目录中，请先查询目录')
            data = await collect_research(_db,'index',index_id) if os.getenv('AKSHARE_ENABLED','true').lower()=='true' else {'state':'disabled','rows':[]}
            analysis = analyze_cycles(_db,index_id,args.get('years',5))
            detail = {**INDEXES[index_id],**{k:v for k,v in data.items() if k!='rows'},'analysis':analysis}
            item = self._evidence('index_analysis',f"{INDEXES[index_id]['name']} 指数分析",data.get('source','本机缓存'),analysis['last_bar'],detail)
            return {'evidence':[item],**detail}
        if name == 'get_market_flow_history':
            if os.getenv('AKSHARE_ENABLED','true').lower()!='true': return {'data_gap':'公共数据采集已关闭'}
            data = await collect_research(_db,'market_flow','CN')
            detail = {**data,'rows':data.get('rows',[])[:30]}
            item = self._evidence('market_flow','沪深大盘资金历史',data['source'],None,detail)
            return {'evidence':[item],**detail}
        if name == 'collect_fund_disclosures':
            codes = list(dict.fromkeys(args.get('codes') or []))
            year = int(args.get('year',datetime.now().year))
            if not 1<=len(codes)<=5 or any(not re.fullmatch(r'\d{6}',str(c)) for c in codes) or not 2000<=year<=datetime.now().year:
                raise ValueError('每次1至5只六位基金代码；年份须为历史或当年')
            if os.getenv('AKSHARE_ENABLED','true').lower()!='true': return {'data_gap':'公共数据采集已关闭'}
            data = await asyncio.gather(*(collect_research(_db,'fund',f'{code}:{year}') for code in codes))
            used=[]
            for code,result in zip(codes,data):
                detail={**result,'fund_code':code,'year':year,'rows':result.get('rows',[])[:30]}
                used.append(self._evidence('fund_holdings',f'基金{code}披露持仓',result['source'],None,detail))
            return {'evidence':used,'note':'逐基金报告成功/缺口，报告期以每行季度为准；未覆盖基金不能外推为全市场。'}
        if name == "get_stock_dossier":
            if self.dossier_reader is None:
                raise ValueError("资料聚合工具未配置")
            data = await self.dossier_reader(str(args.get("instrument_id", "")), args.get("sections") or ["profile", "snapshot"])
            item = self._evidence("stock_dossier", f"{data['instrument_id']} 个股资料", "分项来源见 detail.sections", None, data)
            return {"evidence": [item], **data}
        if name == "search_instruments":
            query = str(args.get("query", "")).strip()[:80]
            if not query:
                raise ValueError("请输入股票名称或代码")
            with _db() as conn:
                rows = conn.execute("SELECT instrument_id,name,symbol,market,last,currency,freshness FROM quotes WHERE name LIKE ? OR symbol LIKE ? OR instrument_id LIKE ? ORDER BY market,symbol LIMIT 10", [f"%{query}%"] * 3).fetchall()
            return {"matches": [dict(row) for row in rows], "note": "仅包含已接入数据的证券；请选择匹配名称再查询明细。"}

        if name == "get_sector_overview":
            sector = str(args.get("name", "")).strip()[:80]
            if not sector or self.sector_reader is None:
                raise ValueError("板块数据源未配置或名称为空")
            data = await self.sector_reader(sector)
            detail = {k: v for k, v in data.items() if k not in {"sectors", "constituents"}}
            constituents = data.get("constituents", [])
            changes = [r.get("涨跌幅") for r in constituents if isinstance(r.get("涨跌幅"), (int, float))]
            detail.update({"constituent_count": len(constituents), "advancers": sum(v > 0 for v in changes),
                           "decliners": sum(v < 0 for v in changes), "constituents": constituents[:20]})
            item = self._evidence("sector_snapshot", f"{sector} 行业板块", data["source"], data.get("received_at"), detail)
            return {"evidence": [item], **detail}
        if name == "get_market_overview":
            market = str(args.get("market", "")).upper()
            if market not in MARKETS:
                raise ValueError("unknown market")
            with _db() as conn:
                rows = conn.execute("SELECT provider,received_at,exchange_time,freshness,change_percent FROM quotes WHERE market=?", (market,)).fetchall()
            observed = [row for row in rows if row["change_percent"] is not None]
            up = sum(row["change_percent"] > 0 for row in observed)
            down = sum(row["change_percent"] < 0 for row in observed)
            latest = max((row["received_at"] for row in rows), default=None)
            detail = {"market": market, "market_name": MARKETS[market], "quote_count": len(rows), "with_change": len(observed),
                      "advancers": up, "decliners": down, "unchanged": len(observed) - up - down,
                      "mean_change_percent": round(sum(r["change_percent"] for r in observed) / len(observed), 4) if observed else None,
                      "freshness_counts": {state: sum(row["freshness"] == state for row in rows) for state in ("realtime", "delayed", "end_of_day", "stale", "unknown")},
                      "market_session": self.market_status(market)["phase"], "next_open": self.market_status(market).get("next_open"),
                      "provider_error": self.market_error(market),
                      "coverage_note": "仅汇总当前本机缓存；不得将未覆盖证券当作无涨跌。"}
            item = self._evidence("market_snapshot", f"{MARKETS[market]} 行情广度", "MySQL quote cache", latest, detail)
            return {"evidence": [item], **detail}

        if name == "get_instrument_research":
            raw = str(args.get("instrument_id", ""))
            if ":" not in raw:
                raise ValueError("instrument_id must use MARKET:SYMBOL format")
            market, symbol = raw.split(":", 1)
            market = market.upper()
            symbol = symbol if market == "GOLD" else symbol.upper()
            if market == "HK" and symbol.isdigit():
                symbol = symbol.zfill(5)
            if market not in MARKETS or not symbol or len(symbol) > 24:
                raise ValueError("invalid instrument_id")
            instrument_id = f"{market}:{symbol}"
            days = min(500, max(20, int(args.get("days", 120))))
            refresh_error = None
            if self.history_refresher and instrument_id not in self._history_attempted:
                with _db() as conn:
                    has_bars = conn.execute("SELECT 1 FROM bars WHERE instrument_id=? AND interval='1d' AND adjustment='none' LIMIT 1", (instrument_id,)).fetchone()
                if not has_bars:
                    self._history_attempted.add(instrument_id)
                    try:
                        await self.history_refresher(instrument_id)
                    except Exception as exc:
                        refresh_error = type(exc).__name__
            with _db() as conn:
                quote = conn.execute("SELECT * FROM quotes WHERE instrument_id=?", (instrument_id,)).fetchone()
                bars = conn.execute("SELECT bar_time,open,high,low,close,volume,provider,received_at,adjustment,price_unit FROM bars WHERE instrument_id=? AND interval='1d' AND adjustment='none' ORDER BY bar_time DESC LIMIT ?", (instrument_id, days)).fetchall()
                manifest = conn.execute("SELECT dataset_version,content_hash,row_count,start_date,end_date,provider FROM dataset_manifests WHERE instrument_id=? ORDER BY ingested_at DESC LIMIT 1", (instrument_id,)).fetchone()
            records = list(reversed([dict(row) for row in bars]))
            result: dict[str, Any] = {"instrument_id": instrument_id, "market_session": self.market_status(market)["phase"],
                                      "bar_count": len(records), "bars_source": records[-1]["provider"] if records else None,
                                      "dataset_manifest": dict(manifest) if manifest else None}
            used = []
            if quote:
                q = self.quote_with_age(quote)
                detail = {key: q.get(key) for key in ("instrument_id", "name", "last", "currency", "price_unit", "quote_kind", "provider", "freshness", "known_delay_seconds", "change_percent", "volume", "exchange_time", "received_at")}
                item = self._evidence("quote", f"{instrument_id} 最新缓存行情", q["provider"], q["exchange_time"] or q["received_at"], detail)
                used.append(item)
                result["quote"] = detail
                result["quote_evidence_id"] = item["evidence_id"]
            if records:
                closes = [float(row["close"]) for row in records if row.get("close") is not None]
                returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
                def sma(window: int) -> float | None:
                    values = closes[-window:]
                    return sum(values) / window if len(values) == window else None
                volatility = None
                if len(returns) >= 20:
                    sample = returns[-20:]
                    mean = sum(sample) / 20
                    volatility = math.sqrt(sum((x - mean) ** 2 for x in sample) / 19) * math.sqrt(252)
                peak = 0.0
                drawdown = 0.0
                for close in closes:
                    peak = max(peak, close)
                    if peak:
                        drawdown = min(drawdown, close / peak - 1)
                recent_20 = records[-20:] if len(records) >= 20 else []
                recent_lows = [float(row["low"]) for row in recent_20 if row.get("low") is not None]
                recent_closes = [float(row["close"]) for row in recent_20 if row.get("close") is not None]
                metrics = {"instrument_id": instrument_id, "first_bar": records[0]["bar_time"], "last_bar": records[-1]["bar_time"],
                           "observations": len(closes), "return_over_window": closes[-1] / closes[0] - 1 if len(closes) > 1 else None,
                           "sma_20": sma(20), "sma_50": sma(50), "annualized_volatility_20d": volatility,
                           "last_close": closes[-1],
                           "low_20d": min(recent_lows) if recent_lows else None,
                           "close_low_20d": min(recent_closes) if recent_closes else None,
                           "close_high_20d": max(recent_closes) if recent_closes else None,
                           "max_drawdown_in_window": drawdown, "adjustment": records[-1]["adjustment"],
                           "price_unit": records[-1]["price_unit"],
                           "dataset_version": result["dataset_manifest"]["dataset_version"] if result["dataset_manifest"] else "unversioned-cache"}
                item = self._evidence("daily_research", f"{instrument_id} 历史日线指标", result["bars_source"] or "local bars", records[-1]["bar_time"], metrics)
                used.append(item)
                result["daily_metrics"] = metrics
                result["daily_evidence_id"] = item["evidence_id"]
            else:
                result["daily_metrics"] = None
                result["data_gap"] = "本地没有该标的日线；自动补数未成功，请在行情页拉取历史数据。"
            if refresh_error:
                result["history_refresh_error"] = refresh_error
            return {"evidence": used, **result}

        if name == "screen_funds":
            query = str(args.get("query", "")).strip()[:80]
            asset_class = str(args.get("asset_class", "all"))
            if asset_class not in {"all", "etf", "mutual_fund"}:
                raise ValueError("unsupported asset_class")
            limit = min(30, max(1, int(args.get("limit", 10))))
            sql = "SELECT instrument_id,symbol,name,asset_class,last,currency,quote_kind,price_unit,exchange_time,received_at,provider,freshness,change_percent,volume FROM quotes WHERE market='FUND'"
            params: list[Any] = []
            if asset_class != "all":
                sql += " AND asset_class=?"
                params.append(asset_class)
            if query:
                sql += " AND (symbol LIKE ? OR name LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
            sql += " ORDER BY change_percent DESC LIMIT ?"
            params.append(limit)
            with _db() as conn:
                rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
                total = conn.execute("SELECT COUNT(*) FROM quotes WHERE market='FUND'").fetchone()[0]
            detail = {"cached_fund_rows": total, "returned": len(rows), "filters": {"query": query, "asset_class": asset_class},
                      "rows": rows, "valuation_note": "mutual_fund 是最近公布 NAV；ETF 是交易所行情。该排序只对存在涨跌幅的缓存行有意义，不是投资评级。"}
            item = self._evidence("fund_screen", "本地基金/ETF行情筛选", "MySQL quote cache", max((r["received_at"] for r in rows), default=None), detail)
            return {"evidence": [item], **detail}

        if name == "get_fund_holdings":
            code = str(args.get("fund_code", ""))
            year = int(args.get("year", datetime.now().year))
            if not re.fullmatch(r"\d{6}", code) or not 2000 <= year <= datetime.now().year:
                raise ValueError("fund_code/year invalid")
            def fetch() -> list[dict[str, Any]]:
                import akshare as ak
                frame = ak.fund_portfolio_hold_em(symbol=code, date=str(year))
                return [] if frame is None or getattr(frame, "empty", True) else frame.head(20).to_dict(orient="records")
            rows = await asyncio.wait_for(asyncio.to_thread(fetch), timeout=PROVIDER_TIMEOUT)
            if not rows:
                return {"evidence": [], "fund_code": code, "report_year": year, "holdings": [], "data_gap": "来源未返回可用持仓；基金持仓是定期披露，不代表实时组合。"}
            detail = {"fund_code": code, "report_year": year, "rows": rows, "note": "显示源数据返回的披露记录，报告期以每行季度字段为准；不代表实时组合。"}
            item = self._evidence("fund_holdings", f"基金 {code} {year} 年持仓披露", "AKShare · fund_portfolio_hold_em", None, detail)
            return {"evidence": [item], **detail}

        if name == "get_fund_trade_changes":
            code = str(args.get("fund_code", ""))
            year = int(args.get("year", datetime.now().year))
            direction = str(args.get("direction", "both"))
            if not re.fullmatch(r"\d{6}", code) or not 2000 <= year <= datetime.now().year or direction not in {"buy", "sell", "both"}:
                raise ValueError("fund_code/year/direction invalid")
            indicators = ["累计买入", "累计卖出"] if direction == "both" else (["累计买入"] if direction == "buy" else ["累计卖出"])
            def fetch_changes() -> dict[str, list[dict[str, Any]]]:
                import akshare as ak
                result = {}
                for indicator in indicators:
                    frame = ak.fund_portfolio_change_em(symbol=code, indicator=indicator, date=str(year))
                    result[indicator] = [] if frame is None or getattr(frame, "empty", True) else frame.head(20).to_dict(orient="records")
                return result
            changes = await asyncio.wait_for(asyncio.to_thread(fetch_changes), timeout=PROVIDER_TIMEOUT)
            if not any(changes.values()):
                return {"evidence": [], "fund_code": code, "report_year": year, "changes": changes,
                        "data_gap": "来源没有返回该基金/年度的重大买入卖出披露；这不是完整或实时成交流水。"}
            detail = {"fund_code": code, "report_year": year, "changes": changes,
                      "note": "AKShare · 天天基金投资组合重大变动。只代表来源披露的年度重大买入/卖出事项，不代表实时持仓或完整交易流水。报告期以字段原值为准。"}
            item = self._evidence("fund_trade_disclosure", f"基金 {code} {year} 年重大买入/卖出披露", "AKShare · fund_portfolio_change_em", None, detail)
            return {"evidence": [item], **detail}

        if name == "get_stock_financials":
            symbol = str(args.get("symbol", ""))
            if not re.fullmatch(r"\d{6}", symbol):
                raise ValueError("仅支持六位 A 股代码")
            def fetch() -> dict[str, Any]:
                import akshare as ak
                frame = ak.stock_financial_abstract(symbol=symbol)
                if frame is None or getattr(frame, "empty", True):
                    return {"columns": [], "rows": []}
                return {"columns": [str(c) for c in frame.columns[:18]],
                        "rows": frame.iloc[:8, :18].where(frame.iloc[:8, :18].notna(), None).to_dict(orient="records")}
            data = await asyncio.wait_for(asyncio.to_thread(fetch), timeout=PROVIDER_TIMEOUT)
            if not data["rows"]:
                return {"evidence": [], "symbol": symbol, "data_gap": "AKShare 未返回财务摘要。"}
            detail = {"symbol": symbol, **data, "note": "按来源原字段展示；报告期、披露日、单位以原始列为准，不推断缺失字段。"}
            item = self._evidence("financial_data", f"A 股 {symbol} 财务摘要", "AKShare · stock_financial_abstract", None, detail)
            return {"evidence": [item], **detail}

        if name == "search_uploaded_documents":
            query = str(args.get("query", "")).strip()[:200]
            if len(query) < 2:
                raise ValueError("query needs at least two characters")
            instrument = str(args.get("instrument_id", "")).upper()
            limit = min(10, max(1, int(args.get("limit", 5))))
            terms = [term for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)[:6] if len(term) >= 2]
            doc_id=str(args.get('document_id',''))
            where = " AND (d.instrument_id=? OR d.instrument_id IS NULL)" if instrument else ""
            params = [instrument] if instrument else []
            if doc_id:
                where += ' AND d.document_id=?'; params.append(doc_id)
            with _db() as conn:
                rows = conn.execute("SELECT p.document_id,p.page_no,p.content,d.filename,d.document_type,d.instrument_id,d.report_period,d.content_hash,d.imported_at FROM ai_document_pages p JOIN ai_documents d USING(document_id) WHERE 1=1" + where + " ORDER BY d.imported_at DESC,p.page_no LIMIT 5000", params).fetchall()
            terms += [word for word in ("营收","营业收入","净利润","现金流","负债","风险","估值","假设","结论","利润","收入") if word in query]
            matches = []
            for row in rows:
                hits = sum(1 for term in terms if term.lower() in row["content"].lower())
                if hits:
                    matches.append((hits, row))
            matches.sort(key=lambda entry: (-entry[0], entry[1]["imported_at"]))
            found, used = [], []
            for hits, row in matches[:limit]:
                content = row["content"]
                term = next((t for t in terms if t.lower() in content.lower()), "")
                start = max(0, content.lower().find(term.lower()) - 500) if term else 0
                detail = {"document_id": row["document_id"], "filename": row["filename"], "document_type": row["document_type"],
                          "instrument_id": row["instrument_id"], "report_period": row["report_period"], "page": row["page_no"],
                          "content_hash": row["content_hash"], "imported_at": row["imported_at"], "match_score": hits,
                          "excerpt": content[start:start + 1500]}
                item = self._evidence("document_excerpt", f"{row['filename']} 第 {row['page_no']} 页", f"User upload · {row['document_id']}", row["report_period"] or row["imported_at"], detail)
                used.append(item)
                found.append({**detail, "evidence_id": item["evidence_id"]})
            return {"evidence": used, "query": query, "matches": found,
                    "data_gap": None if found else "导入文档没有匹配片段；请上传研报/财报或调整关键词。"}

        if name == "get_flow_data_coverage":
            from app.research_data import cached
            data=cached(_db,'market_flow','CN') or {}
            detail = {'available_local_flow_series':['沪深成交分类大盘资金'] if data.get('rows') else [],
                      'market_flow_state':data.get('state','waiting'),'market_flow_received_at':data.get('received_at'),
                      'stock_sector_flow':'AKShare按成交分类估计，个股/行业工具按需查询',
                      'fund_disclosures':'指定基金定期持仓和年度重大买卖披露，不是完整实时流水',
                      'northbound_realtime_buy_sell_turnover':'not_published_by_HKEX_since_2024-08-19',
                      'northbound_connected':False,
                      'note':'北向/南向官方实时买卖额未接入；历史接口的缺失字段不能当零，也不能用主力资金代替北向。',
                      'source_url':'https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en'}
            item = self._evidence('data_coverage','资金数据覆盖','HKEX + 本机采集状态',None,detail)
            return {'evidence':[item],**detail}

        if name == 'read_uploaded_document':
            doc_id=str(args.get('document_id',''))
            page=max(1,int(args.get('page',1)))
            offset=max(0,min(99999,int(args.get('offset',0))))
            with _db() as c:
                doc=c.execute('SELECT document_id,filename,document_type,instrument_id,report_period,content_hash,page_count,imported_at FROM ai_documents WHERE document_id=?',(doc_id,)).fetchone()
                row=c.execute('SELECT page_no,content FROM ai_document_pages WHERE document_id=? AND page_no>=? ORDER BY page_no LIMIT 1',(doc_id,page)).fetchone()
            if not doc: return {'data_gap':'文档不存在或已删除'}
            if not row: return {'document':dict(doc),'data_gap':'没有可提取文本的后续页面'}
            text=row['content']; excerpt=text[offset:offset+6000]
            detail={**dict(doc),'page':row['page_no'],'offset':offset,'excerpt':excerpt,
                    'next_offset':offset+len(excerpt) if offset+len(excerpt)<len(text) else None,
                    'next_page':row['page_no']+1 if row['page_no']<doc['page_count'] else None,
                    'note':'本次仅阅读一个页面片段；不能声称阅读了未取回的其他页面。'}
            item=self._evidence('document_excerpt',f"{doc['filename']} 第{row['page_no']}页",f'User upload · {doc_id}',doc['report_period'],detail)
            return {'evidence':[item],**detail}

        if name == "get_account_snapshot":
            account_id = str(args.get("account_id", ""))
            if not self.account_allowed or account_id != self.account_allowed:
                raise ValueError("账户读取未由用户在本次请求中明确授权")
            data = self.account_reader(account_id)
            if inspect.isawaitable(data): data = await data
            if not data:
                raise ValueError("账户不存在")
            detail = {"account_id": data["account_id"], "label": data["label"], "mode": data["mode"], "currency": data["currency"],
                      "cash": data.get("cash"), "as_of": data.get("as_of"),
                      "principal": data.get("principal"), "total_assets": data.get("total_assets"),
                      "total_pnl": data.get("total_pnl"), "total_return_pct": data.get("total_return_pct"),
                      "valuation_complete": data.get("valuation_complete"),
                      "positions": [{"instrument_id": p["instrument_id"], "quantity": p["quantity"],
                                     "asset_class": p.get("asset_class"), "cost_basis": p.get("cost_basis"),
                                     "current_value": p.get("current_value"), "unrealized_pnl": p.get("unrealized_pnl"),
                                     "unrealized_return_pct": p.get("unrealized_return_pct"),
                                     "reported_return_pct": p.get("reported_return_pct"),
                                     "change_percent": p.get("change_percent"), "quote_time": p.get("quote_time"),
                                     "valuation_source": p.get("valuation_source")}
                                    for p in data.get("positions", [])]}
            item = self._evidence("account_snapshot", "用户本次明确选择的账户摘要", data.get("source") or "local account snapshot", detail["as_of"], detail)
            return {"evidence": [item], **detail}

        if name == "run_sma_backtest":
            try:
                result = self.backtest(args)
            except Exception as exc:
                return {"evidence": [], "error": str(exc)[:300]}
            detail = {key: result[key] for key in ("run_id", "strategy_id", "strategy_version", "instrument_id", "dataset_version", "parameters", "metrics", "start", "end")}
            item = self._evidence("backtest", f"{result['instrument_id']} SMA 历史回测", "deterministic local backtest", result["end"], detail)
            return {"evidence": [item], **detail}

        raise ValueError("tool not registered")
