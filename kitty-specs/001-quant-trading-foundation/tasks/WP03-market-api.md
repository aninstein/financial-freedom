---
work_package_id: WP03
title: Market read API and historical ingestion
lane: partial
depends_on: [WP01, WP02]
---

## Goal
Expose provider health, market status, instruments, watchlists, quotes and OHLCV history through a stable local API.

## Acceptance criteria
- Endpoints match `contracts/openapi.yaml` and return per-market partial results.
- Watchlist daily history can be pulled and stored idempotently; configured intraday polls are bounded to the watchlist.
- Every response includes provider, observed/received timestamps, currency/unit and freshness.
- Historical pulls expose adjustment policy and dataset version.

## Tasks
- [x] Implement FastAPI health, provider, market status, instrument, watchlist, quote and bar routes.
- [x] Add bounded manual quote refresh and daily-bar pull triggers.
- [x] Add local SQLite query path and dataset manifests.
- [x] Add timeout/error responses and local diagnostics.
- [x] Add scheduled daily watchlist backfill and incremental collection with a bounded watchlist, overlap window, and visible latest-bar/error state.
- [x] Persist per-instrument history job state, recover interrupted jobs after restart, and apply exponential retry backoff capped at 24 hours.
- [x] Bound concurrent provider calls with a shared semaphore and per-market refresh interval.
- [x] Persist quote-provider failures per market and back off retries exponentially up to six hours while continuing bounded US watchlist quote refreshes.

Historical ingestion is daily only; no intraday bar ingestion or full-universe scheduler is claimed.
