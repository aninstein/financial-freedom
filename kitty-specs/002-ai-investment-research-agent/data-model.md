# Data model — AI 投研与市场研究 Agent

本文件定义建议实体；实施时需与 Feature 001 SQLite schema 兼容，并保证时间、来源、权限和版本可追踪。

## Core entities

### `research_run`

- `run_id`, `user_id/local_profile_id`, `question`, `task_type` (`security|market|document|fund|flow|strategy`)
- `status` (`queued|running|partial|complete|failed|cancelled`), `created_at`, `started_at`, `completed_at`
- `market_scope`, `universe_snapshot_id`, `time_range`, `as_of`, `account_scope` (nullable, explicit opt-in)
- `model_provider`, `model_id`, `prompt_version`, `output_schema_version`, `toolset_version`
- `budget_limits`, `tool_call_count`, `provider_errors`, `coverage_summary`
- `report_json`, `report_markdown`, `replay_manifest_id`

### `source_document`

- `document_id`, `source_id`, `canonical_instrument_ids`, `market`, `document_type`
- `title`, `language`, `issuer`, `report_period_start/end`, `published_at`, `event_time`, `retrieved_at`
- `source_url`, `original_content` (local SQLite BLOB for the MVP; object storage can replace it later), `content_hash`, `mime_type`, `license_id`, `access_scope`
- `parse_status`, `parser_version`, `ocr_confidence`, `raw_retention_policy`

### `document_chunk`

- `chunk_id`, `document_id`, `ordinal`, `page_start/end`, `section_path`
- `text`, `text_hash`, `embedding_model/version`, `embedding_ref`, `entities_json`, `table_ref`
- `published_at` inherited/queryable for point-in-time search; `retrieved_at`

### `evidence_item`

- `evidence_id`, `run_id`, `evidence_type` (`quote|bar|metric|filing_fact|document_chunk|backtest|market_stat`)
- `source_id`, `source_record_id`, `document_id/chunk_id`, `canonical_instrument_id`
- `claim_key`, `claim_value_json`, `unit`, `currency`, `event_time`, `available_at`, `retrieved_at`
- `dataset_hash`, `source_url`, `citation_locator`, `freshness`, `quality_flags`, `query_parameters`

### `research_claim`

- `claim_id`, `run_id`, `claim_text`, `claim_type` (`fact|interpretation|scenario|risk`)
- `evidence_ids[]`, `verification_state` (`supported|conflicting|unsupported|stale`)
- `confidence_label`, `time_horizon`, `created_at`

### `batch_job`

- `job_id`, `run_id`, `provider_id`, `market`, `universe_hash`, `filters_json`
- `max_items`, `rate_limit`, `cursor`, `processed_count`, `failed_count`, `state`, `next_retry_at`

## Integrity rules

- `published_at/event_time` are distinct from `retrieved_at`; PIT queries filter on when data became public, not merely which period it describes.
- Every numeric fact has a unit and, when monetary, a currency. No cross-currency aggregation without a versioned FX evidence item.
- A run pins its dataset/document/index snapshots and strategy config. New crawls or document revisions never mutate historical run evidence.
- LLM statements are never stored as source facts. All externally checkable claims map to evidence IDs or are marked unsupported.
- Raw documents are retained/deleted according to source license and user deletion policy; embeddings inherit the same access and retention boundary.
- Account evidence requires explicit opt-in, uses account ID pseudonyms, and contains only fields needed for the requested report.
