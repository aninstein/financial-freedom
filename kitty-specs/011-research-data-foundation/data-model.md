# 011 · 数据模型与存储契约

以下为 MySQL/InnoDB 目标逻辑模型；实施时通过版本化迁移建表，不能直接重建已有 `bars`、账本或文档。所有时间以 UTC ISO 8601 存储，查询展示时按市场时区转换。`NULL` 表示未知，不能当作 0 或推断历史可见。

| 逻辑表 | 主键/关键字段 | 索引与约束 |
| --- | --- | --- |
| `source_record` | `record_id`, `source_id`, `external_id`, `payload_hash`, `event_at`, `published_at`, `first_seen_at`, `ingested_at`, `license_id`, `raw_ref`, `status` | `(source_id, external_id, payload_hash)` 去重；原记录不可覆写 |
| `market_bar_observation` | `observation_id`, `instrument_id`, `interval`, `bar_time`, `adjustment`, OHLCV, `currency`, `price_unit`, `volume_unit`, `source_record_id`, `known_at`, `revision_no` | `(instrument_id, interval, bar_time, adjustment, source_record_id)`；同一经济事实可多版本 |
| `financial_fact` | `fact_id`, `issuer_entity_id`, `metric_code`, `value_decimal`, `unit`, `currency`, `period_start/end`, `period_type`, `accounting_scope`, `consolidation`, `published_at`, `first_seen_at`, `known_at`, `source_record_id`, `locator`, `verification_state` | `(issuer_entity_id, metric_code, period_end, known_at)`；`candidate/verified/rejected` |
| `document_version` | `document_version_id`, `document_id`, `content_hash`, `source_record_id`, `filename/title`, `document_type`, `report_period`, `published_at`, `first_seen_at`, `access_scope`, `parse_version`, `state` | `(document_id, content_hash)` 唯一；旧 `ai_documents` 保留兼容映射 |
| `document_chunk` | `chunk_id`, `document_version_id`, `page_start/end`, `char_start/end`, `section_path`, `text`, `text_hash`, `known_at` | `(document_version_id, page_start, char_start)`；页码/偏移回查原文 |
| `document_chunk_fts` 索引 | `text`, `chunk_id`, 文档过滤字段 | MySQL InnoDB `FULLTEXT(text) WITH PARSER ngram`；候选后按原文精确复核 |
| `entity` / `entity_alias` | `entity_id`, `entity_type`, `canonical_name`; `alias`, `market`, `valid_from/to`, `source_record_id` | 证券标识唯一且带市场；别名允许不同有效期，不盲合并 |
| `entity_relation` | `relation_id`, `from_entity_id`, `to_entity_id`, `relation_type`, `valid_from/to`, `known_at`, `source_record_id`, `chunk_id`, `verification_state`, `confidence` | `(from_entity_id, relation_type, known_at)` 与反向索引；需有出处 |
| `dataset_snapshot` / `snapshot_file` | `snapshot_id`, `schema_version`, `source_cutoff`, `created_at`, `published_at`, `state`, `manifest_hash`; `path`, `content_hash`, `row_count`, `min/max_time` | 只读发布态；路径受控且只能在 `data/analytics/` 下 |
| `analysis_result` | `result_id`, `snapshot_id`, `query_version`, `parameter_hash`, `result_hash`, `metrics_json`, `created_at` | `(snapshot_id, query_version, parameter_hash)` 可复现 |
| `research_evidence` | `evidence_uuid`, `run_id`, `display_id`, `source_record_id/chunk_id/fact_id/snapshot_id`, `locator`, `query_parameters_json`, `verification_state`, `revoked_at` | 引用指向不可变版本；删除时撤销或重建 |

### 时点规则

- `known_at = max(published_at, first_seen_at)`；若 `published_at` 不可靠或缺失，仅以 `first_seen_at` 作保守上界。两者都缺失时标 `historical_visibility_unknown`，不纳入 PIT 查询。
- 证券行情的 `bar_time` 是市场时间，不代表当时已经可见；完成交易日、供应商发布时间和本机首次观察分别记录。
- 选择 `as_of` 可见版本时，先过滤 `known_at <= as_of` 与验证状态，再按来源优先级、修订号和 known_at 选择；把选中版本 ID 固化进快照。不能用旧 SQLite 当前 `bars` UPSERT 行倒推历史版本。
- 财报重述不覆盖旧事实；不同会计范围、累计/单季度、币种或单位不能直接比较。数值使用十进制定点或保留原字符串与比例尺，避免浮点比较误差。
- 关系边的 `valid_from/to` 表示经济关系期间；`known_at` 表示研究者何时有证据知道。路径查询同时执行两个时间过滤。

### 检索索引与快照物理布局

- MySQL InnoDB 对片段正文建立 ngram FULLTEXT，`ngram_token_size=2` 在容器配置中固定。中文长词、证券代码、英文术语必须经原文精确复核与检索题集验证。上传、修订、删除在同一事务维护记录与索引；有可重建命令与索引版本。
- Parquet 按数据集类型/市场/频率/年份组织批量文件，例如 `bars/market=CN/interval=1d/year=2026/part-*.parquet`。不按证券逐文件或逐日逐文件；导出批次以目标大小和源数据分布控制文件数。
- manifest 记录全体文件哈希、schema、源 `record_id` 范围、选择版本规则及行数；临时目录校验后才发布。DuckDB 以 `snapshot_id` 解析 manifest，不接受模型输入任意磁盘 glob。
- 向量索引如后续启用，以 `chunk_id + document_version_id + embedding_model_version` 为键，权限与删除传播继承文档版本；向量本身不成为证据。

### 既有表迁移

1. 先将两份旧 SQLite 库的全部在线业务表导入 MySQL 并逐表校验；旧文件只读保留，不再为在线业务写 SQLite。保留 `bars`/`dataset_manifests`/`ai_documents`/`ai_document_pages` API；为旧行创建可追溯映射，不改写历史接收时间。
2. 旧 `bars` 若无原始版本，只迁为 `legacy_unverified`，供当前展示和非 PIT 描述分析；新采集开始写入不可变 observation。
3. 旧上传文档若只有 `imported_at`，将它作为 `first_seen_at`；`published_at` 保持空。保留原页顺序和页码，片段反查文件哈希。
4. 新 schema 双读期记录行数、字段、抽样哈希和查询差异；通过校验再把研究工具切向新视图。任一步失败回退 MySQL 旧查询路径，保留原 SQLite 只读备份。
