# Financial Freedom Project Charter

## Product purpose

Build a local-first personal quant workspace that joins trustworthy market data, read-only account visibility, reproducible quantitative research, paper trading, and later an evidence-grounded AI agent.

## Product principles

1. **Evidence before interpretation.** Every market or account value carries its source, currency/unit, exchange time, ingestion time, and freshness state.
2. **Paper before live.** Phase 1 may read market data and simulate orders only. It must not submit orders to a real broker.
3. **Deterministic finance.** Balances, indicators, sizing, risk checks, fills, and backtest metrics are computed by code. An LLM may explain them in a later phase, but cannot authorize trades.
4. **Market semantics stay explicit.** Exchanges have different calendars, sessions, currencies, lot sizes, price limits, and asset valuation conventions. Never flatten these into an unlabeled universal number.
5. **No fabricated availability.** Missing credentials, unsupported instruments, upstream failures, and stale feeds are shown as such. Demo fixtures are never presented as live data.
6. **Traceable changes.** Persist provider, instrument, dataset, strategy, paper-order, and configuration versions needed to reproduce a result.
7. **Personal and local by default.** Keep secrets on the server, bind the development server to loopback, and do not redistribute vendor data.

## Phase 1 boundary

Support market-state and quote visibility across US equities/ETFs, mainland China A-shares including ChiNext, Hong Kong equities/ETFs, funds, and gold instruments; historical bar ingestion for a user-configured watchlist; read-only/manual account snapshots; deterministic strategy/backtest scaffolding; and an internal paper account/order simulator. No AI recommendations, public multi-user service, or live order routing in this phase.

## Quality bar

- APIs expose explicit source and freshness metadata.
- A provider outage cannot silently return old data as current.
- Paper orders are isolated from live broker credentials and endpoints.
- Market, calendar, timezone, corporate-action, fund-NAV, and gold-contract semantics are represented in the data model.
- Local startup and provider setup are documented; all unavailable integrations are visible in the UI.

## Accepted increment 005 (2026-10-26)

The owner explicitly requested AI-operated paper trading. A single user-confirmed mandate authorizes bounded virtual orders only; the LLM cannot grant or expand that authority. Server code owns account/symbol scope, nominal budget, order count, cash/position risk, matching and idempotency. No real broker routing is authorized. Earlier research-only wording remains the historical phase-1 boundary.

## Accepted increment 006 / superseded live scope (2026-10-26)

Independently funded paper trials and scoped clearing/reopening remain accepted. The earlier live broker integration request is explicitly deferred by the user. Broker code remains an inactive draft; it is not imported, configured or exposed by the running application. Public multi-user registration remains closed.

## Accepted increment 007 (2026-10-26)

Prioritize paper trading and evidence-backed research: stocks, market indices, uploaded reports, financial statements, data collection, flow coverage and descriptive historical cycles. The AI may execute only a bounded user-authorized paper mandate. No brokerage credentials or live order capabilities are required. Missing data and stale sources must remain explicit.

## Accepted increment 008 (2026-10-26)

The user prioritizes live news, reverse repo operations and sector rotation as strategy context. Collect public news with publication/first-seen timestamps, official central-bank OMO disclosures and industry window/observed-date snapshots. Distinguish missing data, overlapping horizons and causal hypotheses. Paper authority remains bounded; no real broker routing or repo-product trading is authorized.

## Accepted increment 009 (2026-10-26)

The user explicitly replaces mandatory TOTP with password sign-in and password-only confirmation for sensitive paper actions. Optional Volcengine SMS may protect login after configuration; email is deferred. Preserve password hashing, private sessions, CSRF, owner authorization, audit and no-live-trading boundaries. This explicit decision supersedes earlier authenticator enrollment requirements; it does not authorize sending paid SMS or changing the existing owner password during development.

## Accepted increment 010 (2026-10-26)

The owner requests a fast market-index page. Refresh the local display each second, collect public index snapshots once per backend process, and optionally receive licensed quote subscriptions. Source exchange time, reception time and actual provider must remain visible. A one-second display cadence is not a claim of one-second exchange data. Historical daily bars stay separate from intraday observations; live broker trading remains deferred.
