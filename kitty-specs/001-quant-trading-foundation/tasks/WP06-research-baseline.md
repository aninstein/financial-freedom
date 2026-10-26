---
work_package_id: WP06
title: Deterministic research and backtest baseline
lane: partial
depends_on: [WP01, WP03]
---

## Goal
Create a reproducible research interface over normalized bars; defer AI-generated signals.

## Acceptance criteria
- Strategy run pins version, parameters, universe, dataset, calendar, adjustment, benchmark, fees and slippage.
- Metrics are deterministic and timestamp-aware; no bar after decision time can be read.
- Outputs are labeled historical research and include a risk summary.

## Tasks
- [x] Persist strategy runs against a content-hashed dataset manifest.
- [x] Add a deterministic SMA trend baseline and buy-and-hold comparison.
- [x] Include transaction fee/slippage assumptions, annualized volatility, Sharpe ratio and max drawdown.
- [ ] Add a broader strategy API, benchmark calendars, corporate-action adjustment policies and unit-level reproducibility controls.

The baseline requires sufficient locally stored daily bars and uses unadjusted prices; it is a research starter, not an investment recommendation.
