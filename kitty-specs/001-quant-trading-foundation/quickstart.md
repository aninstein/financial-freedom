# Quickstart acceptance walkthrough

1. Configure the local app with no provider credentials and start it on `127.0.0.1`.
2. Open the dashboard. Exchange sessions should be shown from calendars. Data-source cards should say unavailable/not configured; no fixture prices, balances or recommendations should look live.
3. Inspect each AKShare market status. Add symbols from returned quote data where available; failed upstream markets must remain visibly unavailable and are not replaced with fixtures.
4. Pull a quote and a daily history range. Confirm the native currency/unit, provider, exchange time, receive time, freshness and delay label.
5. Stop or misconfigure one source. Confirm that source becomes error/stale while other markets and session states still render.
6. Save a manual account snapshot from the dashboard or `POST /api/v1/accounts/manual`; confirm the UI keeps it distinct from paper accounts and currencies are not implicitly summed.
7. Add an instrument such as `HK:00700` or `US:AAPL` to the watchlist if it is not present in the market snapshot. If the HK bulk feed fails, the app fetches a Sina single-symbol quote and labels freshness from its timestamp. If the US full-market spot feed is unavailable, the app fetches its documented 15-minute-delayed Sina quote; if that fails, it attempts to show the daily close as end-of-day data. EOD rows cannot create or fill simulated orders. Preview a valid A-share (100-share buy lot) or US/ETF integer-share paper order; review amount, fee, source and quote time, then explicitly confirm. Confirm duplicate idempotency keys do not create duplicate orders. HK, mutual-fund NAV, gold, and EOD-only order attempts are rejected.
8. Watchlist additions trigger a bounded daily-bar backfill through the previous completed session. Later completed bars are collected on the scheduled refresh and the watchlist displays the latest stored bar date or an ingestion error.
9. Pull daily bars for a supported stock, ETF or SGE spot gold instrument and run the SMA baseline with enough observations. Confirm dataset version, native price unit, fee/slippage assumptions, buy-and-hold comparison, and risk metrics are saved.
10. Verify that the paper workflow contains no call to a live brokerage endpoint.
11. On 2026-10-26, record which sessions are open, which endpoints respond, observed delays, and any unavailable market/provider permission. Do not declare a provider “real-time” based only on its name.
