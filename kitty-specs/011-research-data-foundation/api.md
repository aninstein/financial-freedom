# 011 · 受限查询工具/API 契约

接口由现有 FastAPI 身份层保护。下列是内部研究工具的目标契约；如暴露 HTTP 路由，同样必须校验会话/CSRF（写请求）、范围和审计。工具参数不含 SQL、Cypher、任意文件路径或 URL。

## 公共返回字段

```json
{
  "status": "ok | partial | insufficient_data | stale | rejected",
  "as_of": "2026-10-26T00:00:00Z",
  "snapshot_id": "S-...",
  "source_cutoff": "2026-10-25T16:00:00Z",
  "rows": [],
  "truncated": false,
  "coverage": {"matched": 0, "returned": 0, "missing": []},
  "evidence": [{"evidence_uuid": "...", "display_id": "E001", "source_record_id": "...", "locator": "page=3;chars=120-310", "known_at": "...", "content_hash": "..."}]
}
```

`snapshot_id` 对实时点查可为空，此时必须给出 `source_cutoff` 和来源/新鲜度。`status=partial` 与 `truncated=true` 不等于完整市场覆盖。错误返回明确类型与可重试性，不回传内部路径或私密原件。

## `query_market_facts`

输入：`instrument_ids`（1–20）、`metric_codes`（白名单 1–20）、`start/end`、`adjustment`、`as_of`、`limit<=1000`。输出逐行数值、单位/币种、频率、时间口径、源版本、缺口。对历史 `as_of` 只读可见版本；旧行历史可见性未知时拒绝把它当 PIT 数据。

## `run_research_screen`

输入：`universe_id`、`snapshot_id`、`screen_id`（注册过的确定性筛选模板）、有界参数、`limit<=100`。输出排序、指标定义/版本、样本数、缺失率、快照哈希、耗时。超时或无快照返回明确状态。模型只能选择模板和参数，不能提交表达式代码。

## `search_research_documents` / `read_document_chunk`

搜索输入：`query<=200 chars`、`instrument_ids`、`document_types`、`published_before/as_of`、`report_period`、`limit<=20`。输出候选 `chunk_id`、文档版本、标题、页码、片段、词法/语义匹配来源、可见性与权限。读取输入：`chunk_id`；输出原文、页码、起止偏移、原文件哈希。旧 `search_uploaded_documents` 和 `read_uploaded_document` 保持可用并转接新索引。

## `trace_research_relations`

输入：起点 `entity_id`、允许的 `relation_types`、`as_of`、`max_hops<=3`、`max_nodes<=100`、`include_candidates=false`。输出路径、每条边的 `relation_id`、关系有效期/可见时点、审核状态和 `chunk_id`/源记录。若请求“供应链影响”但只有共现边，返回 `insufficient_data`，不自动补成因果路径。

## `resolve_research_entity`

输入：名称/代码、市场和可选日期。输出零到多个候选与消歧证据；多候选时请求明确市场/实体，不默选同名公司。

## 权限与执行上限

- 服务端固定超时、最大扫描时间/内存、并发和输出字节预算；超限返回 `rejected` 或 `partial`。分析作业独立 Worker，不阻塞页面报价与账本。
- 仅用户明确选择账户并授权本轮研究后，既有账户工具才能返回账户数据；上述文档/行情工具不能推断账户 ID。
- 原件下载仍走已有鉴权路由；检索片段只返回必要文本。llm-wiki 的记忆 ID 不能替代 `evidence_uuid`。
