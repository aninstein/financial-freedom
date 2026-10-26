# 开源量化平台与 AI 交易工具调研

**检索日期：** 2026-10-25。仓库和文档持续变化，采用项目官方仓库/官方文档作为主要来源。Star 数波动较快，本文不把 Star 当作成熟度或实盘安全证据。

## 结论摘要

- **量化研究底座：** Microsoft Qlib 最贴近“AI/ML 量化研究平台”，覆盖数据、模型、回测和策略研究；适合借鉴研究流水线，不直接承担用户账户/交易 Agent 的产品层。
- **交易框架：** vn.py 面向 Python 交易系统开发，国内交易接口生态更相关；Lean 是成熟的事件驱动回测与实盘引擎，适合多资产/跨市场策略基础设施。二者都应封装为执行适配器，不把 LLM 直接接到券商交易接口。
- **AI 研究：** TradingAgents（不是“Transaction AI”）是最可能对应用户记忆的项目：多角色 LLM 研究/辩论并合成交易建议。项目声明用于研究、结果非确定，也不能视为经过验证的投资策略。
- **AI 因子研发：** Microsoft RD-Agent 可参考自动因子挖掘/模型优化工作流；FinGPT 适合金融 NLP/情绪分类的研究参考；FinRL/FinRL-X 适合强化学习或 AI-native 策略实验，不宜直接作为零售实盘推荐器。
- **产品集成路线：** 复用研究/回测引擎与模型思想，自己构建账户连接、检索服务、证据归因、用户交互、权限风控和审计。先只读 + 模拟，再评估实盘。

## 平台比较

| 项目 | 主要定位与能力 | 对本产品的价值 | 需要留意 |
|---|---|---|---|
| [Microsoft Qlib](https://github.com/microsoft/qlib) | AI-oriented 量化研究平台；数据处理、监督学习/强化学习、因子与模型研究、回测、策略分析和在线服务；MIT | 研究层首选参考；可作为离线因子/模型实验与可复现流水线底座 | 本身不是完整个人账户管理产品或交易 Agent；数据准备和领域学习成本较高；先采用研究工件接口集成 |
| [vn.py / VeighNa](https://github.com/vnpy/vnpy) | Python 开源量化交易系统框架，提供事件驱动交易、应用模块和多类交易/行情接口；MIT | 国内 Python 交易适配和事件驱动系统的参考，可能适合未来 A 股/期货模拟或实盘适配 | 可用接口取决于市场、券商和接入条件；需要独立审查接口稳定性、合规和运行保障 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | C# 核心、Python/C# 算法支持的事件驱动交易引擎，可本地研究、回测和实盘；Apache-2.0 | 策略生命周期与回测/实盘一致性参考；多资产引擎可作为隔离执行器候选 | 部署/数据/券商连接复杂度相对高；具体连接能力与市场覆盖需逐一核实 |
| [Backtrader](https://github.com/mementum/backtrader) | Python 回测与交易框架；社区常用的轻量策略原型基础 | MVP 快速理解回测 API 或轻量试验 | 维护活跃度/适配器状态需在选型时核实；不建议以此作为平台主干未经验证 |
| [Zipline Reloaded](https://github.com/stefan-jansen/zipline-reloaded) | Python 事件驱动回测器，社区维护的 Zipline 延续版本 | 经典策略回测和数据管线参考 | 实盘执行不是其主要优势，数据与环境配置需要评估 |

## AI 交易/金融 Agent 项目

| 项目 | 能力摘要 | 借鉴点 | 产品化限制 |
|---|---|---|---|
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 多角色分析师、牛熊研究、研究经理、交易员和风控角色，通过工作流讨论并输出决策；Apache-2.0 | 研究分工、牛熊论据、风控复核、结构化决策记录；可作为实验性研究工作流参考 | 研究框架不是券商交易平台；LLM 输出有随机性，数据源覆盖/时点质量有限；上游也明确不构成投资建议。只吸收可验证的研究流程，不直接照搬建议/交易输出 |
| [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) | 面向量化研究的自动化 R&D Agent，尤其自动因子挖掘和模型优化；MIT（请在采用时复查仓库许可） | 自动研究/实验循环、因子假设生成、实验记录与基准比较 | 研究生产力工具，不是面向投资者的实时账户 Agent；生成的因子需要严格样本外与泄漏检测 |
| [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 开源金融 NLP/FinLLM 研究，含情绪、关系抽取、问答及 RAG 相关方向 | 中文/英文金融文本分类、情绪提取、领域数据集和评测设计参考 | 多数模型/数据陈旧或任务特定；模型许可、数据许可与泛化能力需分别审查，不能把情绪标签当交易信号 |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 用 Gym 风格市场环境和深度强化学习研究交易策略；MIT | 策略训练环境、训练/验证/交易流水线与成本模型研究 | RL 对奖励、环境、成本和数据拆分很敏感；实验结果容易过拟合，先做离线研究 |
| [FinRL-X](https://github.com/AI4Finance-Foundation/FinRL-Trading) | AI-native 模块化量化交易基础设施，涵盖信号、组合、风险与执行适配 | 关注模块解耦、权重接口和风险覆盖 | 项目较新、功能和生态在演进，适合跟踪和小范围评估，不宜未经验证当成熟生产底座 |

### “Transaction AI”名称核对

截至检索日，未找到与描述完全匹配且广泛认可、名为 **Transaction AI** 的开源量化交易平台。最可能记忆的是 **TradingAgents**（多 Agent 金融交易研究框架）；也可能是泛指 AI trading agent。建议先按 TradingAgents 研究工作流做参考，而不是引入一个尚未确认的项目名。

## AI 检索能力如何搭建

推荐采用“工具查询 + 证据汇总”，而非只把全部数据塞进向量库：

1. **证券和行情查询工具：** `resolve_symbol`, `get_quote`, `get_bars`, `get_fundamentals`, `get_positions`, `get_market_status`。每个返回结构化值、来源、as-of 时间、币种/单位、复权规则和缺失标记。
2. **金融文档检索工具：** 新闻、公告、财报段落和宏观资料先全文检索，再对长文本做向量召回；按证券、市场、发布时间、来源过滤；返回标题/URL/发布日期/段落 ID/片段。
3. **策略工具：** `run_backtest`, `compare_benchmark`, `get_risk_metrics` 只引用已完成任务的工件和版本，禁止模型自行编造绩效。
4. **账户工具：** 默认只读，并带用户/账户范围。工具层本身做授权，不能信任 LLM 传来的账户 ID。
5. **Agent 编排：** schema 化意图解析 → 必要工具并行查询 → 数据归一化和 deterministic 计算 → LLM 按输出 schema 总结 → 引用完整性校验 → 展示结果。
6. **执行工具另设权限边界：** 交易草案经独立风险服务校验，用户确认后才创建一笔短时有效的确认授权；提交后查询券商回执并审计。工具检索/文本内容视为不可信输入，避免文档里的 prompt injection 改变权限。

### 结构化数据与向量检索的分工

| 查询问题 | 主路径 | 例子 |
|---|---|---|
| “账户里有多少现金/TSLA 持仓？” | 账户 API + SQL | 余额、持仓、订单 |
| “NVDA 近 60 个交易日波动率是多少？” | 行情存储 + 确定性计算 | 日线、波动、均线 |
| “最近一季公司对数据中心的风险怎么说？” | 关键词/全文 + 向量召回 + 原文引用 | 财报/公告/电话会 |
| “策略去年扣费后相对基准如何？” | 已保存回测工件 + 结构化指标 | 区间、基准、费用、样本外 |
| “结合持仓有哪些值得继续研究的标的？” | 账户/行情 SQL + 文档检索 + 策略工件 + AI 合成 | 候选观察清单及风险 |

## 适配本项目的建议

1. **第一版先不选“大而全交易平台”。** 仓库是空项目，先确定领域接口、市场范围和数据来源；把数据/研究/执行作为适配器。
2. **研究层评估 Qlib；策略执行层按目标市场比较 vn.py 与 Lean。** 选型前对目标数据集做一套同策略的对比回测，核对交易日历、复权、费用、滑点、停牌和订单状态。
3. **TradingAgents 做研究对照，不做交易授权层。** 可实现类似的多角色分析摘要，但输出必须由实时/历史数据证据锚定，结果进入建议记录并长期复盘。
4. **MVP 用 Postgres + FTS/pgvector + Parquet/DuckDB。** 数据规模和召回指标明确后再拆分检索服务。
5. **先模拟盘，确定券商/市场后再接实盘。** 开源代码许可不等于市场数据、券商接口或金融服务许可。

## 主要来源

- Qlib 官方仓库与介绍：[GitHub](https://github.com/microsoft/qlib)
- vn.py 官方仓库：[GitHub](https://github.com/vnpy/vnpy)
- LEAN 官方仓库：[GitHub](https://github.com/QuantConnect/Lean)
- TradingAgents 官方仓库：[GitHub](https://github.com/TauricResearch/TradingAgents)；论文：[arXiv](https://arxiv.org/abs/2412.20138)
- RD-Agent 官方仓库：[GitHub](https://github.com/microsoft/RD-Agent)
- FinGPT 官方仓库：[GitHub](https://github.com/AI4Finance-Foundation/FinGPT)
- FinRL 官方仓库：[GitHub](https://github.com/AI4Finance-Foundation/FinRL)
- FinRL-X 官方仓库：[GitHub](https://github.com/AI4Finance-Foundation/FinRL-Trading)
- Backtrader：[GitHub](https://github.com/mementum/backtrader)
- Zipline Reloaded：[GitHub](https://github.com/stefan-jansen/zipline-reloaded)
