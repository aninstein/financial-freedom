# Implementation plan — AI 投研与市场研究 Agent

**状态：** 首个只读 MVP 已实现；向量检索、异步批处理和额外数据源仍待实现。

## 目标架构

```text
Dashboard / research chat
        ↓
AI research API ── run registry / access policy / budget
        ↓                         ↓
Intent router + schema output   Audit / evidence manifest
        ↓
Read-only tool registry ─── Provider registry
  ├─ quotes / bars / calendar     ├─ existing AKShare adapters
  ├─ accounts (explicit opt-in)  ├─ official filings / announcements
  ├─ funds / connect statistics  ├─ licensed news / financial data
  ├─ document search            └─ user-uploaded documents
  └─ deterministic backtest
        ↓
SQL / full-text index / vector index / document object store
        ↓
Citation validation → report with evidence → user

No path from AI research API to paper orders or broker adapters.
```

## 技术方向

- 延续当前 FastAPI + SQLite；新增研究运行表、证据表、文档元数据表和文档索引状态。文档/向量数据增大后评估 FTS5 + pgvector 或独立向量服务，不预先引入复杂基础设施。
- MVP 把用户上传原件、文本页/片段、SHA-256、来源类型、时间、解析状态和页码映射放在本地 SQLite；增长后再迁移至受控对象存储，删除流程需同步清理研究引用。
- 当前检索采用本地文档分片关键词匹配。后续可增加 SQLite FTS5 和向量召回；向量索引只用于文本语义候选，金融数值事实仍走结构化数据接口。
- LLM 使用服务端 provider interface 和 JSON schema，支持云 API 或 OpenAI-compatible 本地端点；密钥不发给浏览器，不在日志记录提示中的敏感账户原文。
- LLM/embedding/provider 通过配置选择；模型未配置时，功能优雅降级为检索与回测报告，不生成 AI 结论。
- 记录 prompt/model/schema/tool 版本和每次工具响应摘要，支持运行回放与预算限制。
- 最小权限工具注册表无任意 SQL/HTTP/shell 工具，不注册订单读写方法；账户工具默认 disabled。

## 分阶段实施建议

1. **研究与审计底座（MVP 已实现）：** 文本 PDF/UTF-8 文件导入/解析、关键词检索、研究 Run 和 evidence manifest。
2. **财报/研报分析：** 先支持用户上传和官方公开材料；实现页级引用、表格校验与报告导出。
3. **个股/大盘研究：** 接现有行情/因子/交易日历，做技术与结构化基本面工具；LLM 仅综合证据，展示正反观点和周期。
4. **量化策略研究：** 用 Agent 生成受限参数 schema，调用现有确定性 backtest；增加 PIT/样本外/基准核验，再展示结果。
5. **基金和资金流专题：** 明确每个 provider 授权和字段定义后，接基金披露、ETF份额/申赎和官方可用的 Stock Connect 统计；构建限界批量任务。
6. **待补齐：** 后台任务队列/取消、向量检索、新闻与授权研报适配器、引用评测、provider 配额/限流和大范围异步扫描。
7. **试运行与治理：** 评估引用准确率、数据覆盖、错误回退、成本/时延、批任务速率和账户隔离；达到验收后再考虑个性化推荐。

## 数据源准入清单

每个 SourceAdapter 上线前，记录：官方/授权来源、市场和资产覆盖、历史区间、披露/更新时间、实时/延迟属性、API 配额、费用、访问与再分发许可、字段单位、修订机制、错误语义、PII/留存限制。无法确认的字段保持 unavailable/unknown。

## 已知依赖和风险

- AKShare 是现有尽力而为适配器，不足以承诺完整市场/基金/新闻/财务数据覆盖。Feature 002 不应把它当作所有信息需求的唯一数据源。
- Northbound 实时 buy/sell/total turnover 官方不再发布；如要实时资金流需采购已授权定义明确的数据，否则调整问题为历史统计/季度持仓。
- 研报和新闻批量抓取需版权/供应商授权；首版可从用户上传和官方公开披露开始。
- 现有 backtest 是 SMA 基线。Feature 002 可以做研究配置编排，但不能宣称已具备多策略生产级验证。
