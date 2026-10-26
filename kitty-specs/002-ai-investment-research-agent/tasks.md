# Work packages — Feature 002

Feature 002 was authorized on 2026-10-26. Implemented scope and remaining gaps:

1. **WP01 — Read-only research API and run history:** [x] AI status, bounded tool registry, run audit/evidence records, history APIs, ENV model selection and fallback.
2. **WP02 — Document ingestion/retrieval:** [partial] Text PDF/TXT/Markdown/CSV import, text extraction, content hash, page/segment keyword search, citation IDs and delete. Vector retrieval and OCR remain pending.
3. **WP03 — Financial document analysis:** [partial] Upload and retrieve public/user-provided research materials; AKShare A-share financial abstract; generated report references pages/evidence. More robust table parsing, provider filings/news discovery and export remain pending.
4. **WP04 — Single-security/market analysis:** [x] Read-only instrument quote/history indicators and cached market breadth with source freshness and market session.
5. **WP05 — Strategy research:** [partial] Agent can launch the existing deterministic SMA baseline and explain saved metrics. Strategy DSL, strict historical point-in-time dataset manifests and separate out-of-sample workflows remain pending.
6. **WP06 — Fund/flow research:** [partial] Cached fund/ETF screen and on-demand disclosed fund holdings. Wide async universe jobs, persisted official Stock Connect history and licensed flow data remain pending.
7. **WP07 — UI, settings and governance:** [partial] Dashboard AI research UI, server-side model ENV configuration, explicit account opt-in, evidence audit, no trading tools. Citation evaluation, queued jobs/cancellation, provider quota panel and retention settings remain pending.

## Release gates

- No Agent-to-order execution path.
- Tool outputs retain provenance and as-of time; unsupported claims are identified as gaps.
- Batch coverage and provider permissions are displayed before any future whole-market scan.
- Complete remaining partial scope before claiming full Feature 002 acceptance.
