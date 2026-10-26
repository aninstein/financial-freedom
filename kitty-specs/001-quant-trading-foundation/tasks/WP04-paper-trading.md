---
work_package_id: WP04
title: Account snapshots and paper execution
lane: partial
depends_on: [WP01, WP03]
---

## Goal
Provide clear account modes, manual/read-only snapshots, and a deterministic internal paper ledger and matcher.

## Acceptance criteria
- Manual/read-only/paper accounts are visually and structurally distinct.
- Supported equity/ETF buy/sell paper orders have server-side validation, deterministic risk results, fee model, idempotency and auditable status transitions. Mutual-fund NAV, gold spot and HK equities are rejected until their product-specific order/lot rules are modeled.
- Paper fills record quote/bar source and timestamp; unsupported market-specific lot/session rules reject rather than guess.
- No live order SDK or endpoint is invoked.

## Tasks
- [x] Add paper accounts and manual account snapshot API.
- [x] Add transactional simulated fills, cash/position checks, fee record and idempotency.
- [x] Add market/limit paper order creation, later quote matching, rejection and cancellation.
- [x] Add a separate preview-only endpoint and require explicit UI confirmation before paper-order creation.
- [ ] Add credentialed read-only broker adapters after a broker and supported authorization method are selected.

Paper coverage is intentionally limited to A-share round-lot buys and integer-share US/ETF orders. HK, mutual-fund NAV and gold are rejected because product-specific trading rules are not modeled.
