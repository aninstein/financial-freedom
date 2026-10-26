---
work_package_id: WP05
title: Dashboard data wiring and local operations
lane: completed
depends_on: [WP02, WP03, WP04]
---

## Goal
Change the static concept dashboard into a provenance-aware market and paper account workspace without presenting fixture values as live.

## Acceptance criteria
- Market session, provider state, quote provenance/freshness, account mode, and paper order state are visible.
- Errors and unavailable feeds are isolated by source/market; no mock fallback appears connected.
- UI remains readable at current desktop/mobile breakpoints and retains supplied design tokens.
- Quickstart explains local startup, provider config, next-session smoke run, limitations and logs.

## Tasks
- [x] Replace static market status and source cards with API-bound elements.
- [x] Remove fabricated balance, quote, strategy and recommendation content.
- [x] Wire instrument search/watchlist, refresh, account snapshot and paper order flow.
- [x] Add historical research controls and local operations guide.
