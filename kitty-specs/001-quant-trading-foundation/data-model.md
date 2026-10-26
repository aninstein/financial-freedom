# Data model

## Core records

### Instrument

`instrument_id` (stable internal ID), `asset_class` (`equity`, `etf`, `mutual_fund`, `gold_spot`, `gold_benchmark`, `future`), `market` (`US`, `CN`, `HK`, `FUND`, `SGE`, `FUTURES`), `venue`, `provider_symbol`, `canonical_symbol`, `name`, `currency`, `quantity_unit`, `price_unit`, `tick_size`, `lot_size`, `timezone`, `calendar_id`, `trading_status`, `metadata_source`, `valid_from`, `valid_to`.

Aliases map vendor/exchange codes to `instrument_id` and retain validity/source. A ChiNext flag is metadata, not a separate exchange or currency.

### Quote

`instrument_id`, `last`, `bid`, `ask`, `volume`, `currency`, `quote_kind` (`trade`, `nav`, `estimated_nav`, `benchmark`, `settlement`), `exchange_time_utc`, `received_at_utc`, `provider`, `provider_symbol`, `freshness`, `known_delay_seconds`, `raw_reference`, `sequence`.

### Bar

`instrument_id`, `interval`, `start_at_utc`, `end_at_utc`, `open`, `high`, `low`, `close`, `volume`, `currency`, `price_unit`, `adjustment` (`none`, `split`, `total_return`, `provider_default`, `not_applicable`), `provider`, `received_at_utc`, `freshness`, `dataset_version`.

### MarketSession

`market`, `venue`, `calendar_id`, `exchange_timezone`, `session_date_local`, `phase` (`pre_market`, `open`, `break`, `post_market`, `closed`, `holiday`, `unknown`), `opens_at_utc`, `closes_at_utc`, `next_open_at_utc`, `calendar_version`, `computed_at_utc`, `reason`.

### AccountSnapshot / Position

Account has `account_id`, `label`, `mode` (`manual`, `readonly`, `paper`), `provider`, `base_currency`, `as_of_utc`, `connection_state`. Balances and positions retain native currency, units, market value, source, and as-of time. Converted totals also retain FX instrument, rate time, and conversion method.

### PaperOrder / Fill / LedgerEntry

Order fields: `order_id`, `account_id`, `instrument_id`, `side`, `type`, `quantity`, optional `limit_price`, `time_in_force`, `status`, `idempotency_key`, `created_at_utc`, `risk_result`, `simulation_rule_version`.

Fill fields: `fill_id`, `order_id`, `quantity`, `price`, `fee`, `currency`, `source_quote_or_bar_id`, `filled_at_utc`, `slippage_model_version`. Ledger entries are append-only cash/position deltas linked to fill/order.

### StrategyRun / DatasetVersion

Strategy run retains strategy ID/version/parameters, dataset version, universe, time range, calendar, adjustment, benchmark, costs, metrics, artifact URI, and execution time. Dataset version retains provider, market, instruments, frequencies, date range, ingestion time range, schema version, and content manifest/hash.

### DailyHistoryJob

`instrument_id`, `interval`, `state` (`queued`, `running`, `complete`, `retry_wait`, `failed`), `target_bar`, `latest_bar`, `attempt_count`, `last_attempt_at_utc`, `next_retry_at_utc`, `last_success_at_utc`, `last_error`, and `updated_at_utc`. A job is scoped to a watched instrument; retries use capped exponential backoff, and a process restart returns interrupted `running` jobs to `queued`.

### ProviderHealth

`market`, `failure_count`, `last_attempt_at_utc`, `next_retry_at_utc`, `last_success_at_utc`, `last_error`, and `updated_at_utc`. Provider calls share a concurrency bound and per-market refresh interval. Repeated failures back off exponentially up to six hours; explicit user refresh can bypass the wait.

## Invariants

- All stored timestamps are UTC; exchange-local timestamps are derived with an IANA zone and the original source string may be preserved.
- Do not infer missing currency, unit, timezone, or instrument mapping silently.
- An `estimated_nav` is never shown as a published NAV; gold price units/purity are required for comparisons.
- A quote's receipt time never substitutes for provider/exchange observation time.
- Stale and unavailable are distinct states; stale data remains queryable for history but not presented as current.
- Paper ledger balances are derived from an append-only ledger; order confirmation and ledger mutation share a transaction.
