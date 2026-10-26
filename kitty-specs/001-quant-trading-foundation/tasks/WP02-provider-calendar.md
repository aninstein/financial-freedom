---
work_package_id: WP02
title: Provider adapters and market calendars
lane: partial
depends_on: [WP01]
---

## Goal
Fetch supported cross-market quotes/bars through an adapter boundary and calculate exchange sessions independently from provider health.

## Acceptance criteria
- AKShare calls run off the event loop with timeout, throttling, error isolation and per-market health.
- A/HK/US/fund/gold interfaces normalize to the shared envelope; known limitations are surfaced.
- XNYS/XSHG/XHKG session status includes holidays, breaks, timezone, next session; SGE/gold has its own product/calendar mapping.
- Missing entitlements or unsupported markets return a typed unavailable state, never fabricated data.

## Tasks
- [x] Add normalized AKShare snapshot and daily-bar adapters, with Tencent then Sina fallbacks for A shares and Sina fallback for HK after Eastmoney endpoint failure. When HK bulk snapshots fail, request Sina quotes for watched HK symbols. Keep US bulk Sina disabled because it paginates 917 pages in the current runtime; fetch 15-minute-delayed Sina quotes for US watchlist symbols and use daily closes as an EOD-only fallback, blocked from paper matching.
- [x] Bound provider calls with shared concurrency and per-market refresh intervals; persist provider failures and apply capped exponential retry/backoff.
- [x] Add XNYS/XSHG/XHKG session calculation and explicit SGE regular-session approximation.
- [x] Surface per-market connection errors, receipt time, and unknown freshness without fixture fallback.
- [x] Document endpoint coverage and limitations.

Acceptance remains partial because the US full-market spot endpoint fails in the current network, source-specific licensing/freshness remains unverified, and full-market US snapshots are unavailable. US watchlist quotes work through Sina's single-symbol delayed feed with daily close as fallback. HK watchlist quotes also have a Sina single-symbol fallback when the full snapshot times out; its source timestamp is shown without assuming a delay. A-share and HK snapshots currently connect through the documented fallbacks; their observation timestamps/freshness are shown conservatively.
