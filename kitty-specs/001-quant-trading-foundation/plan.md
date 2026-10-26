# Implementation plan

## Architecture

Local-first modular monolith; HTTP API and static dashboard share one process during Phase 1.

```text
Provider adapters (AKShare first; licensed adapters later)
        ↓ normalized envelopes
Market service ── exchange calendars ── quote cache / bar store
        ↓                              ↓
FastAPI read API                  SQLite (dataset-versioned daily bars)
        ↓                              ↓
Dashboard UI                 deterministic research/backtest

Manual/read-only account sources → account snapshot store
Paper order API → risk rules → paper ledger/matcher (isolated from broker adapters)
```

## Technology decisions

- Python 3.10+ / FastAPI / Pydantic for API and provider integration.
- SQLite for local configuration, watchlists, quote/bar cache, manual account snapshots, paper fills, and audit metadata; daily datasets carry a content hash. Add Parquet/DuckDB when local history size warrants a columnar store.
- AKShare as an optional, best-effort multi-source adapter. Provider calls run off the async event loop, with bounded concurrency and per-market errors.
- `exchange_calendars` or equivalent checked calendar package for XNYS, XSHG, and XHKG; gold calendar/session adapter is separate. Confirm supported schedule coverage before acceptance.
- Static vanilla HTML/JS dashboard remains the initial UI to avoid a frontend rewrite; dynamic data comes from versioned API endpoints.
- Internal paper matcher has no dependency on a broker SDK. Webull/IBKR APIs are deferred provider candidates, not active credentials or routing targets.

## Data-source decisions

| Asset/market | Phase 1 source | Coverage and constraints |
|---|---|---|
| US equities / ETFs | AKShare best-effort; Alpaca or Webull adapter candidate | Feed and entitlement determine real-time/delayed state; Alpaca requires API credentials; Webull API permissions/subscriptions are separate. |
| A shares / ChiNext | AKShare best-effort; Webull candidate | Public-site-derived endpoints may throttle/change; Webull A-share coverage uses Stock Connect constraints and data permissions. |
| Hong Kong equities / ETFs | AKShare best-effort; Webull candidate | HKEX market-data licensing/entitlements apply to commercial or redistributed data. |
| Funds | AKShare fund APIs, with NAV versus ETF quote separated | Mutual-fund NAV publication is not continuous market pricing. ETF quote follows exchange market and feed entitlement. |
| Gold | AKShare SGE spot/benchmark and/or supported futures endpoint | Venue, instrument, purity, currency, contract month, and unit are distinct. No generic “gold price” without instrument semantics. |
| Market status | Exchange-calendar package, not quote provider | Calendar package's holiday/session coverage is a versioned dependency; provider outage does not change exchange status. |

## Security and safety

- Bind loopback by default; no public deployment in Phase 1.
- No real-trading methods in `PaperBroker`; keep any future `BrokerAdapter` module unloaded unless a later feature explicitly enables it.
- Keep tokens in environment variables; logs redact keys and account identifiers.
- API validation and ledger transaction are server-side. UI confirmation is required but never the sole risk control.

## Rollout

1. Publish charter/spec/research/data model/contracts and WP dependencies.
2. Implement normalized schemas, persistence, provider health and market status.
3. Implement provider fetches and historical backfill for configured watchlist.
4. Implement account snapshots, deterministic paper ledger and order matcher.
5. Wire dashboard to API; remove unlabeled fake values from the operational path.
6. Run a manual next-session smoke run for each configured feed; record missing permissions, latency and known gaps. Runtime provider coverage is environment-dependent and currently partial.
7. Implement a deterministic SMA research baseline with explicit cost assumptions; AI recommendations remain deferred.

## Risks

- A single open-data library does not guarantee freshness, uptime, market coverage, or terms suitable for redistribution.
- Market calendars and instrument metadata may be incomplete; status and symbol resolution must expose uncertainty.
- Bulk A-share/US/HK snapshots can be slow and trigger provider throttling; do not block the dashboard while pulling.
- Gold is several distinct instrument families; first release should show only supported, unambiguous products.
- Existing prototype contains fabricated balances, prices, strategy metrics and AI recommendation copy; these must not appear as connected/live data after API integration.
