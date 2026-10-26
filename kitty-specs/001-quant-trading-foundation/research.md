# Research notes

**Checked:** 2026-10-25. Product docs and API availability can change; review before enabling an adapter.

## Spec Kitty workflow

This repository had no `specify`, `spec-kit`, or `speckitty` executable installed. These artifacts use Spec Kitty's feature directory shape and workflow: charter → specify → plan/research/data model/contracts → work packages → implementation/review/acceptance. The official project describes work packages in separate task files and their planned lane metadata. Reconcile with the CLI when installed.

- [Spec Kitty repository](https://github.com/spec-kitty/spec-kitty)
- [Spec-driven workflow guide](https://github.com/spec-kitty/spec-kitty/blob/main/docs/context/spec-driven.md)
- [Task generation guide](https://github.com/spec-kitty/spec-kitty/blob/main/docs/guides/how-to/missions/generate-tasks.md)

## Provider comparison

### AKShare — initial best-effort breadth adapter

Its official tutorial lists interfaces for A-share, HK, US, fund ETF and published open-fund NAV, gold exchange spot/benchmark and historical bars. It is a Python research-data toolkit whose interfaces commonly depend on public upstream sites. This makes it useful for personal research/bootstrap breadth, not a guaranteed professional feed. The adapter tries Eastmoney first; A shares then try Tencent and Sina, while HK tries Sina. In this runtime Tencent A shares returned 5,577 normalized rows and Sina HK returned 2,810 rows. A single-symbol Sina HK request for `HK:00700` returned a quote and exchange timestamp; the app uses it only for watched symbols when the full snapshot fails and derives staleness from that timestamp without asserting an undocumented delay. The US Eastmoney endpoint fails here; the documented Sina full-market snapshot paginates 917 pages and was measured at 73/917 pages after 30 seconds, so it is deliberately not enabled as a bulk-refresh fallback. For explicitly watched US symbols, the provider requests Sina's single-symbol endpoint directly (the same upstream feed used by AKShare's bulk Sina adapter, documented as 15-minute-delayed). If unavailable, it falls back to per-symbol daily history. The EOD rows are labeled `eod`/`end_of_day`, cannot overwrite an existing non-EOD quote, and cannot be used for simulated fills. Single-symbol delayed quote calls returned AAPL and MSFT in the current environment. Other snapshot endpoints remain freshness-unknown unless a trustworthy observation timestamp is supplied. Honor upstream terms and expose provider health.

- [AKShare tutorial/API index](https://github.com/akfamily/akshare/blob/main/docs/tutorial.md)
- [AKShare A-share Tencent endpoint](https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_zh_a_tx.py), [A-share Sina implementation](https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_zh_a_sina.py), [HK Sina implementation](https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_hk_sina.py), and [US Sina implementation](https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_us_sina.py). AKShare documents the Sina US snapshot as 15-minute delayed.
- [AKShare public fund API documentation](https://github.com/akfamily/akshare/blob/main/docs/data/fund/fund_public.md)
- [AKShare Shanghai Gold Exchange API documentation](https://github.com/akfamily/akshare/blob/main/docs/data/spot/spot.md)
- [Shanghai Gold Exchange product sessions](https://www.sge.com.cn/cpfw) and [exchange notice on daytime/nighttime trading hours](https://www.sge.com.cn/jjsnotice/5145453)
- [AKShare introduction and usage context](https://github.com/akfamily/akshare/blob/main/docs/introduction.md)
- [AKShare's own agent notes on upstream changes and freshness](https://github.com/akfamily/akshare/blob/main/llms.txt)

### Webull OpenAPI — candidate for authenticated market data and trading later

Official docs list HTTP historical/snapshot data and MQTT streaming for HK/US/A-shares. Data entitlements are separate from app subscriptions; A-share data may be delayed outside Mainland China and is unavailable in Mainland China in the documented setup. Its trading API covers account/order operations, with A-share trading disabled by default and requiring permission. This is a candidate only after the user supplies eligible credentials and permissions; Phase 1 does not route trades.

- [Market Data API overview](https://developer.webull.hk/apis/docs/market-data-api/overview/)
- [Trading API overview](https://developer.webull.hk/apis/docs/trade-api/overview/)
- [OpenAPI overview and supported markets](https://developer.webull.hk/apis/docs/about-open-api/)

### Alpaca — candidate for US market data/paper brokerage

Official stock data endpoints distinguish feeds including IEX and SIP/delayed SIP, so source entitlement must flow to freshness labels. It is US-focused for this proposal and does not solve cross-market coverage.

- [Latest stock bars and feed options](https://docs.alpaca.markets/us/v1.1/reference/stocklatestbars-1)

### IBKR — candidate for account and execution adapter later

IBKR Web API offers account/trading functions and market data subject to authentication and subscriptions. It is not a universal free data provider. Defer until the account, permissions, and market data subscriptions are known.

- [IBKR Web API documentation](https://www.interactivebrokers.com/docs/web-api/)

### Exchange data terms

HKEX states that real-time market data is governed by its market-data licensing/subscription program. Display inside one user's personal tool and external redistribution have different implications; obtain the appropriate entitlement before production or sharing.

- [HKEX Market Data FAQ](https://www.hkex.com.hk/Global/Exchange/FAQ/Market-Data?sc_lang=en)

## Open-source quant/AI platforms

- [Microsoft Qlib](https://github.com/microsoft/qlib): research pipeline, factors, models and backtest tooling; useful research integration, not a broker/account product.
- [vn.py / VeighNa](https://github.com/vnpy/vnpy): Python event-driven trading framework with exchange/broker gateways; adapter candidate, but each gateway and market requires verification.
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean): event-driven research/backtest/live engine; heavier, with separate data/broker integration requirements.
- [TradingAgents](https://github.com/TauricResearch/TradingAgents): likely project the user remembered as “Transaction AI”; multi-agent research discussion, not a verified execution/risk layer.
- [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent), [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT), [FinRL](https://github.com/AI4Finance-Foundation/FinRL): future experimental research references; not Phase 1 dependencies.

## Decision

Use one normalized `MarketDataProvider` interface and start with AKShare only where an endpoint is available. Label feed quality honestly. Implement paper execution locally. Add Webull/Alpaca/IBKR only after access and entitlement setup; never treat a data provider as a broker permission or as a licensed distribution grant.
