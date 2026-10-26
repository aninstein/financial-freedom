# Research notes — AI 投研与市场研究 Agent

**检索日期：** 2026-10-25。项目能力持续变化；以官方项目仓库、交易所和监管机构为依据。研究结论是架构参考，不构成选型批准。

## 开源项目观察

| 项目 | 官方定位/可借鉴点 | 在本产品中的建议 | 主要限制 |
|---|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 多角色金融研究和决策流程；当前仓库材料提到 point-in-time 数据、结构化输出和回测能力 | 借鉴研究拆解、正反观点、经理综合和运行记录 | 研究脚手架不是稳定的收益策略；LLM 结果会随模型和数据变化，不能照搬交易结论 |
| [Microsoft Qlib](https://github.com/microsoft/qlib) | AI 量化研究管线，覆盖数据、建模、回测、风险和组合研究 | 可作为之后批量因子/模型实验的研究引擎候选；先复用现有确定性回测接口 | 不负责本产品级文档证据、账户访问和 UI Agent 权限；接入前评估数据格式、市场覆盖和样本外验证 |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 金融 NLP/语言模型研究，含情绪、关系抽取、问答与 FinGPT-RAG 方向 | 借鉴金融文本任务分解和任务评测；不要求首期部署或微调此模型 | 模型、数据集、市场和许可分别审查；仓库说明 Forecaster 市场覆盖有限，模型输出不能替代实时数据 |

建议首期实现单一编排器 + 类型化只读工具 + 确定性指标/回测，而不是一上来运行多个可互相授予工具权限的 Agent。报告可以按“行情分析、基本面分析、反方审阅、综合”分段，但都在同一受控运行上下文中。

## 数据来源与北向资金口径

- **美股财报：** [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)提供公开公司申报与 XBRL company facts 等 API；调用需遵守 SEC 自动访问要求，并缓存 accession、filing date、period 和原始来源。
- **中国公司公告/财报：** 使用交易所/法定披露平台或获授权供应商；现有 AKShare 可作尽力而为的研究适配器，不能被视为 SLA、许可或完整覆盖保证。PDF/表格抽取需保留原文页码并由结构化数值核验。
- **基金操作/持仓：** 基金定期报告披露持仓和报告期数据；它不是实时基金组合。基金净值、ETF 二级市场行情、ETF 份额、申赎和公告需要不同字段及数据源。
- **北向 Stock Connect：** [HKEX 与 SSE/SZSE 对数据披露的调整](https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en)于 2024-08-19 生效；实时北向买、卖和总成交额停止披露。部分历史日/月统计、十大活跃证券和季度持股仍可获得。HKEX 当前 [Stock Connect 统计目录](https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics?sc_lang=en) 和 [数据市场目录](https://data.hkex.com.hk/catalog/dataset/1e4dbd9c5eb24aebb2d74ce56467dff3)显示存在官方统计/数据产品，但订阅/历史下载会有许可和费用条件。
- 因而，产品不能答“当前北向净流入多少”并套用已停发累计净买入数据。应答可用的日终统计、额度余额（按当前披露条件）、季度持股或经许可供应商指标，明确统计口径与时效；若目标是盘中北向净买入，必须显示官方不可得或要求额外授权数据源。

## 推荐检索与分析架构

1. **领域路由：** 将问题路由到行情/指标、基金、文档、市场统计、策略实验、账户（显式授权）等类型。
2. **SQL/API 优先：** 余额、持仓、行情、日线、财务指标和交易日历使用结构化端点，不用向量搜索替代事实查询。
3. **文档检索：** PDF/HTML/公告解析为带证券、市场、文档类型、发布日期、报告期、页码、原文哈希和权限标签的片段；全文检索 + 向量召回并提供原文引用。
4. **异构来源对齐：** 按证券主数据映射代码；单位、币种、报告期、披露日和事件时间均显式存储。模型不得将相似字段直接求和/比较。
5. **确定性计算：** 技术指标、资金流聚合、基金排名和回测交给版本化服务；记录输入数据快照、代码/参数版本和数据缺口。
6. **LLM 综合：** 输入最小证据集，要求 JSON/schema 输出结论、周期、支持证据、反证、风险、缺失项和置信等级；用引用校验器检查 claim 是否有对应证据。
7. **PIT 与重放：** 所有候选事实同时保存事件/披露时间和系统抓取时间；回测按当时可见时间过滤，不允许后来修订的财报穿越回历史。
8. **批量任务：** 用户指定市场、universe、条件和截止时间；分片调度并行调用，速率限制、缓存、重试和进度可见；任务结束输出实际覆盖率及漏项。

## 关键风险

- **幻觉与引用漂移：** 关键数字必须由工具返回并与原文/行情快照绑定；无引用不输出确定事实。
- **披露时间泄漏：** 财报报告期不是公告可用时间；PIT 用 filing/disclosure timestamp。
- **幸存者/选择偏差：** 回测 universe 要包括退市标的，或明确数据不支持该控制。
- **全量采集/许可：** “网上可访问”不等于允许批量抓取或再分发；每个来源要有速率和许可策略。
- **流量定义混用：** 份额变化、主动买卖估算、成交额和官方资金流不可互换。
- **账户隐私：** 组合研究默认不传账户详细信息；需用户显式启用并限制字段。
- **LLM 不稳定：** 保存模型、提示、参数、工具响应；报告文案可变，但计算结果必须可复现。

## 参考来源

- [TradingAgents 官方仓库](https://github.com/TauricResearch/TradingAgents)
- [Qlib 官方仓库](https://github.com/microsoft/qlib) 与 [Qlib 官方介绍](https://github.com/microsoft/qlib/blob/main/docs/introduction/introduction.rst)
- [FinGPT 官方仓库](https://github.com/AI4Finance-Foundation/FinGPT)
- [SEC EDGAR API 官方文档](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [HKEX Stock Connect 数据披露调整公告](https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en)
- [HKEX Stock Connect 统计](https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics?sc_lang=en)
- [HKEX Data Marketplace](https://data.hkex.com.hk/catalog/dataset/1e4dbd9c5eb24aebb2d74ce56467dff3)
- [AKShare 基金数据文档](https://github.com/akfamily/akshare/blob/main/docs/data/fund/fund_public.md)
