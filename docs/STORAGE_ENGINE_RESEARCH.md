# 股票投研数据存储与检索选型调研

日期：2026-10-26。状态：架构决策与实施建议，尚未完成新引擎性能实测。对应实施规格：[011](../kitty-specs/011-research-data-foundation/spec.md)。

## 结论

**保留 llm-wiki 作为 Agent 的长期记忆模块。** 记忆可帮助恢复研究偏好、历史问题和工作上下文，但行情、财务数值、研报原文及可验证关系应由本项目的带来源数据层回答。Agent 只能通过有界、只读的研究工具取得事实，再把证据 ID 带入答案。

按当前 Docker 部署决策做三件事：

1. **MySQL/InnoDB 作为唯一在线事务数据库**，承载身份、账户、模拟账本、行情热数据、文档、事实、实体关系与证据。通过 Docker Compose 启动，并完整迁移旧 SQLite 数据。不要让模型直接写 SQL。
2. **DuckDB + Parquet 作为派生的列式分析层**，承担跨证券、跨时间的大范围扫描、因子计算和回测数据集读取；从 MySQL 导出版本化快照，不迁移账本权威源。
3. **暂不引入独立图数据库**。先以 MySQL 关系表表达公司、证券、行业、主题、研报观点和证据之间的边；只有真实多跳查询达到性能/维护门槛时，再验证 Neo4j 等图数据库。

这不是单一数据库选型。数值分析、原文检索、关系遍历、长期记忆是四种查询形态，使用同一个向量库或图数据库会使行情聚合、时点约束和审计变得困难。

## 本轮落地状态

2026-10-26 已按参考项目的 Compose 模式启动 MySQL 8.4、一次性迁移任务、Web 和 DeerFlow worker；Web 只绑定宿主 `127.0.0.1:8000`。旧两库逐表行数与内容哈希校验通过，导入时有 30,675 条报价、26,298 条日线、6 个模拟账户、5 条 AI 研究记录和 1 个用户。MySQL 事务/UPSERT 冒烟、健康接口、审计链校验、容器重启恢复和 SQL 备份均通过。旧文件保留；MySQL 数据在持久卷。

旧库中有 1 条没有对应账户的 `external_positions` 孤立记录。迁移为了逐行保留历史数据，在单次导入会话暂时关闭外键检查，随后恢复；该记录需单独清理或归档，不应凭空补造账户。真实密码登录、模拟下单/撮合和模型研究调用尚未端到端验收。本文的全文索引、事实与关系表、DuckDB/Parquet 分析层仍是后续规格，不是已交付能力。

## 项目现状和可见瓶颈

迁移前代码核对：`app/main.py` 的旧 SQLite 库保存 `quotes`、`bars`、`dataset_manifests`、`research_runs`、`ai_documents` 和 `ai_document_pages`；身份、账户账本、新闻缓存以及 DeerFlow checkpoint 也有 SQLite 依赖。`bars` 的旧主键是证券、频率、时间、复权，更新使用 UPSERT；`app/ai_tools.py` 的研报搜索先读最多 5000 页再在 Python 中做关键词包含匹配。页面检索无倒排索引。旧库约 20 MiB、`bars` 约 25,814 行、导入文档 0 份（2026-10-26 本机只读盘点）。**这个样本不能证明 MySQL 或 DuckDB 更快；迁移 MySQL 的直接原因是用户指定的 Docker 服务化部署和统一存储。**

更重要的正确性缺口：`dataset_manifests` 记录哈希，但 `bars` 原值会被覆盖；历史研究若只依赖当前行，无法重放当时可见的数据版本。文档仅有上传时间和手填报告期，缺少正式发布时点、页内段落定位、披露版本、实体消歧和抽取事实审核状态。现有研究证据 ID 只在单次运行内编号，跨运行追溯需持久证据记录。

## 按工作负载比较

| 方案 | 擅长 | 本项目适配 | 主要限制 | 本轮决定 |
| --- | --- | --- | --- | --- |
| MySQL 8.4/InnoDB + ngram FULLTEXT | 服务端事务、证券/日期点查、中文研报关键词、浅层关系 JOIN | 符合 Docker 部署要求；统一身份、账本和研究元数据 | 行式 OLTP 不适合把大范围分析全部压在同一库；全文召回仍需题集验证 | **在线主库** |
| SQLite | 旧本机数据格式 | 只读迁移输入，保留备份供核对 | 不能再成为部署运行时的在线存储 | **退出运行链路** |
| DuckDB + Parquet | 本地列式扫描、窗口函数、跨证券聚合、可复现的数据快照 | 与 Python 研究/回测贴合；可直接读取分区 Parquet | 不应让多进程 Web/Worker 直接共同写一个原生 DuckDB 文件；Parquet 小文件与频繁修订需要批处理治理 | **引入派生分析层** |
| PostgreSQL + TimescaleDB + pgvector | 时序分区/连续聚合、全文和向量检索 | 特定工作负载下可作为未来替代研究 | 不符合本轮明确的 MySQL 主库选型，会增加迁移成本 | **不在本轮** |
| ClickHouse | 大规模高吞吐列式分析与时序聚合 | 多市场分钟/逐笔、持续跨全市场分析时有价值 | 单机当前规模过度；更新、去重、修订需单独设计 | **规模化备选** |
| Neo4j 等图数据库 | 多跳关系路径、复杂模式匹配、图算法 | 供应链、股权穿透、事件传播等经验证需求可能受益 | 不适合 OHLC 聚合/时间序列回测；多一份关系数据与同步链路 | **暂缓** |
| 独立向量库 | 语义召回、相似研报/观点 | 关键词召回漏检时可辅助 | 向量相似不证明数值或因果事实；仍需时间/权限过滤、原文定位 | **按检索评测启用** |

以上能力根据各项目官方文档判断，未做本项目同数据、同硬件基准测试。MySQL 的 ngram FULLTEXT 支持中文二元切词，但需要验证停用词、长词精确复核和排序；InnoDB 有行锁与事务，旧 SQLite 的 `BEGIN IMMEDIATE` 必须改成可验证的 MySQL 并发控制。DuckDB 对 Parquet 支持列与过滤下推，但不承担在线账本；分区太细会产生大量小文件。MySQL 递归 CTE 可用于浅层图关系 PoC。

## 推荐的边界和数据流

```text
来源接口 / 用户上传
  -> 原件与采集日志（不可改写的版本、哈希、来源许可）
  -> 归一化与质量检查
      -> MySQL：最新行情、数值事实版本、文档/片段、实体边、研究证据、账户/账本
      -> 批量快照 -> Parquet：历史行情/因子/财务分析数据集
                         -> DuckDB：确定性统计、筛选、回测
  -> 受限 Research API：结构化查询 / 文档混合检索 / 浅层关系查询
  -> Agent 合成带来源回答

llm-wiki：偏好与历史研究记忆 -> 只提供上下文线索；引用事实仍回查 Research API
```

同一类事实只设一个权威写入面：近期 `bars` 以 MySQL 为准，Parquet 是可重建、带快照 ID 的派生分析工件。分析查询绑定已发布快照，更新完成后原子发布 manifest；用户若询问当前报价，走 MySQL 最新行情工具，明确两个截止时间。不得在分析时悄悄混用未发布的新行与旧 Parquet 快照。将来迁移冷数据权威源需单独迁移、双读校验和回滚方案。

## 图谱设计判断

关系查询确实需要建模，例如“某研报在某页提出的风险，关联哪家公司的哪个业务分部，又关联哪些证券”。第一步采用带类型的 `entity`、`entity_alias`、`entity_relation`、`document_mention` 和 `claim_evidence`。边必须有来源片段、`valid_from/to`、`known_at`、置信/审核状态；“共同出现在一篇研报”只标 `MENTIONS`，不能自动提升为 `SUPPLIES_TO` 或因果影响。查询限定 1–3 跳、边类型与返回节点数，路径每一跳显示出处。

只有满足以下条件之一且经过同数据基准测试，才评估 Neo4j：产品连续出现 4 跳以上的交互路径/图算法需求；关系数据量与遍历复杂度使 MySQL 查询在目标硬件上持续超过延迟目标；或者维护递归 SQL 已明显阻碍正确表达业务。PoC 需要比较路径正确率、P95、同步滞后、运维和删除传播，而不是只看某一个演示查询速度。

## 快速 AI 查询的关键不在数据库名称

- **意图路由**：证券/日期/财务指标走结构化工具；研报观点走片段检索；关系问题走有界路径；记忆检索只补用户上下文。
- **先过滤再召回**：先约束市场、证券、报告期、文档种类、`known_at <= as_of` 和权限；再全文检索，语义检索作为可选补召回；最后重排并读取原文。
- **预计算**：常用收益、波动、最大回撤、财务同比/环比使用版本化计算作业；查询返回指标定义、样本量和所用快照，不让 LLM 现场算。
- **证据小包**：每次工具输出限定行数、字符数、扫描范围和时间；返回 `source_id`、页码/表格单元、发布/首次观察时间、查询参数、数据集哈希及缺口。
- **评测而非口号**：用真实问题集同时测 P50/P95、检索 recall@k、页码准确率、时点泄漏、证券消歧、复现哈希和资源占用。

## 时间语义和数据可信度

至少区分 `event_at`（交易/事件发生）、`period_end`（财报报告期）、`published_at`（正式披露）、`first_seen_at`（本系统首次观察）与 `ingested_at`（落库）。历史可见性采用保守 `known_at = max(published_at, first_seen_at)`；缺失可靠发布时间时只能用 `first_seen_at`，没有历史可见性证据的旧数据不能进入 PIT 回测。修订/重述新增版本，不覆写原版本。财报数值同时携带单位、币种、会计口径、合并/母公司范围、累计/单季口径和抽取审核状态。

上传研报须保留原文件哈希、权限、页码和片段哈希；模型抽取的观点、关系或数值先进入 `candidate`，经结构校验或人工审核后才成为可引用事实。全文或向量命中只说明找到了文本，不证明观点正确。

## 分期、规模门槛与决策

| 阶段 | 交付 | 启动门槛/退出条件 |
| --- | --- | --- |
| 0：MySQL 部署与迁移 | Compose 启动 MySQL、Web、Agent；只读导入旧 SQLite；校验账户、订单、身份及研究记录 | 数据逐表核对并完成登录、模拟账本与研究冒烟验证 |
| A：正确检索 | MySQL 时点化 schema、分段、ngram FULLTEXT、事实与关系、受限工具、证据固化 | 旧接口兼容，旧记录标 `historical_visibility_unknown` |
| B：列式分析 | 从权威 MySQL 导出带哈希 Parquet 快照；DuckDB 只读分析；基准/回滚 | A 的数据契约稳定后；与 MySQL 同输入计算结果一致，才切分析工具 |
| C：语义与图试验 | 向量召回或独立图引擎的离线对照 | 只有检索或多跳评测证明收益且达到下文门槛才实施 |
| D：规模化 | 优化 MySQL 或评估 ClickHouse | 分钟/逐笔数据或分析资源预算超限时重新选型 |

初始性能目标是**验收阈值，不是已测结果**：在目标本机与固定数据集上，单证券日线和财务事实查询 P95 ≤ 200 ms；指定证券/报告期研报检索 P95 ≤ 500 ms；10 年 × 5000 证券日线横截面筛选 P95 ≤ 3 s；3 跳关系查询 P95 ≤ 500 ms。并记录数据量、机器配置、并发 1/4/8、冷热缓存和解析/索引耗时。若数据源覆盖不足以构造该规模，用明确标记的合成数据测试性能，真实题集单独测正确性。

## 官方资料

- [MySQL 8.4 ngram 全文解析器](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)、[InnoDB 事务与锁](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-transaction-model.html)、[递归 CTE](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [DuckDB 读取 Parquet 与过滤/列下推](https://duckdb.org/docs/stable/data/parquet/overview)、[DuckDB 并发模型](https://duckdb.org/docs/stable/connect/concurrency)、[Parquet 分区写入与小文件注意事项](https://duckdb.org/docs/stable/data/partitioning/partitioned_writes)
- [Timescale hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/)、[continuous aggregates](https://docs.timescale.com/use-timescale/latest/continuous-aggregates/about-continuous-aggregates/)
- [PostgreSQL 全文索引](https://www.postgresql.org/docs/current/textsearch-indexes.html)、[pgvector 索引与过滤](https://github.com/pgvector/pgvector#filtering)
- [ClickHouse 时间序列能力](https://clickhouse.com/blog/working-with-time-series-data-and-functions-ClickHouse)、[Neo4j 图模型](https://neo4j.com/docs/getting-started/graph-database/)
