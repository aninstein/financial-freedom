# Feature 001: Quant trading foundation

**Status:** Core local workflows implemented; cross-market data acceptance partial  
**Date:** 2026-10-25  
**Target:** Local, single-user Phase 1  
**Related:** [project charter](../../.kittify/charter/charter.md)

## Why

The current repository contains a visual concept prototype, but no live data service, instrument model, account store, research pipeline, or trading engine. The user needs a reliable view of market state beginning with the next market session, then a safe foundation for quantitative workflows and later AI research.

## Product decisions

- **Markets:** US equities/ETFs, mainland A-shares including ChiNext, Hong Kong equities/ETFs, mutual funds/ETFs, and gold. Each provider's actual coverage is explicit; unsupported instruments remain unavailable.
- **Data mode:** Real or delayed provider data, labeled per feed and instrument. The app may not claim a universal “live” state.
- **Trading mode:** Internal paper account and simulator only. Phase 1 order matching is limited to supported equities/ETFs with an explicit currency and quote; open-end fund NAV and gold products are read-only until their subscription/redemption or contract rules are implemented. No live broker order endpoints or live credentials in Phase 1.
- **Accounts:** Show imported/manual or authorized read-only snapshots. Do not invent balances or imply a connected brokerage account.
- **Coverage:** Maintain a provider-backed instrument directory where practical; ingest daily history for configured watchlists. Intraday updates are limited to configured symbols/feeds to avoid unbounded pulls and provider throttling.
- **AI:** Explicitly deferred. Phase 1 recommendations are not generated; strategy signals and metrics are deterministic and explainable.
- **First data adapter:** AKShare is the initial best-effort research adapter for broad cross-market coverage. Add stable licensed APIs (such as Webull OpenAPI or IBKR) through the same interfaces after account, subscription, and market-data permissions are supplied. AKShare availability and delay vary by upstream source.
- **Deadline expectation:** Prepare the app for a local smoke run on 2026-10-26. Display actual sessions and provider responses available at runtime; do not promise quotes for closed markets, unsupported products, or unconfigured/failed feeds.

## User stories

### P1 — See real market state

As an investor, I can see whether each supported exchange/session is pre-market, open, closed, or in a break, with local exchange time and next session, so I can distinguish “closed” from “feed down.”

**Acceptance:** Status is computed from an exchange calendar and timezone, not from whether a quote arrived. Holiday, daylight-saving, overnight, and lunch-break sessions are represented. If calendar data is unavailable, status says unknown and identifies why.

### P1 — Inspect real/delayed quotes with provenance

As an investor, I can see quotes and daily/intraday bars for supported assets, including source, quote timestamp, retrieval timestamp, freshness and any known delay.

**Acceptance:** The interface distinguishes `realtime`, `delayed`, `end_of_day`, `stale`, `unavailable`, and `unknown`. A stale value remains visibly stale; provider errors do not fall back to fixture data. Cross-currency values retain native currency and never appear summed as a base currency without an FX source and timestamp.

### P1 — Configure a usable universe

As an investor, I can search a provider-backed symbol directory, add symbols to a watchlist, and request daily history for that watchlist.

**Acceptance:** Canonical instrument IDs include market, venue and symbol; aliases are supported; units, currency, timezone, price precision, minimum lot and asset/valuation type are recorded when supplied. A full all-symbol intraday download is not required.

### P1 — See account balances safely

As an investor, I can view manual/imported or authorized read-only account balances and positions, with account mode, currency, source, and as-of time.

**Acceptance:** Account rows cannot be confused with paper accounts. Missing/stale balances are shown as unavailable/stale. No broker credentials are stored in browser storage.

### P1 — Place a paper order

As an investor, I can preview a buy/sell order in a selected paper account, see market/limit terms, estimated cash/fees and deterministic risk checks, then explicitly confirm a simulated order.

**Acceptance:** Paper orders only. The server rejects invalid quantity, unsupported asset/order type, unsupported market lot rules, insufficient paper cash/position, and duplicate idempotency keys. Orders transition through accepted, filled, cancelled, or rejected states. Fills use an explicitly defined quote/bar simulation rule and retain the input data timestamp. No live endpoint is called. Partial fills are deferred.

### P2 — Reproduce a simple quantitative experiment

As an investor, I can select a strategy version and historical dataset, calculate deterministic indicators and compare a backtest with a named benchmark and fee/slippage assumptions.

**Acceptance:** Dataset and strategy versions, time range, adjustment policy, trading calendar, transaction costs, and output metrics are retained. No future data enters a decision timestamp. Results are labeled as historical research, never future performance.

## Functional requirements

- **FR-001:** Provider adapters implement normalized instrument search, quote snapshots, bars, and provider health/status without leaking provider-specific columns into UI/API consumers.
- **FR-002:** Every datum records canonical instrument, provider, provider instrument key, exchange timestamp, receive timestamp, currency/unit, interval/adjustment where relevant, and freshness.
- **FR-003:** Provider schedules use bounded concurrency, explicit timeout/retry/backoff, per-provider rate limits, and a visible last-success/last-error state.
- **FR-004:** Historical bars are idempotently persisted, partitioned by market/instrument/frequency/date, and queryable without overwriting a good row with an older observation.
- **FR-005:** Market session state uses exchange calendars and IANA timezones; SGE uses its published session hours plus the XSHG holiday calendar, with exchange-notice exceptions disclosed.
- **FR-006:** User watchlists define intraday polling scope. Poll interval and stale thresholds are provider-configured and surfaced.
- **FR-006a:** If the full-market US spot endpoint is unavailable, the app fetches documented 15-minute-delayed Sina quotes for explicitly watched US symbols. It retains the source timestamp and delay label. If a symbol quote is unavailable, the app may fetch its daily close, labeled `end_of_day`; EOD data may not overwrite a non-EOD quote and cannot be used to create or fill simulated orders.
- **FR-006c:** If a full-market HK snapshot fails, the app fetches Sina quotes for explicitly watched numeric HK symbols, preserves the source timestamp and derives stale status from its age without claiming an undocumented delay.
- **FR-006b:** Adding a watchlist instrument starts a bounded historical daily-bar backfill. The service checks the watchlist on a schedule and fills newly completed daily bars with overlap so provider corrections can replace recent cached rows; it records the latest stored bar and any ingestion error.
- **FR-007:** Account snapshots support manual/CSV and read-only adapters; base-currency totals require an explicit FX conversion source and valuation time.
- **FR-008:** Paper ledger records cash, positions, orders, fills, fees, and deterministic risk outcomes transactionally.
- **FR-009:** Dashboard UI consumes the backend API for status, quotes, data-source state, account snapshots, and paper orders. Any remaining mock content is removed or visibly labeled as fixture.
- **FR-010:** Health, provider, calendar, and ingestion diagnostics are available locally without exposing secrets.
- **FR-011:** Provider/source terms, supported markets, known delay, and licensing/redistribution limits are documented per adapter.

## Non-functional requirements

- Default bind is `127.0.0.1`; no public exposure or multi-user authentication is implied.
- Secrets are environment-configured and redacted from logs.
- UI remains usable when individual providers fail; errors are isolated by market.
- Timestamps are stored in UTC and rendered in exchange-local time with timezone labels.
- Paper-order transitions are auditable and idempotent.
- Raw provider payloads may be retained only where provider terms permit; normalized records include source provenance.

## Out of scope

- AI/LLM recommendations, document RAG, automatic strategy discovery.
- Live order placement, cancellation, transfer, or account mutation at any broker.
- Claims of licensed real-time feeds, redistribution, trading advice, or guaranteed uptime.
- Exhaustive intraday history for every symbol across every market.
- Tax, suitability, legal, or compliance workflows.

## Failure and edge cases

- Exchange is closed/holiday but provider returns a cached quote: show session closed and quote timestamp/freshness separately.
- Feed returns an empty frame or changes field schema: mark provider error; do not coerce malformed values into zero.
- Fund NAV is published once daily or estimated intraday: show `nav` versus `estimated_nav` and publication time distinctly.
- Gold instruments differ by venue, purity, currency, and unit: never merge spot, benchmark, and futures as one ticker.
- A/HK lot rules, short-sale rules, price limits, and trading halts differ: Phase 1 simulator rejects unsupported rules rather than silently assuming a US round lot.
- Provider clock/timezone differs from exchange time: retain source timestamp, normalize only when timezone semantics are known, otherwise mark unknown.
- Market data permission missing: show `unavailable: permission_required` and provider setup guidance.

## Success measures

- On next-session startup, each market panel shows a calendar-derived session state even when its feed is unavailable.
- Configured feeds show source and both data/retrieval times; disconnected feeds show a concrete error state.
- A user can add an instrument, view its quote/history when a configured provider supports it, and execute a paper order end-to-end.
- No live broker order can be generated by the Phase 1 application.

## Clarifications resolved

1. First markets: US, A-share/ChiNext, funds, Hong Kong, gold — user chose all.
2. First interface mode: real/delayed market data and paper trading — user chose this; no live trading now.
3. Data vendor credentials and subscriptions: not supplied; adapters remain configurable and missing access is an explicit unavailable state.
4. Full-market intraday universe: bounded to watchlist/configuration for Phase 1; full directory and daily data can be expanded subject to provider limits.
