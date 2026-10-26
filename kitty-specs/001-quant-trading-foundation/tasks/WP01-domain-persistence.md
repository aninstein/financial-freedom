---
work_package_id: WP01
title: Domain schemas and local persistence
lane: completed_with_scope_adjustment
depends_on: []
---

## Goal
Create normalized instrument, quote, bar, provider-health, account, and paper-ledger schemas with UTC/provenance invariants.

## Acceptance criteria
- Schemas validate currency, units, freshness, market, asset class, and timestamps without assuming missing values.
- Local metadata/ledger persistence is transactional and supports idempotency keys.
- Historical bars have a dataset-version manifest and can be stored/queryable by instrument and interval.
- No provider-specific dataframe shape is exposed as the domain model.

## Tasks
- [x] Add validated request schemas for account snapshots, orders, bars and research requests.
- [x] Add SQLite metadata, manual account snapshots, paper orders/fills, daily bars and dataset manifests.
- [x] Persist normalized daily bars idempotently with content-hashed dataset versions.
- [ ] Move high-volume historical data to Parquet/DuckDB when data scale justifies another store.
- [x] Keep provider configuration in environment variables; do not persist credentials.

SQLite is the Phase 1 local store for both metadata and daily bars. Full domain-wide Pydantic record coverage and credentialed adapters remain follow-up work.
